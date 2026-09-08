"""e2e do visualizador de mapa (item L2-01-mapa-web).

Cada teste aqui é uma cláusula do portão de pronto do item, provada no navegador de verdade (chromium do
playwright; o google-chrome do sistema quebra nesta máquina):

  * camada de 1 milhão de feições carrega e o mapa continua respondendo — com o tempo MEDIDO;
  * ordem, opacidade, ligar/desligar, enquadrar, mapa-base, escala, coordenadas, medição, pesquisa de
    endereço e de coordenada;
  * legenda gerada da simbologia (as cores da legenda são as cores que o mapa está pintando);
  * janela de atributos, inclusive em feição com campo nulo e geometria multi (refutação do item);
  * impressão em PNG e em PDF com escala e norte, conferida byte a byte (PIL e pdftoppm);
  * 10 camadas ao mesmo tempo, com tempo e memória do navegador medidos (refutação do item);
  * 0 erro de console em tudo.

Depende da bancada `scripts/mapa_demo_camadas.py criar` e do Martin no ar; sem uma das duas, SALTA."""

import subprocess
from pathlib import Path

import httpx
import pytest
from PIL import Image

from tests.e2e.apoio import Tela

ITEM = "L2-01-mapa-web"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
MARTIN = "http://127.0.0.1:8151"
BANCADA = "(L2-01"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="module")
def martin_no_ar():
    try:
        httpx.get(f"{MARTIN}/catalog", timeout=5)
    except httpx.HTTPError as e:
        pytest.skip(f"Martin fora do ar em {MARTIN}: {e}")


@pytest.fixture
def mapa(page, base_url, credenciais_demo, martin_no_ar):
    """Sessão aberta na tela /mapa, com a bancada do item conferida."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    titulos = page.locator(".camada-titulo").all_inner_texts()
    if not any(BANCADA in t for t in titulos):
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_camadas.py criar")
    return tela


def _linha_da_camada(page, trecho):
    return page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{trecho}"))').first


def _ligar(page, trecho, enquadrar=False):
    linha = _linha_da_camada(page, trecho)
    caixa = linha.locator('input[type=checkbox]')
    if not caixa.is_checked():
        caixa.check()
    page.wait_for_timeout(200)
    if enquadrar:
        # a bancada é sintética e cobre o Brasil inteiro; a tela abre em Guarulhos, onde caberiam
        # poucas feições. Enquadrar a camada é o que o usuário faz e é o que põe dado na tela.
        linha.locator('button[data-acao="enquadrar"]').click()
        page.wait_for_timeout(400)
    return linha


def _esperar_feicoes(page, tempo=60000):
    """espera até haver feição DESENHADA (tile carregado ainda não é pixel na tela)."""
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=tempo)
    page.wait_for_function(
        """() => {
             const m = window.plat.mapa;
             const c = m.catalogo.ativas.flatMap((id) => m.catalogo.idsDeEstilo(id))
               .filter((x) => m.map.getLayer(x));
             return c.length && m.map.queryRenderedFeatures({ layers: c }).length > 0;
           }""", timeout=tempo)


def _tiles_pintados(page):
    """quantas feições do catálogo o MapLibre está desenhando agora (não é contagem de banco)."""
    return page.evaluate("""() => {
      const m = window.plat.mapa;
      const camadas = m.catalogo.ativas.flatMap((id) => m.catalogo.idsDeEstilo(id))
        .filter((c) => m.map.getLayer(c));
      return camadas.length ? m.map.queryRenderedFeatures({ layers: camadas }).length : 0;
    }""")


def test_camada_de_um_milhao_carrega_e_o_mapa_continua_respondendo(mapa, page, medida):
    gravar = medida(ITEM)
    _ligar(page, "1mi", enquadrar=True)
    # espera o primeiro tile pintar; o relógio começa no clique e para quando há feição desenhada
    inicio = page.evaluate("() => performance.now()")
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=60000)
    page.wait_for_function(
        """() => {
             const m = window.plat.mapa;
             const c = m.catalogo.ativas.flatMap((id) => m.catalogo.idsDeEstilo(id))
               .filter((x) => m.map.getLayer(x));
             return c.length && m.map.queryRenderedFeatures({ layers: c }).length > 0;
           }""", timeout=60000)
    carga_ms = round(page.evaluate("() => performance.now()") - inicio, 1)
    desenhadas = _tiles_pintados(page)
    assert desenhadas > 0

    # "sem travar" = o laço de eventos continua livre: uma interação (zoom) responde depressa
    resposta_ms = page.evaluate("""async () => {
      const m = window.plat.mapa.map;
      const t0 = performance.now();
      m.zoomIn({ duration: 0 });
      await new Promise((r) => m.once('idle', r));
      return performance.now() - t0;
    }""")
    memoria = page.evaluate("() => (performance.memory ? performance.memory.usedJSHeapSize : null)")

    gravar("camada_1mi_feicoes_no_banco", 1000000, "feições",
           "scripts/mapa_demo_camadas.py criar (pontos sintéticos uniformes no Brasil)")
    gravar("camada_1mi_carga_ate_primeiro_desenho_ms", carga_ms, "ms",
           "performance.now() entre ligar a camada e haver feição em queryRenderedFeatures (chromium 1280x800)")
    gravar("camada_1mi_feicoes_desenhadas_na_tela", desenhadas, "feições",
           "map.queryRenderedFeatures() com a camada enquadrada (extensão inteira do Brasil na tela)")
    gravar("camada_1mi_zoom_ate_idle_ms", round(resposta_ms, 1), "ms",
           "map.zoomIn({duration:0}) até o evento 'idle' com a camada de 1 mi ligada")
    if memoria:
        gravar("camada_1mi_memoria_js_mb", round(memoria / 1048576, 1), "MB",
               "performance.memory.usedJSHeapSize no chromium com a camada de 1 mi ligada")
    assert resposta_ms < 10000, f"zoom levou {resposta_ms} ms com a camada de 1 mi — isso é travar"
    mapa.verificar()


def test_ordem_opacidade_e_enquadrar(mapa, page):
    _ligar(page, "1mi")
    page.wait_for_function("() => window.plat.mapa.catalogo.ativas.length === 1", timeout=20000)
    _ligar(page, "poligonos")
    page.wait_for_function("() => window.plat.mapa.catalogo.ativas.length === 2", timeout=20000)
    ordem = page.evaluate("() => window.plat.mapa.catalogo.ativas.slice()")
    assert len(ordem) == 2
    # a mais recente entra no topo; descer a primeira inverte a ordem de desenho
    _linha_da_camada(page, "poligonos").locator('button[data-acao="descer"]').click()
    page.wait_for_timeout(150)
    assert page.evaluate("() => window.plat.mapa.catalogo.ativas.slice()") == list(reversed(ordem))
    # e a ordem do array de camadas do estilo do MapLibre acompanha (topo da lista = desenhado por último)
    posicoes = page.evaluate("""() => {
      const m = window.plat.mapa;
      const ids = m.map.getStyle().layers.map((c) => c.id);
      return m.catalogo.ativas.map((id) => Math.max(...m.catalogo.idsDeEstilo(id).map((c) => ids.indexOf(c))));
    }""")
    assert posicoes == sorted(posicoes, reverse=True), posicoes

    faixa = _linha_da_camada(page, "poligonos").locator("input.camada-opacidade")
    faixa.fill("30")
    faixa.dispatch_event("input")
    page.wait_for_timeout(150)
    opacidade = page.evaluate("""() => {
      const m = window.plat.mapa;
      const id = m.catalogo.ativas.find((i) => (m.catalogo.ficha(i).titulo || '').includes('poligonos'));
      const c = m.catalogo.idsDeEstilo(id)[0];
      return m.map.getPaintProperty(c, 'fill-opacity');
    }""")
    assert 0.1 < opacidade < 0.2, opacidade  # 0,55 do estilo x 0,30 da faixa

    _linha_da_camada(page, "poligonos").locator('button[data-acao="enquadrar"]').click()
    page.wait_for_timeout(400)
    centro = page.evaluate("() => window.plat.mapa.map.getCenter()")
    assert -70 < centro["lng"] < -30 and -35 < centro["lat"] < 5, centro
    mapa.verificar()


def test_legenda_mostra_as_cores_que_o_mapa_pinta(mapa, page):
    _ligar(page, "1mi", enquadrar=True)
    page.wait_for_selector("#legenda .legenda-bloco")
    cores_legenda = page.evaluate("""() => Array.from(
      document.querySelectorAll('#legenda .legenda-bloco:first-child .legenda-amostra'))
      .map((el) => el.style.getPropertyValue('--cor'))""")
    cores_estilo = page.evaluate("""() => {
      const m = window.plat.mapa;
      const id = m.catalogo.ativas[0];
      const c = m.catalogo.idsDeEstilo(id)[0];
      const v = m.map.getPaintProperty(c, 'circle-color');
      return Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.startsWith('#')) : [v];
    }""")
    assert cores_legenda and cores_legenda == cores_estilo, (cores_legenda, cores_estilo)
    mapa.verificar()


def test_janela_de_atributos_com_campo_nulo_e_geometria_multi(mapa, page):
    _ligar(page, "poligonos", enquadrar=True)
    _esperar_feicoes(page, 30000)
    # aproxima até UMA feição: a bancada tem multipolígonos de duas peças de ~2 km, que na visão do
    # Brasil inteiro ficam menores que um pixel e não dariam um alvo de clique honesto.
    alvo = page.evaluate("""() => {
      const m = window.plat.mapa;
      const camadas = m.catalogo.idsDeEstilo(m.catalogo.ativas[0]).filter((c) => m.map.getLayer(c));
      const fs = m.map.queryRenderedFeatures({ layers: camadas });
      const nula = fs.find((f) => f.properties.nome === undefined || f.properties.nome === null) || fs[0];
      if (!nula) return null;
      const g = nula.geometry;
      const anel = g.type === 'MultiPolygon' ? g.coordinates[0][0] : g.coordinates[0];
      let sx = 0; let sy = 0;
      for (const [x, y] of anel) { sx += x; sy += y; }
      const centro = [sx / anel.length, sy / anel.length];
      m.map.jumpTo({ center: centro, zoom: 13 });
      return { centro, multi: g.type.startsWith('Multi'), temNome: 'nome' in nula.properties };
    }""")
    assert alvo, "nenhuma feição de polígono desenhada para clicar"
    _esperar_feicoes(page, 30000)
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
    assert page.locator(".popup-tabela tr").count() >= 3

    # os campos declarados no catálogo aparecem TODOS, mesmo os que vieram nulos do banco (o MVT
    # simplesmente não traz a chave quando o valor é nulo)
    campos = page.locator(".popup-tabela tr").evaluate_all("els => els.map(e => e.dataset.campo)")
    assert {"nome", "classe", "area_ha"} <= set(campos), campos
    if not alvo["temNome"]:
        assert page.locator('.popup-tabela tr[data-nulo="1"] td.nulo').count() >= 1

    # geometria multi: a mesma feição chega em pedaços e a janela não a repete
    blocos = page.locator(".popup-plat .popup-camada").count()
    assert blocos == 1, blocos
    mapa.verificar()


def test_pesquisa_por_coordenada_e_por_endereco(mapa, page):
    page.fill("#busca-campo", "2.82, -60.67")   # Boa Vista/RR, a UF do CNEFE instalado
    page.click("#busca-form button[type=submit]")
    page.wait_for_timeout(500)
    centro = page.evaluate("() => window.plat.mapa.map.getCenter()")
    assert abs(centro["lat"] - 2.82) < 0.01 and abs(centro["lng"] + 60.67) < 0.01, centro
    assert page.locator(".maplibregl-marker").count() == 1

    page.fill("#busca-campo", "AVENIDA")
    page.wait_for_timeout(900)
    sugestoes = page.locator("#busca-sugestoes .sugestao").count()
    if sugestoes == 0:
        pytest.skip("geocodificador sem CNEFE instalado nesta base (plat.geo_endereco vazia)")
    assert sugestoes >= 1

    page.fill("#busca-campo", "AVENIDA ENE GARCEZ, Boa Vista - RR")
    page.click("#busca-form button[type=submit]")
    page.wait_for_timeout(1500)
    resultado = (page.text_content("#busca-resultado") or "").strip()
    assert "ENE GARCEZ" in resultado.upper(), resultado
    depois = page.evaluate("() => window.plat.mapa.map.getCenter()")
    assert abs(depois["lat"] - 2.825) < 0.05 and abs(depois["lng"] + 60.678) < 0.05, depois
    mapa.verificar()


def test_escala_coordenadas_e_troca_de_mapa_base(mapa, page):
    assert page.locator(".maplibregl-ctrl-scale").count() == 1
    assert page.locator(".maplibregl-ctrl-zoom-in").count() == 1
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_timeout(200)
    coord = page.text_content("#coordenadas").strip()
    assert "," in coord and "z" in coord and "1:" in coord, coord

    _ligar(page, "1mi", enquadrar=True)
    page.select_option("#seletor-base", "sem-base")
    page.wait_for_function("() => window.plat.mapa.catalogo.ativas.length === 1", timeout=20000)
    # a camada do catálogo sobrevive à troca de mapa-base (o estilo é refeito e ela é re-somada)
    assert page.evaluate("() => window.plat.mapa.catalogo.ativas.length") == 1
    assert page.evaluate("""() => {
      const m = window.plat.mapa;
      return m.catalogo.idsDeEstilo(m.catalogo.ativas[0]).every((c) => !!m.map.getLayer(c));
    }""")
    mapa.verificar()


def test_medicao_geodesica_de_distancia_e_area(mapa, page):
    page.click("#btn-distancia")
    caixa = page.locator("#mapa").bounding_box()
    # dois cliques com separação conhecida em graus, medidos pelo próprio mapa
    pontos = page.evaluate("""() => {
      const m = window.plat.mapa.map;
      m.jumpTo({ center: [-46.6, -23.5], zoom: 10 });
      const a = m.project([-46.6, -23.5]);
      const b = m.project([-46.5, -23.5]);
      return [{ x: a.x, y: a.y }, { x: b.x, y: b.y }];
    }""")
    for p in pontos:
        page.mouse.click(caixa["x"] + p["x"], caixa["y"] + p["y"])
        page.wait_for_timeout(120)
    texto = (page.text_content("#medicao-saida") or "").strip()
    assert "km" in texto, texto
    valor = page.evaluate("() => window.plat.mapa.medicao.resultado().valor")
    # 0,1 grau de longitude em -23,5 de latitude = 10,2 km (cos(23,5) x 111,3 km)
    assert 10000 < valor < 10500, valor

    page.click("#btn-medicao-limpar")
    page.click("#btn-area")
    tres = page.evaluate("""() => {
      const m = window.plat.mapa.map;
      return [[-46.6, -23.5], [-46.5, -23.5], [-46.5, -23.6]].map((c) => {
        const p = m.project(c); return { x: p.x, y: p.y };
      });
    }""")
    for p in tres:
        page.mouse.click(caixa["x"] + p["x"], caixa["y"] + p["y"])
        page.wait_for_timeout(120)
    area = page.evaluate("() => window.plat.mapa.medicao.resultado()")
    assert area["tipo"] == "area"
    # triângulo retângulo de 10,2 km x 11,1 km = 56,7 km2; meia tolerância para a esfera
    assert 5.0e7 < area["valor"] < 6.2e7, area
    assert "km²" in (page.text_content("#medicao-saida") or "")
    page.click("#btn-medicao-limpar")
    mapa.verificar()


def test_impressao_png_e_pdf_com_escala_e_norte(mapa, page, medida, tmp_path):
    gravar = medida(ITEM)
    _ligar(page, "1mi", enquadrar=True)
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=60000)
    CAPTURAS.mkdir(parents=True, exist_ok=True)

    with page.expect_download(timeout=30000) as espera:
        page.click("#btn-png")
    png = CAPTURAS / f"{ITEM}_impressao.png"
    espera.value.save_as(str(png))
    with Image.open(png) as im:
        largura, altura = im.size
        cores = len(im.convert("RGB").getcolors(maxcolors=2_000_000) or [])
    assert cores > 50, cores          # não é uma folha em branco
    assert altura > largura * 0.4     # a faixa de escala/norte entra abaixo do mapa

    with page.expect_download(timeout=30000) as espera:
        page.click("#btn-pdf")
    pdf = CAPTURAS / f"{ITEM}_impressao.pdf"
    espera.value.save_as(str(pdf))
    assert pdf.read_bytes()[:5] == b"%PDF-", "arquivo não é PDF"

    # o PDF é lido por um leitor independente (Poppler), não pela nossa própria conta
    saida = subprocess.run(["pdftoppm", "-png", "-r", "60", str(pdf), str(tmp_path / "pagina")],
                           capture_output=True, text=True, timeout=120)
    assert saida.returncode == 0, saida.stderr
    paginas = sorted(tmp_path.glob("pagina*.png"))
    assert len(paginas) == 1, paginas
    with Image.open(paginas[0]) as im:
        cores_pdf = len(im.convert("RGB").getcolors(maxcolors=2_000_000) or [])
    assert cores_pdf > 50, cores_pdf

    texto = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
    assert "escala aproximada 1:" in texto.lower(), texto[:300]
    assert "norte" in texto.lower(), texto[:300]

    gravar("impressao_png_bytes", png.stat().st_size, "bytes", "download do botão PNG da tela /mapa")
    gravar("impressao_pdf_bytes", pdf.stat().st_size, "bytes", "download do botão PDF da tela /mapa")
    gravar("impressao_pdf_paginas", len(paginas), "páginas", "pdftoppm -png -r 60 sobre o PDF gerado")
    gravar("impressao_pdf_cores_distintas", cores_pdf, "contagem",
           "PIL Image.getcolors() sobre a página convertida pelo Poppler")
    mapa.verificar()


def test_dez_camadas_ao_mesmo_tempo(mapa, page, medida):
    """Refutação declarada do item: o adversário liga 10 camadas e mede tempo e memória."""
    gravar = medida(ITEM)
    linhas = page.locator("#lista-camadas li")
    total = min(10, linhas.count())
    inicio = page.evaluate("() => performance.now()")
    for i in range(total):
        caixa = linhas.nth(i).locator('input[type=checkbox]')
        if not caixa.is_checked():
            caixa.check()
        page.wait_for_timeout(80)
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=120000)
    ms = round(page.evaluate("() => performance.now()") - inicio, 1)
    ativas = page.evaluate("() => window.plat.mapa.catalogo.ativas.length")
    memoria = page.evaluate("() => (performance.memory ? performance.memory.usedJSHeapSize : null)")
    resposta = page.evaluate("""async () => {
      const m = window.plat.mapa.map;
      const t0 = performance.now();
      m.panBy([120, 80], { duration: 0 });
      await new Promise((r) => m.once('idle', r));
      return performance.now() - t0;
    }""")
    assert ativas == total, (ativas, total)
    gravar("dez_camadas_ligadas", ativas, "camadas", "checkbox de cada linha da lista, uma a uma")
    gravar("dez_camadas_ate_tiles_carregados_ms", ms, "ms",
           "performance.now() do primeiro clique até map.areTilesLoaded() (inclui a camada de 1 mi)")
    gravar("dez_camadas_pan_ate_idle_ms", round(resposta, 1), "ms",
           "map.panBy([120,80]) até 'idle' com as 10 camadas ligadas")
    if memoria:
        gravar("dez_camadas_memoria_js_mb", round(memoria / 1048576, 1), "MB",
               "performance.memory.usedJSHeapSize com as 10 camadas ligadas")
    page.locator("#mapa").screenshot(path=str(CAPTURAS / f"{ITEM}_dez_camadas.png"))
    mapa.verificar()
