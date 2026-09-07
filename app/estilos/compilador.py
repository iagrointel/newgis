"""Compilador `plat_construtor` -> camadas MapLibre Style Spec v8 (item L2-02-a-modelo-estilo).

Uma função por tipo do construtor. Todas devolvem `(classes, layers)`: `classes` é a lista de
{rotulo, cor, teste} que tanto o `maplibre` quanto a legenda do editor usam (mesma disciplina do
L2-01-mapa-web: legenda e mapa nascem da mesma lista, nunca duas fontes de verdade); `layers` são as
camadas efetivas da Style Spec, sem `sources` (a fonte real é ligada na renderização, nunca gravada
no documento — C2 do L2_CONCEITO).

`campo_ok` valida que todo campo citado está no vocabulário `plat_construtor.campos` (schema
estilo-v1: "referência fora da lista = 422 campo_inexistente"); quem chama fora deste módulo nunca
monta uma expressão `["get", campo]` sem passar por aqui.

Item L2-02-c-editor-simbologia-vetor acrescentou, sem mudar a versão do esquema (só campos opcionais):
`outros` (o que não casa com categoria alguma), classes de TAMANHO (`classes[].tamanho`), ícone por
símbolo/categoria (camada `symbol` sobre o sprite do inquilino), `tracejado`/`seta` em linha, `padrao`
de preenchimento em polígono, `efeitos` (sombra em polígono, brilho em linha; `mistura` só registrada em
metadata — a Style Spec não tem blend por camada), faixa de escala por camada (minzoom/maxzoom a partir
do denominador) e por classe (opacidade por degrau de zoom, porque `zoom` só entra em `step`/`interpolate`).
"""

from __future__ import annotations

import math

# denominador de escala 1:N <-> zoom da web mercator no equador (559.082.264 é 1:N do z0 em 96 dpi/256 px)
ESCALA_Z0 = 559082264.028
TRANSPARENTE = "rgba(0,0,0,0)"


def zoom_de_escala(denominador: float | None) -> float | None:
    """1:N -> zoom fracionário; None/0 = sem limite."""
    if not denominador or denominador <= 0:
        return None
    return round(max(0.0, min(24.0, math.log2(ESCALA_Z0 / float(denominador)))), 2)


GEOMETRIA_TIPO_LAYER = {"ponto": "circle", "linha": "line", "poligono": "fill", "raster": "raster"}
TIPOS = ("unico", "categoria", "classes", "proporcional", "calor", "agrupamento", "raster")


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
        saida.append({"rotulo": c.get("rotulo") or str(v), "cor": c["cor"], "teste": ["==", ["get", campo], v],
                      "icone": c.get("icone"), "escala_min": c.get("escala_min"), "escala_max": c.get("escala_max")})
    outros = pc.get("outros")
    if outros and outros.get("visivel", True):
        # "outros" é o ramo padrão do `case`: nunca tem teste, e por isso é a ÚNICA cor que uma feição sem
        # categoria recebe (antes o padrão era a cor da última categoria — errado para quem tem > 200 valores)
        saida.append({"rotulo": outros.get("rotulo") or "outros", "cor": outros["cor"], "teste": None, "outros": True})
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
        saida.append({"rotulo": rot, "cor": c["cor"], "teste": teste, "tamanho": c.get("tamanho"),
                      "escala_min": c.get("escala_min"), "escala_max": c.get("escala_max")})
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


def _raster(pc: dict) -> tuple[list[dict], dict]:
    if pc.get("geometria") != "raster":
        raise EstiloInvalido("tipo raster exige geometria raster", "plat_construtor.geometria")
    pr = pc.get("parametros_raster") or {}
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


def _cor_por_classe(cls: list[dict], tipo: str | None = None) -> list | str:
    """`case` com uma cor por classe. Em `classes` a última faixa é inclusiva e serve de padrão (como antes);
    em `categoria` o padrão é a cor de `outros` quando existe, senão TRANSPARENTE — feição sem categoria não
    herda a cor da última categoria."""
    if tipo == "categoria":
        com_teste = [c for c in cls if c.get("teste") is not None]
        outros = next((c for c in cls if c.get("outros")), None)
        padrao = outros["cor"] if outros else TRANSPARENTE
        if not com_teste:
            return padrao
        expr: list = ["case"]
        for c in com_teste:
            expr += [c["teste"], c["cor"]]
        expr.append(padrao)
        return expr
    if len(cls) == 1:
        return cls[0]["cor"] or "#4e79a7"
    expr = ["case"]
    for c in cls[:-1]:
        expr.append(c["teste"])
        expr.append(c["cor"])
    expr.append(cls[-1]["cor"])
    return expr


def _tamanho_por_classe(cls: list[dict], padrao: float) -> list | float:
    """classes de TAMANHO (raio do ponto ou largura da linha): `case` por faixa quando alguma classe declara
    `tamanho`; senão o tamanho base do símbolo."""
    if not any(c.get("tamanho") is not None for c in cls):
        return padrao
    com_teste = [c for c in cls if c.get("teste") is not None]
    if not com_teste:
        return float(cls[0].get("tamanho") or padrao)
    expr: list = ["case"]
    for c in com_teste[:-1]:
        expr += [c["teste"], float(c.get("tamanho") if c.get("tamanho") is not None else padrao)]
    expr.append(float(com_teste[-1].get("tamanho") if com_teste[-1].get("tamanho") is not None else padrao))
    return expr


def _icone_por_classe(cls: list[dict], simbolo: dict) -> list | str | None:
    """`icon-image`: ícone fixo do símbolo, ou `case` por categoria quando alguma categoria tem ícone."""
    if any(c.get("icone") for c in cls):
        expr: list = ["case"]
        for c in cls:
            if c.get("teste") is not None and c.get("icone"):
                expr += [c["teste"], c["icone"]]
        expr.append(simbolo.get("icone") or "")
        return expr
    return simbolo.get("icone") or None


def _opacidade_por_escala(cls: list[dict], opacidade: float) -> list | float:
    """faixa de escala POR CLASSE: `zoom` só pode ser lido por `step`/`interpolate` no topo da expressão, então
    a visibilidade de cada classe vira um `step` sobre o zoom cujos degraus são `case` de opacidade."""
    faixas = []
    for c in cls:
        z_min = zoom_de_escala(c.get("escala_max"))  # maior denominador = zoom mínimo
        z_max = zoom_de_escala(c.get("escala_min"))  # menor denominador = zoom máximo
        faixas.append((z_min, z_max))
    if all(f == (None, None) for f in faixas):
        return opacidade
    cortes = sorted({z for f in faixas for z in f if z is not None})

    def visivel(i: int, z: float) -> bool:
        z_min, z_max = faixas[i]
        return (z_min is None or z >= z_min) and (z_max is None or z < z_max)

    def caso(z: float) -> list | float:
        expr: list = ["case"]
        for i, c in enumerate(cls):
            if c.get("teste") is None:
                continue
            expr += [c["teste"], opacidade if visivel(i, z) else 0]
        padrao_i = next((i for i, c in enumerate(cls) if c.get("teste") is None), None)
        expr.append(opacidade if (padrao_i is None or visivel(padrao_i, z)) else 0)
        return expr

    expr: list = ["step", ["zoom"], caso(-1)]
    for z in cortes:
        expr += [z, caso(z)]
    return expr


def _limites_de_zoom(layer: dict, pc: dict) -> dict:
    """faixa de escala da CAMADA inteira: minzoom/maxzoom nativos do MapLibre (a metadata continua)."""
    z_min = zoom_de_escala(pc.get("escala_max"))
    z_max = zoom_de_escala(pc.get("escala_min"))
    if z_min is not None:
        layer["minzoom"] = z_min
    if z_max is not None:
        layer["maxzoom"] = z_max
    return layer


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
        cor = _cor_por_classe(cls, tipo)
        op = _opacidade_por_escala(cls, opacidade)
        icone = _icone_por_classe(cls, s)
        if not (tipo == "unico" and icone):  # símbolo único com ícone: só o ícone, sem o círculo por baixo
            layers.append({**_comum(id_base), "type": "circle", "paint": {
                "circle-color": cor,
                "circle-radius": _tamanho_por_classe(cls, float(s.get("raio", 4))),
                "circle-opacity": op,
                "circle-stroke-width": float(s.get("contorno_largura", 0.5)),
                "circle-stroke-color": s.get("contorno_cor", "#10161a"),
            }})
        if icone:
            layers.append({**_comum(id_base + "-icone"), "type": "symbol",
                           "layout": {"icon-image": icone, "icon-size": float(s.get("icone_tamanho", 1)),
                                      "icon-allow-overlap": True},
                           "paint": {"icon-opacity": op}})
    elif tipo_layer == "line":
        s = pc.get("simbolo") or {}
        largura = _tamanho_por_classe(cls, float(s.get("largura", 1.5)))
        cor = _cor_por_classe(cls, tipo)
        op = _opacidade_por_escala(cls, opacidade)
        ef = pc.get("efeitos") or {}
        if ef.get("brilho"):
            layers.append({**_comum(id_base + "-brilho"), "type": "line", "metadata": {"plat:auxiliar": True},
                           "layout": {"line-cap": "round", "line-join": "round"},
                           "paint": {"line-color": cor, "line-width": ["*", 3, largura] if isinstance(largura, list)
                                     else largura * 3, "line-blur": float(ef["brilho"]),
                                     "line-opacity": 0.6 * opacidade}})
        linha = {**_comum(id_base), "type": "line", "layout": {"line-cap": "round", "line-join": "round"},
                 "paint": {"line-color": cor, "line-width": largura, "line-opacity": op}}
        if s.get("tracejado"):
            linha["paint"]["line-dasharray"] = [float(v) for v in s["tracejado"]]
            linha["layout"]["line-cap"] = "butt"
        layers.append(linha)
        if s.get("seta"):
            layers.append({**_comum(id_base + "-seta"), "type": "symbol",
                           "layout": {"symbol-placement": "line", "symbol-spacing": 80, "icon-image": s["seta"],
                                      "icon-size": float(s.get("icone_tamanho", 0.6)), "icon-allow-overlap": True,
                                      "icon-rotation-alignment": "map", "icon-ignore-placement": True},
                           "paint": {"icon-opacity": opacidade}})
    else:  # fill (poligono)
        s = pc.get("simbolo") or {}
        ef = pc.get("efeitos") or {}
        op = _opacidade_por_escala(cls, opacidade)
        if ef.get("sombra"):
            layers.append({**_comum(id_base + "-sombra"), "type": "fill", "metadata": {"plat:auxiliar": True},
                           "paint": {"fill-color": "#000000", "fill-opacity": 0.35 * opacidade,
                                     "fill-translate": [3, 3], "fill-translate-anchor": "viewport"}})
        preenchimento = {**_comum(id_base), "type": "fill", "paint": {
            "fill-color": _cor_por_classe(cls, tipo), "fill-opacity": op}}
        if s.get("padrao"):
            preenchimento["paint"]["fill-pattern"] = s["padrao"]
        layers.append(preenchimento)
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
    mistura = (pc.get("efeitos") or {}).get("mistura")
    for layer in layers:
        if minz or maxz:
            layer["metadata"] = {**layer.get("metadata", {}), "plat:escala_min": minz, "plat:escala_max": maxz}
            _limites_de_zoom(layer, pc)
        if mistura and mistura != "normal":
            layer.setdefault("metadata", {})["plat:mistura"] = mistura  # sem blend na Style Spec: só registrado

    return {"version": 8, "layers": layers}


def legenda(pc: dict) -> list[dict]:
    """Entradas de legenda — mesma lista de `classes()` usada por `compilar` (com tamanho e ícone quando há)."""
    saida = []
    for c in classes(pc):
        if c["cor"] is None:
            continue
        entrada = {"rotulo": c["rotulo"], "cor": c["cor"]}
        for chave in ("tamanho", "icone"):
            if c.get(chave) is not None:
                entrada[chave] = c[chave]
        saida.append(entrada)
    return saida
