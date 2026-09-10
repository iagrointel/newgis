"""Ponte entre o compositor de layout e o motor de render do L2-12-a (item L2-12-b-layouts-elementos-exportacao).

O quadro de mapa é desenhado por uma página headless (`web/render_layout_mapa.html`) que NÃO tem sessão nem
cookie: ela recebe na URL um token interno de curta duração (HMAC sobre PLAT_SECRET, ≤ 60 s, só do próprio host —
`app/render/token.py`) com um payload assinado que diz QUAL inquilino/usuário e QUAIS camadas desenhar. A página
troca esse token pelo estilo MapLibre completo em `GET /api/render/layout/estilo`: o servidor cunha ali, sob o
contexto do inquilino do payload, um token de tile por camada (`camada:ler:<uuid>`, o mesmo mecanismo do
TileJSON do visualizador) e devolve as camadas de estilo da simbologia (`app/mapa/simbologia.py` — as MESMAS
cores da legenda, por construção). Nada do payload é confiado sem a assinatura; a rota também exige chamador
no host interno.

O worker (job `layout.exportar`) e a API (pré-visualização) usam a mesma função `render_quadro`: cada um roda o
seu próprio pool de chromium (`app/render/motor.py::motor()` é por processo)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

from app import db
from app.auth.sessao import sha256_hex
from app.layout.geometria import Quadro
from app.mapa import simbologia as simb_mod
from app.mapa.consultas import SQL_CAMADA
from app.render.motor import motor
from app.settings import settings

HORAS_TOKEN_TILE = 1
NOME_TOKEN_TILE = "layout-render"
TTL_TOKEN_S = 60


# ---------------------------------------------------------------- token interno com payload
def _assinar(exp: int, nonce: str, payload_b64: str) -> str:
    msg = f"{exp}.{nonce}.{payload_b64}".encode()
    return hmac.new(settings.PLAT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def gerar_token(dados: dict, prazo_s: int = TTL_TOKEN_S) -> str:
    """`<exp>.<nonce>.<payload>.<assinatura>` — payload JSON em base64url, assinado junto; TTL cortado a 60 s."""
    exp = int(time.time()) + max(1, min(prazo_s, TTL_TOKEN_S))
    nonce = secrets.token_hex(8)
    payload = base64.urlsafe_b64encode(json.dumps(dados, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{exp}.{nonce}.{payload}.{_assinar(exp, nonce, payload)}"


def ler_token(token: str) -> dict | None:
    """payload do token quando a assinatura confere e ainda vale; senão None (nunca exceção)."""
    if not token or token.count(".") != 3:
        return None
    exp_s, nonce, payload, assinatura = token.split(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if not hmac.compare_digest(assinatura, _assinar(exp, nonce, payload)):
        return None
    if time.time() > exp:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- estilo para a página headless
def _cunhar_token_tile(cur, tenant_id: int, usuario_id: int, camada_id: str) -> str:
    valor = "plat_" + secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, restricao, "
        "expira_em) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now() + make_interval(hours => %s))",
        (
            tenant_id,
            usuario_id,
            f"{NOME_TOKEN_TILE}:{camada_id}",
            sha256_hex(valor),
            valor[:12],
            [f"camada:ler:{camada_id}"],
            json.dumps({}),
            HORAS_TOKEN_TILE,
        ),
    )
    return valor


def ficha_camada(cur, camada_id: str) -> dict | None:
    """Ficha mínima da camada para o compositor e para o estilo: título, geometria, simbologia normalizada,
    legenda (mesma função do visualizador) e a função de tile."""
    cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (camada_id,))
    linha = cur.fetchone()
    if linha is None:
        return None
    dados = linha["dados"] or {}
    geometria = dados.get("geometria") or "Point"
    simb = simb_mod.normalizar(dados.get("simbologia"), geometria)
    tabela = dados.get("tabela") or ""
    funcao = ("t_" + tabela[2:]) if tabela.startswith("c_") else None
    return {
        "id": str(linha["id"]),
        "titulo": linha["titulo"],
        "geometria": geometria,
        "simbologia": simb,
        "legenda": simb_mod.legenda(simb, geometria),
        "dados": dados,
        "funcao": funcao,
        "esquema": dados.get("schema"),
    }


def estilo_para_mapa(cur, tenant_id: int, usuario_id: int, mapa: dict, base_url: str) -> dict:
    """Fontes vetoriais (tile via /tiles/... com token cunhado agora) + camadas de estilo, na ordem de desenho
    do mapa (a primeira da lista é a de cima, como no visualizador)."""
    fontes: dict = {}
    camadas: list[dict] = []
    avisos: list[str] = []
    ordem = [c for c in (mapa.get("camadas") or []) if c.get("visivel", True) is not False]
    # MapLibre desenha na ordem da lista: a última é a de cima. A lista do mapa tem a primeira em cima.
    for c in reversed(ordem):
        cid = str(c.get("camada_id") or c.get("id") or "")
        ficha = ficha_camada(cur, cid) if cid else None
        if not ficha or not ficha["funcao"] or not ficha["esquema"]:
            avisos.append(f"camada {cid} não é hospedada ou não existe; fora do quadro")
            continue
        token = _cunhar_token_tile(cur, tenant_id, usuario_id, cid)
        fonte = f"plat-{cid}"
        fontes[fonte] = {
            "type": "vector",
            "tiles": [f"{base_url}/tiles/{ficha['esquema']}/{ficha['funcao']}/{{z}}/{{x}}/{{y}}?token={token}"],
            "minzoom": 0,
            "maxzoom": 20,
        }
        estilo = simb_mod.camadas_maplibre(ficha["simbologia"], ficha["geometria"], fonte, fonte, ficha["funcao"])
        op = float(c.get("opacidade", 1.0))
        if op < 1.0:
            for cam in estilo:
                paint = cam.setdefault("paint", {})
                chave = {"circle": "circle-opacity", "line": "line-opacity", "fill": "fill-opacity"}.get(
                    cam.get("type")
                )
                if chave:
                    paint[chave] = float(paint.get(chave, 1.0)) * op
        camadas.extend(estilo)
    return {"fontes": fontes, "camadas": camadas, "base": mapa.get("base") or "osm-guarulhos", "avisos": avisos}


# ---------------------------------------------------------------- render do quadro pelo motor
def base_url_render() -> str:
    return (settings.PLAT_RENDER_BASE_URL or settings.PLAT_URL_PUBLICA).rstrip("/")


def url_da_pagina(quadro: Quadro, mapa: dict, elemento: dict, tenant_id: int, usuario_id: int) -> str:
    payload = {
        "t": tenant_id,
        "u": usuario_id,
        "b": mapa.get("base") or "osm-guarulhos",
        "c": [
            {
                "camada_id": str(c.get("camada_id") or c.get("id")),
                "opacidade": c.get("opacidade", 1.0),
                "visivel": c.get("visivel", True),
            }
            for c in (mapa.get("camadas") or [])
        ],
    }
    token = gerar_token(payload)
    q = {
        "token": token,
        "lng": f"{quadro.centro[0]:.8f}",
        "lat": f"{quadro.centro[1]:.8f}",
        "zoom": f"{quadro.zoom:.6f}",
        "rotacao": f"{float(elemento.get('rotacao') or 0.0):.3f}",
    }
    return f"{base_url_render()}/render/layout-mapa?{urlencode(q)}"


async def _renderizar(url: str, largura: int, altura: int) -> bytes:
    m = motor()
    if not m.ativo:
        await m.iniciar()
    dados, _ = await m.renderizar(url, largura=largura, altura=altura, formato="png", espera_timeout_ms=60000)
    return dados


def render_quadro(quadro: Quadro, mapa: dict, elemento: dict, tenant_id: int, usuario_id: int) -> bytes:
    """Síncrono para o job e para a rota (que já roda em thread do FastAPI quando é `def`)."""
    url = url_da_pagina(quadro, mapa, elemento, tenant_id, usuario_id)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_renderizar(url, quadro.largura_px, quadro.altura_px))
    # dentro de um loop (rota async): roda o motor num loop próprio em thread para não bloquear o servidor
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(_renderizar(url, quadro.largura_px, quadro.altura_px))).result()


def contexto_do_payload(payload: dict) -> db.Contexto:
    return db.Contexto(int(payload["t"]), int(payload["u"]), "render")
