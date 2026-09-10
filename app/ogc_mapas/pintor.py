"""Rasterizador próprio das camadas vetoriais (item L2-04-i). Pillow, sem mapnik e sem navegador.

Por que não o motor de render do L2-12-a: aquele motor tira foto de uma página com chromium
(`app/render/motor.py`) e hoje recusa documento com camada (`501 render_de_camada_nao_suportado`);
além disso um pedido WMS tem de responder em menos de 1,5 s com o processo quente, e subir uma página
por pedido não cabe nesse orçamento. Aqui a imagem sai de geometria + estilo direto, com o mesmo
vocabulário de estilo do L2-02-a (`plat_construtor` -> classes com cor e teste), então a cor de uma
feição no WMS é a MESMA que o visualizador usa.

Antisserrilhado por superamostragem: desenha em 2x e reduz com LANCZOS quando a imagem cabe no
orçamento de memória (`MAX_PX_SUPERAMOSTRA`); acima disso desenha em 1x (a diferença visual em imagem
grande é pequena e a memória, não). O canal alfa é zero fora das feições quando `transparente`.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

MAX_LADO = 4096            # teto do WMS (o pedido acima disto é recusado pela rota)
MAX_PX_SUPERAMOSTRA = 2_000_000
FORMATOS = {
    "image/png": "png", "image/png; mode=8bit": "png8", "image/png8": "png8",
    "image/jpeg": "jpeg", "image/gif": "gif",
}
FUNDO_OPACO = (255, 255, 255)


class ErroPintura(ValueError):
    pass


def _cor(valor, alfa: int = 255):
    """`#rrggbb`, `#rgb` ou `rgba(...)` -> tupla RGBA. Cor desconhecida vira cinza (nunca explode a imagem)."""
    if isinstance(valor, (list, tuple)) and len(valor) in (3, 4):
        c = list(valor) + ([alfa] if len(valor) == 3 else [])
        return tuple(int(v) for v in c)
    s = str(valor or "").strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alfa)
        if len(h) == 8:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    if s.startswith("rgb"):
        partes = s[s.find("(") + 1:s.rfind(")")].split(",")
        try:
            nums = [float(p.strip()) for p in partes]
        except ValueError:
            return (128, 128, 128, alfa)
        if len(nums) == 4:
            return (int(nums[0]), int(nums[1]), int(nums[2]), int(nums[3] * 255))
        if len(nums) == 3:
            return (int(nums[0]), int(nums[1]), int(nums[2]), alfa)
    return (128, 128, 128, alfa)


def _projetor(caixa, largura: int, altura: int, escala: int = 1):
    """Fecha sobre a caixa e devolve (x, y) do CRS -> pixel. Eixo Y do mundo cresce para cima; o da
    imagem, para baixo."""
    minx, miny, maxx, maxy = caixa
    sx = (largura * escala) / (maxx - minx)
    sy = (altura * escala) / (maxy - miny)

    def para_pixel(x, y):
        return ((x - minx) * sx, (maxy - y) * sy)

    return para_pixel


def _aneis(geom, p):
    """Percorre a geometria GeoJSON e devolve [(tipo, [pontos em pixel])] — 'poligono', 'linha', 'ponto'."""
    if not geom:
        return []
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Point":
        return [("ponto", [p(c[0], c[1])])]
    if t == "MultiPoint":
        return [("ponto", [p(x, y)]) for x, y in c]
    if t == "LineString":
        return [("linha", [p(x, y) for x, y in c])]
    if t == "MultiLineString":
        return [("linha", [p(x, y) for x, y in linha]) for linha in c]
    if t == "Polygon":
        return [("poligono", [p(x, y) for x, y in anel]) for anel in c]
    if t == "MultiPolygon":
        saida = []
        for poli in c:
            for anel in poli:
                saida.append(("poligono", [p(x, y) for x, y in anel]))
        return saida
    if t == "GeometryCollection":
        saida = []
        for g in geom.get("geometries", []):
            saida.extend(_aneis(g, p))
        return saida
    return []


def _avaliar(teste, propriedades) -> bool:
    """Avalia o subconjunto de expressão MapLibre que `app/estilos/compilador.py` emite: `==`, `all`,
    `>=`, `<`, `<=`, `>`, sobre `["get", campo]` e `["to-number", ["get", campo]]`. Expressão de outro
    formato devolve False (a feição cai na classe final, que é o padrão do `case` do MapLibre)."""
    if teste is None:
        return True
    if not isinstance(teste, list) or not teste:
        return False
    op = teste[0]
    if op == "all":
        return all(_avaliar(t, propriedades) for t in teste[1:])
    if op == "any":
        return any(_avaliar(t, propriedades) for t in teste[1:])
    if op in ("==", "!=", ">=", "<=", ">", "<"):
        esq = _valor(teste[1], propriedades)
        dir_ = _valor(teste[2], propriedades) if len(teste) > 2 else None
        if esq is None or dir_ is None:
            return op == "!=" and not (esq is None and dir_ is None)
        try:
            if op == "==":
                return esq == dir_ or str(esq) == str(dir_)
            if op == "!=":
                return esq != dir_
            return {">=": esq >= dir_, "<=": esq <= dir_, ">": esq > dir_, "<": esq < dir_}[op]
        except TypeError:
            return False
    return False


def _valor(no, propriedades):
    if isinstance(no, list) and no:
        if no[0] == "get":
            return propriedades.get(no[1])
        if no[0] == "to-number":
            v = _valor(no[1], propriedades)
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        if no[0] == "to-string":
            v = _valor(no[1], propriedades)
            return None if v is None else str(v)
        return None
    return no


def classe_da_feicao(classes: list[dict], propriedades: dict, padrao: bool = True) -> dict | None:
    """A primeira classe cujo teste passa. `padrao=True` (estilo da casa, compilado em `case` do
    MapLibre) devolve a última classe quando nada casa; `padrao=False` (SLD) devolve None e a feição
    não é desenhada — é a semântica do SLD, onde feição sem regra fica de fora do mapa."""
    for c in classes:
        if c.get("teste") is None:
            return c
        if _avaliar(c["teste"], propriedades):
            return c
    if not padrao:
        return None
    return classes[-1] if classes else {"cor": "#4e79a7"}


def pintar(feicoes: list[dict], estilo: dict, caixa, largura: int, altura: int, *,
           transparente: bool = True, formato: str = "png", qualidade: int = 85) -> bytes:
    """Desenha as feições; devolve `(bytes da imagem, número de partes desenhadas)`. `estilo` é
    `{'geometria', 'classes': [{'cor','teste'}], 'simbolo': {...}}` — o vocabulário do L2-02-a."""
    if not (1 <= largura <= MAX_LADO and 1 <= altura <= MAX_LADO):
        raise ErroPintura(f"tamanho fora de 1..{MAX_LADO}: {largura}x{altura}")
    escala = 2 if largura * altura <= MAX_PX_SUPERAMOSTRA else 1
    fundo = (0, 0, 0, 0) if transparente else (*FUNDO_OPACO, 255)
    img = Image.new("RGBA", (largura * escala, altura * escala), fundo)
    desenho = ImageDraw.Draw(img, "RGBA")
    p = _projetor(caixa, largura, altura, escala)
    classes = estilo.get("classes") or [{"cor": "#4e79a7", "teste": None}]
    simbolo = estilo.get("simbolo") or {}
    geometria = estilo.get("geometria") or "poligono"
    opacidade = float(simbolo.get("opacidade", 0.85 if geometria == "poligono" else 1.0))
    alfa = max(0, min(255, int(round(opacidade * 255))))
    largura_traco = max(1, int(round(float(simbolo.get("largura", 1.0)) * escala)))
    raio = max(1, int(round(float(simbolo.get("raio", 4.0)) * escala)))
    cor_contorno = _cor(simbolo["contorno_cor"], 255) if simbolo.get("contorno_cor") else None
    largura_contorno = max(1, int(round(float(simbolo.get("contorno_largura", 1.0)) * escala)))
    padrao = bool(estilo.get("padrao", True))
    desenhadas = 0
    for f in feicoes:
        cls = classe_da_feicao(classes, f.get("propriedades") or {}, padrao)
        if cls is None:
            continue
        cor = _cor(cls.get("cor") or "#4e79a7", alfa)
        for tipo, pontos in _aneis(f.get("geometria"), p):
            if tipo == "poligono" and len(pontos) >= 3:
                desenho.polygon(pontos, fill=cor, outline=cor_contorno or _cor(cls.get("cor"), 255),
                                width=largura_contorno)
            elif tipo == "linha" and len(pontos) >= 2:
                desenho.line(pontos, fill=_cor(cls.get("cor"), 255), width=largura_traco, joint="curve")
            elif tipo == "ponto":
                x, y = pontos[0]
                caixa_ponto = [x - raio, y - raio, x + raio, y + raio]
                desenho.ellipse(caixa_ponto, fill=cor, outline=cor_contorno, width=largura_contorno)
            desenhadas += 1
    if escala > 1:
        img = img.resize((largura, altura), Image.LANCZOS)
    return _codificar(img, formato, transparente, qualidade), desenhadas


def _codificar(img: Image.Image, formato: str, transparente: bool, qualidade: int) -> bytes:
    buf = io.BytesIO()
    if formato == "jpeg":
        img = Image.alpha_composite(Image.new("RGBA", img.size, (*FUNDO_OPACO, 255)), img).convert("RGB")
        img.save(buf, "JPEG", quality=qualidade, optimize=True)
    elif formato in ("png8", "gif"):
        # paleta com transparência: converte com `ADAPTIVE` reservando o índice 0 para o fundo
        conv = img.convert("RGBA")
        palete = conv.convert("P", palette=Image.ADAPTIVE, colors=255)
        if transparente:
            alfa = conv.getchannel("A")
            mascara = alfa.point(lambda v: 255 if v <= 8 else 0)
            palete.paste(255, mascara)
            palete.info["transparency"] = 255
        palete.save(buf, "GIF" if formato == "gif" else "PNG", optimize=True,
                    **({"transparency": 255} if transparente else {}))
    else:
        (img if transparente else img.convert("RGB")).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def imagem_vazia(largura: int, altura: int, transparente: bool, formato: str) -> bytes:
    fundo = (0, 0, 0, 0) if transparente else (*FUNDO_OPACO, 255)
    return _codificar(Image.new("RGBA", (largura, altura), fundo), formato, transparente, 85)
