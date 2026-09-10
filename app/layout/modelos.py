"""Documento de layout (tipo de item `layout`, item L2-12-b-layouts-elementos-exportacao): validação e modelos
padrão. O esquema JSON publicado em `plat.tipo_item` (migração 20260908T1203_layout.sql) é a mesma forma que
`validar()` confere aqui — a rota e o job validam antes de compor, para o erro sair nomeado (422 com o campo)
e nunca como falha do compositor.

Coordenadas em MILÍMETROS a partir do canto superior esquerdo do papel; o editor por arrasto é o L5-08 —
até ele, o formulário do painel escreve estes números. Um layout é `modelo` quando serve de ponto de partida
(modelos do inquilino = itens `layout` com `modelo: true`; os padrão ficam em código, abaixo).
"""

from __future__ import annotations

import copy
from typing import Any

from app import limites
from app.layout.geometria import PAPEIS, dimensoes_papel

ORIENTACOES = ("retrato", "paisagem")
TIPOS_ELEMENTO = (
    "mapa",
    "legenda",
    "escala",
    "norte",
    "grade",
    "titulo",
    "texto",
    "imagem",
    "tabela",
    "data",
    "atribuicao",
)
MODOS_QUADRO = ("escala", "extensao")
PAPEIS_DO_QUADRO = ("principal", "localizacao")
CRS_GRADE = ("4326", "utm")
REFERENCIAS_NORTE = ("verdadeiro", "grade")
FORMATOS_EXPORTACAO = ("pdf", "png", "jpg", "svg")


class ErroLayout(ValueError):
    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.campo = campo


def _num(el: dict, chave: str, minimo: float, maximo: float, onde: str, obrigatorio: bool = True) -> float | None:
    v = el.get(chave)
    if v is None:
        if obrigatorio:
            raise ErroLayout(f"{onde}: falta {chave}", f"{onde}.{chave}")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErroLayout(f"{onde}: {chave} precisa ser número", f"{onde}.{chave}")
    if not (minimo <= float(v) <= maximo):
        raise ErroLayout(f"{onde}: {chave} fora de [{minimo}, {maximo}]", f"{onde}.{chave}")
    return float(v)


def validar(doc: Any) -> dict:
    """Devolve o documento normalizado (cópia) ou levanta ErroLayout nomeando o campo."""
    if not isinstance(doc, dict):
        raise ErroLayout("layout precisa ser um objeto", "layout")
    d = copy.deepcopy(doc)
    d.setdefault("esquema_versao", 1)
    papel = d.get("papel", "A4")
    if papel not in PAPEIS:
        raise ErroLayout(f"papel desconhecido: {papel!r}", "papel")
    orientacao = d.get("orientacao", "retrato")
    if orientacao not in ORIENTACOES:
        raise ErroLayout(f"orientação desconhecida: {orientacao!r}", "orientacao")
    d["papel"], d["orientacao"] = papel, orientacao
    largura, altura = dimensoes_papel(papel, orientacao)
    margens = d.get("margens_mm") or {}
    if not isinstance(margens, dict):
        raise ErroLayout("margens_mm precisa ser um objeto", "margens_mm")
    for lado in ("superior", "inferior", "esquerda", "direita"):
        margens[lado] = _num(margens, lado, 0, 100, "margens_mm", obrigatorio=False) if lado in margens else 10.0
    d["margens_mm"] = margens
    d["modelo"] = bool(d.get("modelo", False))
    if "nome" in d and d["nome"] is not None:
        if not isinstance(d["nome"], str) or len(d["nome"]) > 200:
            raise ErroLayout("nome: texto de até 200 caracteres", "nome")
    elementos = d.get("elementos")
    if not isinstance(elementos, list):
        raise ErroLayout("elementos precisa ser uma lista", "elementos")
    if len(elementos) > limites.LAYOUT_ELEMENTOS_MAX:
        raise ErroLayout(f"no máximo {limites.LAYOUT_ELEMENTOS_MAX} elementos", "elementos")
    ids: set[str] = set()
    quadros = 0
    for i, el in enumerate(elementos):
        onde = f"elementos[{i}]"
        if not isinstance(el, dict):
            raise ErroLayout(f"{onde}: precisa ser um objeto", onde)
        tipo = el.get("tipo")
        if tipo not in TIPOS_ELEMENTO:
            raise ErroLayout(f"{onde}: tipo desconhecido {tipo!r}; aceitos {list(TIPOS_ELEMENTO)}", f"{onde}.tipo")
        eid = str(el.get("id") or f"{tipo}-{i + 1}")
        if eid in ids:
            raise ErroLayout(f"{onde}: id repetido {eid!r}", f"{onde}.id")
        ids.add(eid)
        el["id"] = eid
        if tipo != "grade":
            x = _num(el, "x", 0, largura, onde)
            y = _num(el, "y", 0, altura, onde)
            w = _num(el, "w", 1, largura, onde)
            h = _num(el, "h", 1, altura, onde)
            if x + w > largura + 0.01 or y + h > altura + 0.01:
                raise ErroLayout(f"{onde}: sai do papel ({largura:g} × {altura:g} mm)", onde)
            el.update({"x": x, "y": y, "w": w, "h": h})
        if tipo == "mapa":
            quadros += 1
            modo = el.get("modo", "extensao")
            if modo not in MODOS_QUADRO:
                raise ErroLayout(f"{onde}: modo precisa ser um de {list(MODOS_QUADRO)}", f"{onde}.modo")
            el["modo"] = modo
            papel_q = el.get("papel_do_quadro", "principal")
            if papel_q not in PAPEIS_DO_QUADRO:
                raise ErroLayout(f"{onde}: papel_do_quadro inválido", f"{onde}.papel_do_quadro")
            el["papel_do_quadro"] = papel_q
            if modo == "escala":
                _num(el, "escala", limites.LAYOUT_ESCALA_MIN, limites.LAYOUT_ESCALA_MAX, onde)
                centro = el.get("centro")
                if not (
                    isinstance(centro, list) and len(centro) == 2 and all(isinstance(v, (int, float)) for v in centro)
                ):
                    raise ErroLayout(f"{onde}: modo escala exige centro [lon, lat]", f"{onde}.centro")
                if not (-180 <= centro[0] <= 180 and -85 <= centro[1] <= 85):
                    raise ErroLayout(f"{onde}: centro fora do mundo", f"{onde}.centro")
            else:
                ext = el.get("extensao")
                if ext is None and d["modelo"]:
                    pass  # modelo: a extensão vem do mapa na hora de usar (app/layout/compor.py::_mapa)
                elif not (isinstance(ext, list) and len(ext) == 4 and all(isinstance(v, (int, float)) for v in ext)):
                    raise ErroLayout(
                        f"{onde}: modo extensao exige extensao [oeste, sul, leste, norte]", f"{onde}.extensao"
                    )
                elif not (ext[0] < ext[2] and ext[1] < ext[3]):
                    raise ErroLayout(f"{onde}: extensão inválida (oeste < leste, sul < norte)", f"{onde}.extensao")
            el["rotacao"] = _num(el, "rotacao", -180, 180, onde, obrigatorio=False) or 0.0
            el["moldura"] = bool(el.get("moldura", True))
        elif tipo == "legenda":
            colunas = el.get("colunas", 1)
            if not isinstance(colunas, int) or not (1 <= colunas <= 6):
                raise ErroLayout(f"{onde}: colunas entre 1 e 6", f"{onde}.colunas")
            el["so_visivel"] = bool(el.get("so_visivel", True))
            if el.get("camadas") is not None and not isinstance(el["camadas"], list):
                raise ErroLayout(f"{onde}: camadas precisa ser lista de ids", f"{onde}.camadas")
        elif tipo == "escala":
            div = el.get("divisoes", 4)
            if not isinstance(div, int) or not (1 <= div <= 10):
                raise ErroLayout(f"{onde}: divisoes entre 1 e 10", f"{onde}.divisoes")
            el["divisoes"] = div
            if el.get("unidade", "auto") not in ("auto", "m", "km"):
                raise ErroLayout(f"{onde}: unidade auto, m ou km", f"{onde}.unidade")
        elif tipo == "norte":
            ref = el.get("referencia", "verdadeiro")
            if ref not in REFERENCIAS_NORTE:
                raise ErroLayout(f"{onde}: referencia verdadeiro ou grade", f"{onde}.referencia")
            el["referencia"] = ref
        elif tipo == "grade":
            crs = str(el.get("crs", "utm"))
            if crs not in CRS_GRADE:
                raise ErroLayout(f"{onde}: crs 4326 ou utm", f"{onde}.crs")
            el["crs"] = crs
            if el.get("intervalo") is not None:
                _num(el, "intervalo", 1e-6, 1e7, onde)
            el["rotulos"] = bool(el.get("rotulos", True))
        elif tipo in ("titulo", "texto"):
            texto = el.get("texto", "")
            if not isinstance(texto, str) or len(texto) > limites.LAYOUT_TEXTO_MAX:
                raise ErroLayout(f"{onde}: texto de até {limites.LAYOUT_TEXTO_MAX} caracteres", f"{onde}.texto")
            el["tamanho_pt"] = _num(el, "tamanho_pt", 4, 120, onde, obrigatorio=False) or (
                18.0 if tipo == "titulo" else 10.0
            )
            if el.get("alinhamento", "esquerda") not in ("esquerda", "centro", "direita"):
                raise ErroLayout(f"{onde}: alinhamento esquerda, centro ou direita", f"{onde}.alinhamento")
        elif tipo == "imagem":
            origem = el.get("origem", "logo")
            if origem not in ("logo", "sha256"):
                raise ErroLayout(f"{onde}: origem logo ou sha256", f"{onde}.origem")
            if origem == "sha256" and not isinstance(el.get("sha256"), str):
                raise ErroLayout(f"{onde}: origem sha256 exige sha256", f"{onde}.sha256")
            el["origem"] = origem
        elif tipo == "tabela":
            if not (el.get("selecao_id") or el.get("camada_id")):
                raise ErroLayout(f"{onde}: tabela exige selecao_id ou camada_id", f"{onde}.selecao_id")
            lm = el.get("linhas_max", 20)
            if not isinstance(lm, int) or not (1 <= lm <= limites.LAYOUT_TABELA_LINHAS_MAX):
                raise ErroLayout(
                    f"{onde}: linhas_max entre 1 e {limites.LAYOUT_TABELA_LINHAS_MAX}", f"{onde}.linhas_max"
                )
            el["linhas_max"] = lm
    if quadros > limites.LAYOUT_QUADROS_MAX:
        raise ErroLayout(f"no máximo {limites.LAYOUT_QUADROS_MAX} quadros de mapa", "elementos")
    d["elementos"] = elementos
    return d


# ---------------------------------------------------------------- modelos padrão (em código: valem para todo inquilino)
def _mapa(x, y, w, h, **extra):
    return {"tipo": "mapa", "id": "mapa", "x": x, "y": y, "w": w, "h": h, "modo": "extensao", "moldura": True, **extra}


MODELOS_PADRAO: list[dict] = [
    {
        "id": "a4-retrato-simples",
        "nome": "A4 retrato — mapa com título",
        "papel": "A4",
        "orientacao": "retrato",
        "margens_mm": {"superior": 10, "inferior": 10, "esquerda": 10, "direita": 10},
        "modelo": True,
        "elementos": [
            {
                "tipo": "titulo",
                "id": "titulo",
                "x": 10,
                "y": 8,
                "w": 190,
                "h": 12,
                "texto": "{titulo_mapa}",
                "tamanho_pt": 18,
            },
            _mapa(10, 22, 190, 235),
            {"tipo": "escala", "id": "escala", "x": 10, "y": 262, "w": 70, "h": 12, "divisoes": 4, "unidade": "auto"},
            {"tipo": "norte", "id": "norte", "x": 185, "y": 258, "w": 15, "h": 20, "referencia": "verdadeiro"},
            {
                "tipo": "texto",
                "id": "rodape",
                "x": 10,
                "y": 280,
                "w": 130,
                "h": 8,
                "texto": "{inquilino} · {data} · escala {escala}",
                "tamanho_pt": 8,
            },
            {"tipo": "atribuicao", "id": "atribuicao", "x": 10, "y": 288, "w": 190, "h": 6},
        ],
    },
    {
        "id": "a4-paisagem-legenda",
        "nome": "A4 paisagem — mapa e legenda",
        "papel": "A4",
        "orientacao": "paisagem",
        "margens_mm": {"superior": 10, "inferior": 10, "esquerda": 10, "direita": 10},
        "modelo": True,
        "elementos": [
            {
                "tipo": "titulo",
                "id": "titulo",
                "x": 10,
                "y": 8,
                "w": 277,
                "h": 12,
                "texto": "{titulo_mapa}",
                "tamanho_pt": 18,
            },
            _mapa(10, 22, 205, 168),
            {
                "tipo": "legenda",
                "id": "legenda",
                "x": 220,
                "y": 22,
                "w": 67,
                "h": 120,
                "titulo": "Legenda",
                "colunas": 1,
            },
            {"tipo": "norte", "id": "norte", "x": 270, "y": 150, "w": 15, "h": 20, "referencia": "verdadeiro"},
            {"tipo": "escala", "id": "escala", "x": 220, "y": 176, "w": 67, "h": 12, "divisoes": 4, "unidade": "auto"},
            {"tipo": "data", "id": "data", "x": 220, "y": 192, "w": 67, "h": 6, "formato": "longa"},
            {"tipo": "atribuicao", "id": "atribuicao", "x": 10, "y": 200, "w": 277, "h": 6},
        ],
    },
    {
        "id": "a3-paisagem-completo",
        "nome": "A3 paisagem — mapa, legenda, escala, norte, grade e título",
        "papel": "A3",
        "orientacao": "paisagem",
        "margens_mm": {"superior": 10, "inferior": 10, "esquerda": 10, "direita": 10},
        "modelo": True,
        "elementos": [
            {
                "tipo": "titulo",
                "id": "titulo",
                "x": 15,
                "y": 10,
                "w": 300,
                "h": 14,
                "texto": "{titulo_mapa}",
                "tamanho_pt": 22,
            },
            {"tipo": "imagem", "id": "logo", "x": 355, "y": 8, "w": 50, "h": 18, "origem": "logo"},
            _mapa(15, 28, 300, 240),
            {"tipo": "grade", "id": "grade", "quadro": "mapa", "crs": "utm", "rotulos": True},
            {
                "tipo": "legenda",
                "id": "legenda",
                "x": 325,
                "y": 28,
                "w": 80,
                "h": 150,
                "titulo": "Legenda",
                "colunas": 1,
            },
            {"tipo": "norte", "id": "norte", "x": 385, "y": 190, "w": 20, "h": 26, "referencia": "grade"},
            {"tipo": "escala", "id": "escala", "x": 325, "y": 224, "w": 80, "h": 14, "divisoes": 4, "unidade": "auto"},
            {
                "tipo": "texto",
                "id": "rodape",
                "x": 325,
                "y": 246,
                "w": 80,
                "h": 22,
                "texto": "Escala {escala}\n{inquilino}\n{autor} · {data}",
                "tamanho_pt": 8,
            },
            {"tipo": "atribuicao", "id": "atribuicao", "x": 15, "y": 272, "w": 390, "h": 6},
        ],
    },
]


def modelo_padrao(id_modelo: str) -> dict | None:
    for m in MODELOS_PADRAO:
        if m["id"] == id_modelo:
            return copy.deepcopy(m)
    return None


def para_dimensoes_esri(m: dict) -> dict:
    """Uma linha do `Get Layout Templates Info` da Esri a partir de um modelo nosso."""
    largura, altura = dimensoes_papel(m["papel"], m["orientacao"])
    quadro = next((e for e in m["elementos"] if e["tipo"] == "mapa"), None)
    tipos = {e["tipo"] for e in m["elementos"]}
    return {
        "layoutTemplate": m["id"],
        "pageSize": [round(largura / 25.4, 2), round(altura / 25.4, 2)],
        "pageUnits": "INCHES",
        "activeDataFrameSize": [round(quadro["w"] / 25.4, 2), round(quadro["h"] / 25.4, 2)] if quadro else [0, 0],
        "layoutOptions": {
            "hasTitleText": "titulo" in tipos,
            "hasAuthorText": any(
                e["tipo"] in ("texto",) and "{autor}" in (e.get("texto") or "") for e in m["elementos"]
            ),
            "hasCopyrightText": "atribuicao" in tipos,
            "hasLegend": "legenda" in tipos,
            "customTextElements": [],
        },
    }
