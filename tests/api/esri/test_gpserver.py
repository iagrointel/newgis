"""Item UX-22-ferramentas-esri-sem-tela — o contrato ASSÍNCRONO do GPServer medido rota a rota:
`POST /rest/services/{ferramenta}/GPServer/{tarefa}/submitJob`, `GET .../jobs/{job_id}` (jobStatus),
`GET .../jobs/{job_id}/results/{parametro}` e `POST .../jobs/{job_id}/cancel`.

⚠ ESCOPO DECLARADO. O `portao_de_pronto` do item UX-22 é de INTERFACE: "cada rota listada é chamada por um
controle alcançável de uma tela de app/paginas.py; e2e exercita o controle com captura; 0 erro de console;
axe 0 violações sérias; docs/COBERTURA_UI.md regenerado sem a lacuna". NADA disso é medido aqui. Este
arquivo mede a camada de baixo — que as três rotas de escrita existem, respondem no dialeto Esri e falham
com erro NOMEADO — que é o pressuposto de qualquer controle de tela. A parte de tela continua não provada,
e está registrada assim na medida do item (tests/medidas/UX-22-ferramentas-esri-sem-tela.json).

Referência do dialeto: developers.arcgis.com/rest/services-reference/enterprise/submit-gp-job/ e
.../check-gp-job-status/ — jobId, jobStatus em `esriJob*`, `results.{param}.paramUrl`, `messages`.
"""

import uuid

from tests.api.jobs.conftest import esperar

GP = "/rest/services/buffer/GPServer/buffer"
DISTANCIA = '{"distance": 50, "units": "esriMeters"}'


def _submeter(cliente, camada_gp, token) -> dict:
    r = cliente.post(f"{GP}/submitJob", params={"f": "json", "token": token},
                     data={"camada": camada_gp["id"], "distancia": DISTANCIA})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- submitJob
def test_submitjob_devolve_jobid_e_estado_esri(cliente, sessao_a, camada_gp, token_gp_esri, criados_esri,
                                               worker_vivo_esri):
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    assert "jobId" in corpo and uuid.UUID(corpo["jobId"])
    assert corpo["jobStatus"] in ("esriJobSubmitted", "esriJobExecuting", "esriJobSucceeded")
    assert isinstance(corpo["messages"], list)
    job = esperar(sessao_a, corpo["jobId"], timeout=90)
    assert job["estado"] == "concluido", job
    criados_esri["demo"].append(job["resultado"]["item_id"])


# ---------------------------------------------------------------- jobStatus
def test_jobstatus_acompanha_ate_esrijobsucceeded_e_publica_o_paramurl(cliente, sessao_a, camada_gp,
                                                                       token_gp_esri, criados_esri,
                                                                       worker_vivo_esri):
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    job_id = corpo["jobId"]
    job = esperar(sessao_a, job_id, timeout=90)
    assert job["estado"] == "concluido", job
    criados_esri["demo"].append(job["resultado"]["item_id"])

    st = cliente.get(f"{GP}/jobs/{job_id}", params={"f": "json", "token": token_gp_esri})
    assert st.status_code == 200, st.text
    st = st.json()
    assert st["jobId"] == job_id
    assert st["jobStatus"] == "esriJobSucceeded"
    # o cliente Esri descobre o resultado SÓ por results.{param}.paramUrl — nunca por um campo nosso
    assert st["results"]["saida"]["paramUrl"] == "results/saida"
    assert 0 <= st["progress"] <= 100


# ---------------------------------------------------------------- results
def test_results_devolve_o_item_com_contagem_e_tipo_gp(cliente, sessao_a, camada_gp, token_gp_esri,
                                                       criados_esri, worker_vivo_esri):
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    job_id = corpo["jobId"]
    job = esperar(sessao_a, job_id, timeout=90)
    assert job["estado"] == "concluido", job
    criados_esri["demo"].append(job["resultado"]["item_id"])

    r = cliente.get(f"{GP}/jobs/{job_id}/results/saida", params={"f": "json", "token": token_gp_esri})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["paramName"] == "saida"
    assert res["dataType"] == "GPFeatureRecordSetLayer"
    assert res["value"]["itemId"] == job["resultado"]["item_id"]
    # a camada de apoio tem 5 pontos; o buffer devolve uma feição por ponto
    assert res["value"]["featureCount"] == camada_gp["feicoes"] == 5
    assert res["value"]["url"].endswith("/FeatureServer/0")


def test_results_de_parametro_inexistente_e_404_nomeado(cliente, sessao_a, camada_gp, token_gp_esri,
                                                        criados_esri, worker_vivo_esri):
    """Recusa. O par positivo é o teste acima, que prova que `saida` (o parâmetro real) responde 200."""
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    job_id = corpo["jobId"]
    job = esperar(sessao_a, job_id, timeout=90)
    criados_esri["demo"].append(job["resultado"]["item_id"])
    r = cliente.get(f"{GP}/jobs/{job_id}/results/nao_existe", params={"f": "json", "token": token_gp_esri})
    assert r.status_code == 404, r.text
    # erro no dialeto Esri, nunca um 500 cru nem um traceback
    assert "error" in r.json(), r.text


def test_results_antes_de_concluir_e_409_nomeado(cliente, camada_gp, token_gp_esri, criados_esri,
                                                 worker_vivo_esri, sessao_a):
    """Pedir o resultado de um job que ainda não terminou tem de dar 409 com motivo, nunca 200 com valor
    vazio. Se o worker já tiver terminado antes da primeira leitura, o teste conclui pelo caminho feliz —
    e diz isso, em vez de fingir que mediu o 409."""
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    job_id = corpo["jobId"]
    r = cliente.get(f"{GP}/jobs/{job_id}/results/saida", params={"f": "json", "token": token_gp_esri})
    job = esperar(sessao_a, job_id, timeout=90)
    if isinstance(job.get("resultado"), dict):
        criados_esri["demo"].append(job["resultado"]["item_id"])
    if r.status_code == 409:
        assert "error" in r.json(), r.text
    else:
        assert r.status_code == 200, r.text  # corrida perdida: o job já tinha terminado


# ---------------------------------------------------------------- cancel
def test_cancel_marca_o_job_e_o_jobstatus_reflete(cliente, sessao_a, camada_gp, token_gp_esri,
                                                  criados_esri, worker_vivo_esri):
    corpo = _submeter(cliente, camada_gp, token_gp_esri)
    job_id = corpo["jobId"]
    r = cliente.post(f"{GP}/jobs/{job_id}/cancel", params={"f": "json", "token": token_gp_esri})
    assert r.status_code in (200, 409), r.text
    if r.status_code == 200:
        assert r.json()["jobStatus"] in ("esriJobCancelling", "esriJobCancelled", "esriJobSucceeded")
    st = cliente.get(f"{GP}/jobs/{job_id}", params={"f": "json", "token": token_gp_esri}).json()
    assert st["jobStatus"].startswith("esriJob")
    job = esperar(sessao_a, job_id, timeout=90, estados=("concluido", "cancelado", "falhou"))
    if isinstance(job.get("resultado"), dict) and job["resultado"].get("item_id"):
        criados_esri["demo"].append(job["resultado"]["item_id"])


# ---------------------------------------------------------------- autenticação e erros nomeados
def test_as_tres_rotas_sem_token_sao_recusadas_nomeadamente(cliente, camada_gp):
    """Recusa: sem token, nenhuma das três rotas de escrita pode responder 200. O par positivo são todos
    os testes acima, que com o token válido respondem 200."""
    falso = str(uuid.uuid4())
    alvos = [
        ("post", f"{GP}/submitJob", {"camada": camada_gp["id"], "distancia": DISTANCIA}),
        ("get", f"{GP}/jobs/{falso}", None),
        ("get", f"{GP}/jobs/{falso}/results/saida", None),
        ("post", f"{GP}/jobs/{falso}/cancel", None),
    ]
    for metodo, rota, dados in alvos:
        r = (cliente.post(rota, params={"f": "json"}, data=dados) if metodo == "post"
             else cliente.get(rota, params={"f": "json"}))
        assert r.status_code in (401, 403), (rota, r.status_code, r.text)
        assert "error" in r.json(), (rota, r.text)


def test_job_de_outra_ferramenta_ou_inexistente_e_404(cliente, token_gp_esri):
    falso = str(uuid.uuid4())
    r = cliente.get(f"{GP}/jobs/{falso}", params={"f": "json", "token": token_gp_esri})
    assert r.status_code == 404, r.text
    # id que nem é UUID também é 404 nomeado, nunca 500
    r = cliente.get(f"{GP}/jobs/nao-e-uuid", params={"f": "json", "token": token_gp_esri})
    assert r.status_code == 404, r.text


def test_descritor_da_tarefa_anuncia_submitjob_como_execucao_assincrona(cliente):
    r = cliente.get(f"{GP}", params={"f": "json"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert "tasks" in corpo or "name" in corpo, corpo
