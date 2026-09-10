"""Portão do item L2-02-f-estilo-raster: o editor de estilo raster (RGB, banda única + rampa, NDVI por
expressão, percentil 2-98) gera parâmetros que abrem ladrilho de VERDADE no serviço de ladrilho do L1-02, com
captura por modo no MapLibre (`tests/e2e/apoio_estilo/harness_estilo_raster.html`), legenda com mín/máx reais
da cena (batem com `/estatisticas.json`, que é a mesma rota que o editor chama para propor o esticamento) e
estilo salvo/reaberto idêntico (cláusula de round-trip fica em `tests/api/catalogo/test_estilos.py`).

Diferença do harness vetorial (`tests/e2e/test_estilos_render.py`): lá a fonte é GeoJSON sintética por
`file://`; aqui a fonte é o ladrilho REAL, servido por um `uvicorn` da própria trilha na porta do item
(8248), porque MapLibre carrega raster com `img.crossOrigin='anonymous'` (textura WebGL) e isso exige uma
resposta HTTP de verdade com CORS — não dá para simular em JavaScript estático."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.estilos import compilador
from tests.api.imagens.apoio_raster import semear_raster

RAIZ = Path(__file__).resolve().parents[3]
HARNESS = (RAIZ / "tests" / "e2e" / "apoio_estilo" / "harness_estilo_raster.html").resolve()
CAPTURAS = RAIZ / "tests" / "e2e" / "capturas"
CAPTURAS.mkdir(parents=True, exist_ok=True)
PORTA = 8248
BASE = f"http://127.0.0.1:{PORTA}"


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a):
    return semear_raster(tenant_id_a, "estilo-raster")


@pytest.fixture(scope="module")
def token_tiles(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-estilo-raster", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def servidor_vivo():
    """`uvicorn` de verdade na porta do item (nunca `systemctl restart plat-api`, regra do brief comum):
    o navegador do playwright precisa de uma resposta HTTP real, com CORS, para usar o ladrilho como
    textura WebGL — a `TestClient` (transporte ASGI em processo) não é alcançável pelo Chromium."""
    env = dict(os.environ)
    # achado 07/09 (trilha_ambiente.sh c2c): `git_sha()` não lê o `.git` do worktree por baixo do
    # `uvicorn` (vira 500 em TUDO, inclusive `/saude`) — a variável precisa ir explícita no ambiente.
    env.setdefault(
        "PLAT_GIT_SHA",
        subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short=12", "HEAD"],
                       capture_output=True, text=True, check=True).stdout.strip(),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORTA), "--host", "127.0.0.1"],
        cwd=str(RAIZ), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        ok = False
        for _ in range(100):
            try:
                if httpx.get(f"{BASE}/saude", timeout=1).status_code == 200:
                    ok = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        if not ok:
            saida = proc.stdout.read() if proc.stdout else ""
            proc.terminate()
            pytest.skip(f"uvicorn da trilha não respondeu em 30s na porta {PORTA}: {saida[-2000:]}")
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _tile_url(token: str, item: str, consulta: dict) -> str:
    base = f"{BASE}/svc/{token}/raster/{item}/{{z}}/{{x}}/{{y}}.png"
    if consulta:
        import urllib.parse

        base += "?" + urllib.parse.urlencode(consulta)
    return base


def _bounds(servidor_vivo, token: str, item: str) -> list[float]:
    r = httpx.get(f"{BASE}/svc/{token}/raster/{item}/info.json", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["bounds"]


def _estatisticas(token: str, item: str, *, bandas=None, expressao=None) -> dict:
    params = {}
    if bandas:
        params["bandas"] = ",".join(str(b) for b in bandas)
    if expressao:
        params["expressao"] = expressao
    r = httpx.get(f"{BASE}/svc/{token}/raster/{item}/estatisticas.json", params=params, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _renderizar(page, url_tiles: str, bounds: list[float], nome: str):
    erros_console = []
    page.on("console", lambda m: erros_console.append(m.text) if m.type == "error" else None)
    cfg = {"url_tiles": url_tiles, "bounds": bounds, "opacidade": 1.0}
    page.add_init_script(script=f"window.ESTILO_RASTER_TESTE = {json.dumps(cfg)};")
    page.goto(f"file://{HARNESS}")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    erro_maplibre = page.get_attribute("body", "data-erro")
    assert erro_maplibre is None, f"{nome}: MapLibre reportou erro: {erro_maplibre}"
    assert erros_console == [], f"{nome}: erro de console: {erros_console}"

    canvas = page.query_selector(".maplibregl-canvas")
    assert canvas is not None
    box = canvas.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0

    destino = CAPTURAS / f"estilo_raster_{nome}.png"
    page.screenshot(path=str(destino))
    tamanho = destino.stat().st_size
    assert tamanho > 5000, f"{nome}: captura suspeita de estar em branco ({tamanho} B)"
    return destino


# ---------------------------------------------------------------- as 4 capturas do portão literal
def test_rgb_abre_tile_valido_e_renderiza(page, servidor_vivo, token_tiles, raster_demo):
    tok, item = token_tiles["token"], raster_demo["item_id"]
    est = _estatisticas(tok, item, bandas=[3, 2, 1])
    mn = min(est[b]["min"] for b in ("b1", "b2", "b3"))
    mx = max(est[b]["max"] for b in ("b1", "b2", "b3"))
    pc = {
        "tipo": "raster", "geometria": "raster", "versao": 1,
        "parametros_raster": {"bandas": [3, 2, 1], "rescale": [mn, mx], "esticamento": {"metodo": "minmax"}},
    }
    compilador.compilar(pc)  # compila sem erro (cláusula do modelo de estilo)
    consulta = compilador.parametros_tile(pc)
    url = _tile_url(tok, item, consulta)
    r = httpx.get(url.format(z=12, x=1503, y=2230), timeout=15)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and len(r.content) > 0, (r.status_code, len(r.content))
    _renderizar(page, url, _bounds(servidor_vivo, tok, item), "rgb")


def test_banda_unica_com_rampa_abre_tile_valido_e_renderiza(page, servidor_vivo, token_tiles, raster_demo):
    tok, item = token_tiles["token"], raster_demo["item_id"]
    est = _estatisticas(tok, item, bandas=[4])
    mn, mx = est["b4"]["min"], est["b4"]["max"]
    pc = {
        "tipo": "raster", "geometria": "raster", "versao": 1,
        "parametros_raster": {
            "bandas": [4], "colormap_name": "viridis", "rescale": [mn, mx],
            "esticamento": {"metodo": "minmax"},
        },
    }
    compilador.compilar(pc)
    consulta = compilador.parametros_tile(pc)
    url = _tile_url(tok, item, consulta)
    r = httpx.get(url.format(z=12, x=1503, y=2230), timeout=15)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and len(r.content) > 0

    # legenda: mín/máx que o editor mostraria batem com o que /estatisticas.json (TiTiler) devolveu de VERDADE
    leg = compilador.legenda_raster(pc)
    assert leg == {"colormap_name": "viridis", "min": mn, "max": mx}
    _renderizar(page, url, _bounds(servidor_vivo, tok, item), "banda_unica_rampa")


def test_ndvi_por_expressao_abre_tile_valido_e_renderiza(page, servidor_vivo, token_tiles, raster_demo):
    tok, item = token_tiles["token"], raster_demo["item_id"]
    pc = {
        "tipo": "raster", "geometria": "raster", "versao": 1,
        "parametros_raster": {
            "expression": "(b4-b3)/(b4+b3)", "colormap_name": "rdylgn", "rescale": [-1.0, 1.0],
            "esticamento": {"metodo": "nenhum"},
        },
    }
    compilador.compilar(pc)
    consulta = compilador.parametros_tile(pc)
    url = _tile_url(tok, item, consulta)
    r = httpx.get(url.format(z=12, x=1503, y=2230), timeout=15)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and len(r.content) > 0
    _renderizar(page, url, _bounds(servidor_vivo, tok, item), "ndvi")


def test_percentil_2_98_abre_tile_valido_e_legenda_bate_com_estatisticas(page, servidor_vivo, token_tiles, raster_demo):
    tok, item = token_tiles["token"], raster_demo["item_id"]
    est = _estatisticas(tok, item, bandas=[4])
    p2, p98 = est["b4"]["percentil_2"], est["b4"]["percentil_98"]
    assert p2 < p98
    pc = {
        "tipo": "raster", "geometria": "raster", "versao": 1,
        "parametros_raster": {
            "bandas": [4], "colormap_name": "viridis", "rescale": [p2, p98],
            "esticamento": {"metodo": "percentil_2_98"},
        },
    }
    compilador.compilar(pc)
    consulta = compilador.parametros_tile(pc)
    url = _tile_url(tok, item, consulta)
    r = httpx.get(url.format(z=12, x=1503, y=2230), timeout=15)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG" and len(r.content) > 0

    leg = compilador.legenda_raster(pc)
    assert leg["min"] == p2 and leg["max"] == p98, "legenda tem de citar exatamente o que /estatisticas.json mediu"
    _renderizar(page, url, _bounds(servidor_vivo, tok, item), "percentil")
