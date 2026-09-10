"""Geometria da linguagem de expressão (item L5-11): os números têm de bater com a FÓRMULA FECHADA
correspondente, não com o que o próprio código devolveu. Cada teste aqui compara contra uma
referência escrita à mão (integral da faixa esférica, arco de meridiano, meia-volta da esfera) ou
contra uma propriedade que não depende da implementação (simetria, desigualdade triangular,
monotonia). A igualdade Python × JavaScript é conferida em `test_expressao_equivalencia.py` pelos
vetores de `tests/expressoes/vetores.json`."""

import math
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.expressao.avaliador_py import (  # noqa: E402
    CASAS_GEO,
    RAIO_TERRA_M,
    ErroExpressao,
    avaliar_texto,
)

CELULA_1_GRAU = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def _ponto(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


def _celula(lon1, lat1, lon2, lat2):
    return {
        "type": "Polygon",
        "coordinates": [[[lon1, lat1], [lon2, lat1], [lon2, lat2], [lon1, lat2], [lon1, lat1]]],
    }


def _area_de_faixa(lon1, lat1, lon2, lat2):
    """Referência independente: integral da faixa esférica, A = R²·Δλ·(sin φ₂ − sin φ₁)."""
    dlon = math.radians(lon2 - lon1)
    return RAIO_TERRA_M**2 * dlon * (math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)))


@pytest.mark.parametrize(
    "lon1,lat1,lon2,lat2",
    [(0, 0, 1, 1), (0, 0, 0.01, 0.01), (-46.7, -23.6, -46.6, -23.5), (10, 60, 11, 61), (-180, -90, -179, -89)],
)
def test_area_bate_com_a_integral_da_faixa_esferica(lon1, lat1, lon2, lat2):
    esperado = _area_de_faixa(lon1, lat1, lon2, lat2)
    medido = avaliar_texto("Area($g)", {"g": _celula(lon1, lat1, lon2, lat2)})
    assert medido == pytest.approx(esperado, rel=1e-9, abs=10 ** -CASAS_GEO)


def test_area_desconta_o_anel_interno():
    externo = _celula(0, 0, 1, 1)["coordinates"][0]
    interno = _celula(0.25, 0.25, 0.75, 0.75)["coordinates"][0]
    com_buraco = {"type": "Polygon", "coordinates": [externo, interno]}
    esperado = _area_de_faixa(0, 0, 1, 1) - _area_de_faixa(0.25, 0.25, 0.75, 0.75)
    assert avaliar_texto("Area($g)", {"g": com_buraco}) == pytest.approx(esperado, rel=1e-9)


def test_area_nao_depende_da_orientacao_do_anel():
    horario = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    assert avaliar_texto("Area($g)", {"g": horario}) == avaliar_texto("Area($g)", {"g": CELULA_1_GRAU})


def test_area_de_poligono_degenerado_e_zero_e_nunca_negativa():
    degenerado = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0], [1, 0], [0, 0]]]}
    assert avaliar_texto("Area($g)", {"g": degenerado}) == 0


def test_comprimento_de_um_grau_de_meridiano_e_o_arco_de_circulo_maximo():
    linha = {"type": "LineString", "coordinates": [[0, 0], [0, 1]]}
    esperado = RAIO_TERRA_M * math.radians(1)
    assert avaliar_texto("Comprimento($l)", {"l": linha}) == pytest.approx(esperado, rel=1e-9)


def test_comprimento_soma_os_segmentos_na_ordem():
    l1 = {"type": "LineString", "coordinates": [[0, 0], [0, 1]]}
    l2 = {"type": "LineString", "coordinates": [[0, 1], [1, 1]]}
    l3 = {"type": "LineString", "coordinates": [[0, 0], [0, 1], [1, 1]]}
    soma = avaliar_texto("Comprimento($a) + Comprimento($b)", {"a": l1, "b": l2})
    assert avaliar_texto("Comprimento($l)", {"l": l3}) == pytest.approx(soma, abs=10 ** -CASAS_GEO * 3)


def test_distancia_entre_polos_e_meia_volta_da_esfera():
    ctx = {"a": {"type": "Point", "coordinates": [0, 90]}, "b": {"type": "Point", "coordinates": [0, -90]}}
    assert avaliar_texto("Distancia($a, $b)", ctx) == pytest.approx(math.pi * RAIO_TERRA_M, rel=1e-12)


def test_distancia_e_simetrica_e_zero_no_mesmo_ponto():
    ctx = {"a": {"type": "Point", "coordinates": [-46.6, -23.5]}, "b": {"type": "Point", "coordinates": [-43.2, -22.9]}}
    assert avaliar_texto("Distancia($a, $b)", ctx) == avaliar_texto("Distancia($b, $a)", ctx)
    assert avaliar_texto("Distancia($a, $a)", ctx) == 0


def test_distancia_respeita_a_desigualdade_triangular():
    ctx = {
        "a": {"type": "Point", "coordinates": [-46.6, -23.5]},
        "b": {"type": "Point", "coordinates": [-43.2, -22.9]},
        "c": {"type": "Point", "coordinates": [-47.9, -15.8]},
    }
    direta = avaliar_texto("Distancia($a, $b)", ctx)
    desvio = avaliar_texto("Distancia($a, $c) + Distancia($c, $b)", ctx)
    assert direta <= desvio + 10 ** -CASAS_GEO


def test_distancia_curta_bate_com_o_arco_de_paralelo_no_equador():
    ctx = {"a": _ponto(0, 0), "b": _ponto(0.5, 0)}
    esperado = RAIO_TERRA_M * math.radians(0.5)
    assert avaliar_texto("Distancia($a, $b)", ctx) == pytest.approx(esperado, rel=1e-12, abs=10 ** -CASAS_GEO)


@pytest.mark.parametrize(
    "lon,lat,esperado",
    [
        (0.5, 0.5, True),  # interior
        (2.0, 2.0, False),  # fora, fora da caixa
        (1.5, 0.5, False),  # fora, dentro da faixa de latitude
        (0.0, 0.0, True),  # vértice conta como dentro
        (0.5, 0.0, True),  # aresta conta como dentro
        (1.0, 0.5, True),  # aresta oposta conta como dentro
        (0.0, 1.5, False),  # acima do polígono
    ],
)
def test_dentro_no_quadrado(lon, lat, esperado):
    ctx = {"p": {"type": "Point", "coordinates": [lon, lat]}, "g": CELULA_1_GRAU}
    assert avaliar_texto("Dentro($p, $g)", ctx) is esperado


def test_dentro_em_poligono_concavo_em_forma_de_c():
    c = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [3, 0], [3, 1], [1, 1], [1, 2], [3, 2], [3, 3], [0, 3], [0, 0]]],
    }
    dentro = {"type": "Point", "coordinates": [0.5, 1.5]}
    no_vao = {"type": "Point", "coordinates": [2.0, 1.5]}
    assert avaliar_texto("Dentro($p, $g)", {"p": dentro, "g": c}) is True
    assert avaliar_texto("Dentro($p, $g)", {"p": no_vao, "g": c}) is False


def test_dentro_trata_o_buraco_como_fora_e_a_coroa_como_dentro():
    com_buraco = {
        "type": "Polygon",
        "coordinates": [_celula(0, 0, 1, 1)["coordinates"][0], _celula(0.25, 0.25, 0.75, 0.75)["coordinates"][0]],
    }
    no_buraco = {"type": "Point", "coordinates": [0.5, 0.5]}
    na_coroa = {"type": "Point", "coordinates": [0.1, 0.1]}
    assert avaliar_texto("Dentro($p, $g)", {"p": no_buraco, "g": com_buraco}) is False
    assert avaliar_texto("Dentro($p, $g)", {"p": na_coroa, "g": com_buraco}) is True


@pytest.mark.parametrize(
    "expressao,contexto",
    [
        ("Area($g)", {"g": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}),
        ("Comprimento($g)", {"g": CELULA_1_GRAU}),
        ("Area($g)", {"g": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}}),
        ("Area($g)", {"g": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]}}),
        ("Area($g)", {"g": {"type": "Polygon", "coordinates": []}}),
        ("Area($g)", {"g": {"type": "Polygon"}}),
        ("Area($g)", {"g": {"tipo": "Poligono", "coordenadas": []}}),
        ("Comprimento($g)", {"g": {"type": "LineString", "coordinates": [[0, 0]]}}),
        ("Distancia($a, $b)", {"a": _ponto(0, 91), "b": _ponto(0, 0)}),
        ("Distancia($a, $b)", {"a": _ponto(181, 0), "b": _ponto(0, 0)}),
        ("Distancia($a, $b)", {"a": {"type": "Point", "coordinates": ["0", 0]}, "b": _ponto(0, 0)}),
        ("Distancia($a, $b)", {"a": {"type": "Point", "coordinates": [0]}, "b": _ponto(0, 0)}),
    ],
)
def test_geometria_fora_do_contrato_da_erro_nomeado(expressao, contexto):
    with pytest.raises(ErroExpressao) as excecao:
        avaliar_texto(expressao, contexto)
    assert excecao.value.codigo == "geometria_invalida"


def test_geometria_nula_propaga_nulo():
    assert avaliar_texto("Area($g)", {"g": None}) is None
    assert avaliar_texto("Comprimento($g)", {"g": None}) is None
    assert avaliar_texto("Dentro($p, $g)", {"p": None, "g": CELULA_1_GRAU}) is None


def test_resultado_metrico_tem_no_maximo_as_casas_declaradas():
    """O arredondamento a CASAS_GEO é o que permite os dois avaliadores devolverem o MESMO número."""
    valor = avaliar_texto("Area($g)", {"g": _celula(-46.7123, -23.6456, -46.6987, -23.6321)})
    assert round(valor, CASAS_GEO) == valor


def test_geometria_grande_consome_o_orcamento_de_passos():
    anel = [[i * 0.001, 0.0] for i in range(400)] + [[0.4, 0.4], [0.0, 0.0]]
    grande = {"type": "Polygon", "coordinates": [anel]}
    with pytest.raises(ErroExpressao) as excecao:
        avaliar_texto("Area($g)", {"g": grande}, limite_passos=50)
    assert excecao.value.codigo == "limite_passos"


# ------------------------------------------------------------------ erros nomeados nos dois runtimes

VETORES_ERROS = RAIZ / "tests" / "expressoes" / "vetores_geometria_erros.json"
RUNNER = RAIZ / "tests" / "expressoes" / "executar_js.mjs"


def test_vetores_de_erro_dao_o_mesmo_codigo_no_python_e_no_javascript():
    """Estes vetores vivem em arquivo próprio porque `vetores.json` é o corpus dos vetores que
    AVALIAM (todo item de lá tem `saida`); aqui a saída esperada é o CÓDIGO do erro, e a igualdade
    exigida é entre os dois avaliadores."""
    import json
    import subprocess

    casos = json.loads(VETORES_ERROS.read_text(encoding="utf-8"))
    assert len(casos) >= 10
    r = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=json.dumps(casos),
        cwd=RAIZ,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    resultados = json.loads(r.stdout)
    for caso, obtido in zip(casos, resultados, strict=True):
        with pytest.raises(ErroExpressao) as excecao:
            avaliar_texto(caso["entrada"], caso.get("contexto") or {})
        assert excecao.value.codigo == caso["erro"], caso["descricao"]
        assert obtido["erro"] == caso["erro"], caso["descricao"]
