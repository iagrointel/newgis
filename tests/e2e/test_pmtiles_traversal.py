"""HARD-03 — adversário L2-01-a-basemap-local-pmtiles: a location do nginx que serve o PMTiles usa `alias` com
captura nomeada `(?<arquivo>[^/]+\\.pmtiles)$`. `alias` + regex sem captura é a armadilha clássica de travessia;
aqui a captura só aceita um nome sem barra. Este teste bate a origem com tentativas de travessia e exige que
NENHUMA sirva arquivo fora de web/dados/basemap, e que o .pmtiles legítimo responda 200/206. Contra a URL pública
o cabeçalho vem do nginx real; contra o nginx renderizado de deploy/nginx.conf, do modelo. `-m lento`."""

import httpx
import pytest

ALVOS = [
    "/static/dados/basemap/guarulhos.pmtiles",  # legítimo: 200/206
]
TRAVESSIAS = [
    "/static/dados/basemap/../../../etc/passwd",
    "/static/dados/basemap/..%2f..%2f..%2fetc%2fpasswd",
    "/static/dados/basemap/%2e%2e/%2e%2e/settings.py",
    "/static/dados/basemap/guarulhos.pmtiles/../../../app/settings.py",
    "/static/dados/basemap/....//....//app/main.py",
    "/static/dados/basemap/.pmtiles",
    "/static/dados/basemap/x.pmtiles",  # inexistente: 404, nunca 200 de outro arquivo
]


@pytest.mark.lento
def test_pmtiles_legitimo_responde(base_url):
    r = httpx.get(f"{base_url}{ALVOS[0]}", timeout=20)
    assert r.status_code in (200, 206), (r.status_code, r.text[:120])
    assert r.headers.get("content-type", "").startswith(("application/", "binary")) or r.content[:2] == b"PM", r.headers


@pytest.mark.lento
@pytest.mark.parametrize("caminho", TRAVESSIAS)
def test_pmtiles_travessia_nunca_serve_arquivo_de_fora(base_url, caminho):
    r = httpx.get(f"{base_url}{caminho}", timeout=20, follow_redirects=False)
    assert r.status_code in (400, 403, 404), (caminho, r.status_code, r.text[:120])
    corpo = r.content[:4000]
    for agulha in (b"root:x:", b"PLAT_SECRET", b"def carregar", b"FastAPI", b"password"):
        assert agulha not in corpo, (caminho, agulha)
