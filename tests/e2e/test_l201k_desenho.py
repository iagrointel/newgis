"""e2e da camada de desenho e anotações do mapa (item L2-01-k-desenho-anotacoes): os 7 tipos de desenho
criados na tela de verdade (chromium do playwright), salvos no documento e reabertos idênticos (comparação
do GeoJSON), texto com halo, "promover a camada" com a mesma contagem e geometrias válidas, e refutação do
item (polígono auto-intersectante, círculo no polo, texto de 10 mil caracteres — 0 erro de console em tudo).

Depende de `/mapa` responder (item L2-01-mapa-web) e do terra-draw vendorizado carregar."""

import json
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

ITEM = "L2-01-k-desenho-anotacoes"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa_desenho")
    page.wait_for_function("window.plat && window.plat.mapa && window.plat.mapa.desenho", timeout=15000)
    return tela


def _clicar_no_mapa(page, x=640, y=380):
    canvas = page.locator("#mapa canvas")
    box = canvas.bounding_box()
    page.mouse.click(box["x"] + x - 640 + box["width"] / 2, box["y"] + y - 380 + box["height"] / 2)


def _desenhar_ponto(page, dx=0, dy=0):
    page.click('[data-desenho="ponto"]')
    _clicar_no_mapa(page, 640 + dx, 380 + dy)


def _desenhar_linha(page):
    page.click('[data-desenho="linha"]')
    _clicar_no_mapa(page, 600, 350)
    _clicar_no_mapa(page, 700, 400)
    page.keyboard.press("Enter")


def _desenhar_poligono(page, deslocamento=0):
    page.click('[data-desenho="poligono"]')
    _clicar_no_mapa(page, 560 + deslocamento, 300)
    _clicar_no_mapa(page, 620 + deslocamento, 300)
    _clicar_no_mapa(page, 590 + deslocamento, 340)
    _clicar_no_mapa(page, 560 + deslocamento, 300)
    page.keyboard.press("Enter")


def _desenhar_retangulo(page):
    page.click('[data-desenho="retangulo"]')
    canvas = page.locator("#mapa canvas")
    box = canvas.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx - 120, cy - 120)
    page.mouse.down()
    page.mouse.move(cx - 40, cy - 40, steps=5)
    page.mouse.up()


def test_sete_tipos_desenham_e_contam(mapa, page):
    _desenhar_ponto(page)
    _desenhar_linha(page)
    _desenhar_poligono(page)
    _desenhar_retangulo(page)

    page.once("dialog", lambda d: d.accept("300"))
    page.click('[data-desenho="circulo"]')
    _clicar_no_mapa(page, 500, 500)
    page.wait_for_timeout(150)

    page.once("dialog", lambda d: d.accept("texto de teste com halo"))
    page.click('[data-desenho="texto"]')
    _clicar_no_mapa(page, 450, 450)
    page.wait_for_timeout(150)

    _desenhar_linha(page)  # base da seta: reusa o modo linha e marca tipo_desenho na hora do clique abaixo
    page.click('[data-desenho="seta"]')
    _clicar_no_mapa(page, 800, 300)
    _clicar_no_mapa(page, 850, 260)
    page.keyboard.press("Enter")

    n = page.evaluate("window.plat.mapa.desenho.lista().length")
    tipos = page.evaluate("window.plat.mapa.desenho.lista().map(f => f.properties.tipo_desenho)")
    assert n == 7, tipos
    assert set(tipos) == {"ponto", "linha", "poligono", "retangulo", "circulo", "texto", "seta"}
    tela = mapa
    tela.capturar("sete_tipos")
    tela.verificar()


def test_texto_com_halo_renderizado(mapa, page):
    page.once("dialog", lambda d: d.accept("halo visível"))
    page.click('[data-desenho="texto"]')
    _clicar_no_mapa(page, 640, 380)
    page.wait_for_timeout(150)
    halo = page.evaluate(
        "window.plat.mapa.map.getPaintProperty('plat-desenho-texto', 'text-halo-width')"
    )
    assert halo and halo > 0
    campo = page.evaluate("window.plat.mapa.map.getLayoutProperty('plat-desenho-texto', 'text-field')")
    assert campo == ["get", "texto"]


def test_salvar_e_reabrir_identico(mapa, page, base_url):
    _desenhar_ponto(page)
    _desenhar_poligono(page, deslocamento=40)
    antes = page.evaluate("JSON.stringify(window.plat.mapa.desenho.lista())")
    page.click("#btn-desenho-salvar")
    page.wait_for_function("window.plat.mapa.mapaId", timeout=10000)
    mapa_id = page.evaluate("window.plat.mapa.mapaId")

    page.goto(f"{base_url}/mapa?mapa={mapa_id}", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_function("window.plat && window.plat.mapa && window.plat.mapa.desenho.lista().length > 0",
                           timeout=15000)
    depois = page.evaluate("JSON.stringify(window.plat.mapa.desenho.lista())")

    a = sorted(json.loads(antes), key=lambda f: f["id"])
    b = sorted(json.loads(depois), key=lambda f: f["id"])
    assert len(a) == len(b) == 2
    for fa, fb in zip(a, b, strict=True):
        assert fa["id"] == fb["id"]
        assert fa["geometry"] == fb["geometry"]
        assert fa["properties"]["tipo_desenho"] == fb["properties"]["tipo_desenho"]
        assert fa["properties"]["estilo"] == fb["properties"]["estilo"]
    mapa.capturar("salvar_reabrir")
    mapa.verificar()


def test_promover_a_camada(mapa, page):
    _desenhar_ponto(page)
    _desenhar_poligono(page)
    page.click("#btn-desenho-salvar")
    page.wait_for_function("window.plat.mapa.mapaId", timeout=10000)

    page.once("dialog", lambda d: d.accept("camada e2e do desenho"))
    page.click("#btn-desenho-promover")
    page.wait_for_function(
        "document.getElementById('desenho-saida').textContent.includes('camada e2e do desenho')", timeout=15000
    )
    saida = page.text_content("#desenho-saida")
    assert "2" in saida  # 2 feições promovidas
    mapa.verificar()


def test_apagar_e_mover_na_lista(mapa, page):
    _desenhar_ponto(page)
    _desenhar_ponto(page, dx=40)
    itens = page.locator("#lista-desenho li")
    assert itens.count() == 2
    primeiro_id = page.evaluate("window.plat.mapa.desenho.lista()[0].id")
    page.locator(f'li[data-desenho="{primeiro_id}"] button[aria-label="apagar"]').click()
    assert page.evaluate("window.plat.mapa.desenho.lista().length") == 1
    mapa.verificar()


def test_texto_de_10_mil_caracteres_e_rejeitado_pelo_servidor(mapa, page):
    """Refutação do item: texto de 10 mil+ caracteres não entra (o cliente barra em desenho.js; o
    servidor barra de novo em app/catalogo/documento.py::erros_de_desenho — a prova do servidor está em
    tests/api/catalogo/test_desenho_anotacoes.py::test_texto_com_10001_caracteres_e_422)."""
    grande = "x" * 10001
    page.once("dialog", lambda d: d.accept(grande))
    page.click('[data-desenho="texto"]')
    _clicar_no_mapa(page, 640, 380)
    page.wait_for_timeout(200)
    assert page.evaluate("window.plat.mapa.desenho.lista().length") == 0
    mapa.verificar()


def test_editar_vertice_e_salvar_mantem_id_e_estilo(mapa, page):
    """Cláusula 'editados' do portão: a feição vai para o modo de edição do terra-draw (mover, arrastar
    vértice, apagar vértice), volta com o MESMO id/propriedades e a geometria alterada."""
    _desenhar_poligono(page)
    antes = page.evaluate("window.plat.mapa.desenho.lista()[0]")
    fid = antes["id"]
    assert page.evaluate(f"window.plat.mapa.desenho.editar({fid!r})") is True
    assert page.evaluate("window.plat.mapa.desenho.editando()") == fid

    canvas = page.locator("#mapa canvas")
    box = canvas.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.click(cx - 80, cy - 80)  # seleciona a feição emprestada ao terra-draw
    page.wait_for_timeout(150)
    page.mouse.move(cx - 80, cy - 80)
    page.mouse.down()
    page.mouse.move(cx - 40, cy - 30, steps=8)  # arrasta o vértice
    page.mouse.up()
    page.wait_for_timeout(150)

    page.evaluate("window.plat.mapa.desenho.terminarEdicao()")
    assert page.evaluate("window.plat.mapa.desenho.editando()") is None
    depois = page.evaluate("window.plat.mapa.desenho.lista()[0]")
    assert depois["id"] == fid
    assert depois["properties"]["tipo_desenho"] == "poligono"
    assert depois["properties"]["estilo"] == antes["properties"]["estilo"]
    assert depois["geometry"]["type"] == "Polygon"
    assert depois["geometry"] != antes["geometry"], "arrastar o vértice tinha de mudar a geometria"
    mapa.verificar()


def test_encaixe_10px_cai_no_vertice_da_feicao_alvo(mapa, page):
    """Cláusula de snapping do portão, medida em PIXELS na tela de verdade: com o encaixe ligado, um clique a
    menos de 10 px de um vértice devolve a coordenada EXATA daquele vértice; a 25 px, não devolve nada."""
    _desenhar_poligono(page)
    page.check("#desenho-snap")
    alvo = page.evaluate("window.plat.mapa.desenho.lista()[0].geometry.coordinates[0][0]")
    pixel = page.evaluate(
        "(c) => { const p = window.plat.mapa.map.project({lng: c[0], lat: c[1]}); return [p.x, p.y]; }", alvo)
    perto = page.evaluate("([x, y]) => window.plat.mapa.desenho.encaixar(x + 6, y + 4)", pixel)
    longe = page.evaluate("([x, y]) => window.plat.mapa.desenho.encaixar(x + 25, y + 25)", pixel)
    assert perto is not None, "clique a 7,2 px do vértice tinha de encaixar (tolerância 10 px)"
    assert abs(perto[0] - alvo[0]) < 1e-9 and abs(perto[1] - alvo[1]) < 1e-9, (perto, alvo)
    assert longe is None, "clique a 35 px do vértice não pode encaixar"
    mapa.capturar("encaixe")
    mapa.verificar()


def test_html_no_texto_do_desenho_nao_vira_marcacao(mapa, page):
    """Refutação do item: HTML no texto do desenho é DADO, nunca marcação. O texto é desenhado pelo MapLibre
    (`text-field`, que só aceita string) e o rótulo da lista lateral entra por textContent."""
    bruto = "<img src=x onerror=alert(1)><b>oi</b>"
    page.once("dialog", lambda d: d.accept(bruto))
    page.click('[data-desenho="texto"]')
    _clicar_no_mapa(page, 640, 380)
    page.wait_for_timeout(200)
    assert page.evaluate("window.plat.mapa.desenho.lista()[0].properties.texto") == bruto
    assert page.evaluate("document.querySelectorAll('#lista-desenho img, #lista-desenho b').length") == 0
    mapa.verificar()
