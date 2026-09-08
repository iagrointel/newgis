"""Simbologia e legenda do visualizador (item L2-01-mapa-web, app/mapa/simbologia.py).

A cláusula do portão é "legenda gerada a partir da simbologia, não escrita à mão". O que se prova aqui:
as cores que aparecem na legenda são LITERALMENTE as mesmas que entram na expressão de pintura do
MapLibre, porque as duas saem da função `classes()`. Mudar a simbologia muda as duas na mesma jogada."""

import pytest

from app.mapa import simbologia as s


def _cores_do_estilo(camadas):
    """extrai as cores de uma expressão MapLibre `case` (ou de uma cor literal)."""
    cores = []
    for c in camadas:
        if c["id"].endswith("-contorno"):
            continue  # o contorno do polígono é cor fixa de desenho, não uma classe da legenda
        pintura = c["paint"]
        valor = pintura.get("circle-color") or pintura.get("line-color") or pintura.get("fill-color")
        if isinstance(valor, str):
            cores.append(valor)
        elif isinstance(valor, list) and valor[0] == "case":
            cores.extend(v for v in valor[1:] if isinstance(v, str) and v.startswith("#"))
    return cores


@pytest.mark.parametrize("geometria,tipo_esperado", [
    ("Point", "circle"), ("MultiPoint", "circle"),
    ("LineString", "line"), ("MultiLineString", "line"),
    ("Polygon", "fill"), ("MultiPolygon", "fill"),
])
def test_padrao_por_geometria(geometria, tipo_esperado):
    simb = s.padrao(geometria)
    camadas = s.camadas_maplibre(simb, geometria, "x", "f", "c")
    assert camadas[0]["type"] == tipo_esperado
    assert len(s.legenda(simb, geometria)) == 1


def test_legenda_e_estilo_usam_as_mesmas_cores_em_valores_unicos():
    simb = {"tipo": "valores_unicos", "campo": "categoria", "valores": ["norte", "sul", "leste"]}
    legenda = s.legenda(simb, "Point")
    estilo = s.camadas_maplibre(simb, "Point", "x", "f", "c")
    assert [e["rotulo"] for e in legenda] == ["norte", "sul", "leste", "outros"]
    assert [e["cor"] for e in legenda] == _cores_do_estilo(estilo)


def test_legenda_e_estilo_usam_as_mesmas_cores_em_intervalos():
    simb = {"tipo": "intervalos", "campo": "valor", "cortes": [10, 20, 30]}
    legenda = s.legenda(simb, "Polygon")
    estilo = s.camadas_maplibre(simb, "Polygon", "x", "f", "c")
    assert [e["rotulo"] for e in legenda] == ["< 10", "10 a 20", "20 a 30", ">= 30"]
    assert [e["cor"] for e in legenda] == _cores_do_estilo(estilo)


def test_cor_declarada_pelo_usuario_vence_a_paleta():
    simb = {"tipo": "valores_unicos", "campo": "c", "valores": ["a", "b"], "cores": ["#111111", "#222222"]}
    assert [e["cor"] for e in s.legenda(simb, "Point")][:2] == ["#111111", "#222222"]


@pytest.mark.parametrize("ruim", [
    {"tipo": "mapa_de_calor"},                                  # fora do vocabulário fechado
    {"tipo": "valores_unicos"},                                 # sem campo
    {"tipo": "valores_unicos", "campo": "c"},                   # sem valores
    {"tipo": "intervalos", "campo": "v"},                       # sem cortes
])
def test_simbologia_invalida_e_recusada_sem_cair_no_padrao(ruim):
    with pytest.raises(s.SimbologiaInvalida):
        s.normalizar(ruim, "Point")


def test_estilo_e_style_spec_pura():
    """nenhuma chave nossa vaza para dentro da camada de estilo (conceito C2: Style Spec pura)."""
    simb = {"tipo": "valores_unicos", "campo": "c", "valores": ["a"]}
    for camada in s.camadas_maplibre(simb, "Polygon", "x", "f", "c"):
        assert set(camada) <= {"id", "type", "source", "source-layer", "paint", "layout", "filter",
                               "minzoom", "maxzoom"}
