"""Rotas do mapa (item L2-01-a-documento-mapa; ADR 0022): `POST/GET/PUT /api/mapas`, `GET /api/mapas/{id}` e
`GET /api/mapas/{id}/completo`.

Um mapa NÃO é uma tabela nova: é um item do catálogo do tipo `mapa` (`plat.item`), com toda a máquina do L0-03
por baixo — RLS por inquilino, compartilhamento, pasta, versão imutável (`plat.item_versao`), relações
(`plat.item_relacao`, que é o que faz apagar uma camada usada por um mapa dar 409) e evento de auditoria. Estas
rotas são a porta CURTA para o construtor de mapa: recebem e devolvem o documento, validam o que o esquema não
alcança e resolvem as referências. Quem quiser continua podendo usar `/api/itens` com `tipo: "mapa"` — as duas
portas passam pela MESMA validação, porque a validação mora em `app/catalogo/tipos.py` e em `app/mapas/
documento.py`, não na rota.

`GET /completo` é a razão de existir da rota: o navegador precisa, numa única chamada, do documento com cada
camada já resolvida (título, tipo, campos, estilo, popup, contrato de tiles). Sem ela seriam 1 + N chamadas —
a irritação nº 1 anotada no L0-03-a sobre a migração de Web Map da Esri, onde a camada vem por URL absoluta.
"""

from __future__ import annotations

from typing import Any

import psycopg2
from fastapi import APIRouter, Query, Request, Response
from pydantic import Field

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, tipos
from app.catalogo.modelos import Item, ItemEntrada, Modelo, Pagina
from app.catalogo.rotas_itens import (
    _params_lista,
    carregar_varios,
    editar_item,
    listar_ids,
)
from app.catalogo.rotas_itens import (
    criar as criar_item,
)
from app.erros import ErroAPI
from app.mapas import documento as doc_mapa

router = APIRouter(tags=["mapa"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}

DOCUMENTO_VAZIO = {"esquema_versao": 1, "corpo": {}}


class MapaEntrada(Modelo):
    titulo: str = Field(min_length=1, max_length=limites.ITEM_TITULO_MAX)
    resumo: str | None = Field(default=None, max_length=limites.ITEM_RESUMO_MAX)
    descricao: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    tags: list[str] = Field(default_factory=list, max_length=limites.ITEM_TAGS_MAX)
    pasta_id: str | None = None
    extent: list[float] | None = None
    categorias: list[str] = Field(default_factory=list, max_length=limites.ITEM_CATEGORIAS_MAX)
    dados: dict[str, Any] | None = None


class MapaEditar(Modelo):
    titulo: str | None = Field(default=None, min_length=1, max_length=limites.ITEM_TITULO_MAX)
    resumo: str | None = Field(default=None, max_length=limites.ITEM_RESUMO_MAX)
    descricao: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    tags: list[str] | None = Field(default=None, max_length=limites.ITEM_TAGS_MAX)
    extent: list[float] | None = None
    categorias: list[str] | None = Field(default=None, max_length=limites.ITEM_CATEGORIAS_MAX)
    dados: dict[str, Any] | None = None
    versao_atual: int | None = None


def _documento(dados) -> dict:
    """Documento a gravar: ausente vira o documento vazio válido, nunca `{}` cru (que já falharia no esquema)."""
    if dados is None:
        return dict(DOCUMENTO_VAZIO)
    if not isinstance(dados, dict):
        raise ErroAPI(422, "dados_invalidos", "o campo dados precisa ser um objeto JSON")
    d = dict(dados)
    d.setdefault("esquema_versao", 1)
    d.setdefault("corpo", {})
    return d


def _validar(cur, dados: dict) -> None:
    """Ordem fixa: esquema (caminho do campo), coerência (lista inteira), referências (banco). A ordem importa —
    conferir referência antes do esquema deixaria um documento malformado consultar o banco."""
    tipos.validar("mapa", dados)
    doc_mapa.validar_coerencia(dados)
    doc_mapa.carregar_referencias(cur, dados)


def _mapa_ou_404(cur, id: str) -> dict:
    r = comum.item_ou_404(cur, id)
    if r["tipo"] != "mapa":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


@router.get("/api/mapas", response_model=Pagina, openapi_extra=LER)
def listar_mapas(
    request: Request,
    resposta: Response,
    q: str | None = None,
    ordenar: str | None = None,
    direcao: str | None = None,
    pasta_id: str | None = None,
    meus: bool = False,
    favoritos: bool = False,
    limite: int | None = None,
    deslocamento: int | None = None,
    cursor: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Mesma lista de `/api/itens` com `tipo` travado em `mapa` (os demais filtros da query continuam valendo)."""
    p = _params_lista(request, limite, deslocamento)
    p["tipo"] = ["mapa"]
    with db.db(auth.contexto()) as cur:
        total, ids, proximo, aproximado = listar_ids(cur, auth, p)
        itens = carregar_varios(cur, ids, auth)
    if proximo:
        resposta.headers["Link"] = f'<{request.url.path}?cursor={proximo}>; rel="next"'
    saida = {"total": total, "itens": itens, "proximo_cursor": proximo}
    if aproximado:
        saida["aproximado"] = True
    return saida


@router.post("/api/mapas", response_model=Item, status_code=201, openapi_extra=CRIAR)
def criar_mapa(corpo: MapaEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    dados = _documento(corpo.dados)
    with db.db(auth.contexto()) as cur:
        _validar(cur, dados)
    entrada = ItemEntrada(
        tipo="mapa",
        titulo=corpo.titulo,
        resumo=corpo.resumo,
        descricao=corpo.descricao,
        tags=corpo.tags,
        pasta_id=corpo.pasta_id,
        extent=corpo.extent,
        categorias=corpo.categorias,
        dados=dados,
    )
    return criar_item(entrada, request, auth)


@router.get("/api/mapas/{id}", response_model=Item, openapi_extra=LER)
def ver_mapa(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return comum.item_json(_mapa_ou_404(cur, id), auth)


@router.put("/api/mapas/{id}", response_model=Item, openapi_extra=EDITAR)
def editar_mapa(id: str, corpo: MapaEditar, request: Request, auth: Auth = autenticado()):
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise ErroAPI(422, "validacao", "nada a alterar")
    try:
        with db.db(auth.contexto()) as cur:
            _mapa_ou_404(cur, id)
            if "dados" in campos:
                campos["dados"] = _documento(campos["dados"])
                _validar(cur, campos["dados"])
            return comum.item_json(editar_item(cur, request, auth, id, campos), auth)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/mapas/{id}/completo", openapi_extra=LER)
def mapa_completo(
    id: str,
    incluir_documento: bool = Query(False, description="devolve também o documento como está gravado"),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Documento com as camadas resolvidas em UMA chamada. Referência que o ator não pode ler é 404 aqui também:
    o mapa não vira meio-mapa silencioso quando alguém perde acesso a uma camada."""
    with db.db(auth.contexto()) as cur:
        r = _mapa_ou_404(cur, id)
        saida = doc_mapa.completo(cur, {"id": str(r["id"]), "titulo": r["titulo"], "tipo": r["tipo"]}, r["dados"])
        if incluir_documento:
            saida["documento"] = r["dados"]
        return saida

