"""GPServer compatível (item L2-05-a; referência: developers.arcgis.com/rest/services-reference/enterprise/
gp-service, gp-task, execute-gp-task, submit-gp-job, gp-job, gp-result, cancel-gp-job — 07/09/2026), uma
instância por ferramenta em `/rest/services/<ferramenta>/GPServer/<ferramenta>`, para ArcGIS Pro e apps JS
chamarem as nossas ferramentas como se fossem serviços de geoprocessamento publicados.
  feito    - descritor do serviço e da tarefa (?f=json), execute (síncrono; 400 quando o custo passa do teto
             declarado), submitJob, jobs/{id} (esriJobSubmitted/Executing/Succeeded/Failed/Cancelled), results/{param},
             cancel; `token=` por querystring/form (mesmo padrão do GeocodeServer); erro com o código HTTP real e
             corpo `{error:{code,message,details}}` (L2_CONCEITO C9).
  parcial  - GPFeatureRecordSetLayer de entrada só por referência (uuid do item ou URL de FeatureServer desta
             instalação); FeatureSet inline não é aceito (a camada temporária depende do L2-01-k).
  fora     - jobs/{id}/inputs, messages detalhados por passo, uploads, Pro real (D20)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import limites
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.erros import ErroAPI
from app.ferramentas import registro
from app.ferramentas.rotas import PRIVILEGIO, enfileirar, erro_api, executar_sincrono, ferramenta_ou_404, preparar
from app.jobs import servico
from app.jobs.contexto import ErroServico, sessao_de

router = APIRouter(tags=["ferramentas-esri"])
SERVICO = "/rest/services/{ferramenta}/GPServer"
TAREFA = SERVICO + "/{tarefa}"
JOB = TAREFA + "/jobs/{job_id}"
CURRENT_VERSION = 11.3  # mesma versão declarada no GeocodeServer (app/geocodificador/rotas_esri.py)
ESTADO_GP = {"pendente": "esriJobSubmitted", "rodando": "esriJobExecuting", "concluido": "esriJobSucceeded",
             "falhou": "esriJobFailed", "cancelado": "esriJobCancelled"}
PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}
X = {"x-auth": "S/T", "x-privilegio": PRIVILEGIO}


def _erro_esri(request: Request, e: ErroAPI) -> JSONResponse:
    detalhes = e.detalhe if isinstance(e.detalhe, list) else ([e.detalhe] if e.detalhe else [])
    return JSONResponse({"error": {"code": e.status_code, "message": e.mensagem,
                                   "details": [str(d) for d in detalhes], "erro": e.erro,
                                   "req_id": getattr(request.state, "req_id", None)}},
                        status_code=e.status_code, headers={"Cache-Control": "no-store"})


def _json(dados) -> JSONResponse:
    return JSONResponse(dados, headers={"Cache-Control": "no-store"})


def _autenticar(request: Request):
    """Sessão/cabeçalho Authorization normal OU `?token=`/form `token=` (protocolo Esri); privilégio
    analise.executar no dono."""
    try:
        auth = auth_sessao.resolver(request)
    except ErroAPI:
        auth = None
    if auth is None:
        tok = request.query_params.get("token") or getattr(request.state, "form_token", None)
        if not tok:
            raise ErroAPI(401, "token_requerido", "informe token=<token de serviço plat> (protocolo Esri) ou "
                           "o cabeçalho Authorization: Bearer")
        auth = auth_sessao._auth_de_token(request, tok)  # noqa: SLF001 — reuso deliberado (GeocodeServer faz igual)
        request.state.auth = auth
    if auth.modo == "token":
        esc.exigir_escopo(auth, "jobs:executar")
    if not auth.tem(PRIVILEGIO):
        raise ErroAPI(403, "sem_privilegio", f"a operação exige o privilégio {PRIVILEGIO}", {"exigido": PRIVILEGIO})
    return auth


async def _parametros(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in ct:
            corpo = await request.json()
            if isinstance(corpo, dict):
                p.update(corpo)
    if "token" in p:
        request.state.form_token = p["token"]
    return p


def _tarefa(ferramenta: str, tarefa: str) -> registro.Ferramenta:
    f = ferramenta_ou_404(ferramenta)
    if tarefa != f.nome:
        raise ErroAPI(404, "tarefa_inexistente", f"tarefa inexistente: {tarefa}")
    return f


def _resultado(f: registro.Ferramenta, item_id: str, feicoes: int | None) -> dict:
    saida = f.saidas[0]
    return {"paramName": saida.nome, "dataType": saida.tipo_gp,
            "value": {"url": f"/rest/services/{item_id}/FeatureServer/0", "itemId": item_id, "featureCount": feicoes}}


def _mensagens(job: dict) -> list[dict]:
    m = []
    if job.get("mensagem"):
        m.append({"type": "esriJobMessageTypeInformative", "description": job["mensagem"]})
    if job.get("erro"):
        m.append({"type": "esriJobMessageTypeError", "description": job["erro"]})
    return m


def _job_gp(f: registro.Ferramenta, job: dict) -> dict:
    estado = ESTADO_GP.get(job["estado"], "esriJobSubmitted")
    if job.get("cancelar_solicitado") and job["estado"] in ("pendente", "rodando"):
        estado = "esriJobCancelling"
    corpo = {"jobId": job["id"], "jobStatus": estado, "messages": _mensagens(job), "progress": job.get("progresso", 0)}
    if estado == "esriJobSucceeded" and isinstance(job.get("resultado"), dict):
        corpo["results"] = {f.saidas[0].nome: {"paramUrl": f"results/{f.saidas[0].nome}"}}
    return corpo


def _job_da_ferramenta(auth, f: registro.Ferramenta, job_id: str) -> dict:
    try:
        uuid.UUID(job_id)
    except ValueError as e:
        raise ErroAPI(404, "job_inexistente", "job não encontrado") from e
    try:
        job = servico.obter(sessao_de(auth), job_id)
    except ErroServico as e:
        raise ErroAPI(e.status_code, e.erro, e.mensagem) from e
    if job["tipo"] != "ferramentas.executar" or (job.get("parametros") or {}).get("ferramenta") != f.nome:
        raise ErroAPI(404, "job_inexistente", "job não encontrado")
    return job


# ---------------------------------------------------------------- descritores (metadado, sem autenticação)
@router.get(SERVICO, openapi_extra=PUBLICO, operation_id="gpserver_servico")
def descritor_servico(ferramenta: str, request: Request):
    try:
        f = ferramenta_ou_404(ferramenta)
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json({"currentVersion": CURRENT_VERSION, "serviceDescription": f.descricao, "tasks": [f.nome],
                  "executionType": "esriExecutionTypeAsynchronous", "resultMapServerName": "",
                  "maximumRecords": limites.PAGINA_MAX, "capabilities": "Execute,SubmitJob"})


@router.get(TAREFA, openapi_extra=PUBLICO, operation_id="gpserver_tarefa")
def descritor_tarefa(ferramenta: str, tarefa: str, request: Request):
    try:
        f = _tarefa(ferramenta, tarefa)
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json(registro.descrever_gp(f))


# ---------------------------------------------------------------- execução
async def _entrada(request: Request, ferramenta: str, tarefa: str):
    p = await _parametros(request)
    f = _tarefa(ferramenta, tarefa)
    auth = _autenticar(request)
    try:
        crus = registro.parametros_de_formulario_gp(f, p)
    except registro.ErroParametro as e:
        raise erro_api(e) from e
    normalizados, _entradas, custo = preparar(auth, f, crus)
    return auth, f, normalizados, custo


@router.get(f"{TAREFA}/execute", openapi_extra=X, operation_id="gpserver_execute_get")
@router.post(f"{TAREFA}/execute", openapi_extra=X, operation_id="gpserver_execute_post")
async def execute(ferramenta: str, tarefa: str, request: Request):
    """Execução síncrona (execute-gp-task): só abaixo do custo declarado; acima, 400 mandando usar submitJob."""
    try:
        auth, f, normalizados, custo = await _entrada(request, ferramenta, tarefa)
        if custo > limites.FERRAMENTA_SINCRONO_CUSTO_MAX:
            raise ErroAPI(400, "custo_acima_do_sincrono",
                          f"custo estimado {custo} acima do teto síncrono {limites.FERRAMENTA_SINCRONO_CUSTO_MAX}; "
                          "use submitJob")
        r = executar_sincrono(request, auth, f, normalizados, None)
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json({"results": [_resultado(f, r["item_id"], r["feicoes"])], "messages": []})


@router.get(f"{TAREFA}/submitJob", openapi_extra=X, operation_id="gpserver_submit_get")
@router.post(f"{TAREFA}/submitJob", openapi_extra=X, operation_id="gpserver_submit_post")
async def submit_job(ferramenta: str, tarefa: str, request: Request):
    try:
        auth, f, normalizados, _custo = await _entrada(request, ferramenta, tarefa)
        job = enfileirar(request, auth, f, normalizados, None)
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json(_job_gp(f, job))


@router.get(JOB, openapi_extra=X, operation_id="gpserver_job")
def job_status(ferramenta: str, tarefa: str, job_id: str, request: Request):
    try:
        f = _tarefa(ferramenta, tarefa)
        auth = _autenticar(request)
        job = _job_da_ferramenta(auth, f, job_id)
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json(_job_gp(f, job))


@router.get(f"{JOB}/results/{{parametro}}", openapi_extra=X, operation_id="gpserver_job_resultado")
def job_resultado(ferramenta: str, tarefa: str, job_id: str, parametro: str, request: Request):
    try:
        f = _tarefa(ferramenta, tarefa)
        auth = _autenticar(request)
        job = _job_da_ferramenta(auth, f, job_id)
        if parametro != f.saidas[0].nome:
            raise ErroAPI(404, "parametro_inexistente", f"parâmetro de saída inexistente: {parametro}")
        if job["estado"] != "concluido" or not isinstance(job.get("resultado"), dict):
            raise ErroAPI(409, "job_nao_concluido", f"job em estado {job['estado']}; sem resultado ainda")
    except ErroAPI as e:
        return _erro_esri(request, e)
    r = job["resultado"]
    return _json(_resultado(f, r["item_id"], r.get("feicoes")))


@router.get(f"{JOB}/cancel", openapi_extra=X, operation_id="gpserver_cancel_get")
@router.post(f"{JOB}/cancel", openapi_extra=X, operation_id="gpserver_cancel_post")
async def job_cancel(ferramenta: str, tarefa: str, job_id: str, request: Request):
    try:
        await _parametros(request)
        f = _tarefa(ferramenta, tarefa)
        auth = _autenticar(request)
        _job_da_ferramenta(auth, f, job_id)
        try:
            job = servico.cancelar(sessao_de(auth), job_id)
        except ErroServico as e:
            raise ErroAPI(e.status_code, e.erro, e.mensagem) from e
        from app import db
        from app.auth.comum import registrar_evento

        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "jobs/cancelar", "job", job_id, {"origem": "gpserver"})
    except ErroAPI as e:
        return _erro_esri(request, e)
    return _json(_job_gp(f, job))
