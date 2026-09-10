"""Fronteira de Pareto sobre uma execução do motor multicritério (item L3-08-pareto), pela API.

Portão, cláusula por cláusula:
  a) "ordenação não dominada conferida contra implementação ingênua O(n²)" -> a prova em 2.000 unidades
     está em tests/unit/test_amc_pareto.py; aqui o mesmo laço ingênuo confere o que a ROTA devolveu,
     sobre valores que vieram do banco;
  c) "export da fronteira como camada" -> test_camada_traz_a_fronteira_com_geometria_e_metodo.

A área de estudo é a mesma de tests/api/multiescala/test_multiescala.py (retângulo perto de São Paulo,
dado sintético). Dois fatores em direções opostas no espaço — um cresce para leste, outro para norte —
para que a fronteira tenha mais de uma unidade e a análise não seja trivial.
"""

import math
import secrets

import pytest

CENTRO = (-46.60, -23.50)
LADO_M = 1900.0
_M_POR_GRAU_LAT = 111_320.0
_M_POR_GRAU_LON = 111_320.0 * math.cos(math.radians(CENTRO[1]))
MEIA_LON = (LADO_M / 2) / _M_POR_GRAU_LON
MEIA_LAT = (LADO_M / 2) / _M_POR_GRAU_LAT


def _retangulo() -> dict:
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON, lon + MEIA_LON
    y0, y1 = lat - MEIA_LAT, lat + MEIA_LAT
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _amostras(eixo: str, n: int = 12) -> list[dict]:
    """Grade de pontos cobrindo o retângulo; o valor cresce no eixo pedido (leste ou norte)."""
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON * 0.92, lon + MEIA_LON * 0.92
    y0, y1 = lat - MEIA_LAT * 0.92, lat + MEIA_LAT * 0.92
    pontos = []
    for i in range(n):
        for j in range(n):
            fx, fy = i / (n - 1), j / (n - 1)
            pontos.append({
                "lon": x0 + (x1 - x0) * fx,
                "lat": y0 + (y1 - y0) * fy,
                "valor": 100.0 * (fx if eixo == "leste" else fy),
            })
    return pontos


def _criar_fator(sessao_a, eixo: str) -> dict:
    r = sessao_a.post("/api/multiescala/fatores", json={
        "nome": f"zt-pareto-{eixo}-{secrets.token_hex(4)}", "resolucao_fonte_m": 100.0, "papel": "atrai",
        "unidade": "un", "fonte": "amostra sintética de teste",
    })
    assert r.status_code == 201, r.text
    fator = r.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras", json={"amostras": _amostras(eixo)})
    assert ra.status_code == 201, ra.text
    return fator


@pytest.fixture
def execucao(sessao_a):
    """Execução macro de 500 m sobre o retângulo (4x4 = 16 células) com dois fatores em eixos opostos."""
    r = sessao_a.post("/api/multiescala/conjuntos",
                      json={"nome": f"zt-pareto-{secrets.token_hex(4)}", "area": _retangulo()})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    leste = _criar_fator(sessao_a, "leste")
    norte = _criar_fator(sessao_a, "norte")
    r = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": 500.0,
        "fatores": [{"fator_id": leste["id"], "peso": 1.0}, {"fator_id": norte["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
    })
    assert r.status_code == 201, r.text
    yield {"execucao": r.json(), "conjunto": conjunto, "leste": leste, "norte": norte}
    sessao_a.delete(f"/api/multiescala/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/multiescala/fatores/{leste['id']}")
    sessao_a.delete(f"/api/multiescala/fatores/{norte['id']}")


def _corpo(execucao, direcoes=("maximizar", "maximizar"), ordens=3, base="favorabilidade"):
    return {
        "execucao_id": execucao["execucao"]["id"],
        "ordens": ordens,
        "objetivos": [
            {"fator_id": execucao["leste"]["id"], "direcao": direcoes[0], "base": base},
            {"fator_id": execucao["norte"]["id"], "direcao": direcoes[1], "base": base},
        ],
    }


def _domina(a, b, direcoes) -> bool:
    melhor = False
    for x, y, d in zip(a, b, direcoes, strict=True):
        if (x < y) if d == "maximizar" else (x > y):
            return False
        if x != y:
            melhor = True
    return melhor


def _ingenuo(linhas, direcoes, ordens):
    """Mesma peneira O(n²) do teste de unidade, aplicada ao que a ROTA devolveu."""
    validos = [i for i, v in enumerate(linhas) if all(x is not None for x in v)]
    ordem = [0] * len(linhas)
    restantes = list(validos)
    for k in range(1, ordens + 1):
        frente = [
            i for i in restantes
            if not any(j != i and _domina(linhas[j], linhas[i], direcoes) for j in restantes)
        ]
        for i in frente:
            ordem[i] = k
        restantes = [i for i in restantes if i not in set(frente)]
        if not restantes:
            break
    return ordem


# ---------------------------------------------------------------- a) ordenação
def test_ordenacao_bate_com_o_laco_ingenuo_sobre_o_que_a_rota_devolveu(sessao_a, execucao):
    r = sessao_a.post("/api/amc/pareto", json=_corpo(execucao))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["unidades_avaliadas"] == execucao["execucao"]["celulas"]
    linhas = [u["valores"] for u in j["unidades"]]
    esperado = _ingenuo(linhas, ["maximizar", "maximizar"], 3)
    assert [u["ordem"] for u in j["unidades"]] == esperado
    assert sum(c["unidades"] for c in j["contagem_por_ordem"]) == j["classificadas"]
    assert "pesos" in j["aviso"], "todo resultado carrega a frase de que a fronteira não usa peso"
    assert [o["nome"] for o in j["objetivos"]] == [execucao["leste"]["nome"], execucao["norte"]["nome"]]


def test_fronteira_nao_e_trivial_e_muda_com_a_direcao(sessao_a, execucao):
    """Dois objetivos em eixos opostos: a fronteira tem mais de uma unidade, e inverter a direção de um
    deles troca a fronteira. É a demonstração do item: 'a melhor' depende do peso, que aqui não existe."""
    a = sessao_a.post("/api/amc/pareto", json=_corpo(execucao, ("maximizar", "maximizar"))).json()
    b = sessao_a.post("/api/amc/pareto", json=_corpo(execucao, ("maximizar", "minimizar"))).json()
    frente_a = {u["unidade_id"] for u in a["unidades"] if u["ordem"] == 1}
    frente_b = {u["unidade_id"] for u in b["unidades"] if u["ordem"] == 1}
    assert len(frente_a) > 1, a["contagem_por_ordem"]
    assert frente_a != frente_b


def test_objetivos_identicos_dao_o_maximo_e_seus_empates(sessao_a, execucao):
    """Refutação do item, agora pela rota: o mesmo fator nas duas bases é o mesmo valor em escala
    diferente, então a fronteira é a unidade de favorabilidade máxima e todos os seus empates."""
    corpo = _corpo(execucao)
    corpo["objetivos"][1] = dict(corpo["objetivos"][0])
    corpo["objetivos"][1]["base"] = "valor"
    r = sessao_a.post("/api/amc/pareto", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    com_dado = [u for u in j["unidades"] if u["valores"][0] is not None]
    maximo = max(u["valores"][0] for u in com_dado)
    frente = [u for u in j["unidades"] if u["ordem"] == 1]
    assert frente and all(u["valores"][0] == maximo for u in frente)
    assert len(frente) == sum(1 for u in com_dado if u["valores"][0] == maximo)


# ---------------------------------------------------------------- c) export como camada
def test_camada_traz_a_fronteira_com_geometria_e_metodo(sessao_a, execucao):
    corpo = _corpo(execucao)
    corpo["ordens_incluidas"] = [1]
    r = sessao_a.post("/api/amc/pareto/camada", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["type"] == "FeatureCollection"
    ordenacao = sessao_a.post("/api/amc/pareto", json=_corpo(execucao)).json()
    frente = {u["unidade_id"] for u in ordenacao["unidades"] if u["ordem"] == 1}
    assert {f["properties"]["unidade_id"] for f in j["features"]} == frente
    for f in j["features"]:
        assert f["geometry"]["type"] == "Polygon" and f["geometry"]["coordinates"]
        assert f["properties"]["ordem"] == 1
        assert execucao["leste"]["nome"] in f["properties"]
    assert j["metadados"]["ordens_incluidas"] == [1]
    assert "pesos" in j["metadados"]["aviso"]
    assert [o["direcao"] for o in j["metadados"]["objetivos"]] == ["maximizar", "maximizar"]


def test_camada_com_as_tres_ordens_traz_todas_as_classificadas(sessao_a, execucao):
    corpo = _corpo(execucao)
    corpo["ordens_incluidas"] = [1, 2, 3]
    j = sessao_a.post("/api/amc/pareto/camada", json=corpo).json()
    assert len(j["features"]) == j["metadados"]["classificadas"]
    assert {f["properties"]["ordem"] for f in j["features"]} <= {1, 2, 3}


# ---------------------------------------------------------------- contrato
@pytest.mark.parametrize(
    ("mudanca", "codigo"),
    [
        ({"objetivos": []}, None),                                   # pydantic: 422 sem código nosso
        ({"execucao_id": "nao-e-uuid"}, "execucao_id_invalido"),
        ({"ordens": 0}, None),
        ({"ordens_incluidas": []}, "ordens_incluidas_invalidas"),
        ({"ordens_incluidas": [4]}, "ordens_incluidas_invalidas"),
    ],
)
def test_contrato_da_rota(sessao_a, execucao, mudanca, codigo):
    corpo = _corpo(execucao)
    corpo["ordens_incluidas"] = [1]
    corpo.update(mudanca)
    r = sessao_a.post("/api/amc/pareto/camada", json=corpo)
    assert r.status_code == 422, r.text
    if codigo:
        assert r.json()["erro"] == codigo, r.text


def test_objetivo_repetido_na_mesma_base_e_recusado(sessao_a, execucao):
    corpo = _corpo(execucao)
    corpo["objetivos"][1] = dict(corpo["objetivos"][0])
    r = sessao_a.post("/api/amc/pareto", json=corpo)
    assert r.status_code == 422 and r.json()["erro"] == "objetivo_repetido", r.text


def test_fator_que_nao_e_da_execucao_e_recusado(sessao_a, execucao):
    outro = _criar_fator(sessao_a, "leste")
    corpo = _corpo(execucao)
    corpo["objetivos"][1]["fator_id"] = outro["id"]
    r = sessao_a.post("/api/amc/pareto", json=corpo)
    assert r.status_code == 422 and r.json()["erro"] == "fator_fora_da_execucao", r.text
    sessao_a.delete(f"/api/multiescala/fatores/{outro['id']}")


def test_execucao_inexistente_e_404(sessao_a, execucao):
    corpo = _corpo(execucao)
    corpo["execucao_id"] = "00000000-0000-0000-0000-000000000000"
    r = sessao_a.post("/api/amc/pareto", json=corpo)
    assert r.status_code == 404 and r.json()["erro"] == "execucao_inexistente", r.text
