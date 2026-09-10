"""Localizar regiões sobre uma execução REAL do motor multicritério (item L3-05-localizar-regioes):
`POST /api/multiescala/execucoes/{id}/regioes`. A prova de algoritmo (3 picos, área, forma, distâncias,
determinismo, 1 milhão de células) está em `tests/unit/test_regioes.py`, sem banco; aqui entra o que só existe
com a execução de verdade: a grade e a resolução saem de `plat.escala_grade`, a nota por célula de
`plat.escala_resultado`, e cada região volta com o POLÍGONO (união das células, 4326) e o ponto interno.

Área de estudo: 10 km × 10 km perto de São Paulo, grade macro de 250 m = 40×40 = 1.600 células. O fator tem
amostras que desenham três picos; as três regiões pedidas têm de cair sobre eles."""

from __future__ import annotations

import math
import secrets

import pytest

CENTRO = (-46.60, -23.50)
LADO_M = 10_000.0
RESOLUCAO_M = 250.0
_M_LAT = 111_320.0
_M_LON = 111_320.0 * math.cos(math.radians(CENTRO[1]))
MEIA_LON = (LADO_M / 2) / _M_LON
MEIA_LAT = (LADO_M / 2) / _M_LAT
# três picos, em fração do lado da área (x, y) — o mesmo desenho do teste de unidade, em coordenadas
PICOS = ((0.25, 0.25), (0.75, 0.30), (0.55, 0.80))


def _area() -> dict:
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON, lon + MEIA_LON
    y0, y1 = lat - MEIA_LAT, lat + MEIA_LAT
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _ponto(fx: float, fy: float) -> tuple[float, float]:
    lon, lat = CENTRO
    return (lon - MEIA_LON + 2 * MEIA_LON * fx, lat - MEIA_LAT + 2 * MEIA_LAT * fy)


def _amostras_tres_picos(n_por_lado: int = 45) -> list[dict]:
    """Grade de amostras cobrindo a área, com valor = soma de três gaussianas nos picos (mais um piso)."""
    amostras = []
    for i in range(n_por_lado):
        for j in range(n_por_lado):
            fx, fy = i / (n_por_lado - 1), j / (n_por_lado - 1)
            valor = 10.0
            for px, py in PICOS:
                d2 = (fx - px) ** 2 + (fy - py) ** 2
                valor += 80.0 * math.exp(-d2 / (2 * 0.06 ** 2))
            lon, lat = _ponto(0.02 + 0.96 * fx, 0.02 + 0.96 * fy)
            amostras.append({"lon": lon, "lat": lat, "valor": round(valor, 3)})
    return amostras


@pytest.fixture
def execucao(sessao_a):
    r = sessao_a.post("/api/multiescala/conjuntos",
                      json={"nome": f"zt-regioes-{secrets.token_hex(4)}", "area": _area()})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    r = sessao_a.post("/api/multiescala/fatores", json={
        "nome": f"zt-fator-picos-{secrets.token_hex(4)}", "resolucao_fonte_m": 200.0, "papel": "atrai",
        "unidade": "un", "fonte": "amostra sintética de teste (três picos)",
    })
    assert r.status_code == 201, r.text
    fator = r.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras",
                       json={"amostras": _amostras_tres_picos()})
    assert ra.status_code == 201, ra.text
    r = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": RESOLUCAO_M, "fatores": [{"fator_id": fator["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 30.0,
    })
    assert r.status_code == 201, r.text
    macro = r.json()
    assert macro["celulas_com_nota"] >= 1000, macro
    yield macro
    sessao_a.delete(f"/api/multiescala/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/multiescala/fatores/{fator['id']}")


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot((a[0] - b[0]) * _M_LON, (a[1] - b[1]) * _M_LAT)


def test_tres_regioes_sobre_a_execucao_real_com_poligono(sessao_a, execucao, medida):
    area_total = 3 * 20 * (RESOLUCAO_M ** 2)  # 20 células por região
    r = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json={
        "n_regioes": 3, "area_total_m2": area_total, "compromisso": 50, "semente_aleatoria": 7,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["execucao_id"] == execucao["id"]
    # 10 km / 250 m = 40 colunas nominais; a grade cobre a área inteira, então pode sair 41 (a última coluna
    # é a fatia que fecha o retângulo) — o que o teste fixa é a resolução, não o arredondamento da borda
    assert j["grade"]["resolucao_m"] == RESOLUCAO_M and j["grade"]["colunas"] in (40, 41)
    assert len(j["regioes"]) == 3
    assert abs(j["area_total"] - area_total) <= area_total * 0.05
    assert "pesos são escolhidos pelo usuário" in j["aviso_pesos"]
    picos = [_ponto(px, py) for px, py in PICOS]
    for reg in j["regioes"]:
        assert reg["geometria"]["type"] in ("Polygon", "MultiPolygon")
        assert reg["ponto_interno"]["type"] == "Point"
        assert reg["celulas"] == reg["celulas_ids"] and reg["celulas"] >= 1
        assert 0 <= reg["compacidade"] <= 1 and reg["media"] > 0
        ponto = tuple(reg["ponto_interno"]["coordinates"])
        assert min(_dist_m(ponto, p) for p in picos) <= 2.5 * RESOLUCAO_M, (ponto, picos)
    # uma região por pico
    achados = {min(range(3), key=lambda k: _dist_m(tuple(reg["ponto_interno"]["coordinates"]), picos[k]))
               for reg in j["regioes"]}
    assert achados == {0, 1, 2}
    m = medida("L3-05-localizar-regioes")
    m("execucao_real_celulas", int(execucao["celulas"]), "celulas", "grade macro de 250 m sobre 10 km × 10 km")
    m("execucao_real_regioes", len(j["regioes"]), "regioes", "POST /api/multiescala/execucoes/{id}/regioes")


def test_so_aprovadas_restringe_a_busca(sessao_a, execucao):
    area = 3 * 12 * (RESOLUCAO_M ** 2)
    corpo = {"n_regioes": 3, "area_total_m2": area, "semente_aleatoria": 7}
    tudo = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json=corpo).json()
    so_ok = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes",
                          json={**corpo, "so_aprovadas": True}).json()
    assert so_ok["parametros"]["area_disponivel"] < tudo["parametros"]["area_disponivel"]
    assert so_ok["parametros"]["area_disponivel"] > 0
    for reg in so_ok["regioes"]:
        assert reg["media"] >= 1.0


def test_forma_e_metodo_chegam_ao_motor(sessao_a, execucao):
    area = 40 * (RESOLUCAO_M ** 2)
    for forma in ("circulo", "quadrado", "hexagono"):
        j = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json={
            "n_regioes": 1, "area_total_m2": area, "compromisso": 100, "forma": forma, "semente_aleatoria": 7,
        }).json()
        assert j["parametros"]["forma"] == forma and j["regioes"][0]["compacidade"] >= 0.85, (forma, j["regioes"])
    for metodo in ("maior_media", "maior_soma", "mediana", "maior_area_nucleo"):
        j = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json={
            "n_regioes": 2, "area_total_m2": 2 * area, "metodo": metodo, "semente_aleatoria": 7,
        }).json()
        assert j["parametros"]["metodo"] == metodo and len(j["regioes"]) == 2


def test_recusas_com_codigo_e_mensagem(sessao_a, execucao):
    # área maior que a disponível: 422 com o número, nunca 500
    r = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes",
                      json={"n_regioes": 1, "area_total_m2": 1e12})
    assert r.status_code == 422 and r.json()["erro"] == "area_maior_que_a_disponivel"
    assert r.json()["detalhe"]["area_disponivel"] > 0
    # N = 31: recusado pelo modelo da rota (o teto é o mesmo da referência)
    r = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json={"n_regioes": 31})
    assert r.status_code == 422
    # execução inexistente e id inválido
    nulo = "00000000-0000-4000-8000-000000000000"
    assert sessao_a.post(f"/api/multiescala/execucoes/{nulo}/regioes", json={"n_regioes": 1}).status_code == 404
    assert sessao_a.post("/api/multiescala/execucoes/nao-e-uuid/regioes", json={"n_regioes": 1}).status_code == 404


def test_mesma_semente_mesma_resposta_pela_api(sessao_a, execucao):
    corpo = {"n_regioes": 3, "area_total_m2": 3 * 15 * (RESOLUCAO_M ** 2), "semente_aleatoria": 42}
    a = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json=corpo).json()
    b = sessao_a.post(f"/api/multiescala/execucoes/{execucao['id']}/regioes", json=corpo).json()
    assert a["regioes"] == b["regioes"] and a["area_total"] == b["area_total"]
