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

import math

from app.estilos import rotulos_servidor
from app.expressao import compilador_maplibre
from app.expressao.avaliador_py import ErroExpressao, analisar

GEOMETRIA_TIPO_LAYER = {"ponto": "circle", "linha": "line", "poligono": "fill", "raster": "raster"}
TIPOS = ("unico", "categoria", "classes", "proporcional", "calor", "agrupamento", "raster")
_FONTE_ROTULO_PADRAO = ["Noto Sans Regular"]
# convenção fixa do endpoint de glifos do Martin (item L2-02-e-simbolos-sprites-glifos); casa com o
# padrão do schema (docs/esquemas/estilo-v1.json corpo.maplibre.glyphs, "^/fontes/[a-z0-9]...$").
GLYPHS_PADRAO = "/fontes/plat/{fontstack}/{range}.pbf"
_OPERADORES_FILTRO = {"==", "!=", "<", "<=", ">", ">="}


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
            raise EstiloInvalido(f"faixa invertida ou vazia: min ({mn}) >= max ({mx})", f"plat_construtor.classes.{i}")
        ultima = i == len(cls) - 1
        teste = [
            "all",
            [">=", ["to-number", ["get", campo]], mn],
            [">=" if ultima else "<", ["to-number", ["get", campo]], mx]
            if ultima
            else ["<", ["to-number", ["get", campo]], mx],
        ]
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


def _cor_por_classe(cls: list[dict]) -> list | str:
    if len(cls) == 1:
        return cls[0]["cor"] or "#4e79a7"
    expr: list = ["case"]
    for c in cls[:-1]:
        expr.append(c["teste"])
        expr.append(c["cor"])
    expr.append(cls[-1]["cor"])
    return expr


# Escala <-> zoom (só para os layers de rótulo, item L2-02-d-rotulos): denominador de escala no
# zoom 0, convenção OGC do "pixel de renderização padronizado" de 0,28 mm (WMTS Implementation
# Standard, anexo E; a mesma constante aparece em Leaflet/OpenLayers para a conversão inversa).
# resolução(z) em m/px = 2*pi*6378137 / (256 * 2^z); escala(z) = resolução(z) / 0,00028 m.
_ESCALA_ZOOM_0 = (2 * math.pi * 6378137) / 256 / 0.00028


def _escala_para_zoom(escala: float) -> float:
    return math.log2(_ESCALA_ZOOM_0 / escala)


def _filtro_maplibre(filtro: dict | None) -> list | None:
    if not filtro:
        return None
    op = filtro["operador"]
    if op not in _OPERADORES_FILTRO:
        raise EstiloInvalido(f"operador de filtro de rótulo desconhecido: {op!r}", "plat_construtor.rotulos")
    return [op, ["get", filtro["campo"]], filtro["valor"]]


def _texto_da_classe(pc: dict, classe: dict) -> tuple[object, bool, str | None]:
    """`(expressão MapLibre do text-field, veio_do_servidor, motivo_se_servidor)`.

    `campo` é a leitura direta (sempre compila: `["get", campo]`). `expressao` tenta compilar para
    MapLibre (`app.expressao.compilador_maplibre`); quando a linguagem usa algo sem equivalente
    nativo (ex. `TextoNumero`, formatação pt-BR), cai para `["get", <coluna do servidor>]` — a
    mesma expressão, pré-calculada por `app.estilos.rotulos_servidor.pre_calcular` na ingestão/tile
    (item irmão do L2-04; aqui só o CONTRATO do nome de coluna e do cálculo estão provados)."""
    texto = classe.get("texto") or {}
    campo = texto.get("campo")
    expressao = texto.get("expressao")
    if campo:
        _campo_ok(pc, campo, "plat_construtor.rotulos.classes[].texto.campo")
        return ["get", campo], False, None
    if not expressao:
        raise EstiloInvalido(
            "classe de rótulo exige texto.campo ou texto.expressao", "plat_construtor.rotulos.classes[].texto"
        )
    try:
        ast = analisar(expressao)
        expr = compilador_maplibre.compilar(ast)
        return expr, False, None
    except (ErroExpressao, compilador_maplibre.NaoCompilavel) as e:
        motivo = e.motivo if isinstance(e, compilador_maplibre.NaoCompilavel) else str(e)
        coluna = rotulos_servidor.nome_coluna_servidor(expressao)
        return ["get", coluna], True, motivo


def _rotulo_layer(pc: dict, geom: str, classe: dict, id_base: str) -> dict:
    texto_expr, servidor, motivo = _texto_da_classe(pc, classe)
    coluna_servidor_expr = texto_expr  # antes do sufixo de unidade, para a metadata (linha abaixo)
    if classe.get("unidade"):
        texto_expr = ["concat", ["to-string", texto_expr], " ", classe["unidade"]]

    tamanho = float(classe.get("tamanho", 12))
    tam_zoom_min = classe.get("tamanho_zoom_min")
    tam_zoom_max = classe.get("tamanho_zoom_max")
    tamanho_max = classe.get("tamanho_max")
    if tam_zoom_min is not None and tam_zoom_max is not None and tamanho_max is not None:
        text_size = ["interpolate", ["linear"], ["zoom"], tam_zoom_min, tamanho, tam_zoom_max, float(tamanho_max)]
    else:
        text_size = tamanho

    layout: dict = {
        "text-field": texto_expr,
        "text-size": text_size,
        "text-font": classe.get("fonte") or list(_FONTE_ROTULO_PADRAO),
        "text-anchor": classe.get("ancora", "center"),
        "text-offset": classe.get("deslocamento") or [0, 0],
    }
    if classe.get("maiusculas"):
        layout["text-transform"] = "uppercase"
    if classe.get("varias_linhas_largura_max") is not None:
        layout["text-max-width"] = float(classe["varias_linhas_largura_max"])
    if geom == "linha" and classe.get("ao_longo_da_linha"):
        layout["symbol-placement"] = "line"
        if classe.get("repetir_px") is not None:
            layout["symbol-spacing"] = float(classe["repetir_px"])
    if classe.get("prioridade") is not None:
        # medido de verdade no MapLibre-GL real (tests/e2e/test_rotulos_render.py::
        # test_prioridade_classe_a_vence_b_em_colisao): o motor faz o symbol-sort-key MAIOR vencer
        # a colisão, não o menor (a leitura ingênua da Style Spec sugere o contrário). O campo
        # `prioridade` do editor continua "número menor = mais importante" (convenção cartográfica
        # comum); o compilador nega para casar com o motor sem trair o contrato do editor.
        layout["symbol-sort-key"] = -int(classe["prioridade"])
    if classe.get("permitir_sobreposicao"):
        layout["text-allow-overlap"] = True
        layout["text-ignore-placement"] = True

    paint = {"text-color": classe.get("cor", "#10161a")}
    if classe.get("halo_cor"):
        paint["text-halo-color"] = classe["halo_cor"]
        paint["text-halo-width"] = float(classe.get("halo_largura") or 1.0)

    layer: dict = {**_comum(id_base), "type": "symbol", "layout": layout, "paint": paint}
    filtro = _filtro_maplibre(classe.get("filtro"))
    if filtro is not None:
        layer["filter"] = filtro
    minz = classe.get("escala_min") or 0
    maxz = classe.get("escala_max") or 0
    metadata = {"plat:escala_min": minz, "plat:escala_max": maxz}
    # escala_min (denominador MENOR = mais perto) vira o teto de zoom nativo (some ao zoom in de
    # mais); escala_max (denominador MAIOR = mais longe) vira o piso (some ao zoom out de mais).
    if minz:
        layer["maxzoom"] = _escala_para_zoom(minz)
    if maxz:
        layer["minzoom"] = _escala_para_zoom(maxz)
    if servidor:
        metadata["plat:rotulo_servidor"] = True
        metadata["plat:rotulo_motivo_servidor"] = motivo
        metadata["plat:rotulo_coluna_servidor"] = coluna_servidor_expr
    layer["metadata"] = metadata
    return layer


def _rotulos_layers(pc: dict, rotulos: dict, id_base: str, geom: str) -> list[dict]:
    classes_rotulo = rotulos.get("classes") or []
    if not classes_rotulo:
        raise EstiloInvalido(
            "rotulos.visivel exige ao menos uma classe em rotulos.classes", "plat_construtor.rotulos.classes"
        )
    camadas = []
    for i, classe in enumerate(classes_rotulo):
        sufixo = "-rotulo" if len(classes_rotulo) == 1 else f"-rotulo-{i}"
        camadas.append((i, classe, _rotulo_layer(pc, geom, classe, id_base + sufixo)))

    # ORDEM DOS LAYERS decide a colisão entre classes diferentes, não o `symbol-sort-key` (medido
    # de verdade no MapLibre-GL real: dado o MESMO sort-key ou nenhum, o layer que vem DEPOIS na
    # lista sempre venceu a colisão contra o que vem antes — test_rotulos_render.py::
    # test_prioridade_classe_a_vence_b_em_colisao). `symbol-sort-key` só ordena feições DENTRO do
    # mesmo layer (mesma classe), então continua gravado (paridade com a Style Spec, útil quando
    # uma classe tem muitas feições competindo entre si), mas quem decide classe-vs-classe é a
    # posição no array: classe sem prioridade fica primeiro (perde para qualquer prioridade
    # explícita); entre prioridades explícitas, a de número MENOR (mais importante) fica por
    # último, então vence.
    def chave_ordem(item):
        _, classe, _ = item
        p = classe.get("prioridade")
        return (0, 0) if p is None else (1, -p)

    camadas.sort(key=chave_ordem)
    return [layer for _, _, layer in camadas]


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
        layers.append(
            {
                **_comum(id_base),
                "type": "heatmap",
                "paint": {
                    "heatmap-weight": 1,
                    "heatmap-intensity": float(extra.get("intensidade", 1)),
                    "heatmap-radius": float(extra.get("raio_px", 20)),
                    "heatmap-color": cor_expr,
                    "heatmap-opacity": opacidade,
                },
            }
        )
    elif tipo == "agrupamento":
        degraus = extra["degraus"]
        cor_expr: list = ["step", ["get", "point_count"], degraus[0]["cor"]]
        raio_expr: list = ["step", ["get", "point_count"], degraus[0]["raio"]]
        for d in degraus[1:]:
            if d.get("ate") is None:
                continue
            cor_expr += [d["ate"], d["cor"]]
            raio_expr += [d["ate"], d["raio"]]
        layers.append(
            {
                **_comum(id_base),
                "type": "circle",
                "filter": ["has", "point_count"],
                "paint": {
                    "circle-color": cor_expr,
                    "circle-radius": raio_expr,
                    "circle-opacity": opacidade,
                },
            }
        )
        layers.append(
            {
                **_comum(id_base + "-nao-agrupado"),
                "type": "circle",
                "filter": ["!", ["has", "point_count"]],
                "paint": {"circle-color": degraus[0]["cor"], "circle-radius": 4, "circle-opacity": opacidade},
            }
        )
    elif tipo == "proporcional":
        raio_expr = [
            "interpolate",
            ["linear"],
            ["to-number", ["get", pc["campo"]]],
            extra["valor_min"],
            extra["raio_min"],
            extra["valor_max"],
            extra["raio_max"],
        ]
        layers.append(
            {
                **_comum(id_base),
                "type": "circle",
                "paint": {
                    "circle-color": _cor_por_classe(cls),
                    "circle-radius": raio_expr,
                    "circle-opacity": opacidade,
                },
            }
        )
    elif tipo_layer == "circle":
        s = pc.get("simbolo") or {}
        layers.append(
            {
                **_comum(id_base),
                "type": "circle",
                "paint": {
                    "circle-color": _cor_por_classe(cls),
                    "circle-radius": float(s.get("raio", 4)),
                    "circle-opacity": opacidade,
                    "circle-stroke-width": float(s.get("contorno_largura", 0.5)),
                    "circle-stroke-color": s.get("contorno_cor", "#10161a"),
                },
            }
        )
    elif tipo_layer == "line":
        s = pc.get("simbolo") or {}
        layers.append(
            {
                **_comum(id_base),
                "type": "line",
                "layout": {"line-cap": "round", "line-join": "round"},
                "paint": {
                    "line-color": _cor_por_classe(cls),
                    "line-width": float(s.get("largura", 1.5)),
                    "line-opacity": opacidade,
                },
            }
        )
    else:  # fill (poligono)
        s = pc.get("simbolo") or {}
        layers.append(
            {
                **_comum(id_base),
                "type": "fill",
                "paint": {"fill-color": _cor_por_classe(cls), "fill-opacity": opacidade},
            }
        )
        layers.append(
            {
                **_comum(id_base + "-contorno"),
                "type": "line",
                "paint": {
                    "line-color": s.get("contorno_cor", "#1d3c34"),
                    "line-width": float(s.get("contorno_largura", 0.6)),
                },
            }
        )

    rotulos = pc.get("rotulos")
    if rotulos and rotulos.get("visivel"):
        layers.extend(_rotulos_layers(pc, rotulos, id_base, geom))

    minz = pc.get("escala_min") or 0
    maxz = pc.get("escala_max") or 0
    if minz or maxz:
        for layer in layers:
            # camadas de rótulo já têm a própria faixa de escala por classe (_rotulo_layer); a
            # faixa da camada só entra ali se a classe não declarou nenhuma (0/0 = sem limite).
            existente = layer.get("metadata") or {}
            if existente.get("plat:escala_min") or existente.get("plat:escala_max"):
                continue
            layer["metadata"] = {**existente, "plat:escala_min": minz, "plat:escala_max": maxz}

    documento: dict = {"version": 8, "layers": layers}
    if any(la["type"] == "symbol" for la in layers):
        # a Style Spec exige `glyphs` no documento sempre que há `text-field` (validador oficial,
        # ferramentas/estilo/validar.mjs). Convenção fixa do glifário do Martin (item L2-02-e); o
        # documento de mapa (L2-01-a), ao compor várias camadas, usa o MESMO caminho — não há dois
        # servidores de glifos no produto.
        documento["glyphs"] = GLYPHS_PADRAO
    return documento


def legenda(pc: dict) -> list[dict]:
    """Entradas de legenda — mesma lista de `classes()` usada por `compilar`."""
    return [{"rotulo": c["rotulo"], "cor": c["cor"]} for c in classes(pc) if c["cor"] is not None]
