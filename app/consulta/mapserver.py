"""Motor do MapServer compatível com Esri (item L2-04-f): leitura do mapa do catálogo, desenho da
imagem no servidor, amostras de legenda e as consultas de `identify`/`find`.

Três decisões deste módulo, escritas aqui porque mudam o que o cliente vê:

1. **O serviço é por MAPA, não por camada.** O FeatureServer dos itens irmãos (L2-04-b/c/d) publica
   UMA camada por item de catálogo. O `map image layer` do ArcGIS Pro e a JS API 3.x, ao contrário,
   pedem um serviço com várias camadas numeradas e uma imagem já desenhada. O item de tipo `mapa`
   (documento do L2-01-a) já é exatamente isso: uma lista ordenada de referências a camadas, com
   estilo e extensão. Então o `MapServer` é o documento de mapa, e o identificador de camada é a
   POSIÇÃO no documento (0 é a primeira, que desenha por cima), como o ArcGIS Server faz.

2. **O desenho é do Pillow, no servidor, sem navegador.** `app/catalogo/miniatura.py` já desenha
   feição vetorial com `PIL.ImageDraw` desde o item do catálogo; é o renderizador que a aplicação
   tem. Não se acrescenta dependência (nem motor de tile raster, nem navegador sem cabeça) para
   entregar `export`: o mesmo desenho, com o símbolo do estilo em vez do azul fixo da miniatura.

3. **O símbolo vem do MESMO `drawingInfo` que o FeatureServer publica** (`app/consulta/renderizador.py`).
   Isto é o que garante a cláusula da legenda: a amostra de legenda e o pixel do mapa saem da mesma
   estrutura, então não existe caminho no código em que a legenda diga uma cor e o mapa desenhe outra.
   Quando o estilo não converte, `para_drawing_info` já devolve o `simple` cinza com `_conversao`
   dizendo por quê — a legenda mostra essa mesma classe única, nunca uma cor inventada.

Referência: developers.arcgis.com, "Map service", "Export map", "Identify (map service)",
"Legend (map service)" e "Find" (acesso em 2026-09-08)."""

from __future__ import annotations

import io
import json
import math

from PIL import Image, ImageDraw

from app import limites
from app.consulta import campos as campos_mod
from app.consulta import renderizador, where_ast
from app.erros import ErroAPI

# Unidades da Esri: `width`/`size` de símbolo vêm em PONTOS (1/72 de polegada). O `dpi` do pedido é o
# que converte ponto em pixel — é por isso que a mesma imagem a 300 dpi sai com traço mais grosso.
PONTO_POR_POLEGADA = 72.0
DPI_PADRAO = 96.0
FUNDO_OPACO = (255, 255, 255, 255)
FUNDO_TRANSPARENTE = (255, 255, 255, 0)
LEGENDA_LADO = 20  # amostra quadrada de 20 px, o tamanho que o ArcGIS Server usa por padrão

FORMATOS_IMAGEM = {
    "png": ("PNG", "image/png", True),
    "png8": ("PNG", "image/png", True),
    "png24": ("PNG", "image/png", True),
    "png32": ("PNG", "image/png", True),
    "jpg": ("JPEG", "image/jpeg", False),
    "jpeg": ("JPEG", "image/jpeg", False),
    "pdf": ("PDF", "application/pdf", False),
}


# ------------------------------------------------------------------ leitura do documento de mapa
def mapa_do_item(cur, item_id: str) -> dict:
    """Item de tipo `mapa` visível para o contexto atual. A RLS de `plat.item` é quem decide: item de
    outro inquilino e item inexistente dão a MESMA resposta (404), como manda o contrato de erro."""
    cur.execute(
        "SELECT id, titulo, resumo, dados FROM plat.item "
        "WHERE id = %s::uuid AND tipo = 'mapa' AND apagado_em IS NULL",
        (item_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "mapa_nao_encontrado", "item inexistente, não é mapa, ou sem permissão")
    return r


def _estilo_do_corpo(corpo) -> dict | None:
    """`estilo` de uma camada do documento pode vir embutido (`{"embutido": {...}}`) ou por referência
    a um item de estilo; aqui só o embutido é lido, a referência é resolvida em `camadas_do_mapa`."""
    if isinstance(corpo, dict) and isinstance(corpo.get("embutido"), dict):
        return corpo["embutido"]
    return None


def camadas_do_mapa(cur, mapa: dict) -> list[dict]:
    """As camadas do documento na ordem em que o mapa as declara, já resolvidas contra o catálogo.

    Camada cuja referência a RLS não deixa ler simplesmente NÃO ENTRA na lista — o mapa de um
    inquilino nunca desenha dado de outro, e o cliente vê um serviço com menos camadas, não um erro.
    """
    corpo = ((mapa.get("dados") or {}).get("corpo")) or {}
    refs = []
    for c in corpo.get("camadas") or []:
        if isinstance(c, dict) and isinstance(c.get("ref"), str):
            refs.append(c)
    if not refs:
        return []
    ids = [c["ref"] for c in refs]
    cur.execute(
        "SELECT id::text AS id, titulo, tipo, dados FROM plat.item "
        "WHERE id = ANY(%s::uuid[]) AND apagado_em IS NULL",
        (ids,),
    )
    achados = {r["id"]: r for r in cur.fetchall()}
    # estilos referenciados pelo documento (um pedido só para todos)
    estilo_ids = [
        c["estilo"]["ref"] for c in refs
        if isinstance(c.get("estilo"), dict) and isinstance(c["estilo"].get("ref"), str)
    ]
    estilos: dict[str, dict] = {}
    if estilo_ids:
        cur.execute(
            "SELECT id::text AS id, dados FROM plat.item WHERE id = ANY(%s::uuid[]) "
            "AND tipo = 'estilo' AND apagado_em IS NULL",
            (estilo_ids,),
        )
        estilos = {r["id"]: r for r in cur.fetchall()}

    saida: list[dict] = []
    for c in refs:
        item = achados.get(c["ref"])
        if item is None or item["tipo"] != "camada_vetorial":
            continue
        dados = item["dados"] or {}
        if not (dados.get("schema") and dados.get("tabela") and dados.get("srid")):
            continue
        corpo_estilo = _estilo_do_corpo(c.get("estilo"))
        if corpo_estilo is None and isinstance(c.get("estilo"), dict) and c["estilo"].get("ref") in estilos:
            corpo_estilo = ((estilos[c["estilo"]["ref"]]["dados"] or {}).get("corpo"))
        camada_ml = renderizador_camada(corpo_estilo)
        if camada_ml is None:
            camada_ml = _estilo_ligado_a_camada(cur, item["id"])
        saida.append({
            "id": len(saida),
            "nome": c.get("titulo") or item["titulo"] or item["id"],
            "ref": item["id"],
            "schema": dados["schema"],
            "tabela": dados["tabela"],
            "srid": int(dados["srid"]),
            "geometria": dados.get("geometria"),
            "visivel": bool(c.get("visivel", True)),
            "opacidade": c.get("opacidade", 1),
            "drawing_info": renderizador.para_drawing_info(camada_ml),
        })
    return saida


def renderizador_camada(corpo) -> dict | None:
    """Primeira camada MapLibre do corpo de estilo — a mesma leitura que o descritor do FeatureServer
    faz (`rotas_servico._camada_maplibre`), importada aqui por função para não duplicar a regra."""
    from app.consulta import rotas_servico

    return rotas_servico._camada_maplibre(corpo)  # noqa: SLF001 — mesma família, uma regra só


def _estilo_ligado_a_camada(cur, item_id: str) -> dict | None:
    from app.consulta import rotas_servico

    return rotas_servico._estilo_da_camada(cur, item_id)  # noqa: SLF001 — mesma família, uma regra só


# ------------------------------------------------------------------ símbolo e classe
def _campo_do_renderer(renderer: dict) -> str | None:
    if renderer.get("type") == "uniqueValue":
        return renderer.get("field1")
    if renderer.get("type") == "classBreaks":
        return renderer.get("field")
    return None


def classes(drawing_info: dict) -> list[dict]:
    """As classes do renderer, na ordem em que a legenda as mostra: [{"label","symbol","valor",
    "minimo","maximo"}]. Renderer `simple` tem UMA classe — é a resposta certa, não uma legenda vazia."""
    renderer = (drawing_info or {}).get("renderer") or {}
    tipo = renderer.get("type")
    if tipo == "uniqueValue":
        saida = [
            {"label": i.get("label") or i.get("value") or "", "symbol": i["symbol"],
             "valor": i.get("value"), "minimo": None, "maximo": None}
            for i in renderer.get("uniqueValueInfos") or []
        ]
        if renderer.get("defaultSymbol"):
            saida.append({"label": renderer.get("defaultLabel") or "outros",
                          "symbol": renderer["defaultSymbol"], "valor": None,
                          "minimo": None, "maximo": None})
        return saida
    if tipo == "classBreaks":
        return [
            {"label": i.get("label") or "", "symbol": i["symbol"], "valor": None,
             "minimo": i.get("classMinValue"), "maximo": i.get("classMaxValue")}
            for i in renderer.get("classBreakInfos") or []
        ]
    return [{"label": renderer.get("label") or "", "symbol": renderer.get("symbol") or {},
             "valor": None, "minimo": None, "maximo": None}]


def simbolo_de(drawing_info: dict, valor) -> dict:
    """Símbolo de UMA feição, pelo valor do campo do renderer. Mesma escolha que o cliente Esri faria
    com o `drawingInfo` que este servidor publica — é o que impede a imagem de divergir da legenda."""
    renderer = (drawing_info or {}).get("renderer") or {}
    tipo = renderer.get("type")
    if tipo == "uniqueValue":
        alvo = "" if valor is None else str(valor)
        for i in renderer.get("uniqueValueInfos") or []:
            if str(i.get("value")) == alvo:
                return i["symbol"]
        return renderer.get("defaultSymbol") or {}
    if tipo == "classBreaks":
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return {}
        infos = renderer.get("classBreakInfos") or []
        for i in infos:
            maximo = i.get("classMaxValue")
            if maximo is None or v <= float(maximo):
                return i["symbol"]
        return infos[-1]["symbol"] if infos else {}
    return renderer.get("symbol") or {}


def _rgba(cor, padrao=(128, 128, 128, 255)) -> tuple[int, int, int, int]:
    if not isinstance(cor, (list, tuple)) or len(cor) < 3:
        return padrao
    r, g, b = (int(max(0, min(255, c))) for c in cor[:3])
    a = int(max(0, min(255, cor[3]))) if len(cor) > 3 else 255
    return (r, g, b, a)


def _px(pontos, dpi: float, minimo: float = 1.0) -> int:
    try:
        v = float(pontos)
    except (TypeError, ValueError):
        v = 1.0
    return max(int(minimo), int(round(v * dpi / PONTO_POR_POLEGADA)))


# ------------------------------------------------------------------ desenho
class Tela:
    """Sistema de coordenadas do desenho: extensão do mapa (na referência espacial de saída) para
    pixel. Sem estado de banco — é aritmética pura, e por isso é testável sozinha."""

    def __init__(self, bbox: tuple[float, float, float, float], largura: int, altura: int):
        self.xmin, self.ymin, self.xmax, self.ymax = bbox
        self.largura, self.altura = largura, altura
        self.dx = (self.xmax - self.xmin) or 1e-12
        self.dy = (self.ymax - self.ymin) or 1e-12

    def ponto(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.xmin) / self.dx * self.largura,
                self.altura - (y - self.ymin) / self.dy * self.altura)

    @property
    def tolerancia(self) -> float:
        """Metade de um pixel na unidade do mapa: é a tolerância de simplificação que não muda o
        desenho (o vértice removido cairia dentro do mesmo pixel)."""
        return min(self.dx / max(self.largura, 1), self.dy / max(self.altura, 1)) / 2


def _desenhar_geometria(draw: ImageDraw.ImageDraw, geom: dict, tela: Tela, simbolo: dict, dpi: float) -> None:
    tipo = geom.get("type")
    coords = geom.get("coordinates") or []
    if tipo in ("Point", "MultiPoint"):
        pontos = [coords] if tipo == "Point" else coords
        raio = max(1, _px(simbolo.get("size", 8.0), dpi) // 2)
        cor = _rgba(simbolo.get("color"))
        contorno = _rgba((simbolo.get("outline") or {}).get("color"), (110, 110, 110, 255))
        for p in pontos:
            x, y = tela.ponto(p[0], p[1])
            draw.ellipse((x - raio, y - raio, x + raio, y + raio), fill=cor, outline=contorno)
        return
    if tipo in ("LineString", "MultiLineString"):
        linhas = [coords] if tipo == "LineString" else coords
        cor = _rgba(simbolo.get("color"))
        largura = _px(simbolo.get("width", 1.0), dpi)
        for linha in linhas:
            pts = [tela.ponto(p[0], p[1]) for p in linha]
            if len(pts) > 1:
                draw.line(pts, fill=cor, width=largura, joint="curve")
        return
    if tipo in ("Polygon", "MultiPolygon"):
        poligonos = [coords] if tipo == "Polygon" else coords
        preenche = _rgba(simbolo.get("color"))
        borda_simb = simbolo.get("outline") or {}
        borda = _rgba(borda_simb.get("color"), (110, 110, 110, 255))
        largura = _px(borda_simb.get("width", 0.4), dpi)
        for pol in poligonos:
            for k, anel in enumerate(pol):
                pts = [tela.ponto(p[0], p[1]) for p in anel]
                if len(pts) < 3:
                    continue
                if k == 0:
                    draw.polygon(pts, fill=preenche, outline=borda, width=largura)
                else:  # buraco: recorta com o fundo, depois redesenha a borda
                    draw.polygon(pts, fill=(255, 255, 255, 0), outline=borda, width=largura)
        return
    if tipo == "GeometryCollection":
        for g in geom.get("geometries") or []:
            _desenhar_geometria(draw, g, tela, simbolo, dpi)


def desenhar(feicoes_por_camada: list[tuple[dict, list[tuple[dict, object]]]], tela: Tela,
             dpi: float, transparente: bool) -> Image.Image:
    """Camadas na ordem do documento (0 primeiro). O desenho vai do FIM para o começo, para que a
    camada 0 termine por cima — é a ordem de empilhamento do ArcGIS Server."""
    fundo = FUNDO_TRANSPARENTE if transparente else FUNDO_OPACO
    imagem = Image.new("RGBA", (tela.largura, tela.altura), fundo)
    for camada, feicoes in reversed(feicoes_por_camada):
        camada_img = Image.new("RGBA", (tela.largura, tela.altura), (255, 255, 255, 0))
        draw = ImageDraw.Draw(camada_img, "RGBA")
        for geom, valor in feicoes:
            _desenhar_geometria(draw, geom, tela, simbolo_de(camada["drawing_info"], valor), dpi)
        opacidade = camada.get("opacidade", 1)
        try:
            fator = min(max(float(opacidade), 0.0), 1.0)
        except (TypeError, ValueError):
            fator = 1.0
        if fator < 1.0:
            alfa = camada_img.getchannel("A").point(lambda a, f=fator: int(a * f))
            camada_img.putalpha(alfa)
        imagem = Image.alpha_composite(imagem, camada_img)
    return imagem


def bytes_da_imagem(imagem: Image.Image, formato: str) -> tuple[bytes, str]:
    """Codifica na forma pedida. `png32` é RGBA; `jpg` e `pdf` não têm canal alfa e recebem o fundo
    branco por baixo (achatar em vez de recusar é o que o ArcGIS Server faz)."""
    nome, tipo_conteudo, tem_alfa = FORMATOS_IMAGEM[formato]
    saida = io.BytesIO()
    if tem_alfa and formato in ("png", "png32"):
        imagem.save(saida, format=nome, optimize=True)
    elif tem_alfa:
        imagem.convert("P", palette=Image.Palette.ADAPTIVE).save(saida, format=nome, optimize=True)
    else:
        fundo = Image.new("RGB", imagem.size, (255, 255, 255))
        fundo.paste(imagem, (0, 0), imagem)
        opcoes = {"quality": 90} if nome == "JPEG" else {"resolution": 96.0}
        fundo.save(saida, format=nome, **opcoes)
    return saida.getvalue(), tipo_conteudo


def amostra_de_legenda(simbolo: dict, geometria: str | None, dpi: float = DPI_PADRAO) -> bytes:
    """PNG quadrado de 20 px com o símbolo desenhado — a amostra que a operação `legend` devolve em
    `imageData`. O desenho é o MESMO `_desenhar_geometria` da imagem do mapa: uma classe da legenda
    não pode sair com cor diferente da que o mapa usa para aquela classe."""
    lado = LEGENDA_LADO
    imagem = Image.new("RGBA", (lado, lado), (255, 255, 255, 0))
    draw = ImageDraw.Draw(imagem, "RGBA")
    tela = Tela((0.0, 0.0, 1.0, 1.0), lado, lado)
    familia = (geometria or "").lower()
    if "point" in familia:
        geom = {"type": "Point", "coordinates": [0.5, 0.5]}
    elif "line" in familia:
        geom = {"type": "LineString", "coordinates": [[0.1, 0.2], [0.4, 0.75], [0.9, 0.3]]}
    else:
        geom = {"type": "Polygon", "coordinates": [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9], [0.1, 0.1]]]}
    _desenhar_geometria(draw, geom, tela, simbolo, dpi)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return saida.getvalue()


# ------------------------------------------------------------------ leitura das feições
def _tamanho_do_pedido(size: str | None) -> tuple[int, int]:
    partes = (size or "400,400").split(",")
    if len(partes) != 2:
        raise ErroAPI(400, "size_invalido", "size precisa ser 'largura,altura'")
    try:
        largura, altura = int(float(partes[0])), int(float(partes[1]))
    except ValueError as e:
        raise ErroAPI(400, "size_invalido", "size precisa ser 'largura,altura' em pixels") from e
    if largura < 1 or altura < 1:
        raise ErroAPI(400, "size_invalido", "largura e altura precisam ser positivas")
    if largura > limites.MAPSERVER_LADO_MAX or altura > limites.MAPSERVER_LADO_MAX:
        raise ErroAPI(400, "imagem_grande_demais",
                      f"lado acima de {limites.MAPSERVER_LADO_MAX} px (limite declarado do serviço)")
    if largura * altura > limites.MAPSERVER_PIXELS_MAX:
        raise ErroAPI(400, "imagem_grande_demais",
                      f"imagem acima de {limites.MAPSERVER_PIXELS_MAX} pixels (limite declarado do serviço)")
    return largura, altura


def tamanho_do_pedido(size: str | None) -> tuple[int, int]:
    return _tamanho_do_pedido(size)


def dpi_do_pedido(valor) -> float:
    if valor in (None, ""):
        return DPI_PADRAO
    try:
        dpi = float(valor)
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "dpi_invalido", "dpi precisa ser número") from e
    if dpi <= 0 or dpi > limites.MAPSERVER_DPI_MAX:
        raise ErroAPI(400, "dpi_invalido", f"dpi fora da faixa 1..{limites.MAPSERVER_DPI_MAX}")
    return dpi


def bbox_do_pedido(bruto: str | None) -> tuple[float, float, float, float]:
    partes = (bruto or "").split(",")
    if len(partes) != 4:
        raise ErroAPI(400, "bbox_invalido", "bbox precisa ser 'xmin,ymin,xmax,ymax'")
    try:
        xmin, ymin, xmax, ymax = (float(p) for p in partes)
    except ValueError as e:
        raise ErroAPI(400, "bbox_invalido", "bbox precisa ter quatro números") from e
    if not (math.isfinite(xmin) and math.isfinite(ymin) and math.isfinite(xmax) and math.isfinite(ymax)):
        raise ErroAPI(400, "bbox_invalido", "bbox com valor não finito")
    if xmax <= xmin or ymax <= ymin:
        raise ErroAPI(400, "bbox_invalido", "bbox invertido: xmax/ymax precisam ser maiores que xmin/ymin")
    return (xmin, ymin, xmax, ymax)


def selecao_de_camadas(camadas: list[dict], layers: str | None) -> list[dict]:
    """`layers` do protocolo: `show:0,2`, `hide:1`, `include:`/`exclude:` (tratados como show/hide
    sobre a visibilidade do documento). Sem o parâmetro vale a visibilidade declarada no mapa."""
    if not layers:
        return [c for c in camadas if c["visivel"]]
    bruto = layers.strip()
    if ":" not in bruto:
        raise ErroAPI(400, "layers_invalido", "layers precisa ser 'show:0,1', 'hide:2', 'include:' ou 'exclude:'")
    modo, lista = bruto.split(":", 1)
    modo = modo.strip().lower()
    if modo not in ("show", "hide", "include", "exclude"):
        raise ErroAPI(400, "layers_invalido", f"modo de layers não reconhecido: {modo!r}")
    ids = set()
    for parte in lista.split(","):
        parte = parte.strip()
        if parte == "":
            continue
        if not parte.isdigit():
            raise ErroAPI(400, "layers_invalido", "identificador de camada precisa ser inteiro")
        ids.add(int(parte))
    if modo in ("show", "include"):
        return [c for c in camadas if c["id"] in ids or (modo == "include" and c["visivel"])]
    return [c for c in camadas if c["id"] not in ids and c["visivel"]]


def defs_por_camada(layer_defs: str | None) -> dict[int, str]:
    """`layerDefs` como JSON (`{"0":"pop > 10"}`) ou na forma antiga `0:pop > 10;1:...`."""
    if not layer_defs:
        return {}
    bruto = layer_defs.strip()
    saida: dict[int, str] = {}
    if bruto.startswith("{"):
        try:
            obj = json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "layerdefs_invalido", "layerDefs não é JSON válido") from e
        if not isinstance(obj, dict):
            raise ErroAPI(400, "layerdefs_invalido", "layerDefs JSON precisa ser um objeto")
        itens = obj.items()
    else:
        itens = []
        for parte in bruto.split(";"):
            if parte.strip() == "":
                continue
            if ":" not in parte:
                raise ErroAPI(400, "layerdefs_invalido", "layerDefs antigo é 'id:expressao;id:expressao'")
            chave, valor = parte.split(":", 1)
            itens.append((chave, valor))
    for chave, valor in itens:
        chave = str(chave).strip()
        if not chave.isdigit():
            raise ErroAPI(400, "layerdefs_invalido", "identificador de camada em layerDefs precisa ser inteiro")
        saida[int(chave)] = str(valor)
    return saida


def where_compilado(expressao: str | None, colunas: dict) -> tuple[str, list]:
    """Compila a expressão do cliente pelo MESMO analisador da operação `query` (`where_ast`): lista
    branca de colunas, sem concatenação de texto do cliente no SQL. Expressão fora da gramática é
    400, nunca chega ao banco — é a resposta à refutação do `layerDefs` com SQL injetado."""
    if not expressao or expressao.strip() in ("", "1=1"):
        return "TRUE", []
    try:
        c = where_ast.compilar_where(expressao, colunas)
    except where_ast.ErroWhere as e:
        raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
    return c.sql, list(c.params)


def feicoes_para_desenho(cur, camada: dict, tela: Tela, srid_saida: int, where_extra: str | None,
                         teto: int) -> list[tuple[dict, object]]:
    """Geometria já reprojetada para a referência de saída e simplificada a meio pixel, com o valor
    do campo do renderer ao lado. O recorte usa `&&` sobre a coluna nativa, que é o que usa o índice
    GIST — reprojetar a coluna inteira antes de filtrar mataria o índice."""
    meta = campos_mod.campos_da_camada(cur, camada["schema"], camada["tabela"])
    colunas = campos_mod.lista_branca(meta)
    where_sql, where_params = where_compilado(where_extra, colunas)
    campo = _campo_do_renderer((camada["drawing_info"] or {}).get("renderer") or {})
    coluna_valor = colunas.get(campo) if campo else None
    selecao_valor = f", {coluna_valor} AS __valor" if coluna_valor else ", NULL AS __valor"
    sql = (
        f'SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology('
        f'  ST_Transform("geom", %s), %s), 8) AS __gj{selecao_valor} '
        f'FROM "{camada["schema"]}"."{camada["tabela"]}" '
        f'WHERE "geom" IS NOT NULL AND {where_sql} '
        f'  AND "geom" && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, %s), %s) '
        f'LIMIT %s'
    )  # noqa: S608 — where_sql vem de where_ast (lista branca), nunca do texto do cliente
    params = [srid_saida, tela.tolerancia, *where_params,
              tela.xmin, tela.ymin, tela.xmax, tela.ymax, srid_saida, camada["srid"], teto]
    cur.execute(sql, params)
    saida = []
    for r in cur.fetchall():
        if r["__gj"]:
            saida.append((json.loads(r["__gj"]), r["__valor"]))
    return saida
