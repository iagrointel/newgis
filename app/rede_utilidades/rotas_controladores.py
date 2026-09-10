"""Rotas do controlador de subrede e dos tiers (item L4-04-a-controladores-e-tiers).

`POST /api/rede/{rede_id}/controlador` marca o terminal de um dispositivo como controlador de uma subrede;
`DELETE /api/rede/{rede_id}/controlador/{id}` desfaz. `GET .../controladores` e `GET .../controlador/{id}`
leem; `GET .../subredes` é a tabela de subredes (tier, controladores, estado limpa/suja, resumo);
`POST .../subredes/{id}/atualizar` refaz o traçado da subrede e a devolve limpa; `GET .../tiers` lista a
hierarquia declarada no pacote. `POST .../controladores/importar` marca o que a importação permite deduzir.

Mesmo padrão dos outros módulos de rede: escrita exige `rede.editar`, leitura segue a visibilidade por
inquilino (RLS), trabalho pesado vai para o threadpool."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import controladores, subredes
from app.rede_utilidades.modelos import Controlador, ControladorEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — controladores e tiers"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 2000


def _uuid_ok(valor: str, erro: str = "rede_inexistente", texto: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, erro, texto) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


@router.post("/{rede_id}/controlador", response_model=Controlador, status_code=201, openapi_extra=EDITAR)
def definir_controlador(rede_id: str, corpo: ControladorEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    """Só um tipo de ativo com a categoria de rede `controlador` pode controlar uma subrede, e o controlador
    é sempre um TERMINAL do dispositivo — não a feição inteira."""
    rid = _uuid_ok(rede_id)
    fid = _uuid_ok(corpo.feicao_id, "feicao_inexistente", "esta feição de ponto não existe nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            r = controladores.definir(
                cur, auth.tenant_id, rid, feicao_id=fid, terminal=corpo.terminal, subrede=corpo.subrede,
                tier_codigo=corpo.tier, papel=corpo.papel, nome=corpo.nome, usuario_id=auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/controlador_definir", "rede", rid,
                         {"subrede": r["subrede"], "tier": r["tier"], "nome": r["nome"],
                          "feicao_id": r["feicao_id"], "terminal": r["terminal"], "papel": r["papel"]})
        return controladores.ver_controlador(cur, rid, r["id"])


@router.delete("/{rede_id}/controlador/{controlador_id}", status_code=204, openapi_extra=EDITAR)
def remover_controlador(rede_id: str, controlador_id: str, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    cid = _uuid_ok(controlador_id, "controlador_inexistente", "este controlador não existe nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = controladores.remover(cur, rid, cid)
        registrar_evento(cur, request, "redes/controlador_remover", "rede", rid,
                         {"nome": r["nome"], "controladores_restantes": r["controladores_restantes"]})
    return Response(status_code=204)


@router.get("/{rede_id}/controladores", openapi_extra=LER)
def listar_controladores(rede_id: str, limite: int = 200,
                         auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = controladores.listar_controladores(cur, rid, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/controlador/{controlador_id}", response_model=Controlador, openapi_extra=LER)
def ver_controlador(rede_id: str, controlador_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A ficha do controlador: qual dispositivo, qual terminal, em que tier, de que subrede, e o nó que ele
    ocupa na topologia CORRENTE (`no_id` nulo = a topologia foi reconstruída e não há nó nessa âncora)."""
    rid = _uuid_ok(rede_id)
    cid = _uuid_ok(controlador_id, "controlador_inexistente", "este controlador não existe nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return controladores.ver_controlador(cur, rid, cid)


@router.get("/{rede_id}/subredes", openapi_extra=LER)
def listar_subredes(rede_id: str, tier: str | None = None, limite: int = 200,
                    auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A tabela de subredes: nome, tier, controladores, estado (limpa/suja) e resumo da última atualização."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = controladores.listar_subredes(cur, rid, min(limite, LISTA_LIMITE_MAX), tier)
        for s in itens:
            s["atualizado_em"] = iso(s["atualizado_em"]) if s["atualizado_em"] else None
            s["criado_em"] = iso(s["criado_em"])
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/tiers", openapi_extra=LER)
def listar_tiers(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Os tiers da rede na ordem da hierarquia (subestação > alimentador > transformador > baixa tensão no
    pacote elétrico), com o tipo (hierárquico ou particionado) e quantas subredes cada um já tem."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = controladores.listar_tiers(cur, rid)
        return {"total": len(itens), "itens": itens}


def _atualizar_sincrono(rid: str, sid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            r = subredes.atualizar(cur, auth.tenant_id, rid, sid)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/subrede_atualizar", "rede", rid,
                         {"subrede": r["nome"], "tier": r["tier"], **r["resumo"]})
    return {**r, "atualizado_em": iso(r["atualizado_em"])}


@router.post("/{rede_id}/subredes/{subrede_id}/atualizar", status_code=200, openapi_extra=EDITAR)
async def atualizar_subrede(rede_id: str, subrede_id: str, request: Request,
                            auth: Auth = autenticado("rede.editar")):
    """Refaz o traçado da subrede a partir dos controladores dela, grava o resumo e a devolve `limpa`."""
    rid = _uuid_ok(rede_id)
    sid = _uuid_ok(subrede_id, "subrede_inexistente", "esta subrede não existe nesta rede")
    return await run_in_threadpool(_atualizar_sincrono, rid, sid, auth, request)


def _importar_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            contagem = controladores.marcar_da_importacao(cur, auth.tenant_id, rid, auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/controlador_importar", "rede", rid, contagem)
    return contagem


@router.post("/{rede_id}/controladores/importar", status_code=200, openapi_extra=EDITAR)
async def importar_controladores(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Marca um controlador por alimentador (CTMT) no tier de média tensão e um por transformador de
    distribuição (UNTRMT) no tier de baixa tensão, a partir do que a importação da BDGD trouxe."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_importar_sincrono, rid, auth, request)
