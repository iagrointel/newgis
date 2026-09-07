"""Compilador `plat_construtor` -> camadas MapLibre Style Spec v8 (item L2-02-a-modelo-estilo).

Uma função por tipo do construtor. Todas devolvem `(classes, layers)`: `classes` é a lista de
{rotulo, cor, teste} que tanto o `maplibre` quanto a legenda do editor usam (mesma disciplina do
L2-01-mapa-web: legenda e mapa nascem da mesma lista, nunca duas fontes de verdade); `layers` são as
camadas efetivas da Style Spec, sem `sources` (a fonte real é ligada na renderização, nunca gravada
no documento — C2 do L2_CONCEITO).

`campo_ok` valida que todo campo citado está no vocabulário `plat_construtor.campos` (schema
estilo-v1: "referência fora da lista = 422 campo_inexistente"); quem chama fora deste módulo nunca
monta uma expressão `["get", campo]` sem passar por aqui.
"""

from __future__ import annotations

import re

GEOMETRIA_TIPO_LAYER = {"ponto": "circle", "linha": "line", "poligono": "fill", "raster": "raster"}
TIPOS = ("unico", "categoria", "classes", "proporcional", "calor", "agrupamento", "raster")


_DIVISAO_ZERO = re.compile(r"/\s*0(?:\.0*)?(?![0-9.])")


def _re_divisao_por_zero(expressao: str) -> bool:
    return bool(_DIVISAO_ZERO.search(expressao))


class EstiloInvalido(ValueError):
    """A combinação de `plat_construtor` não pode ser compilada (campo ausente, faixa invertida etc.).

    `campo` (opcional) aponta o caminho JSON do problema, para a rota devolver o 422 apontado."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.campo = campo


def _campo_ok(pc: dict, campo: str | None, caminho: str) -> None:
    if campo is None:
        return
    campos = pc.get("campos") or []
    if campos and campo not in campos:
        raise EstiloInvalido(f"campo {campo!r} não está no vocabulário plat_construtor.campos", caminho)


def _comum(id_base: str) -> dict:
    return {"id": id_base}


def _unico(pc: dict) -> tuple[list[dict], dict]:
    s = pc.get("simbolo") or {}
    cor = s.get("cor") or "#4e79a7"
    return [{"rotulo": pc.get("campo") or "todas as feições", "cor": cor, "teste": None}], s


def _categoria(pc: dict) -> tuple[list[dict], dict]:
    campo = pc.get("campo")
    if not campo:
        raise EstiloInvalido("tipo categoria exige plat_construtor.campo", "plat_construtor.campo")
    _campo_ok(pc, campo, "plat_construtor.campo")
    cats = pc.get("categorias") or []
    if not cats:
        raise EstiloInvalido("tipo categoria exige ao menos uma entrada em categorias", "plat_construtor.categorias")
    vistos = set()
    saida = []
    for i, c in enumerate(cats):
        v = c["valor"]
        if v in vistos:
            raise EstiloInvalido(f"valor duplicado em categorias: {v!r}", f"plat_construtor.categorias.{i}.valor")
        vistos.add(v)
        saida.append({"rotulo": c.get("rotulo") or str(v), "cor": c["cor"], "teste": ["==", ["get", campo], v]})
    return saida, {}


def _classes(pc: dict) -> tuple[list[dict], dict]:
    campo = pc.get("campo")
    if not campo:
        raise EstiloInvalido("tipo classes exige plat_construtor.campo", "plat_construtor.campo")
    _campo_ok(pc, campo, "plat_construtor.campo")
    cls = pc.get("classes") or []
    if not cls:
        raise EstiloInvalido("tipo classes exige ao menos uma faixa em classes", "plat_construtor.classes")
    saida = []
    for i, c in enumerate(cls):
        mn, mx = c["min"], c["max"]
        if mn >= mx:
            raise EstiloInvalido(
                f"faixa invertida ou vazia: min ({mn}) >= max ({mx})", f"plat_construtor.classes.{i}"
            )
        ultima = i == len(cls) - 1
        teste = ["all", [">=", ["to-number", ["get", campo]], mn],
                 [">=" if ultima else "<", ["to-number", ["get", campo]], mx] if ultima
                 else ["<", ["to-number", ["get", campo]], mx]]
        rot = c.get("rotulo") or (f"{mn:g} a {mx:g}")
        saida.append({"rotulo": rot, "cor": c["cor"], "teste": teste})
    return saida, {}


def _proporcional(pc: dict) -> tuple[list[dict], dict]:
    campo = pc.get("campo")
    prop = pc.get("proporcional")
    if not campo or not prop:
        raise EstiloInvalido("tipo proporcional exige campo e o bloco proporcional", "plat_construtor.proporcional")
    _campo_ok(pc, campo, "plat_construtor.campo")
    if prop["valor_min"] >= prop["valor_max"]:
        raise EstiloInvalido("proporcional.valor_min precisa ser menor que valor_max", "plat_construtor.proporcional")
    if prop["raio_min"] > prop["raio_max"]:
        raise EstiloInvalido("proporcional.raio_min precisa ser <= raio_max", "plat_construtor.proporcional")
    cor = prop.get("cor") or (pc.get("simbolo") or {}).get("cor") or "#4e79a7"
    return [{"rotulo": campo, "cor": cor, "teste": None}], prop


def _calor(pc: dict) -> tuple[list[dict], dict]:
    if pc.get("geometria") != "ponto":
        raise EstiloInvalido("tipo calor só se aplica a geometria ponto", "plat_construtor.geometria")
    cal = pc.get("calor")
    if not cal:
        raise EstiloInvalido("tipo calor exige o bloco calor", "plat_construtor.calor")
    return [{"rotulo": "densidade", "cor": (cal.get("rampa") or ["#000004", "#fca50a"])[-1], "teste": None}], cal


def _agrupamento(pc: dict) -> tuple[list[dict], dict]:
    if pc.get("geometria") != "ponto":
        raise EstiloInvalido("tipo agrupamento só se aplica a geometria ponto", "plat_construtor.geometria")
    ag = pc.get("agrupamento")
    if not ag or not ag.get("degraus"):
        raise EstiloInvalido("tipo agrupamento exige o bloco agrupamento com degraus", "plat_construtor.agrupamento")
    saida = []
    for i, d in enumerate(ag["degraus"]):
        rot = f"até {d['ate']}" if d.get("ate") is not None else f"acima de {ag['degraus'][i - 1].get('ate', 0)}"
        saida.append({"rotulo": rot, "cor": d["cor"], "teste": None})
    return saida, ag


def _vocabulario_titiler():
    """Importa a fonte única do vocabulário aceito pelo serviço de ladrilho (item L1-02): colormap,
    gramática de expressão e limites de banda. Nunca duplicar esta lista aqui — é exatamente a
    duplicação que deixaria a URL de tile aceitar algo que o TiTiler recusaria (ou pior, o contrário:
    o editor recusar por conta própria e permitir na URL algo que ele nunca validou)."""
    from app.imagens import tiles as titiler
    return titiler


def _raster(pc: dict) -> tuple[list[dict], dict]:
    if pc.get("geometria") != "raster":
        raise EstiloInvalido("tipo raster exige geometria raster", "plat_construtor.geometria")
    pr = pc.get("parametros_raster") or {}
    titiler = _vocabulario_titiler()

    bandas = pr.get("bandas")
    if bandas is not None:
        if not (1 <= len(bandas) <= 4) or any(not isinstance(b, int) or b < 1 or b > 64 for b in bandas):
            raise EstiloInvalido("parametros_raster.bandas exige de 1 a 4 inteiros entre 1 e 64",
                                 "plat_construtor.parametros_raster.bandas")

    expressao = pr.get("expression")
    if expressao is not None:
        ok, motivo = titiler.expressao_valida(expressao)
        if not ok:
            raise EstiloInvalido(f"parametros_raster.expression inválida: {motivo}",
                                 "plat_construtor.parametros_raster.expression")
        # divisão por literal zero: a gramática do TiTiler aceita o token "/0" (é aritmética válida),
        # mas nenhum uso real da casa divide por uma constante zero — é o caso do adversário do item.
        if _re_divisao_por_zero(expressao):
            raise EstiloInvalido("parametros_raster.expression divide por zero literal",
                                 "plat_construtor.parametros_raster.expression")

    colormap = pr.get("colormap_name")
    if colormap is not None and colormap not in titiler.COLORMAPS:
        raise EstiloInvalido(f"parametros_raster.colormap_name desconhecido do TiTiler: {colormap!r}",
                             "plat_construtor.parametros_raster.colormap_name")

    rescale = pr.get("rescale")
    if rescale is not None:
        mn, mx = rescale
        if mn >= mx:
            raise EstiloInvalido(f"parametros_raster.rescale invertido ou vazio: min ({mn}) >= max ({mx})",
                                 "plat_construtor.parametros_raster.rescale")

    reamostragem = pr.get("resampling")
    if reamostragem is not None and reamostragem not in ("vizinho", "bilinear"):
        raise EstiloInvalido("parametros_raster.resampling só aceita 'vizinho' ou 'bilinear'",
                             "plat_construtor.parametros_raster.resampling")

    esticamento = pr.get("esticamento")
    if esticamento is not None and esticamento.get("metodo") not in (
        "minmax", "percentil_2_98", "desvio_padrao", "nenhum"
    ):
        raise EstiloInvalido(
            "parametros_raster.esticamento.metodo só aceita minmax/percentil_2_98/desvio_padrao/nenhum",
            "plat_construtor.parametros_raster.esticamento")

    return [{"rotulo": "raster", "cor": None, "teste": None}], pr



_COMPILADORES = {
    "unico": _unico,
    "categoria": _categoria,
    "classes": _classes,
    "proporcional": _proporcional,
    "calor": _calor,
    "agrupamento": _agrupamento,
    "raster": _raster,
}


def classes(pc: dict) -> list[dict]:
    """A lista única de classes (rótulo, cor, teste) — a mesma que a legenda e o `maplibre` usam."""
    tipo = pc.get("tipo")
    if tipo not in _COMPILADORES:
        raise EstiloInvalido(f"tipo de construtor desconhecido: {tipo!r}", "plat_construtor.tipo")
    saida, _ = _COMPILADORES[tipo](pc)
    return saida


def _cor_por_classe(cls: list[dict]) -> list | str:
    if len(cls) == 1:
        return cls[0]["cor"] or "#4e79a7"
    expr: list = ["case"]
    for c in cls[:-1]:
        expr.append(c["teste"])
        expr.append(c["cor"])
    expr.append(cls[-1]["cor"])
    return expr


def compilar(pc: dict, id_base: str = "camada") -> dict:
    """Compila `plat_construtor` inteiro em `{"version": 8, "layers": [...]}` (sem `sources`)."""
    tipo = pc.get("tipo")
    if tipo not in _COMPILADORES:
        raise EstiloInvalido(f"tipo de construtor desconhecido: {tipo!r}", "plat_construtor.tipo")
    cls, extra = _COMPILADORES[tipo](pc)
    geom = pc.get("geometria")
    tipo_layer = GEOMETRIA_TIPO_LAYER.get(geom)
    if tipo_layer is None:
        raise EstiloInvalido(f"geometria desconhecida: {geom!r}", "plat_construtor.geometria")
    opacidade = 1.0 - float(pc.get("transparencia") or 0.0)
    layers: list[dict] = []

    if tipo == "raster":
        layer = {**_comum(id_base), "type": "raster", "paint": {"raster-opacity": opacidade}}
        layers.append(layer)
    elif tipo == "calor":
        rampa = extra.get("rampa") or ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]
        cor_expr = ["interpolate", ["linear"], ["heatmap-density"]]
        for i, c in enumerate(rampa):
            cor_expr += [i / max(1, len(rampa) - 1), c]
        layers.append({**_comum(id_base), "type": "heatmap", "paint": {
            "heatmap-weight": 1,
            "heatmap-intensity": float(extra.get("intensidade", 1)),
            "heatmap-radius": float(extra.get("raio_px", 20)),
            "heatmap-color": cor_expr,
            "heatmap-opacity": opacidade,
        }})
    elif tipo == "agrupamento":
        degraus = extra["degraus"]
        cor_expr: list = ["step", ["get", "point_count"], degraus[0]["cor"]]
        raio_expr: list = ["step", ["get", "point_count"], degraus[0]["raio"]]
        for d in degraus[1:]:
            if d.get("ate") is None:
                continue
            cor_expr += [d["ate"], d["cor"]]
            raio_expr += [d["ate"], d["raio"]]
        layers.append({**_comum(id_base), "type": "circle", "filter": ["has", "point_count"], "paint": {
            "circle-color": cor_expr, "circle-radius": raio_expr, "circle-opacity": opacidade,
        }})
        layers.append({**_comum(id_base + "-nao-agrupado"), "type": "circle", "filter": ["!", ["has", "point_count"]],
                       "paint": {"circle-color": degraus[0]["cor"], "circle-radius": 4, "circle-opacity": opacidade}})
    elif tipo == "proporcional":
        raio_expr = ["interpolate", ["linear"], ["to-number", ["get", pc["campo"]]],
                     extra["valor_min"], extra["raio_min"], extra["valor_max"], extra["raio_max"]]
        layers.append({**_comum(id_base), "type": "circle", "paint": {
            "circle-color": _cor_por_classe(cls), "circle-radius": raio_expr, "circle-opacity": opacidade,
        }})
    elif tipo_layer == "circle":
        s = pc.get("simbolo") or {}
        layers.append({**_comum(id_base), "type": "circle", "paint": {
            "circle-color": _cor_por_classe(cls),
            "circle-radius": float(s.get("raio", 4)),
            "circle-opacity": opacidade,
            "circle-stroke-width": float(s.get("contorno_largura", 0.5)),
            "circle-stroke-color": s.get("contorno_cor", "#10161a"),
        }})
    elif tipo_layer == "line":
        s = pc.get("simbolo") or {}
        layers.append({**_comum(id_base), "type": "line", "layout": {"line-cap": "round", "line-join": "round"},
                       "paint": {"line-color": _cor_por_classe(cls), "line-width": float(s.get("largura", 1.5)),
                                 "line-opacity": opacidade}})
    else:  # fill (poligono)
        s = pc.get("simbolo") or {}
        layers.append({**_comum(id_base), "type": "fill", "paint": {
            "fill-color": _cor_por_classe(cls), "fill-opacity": opacidade}})
        layers.append({**_comum(id_base + "-contorno"), "type": "line",
                       "paint": {"line-color": s.get("contorno_cor", "#1d3c34"),
                                 "line-width": float(s.get("contorno_largura", 0.6))}})

    rotulos = pc.get("rotulos")
    if rotulos and rotulos.get("visivel"):
        _campo_ok(pc, rotulos.get("campo"), "plat_construtor.rotulos.campo")
        layers.append({
            **_comum(id_base + "-rotulo"), "type": "symbol",
            "layout": {"text-field": ["get", rotulos["campo"]], "text-size": float(rotulos.get("tamanho", 12))},
            "paint": {"text-color": rotulos.get("cor", "#10161a")},
        })

    minz = pc.get("escala_min") or 0
    maxz = pc.get("escala_max") or 0
    if minz or maxz:
        for layer in layers:
            layer["metadata"] = {"plat:escala_min": minz, "plat:escala_max": maxz}

    return {"version": 8, "layers": layers}


def legenda(pc: dict) -> list[dict]:
    """Entradas de legenda — mesma lista de `classes()` usada por `compilar`."""
    return [{"rotulo": c["rotulo"], "cor": c["cor"]} for c in classes(pc) if c["cor"] is not None]


def legenda_raster(pc: dict) -> dict | None:
    """Legenda contínua do tipo raster: mín/máx e nome da rampa, para o editor desenhar a barra de
    cor com valores reais — os mesmos que `estatisticas_json` (L1-02) devolveu e que o editor gravou
    em `rescale` (nunca recalculado aqui: fonte única é a rota de estatísticas)."""
    if pc.get("tipo") != "raster":
        return None
    pr = pc.get("parametros_raster") or {}
    rescale = pr.get("rescale")
    if rescale is None:
        return None
    return {"colormap_name": pr.get("colormap_name"), "min": rescale[0], "max": rescale[1]}


def parametros_tile(pc: dict) -> dict:
    """`plat_construtor.parametros_raster` -> dicionário de consulta do serviço de ladrilho (item
    L1-02): traduz o vocabulário do documento (nomes do TiTiler, C2 do L2_CONCEITO) para os nomes de
    parâmetro em português que `app/imagens/rotas_tiles.py` de fato aceita (`expressao`, `bandas`,
    `faixa`, `colormap`). Só os quatro nomes que o L1-02 lê saem daqui — nenhum outro campo do
    construtor (esticamento, resampling ainda não suportado pelo L1-02, nodata) vaza para a URL."""
    if pc.get("tipo") != "raster":
        raise EstiloInvalido("parametros_tile só se aplica ao tipo raster", "plat_construtor.tipo")
    pr = pc.get("parametros_raster") or {}
    saida: dict[str, str] = {}
    if pr.get("expression"):
        saida["expressao"] = pr["expression"]
    if pr.get("bandas"):
        saida["bandas"] = ",".join(str(b) for b in pr["bandas"])
    if pr.get("rescale"):
        saida["faixa"] = ",".join(str(v) for v in pr["rescale"])
    if pr.get("colormap_name"):
        saida["colormap"] = pr["colormap_name"]
    return saida
