"""API própria das ferramentas (item L2-05-a): catálogo com esquema JSON (o formulário do navegador é gerado
dele), estimativa de custo e execução — em processo quando o custo fica abaixo de
`limites.FERRAMENTA_SINCRONO_CUSTO_MAX` (L2_CONCEITO C8), senão como job `ferramentas.executar`.
Histórico de análises por usuário = `GET /api/jobs?tipo=ferramentas.executar` e rerodar = `POST /api/jobs/{id}/repetir`
(L0-05 já filtra por dono e guarda os parâmetros: nada a duplicar aqui)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import db, limites
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.consulta_grande import consulta_livre as _consulta_livre  # noqa: F401 — L2-15-b: registra consulta_sql
from app.consulta_grande import ferramentas_grandes as _grandes  # noqa: F401 — L2-15-b: registra as grandes
from app.ferramentas import buffer as _buffer  # noqa: F401 — a importação registra a ferramenta de exemplo
from app.ferramentas import executor, registro
from app.jobs import servico
from app.jobs.contexto import ErroServico, sessao_de

router = APIRouter(tags=["ferramentas"])
PRIVILEGIO = "analise.executar"
ESCOPO = "jobs:executar"
X = {"x-auth": "S/T", "x-privilegio": PRIVILEGIO}
AUTH = autenticado(PRIVILEGIO, escopo_token=ESCOPO)


class Execucao(BaseModel):
    parametros: dict = {}
    titulo: str | None = None
    modo: str = "auto"  # auto (síncrono abaixo do custo) | job (sempre fila)


def ferramenta_ou_404(nome: str) -> registro.Ferramenta:
    f = registro.obter(nome)
    if f is None:
        raise ErroAPI(404, "ferramenta_inexistente", f"ferramenta inexistente: {nome}")
    return f


def erro_api(e: Exception) -> ErroAPI:
    if isinstance(e, registro.ErroParametro):
        return ErroAPI(422, "parametros_invalidos", "parâmetros inválidos",
                       [{"campo": e.campo, "mensagem": e.mensagem}])
    if isinstance(e, executor.ErroExecucao):
        return ErroAPI(e.status, e.codigo, e.mensagem, e.detalhe)
    raise e


def _sem_cache(dados, status: int = 200) -> JSONResponse:
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})


@router.get("/api/ferramentas", openapi_extra=X)
def listar(auth: Auth = AUTH):
    """Catálogo das ferramentas registradas, com manifesto e JSON Schema dos parâmetros."""
    return _sem_cache([registro.descrever(f) for _, f in sorted(registro.REGISTRO.items())])


@router.get("/api/ferramentas/{nome}", openapi_extra=X)
def obter(nome: str, auth: Auth = AUTH):
    return _sem_cache(registro.descrever(ferramenta_ou_404(nome)))


def preparar(auth: Auth, f: registro.Ferramenta, parametros: dict) -> tuple[dict, dict, int]:
    """Valida, resolve as entradas no inquilino do chamador e estima o custo: (normalizados, entradas, custo)."""
    try:
        normalizados = registro.validar_parametros(f, parametros or {})
        with db.db(auth.contexto()) as cur:
            entradas = executor.resolver_entradas(cur, f, normalizados)
        return normalizados, entradas, executor.custo_estimado(f, entradas, normalizados)
    except (registro.ErroParametro, executor.ErroExecucao) as e:
        raise erro_api(e) from e


def executar_sincrono(request: Request, auth: Auth, f: registro.Ferramenta, normalizados: dict,
                      titulo: str | None) -> dict:
    ctx = executor.ContextoSincrono(auth.contexto())
    try:
        return executor.executar(ctx, f, normalizados, titulo, request=request)
    except (registro.ErroParametro, executor.ErroExecucao) as e:
        raise erro_api(e) from e


def enfileirar(request: Request, auth: Auth, f: registro.Ferramenta, normalizados: dict, titulo: str | None) -> dict:
    s = sessao_de(auth)
    try:
        job = servico.criar(s, "ferramentas.executar", {"ferramenta": f.nome, "parametros": normalizados,
                                                        "titulo": titulo})
    except ErroServico:
        raise
    with db.db(s.ctx) as cur:
        registrar_evento(cur, request, "jobs/criar", "job", job["id"], {"tipo": job["tipo"], "origem": "ferramenta",
                                                                      "ferramenta": f.nome})
    return job


@router.post("/api/ferramentas/{nome}/executar", openapi_extra=X, status_code=200)
def executar(nome: str, request: Request, corpo: Execucao = Body(...), auth: Auth = AUTH):  # noqa: B008
    """Roda a ferramenta. Custo <= FERRAMENTA_SINCRONO_CUSTO_MAX e modo=auto: em processo, devolve 200 com o item.
    Senão: 202 com o job (`ferramentas.executar`); o resultado aparece em `resultado.item_id` do job."""
    f = ferramenta_ou_404(nome)
    normalizados, _entradas, custo = preparar(auth, f, corpo.parametros)
    if corpo.modo not in ("auto", "job"):
        raise ErroAPI(422, "modo_invalido", "modo deve ser auto ou job")
    if corpo.modo == "auto" and custo <= limites.FERRAMENTA_SINCRONO_CUSTO_MAX:
        r = executar_sincrono(request, auth, f, normalizados, corpo.titulo)
        return _sem_cache({"sincrono": True, "custo": custo, "item_id": r["item_id"], "titulo": r["titulo"],
                           "feicoes": r["feicoes"], "sha256": r["sha256"], "entradas": r["entradas"]})
    job = enfileirar(request, auth, f, normalizados, corpo.titulo)
    return _sem_cache({"sincrono": False, "custo": custo, "job_id": job["id"], "job": job}, 202)
