"""Rotas de exportação vetorial (item L6-02-o-importacao-exportacao-formatos): `POST /api/itens/{id}/exportar`
dispara `ingestao.exportar_camada` para uma camada hospedada; `POST /api/org/exportar` dispara
`ingestao.exportar_inquilino` (escrow do L0-06 — todas as camadas do inquilino num GeoPackage + manifesto JSON).
Os dois só criam o job (202); o resultado (chave do objeto, avisos de formato) sai de `GET /api/jobs/{id}`,
mesmo padrão de `app/ingestao/rotas.py`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import JobCriado, Modelo
from app.erros import ErroAPI
from app.ingestao.exportar import FORMATOS_EXPORTACAO
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["ingestao"])
PUBLICAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}
ORG_EXPORTAR = {"x-auth": "S", "x-privilegio": "org.exportar"}


class ExportarCamadaEntrada(Modelo):
    formato: str
    crs_srid: int | None = None
    campos: list[dict] | None = None


@router.post("/api/itens/{id}/exportar", response_model=JobCriado, status_code=202, openapi_extra=PUBLICAR)
def exportar_camada(id: str, corpo: ExportarCamadaEntrada, request: Request,
                    auth: Auth = autenticado("conteudo.publicar_camada")):
    if corpo.formato not in FORMATOS_EXPORTACAO:
        raise ErroAPI(422, "formato_nao_suportado",
                      f"formato {corpo.formato!r} não suportado para exportação; aceitos: {sorted(FORMATOS_EXPORTACAO)}",  # noqa: E501
                      {"aceitos": sorted(FORMATOS_EXPORTACAO)})
    item_id = uuid_ok(id, "item_inexistente", "item inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "item_inexistente", "camada inexistente (ou não é uma camada_vetorial)")
        registrar_evento(cur, request, "camadas/exportar_pedir", "item", item_id, {"formato": corpo.formato})
    parametros = {"item_id": item_id, "formato": corpo.formato}
    if corpo.crs_srid is not None:
        parametros["crs_srid"] = corpo.crs_srid
    if corpo.campos is not None:
        parametros["campos"] = corpo.campos
    job = servico.criar(sessao_de(auth), "ingestao.exportar_camada", parametros)
    return {"job_id": job["id"]}


@router.post("/api/org/exportar", response_model=JobCriado, status_code=202, openapi_extra=ORG_EXPORTAR)
def exportar_inquilino(request: Request, auth: Auth = autenticado("org.exportar")):
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "org/exportar_pedir", "tenant", str(auth.tenant_id), {})
    job = servico.criar(sessao_de(auth), "ingestao.exportar_inquilino", {})
    return {"job_id": job["id"]}
