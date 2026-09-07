"""Verificação de token para o Martin (item L2-01-b-martin-tiles-vetoriais).

O Martin (`GetTileWithQueryError`, martin-core/src/tiles/postgres/errors.rs) classifica QUALQUER erro do
Postgres na função de tile — inclusive `token_ausente`, `token_revogado`, `escopo_insuficiente` — como
`ErrorKind::Internal`, isto é, HTTP 500. Não há como o Martin devolver 401/403, nem hoje nem por
configuração (conferido no código-fonte da tag martin-v1.15.0; ver docs/adr/0023). Por isso a validação do
token acontece ANTES de o pedido chegar ao Martin, via `auth_request` do nginx apontando para esta rota.

Achado do adversário nesta rodada (registrado no ADR e na migração 20260907T0213): a primeira versão desta
rota recebia o `item` de QUERY PARAM do cliente. Um token AMPLO ("camada:ler", sem uuid — formato de token
de serviço/admin) de QUALQUER inquilino passava `plat.escopo_cobre` para QUALQUER item que o cliente
alegasse, porque `escopo_cobre` só compara o texto do próprio token; quem checava se o item pertencia ao
MESMO inquilino do token era, até então, só a função de tile lá dentro do Martin (hardcoded na criação por
`camada_tile_garantir`) — esta rota não tinha esse hardcode. Medido: token largo do inquilino B pedindo o
item do inquilino A autenticava com 200. Corrigido: o item (e portanto o inquilino esperado) NUNCA vem do
cliente — vem da TABELA que está no CAMINHO da própria URL (nginx repassa `$request_uri` original em
`X-Original-Uri`), resolvida no banco por `plat.item_da_tabela` (SECURITY DEFINER). Se o caminho não casar
com `t_<16 hex>`, ou a tabela não estiver no catálogo, a rota recusa com `tabela_nao_catalogada` — nunca
aceita um item arbitrário."""

import logging
import re

import psycopg2
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app import db_leitor

router = APIRouter()
log = logging.getLogger("plat.tiles")

_ESCOPO_INSUFICIENTE = "escopo_insuficiente"
_TABELA_NA_URL = re.compile(r"/(t_[0-9a-f]{16})(?:/|$)")


def _tabela_da_url(caminho: str) -> str | None:
    m = _TABELA_NA_URL.search(caminho or "")
    if not m:
        return None
    return "c_" + m.group(1)[2:]


@router.get("/internal/tiles/verificar", include_in_schema=False)
def verificar(request: Request, token: str | None = Query(default=None)):
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    origem = request.headers.get("origin") or request.headers.get("referer")
    caminho_original = request.headers.get("x-original-uri") or ""
    token = token or None
    tabela = _tabela_da_url(caminho_original)
    if tabela is None:
        log.info("tiles.verificar recusado motivo=tabela_nao_reconhecida caminho=%s", caminho_original)
        return Response(status_code=401, headers={"X-Motivo-Recusa": "tabela_nao_reconhecida"})
    try:
        with db_leitor.conexao_leitor() as cur:
            cur.execute("SELECT item_id, tenant_id FROM plat.item_da_tabela(%s)", (tabela,))
            linha = cur.fetchone()
            if linha is None:
                log.info("tiles.verificar recusado motivo=tabela_nao_catalogada tabela=%s", tabela)
                return Response(status_code=401, headers={"X-Motivo-Recusa": "tabela_nao_catalogada"})
            item_id, tenant_dono = linha["item_id"], linha["tenant_id"]
            cur.execute(
                "SELECT plat.contexto_por_token(%s, %s, %s, %s::uuid, 'camada:ler', '/tiles') AS tenant",
                (token, ip, origem, item_id),
            )
            ctx_tenant = cur.fetchone()["tenant"]
            # espelho EXATO do `IF ctx IS DISTINCT FROM tid` hardcoded na função de tile
            # (db/migracoes/20260906T1546_leitor_tiles.sql, plat.camada_tile_garantir): a escopo_cobre()
            # do banco só compara o TEXTO do token, nunca se o inquilino do token é DONO do item — um
            # token amplo ("camada:ler", sem uuid) de QUALQUER inquilino cobre qualquer item que se
            # alegue. Achado do adversário nesta rodada: sem esta comparação, o token largo do inquilino
            # B autenticava para o item do inquilino A com 204 (docs/adr/0023).
            if ctx_tenant != tenant_dono:
                log.info("tiles.verificar recusado motivo=tile_de_outro_inquilino tabela=%s", tabela)
                return Response(status_code=401, headers={"X-Motivo-Recusa": "tile_de_outro_inquilino"})
        return Response(status_code=204)
    except db_leitor.SemLeitorConfigurado:
        log.error("tiles.verificar: PLAT_DSN_LEITOR não configurado — falha fechada (503)")
        return Response(status_code=503, headers={"X-Motivo-Recusa": "leitor_nao_configurado"})
    except (psycopg2.pool.PoolError, psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
        # achado do adversário (200 pedidos em paralelo ao z0 da camada de 1 mi, docs/adr/0023): com a
        # piscina pequena demais, `getconn()` esgotava e a exceção (SEM `.diag`, não é erro do Postgres,
        # é erro do CLIENTE) caía no `except Exception` genérico abaixo e virava "token_invalido" — 401
        # por um motivo ERRADO, ainda que seguro (nunca deixava passar). Erro de infraestrutura é 503,
        # não recusa de autenticação; aumentar a piscina (1 a 10) resolveu a causa, isto é defesa extra.
        # Cuidado: psycopg2 mapeia a CLASSE de SQLSTATE 28 (invalid_authorization_specification — o
        # ERRCODE que `token_ausente`/`token_revogado` usam, migração 20260906T1546) para
        # `OperationalError` também — isso É uma recusa de autenticação legítima do banco, não uma falha
        # de infraestrutura, e tem `.diag` preenchido; só cai aqui quando NÃO tem `.diag` (erro real de
        # conexão/pool).
        if getattr(exc, "diag", None) is not None and getattr(exc.diag, "message_primary", None):
            motivo = _motivo(exc)
            status = 403 if motivo == _ESCOPO_INSUFICIENTE else 401
            log.info("tiles.verificar recusado motivo=%s", motivo)
            return Response(status_code=status, headers={"X-Motivo-Recusa": motivo})
        log.warning("tiles.verificar: piscina/conexão em erro (%s) — 503", exc.__class__.__name__)
        return Response(status_code=503, headers={"X-Motivo-Recusa": "leitor_indisponivel"})
    except Exception as exc:  # noqa: BLE001 — qualquer recusa do BANCO vira 401/403, nunca 500 aqui
        motivo = _motivo(exc)
        status = 403 if motivo == _ESCOPO_INSUFICIENTE else 401
        log.info("tiles.verificar recusado motivo=%s", motivo)
        return Response(status_code=status, headers={"X-Motivo-Recusa": motivo})


def _motivo(exc: Exception) -> str:
    """psycopg2 embrulha `RAISE EXCEPTION '%'` como diag.message_primary igual ao nome da exceção."""
    diag = getattr(exc, "diag", None)
    if diag is not None and getattr(diag, "message_primary", None):
        return diag.message_primary
    return "token_invalido"
