"""Item L3-01-g-tela-motor pela API de verdade: GET /api/amc/execucoes/{id}/matriz e
POST /api/amc/transformacoes/previsao.

A matriz é o que permite a tela recombinar ao mover um peso SEM novo job: ela traz, por unidade, o valor bruto
e a favorabilidade de cada fator. Os dois testes centrais são (1) a favorabilidade por fator da matriz é a
MESMA que a rota de explicação devolve para a mesma unidade — se divergirem, a tela e a explicação contam
histórias diferentes sobre o mesmo número; e (2) recombinar a matriz com pesos novos dá o mesmo que o
combinador do servidor com os mesmos pesos, que é a afirmação inteira do item.

Modelo de cinco fatores (dois raster, dois polígono, um ponto), o mesmo que o portão do item nomeia."""

import pytest

from app.amc.combinacao import combinar
from tests.api.amc import exemplos
from tests.api.amc.test_amc_adversario_api import (
    conjunto_pronto,
    contexto,
    criar_item,
    ids_por_slug,
)

PREFIXO = "zt-amcmatriz"
# valores brutos por unidade, escolhidos para dar favorabilidade fechada em cada transformação do modelo:
# declividade 12 % (linear 0-30 decrescente -> 60) · altitude 700 m (linear 500-900 crescente -> 50) ·
# uso_urbano 0,25 (linear 0-1 crescente -> 25) · restricao_amb 0,20 (linear 0-1 decrescente -> 80) ·
# dist_acesso 1000 m (degraus, banda "até 2000" -> 60)
BRUTOS = {"declividade": 12.0, "altitude": 700.0, "uso_urbano": 0.25, "restricao_amb": 0.20,
          "dist_acesso": 1000.0}
FAVORABILIDADES = {"declividade": 60.0, "altitude": 50.0, "uso_urbano": 25.0, "restricao_amb": 80.0,
                   "dist_acesso": 60.0}


def modelo_cinco_com_itens(sessao) -> dict:
    m = exemplos.modelo_cinco_fatores()
    m["nome"] = f"{PREFIXO} modelo"
    for f in m["fatores"]:
        f["camada"]["id"] = criar_item(sessao, f["id"])
    for r in m.get("restricoes") or []:
        r["camada"]["id"] = criar_item(sessao, r["id"])
    return m


@pytest.fixture
def cenario(sessao_a, conexao_plat_app):
    definicao = modelo_cinco_com_itens(sessao_a)
    r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo = r.json()
    conjunto = conjunto_pronto(sessao_a, conexao_plat_app, "a")
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"],
                                                  "semente": 5})
    assert r.status_code == 201, r.text
    execucao = r.json()
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    contexto(conexao_plat_app, tenant_id)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT unidade_id FROM plat.amc_unidade WHERE conjunto_id = %s ORDER BY unidade_id LIMIT 3",
                    (conjunto["id"],))
        unidades = [x["unidade_id"] for x in cur.fetchall()]
    assert len(unidades) >= 3, "grade pequena não gerou unidades suficientes"
    contexto(conexao_plat_app, tenant_id)
    with conexao_plat_app.cursor() as cur:
        for k, u in enumerate(unidades):
            for fator, valor in BRUTOS.items():
                # a terceira unidade fica SEM um dos fatores: a matriz tem de devolver NULL, nunca 0
                if k == 2 and fator == "altitude":
                    continue
                cur.execute("INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, "
                            "cobertura) VALUES (%s::uuid, %s, %s, %s, %s, 1.0)",
                            (execucao["id"], tenant_id, u, fator, valor))
        # a segunda unidade é vetada por restrição declarada
        # o banco exige favorabilidade NULL na linha vetada (CHECK de 20260907T1206_amc.sql): unidade vetada
        # não carrega nota, carrega motivo
        cur.execute("INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, vetado, "
                    "motivo, cobertura) VALUES (%s::uuid, %s, %s, NULL, true, %s, 1.0)",
                    (execucao["id"], tenant_id, unidades[1], "vetado por precaução: unidade sobre área alagável"))
    conexao_plat_app.commit()
    yield {"definicao": definicao, "modelo": modelo, "conjunto": conjunto, "execucao": execucao,
           "unidades": unidades}
    sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")
    sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


def test_matriz_traz_cinco_fatores_com_proveniencia(cenario, sessao_a):
    r = sessao_a.get(f"/api/amc/execucoes/{cenario['execucao']['id']}/matriz")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["aviso_pesos"] == "pesos escolhidos pelo usuário, não medidos"
    assert [f["id"] for f in corpo["fatores"]] == list(BRUTOS)
    for f in corpo["fatores"]:
        assert f["fonte"] and f["unidade"] and f["base"] and f["extrator_tipo"]
    assert corpo["total"] == 3
    assert corpo["combinador"]["tipo"] == "soma_ponderada_normalizada"
    assert corpo["dado_ausente"] == "excluir_fator"


def test_favorabilidade_por_fator_e_a_declarada_e_ausencia_fica_nula(cenario, sessao_a):
    r = sessao_a.get(f"/api/amc/execucoes/{cenario['execucao']['id']}/matriz")
    corpo = r.json()
    ordem = [f["id"] for f in corpo["fatores"]]
    por_id = {u["unidade_id"]: u for u in corpo["unidades"]}
    primeira = por_id[cenario["unidades"][0]]
    for i, fid in enumerate(ordem):
        assert primeira["favorabilidades"][i] == pytest.approx(FAVORABILIDADES[fid], abs=0.5), fid
        assert primeira["brutos"][i] == pytest.approx(BRUTOS[fid])
    terceira = por_id[cenario["unidades"][2]]
    j = ordem.index("altitude")
    assert terceira["brutos"][j] is None
    assert terceira["favorabilidades"][j] is None  # ausência de dado nunca vira 0


def test_veto_da_matriz_e_o_gravado(cenario, sessao_a):
    r = sessao_a.get(f"/api/amc/execucoes/{cenario['execucao']['id']}/matriz")
    por_id = {u["unidade_id"]: u for u in r.json()["unidades"]}
    vetada = por_id[cenario["unidades"][1]]
    assert vetada["vetado"] is True
    assert "precaução" in vetada["motivo"]
    assert por_id[cenario["unidades"][0]]["vetado"] is False


def test_matriz_e_explicacao_dao_o_mesmo_numero_por_fator(cenario, sessao_a):
    """Sem isto a tela do motor e a tela de explicação poderiam contar histórias diferentes do mesmo fator."""
    eid = cenario["execucao"]["id"]
    unidade = cenario["unidades"][0]
    m = sessao_a.get(f"/api/amc/execucoes/{eid}/matriz").json()
    e = sessao_a.get(f"/api/amc/execucoes/{eid}/unidades/{unidade}/explicacao").json()
    ordem = [f["id"] for f in m["fatores"]]
    da_matriz = dict(zip(ordem, next(u for u in m["unidades"] if u["unidade_id"] == unidade)["favorabilidades"],
                         strict=True))
    for f in e["fatores"]:
        assert da_matriz[f["fator_id"]] == pytest.approx(f["favorabilidade_fator"], abs=1e-9), f["fator_id"]


def test_recombinar_a_matriz_com_pesos_novos_bate_o_combinador_do_servidor(cenario, sessao_a):
    """A afirmação central do item: mover um peso não exige novo job, porque a parte cara (a extração) já está
    na matriz e a parte barata (a soma ponderada) é a mesma conta em qualquer lado."""
    m = sessao_a.get(f"/api/amc/execucoes/{cenario['execucao']['id']}/matriz").json()
    ordem = [f["id"] for f in m["fatores"]]
    pesos_novos = [5.0, 0.5, 1.0, 4.0, 2.0]
    linhas = [u["favorabilidades"] for u in m["unidades"]]
    fracao_vetada = [1.0 if u["vetado"] else 0.0 for u in m["unidades"]]
    r = combinar(linhas, pesos_novos, combinador="soma_ponderada", politica_ausente="excluir",
                 fracao_vetada=fracao_vetada, ids_fatores=ordem)
    esperado_primeira = sum(FAVORABILIDADES[f] * w for f, w in zip(ordem, pesos_novos, strict=True)) \
        / sum(pesos_novos)
    i0 = [u["unidade_id"] for u in m["unidades"]].index(cenario["unidades"][0])
    assert r.fav[i0] == pytest.approx(esperado_primeira, abs=0.5)
    i1 = [u["unidade_id"] for u in m["unidades"]].index(cenario["unidades"][1])
    assert r.fav[i1] == pytest.approx(0.0)  # a unidade vetada zera, por veto e não por peso


def test_previsao_devolve_histograma_e_curva_da_transformacao(cenario, sessao_a):
    valores = [float(x) for x in range(0, 31)]
    r = sessao_a.post("/api/amc/transformacoes/previsao", json={
        "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 30, "direcao": "decrescente"},
        "valores": valores})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["n"] == 31 and corpo["n_nulo"] == 0
    assert sum(corpo["entrada_histograma"]["contagens"]) == 31
    assert sum(corpo["saida_histograma"]["contagens"]) == 31
    pares = corpo["curva"]["pares"]
    assert pares[0][1] == pytest.approx(100.0, abs=0.5)   # valor mínimo, direção decrescente
    assert pares[-1][1] == pytest.approx(0.0, abs=0.5)


def test_previsao_com_transformacao_impossivel_e_recusada_com_razao(sessao_a):
    r = sessao_a.post("/api/amc/transformacoes/previsao",
                      json={"transformacao": {"tipo": "nao_existe"}, "valores": [1.0]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "transformacao_invalida", r.text


def test_matriz_de_execucao_inexistente_e_404(sessao_a):
    r = sessao_a.get("/api/amc/execucoes/00000000-0000-0000-0000-000000000000/matriz")
    assert r.status_code == 404
