"""Consulta do log de acesso e dos eventos (ADR 0002 seções 9.3, 9.4): filtros, janela máxima de 92 dias,
CSV até 100 mil linhas, `X-Plat-Inquilino` para o superadmin (transação só leitura, com evento de trilha).

Item L7-06-c acrescenta: filtro por `req_id` em `/api/log` (RLS de `plat.log_acesso` já garante que o
admin de um inquilino nunca vê a linha de outro, MESMO forjando o req_id de outro pedido — o WHERE é
sempre `tenant_id = tenant_atual()` primeiro) e as rotas de nível de log em tempo de execução, só para o
superadmin da plataforma (afeta o processo inteiro, não um inquilino)."""

import csv
import datetime
import io

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db, limites
from app import log as plat_log
from app.auth.comum import paginacao, registrar_evento
from app.auth.modelos import Pagina
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.settings import NIVEIS

router = APIRouter(prefix="/api", tags=["log"])
SUPER = {"x-auth": "S", "x-privilegio": "superadmin"}
COLUNAS = (
    "id",
    "em",
    "usuario_id",
    "usuario",
    "token_id",
    "token_prefixo",
    "ip",
    "metodo",
    "rota",
    "status",
    "bytes",
    "tempo_ms",
    "agente",
    "resultado",
    "req_id",
)


def _instante(valor: str | None, padrao: datetime.datetime, campo: str) -> datetime.datetime:
    if not valor:
        return padrao
    try:
        dt = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as e:
        raise ErroAPI(422, "validacao", f"{campo} precisa ser ISO 8601", {"campo": campo}) from e
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.UTC)


def janela(desde: str | None, ate: str | None) -> tuple[datetime.datetime, datetime.datetime]:
    agora = datetime.datetime.now(datetime.UTC)
    fim = _instante(ate, agora, "ate")
    inicio = _instante(desde, fim - datetime.timedelta(days=7), "desde")
    if inicio > fim:
        raise ErroAPI(422, "validacao", "desde é posterior a ate")
    if fim - inicio > datetime.timedelta(days=limites.LOG_JANELA_DIAS):
        raise ErroAPI(422, "janela_maior_que_92_dias", f"consulte no máximo {limites.LOG_JANELA_DIAS} dias por vez")
    return inicio, fim


def _linha(r: dict) -> dict:
    return {
        "id": r["id"],
        "em": iso(r["em"]),
        "usuario_id": r["usuario_id"],
        "usuario": r.get("usuario"),
        "token_id": r["token_id"],
        "token_prefixo": r.get("token_prefixo"),
        "ip": r["ip"],
        "metodo": r["metodo"],
        "rota": r["rota"],
        "status": r["status"],
        "bytes": r["bytes"],
        "tempo_ms": r["tempo_ms"],
        "agente": r["agente"],
        "resultado": r["resultado"],
        "req_id": r.get("req_id"),
    }


def consultar_log(
    cur, *, usuario_id=None, token_id=None, rota=None, status=None, desde=None, ate=None, limite=50, deslocamento=0,
    req_id=None,
) -> dict:
    inicio, fim = janela(desde, ate)
    condicoes, params = ["l.em >= %s", "l.em < %s"], [inicio, fim]
    if usuario_id is not None:
        condicoes.append("l.usuario_id = %s")
        params.append(usuario_id)
    if token_id is not None:
        condicoes.append("l.token_id = %s")
        params.append(token_id)
    if req_id:
        # o isolamento não é o req_id ser secreto: é o `WHERE tenant_id = tenant_atual()` da RLS, que
        # roda ANTES desta condição — um req_id forjado de outro inquilino só devolve zero linhas
        # (tests/api/test_log_consulta.py::test_req_id_de_outro_inquilino_nao_vaza).
        condicoes.append("l.req_id = %s")
        params.append(req_id)
    if rota:
        condicoes.append("l.rota LIKE %s")
        params.append(rota.replace("%", r"\%") + "%")
    if status:
        s = str(status).lower()
        if len(s) == 3 and s.endswith("xx") and s[0].isdigit():
            condicoes.append("l.status BETWEEN %s AND %s")
            params += [int(s[0]) * 100, int(s[0]) * 100 + 99]
        elif s.isdigit():
            condicoes.append("l.status = %s")
            params.append(int(s))
        else:
            raise ErroAPI(422, "validacao", "status aceita um código (401) ou uma classe (4xx)", {"campo": "status"})
    onde = " WHERE " + " AND ".join(condicoes)
    cur.execute("SELECT count(*) AS n FROM plat.log_acesso l" + onde, params)
    total = cur.fetchone()["n"]
    cur.execute(
        """
        SELECT l.*, u.login AS usuario, k.prefixo AS token_prefixo FROM plat.log_acesso l
        LEFT JOIN plat.usuario u ON u.id = l.usuario_id LEFT JOIN plat.token_servico k ON k.id = l.token_id"""
        + onde
        + " ORDER BY l.em DESC LIMIT %s OFFSET %s",
        params + [limite, deslocamento],
    )
    return {"total": total, "itens": [_linha(r) for r in cur.fetchall()]}


@router.get(
    "/log",
    response_model=Pagina,
    responses={200: {"content": {"text/csv": {}}}},
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.log_ver"},
)
def log_acesso(
    usuario_id: int | None = None,
    token_id: int | None = None,
    rota: str | None = None,
    status: str | None = None,
    desde: str | None = None,
    ate: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    formato: str = "json",
    req_id: str | None = None,
    auth: Auth = autenticado("org.log_ver", superadmin_pode_ler=True),
):
    somente_leitura = auth.leitura_inquilino is not None
    if formato == "csv":
        with db.db(auth.contexto_leitura(), somente_leitura=somente_leitura) as cur:
            pagina = consultar_log(
                cur,
                usuario_id=usuario_id,
                token_id=token_id,
                rota=rota,
                status=status,
                desde=desde,
                ate=ate,
                limite=limites.LOG_CSV_MAX,
                deslocamento=0,
                req_id=req_id,
            )
        saida = io.StringIO()
        w = csv.DictWriter(saida, fieldnames=COLUNAS)
        w.writeheader()
        for item in pagina["itens"]:
            w.writerow(item)
        return StreamingResponse(
            iter([saida.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=log_acesso.csv"},
        )
    lim, desl = paginacao(limite, deslocamento, limites.LOG_LIMITE_MAX)
    with db.db(auth.contexto_leitura(), somente_leitura=somente_leitura) as cur:
        return consultar_log(
            cur,
            usuario_id=usuario_id,
            token_id=token_id,
            rota=rota,
            status=status,
            desde=desde,
            ate=ate,
            limite=lim,
            deslocamento=desl,
            req_id=req_id,
        )


@router.get("/eventos", response_model=Pagina, openapi_extra={"x-auth": "S/T", "x-privilegio": "org.log_ver"})
def eventos(
    tipo: str | None = None,
    ator_id: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado("org.log_ver"),
):
    lim, desl = paginacao(limite, deslocamento, limites.LOG_LIMITE_MAX)
    inicio, fim = janela(desde, ate)
    condicoes, params = ["e.em >= %s", "e.em < %s"], [inicio, fim]
    if tipo:
        condicoes.append("e.tipo = %s")
        params.append(tipo)
    if ator_id is not None:
        condicoes.append("e.ator_id = %s")
        params.append(ator_id)
    onde = " WHERE " + " AND ".join(condicoes)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.evento e" + onde, params)
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT e.*, u.login AS ator_login FROM plat.evento e LEFT JOIN plat.usuario u ON u.id = e.ator_id"
            + onde
            + " ORDER BY e.em DESC, e.id DESC LIMIT %s OFFSET %s",
            params + [lim, desl],
        )
        itens = [
            {
                "id": r["id"],
                "em": iso(r["em"]),
                "tipo": r["tipo"],
                "ator": ({"id": r["ator_id"], "login": r["ator_login"]} if r["ator_id"] else None),
                "alvo_tipo": r["alvo_tipo"],
                "alvo_id": r["alvo_id"],
                "propriedades": r["propriedades"],
                "ip": r["ip"],
                "req_id": r["req_id"],
            }
            for r in cur.fetchall()
        ]
    return {"total": total, "itens": itens}


class NivelDefinir(BaseModel):
    componente: str = Field(..., min_length=1, max_length=200, description="nome do logger (app.consulta), "
                             "prefixo de rota (rota:/api/tiles) ou * (global)")
    nivel: str
    minutos: float | None = Field(default=None, gt=0, le=1440, description="prazo; None = até ser removido")


@router.get("/log/nivel", openapi_extra=SUPER)
def nivel_listar(auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    """Overrides ativos (não expirados) de nível de log em tempo de execução — afeta o PROCESSO inteiro,
    não um inquilino, por isso só o superadmin da plataforma mexe aqui."""
    return {"itens": plat_log.listar_overrides()}


@router.post("/log/nivel", status_code=201, openapi_extra=SUPER)
def nivel_definir(corpo: NivelDefinir, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    if corpo.nivel.upper() not in NIVEIS:
        raise ErroAPI(422, "validacao", f"nivel aceita um de {NIVEIS}", {"campo": "nivel"})
    registro = plat_log.definir_override(corpo.componente, corpo.nivel, corpo.minutos)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "log/nivel_definir", "log_nivel", corpo.componente, registro)
    return registro


@router.delete("/log/nivel", status_code=204, openapi_extra=SUPER)
def nivel_remover(componente: str, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    if not plat_log.remover_override(componente):
        raise ErroAPI(404, "nao_encontrado", "não há override desse componente", {"componente": componente})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "log/nivel_remover", "log_nivel", componente)
    return Response(status_code=204)
