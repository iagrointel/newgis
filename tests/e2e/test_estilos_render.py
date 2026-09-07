"""E2E do item L2-02-a-modelo-estilo: os documentos de exemplo (`tests/estilos/*.json`) desenham de
verdade no MapLibre vendorizado (o mesmo `web/vendor/maplibre-gl-4.7.1.js` que a tela de mapa usa),
com captura por tipo em `tests/e2e/capturas/`. Roda inteiramente por `file://` sobre um arnês estático
(`tests/e2e/apoio_estilo/harness_estilo.html`) — não depende do backend nem do item L2-01-mapa-web
(ainda não juntado) estar no ar. O tipo `raster` fica fora daqui (sem servidor de tile na bancada de
teste; ver `docs/PARIDADE.md`); os 6 restantes são os que o portão pede."""

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "estilos"
HARNESS = (Path(__file__).parent / "apoio_estilo" / "harness_estilo.html").resolve()
CAPTURAS = Path(__file__).parent / "capturas"
CAPTURAS.mkdir(exist_ok=True)

TIPOS_E2E = ("unico", "categoria", "classes", "proporcional", "calor", "agrupamento")


@pytest.mark.parametrize("nome", TIPOS_E2E)
def test_estilo_de_exemplo_renderiza_no_maplibre(page, nome):
    doc = json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))
    erros_console = []
    page.on("console", lambda m: erros_console.append(m.text) if m.type == "error" else None)
    page.add_init_script(script=f"window.ESTILO_TESTE = {json.dumps(doc)};")
    page.goto(f"file://{HARNESS}")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    erro_maplibre = page.get_attribute("body", "data-erro")
    assert erro_maplibre is None, f"{nome}: MapLibre reportou erro: {erro_maplibre}"
    assert erros_console == [], f"{nome}: erro de console: {erros_console}"

    canvas = page.query_selector(".maplibregl-canvas")
    assert canvas is not None
    box = canvas.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0

    destino = CAPTURAS / f"estilo_{nome}.png"
    page.screenshot(path=str(destino))
    assert destino.stat().st_size > 5000, f"{nome}: captura suspeita de estar em branco ({destino.stat().st_size} B)"


def test_legenda_e_mapa_usam_a_mesma_cor_no_navegador(page):
    """A cor que o MapLibre REALMENTE pintou (lida de volta com `getPaintProperty`, não o JSON estático
    que mandamos) bate com a entrada de legenda que `app/estilos/compilador.legenda` calcula do MESMO
    `plat_construtor` — a mesma disciplina de prova do item L2-01-mapa-web
    (`test_legenda_mostra_as_cores_que_o_mapa_pinta`), agora para o vocabulário completo do construtor."""
    from app.estilos import compilador

    doc = json.loads((FIXTURES / "categoria.json").read_text(encoding="utf-8"))
    pc = doc["corpo"]["plat_construtor"]
    legenda = compilador.legenda(pc)

    page.add_init_script(script=f"window.ESTILO_TESTE = {json.dumps(doc)};")
    page.goto(f"file://{HARNESS}")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)

    cor_pintada = page.evaluate("() => window.mapaEstilo.getPaintProperty('camada', 'fill-color')")
    # a expressão pintada é o "case" inteiro (["case", teste0, cor0, ..., corN]); as cores dela, na
    # ordem, são exatamente a mesma lista que a legenda mostra — não duas fontes de cor, uma só.
    cores_no_case = cor_pintada[2::2] + [cor_pintada[-1]]
    assert cores_no_case == [c["cor"] for c in legenda]
    assert legenda[0]["cor"] == pc["categorias"][0]["cor"]
