"""Rotas do LOTE de importação (item L6-02-o): agrupa N chamadas de `app.ingestao.rotas` numa só, sem
reescrever prova de conteúdo, inspeção ou carga — o núcleo de cada arquivo continua sendo `ingestao.inspecionar`
e `ingestao.carregar` (L0-04). O que existe aqui é só o LOOP e o agrupamento (`plat.intercambio_lote_importacao`,
migração 20260907T1645):

    POST /api/intercambio/importacoes-lote                   cria até INTERCAMBIO_LOTE_ITENS_MAX importações
    PUT  /api/intercambio/importacoes-lote/{lote_id}/confirmar  confirma as que já estão em 'proposta'

A criação é UMA transação: se o item 5 de 10 tem formato não suportado, os 4 anteriores também não existem
(rollback), e a resposta chega antes de qualquer job na fila — a mesma garantia que `POST /api/importacoes`
já dava para 1 arquivo. A confirmação aceita mapeamento de campos e CRS por item (cada arquivo pode ter uma
proposta diferente; não existe 'um mapeamento para todos' quando os arquivos não são do mesmo esquema)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, Modelo
from app.erros import ErroAPI
from app.ingestao.rotas import (
    ConfirmarEntrada,
    carregar_importacao,
    importacao_json,
    preparar_confirmacao,
    preparar_importacao,
)
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["intercambio"])
PUBLICAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}


class ImportacaoLoteItem(Modelo):
    arquivo_id: str = Field(pattern=UUID_PADRAO)
    formato: str = Field(min_length=1, max_length=40)


class ImportacaoLoteEntrada(Modelo):
    itens: list[ImportacaoLoteItem] = Field(min_length=1, max_length=limites.INTERCAMBIO_LOTE_ITENS_MAX)


class ConfirmarLoteItem(ConfirmarEntrada):
    importacao_id: str = Field(pattern=UUID_PADRAO)


class ConfirmarLoteEntrada(Modelo):
    itens: list[ConfirmarLoteItem] = Field(min_length=1, max_length=limites.INTERCAMBIO_LOTE_ITENS_MAX)


@router.post("/api/intercambio/importacoes-lote", status_code=202, openapi_extra=PUBLICAR)
def criar_lote(corpo: ImportacaoLoteEntrada, request: Request,
              auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.intercambio_lote_importacao(tenant_id, usuario_id, total) "
            "VALUES (%s, %s, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, len(corpo.itens)),
        )
        lote_id = str(cur.fetchone()["id"])
        importacao_ids = []
        for item in corpo.itens:
            iid = preparar_importacao(cur, request, auth, item.arquivo_id, item.formato)
            cur.execute("UPDATE plat.importacao SET lote_id = %s::uuid WHERE id = %s::uuid", (lote_id, iid))
            importacao_ids.append(iid)
        registrar_evento(cur, request, "intercambio/importar_lote", "tenant", str(auth.tenant_id),
                         {"lote_id": lote_id, "total": len(importacao_ids)})
    # jobs SEMPRE fora da transação de escrita (mesmo padrão de app.ingestao.rotas.criar): um job que falhasse
    # a criar não deveria reverter o registro já commitado, e o inverso (registro sem job) é visível e corrigível.
    itens_saida = []
    for iid in importacao_ids:
        job = servico.criar(sessao_de(auth), "ingestao.inspecionar", {"importacao_id": iid})
        with db.db(auth.contexto()) as cur:
            cur.execute("UPDATE plat.importacao SET job_inspecao = %s::uuid WHERE id = %s::uuid",
                        (job["id"], iid))
        itens_saida.append({"importacao_id": iid, "job_id": job["id"]})
    return {"lote_id": lote_id, "itens": itens_saida}


@router.get("/api/intercambio/importacoes-lote/{lote_id}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def ver_lote(lote_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    lid = uuid_ok(lote_id, "lote_inexistente", "lote de importação inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.intercambio_lote_importacao WHERE id = %s::uuid", (lid,))
        lote = cur.fetchone()
        if lote is None:
            raise ErroAPI(404, "lote_inexistente", "lote de importação inexistente")
        cur.execute("SELECT * FROM plat.importacao WHERE lote_id = %s::uuid ORDER BY criado_em", (lid,))
        itens = cur.fetchall()
    return {
        "id": str(lote["id"]), "total": lote["total"],
        "criado_em": lote["criado_em"].isoformat() if lote["criado_em"] else None,
        "itens": [importacao_json(r) for r in itens],
    }


@router.put("/api/intercambio/importacoes-lote/{lote_id}/confirmar", status_code=202, openapi_extra=PUBLICAR)
def confirmar_lote(lote_id: str, corpo: ConfirmarLoteEntrada, request: Request,
                   auth: Auth = autenticado("conteudo.publicar_camada")):
    lid = uuid_ok(lote_id, "lote_inexistente", "lote de importação inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.intercambio_lote_importacao WHERE id = %s::uuid", (lid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "lote_inexistente", "lote de importação inexistente")
        alvos = []
        for item in corpo.itens:
            r = carregar_importacao(cur, auth, item.importacao_id)
            if str(r["lote_id"]) != lid:
                raise ErroAPI(422, "importacao_fora_do_lote",
                              f"importação {item.importacao_id!r} não pertence ao lote {lote_id!r}")
            preparar_confirmacao(cur, request, r, item)
            alvos.append(str(r["id"]))
    itens_saida = []
    for iid in alvos:
        job = servico.criar(sessao_de(auth), "ingestao.carregar", {"importacao_id": iid})
        with db.db(auth.contexto()) as cur:
            cur.execute("UPDATE plat.importacao SET job_carga = %s::uuid WHERE id = %s::uuid", (job["id"], iid))
        itens_saida.append({"importacao_id": iid, "job_id": job["id"]})
    return {"lote_id": lote_id, "itens": itens_saida}
