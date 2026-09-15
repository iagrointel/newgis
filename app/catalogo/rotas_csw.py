"""Rota `/csw` (KVP OGC — `SERVICE=CSW&REQUEST=...&VERSION=2.0.2`), item L0-09-metadado-catalogo cláusula 1.
Um único endpoint (mesmo padrão de `app/consulta/rotas_wfs.py::wfs_kvp`): `REQUEST=` decide a operação.
Autenticação sempre `catalogo:ler` (sessão OU token de serviço) — nunca aberta, mesma regra de `/ogc/records`
(`app/catalogo/rotas_ogc.py`). O corpo de cada operação vive em `app/catalogo/csw.py`; este módulo só lê o
KVP e chama."""

import re

from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import csw as mod_csw
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/csw", tags=["csw"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
_XML = "application/xml"
_MAX_RECORDS_PADRAO = 10
# CQL mínimo que o portão do item pede: `AnyText LIKE '%termo%'` (com ou sem os `%`) — qualquer outra
# expressão (comparação por outra propriedade, AND/OR, BBOX) é 400 `cql_nao_suportado`, nomeado.
_RE_ANYTEXT_LIKE = re.compile(r"(?is)^\s*AnyText\s+LIKE\s+'%?(?P<termo>.*?)%?'\s*$")


def _base(request: Request) -> str:
    return settings.PLAT_URL_PUBLICA or str(request.base_url)


def _termo_do_cql(constraint: str | None) -> str | None:
    if not constraint:
        return None
    m = _RE_ANYTEXT_LIKE.match(constraint)
    if not m:
        raise ErroAPI(
            400,
            "cql_nao_suportado",
            "esta passagem só aceita CQL `AnyText LIKE '%termo%'`",
            {"constraint": constraint},
        )
    return m.group("termo")


@router.get("", openapi_extra=LER, operation_id="csw_kvp")
def csw_kvp(request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    p = {k.upper(): v for k, v in request.query_params.items()}
    requisicao = (p.get("REQUEST") or "").lower()
    base_url = _base(request)

    if requisicao == "getcapabilities":
        return Response(mod_csw.get_capabilities(base_url, "Catálogo da plataforma"), media_type=_XML)

    if requisicao == "getrecords":
        output_schema = p.get("OUTPUTSCHEMA") or mod_csw.CSW
        try:
            start = max(int(p.get("STARTPOSITION") or 1), 1)
            max_records = max(int(p.get("MAXRECORDS") or _MAX_RECORDS_PADRAO), 1)
        except ValueError as e:
            raise ErroAPI(400, "pedido_invalido", "STARTPOSITION/MAXRECORDS exigem inteiro") from e
        termo = _termo_do_cql(p.get("CONSTRAINT"))
        pl = {
            "q": termo,
            "limite": max_records,
            "deslocamento": start - 1,
            "favoritos": False,
            "meus": False,
            "prefixo": False,
        }
        with db.db(auth.contexto()) as cur:
            xml = mod_csw.get_records_response(cur, auth, base_url, pl, start, output_schema, auth.tenant_nome)
        return Response(xml, media_type=_XML)

    if requisicao == "getrecordbyid":
        output_schema = p.get("OUTPUTSCHEMA") or mod_csw.CSW
        item_id = p.get("ID")
        if not item_id:
            raise ErroAPI(400, "pedido_invalido", "GetRecordById exige ID")
        with db.db(auth.contexto()) as cur:
            from app.catalogo.comum import item_ou_404

            row = item_ou_404(cur, item_id)
            xml = mod_csw.get_record_by_id_response(row, auth, base_url, output_schema, auth.tenant_nome)
        return Response(xml, media_type=_XML)

    raise ErroAPI(
        400,
        "pedido_invalido",
        "REQUEST precisa ser GetCapabilities, GetRecords ou GetRecordById",
        {"request": p.get("REQUEST")},
    )
