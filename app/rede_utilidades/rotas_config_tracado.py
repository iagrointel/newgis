"""Rotas da configuração de traçado (item L4-02-e-configuracoes-de-tracado).

CRUD em `/api/rede/{rede_id}/config_tracado`: `POST` cria, `GET` lista, `GET /{id}` lê, `PUT /{id}` altera e
`DELETE /{id}` apaga. O uso da configuração está no endpoint de traçado que já existia — `POST
/api/rede/{rede_id}/tracar` com `config_id` —, nunca numa rota paralela: a configuração descreve um pedido
ao motor de sempre, não um segundo motor.

⛔ Nome do caminho: o portão do item dizia `/api/v1/rede/{id}/config_tracado`. O produto inteiro responde em
`/api/` sem versão na URL, e `tests/api/test_versionamento.py` reprova qualquer rota `/api/v1/...`
(docs/CONTRATO_API.md). Mesma decisão dos ADR 0019 §6 e 0020 §6, pelos mesmos motivos.

Escrita exige `rede.editar`; leitura segue a visibilidade por inquilino (RLS). O compartilhamento é DENTRO do
inquilino: `compartilhada=false` deixa a configuração visível só para quem a criou, e nenhuma das duas formas
atravessa a fronteira do inquilino."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import config_tracado
from app.rede_utilidades.modelos import ConfigTracado, ConfigTracadoEntrada, ConfigTracadoPagina

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — configuração de traçado"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 500


def _uuid_ok(valor: str, erro: str = "rede_inexistente", texto: str = "rede inexistente") -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, erro, texto) from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


@router.post("/{rede_id}/config_tracado", response_model=ConfigTracado, status_code=201,
             openapi_extra=EDITAR)
def criar_config(rede_id: str, corpo: ConfigTracadoEntrada, request: Request,
                 auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            ficha = config_tracado.criar(cur, auth.tenant_id, rid, corpo, auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/config_tracado_criar", "rede", rid,
                         {"codigo": ficha["codigo"], "tipo": ficha["tipo"]})
        return ficha


@router.get("/{rede_id}/config_tracado", response_model=ConfigTracadoPagina, openapi_extra=LER)
def listar_configs(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = config_tracado.listar(cur, rid, auth.usuario_id, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/config_tracado/{config_id}", response_model=ConfigTracado, openapi_extra=LER)
def ver_config(rede_id: str, config_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    cid = _uuid_ok(config_id, "config_inexistente", "configuração de traçado inexistente nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return config_tracado.obter(cur, rid, cid, auth.usuario_id)


@router.put("/{rede_id}/config_tracado/{config_id}", response_model=ConfigTracado, openapi_extra=EDITAR)
def alterar_config(rede_id: str, config_id: str, corpo: ConfigTracadoEntrada, request: Request,
                   auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    cid = _uuid_ok(config_id, "config_inexistente", "configuração de traçado inexistente nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            ficha = config_tracado.atualizar(cur, rid, cid, corpo, auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/config_tracado_alterar", "rede", rid,
                         {"codigo": ficha["codigo"], "tipo": ficha["tipo"]})
        return ficha


@router.delete("/{rede_id}/config_tracado/{config_id}", status_code=204, openapi_extra=EDITAR)
def apagar_config(rede_id: str, config_id: str, request: Request,
                  auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    cid = _uuid_ok(config_id, "config_inexistente", "configuração de traçado inexistente nesta rede")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        ficha = config_tracado.apagar(cur, rid, cid, auth.usuario_id)
        registrar_evento(cur, request, "redes/config_tracado_apagar", "rede", rid,
                         {"codigo": ficha["codigo"]})
    return None
