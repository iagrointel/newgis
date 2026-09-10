"""Rotas dos relatórios do admin (item L0-07-e-relatorios; privilégio `org.exportar`, já semeado na 003 como
"exportar o inquilino, relatórios"): tipos com cabeçalho documentado, pedir (vira job `relatorios.gerar`), listar,
baixar o CSV, agendar (vira `plat.agenda` diária/semanal/mensal com entrega por e-mail) e o painel Atividade
(10 itens mais acessados, eventos por dia e por tipo, acessos por dia).

Limites declarados, iguais aos relatórios de uso da Esri: janela de até 12 meses (422 acima), 10 mil linhas por
relatório (o job corta e marca `truncado`) e um pedido por tipo por hora (429; o disparo de agenda pelo worker
não passa por aqui e não conta). Isolamento: o job e o CSV vivem sob a RLS de plat.job/plat.arquivo — o job de
outro inquilino é 404 (servico.obter), o objeto tem a chave prefixada pelo slug do inquilino do job."""

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import Field

from app import db, limites, objetos
from app.auth.comum import registrar_evento
from app.auth.modelos import Modelo, Saida
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de
from app.relatorios import tarefas

router = APIRouter(prefix="/api", tags=["relatorios"])
PRIV = {"x-auth": "S/T", "x-privilegio": "org.exportar"}
TIPO_JOB = "relatorios.gerar"
PERIODICIDADES = {"diario": ("0 {h} * * *", 1), "semanal": ("0 {h} * * 1", 7), "mensal": ("0 {h} 1 * *", 31)}


# ---------------------------------------------------------------- modelos
class RelatorioPedido(Modelo):
    tipo: str = Field(pattern="^(membros|itens|grupos|atividade|uso)$")
    desde: str | None = Field(default=None, max_length=40)
    ate: str | None = Field(default=None, max_length=40)
    email: bool = False


class AgendaPedido(Modelo):
    tipo: str = Field(pattern="^(membros|itens|grupos|atividade|uso)$")
    periodicidade: str = Field(pattern="^(diario|semanal|mensal)$")
    hora: int = Field(default=6, ge=0, le=23)
    email: bool = True
    fuso: str = Field(default="America/Sao_Paulo", max_length=64)


class TipoRelatorio(Saida):
    tipo: str
    descricao: str
    cabecalho: list[str]


class Limites(Saida):
    janela_dias: int
    linhas_max: int
    por_tipo_por_hora: int


class TiposRelatorio(Saida):
    tipos: list[TipoRelatorio]
    limites: Limites


class Painel(Saida):
    janela: dict[str, Any]
    totais: dict[str, int]
    top_itens: list[dict[str, Any]]
    eventos_por_dia: list[dict[str, Any]]
    eventos_por_tipo: list[dict[str, Any]]
    acessos_por_dia: list[dict[str, Any]]


# ---------------------------------------------------------------- apoio
def _janela_valida(desde: str | None, ate: str | None) -> tuple[str | None, str | None]:
    """Mesma regra do job (tarefas.janela), só que respondendo 422 antes de enfileirar."""
    try:
        inicio, fim = tarefas.janela(desde, ate, limites.RELATORIO_JANELA_DIAS if desde else 30)
    except tarefas.FalhaDefinitiva as e:
        raise ErroAPI(422, "validacao", str(e), {"campo": "desde"}) from e
    return (iso(inicio) if desde else None, iso(fim) if ate else None)


def _limite_por_hora(auth: Auth, tipo: str) -> None:
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.job WHERE tipo = %s AND parametros->>'tipo' = %s "
            "AND agenda_id IS NULL AND criado_em > now() - interval '1 hour' AND estado <> 'cancelado'",
            (TIPO_JOB, tipo),
        )
        n = cur.fetchone()["n"]
    if n >= limites.RELATORIO_POR_TIPO_HORA:
        raise ErroAPI(
            429,
            "relatorio_limite_hora",
            f"limite de {limites.RELATORIO_POR_TIPO_HORA} relatório de {tipo} por hora; cancele o pendente ou aguarde",
            {"tipo": tipo, "por_hora": limites.RELATORIO_POR_TIPO_HORA},
        )


def _evento(auth: Auth, request: Request, tipo: str, alvo_tipo: str, alvo_id, propriedades: dict) -> None:
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, tipo, alvo_tipo, alvo_id, propriedades)


# ---------------------------------------------------------------- relatórios
@router.get("/relatorios/tipos", response_model=TiposRelatorio, openapi_extra=PRIV)
def tipos(auth: Auth = autenticado("org.exportar")):
    return {
        "tipos": [
            {"tipo": t, "descricao": tarefas.DESCRICOES[t], "cabecalho": tarefas.CABECALHOS[t]} for t in tarefas.TIPOS
        ],
        "limites": {
            "janela_dias": limites.RELATORIO_JANELA_DIAS,
            "linhas_max": limites.RELATORIO_LINHAS_MAX,
            "por_tipo_por_hora": limites.RELATORIO_POR_TIPO_HORA,
        },
    }


@router.get("/relatorios", openapi_extra=PRIV)
def listar(
    tipo: str | None = None,
    limite: int = Query(50, ge=1, le=200),
    deslocamento: int = Query(0, ge=0),
    auth: Auth = autenticado("org.exportar"),
):
    """Jobs `relatorios.gerar` do inquilino (a lista da fila filtrada pelo tipo de job; `tipo` filtra o relatório)."""
    dados = servico.listar(sessao_de(auth), tipo=TIPO_JOB, limite=limite, deslocamento=deslocamento)
    itens = [j for j in dados["itens"] if not tipo or (j.get("parametros") or {}).get("tipo") == tipo]
    return {"itens": itens, "total": dados["total"] if not tipo else len(itens)}


@router.post("/relatorios", status_code=201, openapi_extra=PRIV)
def pedir(corpo: RelatorioPedido, request: Request, auth: Auth = autenticado("org.exportar")):
    desde, ate = _janela_valida(corpo.desde, corpo.ate)
    _limite_por_hora(auth, corpo.tipo)
    params = {"tipo": corpo.tipo, "email": corpo.email}
    if desde:
        params["desde"] = desde
    if ate:
        params["ate"] = ate
    job = servico.criar(sessao_de(auth), TIPO_JOB, params)
    propriedades = {"tipo": corpo.tipo, "desde": desde, "ate": ate, "email": corpo.email}
    _evento(auth, request, "relatorios/gerar", "job", job["id"], propriedades)
    return job


@router.get("/relatorios/agendas", openapi_extra=PRIV)
def agendas(auth: Auth = autenticado("org.exportar")):
    return servico.agendas_listar(sessao_de(auth), tipo=TIPO_JOB, limite=200)


@router.post("/relatorios/agendas", status_code=201, openapi_extra=PRIV)
def agendar(corpo: AgendaPedido, request: Request, auth: Auth = autenticado("org.exportar")):
    """Agenda diária/semanal/mensal (`plat.agenda`, tipo relatorios.gerar): a janela de cada execução é o período
    (1, 7 ou 31 dias até a hora do disparo) e o link vai por e-mail ao dono da agenda quando `email`."""
    cron, dias = PERIODICIDADES[corpo.periodicidade]
    dados = {
        "nome": f"relatorio {corpo.tipo} {corpo.periodicidade}",
        "tipo": TIPO_JOB,
        "parametros": {"tipo": corpo.tipo, "dias": dias, "email": corpo.email},
        "cron": cron.format(h=corpo.hora),
        "fuso": corpo.fuso,
    }
    agenda = servico.agenda_criar(sessao_de(auth), dados)
    _evento(auth, request, "relatorios/agendar", "agenda", agenda["id"],
            {"tipo": corpo.tipo, "periodicidade": corpo.periodicidade, "cron": dados["cron"], "email": corpo.email})
    return agenda


@router.get("/relatorios/{job_id}", openapi_extra=PRIV)
def obter(job_id: uuid.UUID, auth: Auth = autenticado("org.exportar")):
    job = servico.obter(sessao_de(auth), job_id)
    if job["tipo"] != TIPO_JOB:
        raise ErroAPI(404, "job_inexistente", "job não encontrado")
    return job


@router.get(
    "/relatorios/{job_id}/csv",
    openapi_extra=PRIV,
    responses={200: {"content": {"text/csv": {}}}},
)
def csv(job_id: uuid.UUID, auth: Auth = autenticado("org.exportar")):
    """O CSV do relatório concluído (409 enquanto não terminou); job de outro inquilino = 404 pela RLS."""
    job = servico.obter(sessao_de(auth), job_id)
    if job["tipo"] != TIPO_JOB:
        raise ErroAPI(404, "job_inexistente", "job não encontrado")
    if job["estado"] != "concluido" or not (job.get("resultado") or {}).get("chave"):
        raise ErroAPI(409, "relatorio_nao_pronto", f"o relatório está em estado {job['estado']}")
    chave = job["resultado"]["chave"]
    try:
        dados = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "o CSV do relatório não está mais no armazenamento") from e
    nome = tarefas.nome_arquivo(job["resultado"]["tipo"], job_id)
    return Response(
        dados,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nome}", "Cache-Control": "private, no-store"},
    )


# ---------------------------------------------------------------- painel Atividade
@router.get("/atividade", response_model=Painel, openapi_extra=PRIV)
def atividade(dias: int = Query(30, ge=1, le=limites.RELATORIO_JANELA_DIAS), auth: Auth = autenticado("org.exportar")):
    fim = datetime.datetime.now(datetime.UTC)
    inicio = fim - datetime.timedelta(days=dias)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            """
            WITH acessos AS (
              SELECT substring(l.rota FROM '^/api/itens/([0-9a-f-]{36})')::uuid AS item_id, count(*) AS n
              FROM plat.log_acesso l
              WHERE l.em >= %s AND l.em < %s AND l.rota LIKE '/api/itens/%%' AND l.status < 400
              GROUP BY 1
            )
            SELECT i.id, i.titulo, i.tipo, u.login AS dono, a.n AS acessos
            FROM acessos a JOIN plat.item i ON i.id = a.item_id JOIN plat.usuario u ON u.id = i.dono_id
            WHERE i.apagado_em IS NULL
            ORDER BY a.n DESC, i.titulo LIMIT 10
            """,
            (inicio, fim),
        )
        top = [{**r, "id": str(r["id"])} for r in cur.fetchall()]
        cur.execute(
            "SELECT (em AT TIME ZONE 'UTC')::date AS dia, count(*) AS n FROM plat.evento "
            "WHERE em >= %s AND em < %s GROUP BY 1 ORDER BY 1",
            (inicio, fim),
        )
        por_dia = [{"dia": r["dia"].isoformat(), "n": r["n"]} for r in cur.fetchall()]
        cur.execute(
            "SELECT tipo, count(*) AS n FROM plat.evento WHERE em >= %s AND em < %s "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12",
            (inicio, fim),
        )
        por_tipo = [{"tipo": r["tipo"], "n": r["n"]} for r in cur.fetchall()]
        cur.execute(
            "SELECT (em AT TIME ZONE 'UTC')::date AS dia, count(*) AS n, count(DISTINCT usuario_id) AS usuarios "
            "FROM plat.log_acesso WHERE em >= %s AND em < %s GROUP BY 1 ORDER BY 1",
            (inicio, fim),
        )
        acessos_dia = [{"dia": r["dia"].isoformat(), "n": r["n"], "usuarios": r["usuarios"]} for r in cur.fetchall()]
        cur.execute(
            "SELECT (SELECT count(*) FROM plat.evento WHERE em >= %s AND em < %s) AS eventos, "
            "(SELECT count(*) FROM plat.log_acesso WHERE em >= %s AND em < %s) AS acessos, "
            "(SELECT count(DISTINCT usuario_id) FROM plat.log_acesso WHERE em >= %s AND em < %s "
            " AND usuario_id IS NOT NULL) AS usuarios_ativos, "
            "(SELECT count(*) FROM plat.item WHERE criado_em >= %s AND criado_em < %s AND apagado_em IS NULL) "
            "AS itens_novos",
            (inicio, fim) * 4,
        )
        totais = dict(cur.fetchone())
    return {
        "janela": {"desde": iso(inicio), "ate": iso(fim), "dias": dias},
        "totais": {k: int(v) for k, v in totais.items()},
        "top_itens": top,
        "eventos_por_dia": por_dia,
        "eventos_por_tipo": por_tipo,
        "acessos_por_dia": acessos_dia,
    }
