"""Rotas do módulo modelo 3D / foto 360 (item L1-03-modelo3d; mesmo desenho de app/imagens/rotas_imagens.py):

- `POST /api/modelo3d/ingestoes` — cria o job `modelo3d.converter` a partir de um item `arquivo` (.ifc ou
  .xkt) já enviado. Porta "upload pelo navegador -> job", igual à de imagens.
- `GET /api/modelo3d/{item_id}` — painel do item: chave/URL assinada do .xkt, resumo do IFC quando houver
  (ambientes, elementos, pavimentos), tamanho.
- `POST /api/foto360` — foto 360 (JPEG equirretangular) não precisa de conversão nenhuma: cria o item
  `foto360` direto, síncrono, reaproveitando o MESMO objeto que o upload já gravou (sem copiar bytes).
- `GET /api/foto360/{item_id}` — painel do item: URL assinada da imagem.

Isolamento: mesma regra do L1-01 — toda leitura passa por `db.db(auth.contexto())` (RLS de `plat.item`) e a
URL do objeto é assinada por tempo (`objetos.url_assinada`), nunca a chave interna exposta crua."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo import tipos as tipos_item
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["modelo3d"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


def _arquivo_ok(cur, tenant_id: int, arquivo_id: str) -> dict:
    cur.execute("SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'", (arquivo_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "item_inexistente", "item de arquivo inexistente")
    return r


def _url(chave: str | None) -> str | None:
    if not chave:
        return None
    return objetos.url_assinada(chave, limites.MODELO3D_URL_VALIDADE_S)


# ---------------------------------------------------------------- modelo 3D (IFC -> xkt, ou xkt direto)
class IngestaoEntrada(Modelo):
    model_config = ConfigDict(title="IngestaoEntradaModelo3d")
    arquivo_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    titulo: str | None = Field(default=None, min_length=1, max_length=250)


@router.post("/api/modelo3d/ingestoes", status_code=202, openapi_extra=PUBLICAR)
def modelo3d_ingestao_criar(corpo: IngestaoEntrada, request: Request,
                            auth: Auth = autenticado("conteudo.publicar_camada")):
    arquivo_id = uuid_ok(corpo.arquivo_id, "item_inexistente", "item de arquivo inexistente")
    with db.db(auth.contexto()) as cur:
        _arquivo_ok(cur, auth.tenant_id, arquivo_id)
    job = servico.criar(sessao_de(auth), "modelo3d.converter", {"arquivo_id": arquivo_id, "titulo": corpo.titulo})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "modelo3d/ingestar", "item", arquivo_id, {"job_id": job["id"]})
    return {"job_id": job["id"], "estado": job["estado"]}


def _item_tipo(cur, item_id: str, tipo: str) -> dict:
    iid = uuid_ok(item_id, "item_inexistente", "item inexistente")
    cur.execute("SELECT id, titulo, dados, tamanho_bytes, criado_em FROM plat.item WHERE id = %s::uuid AND tipo = %s",
                (iid, tipo))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


@router.get("/api/modelo3d/{item_id}", openapi_extra=LER)
def modelo3d_ver(item_id: str, auth: Auth = autenticado(escopo_token="modelo3d:ler")):
    with db.db(auth.contexto()) as cur:
        item = _item_tipo(cur, item_id, "modelo3d")
    dados = item["dados"] or {}
    corpo = {
        "item_id": str(item["id"]),
        "titulo": item["titulo"],
        "origem": dados.get("origem"),
        "xkt_url": _url(dados.get("xkt_chave")),
        "bytes_xkt": dados.get("bytes_xkt") or item["tamanho_bytes"],
        "schema_ifc": dados.get("schema_ifc"),
        "projeto": dados.get("projeto"),
        "pavimentos": dados.get("pavimentos") or [],
        "ambientes": dados.get("ambientes") or [],
        "n_ambientes": dados.get("n_ambientes"),
        "n_elementos": dados.get("n_elementos"),
        "conversao": dados.get("conversao"),
        "tem_ifc": bool(dados.get("ifc_chave")),
        "criado_em": item["criado_em"].isoformat() if item["criado_em"] else None,
    }
    return JSONResponse(corpo, headers=SEM_CACHE)


# ---------------------------------------------------------------- foto 360 (sem conversão: síncrono)
class Foto360Entrada(Modelo):
    arquivo_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    titulo: str | None = Field(default=None, min_length=1, max_length=250)


@router.post("/api/foto360", status_code=201, openapi_extra=PUBLICAR)
def foto360_criar(corpo: Foto360Entrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    arquivo_id = uuid_ok(corpo.arquivo_id, "item_inexistente", "item de arquivo inexistente")
    with db.db(auth.contexto()) as cur:
        arq = _arquivo_ok(cur, auth.tenant_id, arquivo_id)
        dados_arq = arq["dados"] or {}
        chave = dados_arq.get("chave")
        if not chave:
            raise ErroAPI(422, "sem_objeto", "item de arquivo sem chave de objeto no campo dados")
        if (dados_arq.get("tipo_declarado") or "").lower() != "foto360":
            raise ErroAPI(422, "tipo_nao_e_foto360", "o arquivo enviado não foi declarado como foto360")
        titulo_final = (corpo.titulo or dados_arq.get("nome_original") or arq["titulo"] or "foto 360")[:250]
        item_id = str(uuid.uuid4())
        # reaproveita o MESMO objeto que o upload já gravou (sem conversão, não há por que duplicar bytes) —
        # a chave já está sob a classe "objeto" do upload; o item passa a apontar para ela
        dados_item = {"imagem_chave": chave, "origem": "enviada"}
        tipos_item.validar("foto360", dados_item)
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'foto360', %s, %s, %s, %s, %s, %s)",
            (item_id, auth.tenant_id, titulo_final, auth.usuario_id, jsonb(dados_item),
             dados_arq.get("bytes"), auth.usuario_id, auth.usuario_id),
        )
        registrar_evento(cur, request, "foto360/criar", "item", item_id, {"arquivo_id": arquivo_id})
    return {"item_id": item_id}


@router.get("/api/foto360/{item_id}", openapi_extra=LER)
def foto360_ver(item_id: str, auth: Auth = autenticado(escopo_token="modelo3d:ler")):
    with db.db(auth.contexto()) as cur:
        item = _item_tipo(cur, item_id, "foto360")
    dados = item["dados"] or {}
    corpo = {
        "item_id": str(item["id"]),
        "titulo": item["titulo"],
        "imagem_url": _url(dados.get("imagem_chave")),
        "origem": dados.get("origem"),
        "criado_em": item["criado_em"].isoformat() if item["criado_em"] else None,
    }
    return JSONResponse(corpo, headers=SEM_CACHE)


__all__ = ["router"]
