"""Cliente HTTP para o Martin (item L2-04-e). O Martin (`deploy/martin.yaml`, item L2-01-b) publica
uma fonte por FUNÇÃO de tile com `source_id_format: "{function}"` — conferido no processo real
(`martin-v1.15.0 --config ...`, log `Auto-publishing functions`): o `source_id` é o nome puro da
função (`t_<16 hex>`), sem o schema, porque o nome já é globalmente único (16 hex aleatórios por
camada). O tile em si é `GET /<funcao>/<z>/<x>/<y>` com `token`/`item` na query string — o Martin
repassa TODA a query string ao 4º parâmetro `query_params::json` da função (comportamento medido
em 07/09, `docs/adr/20260907T1400-vector-tile-server-contratos.md`)."""

from __future__ import annotations

import os

import httpx

from app.erros import ErroAPI
from app.settings import settings

_TIMEOUT_S = 8.0


def base_url() -> str:
    """URL base do Martin (sem barra final). `PLAT_MARTIN_TILES_URL` tem prioridade (produção pode
    querer separar o endereço de checagem de saúde do de tiles); na falta dela, deriva de
    `PLAT_MARTIN_URL` (usado hoje só para `/health`, ver `app/tiles/rotas.py`/ADR 20260907T0235)
    removendo o sufixo `/health`; sem nenhuma das duas, o padrão de produção do `martin.yaml`
    (`listen_addresses: 127.0.0.1:8151`)."""
    direta = os.environ.get("PLAT_MARTIN_TILES_URL")
    if direta:
        return direta.rstrip("/")
    saude = settings.PLAT_MARTIN_URL
    if saude:
        return saude.rstrip("/").removesuffix("/health")
    return "http://127.0.0.1:8151"


def tile_mvt(funcao: str, z: int, x: int, y: int, *, token: str, item: str) -> tuple[bytes, int]:
    """(bytes, status). 204 sem corpo = tile vazio (fora da cobertura); 401/403 quando o Martin
    devolve algo != 200/204 — na prática o Martin nunca dá 401/403 de verdade (ADR 20260907T0235:
    `GetTileWithQueryError` classifica todo erro do Postgres como 500), então esta função só
    existe para quem JÁ passou pela autorização própria da aplicação (`app.tiles.autorizacao`) e
    quer os BYTES do tile; um 500 aqui é falha de infraestrutura (502 para o cliente), não recusa."""
    url = f"{base_url()}/{funcao}/{z}/{x}/{y}"
    try:
        r = httpx.get(url, params={"token": token, "item": item}, timeout=_TIMEOUT_S)
    except httpx.HTTPError as e:
        raise ErroAPI(502, "martin_indisponivel", f"não foi possível falar com o Martin: {e}") from e
    if r.status_code not in (200, 204):
        raise ErroAPI(502, "martin_erro", f"o Martin devolveu {r.status_code} para o tile", {"corpo": r.text[:300]})
    return r.content, r.status_code
