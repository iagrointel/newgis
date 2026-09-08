"""API própria do versionamento por ramo (item L2-13-a). O VersionManagementServer compatível com a Esri
(`app/versionamento/rotas_esri.py`) fala com estas mesmas funções — não há duas implementações."""

import psycopg2
from fastapi import APIRouter, Depends, Request

from app import db
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.edicao.rotas import _auth_editor
from app.versionamento import servico
from app.versionamento.modelos import PublicarEntrada, ResolverEntrada, VersaoEntrada, VersionarEntrada

router = APIRouter(tags=["versionamento"])
EDITAR = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


def _editor(auth: Auth = Depends(_auth_editor)) -> Auth:  # noqa: B008
    return auth


@router.post("/api/camadas/{id}/versionar", openapi_extra=EDITAR)
def versionar_camada(
    id: str, corpo: VersionarEntrada, request: Request, auth: Auth = Depends(_editor)
) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.versionar_camada(cur, request, auth, iid, corpo.ramos_max)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/versoes", openapi_extra=LER)
def listar_versoes(id: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> list[dict]:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        servico.camada_versionada_ou_erro(cur, iid)
        return servico.listar_versoes(cur, iid, auth)


@router.post("/api/camadas/{id}/versoes", status_code=201, openapi_extra=EDITAR)
def criar_versao(id: str, corpo: VersaoEntrada, request: Request, auth: Auth = Depends(_editor)) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.criar_versao(cur, request, auth, iid, corpo.nome, corpo.descricao, corpo.acesso)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/versoes/{versao}", openapi_extra=LER)
def obter_versao(id: str, versao: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        servico.camada_versionada_ou_erro(cur, iid)
        return servico.como_json(servico.obter_versao(cur, iid, versao, auth))


@router.delete("/api/camadas/{id}/versoes/{versao}", openapi_extra=EDITAR)
def apagar_versao(id: str, versao: str, request: Request, auth: Auth = Depends(_editor)) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.apagar_versao(cur, request, auth, iid, versao)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.post("/api/camadas/{id}/versoes/{versao}/reconciliar", openapi_extra=EDITAR)
def reconciliar(id: str, versao: str, request: Request, auth: Auth = Depends(_editor)) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.reconciliar_versao(cur, request, auth, iid, versao)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/versoes/{versao}/conflitos", openapi_extra=LER)
def conflitos(id: str, versao: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        return servico.conflitos_da_versao(cur, iid, versao, auth)


@router.post("/api/camadas/{id}/versoes/{versao}/conflitos/{globalid}/resolver", openapi_extra=EDITAR)
def resolver(
    id: str, versao: str, globalid: str, corpo: ResolverEntrada, request: Request,
    auth: Auth = Depends(_editor),
) -> dict:
    iid = comum.uuid_ok(id)
    gid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.resolver_conflito(
                cur, request, auth, iid, versao, gid, corpo.decisao, corpo.atributos, corpo.geometria
            )
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.post("/api/camadas/{id}/versoes/{versao}/publicar", openapi_extra=EDITAR)
def publicar(
    id: str, versao: str, corpo: PublicarEntrada, request: Request, auth: Auth = Depends(_editor)
) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return servico.publicar_versao(cur, request, auth, iid, versao, corpo.modo)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
