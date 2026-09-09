"""e2e /simbolos (item L2-02-e-simbolos-sprites-glifos): galeria carrega o sprite servido pela API, busca
filtra, escolher um ícone da galeria coloca um marcador no mapa (a cláusula literal do portão) e os glifos
embutidos (Noto Sans, servidos por app/simbolos/fontes.py) renderizam acento português — captura real do
navegador. Captura em tests/e2e/capturas/L2-02-e-simbolos-sprites-glifos_*.png."""
from pathlib import Path

import pytest
from PIL import Image

from tests.e2e.apoio import Tela, gravar_medidas

ITEM = "L2-02-e-simbolos-sprites-glifos"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _cores_distintas(caminho_png: Path) -> int:
    """Mesma técnica de tests/e2e/test_mapa.py: captura real do navegador (não readPixels do WebGL, que o
    MapLibre zera fora do callback de render). Mais de uma cor prova que algo foi desenhado."""
    with Image.open(caminho_png) as im:
        return len(im.convert("RGB").getcolors(maxcolors=2_000_000) or [])


def test_galeria_busca_e_coloca_icone_no_mapa(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, item=ITEM)
    # a base desta trilha não tem worker/fila/martin de pé (ambiente isolado por schema, ver
    # laco/trilha_ambiente.sh): /saude devolve 503 de propósito, e a página inicial (app.js) o busca no
    # meio do redirecionamento do login — nada disto é rota do item L2-02-e; é o mesmo 503 em qualquer e2e
    # desta trilha.
    tela.esperar_status(503)
    tela.entrar(slug, login, senha)
    tela.ir("/simbolos", "pagina_pronta_ms_simbolos")

    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    page.wait_for_selector(".simbolos-icone", timeout=20000)

    total_icones = page.locator(".simbolos-icone").count()
    assert total_icones >= 150, total_icones  # portão: >= 150 ícones próprios na galeria

    # busca por nome filtra a grade (cláusula "busca por nome e tema")
    page.fill("#busca", "raio")
    page.wait_for_function(
        "() => document.querySelectorAll('.simbolos-icone').length > 0 "
        "&& document.querySelectorAll('.simbolos-icone').length < 150"
    )
    filtrados = page.locator(".simbolos-icone").count()
    assert 0 < filtrados < total_icones, filtrados
    for span in page.locator(".simbolos-icone span").all_text_contents():
        assert "raio" in span

    page.fill("#busca", "")
    page.wait_for_function(f"() => document.querySelectorAll('.simbolos-icone').length >= {total_icones}")

    # a cláusula de e2e do portão: escolher ícone da galeria e ver no mapa
    assert page.locator(".maplibregl-marker").count() == 0
    page.locator(".simbolos-icone").first.click()
    page.wait_for_selector(".maplibregl-marker", timeout=5000)
    assert page.locator(".maplibregl-marker").count() == 1
    tela.capturar("icone_no_mapa")

    tela.verificar()
    gravar_medidas(medida, tela)


def test_glifos_noto_sans_renderizam_acento_portugues(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, item=ITEM)
    # a base desta trilha não tem worker/fila/martin de pé (ambiente isolado por schema, ver
    # laco/trilha_ambiente.sh): /saude devolve 503 de propósito, e a página inicial (app.js) o busca no
    # meio do redirecionamento do login — nada disto é rota do item L2-02-e; é o mesmo 503 em qualquer e2e
    # desta trilha.
    tela.esperar_status(503)
    tela.entrar(slug, login, senha)
    tela.ir("/simbolos", "pagina_pronta_ms_simbolos_glifos")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)

    # camada de texto de prova, usando o MESMO par sprite+glyphs desta tela (window.__platMapaSimbolos,
    # exposto só para este e2e — ver web/js/simbolos/galeria.js): confirma que a fonte embutida (Noto Sans,
    # servida por app/simbolos/fontes.py) tem os glifos acentuados, não só ASCII.
    page.evaluate(
        """(slug) => {
            const map = window.__platMapaSimbolos;
            map.addSource('prova-texto', {
              type: 'geojson',
              data: { type: 'FeatureCollection', features: [
                { type: 'Feature', geometry: { type: 'Point', coordinates: [-46.593018, -23.493476] },
                  properties: { rotulo: 'Nação, Água, Ímã, Coração, Codificação' } },
              ] },
            });
            map.addLayer({
              id: 'prova-texto-camada', type: 'symbol', source: 'prova-texto',
              layout: {
                'text-field': ['get', 'rotulo'],
                'text-font': ['Noto Sans Regular'],
                'text-size': 28,
              },
              paint: { 'text-color': '#ffffff', 'text-halo-color': '#000000', 'text-halo-width': 2 },
            });
        }""",
        slug,
    )
    page.wait_for_timeout(1200)  # carregamento assíncrono dos glifos (.pbf) + composição do quadro
    caminho = tela.capturar("glifos_acento_portugues")
    cores = _cores_distintas(caminho)
    assert cores > 1, f"captura sem texto desenhado (cores distintas: {cores})"
    tela.verificar()
