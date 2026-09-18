"""Predefinições de renderização e legenda (item L1-02-f-predefinicoes-de-renderizacao-e-legenda).

Duas famílias, uma resolução (`resolver`) que devolve sempre a mesma forma (`Resolvido`):

  FÁBRICA (`FABRICA`, este módulo) — 6 predefinições fixas, código puro, sempre válidas por
  construção, servidas para QUALQUER item do QUALQUER inquilino que tenha bandas suficientes (sem
  linha de banco: replicar o mesmo JSON por inquilino seria o "número digitado" que a casa proíbe).

  CUSTOM (`plat.render_predefinicao`, migração 20260910T1620) — o que um inquilino nomeia e guarda
  para UM item seu; validada por `docs/esquemas/renderizacao-v1.json` (Draft 2020-12, mesmo padrão
  de `app/catalogo/tipos.py`) mais a checagem "a banda pedida existe no item" (JSON Schema não sabe
  contar banda de um item específico).

Decisões de escopo (deixadas por escrito porque o portão do item cita coisa que a casa ainda não
tem):
  - NDVI/NDWI/NBR usam a gramática de expressão JÁ EXISTENTE em `app/imagens/tiles.py` (numexpr
    restrito, item L1-02). Não é uma linguagem de expressão livre por predefinição do usuário —
    isso é o item L1-12 (pendente); aqui as 3 expressões são FIXAS, escolhidas em código.
  - a convenção de banda (1=azul, 2=verde, 3=vermelho, 4=infravermelho próximo) é a MESMA do COG
    sintético de teste da suíte (`tests/api/imagens/apoio_raster.py`); a ingestão desta plataforma
    não grava `eo:bands`/`common_name` (conferido em `app/imagens/ingestao.py`), então não há como
    resolver banda por nome — só por índice, como o resto da casa já faz (`bandas=3,2,1` no XYZ).
  - NBR de verdade precisa de banda SWIR; nenhum item desta instalação a tem marcada. A predefinição
    `nbr-aproximado` usa a banda 1 como substituta só para exercitar o mecanismo (índice normalizado
    + rampa de cor) — vem com `parcial=True` em toda resposta que a usa, e a descrição do preset diz
    isso em português. Nunca é citada como NBR real.
  - esticamento "percentil" é uma APROXIMAÇÃO normal a partir de média/desvio-padrão (`NormalDist`,
    stdlib) — a casa guarda min/max/mean/stddev por banda (`raster:bands.statistics`), não histograma;
    recalcular por pixel violaria a regra do item ("usa a estatística que já está no item, sem
    recalcular").
  - "relevo-sombreado" calcula hillshade de verdade (gradiente numpy, fórmula padrão azimute/altitude)
    dentro do ladrilho/recorte pedido — sem acesso a pixel vizinho fora dele, então pode haver
    descontinuidade sutil na borda entre ladrilhos adjacentes (visualização, não análise de declive).
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import rasterio
from jsonschema import Draft202012Validator
from rio_tiler.io import Reader

from app.erros import ErroAPI
from app.imagens import tiles

ROOT = Path(__file__).resolve().parents[2]
ESQUEMA_PATH = ROOT / "docs" / "esquemas" / "renderizacao-v1.json"
_ESQUEMA = json.loads(ESQUEMA_PATH.read_text())
_VALIDADOR = Draft202012Validator(_ESQUEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)

RESAMPLINGS = ("nearest", "bilinear", "cubic", "cubic_spline", "lanczos", "average", "mode", "gauss", "rms")

# ---------------------------------------------------------------------------- fábrica (6 predefinições)
FABRICA: dict[str, dict[str, Any]] = {
    "rgb-natural": {
        "titulo": "RGB natural",
        "descricao": "as 3 primeiras bandas do asset científico, na ordem em que a ingestão gravou "
                    "(a mesma suposição que o ladrilho XYZ já faz hoje sem parâmetro nenhum), esticadas "
                    "pelo percentil 2-98 aproximado da estatística do item.",
        "bandas": [1, 2, 3], "min_bandas": 3, "expressao": None, "colormap": None,
        "esticamento": {"tipo": "percentil", "percentil_baixo": 2.0, "percentil_alto": 98.0},
    },
    "falsa-cor-nir": {
        "titulo": "Falsa cor (infravermelho-vermelho-verde)",
        "descricao": "banda 4 (infravermelho próximo, convenção desta plataforma) no canal vermelho, "
                    "banda 3 no verde, banda 2 no azul — a composição clássica de vegetação; exige item "
                    "com 4 bandas ou mais.",
        "bandas": [4, 3, 2], "min_bandas": 4, "expressao": None, "colormap": None,
        "esticamento": {"tipo": "percentil", "percentil_baixo": 2.0, "percentil_alto": 98.0},
    },
    "ndvi": {
        "titulo": "NDVI (índice de vegetação por diferença normalizada)",
        "descricao": "(banda4 − banda3) / (banda4 + banda3); banda4 = infravermelho próximo, "
                    "banda3 = vermelho.",
        "min_bandas": 4, "expressao": "(b4-b3)/(b4+b3)", "colormap": "rdylgn",
        "esticamento": {"tipo": "explicito", "faixas": [[-1.0, 1.0]]},
    },
    "ndwi": {
        "titulo": "NDWI (índice de água por diferença normalizada, McFeeters 1996)",
        "descricao": "(banda2 − banda4) / (banda2 + banda4); banda2 = verde, banda4 = infravermelho "
                    "próximo.",
        "min_bandas": 4, "expressao": "(b2-b4)/(b2+b4)", "colormap": "rdbu",
        "esticamento": {"tipo": "explicito", "faixas": [[-1.0, 1.0]]},
    },
    "nbr-aproximado": {
        "titulo": "NBR aproximado (índice de área queimada) — PARCIAL, sem banda SWIR real",
        "descricao": "PARCIAL: o NBR de verdade é (infravermelho próximo − SWIR) / (infravermelho "
                    "próximo + SWIR); esta instalação não ingere/marca banda SWIR em nenhum item "
                    "(raster:bands sem eo:bands/common_name). Esta predefinição usa a banda 1 como "
                    "substituta só para provar o mecanismo (índice normalizado + rampa de cor) — o "
                    "número devolvido NÃO é NBR real, nunca citar como medição de queimada.",
        "min_bandas": 4, "expressao": "(b4-b1)/(b4+b1)", "colormap": "rdylgn", "parcial": True,
        "esticamento": {"tipo": "explicito", "faixas": [[-1.0, 1.0]]},
    },
    "relevo-sombreado": {
        "titulo": "Relevo sombreado (hillshade)",
        "descricao": "sombreamento analítico (azimute 315°, altitude 45°, fórmula padrão) calculado só "
                    "dentro do ladrilho/recorte pedido, sobre a banda 1 do asset científico como "
                    "elevação — pode haver descontinuidade sutil na borda entre ladrilhos vizinhos "
                    "(sem leitura de pixel fora do recorte); é visualização, não análise de declive.",
        "min_bandas": 1, "hillshade": True, "colormap": None, "esticamento": None,
    },
}
NOMES_FABRICA = tuple(FABRICA)


# ---------------------------------------------------------------------------- validação (predefinição CUSTOM)
def erros_de(corpo: dict) -> list[dict]:
    """Lista [{campo, erro, regra}] (vazia = válido), mesmo formato de app/catalogo/tipos.py::erros_de."""
    saida = []
    for e in sorted(_VALIDADOR.iter_errors(corpo), key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in e.absolute_path)
        saida.append({"campo": caminho or "(raiz)", "erro": e.message[:500], "regra": e.validator})
    return saida


def validar_corpo(corpo: dict) -> None:
    if not isinstance(corpo, dict):
        raise ErroAPI(422, "predefinicao_invalida", "o corpo da predefinição precisa ser um objeto JSON",
                      [{"campo": "(raiz)", "erro": "não é objeto", "regra": "type"}])
    erros = erros_de(corpo)
    if erros:
        raise ErroAPI(422, "predefinicao_invalida",
                      "predefinição fora do esquema (docs/esquemas/renderizacao-v1.json)", erros)
    colormap = corpo.get("colormap")
    if isinstance(colormap, str) and colormap not in tiles.COLORMAPS:
        raise ErroAPI(422, "predefinicao_invalida", f"colormap desconhecido: {colormap}",
                      [{"campo": "colormap", "erro": "fora do catálogo do rio-tiler", "regra": "enum"}])
    if isinstance(colormap, dict):
        # tabela de cor EXPLÍCITA (item L1-02-f): o esquema já garantiu a forma e o teto de 256
        # entradas; aqui se prova que ela de fato COMPILA no motor de render, para que a predefinição
        # nunca seja gravada podendo quebrar só na hora de desenhar o ladrilho.
        try:
            tiles.colormap_de(colormap)
        except tiles.ErroTile as e:
            raise ErroAPI(422, "predefinicao_invalida", str(e),
                          [{"campo": "colormap", "erro": str(e), "regra": "colormap_explicito"}]) from e
    esticamento = corpo.get("esticamento")
    if esticamento and esticamento.get("tipo") == "explicito" and not esticamento.get("faixas"):
        raise ErroAPI(422, "predefinicao_invalida", "esticamento explícito exige 'faixas'",
                      [{"campo": "esticamento.faixas", "erro": "ausente", "regra": "required"}])


# ---------------------------------------------------------------------------- estatística -> faixa concreta
def n_bandas(stac: dict, asset: str) -> int:
    return len(((stac.get("assets") or {}).get(asset) or {}).get("raster:bands") or [])


def _stat_banda(stac: dict, asset: str, indice_1based: int) -> dict | None:
    bandas = ((stac.get("assets") or {}).get(asset) or {}).get("raster:bands") or []
    if indice_1based < 1 or indice_1based > len(bandas):
        return None
    return (bandas[indice_1based - 1] or {}).get("statistics")


def faixa_de_esticamento(
    esticamento: dict | None, stac: dict, asset: str, bandas_saida: list[int],
) -> list[tuple[float, float]] | None:
    """Converte um `esticamento` (tipo + parâmetro) na faixa concreta [(lo,hi), ...] — uma por banda de
    saída —, lendo SÓ a estatística já gravada em `raster:bands.statistics` (nunca abre o COG de novo).
    Devolve None quando não dá para calcular (estatística ausente): quem chama cai no comportamento
    padrão de hoje (min/max do próprio recorte, calculado em `tiles.ladrilho`/`tiles.recorte`)."""
    if not esticamento:
        return None
    tipo = esticamento.get("tipo", "minmax")
    if tipo == "explicito":
        faixas = [tuple(f) for f in (esticamento.get("faixas") or [])]
        if not faixas:
            return None
        if len(faixas) == 1 and len(bandas_saida) > 1:
            return [faixas[0]] * len(bandas_saida)
        return faixas
    saida: list[tuple[float, float]] = []
    for b in bandas_saida:
        st = _stat_banda(stac, asset, b)
        if not st:
            return None
        if tipo == "minmax":
            if st.get("minimum") is None or st.get("maximum") is None:
                return None
            saida.append((float(st["minimum"]), float(st["maximum"])))
        elif tipo == "desvio_padrao":
            if st.get("mean") is None or st.get("stddev") is None:
                return None
            k = float(esticamento.get("desvios", 2.0))
            saida.append((float(st["mean"]) - k * float(st["stddev"]), float(st["mean"]) + k * float(st["stddev"])))
        elif tipo == "percentil":
            if st.get("mean") is None or st.get("stddev") is None:
                return None
            nd = NormalDist()
            lo_p = min(max(float(esticamento.get("percentil_baixo", 2.0)), 0.001), 49.999) / 100
            hi_p = min(max(float(esticamento.get("percentil_alto", 98.0)), 50.001), 99.999) / 100
            z_lo, z_hi = nd.inv_cdf(lo_p), nd.inv_cdf(hi_p)
            media, desvio = float(st["mean"]), float(st["stddev"])
            saida.append((media + z_lo * desvio, media + z_hi * desvio))
        else:
            return None
    return saida


# ---------------------------------------------------------------------------- resolução (fábrica ∪ custom)
@dataclass(frozen=True)
class Resolvido:
    nome: str
    titulo: str
    fabrica: bool
    versao: int | None
    bandas: list[int] | None
    expressao: str | None
    colormap: "str | dict | None"  # nome do catálogo OU tabela de cor explícita (item L1-02-f)
    rescale: list[tuple[float, float]] | None
    nodata_transparente: bool
    opacidade: float
    resampling: str
    hillshade: bool
    parcial: bool
    descricao: str = ""


def listar_fabrica() -> list[dict]:
    return [
        {"nome": nome, "titulo": e["titulo"], "descricao": e.get("descricao", ""), "fabrica": True,
         "min_bandas": e["min_bandas"], "parcial": bool(e.get("parcial")), "hillshade": bool(e.get("hillshade")),
         "colormap": e.get("colormap")}
        for nome, e in FABRICA.items()
    ]


def _resolver_fabrica(nome: str, stac: dict, asset: str) -> Resolvido:
    spec = FABRICA[nome]
    disponiveis = n_bandas(stac, asset)
    if disponiveis < spec["min_bandas"]:
        raise ErroAPI(422, "predefinicao_incompativel",
                      f"a predefinição {nome!r} exige ao menos {spec['min_bandas']} banda(s); o item "
                      f"tem {disponiveis} no asset {asset!r}",
                      {"predefinicao": nome, "min_bandas": spec["min_bandas"], "bandas_do_item": disponiveis})
    bandas = list(spec.get("bandas") or ([1] if spec.get("hillshade") else []))
    if spec.get("expressao"):
        # expressão produz 1 banda DERIVADA (não uma das bandas originais lidas do COG) — a faixa vem
        # do domínio matemático do próprio índice (-1..1, declarado em FABRICA[nome]["esticamento"]),
        # nunca da estatística de pixel bruto (grandeza diferente); por isso passa [1] (uma faixa só).
        rescale = faixa_de_esticamento(spec.get("esticamento"), stac, asset, [1])
    elif spec.get("hillshade"):
        rescale = None
    else:
        rescale = faixa_de_esticamento(spec.get("esticamento"), stac, asset, bandas or [1, 2, 3])
    return Resolvido(
        nome=nome, titulo=spec["titulo"], fabrica=True, versao=None,
        bandas=bandas or None, expressao=spec.get("expressao"), colormap=spec.get("colormap"),
        rescale=rescale, nodata_transparente=True, opacidade=1.0, resampling="nearest",
        hillshade=bool(spec.get("hillshade")), parcial=bool(spec.get("parcial")),
        descricao=spec.get("descricao", ""),
    )


def _e_uuid(valor: str) -> bool:
    """`plat.render_predefinicao.item_id` é uuid (o item do CATÁLOGO). Um `plat.raster_item` de fixture
    de teste antiga pode ter `item_id` texto livre (`item-espelho-1`, fora do catálogo) — nunca tem
    predefinição custom, e um `item_id::uuid` cego nesse caso quebra com 500 (achado ligando este item
    ao WMS/TileJSON da demo: `GetCapabilities` varre todo item ativo do inquilino, catálogo ou não)."""
    import uuid as _uuid_mod

    try:
        _uuid_mod.UUID(str(valor))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _resolver_custom(cur, tenant_id: int, item_id: str, nome: str, stac: dict, asset: str) -> Resolvido:
    if not _e_uuid(item_id):
        raise ErroAPI(404, "predefinicao_inexistente", f"predefinição inexistente para este item: {nome}",
                      {"predefinicao": nome})
    cur.execute(
        "SELECT nome, titulo, corpo, versao FROM plat.render_predefinicao "
        "WHERE tenant_id = %s AND item_id = %s::uuid AND nome = %s AND apagado_em IS NULL",
        (tenant_id, item_id, nome),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "predefinicao_inexistente", f"predefinição inexistente para este item: {nome}",
                      {"predefinicao": nome})
    corpo = r["corpo"]
    bandas = corpo.get("bandas")
    disponiveis = n_bandas(stac, asset)
    maior = max(bandas) if bandas else 0
    if maior > disponiveis:
        raise ErroAPI(422, "predefinicao_incompativel",
                      f"a predefinição {nome!r} referencia a banda {maior}; o item tem {disponiveis} "
                      f"no asset {asset!r}",
                      {"predefinicao": nome, "banda_pedida": maior, "bandas_do_item": disponiveis})
    rescale = faixa_de_esticamento(corpo.get("esticamento"), stac, asset, bandas or [1, 2, 3])
    return Resolvido(
        nome=nome, titulo=r["titulo"], fabrica=False, versao=r["versao"],
        bandas=bandas, expressao=None, colormap=corpo.get("colormap"),
        rescale=rescale, nodata_transparente=bool(corpo.get("nodata_transparente", True)),
        opacidade=float(corpo.get("opacidade", 1.0)), resampling=corpo.get("resampling") or "nearest",
        hillshade=False, parcial=False, descricao=corpo.get("descricao", ""),
    )


def resolver(cur, tenant_id: int, item_id: str, nome: str, stac: dict, asset: str) -> Resolvido:
    """Nome de predefinição -> `Resolvido`. 404 se não existe (nem fábrica, nem custom do item); 422
    `predefinicao_incompativel` se existe mas o item não tem banda suficiente."""
    if nome in FABRICA:
        return _resolver_fabrica(nome, stac, asset)
    return _resolver_custom(cur, tenant_id, item_id, nome, stac, asset)


def padrao_do_item(cur, tenant_id: int, item_id: str) -> tuple[str, int] | None:
    """(nome, versão) da predefinição CUSTOM marcada `padrao` para o item, ou None (sem padrão custom —
    quem chama continua com o comportamento de hoje, sem predefinição nenhuma)."""
    if not _e_uuid(item_id):
        return None
    cur.execute(
        "SELECT nome, versao FROM plat.render_predefinicao "
        "WHERE tenant_id = %s AND item_id = %s::uuid AND padrao AND apagado_em IS NULL LIMIT 1",
        (tenant_id, item_id),
    )
    r = cur.fetchone()
    return (r["nome"], r["versao"]) if r else None


# ---------------------------------------------------------------------------- pós-processamento (opacidade)
def aplicar_opacidade(corpo_png_ou_jpg: bytes, formato: str, opacidade: float) -> bytes:
    """Multiplica o canal alfa por `opacidade` (0..1). Sem alfa (JPEG, ou PNG sem máscara) e
    `opacidade==1.0`: devolve os bytes originais sem decodificar — caminho quente do dia a dia."""
    if opacidade >= 1.0 or formato == "jpg":
        return corpo_png_ou_jpg
    from PIL import Image

    img = Image.open(io.BytesIO(corpo_png_ou_jpg)).convert("RGBA")
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * max(0.0, min(1.0, opacidade))))
    img.putalpha(a)
    buf = io.BytesIO()
    img.save(buf, format="PNG" if formato != "webp" else "WEBP")
    return buf.getvalue()


# ---------------------------------------------------------------------------- relevo sombreado (hillshade)
def _hillshade_uint8(elevacao: np.ndarray, azimute: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    """Fórmula padrão de sombreamento analítico (a mesma usada por `gdaldem hillshade`/ArcGIS): gradiente
    numérico (`np.gradient`, vizinhança 3x3 DENTRO do array recebido — daí a descontinuidade de borda
    entre ladrilhos, declarada na docstring do módulo), depois o produto escalar sol×normal-da-superfície.
    Só dentro do array recebido — não lê pixel fora do ladrilho/recorte pedido."""
    z = elevacao.astype("float64")
    dzdy, dzdx = np.gradient(z)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az_rad = math.radians(azimute)
    alt_rad = math.radians(altitude)
    sombreado = np.sin(alt_rad) * np.cos(slope) + np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect)
    sombreado = np.clip(sombreado, 0.0, 1.0)
    return (sombreado * 255).astype("uint8")


def renderizar_hillshade(
    fonte: tiles.Fonte, *, banda: int, formato: str, resampling: str = "nearest",
    nodata_transparente: bool = True,
    tile: tuple[int, int, int] | None = None,
    parte: tuple[tuple[float, float, float, float], Any, int, int] | None = None,
) -> bytes:
    """Bytes já codificados do relevo sombreado da `banda` — mesmo ladrilho XYZ (`tile=(z,x,y)`) ou
    mesmo recorte arbitrário (`parte=(bbox, crs_obj, width, height)`) do resto do módulo, mas sem passar
    pelo `img.render` do rio-tiler: a máscara vira alfa por PIL diretamente (mesma convenção de
    `img.mask`: 255 = dado válido, 0 = nodata — rio_tiler.models.ImageData.mask, "rasterio dataset mask")."""
    if formato not in tiles.RENDER:
        raise tiles.ErroTile(f"formato de imagem desconhecido: {formato}")
    with rasterio.Env(session=fonte.sessao, **fonte.env):
        with Reader(fonte.caminho, tms=tiles.TMS) as src:
            if tile is not None:
                z, x, y = tile
                try:
                    img = src.tile(x, y, z, tilesize=tiles.TAMANHO, indexes=[banda], resampling_method=resampling)
                except Exception as e:
                    from rio_tiler.errors import TileOutsideBounds

                    if isinstance(e, TileOutsideBounds):
                        raise tiles.ForaDaCobertura(str(e)) from e
                    raise
            else:
                bbox, crs_obj, width, height = parte
                img = src.part(bbox, dst_crs=crs_obj, bounds_crs=crs_obj, indexes=[banda], width=width,
                               height=height, resampling_method=resampling)
    elevacao = img.array[0]
    dados = np.ma.filled(elevacao, np.nanmean(elevacao) if elevacao.size else 0.0)
    sombra = _hillshade_uint8(dados)
    from PIL import Image

    if nodata_transparente:
        base = Image.fromarray(sombra, mode="L").convert("LA")
        alfa = Image.fromarray(img.mask.astype("uint8"), mode="L")
        base.putalpha(alfa)
    else:
        base = Image.fromarray(sombra, mode="L").convert("RGB")
    buf = io.BytesIO()
    base.save(buf, format=tiles.RENDER[formato])
    return buf.getvalue()


# ---------------------------------------------------------------------------- legenda
def _amostras_colormap(nome_colormap, faixa: tuple[float, float], n: int = 5) -> list[dict]:
    if not isinstance(nome_colormap, str):
        return _amostras_explicitas(nome_colormap)
    cm = tiles.colormaps.get(nome_colormap)
    lo, hi = faixa
    saida = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        indice_255 = round(frac * 255)
        rgba = cm.get(indice_255) or cm.get(min(cm.keys(), key=lambda k: abs(k - indice_255)))
        valor = lo + frac * (hi - lo)
        saida.append({"valor": round(valor, 4), "cor": "#%02x%02x%02x" % tuple(rgba[:3])})
    return saida


def _amostras_explicitas(colormap: dict) -> list[dict]:
    """Legenda de tabela de cor explícita: cada entrada vira uma amostra, com o VALOR (ou o intervalo)
    que a produz — a legenda sai da MESMA estrutura que pinta o pixel, nunca de uma segunda tabela."""
    saida = []
    if colormap["tipo"] == "valor":
        for chave, cor in sorted(colormap["entradas"].items(), key=lambda kv: int(kv[0])):
            saida.append({"valor": int(chave), "cor": "#%02x%02x%02x" % tuple(int(c) for c in cor[:3])})
    else:
        for faixa, cor in colormap["entradas"]:
            saida.append({"valor": [float(faixa[0]), float(faixa[1])],
                          "cor": "#%02x%02x%02x" % tuple(int(c) for c in cor[:3])})
    return saida


def legenda_json(resolvido: Resolvido) -> dict:
    """Descrição estruturada da legenda — a MESMA fonte que `legenda_png` desenha (nunca duas fontes de
    verdade, mesma disciplina do compilador de estilo vetorial em app/estilos/compilador.py)."""
    base = {
        "predefinicao": resolvido.nome, "titulo": resolvido.titulo, "descricao": resolvido.descricao,
        "parcial": resolvido.parcial,
    }
    if resolvido.hillshade:
        base["tipo"] = "relevo_sombreado"
        base["nota"] = "tons de cinza: 0 = sombra, 255 = voltado para o sol (azimute 315°, altitude 45°)"
        return base
    if isinstance(resolvido.colormap, dict):
        base["tipo"] = "tabela_de_cor"
        base["colormap"] = resolvido.colormap
        base["faixa"] = list(resolvido.rescale[0]) if resolvido.rescale else None
        base["amostras"] = _amostras_explicitas(resolvido.colormap)
        return base
    if resolvido.colormap and resolvido.rescale:
        base["tipo"] = "rampa"
        base["colormap"] = resolvido.colormap
        base["faixa"] = list(resolvido.rescale[0])
        base["amostras"] = _amostras_colormap(resolvido.colormap, resolvido.rescale[0])
        return base
    base["tipo"] = "composicao_bandas"
    papel = ["vermelho", "verde", "azul"][: len(resolvido.bandas or [])]
    base["bandas"] = [{"canal": p, "banda": b} for p, b in zip(papel, resolvido.bandas or [], strict=False)]
    return base


def legenda_png(resolvido: Resolvido, *, largura: int = 240, altura: int = 56) -> bytes:
    from PIL import Image, ImageDraw

    doc = legenda_json(resolvido)
    img = Image.new("RGBA", (largura, altura), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    if doc["tipo"] == "rampa":
        amostras = doc["amostras"]
        n = len(amostras)
        largura_barra = largura - 10
        for i in range(largura_barra):
            frac = i / max(largura_barra - 1, 1)
            idx = min(int(frac * (n - 1)), n - 2) if n > 1 else 0
            a, b = amostras[idx], amostras[min(idx + 1, n - 1)]
            t = (frac * (n - 1)) - idx if n > 1 else 0.0
            cor = tuple(
                round(int(a["cor"][j:j + 2], 16) * (1 - t) + int(b["cor"][j:j + 2], 16) * t)
                for j in (1, 3, 5)
            )
            draw.line([(5 + i, 8), (5 + i, 28)], fill=(*cor, 255))
        draw.text((5, 32), f"{amostras[0]['valor']}", fill=(0, 0, 0, 255))
        txt = f"{amostras[-1]['valor']}"
        draw.text((largura - 5 - 6 * len(txt), 32), txt, fill=(0, 0, 0, 255))
    elif doc["tipo"] == "tabela_de_cor":
        # tabela de cor explícita (L1-02-f): faixa DISCRETA, um retângulo por entrada, sem interpolar —
        # interpolar entre classes desenharia uma cor que nenhuma classe tem.
        amostras = doc["amostras"][:12]
        larg = max(1, (largura - 10) // max(len(amostras), 1))
        for i, a in enumerate(amostras):
            cor = tuple(int(a["cor"][j:j + 2], 16) for j in (1, 3, 5))
            draw.rectangle([5 + i * larg, 8, 5 + (i + 1) * larg - 1, 28], fill=(*cor, 255))
        rotulo = str(amostras[0]["valor"]) if amostras else ""
        draw.text((5, 32), rotulo, fill=(0, 0, 0, 255))
    elif doc["tipo"] == "relevo_sombreado":
        for i in range(largura - 10):
            v = round(255 * i / max(largura - 11, 1))
            draw.line([(5 + i, 8), (5 + i, 28)], fill=(v, v, v, 255))
        draw.text((5, 32), "sombra", fill=(0, 0, 0, 255))
        draw.text((largura - 40, 32), "sol", fill=(0, 0, 0, 255))
    else:
        cores = {"vermelho": (220, 40, 40), "verde": (40, 160, 60), "azul": (40, 90, 220)}
        x = 5
        for b in doc.get("bandas", []):
            cor = cores.get(b["canal"], (120, 120, 120))
            draw.rectangle([x, 8, x + 24, 28], fill=(*cor, 255))
            draw.text((x, 32), f"{b['canal'][0].upper()}=b{b['banda']}", fill=(0, 0, 0, 255))
            x += 60
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


__all__ = [
    "FABRICA", "NOMES_FABRICA", "RESAMPLINGS", "Resolvido",
    "aplicar_opacidade", "erros_de", "faixa_de_esticamento", "legenda_json", "legenda_png",
    "listar_fabrica", "n_bandas", "padrao_do_item", "renderizar_hillshade", "resolver", "validar_corpo",
]
