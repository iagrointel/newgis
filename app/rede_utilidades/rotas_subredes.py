"""Rotas da atualização em lote, da conferência e da exportação de subrede (item L4-04-b).

  * `POST /api/rede/{rede_id}/subredes/atualizar` — enfileira o job que atualiza as subredes SUJAS da rede
    (`todas=true` refaz a rede inteira). A atualização de UMA subrede continua síncrona, em
    `rotas_controladores.py` — é rápida e a tela precisa da resposta na hora.
  * `PUT /api/rede/{rede_id}/tier/{codigo}/propagadores` — declara os atributos que o tier propaga.
  * `GET /api/rede/{rede_id}/subredes/conferencia` — compara o nome calculado da subrede com um atributo do
    ARQUIVO no mesmo elemento; a diferença sai listada como candidata a erro de cadastro, nunca como erro
    provado.
  * `GET /api/rede/{rede_id}/subrede/{nome}/exportar` — o JSON da subrede (elementos, conectividade,
    controladores, resumo), validado contra o esquema declarado antes de sair."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de
from app.rede_utilidades import subredes
from app.rede_utilidades.modelos import PropagadoresEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — subredes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
CONFERENCIA_LIMITE_MAX = 1000


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


@router.post("/{rede_id}/subredes/atualizar", status_code=202, openapi_extra=EDITAR)
def atualizar_subredes(rede_id: str, request: Request, todas: bool = False, tier: str | None = None,
                       auth: Auth = autenticado("rede.editar")):
    """Enfileira o job `redes.subredes_atualizar`. Devolve 202 com o id do job: quem chama acompanha em
    `GET /api/jobs/{id}` como em qualquer outro trabalho pesado da plataforma."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
    job = servico.criar(sessao_de(auth), "redes.subredes_atualizar",
                        {"rede_id": rid, "todas": todas, "tier": tier})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "redes/subredes_atualizar", "rede", rid,
                         {"job_id": str(job["id"]), "todas": todas, "tier": tier})
    return {"rede_id": rid, "job_id": str(job["id"]), "todas": todas, "tier": tier}


@router.put("/{rede_id}/tier/{codigo}/propagadores", status_code=200, openapi_extra=EDITAR)
def definir_propagadores(rede_id: str, codigo: str, corpo: PropagadoresEntrada, request: Request,
                         auth: Auth = autenticado("rede.editar")):
    """Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            r = subredes.definir_propagadores(cur, rid, codigo, corpo.propagadores)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/tier_propagadores", "rede", rid, r)
        return r


@router.get("/{rede_id}/subredes/conferencia", openapi_extra=LER)
def conferir_subredes(rede_id: str, atributo: str = "ctmt", grupo: str = "trecho_de_media_tensao",
                      tier: str | None = None, limite: int = 200,
                      auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Concordância entre o nome da subrede calculado pelo traçado e o atributo do arquivo no mesmo elemento.
    A saída traz o universo (quantos elementos), quantos são comparáveis e a lista das diferenças — que são
    candidatas a erro de cadastro, não erro provado."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return subredes.conferir(cur, rid, atributo, grupo, tier, min(max(limite, 1),
                                                                     CONFERENCIA_LIMITE_MAX))


def _exportar_sincrono(rid: str, nome: str, tier: str | None, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return subredes.exportar(cur, rid, nome, tier)


@router.get("/{rede_id}/subrede/{nome}/exportar", openapi_extra=LER)
async def exportar_subrede(rede_id: str, nome: str, tier: str | None = None,
                           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O JSON da subrede: rede, subrede (com a linha agregada), controladores, elementos, conectividade e
    resumo. Validado contra `plat.rede.subrede_exportada` antes de sair."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_exportar_sincrono, rid, nome, tier, auth)
