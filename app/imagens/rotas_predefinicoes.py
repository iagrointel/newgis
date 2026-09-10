"""CRUD de predefinições CUSTOM de renderização (item L1-02-f-predefinicoes-de-renderizacao-e-legenda).

Sessão/token, sob `/api/imagens/{item_id}/predefinicoes` — a porta de EDIÇÃO (quem monta/nomeia a
predefinição, mesmo privilégio de `POST /api/imagens/ingestoes`). A porta de LEITURA/USO por token de
serviço é outra (`GET /svc/<token>/raster/<item>/predefinicoes.json` e o parâmetro `predef=`/`STYLES=`/
`renderingRule`, em `rotas_tiles.py`/`rotas_wms.py`/`rotas_imageserver.py`) — a mesma separação leitura×
edição que o resto da linha de imagens já usa.

As 6 predefinições de FÁBRICA não aparecem aqui (não são deste inquilino, não têm o que editar/apagar);
`GET` lista as duas famílias juntas só para a tela ter um lugar só de onde ler."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.imagens import pgstac as ps
from app.imagens import predefinicoes as pred

router = APIRouter(tags=["imagens-predefinicoes"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EDITAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


def _item_raster(cur, item_id: str) -> dict:
    iid = uuid_ok(item_id, "item_inexistente", "item inexistente")
    cur.execute(
        "SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'raster'",
        (iid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


def _stac_do_item(cur, auth, item: dict) -> dict:
    dados = item["dados"] or {}
    colecao = dados.get("colecao") or ""
    if not ps.colecao_pertence(colecao, auth.tenant_id):
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    stac = ps.item_obter(cur, auth.tenant_id, colecao, dados.get("stac_id") or "")
    if stac is None:
        raise ErroAPI(404, "item_inexistente", "item sem registro STAC")
    return stac


class PredefinicaoEntrada(Modelo):
    nome: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,58}$")
    titulo: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=500)
    bandas: list[int] | None = Field(default=None, min_length=1, max_length=4)
    colormap: str | None = Field(default=None, max_length=40)
    esticamento: dict | None = None
    nodata_transparente: bool = True
    opacidade: float = Field(default=1.0, ge=0.0, le=1.0)
    resampling: str = Field(default="nearest")


def _corpo_de(entrada: PredefinicaoEntrada) -> dict:
    corpo: dict = {"titulo": entrada.titulo}
    if entrada.descricao is not None:
        corpo["descricao"] = entrada.descricao
    if entrada.bandas is not None:
        corpo["bandas"] = entrada.bandas
    if entrada.colormap is not None:
        corpo["colormap"] = entrada.colormap
    if entrada.esticamento is not None:
        corpo["esticamento"] = entrada.esticamento
    corpo["nodata_transparente"] = entrada.nodata_transparente
    corpo["opacidade"] = entrada.opacidade
    corpo["resampling"] = entrada.resampling
    return corpo


def _checar_bandas_do_item(cur, auth, item: dict, corpo: dict) -> None:
    stac = _stac_do_item(cur, auth, item)
    bandas = corpo.get("bandas") or []
    if not bandas:
        return
    disponiveis = pred.n_bandas(stac, "cientifico")
    maior = max(bandas)
    if maior > disponiveis:
        raise ErroAPI(422, "predefinicao_incompativel",
                      f"a predefinição referencia a banda {maior}; o item tem {disponiveis} "
                      "no asset científico", {"banda_pedida": maior, "bandas_do_item": disponiveis})


def _linha(r: dict) -> dict:
    corpo = r["corpo"]
    return {
        "nome": r["nome"], "titulo": r["titulo"], "versao": r["versao"], "padrao": r["padrao"],
        "criado_em": r["criado_em"].isoformat() if r.get("criado_em") else None,
        "atualizado_em": r["atualizado_em"].isoformat() if r.get("atualizado_em") else None,
        "corpo": corpo,
    }


@router.get("/api/imagens/{item_id}/predefinicoes", openapi_extra=LER)
def listar(item_id: str, auth: Auth = autenticado(escopo_token="imagens:ler")):
    with db.db(auth.contexto()) as cur:
        _item_raster(cur, item_id)
        cur.execute(
            "SELECT nome, titulo, corpo, versao, padrao, criado_em, atualizado_em "
            "FROM plat.render_predefinicao WHERE tenant_id = %s AND item_id = %s::uuid "
            "AND apagado_em IS NULL ORDER BY nome",
            (auth.tenant_id, item_id),
        )
        custom = [_linha(r) for r in cur.fetchall()]
    return {"item_id": item_id, "fabrica": pred.listar_fabrica(), "custom": custom}


@router.post("/api/imagens/{item_id}/predefinicoes", status_code=201, openapi_extra=EDITAR)
def criar(item_id: str, corpo: PredefinicaoEntrada, request: Request,
         auth: Auth = autenticado("conteudo.publicar_camada", escopo_token="imagens:ler")):
    if corpo.nome in pred.NOMES_FABRICA:
        raise ErroAPI(409, "nome_reservado", f"{corpo.nome!r} é uma predefinição de fábrica; escolha outro nome",
                      {"nome": corpo.nome})
    corpo_json = _corpo_de(corpo)
    pred.validar_corpo(corpo_json)
    with db.db(auth.contexto()) as cur:
        item = _item_raster(cur, item_id)
        _checar_bandas_do_item(cur, auth, item, corpo_json)
        cur.execute(
            "SELECT 1 FROM plat.render_predefinicao WHERE tenant_id = %s AND item_id = %s::uuid "
            "AND nome = %s AND apagado_em IS NULL",
            (auth.tenant_id, item_id, corpo.nome),
        )
        if cur.fetchone() is not None:
            raise ErroAPI(409, "nome_em_uso", f"já existe uma predefinição {corpo.nome!r} neste item",
                          {"nome": corpo.nome})
        cur.execute(
            "INSERT INTO plat.render_predefinicao (tenant_id, item_id, nome, titulo, corpo, criado_por) "
            "VALUES (%s, %s::uuid, %s, %s, %s, %s) "
            "RETURNING nome, titulo, corpo, versao, padrao, criado_em, atualizado_em",
            (auth.tenant_id, item_id, corpo.nome, corpo.titulo, jsonb(corpo_json), auth.usuario_id),
        )
        linha = cur.fetchone()
        registrar_evento(cur, request, "imagens/predefinicao_criar", "item", item_id, {"nome": corpo.nome})
    return _linha(linha)


@router.put("/api/imagens/{item_id}/predefinicoes/{nome}", openapi_extra=EDITAR)
def atualizar(item_id: str, nome: str, corpo: PredefinicaoEntrada, request: Request,
             auth: Auth = autenticado("conteudo.publicar_camada", escopo_token="imagens:ler")):
    if nome in pred.NOMES_FABRICA:
        raise ErroAPI(409, "nome_reservado", f"{nome!r} é uma predefinição de fábrica, não editável", {"nome": nome})
    if corpo.nome != nome:
        raise ErroAPI(422, "nome_imutavel", "o nome da predefinição não pode mudar num PUT; apague e recrie",
                      {"nome_na_url": nome, "nome_no_corpo": corpo.nome})
    corpo_json = _corpo_de(corpo)
    pred.validar_corpo(corpo_json)
    with db.db(auth.contexto()) as cur:
        item = _item_raster(cur, item_id)
        _checar_bandas_do_item(cur, auth, item, corpo_json)
        cur.execute(
            "UPDATE plat.render_predefinicao SET titulo = %s, corpo = %s "
            "WHERE tenant_id = %s AND item_id = %s::uuid AND nome = %s AND apagado_em IS NULL "
            "RETURNING nome, titulo, corpo, versao, padrao, criado_em, atualizado_em",
            (corpo.titulo, jsonb(corpo_json), auth.tenant_id, item_id, nome),
        )
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "predefinicao_inexistente", f"predefinição inexistente: {nome}", {"nome": nome})
        registrar_evento(cur, request, "imagens/predefinicao_atualizar", "item", item_id, {"nome": nome})
    return _linha(linha)


@router.delete("/api/imagens/{item_id}/predefinicoes/{nome}", status_code=204, openapi_extra=EDITAR)
def apagar(item_id: str, nome: str, request: Request,
          auth: Auth = autenticado("conteudo.publicar_camada", escopo_token="imagens:ler")):
    if nome in pred.NOMES_FABRICA:
        raise ErroAPI(409, "nome_reservado", f"{nome!r} é uma predefinição de fábrica, não apagável", {"nome": nome})
    with db.db(auth.contexto()) as cur:
        _item_raster(cur, item_id)
        cur.execute(
            "UPDATE plat.render_predefinicao SET apagado_em = now(), padrao = false "
            "WHERE tenant_id = %s AND item_id = %s::uuid AND nome = %s AND apagado_em IS NULL "
            "RETURNING nome",
            (auth.tenant_id, item_id, nome),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "predefinicao_inexistente", f"predefinição inexistente: {nome}", {"nome": nome})
        registrar_evento(cur, request, "imagens/predefinicao_apagar", "item", item_id, {"nome": nome})
    return None


@router.post("/api/imagens/{item_id}/predefinicoes/{nome}/tornar-padrao", openapi_extra=EDITAR)
def tornar_padrao(item_id: str, nome: str, request: Request,
                  auth: Auth = autenticado("conteudo.publicar_camada", escopo_token="imagens:ler")):
    """Marca `nome` como a predefinição padrão do item — a que resolve quando ninguém passa `predef=`/
    `STYLES=`/`renderingRule` nenhum. Fábrica pode virar padrão (não precisa existir na tabela: só grava
    o nome quando é CUSTOM; um padrão de fábrica é lido direto de `pred.FABRICA`, sem linha — ver
    `padrao_do_item`/`_predef_publicada` em rotas_tiles.py). Trocar o padrão NÃO apaga a predefinição
    anterior nem quebra uma URL que já a nomeia explicitamente (portão do item)."""
    with db.db(auth.contexto()) as cur:
        _item_raster(cur, item_id)
        if nome not in pred.NOMES_FABRICA:
            cur.execute(
                "SELECT 1 FROM plat.render_predefinicao WHERE tenant_id = %s AND item_id = %s::uuid "
                "AND nome = %s AND apagado_em IS NULL",
                (auth.tenant_id, item_id, nome),
            )
            if cur.fetchone() is None:
                raise ErroAPI(404, "predefinicao_inexistente", f"predefinição inexistente: {nome}", {"nome": nome})
        cur.execute(
            "UPDATE plat.render_predefinicao SET padrao = false "
            "WHERE tenant_id = %s AND item_id = %s::uuid AND padrao AND apagado_em IS NULL",
            (auth.tenant_id, item_id),
        )
        if nome not in pred.NOMES_FABRICA:
            cur.execute(
                "UPDATE plat.render_predefinicao SET padrao = true "
                "WHERE tenant_id = %s AND item_id = %s::uuid AND nome = %s AND apagado_em IS NULL",
                (auth.tenant_id, item_id, nome),
            )
        registrar_evento(cur, request, "imagens/predefinicao_tornar_padrao", "item", item_id, {"nome": nome})
    return {"item_id": item_id, "padrao": nome}


__all__ = ["router"]
