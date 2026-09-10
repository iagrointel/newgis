"""O appliance não pode depender de nada fora da instalação (item L7-11-b-appliance-sem-internet; L7_CONCEITO
C13 e o achado do adversário T1: Swagger UI vindo de CDN). Trava estática, lida dos arquivos: nenhum HTML/JS/
CSS servido pelo produto (fora de `web/vendor/`, que é código de terceiro vendorizado e conferido por sha256 em
`VERSOES.txt`) carrega recurso por `http(s)://`; nenhum `@import url(...)`/`url(http...)` em CSS; as fontes de
letra e as bibliotecas (MapLibre, PMTiles, DOMPurify, Swagger UI) existem em `web/vendor/`; o mapa-base é um
PMTiles local em `web/dados/basemap/`; o Swagger é servido de `/static/vendor/`. A prova dinâmica (e2e inteiro
atrás de um proxy que só deixa passar a própria instalação) é `scripts/appliance_offline_medir.py`."""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "web"
# atributos/chamadas que fazem o navegador BUSCAR alguma coisa; xmlns e comentários com URL não contam
RE_CARGA = re.compile(
    r"""(?:src|href|action|poster|data-src)\s*=\s*["']https?://|url\(\s*["']?https?://|@import\s+["']?https?://|"""
    r"""(?:fetch|import|open|XMLHttpRequest)\s*\(\s*["'`]https?://""",
    re.I,
)
EXCECOES_TEXTO = ("xmlns", "w3.org/2000/svg", "w3.org/1999/xlink")


def _arquivos_da_tela():
    for ext in ("*.html", "*.js", "*.css"):
        for arq in WEB.rglob(ext):
            if "vendor" in arq.parts or "node_modules" in arq.parts:
                continue
            yield arq


def test_nenhum_html_js_css_carrega_recurso_externo():
    ofensas = []
    for arq in _arquivos_da_tela():
        for n, linha in enumerate(arq.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if RE_CARGA.search(linha) and not any(e in linha for e in EXCECOES_TEXTO):
                ofensas.append(f"{arq.relative_to(RAIZ)}:{n}: {linha.strip()[:120]}")
    assert not ofensas, "\n".join(ofensas)


def test_bibliotecas_e_fontes_vendorizadas_e_conferidas():
    vendor = WEB / "vendor"
    versoes = (vendor / "VERSOES.txt").read_text(encoding="utf-8")
    for nome in ("maplibre-gl", "pmtiles", "dompurify", "swagger-ui-bundle", "swagger-ui-", "ibm-plex-sans",
                 "ibm-plex-mono-regular", "big-shoulders-display"):
        assert any(a.name.startswith(nome) for a in vendor.iterdir()), f"{nome} não vendorizado em web/vendor"
    for arq in vendor.iterdir():
        if arq.name != "VERSOES.txt":
            assert arq.name in versoes, f"{arq.name} sem sha256 em web/vendor/VERSOES.txt"


def test_mapa_base_local_e_swagger_local():
    basemap = list((WEB / "dados" / "basemap").glob("*.pmtiles"))
    assert basemap, "sem PMTiles local em web/dados/basemap (item L2-01-a)"
    mapa_js = (WEB / "js" / "mapa" / "mapa.js").read_text(encoding="utf-8")
    assert "pmtiles://" in mapa_js or "pmtiles" in mapa_js
    assert "tile.openstreetmap" not in mapa_js and "basemaps.cartocdn" not in mapa_js
    main = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    assert '"/static/vendor/swagger-ui-bundle' in main and "cdn.jsdelivr" not in main and "unpkg.com" not in main
