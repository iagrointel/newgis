"""Rotas /api/jobs, /api/agendas e as páginas /tarefas (ADR 0003 seção 9). Toda rota exige o privilégio
`jobs.executar` pela dependência da trilha A (`app.auth.sessao.autenticado`: cookie ou token, CSRF sob cookie,
pendências); erros no formato D18 pelo tratador global de `app.erros`. Modelos pydantic de resposta em toda rota."""

import uuid
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import paginas
from app.auth.sessao import Auth
from app.jobs import eventos, servico
from app.jobs.contexto import ErroServico, dependencia_jobs, sessao_de

router = APIRouter()
AUTH = dependencia_jobs()  # singleton de módulo: cookie ou token com privilégio jobs.executar


# ---------------------------------------------------------------- modelos de resposta
class Erro(BaseModel):
    erro: str
    mensagem: str
    detalhe: Any | None = None
    req_id: str | None = None


class Job(BaseModel):
    id: uuid.UUID
    tipo: str
    estado: str
    progresso: int
    mensagem: str | None = None
    prioridade: int
    pesado: bool
    executor: str
    usuario_id: int | None = None
    usuario_login: str | None = None
    criado_em: str
    agendado_para: str | None = None
    iniciado_em: str | None = None
    heartbeat_em: str | None = None
    terminado_em: str | None = None
    duracao_s: float | None = None
    tentativa: int
    max_tentativas: int
    reinicios: int
    cancelar_solicitado: bool
    cancelado_por: int | None = None
    cancelado_em: str | None = None
    worker: str | None = None
    chave: str | None = None
    agenda_id: uuid.UUID | None = None
    programado_para: str | None = None
    resultado: Any | None = None
    erro: str | None = None
    linhas_log: int
    parametros: dict
    proveniencia: Any | None = None
    memoria_mb: int
    timeout_s: int


class ListaJobs(BaseModel):
    itens: list[Job]
    total: int
    limite: int
    deslocamento: int


class Resumo(BaseModel):
    pendente: int
    rodando: int
    concluido_24h: int
    falhou_24h: int
    cancelado_24h: int


class TipoJob(BaseModel):
    nome: str
    descricao: str
    pesado: bool
    memoria_mb: int
    timeout_s: int
    tentativas: int
    executor: str
    versao: int
    perfil_minimo: str
    parametros_schema: dict


class LinhaLog(BaseModel):
    id: int
    em: str
    nivel: str
    mensagem: str


class Log(BaseModel):
    linhas: list[LinhaLog]
    total: int


class Agenda(BaseModel):
    id: uuid.UUID
    nome: str
    tipo: str
    parametros: dict
    cron: str
    fuso: str
    ativa: bool
    proxima_em: str | None = None
    ultima_em: str | None = None
    ultimo_job_id: uuid.UUID | None = None
    ultimo_estado: str | None = None
    falhas_seguidas: int
    expira_em: str | None = None
    criado_em: str
    usuario_id: int | None = None
    usuario_login: str | None = None


class ListaAgendas(BaseModel):
    itens: list[Agenda]
    total: int


class NovoJob(BaseModel):
    tipo: str = Field(..., examples=["prova.progresso"])
    parametros: dict = Field(default_factory=dict)
    prioridade: int = Field(5, ge=1, le=9)
    agendado_para: str | None = None


class NovaAgenda(BaseModel):
    nome: str
    tipo: str
    parametros: dict = Field(default_factory=dict)
    cron: str = Field(..., examples=["30 3 * * *"])
    fuso: str = "America/Sao_Paulo"
    expira_em: str | None = None


ERROS = {401: {"model": Erro}, 403: {"model": Erro}, 404: {"model": Erro}, 409: {"model": Erro}, 413: {"model": Erro},
         422: {"model": Erro}, 429: {"model": Erro}}



def _sem_cache(dados, status: int = 200) -> JSONResponse:
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- jobs
@router.get("/api/jobs", response_model=ListaJobs, responses=ERROS, tags=["jobs"])
def listar_jobs(request: Request, auth: Auth = AUTH, estado: str | None = None, tipo: str | None = None,
                usuario_id: int | None = None,
                de: str | None = None, ate: str | None = None, agenda_id: str | None = None,
                limite: int = Query(50, ge=1, le=200), deslocamento: int = Query(0, ge=0),
                ordenar: str = "criado_em:desc"):
    s = sessao_de(auth)
    return _sem_cache(servico.listar(s, estado, tipo, usuario_id, de, ate, agenda_id, limite, deslocamento, ordenar))


@router.post("/api/jobs", response_model=Job, status_code=201, responses=ERROS, tags=["jobs"])
def criar_job(request: Request, corpo: dict = Body(...), auth: Auth = AUTH):  # noqa: B008
    s = sessao_de(auth)
    if not isinstance(corpo, dict) or not isinstance(corpo.get("tipo"), str):
        raise ErroServico(422, "corpo_invalido", "corpo deve ser {tipo, parametros?, prioridade?, agendado_para?}")
    job = servico.criar(s, corpo["tipo"], corpo.get("parametros"), corpo.get("prioridade", 5),
                        corpo.get("agendado_para"))
    return _sem_cache(job, 201)


@router.get("/api/jobs/resumo", response_model=Resumo, responses=ERROS, tags=["jobs"])
def resumo_jobs(request: Request, auth: Auth = AUTH):
    return _sem_cache(servico.resumo(sessao_de(auth)))


@router.get("/api/jobs/tipos", response_model=list[TipoJob], responses=ERROS, tags=["jobs"])
def tipos_de_job(request: Request, auth: Auth = AUTH):
    return _sem_cache(servico.tipos())


@router.get("/api/jobs/{job_id}", response_model=Job, responses=ERROS, tags=["jobs"])
def obter_job(request: Request, job_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.obter(sessao_de(auth), job_id))


@router.post("/api/jobs/{job_id}/cancelar", response_model=Job, status_code=202, responses=ERROS, tags=["jobs"])
def cancelar_job(request: Request, job_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.cancelar(sessao_de(auth), job_id), 202)


@router.post("/api/jobs/{job_id}/repetir", response_model=Job, status_code=201, responses=ERROS, tags=["jobs"])
def repetir_job(request: Request, job_id: uuid.UUID, corpo: dict | None = Body(None),  # noqa: B008
                auth: Auth = AUTH):
    extra = (corpo or {}).get("parametros") if isinstance(corpo, dict) else None
    return _sem_cache(servico.repetir(sessao_de(auth), job_id, extra), 201)


@router.get("/api/jobs/{job_id}/log", response_model=Log, responses=ERROS, tags=["jobs"])
def log_do_job(request: Request, job_id: uuid.UUID, apos: int = Query(0, ge=0), nivel: str | None = None,
               limite: int = Query(500, ge=1, le=2000), auth: Auth = AUTH):
    return _sem_cache(servico.log(sessao_de(auth), job_id, apos, nivel, limite))


@router.get("/api/jobs/{job_id}/eventos", responses={**ERROS, 200: {"content": {"text/event-stream": {}}}},
            tags=["jobs"])
async def eventos_do_job(request: Request, job_id: uuid.UUID, auth: Auth = AUTH):
    """SSE: primeiro evento `estado`, depois `log`/`estado`, `fim` no estado final; Last-Event-ID reenvia o log."""
    s = sessao_de(auth)
    job = await run_in_threadpool(servico.obter, s, job_id)
    eventos.reservar(s)
    ultimo = request.headers.get("Last-Event-ID")
    ultimo_id = int(ultimo) if ultimo and ultimo.isdigit() else None
    return StreamingResponse(
        eventos.gerar(s, job, ultimo_id), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------- agendas
@router.get("/api/agendas", response_model=ListaAgendas, responses=ERROS, tags=["agendas"])
def listar_agendas(request: Request, ativa: bool | None = None, tipo: str | None = None,
                   limite: int = Query(50, ge=1, le=200), deslocamento: int = Query(0, ge=0),
                   auth: Auth = AUTH):
    return _sem_cache(servico.agendas_listar(sessao_de(auth), ativa, tipo, limite, deslocamento))


@router.post("/api/agendas", response_model=Agenda, status_code=201, responses=ERROS, tags=["agendas"])
def criar_agenda(request: Request, corpo: dict = Body(...), auth: Auth = AUTH):  # noqa: B008
    if not isinstance(corpo, dict):
        raise ErroServico(422, "corpo_invalido", "corpo deve ser {nome, tipo, parametros?, cron, fuso?, expira_em?}")
    return _sem_cache(servico.agenda_criar(sessao_de(auth), corpo), 201)


@router.get("/api/agendas/{agenda_id}", response_model=Agenda, responses=ERROS, tags=["agendas"])
def obter_agenda(request: Request, agenda_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.agenda_obter(sessao_de(auth), agenda_id))


@router.put("/api/agendas/{agenda_id}", response_model=Agenda, responses=ERROS, tags=["agendas"])
def atualizar_agenda(request: Request, agenda_id: uuid.UUID, corpo: dict = Body(...),  # noqa: B008
                     auth: Auth = AUTH):
    if not isinstance(corpo, dict):
        raise ErroServico(422, "corpo_invalido", "corpo deve ser um objeto JSON")
    return _sem_cache(servico.agenda_atualizar(sessao_de(auth), agenda_id, corpo))


@router.delete("/api/agendas/{agenda_id}", status_code=204, responses=ERROS, tags=["agendas"])
def apagar_agenda(request: Request, agenda_id: uuid.UUID, auth: Auth = AUTH):
    servico.agenda_apagar(sessao_de(auth), agenda_id)
    return Response(status_code=204)


@router.post("/api/agendas/{agenda_id}/pausar", response_model=Agenda, responses=ERROS, tags=["agendas"])
def pausar_agenda(request: Request, agenda_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.agenda_pausar(sessao_de(auth), agenda_id))


@router.post("/api/agendas/{agenda_id}/retomar", response_model=Agenda, responses=ERROS, tags=["agendas"])
def retomar_agenda(request: Request, agenda_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.agenda_retomar(sessao_de(auth), agenda_id))


@router.post("/api/agendas/{agenda_id}/rodar-agora", response_model=Job, status_code=201, responses=ERROS,
             tags=["agendas"])
def rodar_agenda_agora(request: Request, agenda_id: uuid.UUID, auth: Auth = AUTH):
    return _sem_cache(servico.agenda_rodar_agora(sessao_de(auth), agenda_id), 201)


# ---------------------------------------------------------------- página Tarefas (API serve o HTML; estáticos: nginx)
@router.get("/tarefas", include_in_schema=False)
def pagina_tarefas():
    return paginas.servir("tarefas.html")


@router.get("/tarefas/{job_id}", include_in_schema=False)
def pagina_tarefa(job_id: str):
    return paginas.servir("tarefas.html")
