"""e2e da galeria de mapas base (item L2-01-e-mapas-base): a tela /mapa instala as fontes abertas padrão na
primeira visita, desenha cada uma de verdade no canvas WebGL, troca de mapa base sem perder as camadas
operacionais nem a extensão, e mostra a atribuição exigida pelas licenças (ODbL 1.0 / CC BY-SA 2.0 /
Copernicus) tanto na tela quanto na impressão.

Como o L2-01-a: precisa da URL pública com nginx na frente (é o nginx que serve `/static` e o PMTiles por
Range). Nas bases por trilha `PLAT_URL_PUBLICA` é `https://trilha-<nome>.invalido` de propósito
(`laco/trilha_ambiente.sh`) e a suíte SALTA — o e2e roda em homologação/instalação real, onde há nginx.

Capturas em tests/e2e/capturas/L2-01-e-mapas-base_<tipo>.png, uma por mapa base (cláusula do portão
"galeria com >= 3 mapas base funcionando por e2e (captura de cada)")."""

from pathlib import Path

import httpx
import pytest
from PIL import Image

from tests.e2e.apoio import Tela

ITEM = "L2-01-e-mapas-base"          # prefixo das capturas
MEDIDA = "L2-01-e"                   # arquivo de medidas nomeado no portao do item
CAPTURAS = Path(__file__).resolve().parent / "capturas"
MINIMO_DE_BASES = 3  # portão do item

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

# camada operacional de prova: um ponto GeoJSON embutido, sem depender de nenhum dado de inquilino nem de
# nenhum outro item. O que se prova não é a camada, é ela SOBREVIVER ao setStyle da troca de mapa base.
CAMADA_PROVA = {
    "sourceId": "zt-operacional",
    "sourceDef": {
        "type": "geojson",
        "data": {"type": "Feature", "properties": {},
                 "geometry": {"type": "Point", "coordinates": [-46.593018, -23.493476]}},
    },
    "layerDef": {"id": "zt-operacional-ponto", "type": "circle", "source": "zt-operacional",
                 "paint": {"circle-radius": 8, "circle-color": "#ff00ff"}},
}


def _cores_distintas(caminho_png: Path) -> int:
    """Idem test_mapa.py: o screenshot do Chromium compõe a página, logo lê o canvas de verdade (readPixels
    fora do callback de render lê zero — MapLibre usa preserveDrawingBuffer: false)."""
    with Image.open(caminho_png) as im:
        return len(im.convert("RGB").getcolors(maxcolors=2_000_000) or [])


def test_pmtiles_do_mapa_base_com_range_206_e_sem_gzip(base_url, url_publica_resolve, medida):
    """Cláusula 'PMTiles do mapa base servido com Range 206 (teste HTTP) e gzip desligado'. O PMTiles do
    item L2-01-a é a fonte 1 da galeria; sem 206 o navegador baixaria os 18 MiB inteiros por ladrilho."""
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina (base por trilha, sem nginx)")
    url = f"{base_url}/static/dados/basemap/guarulhos.pmtiles"
    r = httpx.get(url, headers={"Range": "bytes=0-99"}, timeout=15)
    assert r.status_code == 206, (r.status_code, dict(r.headers))
    assert r.headers.get("content-range", "").startswith("bytes 0-99/")
    assert "gzip" not in (r.headers.get("content-encoding") or "")
    assert len(r.content) == 100
    inteiro = int(r.headers["content-range"].split("/")[-1])
    medida(MEDIDA)("pmtiles_bytes_no_servidor", inteiro, "bytes", f"Content-Range de GET {url} com Range: bytes=0-99")


def test_galeria_desenha_troca_preserva_e_atribui(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa")
    page.wait_for_selector("body[data-pronto='1']", timeout=30000)

    galeria = page.evaluate(
        "() => window.platMapa.galeria.map((b) => ({id: b.id, tipo: b.dados.tipo, titulo: b.titulo}))"
    )
    assert len(galeria) >= MINIMO_DE_BASES, galeria

    # camada operacional montada por cima do mapa base atual
    page.evaluate("(c) => window.platMapa.adicionarCamadaOperacional(window.platMapa.map, c)", CAMADA_PROVA)
    assert page.evaluate("() => !!window.platMapa.map.getLayer('zt-operacional-ponto')")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    gravar = medida(MEDIDA)
    gravar("mapas_base_na_galeria", len(galeria), "contagem", "window.platMapa.galeria.length em /mapa")

    for base in galeria:
        page.select_option("#seletor-base", base["id"])
        page.wait_for_function("() => window.platMapa.map.isStyleLoaded()", timeout=20000)
        page.wait_for_timeout(1500)  # deixa o primeiro quadro com tiles pintar antes da captura

        # a camada operacional sobreviveu ao setStyle da troca
        assert page.evaluate("() => !!window.platMapa.map.getLayer('zt-operacional-ponto')"), base
        # e a extensão também (mesmo centro/zoom, dentro da tolerância de projeção do jumpTo)
        pos = page.evaluate(
            "() => ({lng: window.platMapa.map.getCenter().lng, lat: window.platMapa.map.getCenter().lat,"
            " z: window.platMapa.map.getZoom()})"
        )
        assert abs(pos["lng"] - (-46.593018)) < 0.01 and abs(pos["lat"] - (-23.493476)) < 0.01, (base, pos)

        caminho = CAPTURAS / f"{ITEM}_{base['tipo']}.png"
        page.locator("#mapa").screenshot(path=str(caminho))
        cores = _cores_distintas(caminho)
        minimo = 2 if base["tipo"] == "nenhum" else 20  # 'nenhum' é fundo cor sólida + a camada de prova
        assert cores >= minimo, (base, cores)
        gravar(f"cores_distintas_{base['tipo']}", cores, "contagem",
               f"PIL Image.getcolors() sobre {caminho.name} (screenshot do #mapa com o mapa base {base['tipo']})")

        # atribuição visível no DOM enquanto a fonte tem crédito a dar
        atrib = page.text_content(".maplibregl-ctrl-attrib") or ""
        if base["tipo"] != "nenhum":
            assert "OpenStreetMap" in atrib or "Copernicus" in atrib or "Sentinel" in atrib, (base, atrib)

    # atribuição na IMPRESSÃO: com media=print o CSS do item esconde o chrome mas mantém o crédito
    page.select_option("#seletor-base", galeria[0]["id"])
    page.wait_for_function("() => window.platMapa.map.isStyleLoaded()", timeout=20000)
    page.emulate_media(media="print")
    assert page.locator(".maplibregl-ctrl-attrib").is_visible(), "atribuição sumiu na impressão"
    assert "OpenStreetMap" in (page.text_content(".maplibregl-ctrl-attrib") or "")
    assert not page.locator(".mapa-painel-base").is_visible()
    page.emulate_media(media="screen")

    tela.verificar()  # 0 erro de console, 0 resposta >= 400 não esperada
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/apoio.py Tela.ir)")
