"""Item L3-01-f-explicacao pela API de verdade: GET /api/amc/execucoes/{id}/unidades/{id}/explicacao.

O cálculo em si (transformação, soma das contribuições, 100 unidades sorteadas) já está provado sem banco em
tests/unit/test_amc_explicacao.py; aqui a prova é que a ROTA busca as três peças certas (definição da versão do
modelo, pesos da execução, fatores brutos gravados) e devolve o mesmo número, sobre um modelo e um conjunto REAIS
criados pela API — inclusive o caso de unidade vetada e o de unidade sem extração (404, não um número inventado).
Latência: item exige resposta em ≤ 100 ms; medida com a máquina calma, carga registrada ao lado (ver brief comum
de 07/09, "cláusula de desempenho")."""

import os
import time

import pytest

from tests.api.amc.test_amc_adversario_api import conjunto_pronto, contexto, ids_por_slug, modelo_com_itens

PREFIXO = "zt-amcexpl"


@pytest.fixture
def cenario(sessao_a, conexao_plat_app):
    definicao = modelo_com_itens(sessao_a)
    definicao["nome"] = f"{PREFIXO} modelo"
    r = sessao_a.post("/api/amc/modelos", json={"definicao": definicao})
    assert r.status_code == 201, r.text
    modelo = r.json()
    conjunto = conjunto_pronto(sessao_a, conexao_plat_app, "a")
    r = sessao_a.post("/api/amc/execucoes", json={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"],
                                                  "semente": 7})
    assert r.status_code == 201, r.text
    execucao = r.json()
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT unidade_id FROM plat.amc_unidade WHERE conjunto_id = %s ORDER BY unidade_id LIMIT 3",
                    (conjunto["id"],))
        unidades = [row["unidade_id"] for row in cur.fetchall()]
    conexao_plat_app.commit()
    assert len(unidades) >= 3, "grade pequena não gerou unidades suficientes para o teste"
    yield {"definicao": definicao, "modelo": modelo, "conjunto": conjunto, "execucao": execucao,
           "unidades": unidades}
    sessao_a.delete(f"/api/amc/execucoes/{execucao['id']}")
    sessao_a.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/amc/modelos/{modelo['id']}")


def _gravar_bruto(con, tenant_id, execucao_id, unidade_id, valores: dict):
    contexto(con, tenant_id)  # set_config é LOCAL à transação: repetir a cada commit (test_rls do repositório)
    with con.cursor() as cur:
        for fator, valor in valores.items():
            cur.execute(
                "INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, cobertura) "
                "VALUES (%s::uuid, %s, %s, %s, %s, 1.0)", (execucao_id, tenant_id, unidade_id, fator, valor))
    con.commit()


def _gravar_resultado(con, tenant_id, execucao_id, unidade_id, favorabilidade, cobertura, vetado=False, motivo=None):
    contexto(con, tenant_id)
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, vetado, motivo, "
            "cobertura) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
            (execucao_id, tenant_id, unidade_id, favorabilidade, vetado, motivo, cobertura))
    con.commit()


def test_explicacao_soma_das_contribuicoes_bate_a_gravada(cenario, sessao_a, conexao_plat_app, medida):
    """fatores do modelo de exemplo (tests/api/amc/exemplos.py): declividade (linear decrescente 0-30: valor 12
    -> favorabilidade 100*(1-12/30) = 60) e dist_via (degraus: valor 1000 cai na banda 'até 2000' -> nota 60).
    Os dois fatores dão favorabilidade 60 cada -> a soma ponderada normalizada também dá 60, qualquer que seja
    o peso relativo (3,0 e 1,5) -- por isso o valor gravado abaixo é exato, não aproximado."""
    execucao = cenario["execucao"]
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    unidade = cenario["unidades"][0]
    _gravar_bruto(conexao_plat_app, tenant_id, execucao["id"], unidade, {"declividade": 12.0, "dist_via": 1000.0})
    _gravar_resultado(conexao_plat_app, tenant_id, execucao["id"], unidade, favorabilidade=60.0, cobertura=1.0)

    r = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/unidades/{unidade}/explicacao")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["vetado"] is False
    assert corpo["favorabilidade_gravada"] == pytest.approx(60.0)
    assert corpo["favorabilidade_recalculada"] == pytest.approx(60.0, abs=0.5)
    assert corpo["delta"] <= 0.5
    soma = sum(f["contribuicao"] for f in corpo["fatores"] if f["contribuicao"] is not None)
    assert soma == pytest.approx(corpo["favorabilidade_recalculada"], abs=1e-6)
    for f in corpo["fatores"]:
        assert f["fonte"] and f["unidade_medida"]  # a tabela sempre traz proveniência, não só o número
    gravar = medida("L3-01-f-explicacao")
    gravar("delta_soma_vs_gravada_1_chamada_api", abs(soma - corpo["favorabilidade_gravada"]), "pontos",
          "GET .../explicacao sobre execução real da API; ver também os 100 pontos sintéticos em "
          "tests/unit/test_amc_explicacao.py::test_montar_explicacao_100_unidades_sorteadas_bate_combinacao_independente")


def test_explicacao_unidade_vetada_mostra_fator_e_motivo(cenario, sessao_a, conexao_plat_app, medida):
    execucao = cenario["execucao"]
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    unidade = cenario["unidades"][1]
    motivo = "unidade inteiramente coberta por restrição declarada no modelo (área alagável de teste)"
    _gravar_bruto(conexao_plat_app, tenant_id, execucao["id"], unidade, {"declividade": 5.0, "dist_via": 200.0})
    _gravar_resultado(conexao_plat_app, tenant_id, execucao["id"], unidade, favorabilidade=None, cobertura=1.0,
                      vetado=True, motivo=motivo)

    r = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/unidades/{unidade}/explicacao")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["vetado"] is True
    assert corpo["motivo_veto"] == motivo
    assert corpo["favorabilidade_gravada"] is None
    # a tabela de fatores continua presente: "mostra fator e motivo", não só o motivo isolado
    assert len(corpo["fatores"]) >= 2
    assert any(f["valor_bruto"] is not None for f in corpo["fatores"])
    gravar = medida("L3-01-f-explicacao")
    gravar("veto_mostra_fator_e_motivo", True, "bool",
          "GET .../explicacao de unidade vetada: motivo_veto presente e tabela de fatores não fica vazia")


def test_explicacao_sem_extracao_e_404_nao_numero_inventado(cenario, sessao_a):
    execucao = cenario["execucao"]
    r = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/unidades/unidade-sem-extracao/explicacao")
    assert r.status_code == 404, r.text


def test_explicacao_responde_em_ate_100ms(cenario, sessao_a, conexao_plat_app, medida):
    """Cláusula de desempenho do portão. Medida só com a máquina calma (brief comum 07/09); acima de carga 8,
    a cláusula fica 'não medida' com o motivo — não é reprovação do produto, é a casa ocupada."""
    execucao = cenario["execucao"]
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    unidade = cenario["unidades"][2]
    _gravar_bruto(conexao_plat_app, tenant_id, execucao["id"], unidade, {"declividade": 8.0, "dist_via": 500.0})
    _gravar_resultado(conexao_plat_app, tenant_id, execucao["id"], unidade, favorabilidade=70.0, cobertura=1.0)

    carga_1min = os.getloadavg()[0]
    tempos = []
    for _ in range(20):
        t0 = time.perf_counter()
        r = sessao_a.get(f"/api/amc/execucoes/{execucao['id']}/unidades/{unidade}/explicacao")
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    tempos.sort()
    mediana_ms = tempos[len(tempos) // 2]
    gravar = medida("L3-01-f-explicacao")
    if carga_1min > 8:
        gravar("latencia_p50_ms", None, "ms", f"não medida: carga_1min={carga_1min:.1f} acima de 8 (máquina ocupada)")
        pytest.skip(f"carga_1min={carga_1min:.1f} acima de 8: latência não medida, ver tests/medidas")
        return
    gravar("latencia_p50_ms", round(mediana_ms, 2), "ms",
          f"20 chamadas a /api/amc/execucoes/.../explicacao; carga_1min={carga_1min:.2f}")
    assert mediana_ms <= 100.0, (mediana_ms, tempos)
