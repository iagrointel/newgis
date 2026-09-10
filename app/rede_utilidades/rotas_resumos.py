"""Rotas do sumário por subrede (item L4-04-c-sumarios-por-subrede).

`POST /api/rede/{rede_id}/subredes/resumos/calcular` recalcula os sumários (a rede inteira, um tier ou uma
subrede) e grava em `plat.rede_subrede_resumo`. `GET /api/rede/{rede_id}/subredes/resumos` devolve a tabela:
a descrição das colunas (código, nome, tipo, unidade) junto com as linhas, que é o que um painel precisa
para ligar um elemento a esta fonte sem que ninguém escreva os rótulos à mão; com `formato=csv` a mesma
tabela sai em CSV (mesmo padrão do log de acesso do L0-02).

Mesmo padrão dos outros módulos de rede: escrita exige `rede.editar`, leitura segue a visibilidade por
inquilino (RLS), trabalho pesado vai para o threadpool."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import resumos

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — sumário por subrede"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 5000


def _uuid_ok(valor: str, erro: str = "rede_inexistente", texto: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, erro, texto) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _calcular_sincrono(rid: str, tier: str | None, subrede_id: str | None, auth: Auth,
                       request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            contagem = resumos.calcular_todas(cur, auth.tenant_id, rid, tier, subrede_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/subrede_resumo", "rede", rid, contagem)
    return contagem


@router.post("/{rede_id}/subredes/resumos/calcular", status_code=200, openapi_extra=EDITAR)
async def calcular_resumos(rede_id: str, request: Request, tier: str | None = None,
                           subrede_id: str | None = None, auth: Auth = autenticado("rede.editar")):
    """Recalcula o sumário de cada subrede: quilômetro por nível de tensão, transformadores e potência
    instalada, unidades consumidoras por classe, energia anual faturada, dispositivos por categoria,
    geração distribuída e tronco. Sem `tier` nem `subrede_id`, recalcula a rede inteira."""
    rid = _uuid_ok(rede_id)
    sid = _uuid_ok(subrede_id, "subrede_inexistente", "esta subrede não existe nesta rede") if subrede_id \
        else None
    return await run_in_threadpool(_calcular_sincrono, rid, tier, sid, auth, request)


@router.get("/{rede_id}/subredes/resumos", responses={200: {"content": {"text/csv": {}}}},
            openapi_extra=LER)
def listar_resumos(rede_id: str, tier: str | None = None, limite: int = 500, formato: str = "json",
                   auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A tabela de sumários: `colunas` descreve cada coluna (código, nome, tipo, unidade) e `itens` traz as
    linhas. `formato=csv` devolve a mesma tabela como arquivo."""
    rid = _uuid_ok(rede_id)
    if formato not in ("json", "csv"):
        raise ErroAPI(422, "formato_invalido", "formato tem de ser 'json' ou 'csv'")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = resumos.listar(cur, rid, min(limite, LISTA_LIMITE_MAX), tier)
    if formato == "csv":
        return StreamingResponse(
            iter([resumos.csv_de(itens)]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=subredes_resumo.csv"},
        )
    for item in itens:
        item["calculado_em"] = iso(item["calculado_em"])
    return {"total": len(itens), "colunas": [dict(c) for c in resumos.COLUNAS], "itens": itens}
