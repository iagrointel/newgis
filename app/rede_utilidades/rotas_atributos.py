"""Rotas de atributos de rede (item L4-01-d-atributos-de-rede; migração 20260907T1239).

`POST .../atributos/sincronizar` faz a sincronização em LOTE (tensão/capacidade + aresta interna do
dispositivo); a sincronização de UMA feição já editada é o trigger da migração, sem rota própria.
`POST .../atributos/propagar-fase` propaga a fase do(s) controlador(es) e grava discrepância.
`POST .../atributos/conectividade` recalcula `is_connected`/`subrede`. `POST .../atributos/substituicoes`
declara a regra de substituição. `GET .../atributos/discrepancias` lista o que foi achado.

Mesmo padrão de `rotas_topologia.py`: escrita exige `rede.editar`; leitura segue RLS; passos custosos vão
para o threadpool."""

import uuid as uuid_mod

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import atributos

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — atributos"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 2000


def _uuid_ok(valor: str, entidade: str = "rede") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, f"{entidade}_inexistente", f"{entidade} inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


class SubstituicaoEntrada(BaseModel):
    tipo_id: str
    atributo_codigo: str = Field(min_length=1, max_length=63)
    de_valor: int = Field(ge=0, le=7)
    para_valor: int = Field(ge=0, le=7)
    descricao: str | None = Field(default=None, max_length=2000)


def _sincronizar_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        resumo = atributos.sincronizar_topologia_lote(cur, auth.tenant_id, rid)
        registrar_evento(cur, request, "redes/atributos_sincronizar", "rede", rid, resumo)
    return resumo


@router.post("/{rede_id}/atributos/sincronizar", status_code=200, openapi_extra=EDITAR)
async def sincronizar_atributos(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Sincroniza em lote: tensão/capacidade das feições -> topologia, e (re)constrói a aresta interna de
    cada dispositivo de dois terminais (`plat.rede_topo_dispositivo_aresta`). Exige topologia já habilitada."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_sincronizar_sincrono, rid, auth, request)


def _propagar_fase_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        resumo = atributos.propagar_fase(cur, auth.tenant_id, rid)
        registrar_evento(cur, request, "redes/fase_propagar", "rede", rid, resumo)
    return resumo


@router.post("/{rede_id}/atributos/propagar-fase", status_code=200, openapi_extra=EDITAR)
async def propagar_fase(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Propaga a fase do(s) nó(s) controlador(es) para jusante (BFS respeitando traversabilidade e regra de
    substituição) e grava a divergência contra a fase declarada em `plat.rede_atributo_discrepancia`."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_propagar_fase_sincrono, rid, auth, request)


def _conectividade_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        resumo = atributos.recalcular_conectividade(cur, auth.tenant_id, rid)
        registrar_evento(cur, request, "redes/conectividade_recalcular", "rede", rid, resumo)
    return resumo


@router.post("/{rede_id}/atributos/conectividade", status_code=200, openapi_extra=EDITAR)
async def recalcular_conectividade(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Recalcula `is_connected`/`subrede` por alcançabilidade a partir do(s) controlador(es)."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_conectividade_sincrono, rid, auth, request)


@router.post("/{rede_id}/atributos/substituicoes", status_code=201, openapi_extra=EDITAR)
def criar_substituicao(rede_id: str, corpo: SubstituicaoEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    tid = _uuid_ok(corpo.tipo_id, "tipo")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute("SELECT 1 FROM plat.rede_tipo WHERE id = %s::uuid AND rede_id = %s::uuid", (tid, rid))
        if cur.fetchone() is None:
            raise ErroAPI(404, "tipo_inexistente", "tipo inexistente nesta rede")
        sid = atributos.definir_substituicao(cur, auth.tenant_id, rid, tid, corpo.atributo_codigo,
                                              corpo.de_valor, corpo.para_valor, corpo.descricao)
        registrar_evento(cur, request, "redes/substituicao_definir", "rede", rid,
                         {"tipo_id": tid, "atributo_codigo": corpo.atributo_codigo})
        return {"id": sid}


@router.get("/{rede_id}/atributos/discrepancias", openapi_extra=LER)
def listar_discrepancias(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT id, aresta_id, atributo_codigo, valor_declarado, valor_propagado, detectada_em "
            "FROM plat.rede_atributo_discrepancia WHERE rede_id = %s::uuid ORDER BY detectada_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "aresta_id": str(r["aresta_id"]), "atributo_codigo": r["atributo_codigo"],
             "valor_declarado": r["valor_declarado"], "valor_propagado": r["valor_propagado"],
             "detectada_em": r["detectada_em"].isoformat()}
            for r in cur.fetchall()
        ]
        return {"total": len(itens), "itens": itens}
