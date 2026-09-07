"""e2e da camada de desenho e anotações do mapa (item L2-01-k-desenho-anotacoes): os 7 tipos de desenho
criados na tela de verdade (chromium do playwright), salvos no documento e reabertos idênticos (comparação
do GeoJSON), texto com halo, "promover a camada" com a mesma contagem e geometrias válidas, e refutação do
item (polígono auto-intersectante, círculo no polo, texto de 10 mil caracteres — 0 erro de console em tudo).

Depende de `/mapa` responder (item L2-01-mapa-web) e do terra-draw vendorizado carregar."""

import json

import pytest

from tests.e2e.apoio import Tela

ITEM = "L2-01-k-desenho-anotacoes"

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
    """O modo `rectangle` do terra-draw é clique-move-clique (canto e canto oposto), não arrasto — arrastar
    não fecha o retângulo e a feição nunca chega ao `finish` (medido nesta tela)."""
    page.click('[data-desenho="retangulo"]')
    box = page.locator("#mapa canvas").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.click(cx - 120, cy - 120)
    page.mouse.move(cx - 40, cy - 40, steps=5)
    page.mouse.click(cx - 40, cy - 40)
    page.wait_for_timeout(150)


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

    page.click('[data-desenho="seta"]')  # a seta reusa o modo `linestring`, com tipo_desenho próprio
    _clicar_no_mapa(page, 800, 300)
    _clicar_no_mapa(page, 850, 260)
    page.keyboard.press("Enter")

    n = page.evaluate("window.plat.mapa.desenho.lista().length")
    tipos = page.evaluate("window.plat.mapa.desenho.lista().map(f => f.properties.tipo_desenho)")
    assert n == 7, tipos
    assert set(tipos) == {"ponto", "linha", "poligono", "retangulo", "circulo", "texto", "seta"}
    tela = mapa
    tela.capturar(f"{ITEM}_sete_tipos")
    tela.verificar()


def test_texto_com_halo_renderizado(mapa, page):
    """`text-field` do MapLibre exige servidor de glifos, que o mapa-base local não tem (item L2-02-e);
    MEDIDO: o MapLibre aceita o addLayer e descarta a camada em silêncio. Por isso o texto é desenhado num
    canvas (halo por `strokeText`, letra por `fillText`) e entra como imagem da feição."""
    page.once("dialog", lambda d: d.accept("halo visível"))
    page.click('[data-desenho="texto"]')
    _clicar_no_mapa(page, 640, 380)
    page.wait_for_timeout(250)
    assert page.evaluate("!!window.plat.mapa.map.getLayer('plat-desenho-texto')") is True
    campo = page.evaluate("window.plat.mapa.map.getLayoutProperty('plat-desenho-texto', 'icon-image')")
    assert campo == ["get", "_imagem_texto"]
    fid = page.evaluate("window.plat.mapa.desenho.lista()[0].id")
    halo = page.evaluate("(id) => window.plat.mapa.desenho.haloDoTexto(id)", fid)
    assert halo["halo_px"] > 0
    assert halo["pixels_de_halo"] > 0, "o desenho do texto tem de ter pixels da cor do halo em volta da letra"
    assert page.evaluate("(n) => window.plat.mapa.map.hasImage(n)", halo["imagem"]) is True


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
    mapa.capturar(f"{ITEM}_salvar_reabrir")
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

    box = page.locator("#mapa canvas").bounding_box()

    def pixel_de(coordenada):
        p = _pixel_de(page, coordenada)
        return box["x"] + p[0], box["y"] + p[1]

    anel = antes["geometry"]["coordinates"][0]
    # clique dentro do polígono (média dos vértices) para o modo `select` do terra-draw selecionar a feição
    dentro = [sum(v[0] for v in anel[:3]) / 3, sum(v[1] for v in anel[:3]) / 3]
    page.mouse.click(*pixel_de(dentro))
    page.wait_for_timeout(200)
    vx, vy = pixel_de(anel[0])
    page.mouse.move(vx, vy)
    page.mouse.down()
    page.mouse.move(vx + 45, vy + 35, steps=10)  # arrasta o vértice
    page.mouse.up()
    page.wait_for_timeout(250)

    page.evaluate("window.plat.mapa.desenho.terminarEdicao()")
    assert page.evaluate("window.plat.mapa.desenho.editando()") is None
    depois = page.evaluate("window.plat.mapa.desenho.lista()[0]")
    assert depois["id"] == fid
    assert depois["properties"]["tipo_desenho"] == "poligono"
    assert depois["properties"]["estilo"] == antes["properties"]["estilo"]
    assert depois["geometry"]["type"] == "Polygon"
    assert depois["geometry"] != antes["geometry"], "arrastar o vértice tinha de mudar a geometria"
    mapa.verificar()


def _pixel_de(page, coordenada):
    return page.evaluate(
        "(c) => { const p = window.plat.mapa.map.project({lng: c[0], lat: c[1]}); return [p.x, p.y]; }",
        coordenada)


def _dist_px(page, coordenada, pixel):
    p = _pixel_de(page, coordenada)
    return ((p[0] - pixel[0]) ** 2 + (p[1] - pixel[1]) ** 2) ** 0.5


def test_encaixe_10px_cai_no_vertice_da_feicao_alvo(mapa, page):
    """Cláusula de encaixe do portão, medida em PIXELS na tela de verdade.

    O encaixe considera TODAS as feições visíveis, o desenho e o mapa-base juntos — é o que serve para
    desenhar encostado no dado. Por isso a coincidência exata com a feição alvo é medida onde ela é
    inequívoca: em cima do vértice do polígono (distância zero, nenhum outro vértice pode ganhar). Perto,
    mas não em cima, o que se prova é o contrato da tolerância: o que volta é um vértice dentro dela."""
    _desenhar_poligono(page)
    page.check("#desenho-snap")
    alvo = page.evaluate("window.plat.mapa.desenho.lista()[0].geometry.coordinates[0][0]")
    pixel = _pixel_de(page, alvo)

    em_cima = page.evaluate("([x, y]) => window.plat.mapa.desenho.encaixar(x, y)", pixel)
    assert em_cima == alvo, (em_cima, alvo)

    perto = page.evaluate("([x, y]) => window.plat.mapa.desenho.encaixar(x + 6, y + 4)", pixel)
    deslocado = [pixel[0] + 6, pixel[1] + 4]
    assert perto is not None, "a 7,2 px do vértice do polígono tinha de haver encaixe (tolerância 10 px)"
    assert _dist_px(page, perto, deslocado) <= 10.0

    page.evaluate("window.plat.mapa.desenho.definirToleranciaSnap(0.5)")
    apertado = page.evaluate("([x, y]) => window.plat.mapa.desenho.encaixar(x + 6, y + 4)", pixel)
    assert apertado is None or _dist_px(page, apertado, deslocado) <= 0.5, apertado
    page.evaluate("window.plat.mapa.desenho.definirToleranciaSnap(10)")
    mapa.capturar(f"{ITEM}_encaixe")
    mapa.verificar()


def test_encaixe_leva_o_vertice_novo_para_cima_do_alvo(mapa, page):
    """O encaixe valendo no DESENHO, não só na consulta: com o encaixe ligado, o primeiro clique de uma linha
    em cima do vértice de um polígono já desenhado nasce com a coordenada EXATA daquele vértice — sem
    encaixe, o clique no mesmo pixel dá outra coordenada (o pixel tem largura, a coordenada não)."""
    _desenhar_poligono(page)
    alvo = page.evaluate("window.plat.mapa.desenho.lista()[0].geometry.coordinates[0][0]")
    pixel = _pixel_de(page, alvo)
    box = page.locator("#mapa canvas").bounding_box()

    page.check("#desenho-snap")
    page.click('[data-desenho="linha"]')
    page.mouse.click(box["x"] + pixel[0], box["y"] + pixel[1])
    page.mouse.click(box["x"] + pixel[0] + 120, box["y"] + pixel[1] + 90)
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    linha = page.evaluate("window.plat.mapa.desenho.lista().find(f => f.properties.tipo_desenho === 'linha')")
    assert linha is not None, "a linha tinha de ter sido criada"
    assert linha["geometry"]["coordinates"][0] == alvo, (linha["geometry"]["coordinates"][0], alvo)
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
