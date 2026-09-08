"""Simbologia da camada e a legenda que nasce DELA (item L2-01-mapa-web; conceito C2 de
`laco/decomposicao/L2_CONCEITO.md`).

Uma decisão do conceito manda aqui: o formato de estilo é a **MapLibre Style Spec pura**, com um bloco
lateral `plat_construtor` que descreve a intenção do usuário (tipo de classificação, campo, cortes,
cores). Este módulo é a implementação desse bloco: ele recebe o `plat_construtor` (guardado em
`plat.item.dados.simbologia`) e devolve DUAS saídas da MESMA lista de classes:

  * `camadas_maplibre(...)` — as camadas de estilo que o navegador desenha;
  * `legenda(...)` — as entradas da legenda que o navegador mostra.

Elas saem da mesma função `classes()`. É isso que a cláusula "legenda gerada a partir da simbologia, não
escrita à mão" quer dizer: não existe caminho no código em que a legenda diga uma cor e o mapa desenhe
outra — mudar a simbologia muda as duas, e o teste `tests/unit/test_simbologia.py` prova a igualdade
comparando as cores das duas saídas.

Vocabulário fechado de `tipo`: `simples`, `valores_unicos`, `intervalos`. Qualquer outro valor é recusado
(nunca "cai no padrão em silêncio").
"""

from __future__ import annotations

# Paleta categórica de 12 cores, distinguível em fundo claro e escuro. Ordem fixa: a mesma classe recebe a
# mesma cor em toda sessão e em toda máquina (a legenda de um mapa impresso ontem tem de valer hoje).
PALETA = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2",
    "#edc948", "#9c755f", "#ff9da7", "#8cd17d", "#bab0ac", "#d37295",
]
# Rampa sequencial de 7 passos para classificação por intervalo (claro -> escuro do mesmo tom).
RAMPA = ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"]

CORES_PADRAO = {"Point": "#4e79a7", "LineString": "#f28e2b", "Polygon": "#59a14f"}
TIPOS = ("simples", "valores_unicos", "intervalos")


class SimbologiaInvalida(ValueError):
    """A simbologia guardada no item não obedece ao vocabulário fechado."""


def familia(geometria: str | None) -> str:
    """Reduz o tipo de geometria da camada a uma das três famílias de desenho."""
    g = (geometria or "").lower()
    if "point" in g:
        return "Point"
    if "line" in g:
        return "LineString"
    if "polygon" in g:
        return "Polygon"
    return "Point"


def padrao(geometria: str | None) -> dict:
    """Simbologia de uma camada que ainda não tem nenhuma declarada."""
    fam = familia(geometria)
    simb = {"tipo": "simples", "cor": CORES_PADRAO[fam]}
    if fam == "Point":
        simb["tamanho"] = 4
    elif fam == "LineString":
        simb["largura"] = 1.5
    else:
        simb["opacidade"] = 0.55
        simb["contorno"] = "#1d3c34"
    return simb


def normalizar(simb: dict | None, geometria: str | None) -> dict:
    if not simb:
        return padrao(geometria)
    if not isinstance(simb, dict):
        raise SimbologiaInvalida("simbologia precisa ser um objeto")
    tipo = simb.get("tipo")
    if tipo not in TIPOS:
        raise SimbologiaInvalida(f"tipo de simbologia desconhecido: {tipo!r} (aceitos: {', '.join(TIPOS)})")
    if tipo in ("valores_unicos", "intervalos") and not simb.get("campo"):
        raise SimbologiaInvalida(f"simbologia {tipo} exige o campo classificador")
    if tipo == "intervalos" and not simb.get("cortes"):
        raise SimbologiaInvalida("simbologia intervalos exige a lista de cortes")
    if tipo == "valores_unicos" and not simb.get("valores"):
        raise SimbologiaInvalida("simbologia valores_unicos exige a lista de valores")
    return simb


def classes(simb: dict, geometria: str | None) -> list[dict]:
    """A lista única de classes: rótulo, cor e o teste que decide a qual classe a feição pertence.

    `teste` é a expressão MapLibre (Style Spec) que vale para aquela classe, ou None quando a classe é a
    única (simbologia simples). A legenda usa rótulo + cor; o estilo usa cor + teste. Uma lista só."""
    simb = normalizar(simb, geometria)
    fam = familia(geometria)
    tipo = simb["tipo"]
    if tipo == "simples":
        return [{"rotulo": simb.get("rotulo") or "todas as feições",
                 "cor": simb.get("cor") or CORES_PADRAO[fam], "teste": None}]
    if tipo == "valores_unicos":
        campo = simb["campo"]
        valores = list(simb["valores"])
        cores = list(simb.get("cores") or [])
        saida = []
        for i, v in enumerate(valores):
            saida.append({"rotulo": str(v), "cor": cores[i] if i < len(cores) else PALETA[i % len(PALETA)],
                          "teste": ["==", ["get", campo], v]})
        saida.append({"rotulo": simb.get("rotulo_outros") or "outros",
                      "cor": simb.get("cor_outros") or "#9aa0a6", "teste": None})
        return saida
    # intervalos: n cortes -> n+1 classes (o último "teste" é o resto)
    campo = simb["campo"]
    cortes = [float(c) for c in simb["cortes"]]
    rampa = list(simb.get("rampa") or RAMPA)
    saida = []
    anterior = None
    for i, corte in enumerate(cortes):
        cor = rampa[min(i, len(rampa) - 1)]
        rot = f"< {corte:g}" if anterior is None else f"{anterior:g} a {corte:g}"
        saida.append({"rotulo": rot, "cor": cor, "teste": ["<", ["to-number", ["get", campo]], corte]})
        anterior = corte
    saida.append({"rotulo": f">= {cortes[-1]:g}", "cor": rampa[min(len(cortes), len(rampa) - 1)],
                  "teste": None})
    return saida


def _cor_por_classe(cls: list[dict], simb: dict) -> list | str:
    """Expressão MapLibre `case` construída da MESMA lista de classes que a legenda usa."""
    if len(cls) == 1:
        return cls[0]["cor"]
    expr: list = ["case"]
    for c in cls[:-1]:
        expr.append(c["teste"])
        expr.append(c["cor"])
    expr.append(cls[-1]["cor"])  # o último é sempre o "resto", sem teste
    return expr


def camadas_maplibre(simb: dict | None, geometria: str | None, id_base: str, fonte: str,
                     camada_fonte: str) -> list[dict]:
    """Camadas de estilo (MapLibre Style Spec v8) para uma camada de dado. Sem nada fora da spec."""
    simb = normalizar(simb, geometria)
    cls = classes(simb, geometria)
    cor = _cor_por_classe(cls, simb)
    fam = familia(geometria)
    comum = {"source": fonte, "source-layer": camada_fonte}
    if fam == "Point":
        return [{"id": id_base, "type": "circle", **comum, "paint": {
            "circle-color": cor,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, max(1.5, float(simb.get("tamanho", 4)) / 2),
                              14, float(simb.get("tamanho", 4))],
            "circle-opacity": float(simb.get("opacidade", 0.9)),
            "circle-stroke-width": 0.4, "circle-stroke-color": "#10161a"}}]
    if fam == "LineString":
        return [{"id": id_base, "type": "line", **comum,
                 "layout": {"line-cap": "round", "line-join": "round"},
                 "paint": {"line-color": cor, "line-width": float(simb.get("largura", 1.5)),
                           "line-opacity": float(simb.get("opacidade", 0.95))}}]
    return [
        {"id": id_base, "type": "fill", **comum,
         "paint": {"fill-color": cor, "fill-opacity": float(simb.get("opacidade", 0.55))}},
        {"id": id_base + "-contorno", "type": "line", **comum,
         "paint": {"line-color": simb.get("contorno") or "#1d3c34", "line-width": 0.6}},
    ]


def legenda(simb: dict | None, geometria: str | None) -> list[dict]:
    """Entradas da legenda — mesma lista de classes, mesma ordem, mesmas cores do estilo."""
    simb = normalizar(simb, geometria)
    fam = familia(geometria)
    forma = {"Point": "ponto", "LineString": "linha", "Polygon": "poligono"}[fam]
    return [{"rotulo": c["rotulo"], "cor": c["cor"], "forma": forma} for c in classes(simb, geometria)]
