"""Item L3-15-metadado-fator pela API, com a REFUTAÇÃO exigida no portão:

    "o adversário tenta salvar fator sem fonte e proxy com peso máximo".

As duas tentativas são feitas contra a API de verdade (`POST /api/amc/modelos/validar` e `POST /api/amc/modelos`)
e pela porta dos fundos (`POST /api/amc/execucoes` com pesos que sobrescrevem os do modelo). Em todos os casos a
resposta tem de ser 422 com a cláusula violada nomeada e a explicação do que fazer — e o modelo NÃO pode existir
depois.
"""

from tests.api.amc import exemplos
from tests.api.amc.test_amc_adversario_api import conjunto_pronto, criar_item, modelo_com_itens

PREFIXO = "zt-amcmeta"
CLAUSULA_TETO = "fatores[].proxy: fatia do peso <= proxy.teto_peso"
PROXY = {"descricao": "a camada mede presença declarada de vegetação, não supressão de árvore"}


def modelo_base() -> dict:
    m = exemplos.modelo_sem_camada_externa()
    m["nome"] = f"{PREFIXO} modelo"
    m["fatores"].append({
        "id": "veg", "nome": "vegetação declarada", "fonte": "camada de teste interno",
        "versao_fonte": "edição de teste 2026-09", "unidade": "%", "direcao": "menor_melhor", "base": "engenharia",
        "camada": {"tipo": "item", "id": "00000000-0000-0000-0000-000000000009"},
        "extrator": {"tipo": "valor_pronto", "parametros": {}},
        "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 100, "direcao": "decrescente"},
        "peso": 1.0, "proxy": dict(PROXY), "classe_peso": "apetite_de_risco", "ancora_peso": "escolhida",
        "nao_sustenta": "não distingue supressão de árvore de presença declarada de vegetação",
    })
    return m


def _n_modelos(sessao) -> int:
    r = sessao.get("/api/amc/modelos?limite=100")
    assert r.status_code == 200, r.text
    return len([m for m in r.json()["modelos"] if m["nome"].startswith(PREFIXO)])


# ---------------------------------------------------------------- o caminho feliz continua aberto
def test_modelo_com_metadado_completo_e_aceito(sessao_a):
    m = modelo_base()
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": m})
    assert r.status_code == 200, r.text
    assert r.json()["valido"] is True


# ---------------------------------------------------------------- refutação 1: fator sem fonte
def test_adversario_salva_fator_sem_fonte(sessao_a):
    m = modelo_base()
    del m["fatores"][-1]["fonte"]
    antes = _n_modelos(sessao_a)
    for rota in ("/api/amc/modelos/validar", "/api/amc/modelos"):
        r = sessao_a.post(rota, json={"definicao": m})
        assert r.status_code == 422, f"{rota} aceitou fator sem fonte: {r.text}"
        corpo = r.json()
        assert corpo["erro"] == "modelo_invalido", corpo
        violacoes = corpo["detalhe"]["violacoes"]
        assert any(v["caminho"] == "$.fatores[1]" and "fonte" in v["mensagem"] for v in violacoes), violacoes
    assert _n_modelos(sessao_a) == antes, "o modelo recusado não pode ter sido gravado"


def test_adversario_salva_fator_sem_base(sessao_a):
    m = modelo_base()
    del m["fatores"][-1]["base"]
    r = sessao_a.post("/api/amc/modelos", json={"definicao": m})
    assert r.status_code == 422, r.text
    violacoes = r.json()["detalhe"]["violacoes"]
    assert any(v["caminho"] == "$.fatores[1]" and "base" in v["mensagem"] for v in violacoes), violacoes


# ---------------------------------------------------------------- refutação 2: proxy com peso máximo
def test_adversario_salva_proxy_com_peso_maximo(sessao_a):
    """O adversário põe o proxy com o maior peso do modelo e os demais no menor peso possível."""
    m = modelo_base()
    m["fatores"][0]["peso"] = 0.001
    m["fatores"][-1]["peso"] = 1000.0
    antes = _n_modelos(sessao_a)
    for rota in ("/api/amc/modelos/validar", "/api/amc/modelos"):
        r = sessao_a.post(rota, json={"definicao": m})
        assert r.status_code == 422, f"{rota} aceitou proxy com peso máximo: {r.text}"
        corpo = r.json()
        violacoes = [v for v in corpo["detalhe"]["violacoes"] if v["clausula"] == CLAUSULA_TETO]
        assert len(violacoes) == 1, corpo["detalhe"]["violacoes"]
        mensagem = violacoes[0]["mensagem"]
        # a recusa EXPLICA: nomeia o fator, a fatia medida, o teto e o peso que caberia
        for pedaco in ("veg", "100.0%", "60.0%", "presença declarada", "reduza o peso"):
            assert pedaco in mensagem, mensagem
    assert _n_modelos(sessao_a) == antes, "o modelo recusado não pode ter sido gravado"


def test_adversario_tira_a_marca_de_proxy_e_o_peso_passa(sessao_a):
    """A regra vale para quem SE DECLARA proxy: o teto não é um limite universal de peso. Quem tira a marca
    responde pelo que declarou — é isso que a ficha e o relatório mostram."""
    m = modelo_base()
    m["fatores"][0]["peso"] = 0.001
    m["fatores"][-1]["peso"] = 1000.0
    del m["fatores"][-1]["proxy"]
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": m})
    assert r.status_code == 200, r.text


def test_adversario_zera_o_teto_do_proxy(sessao_a):
    """Teto 0 tornaria a regra vazia (nenhum peso o satisfaz, mas o documento fica impossível de salvar) —
    o esquema recusa teto não positivo em vez de aceitar um número que não quer dizer nada."""
    m = modelo_base()
    m["fatores"][-1]["proxy"] = {"descricao": PROXY["descricao"], "teto_peso": 0}
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": m})
    assert r.status_code == 422, r.text
    assert any(v["caminho"].endswith("teto_peso") for v in r.json()["detalhe"]["violacoes"]), r.text


def test_adversario_declara_proxy_sem_descricao(sessao_a):
    m = modelo_base()
    m["fatores"][-1]["proxy"] = {}
    r = sessao_a.post("/api/amc/modelos/validar", json={"definicao": m})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- porta dos fundos: pesos da execução
def test_adversario_estoura_o_teto_pelos_pesos_da_execucao(sessao_a, conexao_plat_app):
    """Modelo dentro do teto, execução fora: `POST /api/amc/execucoes` com `pesos` que sobrescrevem os do
    modelo. Este é o caminho que uma validação só no documento deixaria aberto."""
    # a execução resolve a proveniência de cada camada, então aqui as camadas apontam para itens REAIS
    m = modelo_com_itens(sessao_a)
    m["nome"] = f"{PREFIXO} modelo com itens"
    proxy = [f for f in modelo_base()["fatores"] if f["id"] == "veg"][0]
    proxy["camada"]["id"] = criar_item(sessao_a, "vegetação")
    m["fatores"].append(proxy)
    r = sessao_a.post("/api/amc/modelos", json={"definicao": m})
    assert r.status_code == 201, r.text
    modelo = r.json()
    conjunto = conjunto_pronto(sessao_a, conexao_plat_app, "a")
    try:
        r = sessao_a.post("/api/amc/execucoes", json={
            "modelo_id": modelo["id"], "conjunto_id": conjunto["id"], "semente": 7,
            "pesos": {"declividade": 0.001, "dist_via": 0.001, "veg": 1000.0}})
        assert r.status_code == 422, f"a execução aceitou o proxy acima do teto: {r.text}"
        corpo = r.json()
        assert corpo["erro"] == "pesos_invalidos", corpo
        assert any(v["clausula"] == CLAUSULA_TETO for v in corpo["detalhe"]["violacoes"]), corpo
        assert "60.0%" in corpo["mensagem"], corpo["mensagem"]

        # e o mesmo pedido com o proxy dentro do teto passa
        r = sessao_a.post("/api/amc/execucoes", json={
            "modelo_id": modelo["id"], "conjunto_id": conjunto["id"], "semente": 7,
            "pesos": {"declividade": 1.0, "dist_via": 1.0, "veg": 1.0}})
        assert r.status_code == 201, r.text
        sessao_a.delete(f"/api/amc/execucoes/{r.json()['id']}")
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
        sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")
