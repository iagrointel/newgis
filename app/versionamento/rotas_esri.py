"""VersionManagementServer compatível com o protocolo da Esri (item L2-13-a).

É a mesma máquina da API própria (`app/versionamento/servico.py`) vestida com os nomes e as formas de
resposta que o ArcGIS Pro e o cliente Python `arcgis` esperam. Nada é implementado duas vezes.

O que este servidor NÃO faz, escrito aqui para não haver surpresa: `startReading`/`stopReading`/
`startEditing`/`stopEditing` existem porque o cliente da Esri os chama antes de reconciliar e publicar,
mas nesta plataforma a leitura consistente e a escrita atômica vêm da transação do Postgres, não de uma
sessão de versão mantida pelo servidor. As quatro rotas conferem existência do ramo e permissão de
verdade (e recusam quem não tem), devolvem o momento do servidor e não guardam sessão. Documentado em
docs/PARIDADE.md.

`sessionId` é aceito e ecoado quando vem, sem ser exigido: exigi-lo obrigaria a inventar um controle de
sessão que a plataforma não usa.
"""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg2
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db
from app.catalogo import comum
from app.consulta.rotas_query import _autenticar, _item_id_valido
from app.erros import ErroAPI
from app.versionamento import servico

router = APIRouter(tags=["versionamento-esri"])
PREFIXO = "/rest/services/{item_id}/VersionManagementServer"
ABERTURA = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}
LEITURA = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CURRENT_VERSION = 11.4
NOME_PADRAO = "sde.DEFAULT"
GUID_PADRAO = "{00000000-0000-0000-0000-000000000000}"
_CHAVES = re.compile(r"^[A-Za-z0-9_.\- ]{1,128}$")


def _erro(e: ErroAPI) -> JSONResponse:
    """Erro no envelope da Esri (HTTP 200 com `error` dentro é o que o cliente dela entende), mas
    mantendo o código HTTP correto: o cliente `arcgis` lê o corpo, o resto do mundo lê o status."""
    corpo = {"error": {"code": e.status_code, "message": e.mensagem, "details": [e.erro]}}
    return JSONResponse(corpo, status_code=e.status_code)


def _resposta(corpo: dict) -> JSONResponse:
    return JSONResponse(json.loads(json.dumps(corpo, default=str)))


async def _parametros(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in ct:
            try:
                corpo = await request.json()
            except (ValueError, UnicodeDecodeError) as e:
                raise ErroAPI(400, "corpo_invalido", "corpo não é JSON válido") from e
            if isinstance(corpo, dict):
                p.update({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in corpo.items()})
    return p


def _guid(valor: Any) -> str:
    return "{" + str(valor).strip("{}").upper() + "}"


def _ref(versao_guid: str) -> str:
    """O caminho traz o identificador entre chaves (`{...}`), como a Esri escreve. Aceita sem chaves
    também, e aceita o NOME do ramo — é o que torna a URL utilizável à mão."""
    limpo = versao_guid.strip("{}")
    if not _CHAVES.match(limpo):
        raise ErroAPI(404, "versao_inexistente", "ramo inexistente nesta camada")
    return limpo


def _info(v: dict, auth) -> dict:
    return {
        "versionName": v["nome"],
        "versionGuid": _guid(v["id"]),
        "versionId": str(v["id"]),
        "description": v["descricao"] or "",
        "created": v["criada_em"],
        "modified": v["reconciliada_em"] or v["criada_em"],
        "reconcileDate": v["reconciliada_em"],
        "evaluationDate": v["reconciliada_em"],
        "previousAncestorDate": v["momento"],
        "commonAncestorDate": v["momento"],
        "access": {"privado": "private", "protegido": "protected", "publico": "public"}[v["acesso"]],
        "isOwner": v["dono_id"] == auth.usuario_id,
        "parentVersionName": NOME_PADRAO,
        "state": {"aberta": "open", "publicada": "posted", "apagada": "deleted"}[v["estado"]],
    }


def _versao_padrao() -> dict:
    return {
        "versionName": NOME_PADRAO, "versionGuid": GUID_PADRAO, "versionId": "0",
        "description": "versão padrão da camada", "isOwner": False, "parentVersionName": None,
        "access": "public", "state": "open",
    }


def _momento_ms(cur) -> int:
    cur.execute("SELECT (extract(epoch from now()) * 1000)::bigint AS m")
    return int(cur.fetchone()["m"])


# ---------------------------------------------------------------- descritor
@router.get(PREFIXO, openapi_extra=LEITURA, operation_id="vms_descritor_get")
async def descritor_get(request: Request, item_id: str):
    return await _descritor(request, item_id)


@router.post(PREFIXO, openapi_extra=LEITURA, operation_id="vms_descritor_post")
async def descritor_post(request: Request, item_id: str):
    return await _descritor(request, item_id)


async def _descritor(request: Request, item_id: str):
    try:
        _item_id_valido(item_id)
        auth = _autenticar(request, item_id, "camada:ler")
        with db.db(auth.contexto()) as cur:
            servico.camada_versionada_ou_erro(cur, item_id)
            return _resposta(
                {
                    "currentVersion": CURRENT_VERSION,
                    "defaultVersionName": NOME_PADRAO,
                    "defaultVersionGuid": GUID_PADRAO,
                    "capabilities": "Create,Delete,Read,Edit,Reconcile,Post",
                    "size": len(servico.listar_versoes(cur, item_id, auth)),
                }
            )
    except ErroAPI as e:
        return _erro(e)


# ---------------------------------------------------------------- lista de ramos
@router.get(f"{PREFIXO}/versions", openapi_extra=LEITURA, operation_id="vms_versions_get")
async def versions_get(request: Request, item_id: str):
    return await _versions(request, item_id)


@router.post(f"{PREFIXO}/versions", openapi_extra=LEITURA, operation_id="vms_versions_post")
async def versions_post(request: Request, item_id: str):
    return await _versions(request, item_id)


@router.get(f"{PREFIXO}/versionInfos", openapi_extra=LEITURA, operation_id="vms_version_infos_get")
async def version_infos_get(request: Request, item_id: str):
    return await _versions(request, item_id)


@router.post(f"{PREFIXO}/versionInfos", openapi_extra=LEITURA, operation_id="vms_version_infos_post")
async def version_infos_post(request: Request, item_id: str):
    return await _versions(request, item_id)


async def _versions(request: Request, item_id: str):
    try:
        _item_id_valido(item_id)
        auth = _autenticar(request, item_id, "camada:ler")
        with db.db(auth.contexto()) as cur:
            servico.camada_versionada_ou_erro(cur, item_id)
            cur.execute(
                "SELECT * FROM plat.versao WHERE item_id = %s::uuid AND estado <> 'apagada' ORDER BY criada_em",
                (item_id,),
            )
            linhas = [
                v for v in cur.fetchall()
                if auth.tem("feicoes.editar_total") or v["acesso"] != "privado" or v["dono_id"] == auth.usuario_id
            ]
            return _resposta({"versions": [_versao_padrao(), *[_info(v, auth) for v in linhas]]})
    except ErroAPI as e:
        return _erro(e)


# ---------------------------------------------------------------- criar / apagar
@router.post(f"{PREFIXO}/create", openapi_extra=ABERTURA, operation_id="vms_create")
async def criar(request: Request, item_id: str):
    try:
        _item_id_valido(item_id)
        p = await _parametros(request)
        auth = _autenticar(request, item_id, "camada:editar")
        _exigir_editor(auth)
        nome = p.get("versionName") or ""
        if not nome:
            raise ErroAPI(400, "versionname_ausente", "create exige versionName")
        acesso = {"private": "privado", "protected": "protegido", "public": "publico"}.get(
            (p.get("accessPermission") or "protected").lower()
        )
        if acesso is None:
            raise ErroAPI(400, "access_invalido", "accessPermission precisa ser private, protected ou public")
        with db.db(auth.contexto()) as cur:
            v = servico.criar_versao(cur, request, auth, item_id, nome, p.get("description"), acesso)
            cur.execute("SELECT * FROM plat.versao WHERE id = %s::uuid", (v["id"],))
            return _resposta({"success": True, "versionInfo": _info(cur.fetchone(), auth)})
    except ErroAPI as e:
        return _erro(e)
    except psycopg2.Error as e:
        return _erro(comum.erro_do_banco(e))


@router.post(f"{PREFIXO}/{{versao_guid}}/delete", openapi_extra=ABERTURA, operation_id="vms_delete")
async def apagar(request: Request, item_id: str, versao_guid: str):
    try:
        _item_id_valido(item_id)
        auth = _autenticar(request, item_id, "camada:editar")
        _exigir_editor(auth)
        with db.db(auth.contexto()) as cur:
            saida = servico.apagar_versao(cur, request, auth, item_id, _ref(versao_guid))
            return _resposta({"success": True, "versionGuid": _guid(saida["id"])})
    except ErroAPI as e:
        return _erro(e)
    except psycopg2.Error as e:
        return _erro(comum.erro_do_banco(e))


# ---------------------------------------------------------------- reconciliar / conflitos / publicar
@router.post(f"{PREFIXO}/{{versao_guid}}/reconcile", openapi_extra=ABERTURA, operation_id="vms_reconcile")
async def reconciliar(request: Request, item_id: str, versao_guid: str):
    try:
        _item_id_valido(item_id)
        p = await _parametros(request)
        auth = _autenticar(request, item_id, "camada:editar")
        _exigir_editor(auth)
        abortar = str(p.get("abortIfConflicts", "false")).lower() == "true"
        com_post = str(p.get("withPost", "false")).lower() == "true"
        with db.db(auth.contexto()) as cur:
            saida = servico.reconciliar_versao(cur, request, auth, item_id, _ref(versao_guid))
            tem = saida["pendentes"] > 0
            if tem and abortar:
                raise ErroAPI(
                    409, "conflitos_pendentes", "reconciliação abortada: há conflitos",
                    {"pendentes": saida["pendentes"]},
                )
            corpo = {"success": True, "hasConflicts": tem, "moment": _momento_ms(cur),
                     "conflictCount": len(saida["conflitos"])}
            if com_post and not tem:
                publicado = servico.publicar_versao(cur, request, auth, item_id, _ref(versao_guid), "fechar")
                corpo["postSuccess"] = True
                corpo["postSummary"] = publicado
            return _resposta(corpo)
    except ErroAPI as e:
        return _erro(e)
    except psycopg2.Error as e:
        return _erro(comum.erro_do_banco(e))


@router.get(f"{PREFIXO}/{{versao_guid}}/conflicts", openapi_extra=LEITURA, operation_id="vms_conflicts_get")
async def conflitos_get(request: Request, item_id: str, versao_guid: str):
    return await _conflitos(request, item_id, versao_guid)


@router.post(f"{PREFIXO}/{{versao_guid}}/conflicts", openapi_extra=LEITURA, operation_id="vms_conflicts_post")
async def conflitos_post(request: Request, item_id: str, versao_guid: str):
    return await _conflitos(request, item_id, versao_guid)


async def _conflitos(request: Request, item_id: str, versao_guid: str):
    try:
        _item_id_valido(item_id)
        auth = _autenticar(request, item_id, "camada:ler")
        with db.db(auth.contexto()) as cur:
            saida = servico.conflitos_da_versao(cur, item_id, _ref(versao_guid), auth)
            feicoes = [
                {
                    "globalId": "{" + c["globalid"].upper() + "}",
                    "conflictType": c["tipo"],
                    "resolved": c["resolvido_em"] is not None,
                    "resolution": c["decisao"],
                    "fields": c["detalhe"].get("atributos") or {},
                    "geometryChanged": bool((c["detalhe"].get("geometria") or {}).get("mudou_no_ramo")),
                }
                for c in saida["conflitos"]
            ]
            # esta implementação publica UMA camada por item (layerId 0), como o resto do FeatureServer
            return _resposta({"conflicts": [{"layerId": 0, "features": feicoes}] if feicoes else []})
    except ErroAPI as e:
        return _erro(e)


@router.post(f"{PREFIXO}/{{versao_guid}}/post", openapi_extra=ABERTURA, operation_id="vms_post")
async def publicar(request: Request, item_id: str, versao_guid: str):
    try:
        _item_id_valido(item_id)
        auth = _autenticar(request, item_id, "camada:editar")
        _exigir_editor(auth)
        with db.db(auth.contexto()) as cur:
            saida = servico.publicar_versao(cur, request, auth, item_id, _ref(versao_guid), "fechar")
            return _resposta({"success": True, "moment": _momento_ms(cur), "summary": saida})
    except ErroAPI as e:
        return _erro(e)
    except psycopg2.Error as e:
        return _erro(comum.erro_do_banco(e))


# ---------------------------------------------------------------- sessões de leitura/edição do protocolo
def _exigir_editor(auth) -> None:
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )


async def _sessao(request: Request, item_id: str, versao_guid: str, escrita: bool):
    try:
        _item_id_valido(item_id)
        p = await _parametros(request)
        auth = _autenticar(request, item_id, "camada:editar" if escrita else "camada:ler")
        if escrita:
            _exigir_editor(auth)
        with db.db(auth.contexto()) as cur:
            servico.camada_versionada_ou_erro(cur, item_id)
            servico.obter_versao(cur, item_id, _ref(versao_guid), auth, escrita=escrita)
            corpo = {"success": True, "moment": _momento_ms(cur)}
            if p.get("sessionId"):
                corpo["sessionId"] = p["sessionId"]
            return _resposta(corpo)
    except ErroAPI as e:
        return _erro(e)


@router.post(f"{PREFIXO}/{{versao_guid}}/startReading", openapi_extra=LEITURA, operation_id="vms_start_reading")
async def start_reading(request: Request, item_id: str, versao_guid: str):
    return await _sessao(request, item_id, versao_guid, False)


@router.post(f"{PREFIXO}/{{versao_guid}}/stopReading", openapi_extra=LEITURA, operation_id="vms_stop_reading")
async def stop_reading(request: Request, item_id: str, versao_guid: str):
    return await _sessao(request, item_id, versao_guid, False)


@router.post(f"{PREFIXO}/{{versao_guid}}/startEditing", openapi_extra=ABERTURA, operation_id="vms_start_editing")
async def start_editing(request: Request, item_id: str, versao_guid: str):
    return await _sessao(request, item_id, versao_guid, True)


@router.post(f"{PREFIXO}/{{versao_guid}}/stopEditing", openapi_extra=ABERTURA, operation_id="vms_stop_editing")
async def stop_editing(request: Request, item_id: str, versao_guid: str):
    return await _sessao(request, item_id, versao_guid, True)
