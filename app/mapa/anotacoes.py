"""Anotação de usuário ligada a uma feição de camada (item L2-01-k-desenho-anotacoes; ativo da casa:
`/api/anotacoes` do SIG de teste interno, `app/v3.py`). Comentário com autor/data, texto sempre tratado como
TEXTO puro (nunca HTML) — quem escapa na exibição é o front (`textContent`, nunca `innerHTML`; ver
`web/js/mapa/desenho.js`); aqui só valida tamanho e existência.

Visibilidade: RLS de `plat.anotacao_feicao` (migração 20260907T1655) — membro ATIVO do grupo em que a
anotação foi criada enxerga; outro inquilino nunca (a política já filtra por `tenant_id`, então um uuid de
anotação de outro inquilino cai no mesmo 404 de uuid inexistente, como o resto do catálogo)."""

from __future__ import annotations

import uuid as uuid_mod

import psycopg2.errors
from fastapi import APIRouter, Body, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404
from app.erros import ErroAPI

router = APIRouter(tags=["mapa"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}

_SELECT = """
SELECT a.id::text AS id, a.camada_id::text AS camada_id, a.fid, a.grupo_id::text AS grupo_id,
       a.autor_id, u.nome AS autor_nome, a.texto, a.criado_em, a.editado_em,
       a.resolvido, a.resolvido_em, a.resolvido_por
FROM plat.anotacao_feicao a JOIN plat.usuario u ON u.id = a.autor_id
"""


def _linha(r: dict) -> dict:
    return dict(r)


class AnotacaoEntrada(BaseModel):
    camada_id: str
    fid: str = Field(min_length=1, max_length=128)
    grupo_id: str
    texto: str = Field(min_length=1, max_length=4000)


class AnotacaoEdicao(BaseModel):
    texto: str | None = Field(default=None, min_length=1, max_length=4000)
    resolvido: bool | None = None


@router.get("/api/anotacoes", openapi_extra=LER)
def listar(
    camada_id: str = Query(...),
    fid: str = Query(...),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, camada_id)  # 404 se a camada não existe ou não é legível (mesmo contrato do catálogo)
        cur.execute(_SELECT + " WHERE a.camada_id = %s::uuid AND a.fid = %s ORDER BY a.criado_em", (camada_id, fid))
        return {"anotacoes": [_linha(r) for r in cur.fetchall()]}


@router.post("/api/anotacoes", status_code=201, openapi_extra=ESCREVER)
def criar(entrada: AnotacaoEntrada = Body(...), auth: Auth = autenticado()):  # noqa: B008
    with db.db(auth.contexto()) as cur:
        item_ou_404(cur, entrada.camada_id)
        try:
            uuid_mod.UUID(entrada.grupo_id)
        except ValueError as e:
            raise ErroAPI(422, "grupo_invalido", "grupo_id precisa ser um uuid") from e
        try:
            cur.execute(
                "INSERT INTO plat.anotacao_feicao(tenant_id, camada_id, fid, grupo_id, autor_id, texto) "
                "VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s) RETURNING id::text AS id",
                (auth.tenant_id, entrada.camada_id, entrada.fid, entrada.grupo_id, auth.usuario_id, entrada.texto),
            )
        except psycopg2.errors.RaiseException as e:
            # e.pgerror traz "ERROR:  <mensagem>\nCONTEXT:  ..." — a mensagem do RAISE é a diag, não a
            # última linha (achado ao testar: splitlines()[-1] pegava a linha de CONTEXT, nunca o motivo).
            motivo = e.diag.message_primary or str(e)
            if "grupo_de_outro_inquilino" in motivo:
                raise ErroAPI(404, "grupo_inexistente", "grupo inexistente ou de outro inquilino") from e
            if "sem_contribuicao_no_grupo" in motivo:
                raise ErroAPI(403, "sem_contribuicao_no_grupo", "você não é membro ativo deste grupo") from e
            raise ErroAPI(422, "anotacao_invalida", "não foi possível criar a anotação") from e
        novo_id = cur.fetchone()["id"]
        cur.execute(_SELECT + " WHERE a.id = %s::uuid", (novo_id,))
        return _linha(cur.fetchone())


@router.patch("/api/anotacoes/{id}", openapi_extra=ESCREVER)
def editar(id: str, entrada: AnotacaoEdicao = Body(...), auth: Auth = autenticado()):  # noqa: B008
    with db.db(auth.contexto()) as cur:
        cur.execute(_SELECT + " WHERE a.id = %s::uuid", (id,))
        atual = cur.fetchone()
        if atual is None:
            raise ErroAPI(404, "anotacao_inexistente", "anotação inexistente ou sem permissão de leitura")
        if entrada.texto is not None:
            if atual["autor_id"] != auth.usuario_id:
                raise ErroAPI(403, "sem_permissao", "só o autor edita o texto da anotação")
            cur.execute(
                "UPDATE plat.anotacao_feicao SET texto = %s, editado_em = now() WHERE id = %s::uuid",
                (entrada.texto, id),
            )
        if entrada.resolvido is not None:
            cur.execute(
                "UPDATE plat.anotacao_feicao SET resolvido = %s, "
                "resolvido_em = CASE WHEN %s THEN now() ELSE NULL END, "
                "resolvido_por = CASE WHEN %s THEN %s ELSE NULL END WHERE id = %s::uuid",
                (entrada.resolvido, entrada.resolvido, entrada.resolvido, auth.usuario_id, id),
            )
        cur.execute(_SELECT + " WHERE a.id = %s::uuid", (id,))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "anotacao_inexistente", "anotação inexistente ou sem permissão de leitura")
        return _linha(linha)


@router.delete("/api/anotacoes/{id}", status_code=204, response_class=Response, openapi_extra=ESCREVER)
def apagar(id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        cur.execute("DELETE FROM plat.anotacao_feicao WHERE id = %s::uuid AND autor_id = %s", (id, auth.usuario_id))
        if cur.rowcount == 0:
            raise ErroAPI(404, "anotacao_inexistente", "anotação inexistente, de outro autor, ou sem permissão")
    return Response(status_code=204)
