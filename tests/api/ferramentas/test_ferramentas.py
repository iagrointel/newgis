"""Item L2-05-a: catálogo de ferramentas, validação de parâmetro, buffer pelo mesmo caminho por API própria, por
GPServer (execute e submitJob) e o formulário (que posta na API própria; o e2e prova a tela), proveniência com
sha256 recalculado por SQL independente, relação derivado_de, rerodar do histórico, cancelamento sem camada órfã,
camada de outro inquilino = 404, custo acima do teto = job / 400 no execute."""

import time

import pytest

from app import limites
from app.ferramentas import executor, registro
from app.jobs.registro import Cancelado
from tests.api.ferramentas import apoio
from tests.api.jobs.conftest import esperar

GP = "/rest/services/buffer/GPServer/buffer"


def _resultado(sessao, item_id: str) -> dict:
    r = sessao.get(f"/api/itens/{item_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_catalogo_lista_buffer_com_esquema_e_gpserver(sessao_a):
    r = sessao_a.get("/api/ferramentas")
    assert r.status_code == 200, r.text
    nomes = {f["nome"] for f in r.json()}
    assert "buffer" in nomes
    f = sessao_a.get("/api/ferramentas/buffer").json()
    assert f["esquema"]["properties"]["distancia"]["x-tipo-gp"] == "GPLinearUnit"
    assert f["esquema"]["required"] == ["camada"]
    assert f["gpserver"] == GP
    assert sessao_a.get("/api/ferramentas/nao_existe").status_code == 404


def test_parametro_fora_do_tipo_e_422_nomeando_o_campo(sessao_a, camada_a):
    casos = [
        ({"camada": camada_a["id"], "distancia": "abc"}, "distancia"),
        ({"camada": camada_a["id"], "distancia": {"distance": 10, "units": "esriParsecs"}}, "distancia"),
        ({"camada": camada_a["id"], "distancia": {"distance": 10 ** 9}}, "distancia"),
        ({"camada": "nao-e-uuid"}, "camada"),
        ({"camada": camada_a["id"], "dissolver": "talvez"}, "dissolver"),
        ({"camada": camada_a["id"], "raio": 5}, "raio"),
        ({}, "camada"),
    ]
    for corpo, campo in casos:
        r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": corpo})
        assert r.status_code == 422, (corpo, r.text)
        assert r.json()["erro"] == "parametros_invalidos" and r.json()["detalhe"][0]["campo"] == campo, r.text


def test_buffer_por_api_propria_gpserver_execute_e_submitjob_dao_o_mesmo_resultado(
    env, sessao_a, cliente, camada_a, token_gp, criados, worker_vivo,
):
    params = {"camada": camada_a["id"], "distancia": {"distance": 50, "units": "esriMeters"}}
    # 1. API própria (é onde o formulário do navegador posta): custo 5 <= teto → em processo
    r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": params, "titulo": "zt buffer api"})
    assert r.status_code == 200, r.text
    api_ = r.json()
    criados["demo"].append(api_["item_id"])
    assert api_["sincrono"] is True and api_["feicoes"] == 5 and api_["custo"] == 5
    # 2. GPServer execute (síncrono), token por querystring, parâmetros como texto/JSON no form
    r = cliente.post(f"{GP}/execute", params={"f": "json", "token": token_gp},
                     data={"camada": camada_a["id"], "distancia": '{"distance": 50, "units": "esriMeters"}'})
    assert r.status_code == 200, r.text
    gp_exec = r.json()["results"][0]
    assert gp_exec["paramName"] == "saida" and gp_exec["dataType"] == "GPFeatureRecordSetLayer"
    criados["demo"].append(gp_exec["value"]["itemId"])
    assert gp_exec["value"]["featureCount"] == 5
    # 3. GPServer submitJob → worker → jobs/{id} → results/saida
    r = cliente.post(f"{GP}/submitJob", params={"f": "json", "token": token_gp},
                     data={"camada": camada_a["id"], "distancia": '{"distance": 50, "units": "esriMeters"}'})
    assert r.status_code == 200, r.text
    job_id = r.json()["jobId"]
    assert r.json()["jobStatus"] == "esriJobSubmitted"
    job = esperar(sessao_a, job_id, timeout=90)
    assert job["estado"] == "concluido", job
    criados["demo"].append(job["resultado"]["item_id"])
    st = cliente.get(f"{GP}/jobs/{job_id}", params={"f": "json", "token": token_gp}).json()
    assert st["jobStatus"] == "esriJobSucceeded" and st["results"]["saida"]["paramUrl"] == "results/saida"
    res = cliente.get(f"{GP}/jobs/{job_id}/results/saida", params={"f": "json", "token": token_gp}).json()
    assert res["value"]["itemId"] == job["resultado"]["item_id"] and res["value"]["featureCount"] == 5
    assert job["proveniencia"]["entradas"][0]["item_id"] == camada_a["id"]

    # o mesmo resultado pelos três caminhos: contagem e sha256 de conteúdo iguais
    shas = {api_["sha256"], _resultado(sessao_a, gp_exec["value"]["itemId"])["dados"]["procedencia"]["sha256"],
            job["resultado"]["sha256"]}
    assert len(shas) == 1, shas

    # proveniência gravada e conferível: sha256 da entrada recalculado por SQL independente
    item = _resultado(sessao_a, api_["item_id"])
    prov = item["dados"]["procedencia"]["ferramenta"]
    assert prov["ferramenta"] == "buffer" and prov["versao"] == 1
    assert prov["parametros"]["distancia"]["metros"] == 50.0
    assert prov["autor"]["login"] == "admin" and prov["executada_em"]
    entrada = prov["entradas"][0]
    assert entrada["item_id"] == camada_a["id"] and entrada["versao"] >= 0
    assert entrada["sha256"] == apoio.sha256_independente(env, "demo", camada_a["schema"], camada_a["tabela"],
                                                          ["nome", "valor"])
    assert item["dados"]["procedencia"]["sha256"] == apoio.sha256_independente(
        env, "demo", item["dados"]["schema"], item["dados"]["tabela"], ["nome", "valor"])
    assert item["dados"]["geometria"] == "MultiPolygon" and item["extent"]
    # relação derivado_de: resultado → entrada
    rel = sessao_a.get(f"/api/itens/{api_['item_id']}/criado-a-partir-de").json()
    assert any(x["id"] == camada_a["id"] and x["tipo_relacao"] == "derivado_de" for x in rel), rel
    usado = sessao_a.get(f"/api/itens/{camada_a['id']}/usado-por").json()
    assert any(x["id"] == api_["item_id"] for x in usado), usado


def test_rerodar_do_historico_reproduz_contagem_e_sha256(sessao_a, camada_a, criados, worker_vivo):
    params = {"camada": camada_a["id"], "distancia": {"distance": 120, "units": "esriMeters"}, "dissolver": True}
    r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": params, "modo": "job"})
    assert r.status_code == 202, r.text
    job1 = esperar(sessao_a, r.json()["job_id"], timeout=90)
    assert job1["estado"] == "concluido", job1
    criados["demo"].append(job1["resultado"]["item_id"])
    historico = sessao_a.get("/api/jobs", params={"tipo": "ferramentas.executar", "limite": 50}).json()["itens"]
    assert any(j["id"] == job1["id"] for j in historico)
    r = sessao_a.post(f"/api/jobs/{job1['id']}/repetir")
    assert r.status_code == 201, r.text
    job2 = esperar(sessao_a, r.json()["id"], timeout=90)
    assert job2["estado"] == "concluido", job2
    criados["demo"].append(job2["resultado"]["item_id"])
    assert job2["parametros"] == job1["parametros"]
    assert job2["resultado"]["feicoes"] == job1["resultado"]["feicoes"] == 1
    assert job2["resultado"]["sha256"] == job1["resultado"]["sha256"]
    assert job2["resultado"]["item_id"] != job1["resultado"]["item_id"]


def test_camada_de_outro_inquilino_e_404_na_api_e_no_gpserver(sessao_a, cliente, camada_b, token_gp):
    r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": {"camada": camada_b["id"]}})
    assert r.status_code == 404 and r.json()["erro"] == "camada_inexistente", r.text
    r = cliente.post(f"{GP}/submitJob", params={"f": "json", "token": token_gp}, data={"camada": camada_b["id"]})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == 404 and "camada" in r.json()["error"]["message"]


def test_cancelamento_apos_criar_a_tabela_nao_deixa_camada_orfa(env, sessao_a, camada_a, monkeypatch):
    """Roda o executor em processo com um contexto que pede cancelamento no primeiro progresso DEPOIS de a
    tabela de saída existir; nem tabela nem item sobram."""
    from app import db
    from tests import jobs_sessao
    from tests.api.test_rls import ids_por_slug

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        tid = ids_por_slug(con)["demo"]
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
    finally:
        con.close()
    destinos = {}

    class Cancelador(executor.ContextoSincrono):
        def progresso(self, pct, mensagem=""):
            if pct >= 70:
                raise Cancelado("cancelamento de teste")

    ctx = Cancelador(db.Contexto(tid, adm, "admin"))
    original = executor.uuid.uuid4

    def uuid_espiao():
        u = original()
        destinos["item_id"] = str(u)
        return u

    monkeypatch.setattr(executor.uuid, "uuid4", uuid_espiao)
    f = registro.obter("buffer")
    params = registro.validar_parametros(f, {"camada": camada_a["id"]})
    with pytest.raises(Cancelado):
        executor.executar(ctx, f, params)
    tabela = "c_" + destinos["item_id"].replace("-", "")[:16]
    assert not apoio.tabela_existe(env, camada_a["schema"], tabela)
    assert sessao_a.get(f"/api/itens/{destinos['item_id']}").status_code == 404


def test_custo_acima_do_teto_vira_job_e_execute_recusa_com_erro_esri(sessao_a, cliente, camada_a, token_gp,
                                                                     monkeypatch, criados, worker_vivo):
    monkeypatch.setattr(limites, "FERRAMENTA_SINCRONO_CUSTO_MAX", 0)
    r = cliente.post(f"{GP}/execute", params={"f": "json", "token": token_gp}, data={"camada": camada_a["id"]})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == 400 and "submitJob" in r.json()["error"]["message"]
    r = sessao_a.post("/api/ferramentas/buffer/executar", json={"parametros": {"camada": camada_a["id"]}})
    assert r.status_code == 202 and r.json()["sincrono"] is False, r.text
    job = esperar(sessao_a, r.json()["job_id"], timeout=90)
    assert job["estado"] == "concluido", job
    criados["demo"].append(job["resultado"]["item_id"])


def test_gpserver_descritores_publicos_token_obrigatorio_e_cancel(sessao_a, cliente, camada_a, token_gp):
    r = cliente.get("/rest/services/buffer/GPServer", params={"f": "json"})
    assert r.status_code == 200 and r.json()["tasks"] == ["buffer"], r.text
    t = cliente.get(GP, params={"f": "json"}).json()
    nomes = {p["name"]: p for p in t["parameters"]}
    assert nomes["camada"]["dataType"] == "GPFeatureRecordSetLayer"
    assert nomes["saida"]["direction"] == "esriGPParameterDirectionOutput"
    assert nomes["distancia"]["defaultValue"] == {"distance": 100, "units": "esriMeters"}
    assert cliente.get("/rest/services/nao_existe/GPServer").status_code == 404
    r = cliente.post(f"{GP}/execute", data={"camada": camada_a["id"]})
    assert r.status_code == 401 and r.json()["error"]["code"] == 401, r.text
    # cancel de job inexistente = 404 no formato Esri; cancel de job pendente agendado para o futuro = esriJobCancelled
    r = cliente.post(f"{GP}/jobs/00000000-0000-0000-0000-000000000000/cancel", params={"token": token_gp})
    assert r.status_code == 404, r.text
    r = sessao_a.post("/api/jobs", json={
        "tipo": "ferramentas.executar", "agendado_para": "2099-01-01T00:00:00Z",
        "parametros": {"ferramenta": "buffer", "parametros": {"camada": camada_a["id"]}}})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    r = cliente.post(f"{GP}/jobs/{job_id}/cancel", params={"f": "json", "token": token_gp})
    assert r.status_code == 200, r.text
    fim = time.monotonic() + 10
    while r.json()["jobStatus"] != "esriJobCancelled" and time.monotonic() < fim:
        time.sleep(0.3)
        r = cliente.get(f"{GP}/jobs/{job_id}", params={"f": "json", "token": token_gp})
    assert r.json()["jobStatus"] == "esriJobCancelled", r.text
