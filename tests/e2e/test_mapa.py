"""e2e /mapa (item L2-01-a-basemap-local-pmtiles): mapa-base local em MapLibre GL JS lendo PMTiles servido pelo
próprio nginx (sem Martin, sem chave de terceiro). Prova: o canvas WebGL desenha algo de verdade (captura real do
navegador com mais de uma cor — não é uma tela em branco), 0 erro de console, controles de navegação/escala/
coordenadas/seleção de camada base presentes e funcionando, nginx serve o PMTiles com Range (206) e sem gzip.
Captura em tests/e2e/capturas/L2-01-a-basemap-local-pmtiles_mapa.png."""

from pathlib import Path

import httpx
import pytest
from PIL import Image

from tests.e2e.apoio import Tela, local

ITEM = "L2-01-a-basemap-local-pmtiles"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _cores_distintas(caminho_png: Path) -> int:
    """Conta cores distintas na captura real (screenshot do navegador, não `readPixels` do WebGL: o MapLibre usa
    `preserveDrawingBuffer: false` por padrão — o navegador limpa o framebuffer depois de compor cada quadro, e
    `readPixels` chamado fora do próprio callback de render lia sempre zero, MEDIDO nesta suíte (canvas 1048×744,
    `distintos: 0`). O screenshot do Chromium compõe a página primeiro, então lê a tela de verdade). Mais de uma
    cor prova que o mapa desenhou algo — não é uma tela em branco."""
    with Image.open(caminho_png) as im:
        return len(im.convert("RGB").getcolors(maxcolors=2_000_000) or [])


def test_pmtiles_servido_com_range_e_sem_gzip(base_url, url_publica_resolve):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    r = httpx.get(f"{base_url}/static/dados/basemap/guarulhos.pmtiles", headers={"Range": "bytes=0-99"}, timeout=15,
                  verify=not local(base_url))
    assert r.status_code == 206, (r.status_code, dict(r.headers))
    assert r.headers.get("content-range", "").startswith("bytes 0-99/")
    assert "gzip" not in (r.headers.get("content-encoding") or "")
    assert len(r.content) == 100


def test_mapa_desenha_webgl_sem_erro(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa")

    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    # o mapa dispara 'load' antes de body[data-pronto=1] (mapa.js); mais uma volta de espera garante que os
    # tiles do primeiro quadro já pintaram (evita capturar o quadro do fundo só, ainda sem tile)
    page.wait_for_timeout(1500)

    # controles do portão: navegação (MapLibre), escala (MapLibre), coordenadas do cursor (nosso), camada base (nosso)
    assert page.locator(".maplibregl-ctrl-zoom-in").count() == 1
    assert page.locator(".maplibregl-ctrl-scale").count() == 1
    assert page.locator("#seletor-base option").count() >= 1
    coord_antes = page.text_content("#coordenadas").strip()
    assert coord_antes and coord_antes != "—"

    caixa = page.locator("#mapa").bounding_box()
    page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_timeout(200)
    coord_depois = page.text_content("#coordenadas").strip()
    assert "," in coord_depois and "z" in coord_depois, coord_depois

    # zoom por clique no controle de navegação muda o zoom mostrado nas coordenadas (MapLibre anima o zoomIn;
    # espera a condição, não um tempo fixo — a animação pode passar de 400 ms sob carga da máquina)
    zoom_antes = coord_depois.split("z")[-1]
    page.click(".maplibregl-ctrl-zoom-in")
    page.wait_for_function(
        "(zoomAntes) => (document.getElementById('coordenadas').textContent.split('z').pop() !== zoomAntes)",
        arg=zoom_antes,
        timeout=5000,
    )
    coord_zoom = page.text_content("#coordenadas").strip()
    assert coord_zoom.split("z")[-1] != zoom_antes, (coord_antes, coord_zoom)

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho_captura = CAPTURAS / f"{ITEM}_mapa.png"
    page.locator("#mapa").screenshot(path=str(caminho_captura))
    cores = _cores_distintas(caminho_captura)
    assert cores > 50, cores  # mais de 50 cores distintas = mapa desenhado, não uma tela em branco

    tela.verificar()  # 0 erro de console, 0 resposta >= 400 não esperada
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/apoio.py Tela.ir)")
    gravar("cores_distintas_na_captura", cores, "contagem",
           f"PIL Image.getcolors() sobre {caminho_captura.name} (screenshot do elemento #mapa)")
