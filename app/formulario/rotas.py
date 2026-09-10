"""Rotas do construtor de formulário (item L5-03-form-builder): `/api/camadas/{id}/formulario*`.

Leitura (formulário publicado, lista de campos da camada) exige só `camada:ler` — é o que a edição web
e o PWA de campo usam para desenhar o formulário de verdade. Escrita (salvar rascunho, publicar) exige
`comum.exigir_edicao` — o MESMO privilégio (`conteudo.criar` no dono, `conteudo.editar_tudo` no admin) já
usado para editar metadado de qualquer item do catálogo; não há privilégio novo neste item."""

from __future__ import annotations

import psycopg2
from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.formulario import servico
from app.formulario.modelos import FormularioCriar, VersaoSalvar

router = APIRouter(tags=["formulario"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "conteudo.criar|conteudo.editar_tudo"}


def _versao_json(v: dict, com_desenho: bool = False) -> dict:
    j = {
        "id": str(v["id"]), "versao": v["versao"], "publicado": v["publicado"],
        "criado_em": v["criado_em"].isoformat(),
    }
    if com_desenho:
        j["desenho"] = v["desenho"]
    return j


@router.get("/api/camadas/{id}/campos", openapi_extra=LER)
def campos_da_camada(id: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> dict:
    """Paleta do construtor: atributos reais da camada (nome/tipo/alias) — o campo do desenho tem de
    casar com um destes, ou ser declarado `persistido: false` (portão cláusula 2)."""
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        _item, dados = servico.camada_ou_404(cur, iid)
    return {"campos": dados.get("campos") or []}


@router.get("/api/camadas/{id}/formulario", openapi_extra=LER)
def formulario_publicado(id: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> dict:
    """Formulário PUBLICADO da camada — o que a edição web e o PWA de campo renderizam. `desenho: null`
    quando a camada não tem formulário publicado ainda (a tela cai para o formulário genérico de sempre,
    campo a campo sem grupo/condicional/cálculo)."""
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        servico.camada_ou_404(cur, iid)
        f = servico.formulario_obter(cur, iid)
        desenho = servico.desenho_publicado(cur, iid)
    return {"formulario": servico.formulario_json(f) if f else None, "desenho": desenho}


@router.get("/api/camadas/{id}/formulario/versoes", openapi_extra=ESCREVER)
def formulario_versoes(id: str, auth: Auth = autenticado(escopo_token="camada:editar")) -> dict:
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        comum.exigir_edicao(cur, iid)
        f = servico.formulario_obter(cur, iid)
        if f is None:
            return {"formulario": None, "versoes": []}
        versoes = servico.versoes_listar(cur, str(f["id"]))
    return {"formulario": servico.formulario_json(f), "versoes": [_versao_json(v) for v in versoes]}


@router.get("/api/camadas/{id}/formulario/versoes/{versao}", openapi_extra=ESCREVER)
def formulario_versao_ver(id: str, versao: int, auth: Auth = autenticado(escopo_token="camada:editar")) -> dict:
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        comum.exigir_edicao(cur, iid)
        f = servico.formulario_ou_404(cur, iid)
        v = servico.versao_ou_404(cur, str(f["id"]), versao)
    return _versao_json(v, com_desenho=True)


@router.post("/api/camadas/{id}/formulario", status_code=201, openapi_extra=ESCREVER)
def formulario_criar_ou_renomear(id: str, corpo: FormularioCriar, request: Request,
                                 auth: Auth = autenticado(escopo_token="camada:editar")) -> dict:
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        comum.exigir_edicao(cur, iid)
        servico.camada_ou_404(cur, iid)
        f = servico.formulario_obter(cur, iid)
        if f is None:
            f = servico.formulario_ou_criar(cur, auth, iid, corpo.nome)
            comum.registrar_evento(cur, request, "formulario/criar", "formulario", str(f["id"]), {"camada_id": iid})
        else:
            cur.execute("UPDATE plat.formulario SET nome = %s WHERE id = %s::uuid", (corpo.nome, f["id"]))
            f = servico.formulario_obter(cur, iid)
    return servico.formulario_json(f)


@router.post("/api/camadas/{id}/formulario/versoes", status_code=201, openapi_extra=ESCREVER)
def formulario_salvar_versao(id: str, corpo: VersaoSalvar, request: Request,
                             auth: Auth = autenticado(escopo_token="camada:editar")) -> dict:
    iid = comum.uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            comum.exigir_edicao(cur, iid)
            _item, dados_camada = servico.camada_ou_404(cur, iid)
            v = servico.versao_salvar(cur, auth, iid, dados_camada, corpo.desenho)
            comum.registrar_evento(cur, request, "formulario/versao_salvar", "formulario_versao", str(v["id"]), {
                "camada_id": iid, "versao": v["versao"],
            })
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return _versao_json(v, com_desenho=True)


@router.post("/api/camadas/{id}/formulario/versoes/{versao}/publicar", openapi_extra=ESCREVER)
def formulario_publicar(id: str, versao: int, request: Request,
                        auth: Auth = autenticado(escopo_token="camada:editar")) -> dict:
    iid = comum.uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            comum.exigir_edicao(cur, iid)
            _item, dados_camada = servico.camada_ou_404(cur, iid)
            r = servico.versao_publicar(cur, auth, iid, dados_camada, versao)
            comum.registrar_evento(
                cur, request, "formulario/versao_publicar", "formulario_versao", r["formulario_id"],
                {"camada_id": iid, "versao": versao},
            )
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return r


__all__ = ["router"]
