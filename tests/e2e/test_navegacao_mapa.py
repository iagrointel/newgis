"""e2e do item L2-01-f-navegacao-medicao-coordenadas na tela /mapa (chromium do playwright, sem bancada de
camadas: tudo aqui roda sobre o mapa-base local). Uma captura por ferramenta em tests/e2e/capturas/:
escala + coordenada em CRS escolhido, ir para (três formas), medição com segmentos e cópia, favorito salvo e
reaberto (± 1 px), histórico voltar/avançar, norte/rotação, tela cheia, minha localização (geolocalização
simulada pelo playwright, com círculo de precisão), atalhos. Refutação: linha que cruza o antimeridiano e
linha no equador comparadas com o PostGIS; barra de escala × distância medida; texto malformado no 'ir para'.
0 erro de console."""

from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

ITEM = "L2-01-f-navegacao-medicao-coordenadas"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """geolocalização simulada: a estação RBMC de Brasília (aproximada), com 25 m de precisão"""
    return {**browser_context_args, "geolocation": {"latitude": -15.947475, "longitude": -47.877869, "accuracy": 25},
            "permissions": ["geolocation", "clipboard-read", "clipboard-write"]}


@pytest.fixture
def mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_mapa_ms")
    page.wait_for_function("() => window.plat && window.plat.mapa && window.plat.mapa.map.loaded()", timeout=30000)
    return tela


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"))


def _clicar_pontos(page, coords):
    caixa = page.locator("#mapa").bounding_box()
    for lon, lat in coords:
        p = page.evaluate("([lon, lat]) => { const q = window.plat.mapa.map.project([lon, lat]); return [q.x, q.y]; }",
                          [lon, lat])
        page.mouse.click(caixa["x"] + p[0], caixa["y"] + p[1])
        page.wait_for_timeout(120)


def _st(conexao_plat_app, sql, params):
    with conexao_plat_app.cursor() as cur:
        cur.execute(sql, params)
        return float(cur.fetchone()["v"])


def test_escala_coordenada_em_crs_e_ir_para(mapa, page, conexao_plat_app):
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-51.1198, -30.0740], zoom: 12 })")
    page.wait_for_timeout(200)
    # coordenada do cursor em UTM 22S bate com ST_Transform (≤ 1 cm) num ponto conhecido do centro
    page.select_option("#seletor-crs", "31982")
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_timeout(200)
    texto = page.text_content("#coordenadas").strip()
    assert page.get_attribute("#coordenadas", "data-srid") == "31982" and " m ·" in texto, texto
    lon = float(page.get_attribute("#coordenadas", "data-lon"))
    lat = float(page.get_attribute("#coordenadas", "data-lat"))
    x_txt, y_txt = texto.split(" m")[0].split(" ")[:2]
    x = float(x_txt.replace(".", "").replace(",", "."))
    y = float(y_txt.replace(".", "").replace(",", "."))
    sql = "SELECT ST_%s(ST_Transform(ST_SetSRID(ST_MakePoint(%%s, %%s), 4326), 31982)) AS v"
    x_ref = _st(conexao_plat_app, sql % "X", (lon, lat))
    y_ref = _st(conexao_plat_app, sql % "Y", (lon, lat))
    assert abs(x - x_ref) <= 0.01 and abs(y - y_ref) <= 0.01, (texto, x_ref, y_ref)
    # barra de escala (MapLibre, geodésica na latitude do centro) × distância medida na mesma largura de tela
    barra = page.evaluate("""() => { const el = document.querySelector('.maplibregl-ctrl-scale');
      const m = window.plat.mapa.map; const c = m.getCenter(); const y = m.project(c).y;
      const a = m.unproject([0, y]); const b = m.unproject([el.getBoundingClientRect().width, y]);
      return { rotulo: el.textContent, largura: el.getBoundingClientRect().width,
               a: [a.lng, a.lat], b: [b.lng, b.lat] }; }""")
    dist = _st(conexao_plat_app, "SELECT ST_Length(ST_MakeLine(ST_SetSRID(ST_MakePoint(%s, %s), 4326), "
               "ST_SetSRID(ST_MakePoint(%s, %s), 4326))::geography) AS v", (*barra["a"], *barra["b"]))
    rotulo = barra["rotulo"].strip()
    valor = float(rotulo.replace("km", "").replace("m", "").strip().replace(",", "."))
    metros = valor * 1000 if rotulo.endswith("km") else valor
    assert abs(metros - dist) / dist < 0.01, (rotulo, dist)
    _capturar(page, "escala_coordenada_crs")
    # ir para: as três formas do portão
    for texto_ir, esperado in [("−23,55 −46,63", (-23.55, -46.63)), ("23°33′S 46°38′W", (-23.55, -(46 + 38 / 60)))]:
        page.fill("#busca-campo", texto_ir)
        page.press("#busca-campo", "Enter")
        page.wait_for_timeout(300)
        c = page.evaluate("() => { const c = window.plat.mapa.map.getCenter(); return [c.lat, c.lng]; }")
        assert abs(c[0] - esperado[0]) < 1e-4 and abs(c[1] - esperado[1]) < 1e-4, (texto_ir, c)
    page.fill("#busca-campo", "333.000 7.394.000 EPSG:31983")
    page.press("#busca-campo", "Enter")
    page.wait_for_timeout(300)
    c = page.evaluate("() => { const c = window.plat.mapa.map.getCenter(); return [c.lng, c.lat]; }")
    sql = "SELECT ST_%s(ST_Transform(ST_SetSRID(ST_MakePoint(333000, 7394000), 31983), 4326)) AS v"
    lon_ref = _st(conexao_plat_app, sql % "X", ())
    lat_ref = _st(conexao_plat_app, sql % "Y", ())
    assert abs(c[0] - lon_ref) < 1e-5 and abs(c[1] - lat_ref) < 1e-5, (c, lon_ref, lat_ref)
    _capturar(page, "ir_para")
    # refutação: texto malformado com cara de coordenada não vai ao geocodificador e diz o motivo; texto hostil
    # sem cara de coordenada vai ao geocodificador como endereço e volta "nada encontrado" — nada quebra
    for ruim in ["333.000 7.394.000 EPSG:99999", "-95, 100", "23°S"]:
        page.fill("#busca-campo", ruim)
        page.press("#busca-campo", "Enter")
        page.wait_for_timeout(300)
        assert "não reconhecida" in page.text_content("#busca-resultado"), ruim
    page.fill("#busca-campo", "'; DROP TABLE x; --")
    page.press("#busca-campo", "Enter")
    page.wait_for_timeout(500)
    assert page.text_content("#busca-resultado").strip() != ""
    mapa.esperar_status(404, 422)
    mapa.verificar()


def test_medicao_com_segmentos_copia_antimeridiano_e_equador(mapa, page, conexao_plat_app):
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-46.55, -23.55], zoom: 11 })")
    page.click("#btn-distancia")
    pontos = [(-46.60, -23.50), (-46.50, -23.50), (-46.50, -23.60)]
    _clicar_pontos(page, pontos)
    r = page.evaluate("() => window.plat.mapa.medicao.resultado()")
    assert r["tipo"] == "distancia" and len(r["segmentos"]) == 2
    assert page.locator("#medicao-segmentos li").count() == 2
    ref = _st(conexao_plat_app, "SELECT ST_Length(ST_GeomFromText(%s, 4326)::geography) AS v",
              ("LINESTRING(" + ", ".join(f"{x} {y}" for x, y in pontos) + ")",))
    assert abs(r["valor"] - ref) / ref <= 0.001, (r["valor"], ref)
    page.click("#btn-medicao-copiar")
    page.wait_for_timeout(200)
    copiado = page.evaluate("() => navigator.clipboard.readText()")
    assert "distância" in copiado and "segmento 2:" in copiado and "GRS80" in copiado
    _capturar(page, "medicao_distancia")
    page.click("#btn-medicao-limpar")
    page.click("#btn-area")
    _clicar_pontos(page, pontos)
    a = page.evaluate("() => window.plat.mapa.medicao.resultado()")
    ref_a = _st(conexao_plat_app, "SELECT ST_Area(ST_GeomFromText(%s, 4326)::geography) AS v",
                ("POLYGON((" + ", ".join(f"{x} {y}" for x, y in pontos + [pontos[0]]) + "))",))
    assert a["tipo"] == "area" and a["metodo"].startswith("elipsoide"), a
    assert abs(a["valor"] - ref_a) / ref_a <= 0.001, (a, ref_a)
    _capturar(page, "medicao_area")
    page.click("#btn-medicao-limpar")
    # refutação: linha que cruza o antimeridiano (Fiji → Samoa) e linha no equador, pelo motor da tela
    for nome, par in [("antimeridiano", [[178.0, -17.5], [-172.0, -13.8]]), ("equador", [[-60.0, 0.0], [-50.0, 0.0]])]:
        nosso = page.evaluate("async ([a, b]) => { const m = await import('/static/js/mapa/medicao.js'); "
                              "return m.distancia(a, b); }", par)
        ref = _st(conexao_plat_app, "SELECT ST_Length(ST_MakeLine(ST_SetSRID(ST_MakePoint(%s, %s), 4326), "
                  "ST_SetSRID(ST_MakePoint(%s, %s), 4326))::geography) AS v", (*par[0], *par[1]))
        assert abs(nosso - ref) / ref <= 0.001, (nome, nosso, ref)
    mapa.verificar()


def test_favorito_historico_norte_tela_cheia_localizacao_e_atalhos(mapa, page):
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-47.8779, -15.9475], zoom: 13, bearing: 30 })")
    page.wait_for_timeout(200)
    # favorito: salvar, mudar a vista, recarregar a página, reabrir → ± 1 px
    page.fill("#favorito-nome", "Brasília girada")
    page.click("#btn-favorito-salvar")
    assert page.locator('#favoritos li[data-favorito="Brasília girada"]').count() == 1
    projetar = ("() => { const m = window.plat.mapa.map; const p = m.project([-47.8779, -15.9475]); "
                "return [p.x, p.y, m.getBearing()]; }")
    antes = page.evaluate(projetar)
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-51.1198, -30.0740], zoom: 8, bearing: 0 })")
    page.wait_for_timeout(200)
    _capturar(page, "favoritos")
    page.reload()
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_function("() => window.plat && window.plat.mapa && window.plat.mapa.map.loaded()", timeout=30000)
    page.click('#favoritos button[data-ir-favorito="Brasília girada"]')
    page.wait_for_timeout(300)
    depois = page.evaluate(projetar)
    assert abs(antes[0] - depois[0]) <= 1 and abs(antes[1] - depois[1]) <= 1, (antes, depois)
    assert abs(antes[2] - depois[2]) < 0.01, (antes, depois)
    # histórico: duas extensões, volta, avança
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-38.5165, -12.9749], zoom: 10, bearing: 0 })")
    page.wait_for_timeout(200)
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-34.9514, -8.0509], zoom: 9 })")
    page.wait_for_timeout(200)
    page.click("#btn-voltar-extensao")
    page.wait_for_timeout(200)
    c = page.evaluate("() => { const c = window.plat.mapa.map.getCenter(); return [c.lng, c.lat]; }")
    assert abs(c[0] + 38.5165) < 1e-6 and abs(c[1] + 12.9749) < 1e-6, c
    page.keyboard.press("Alt+ArrowRight")
    page.wait_for_timeout(200)
    c = page.evaluate("() => { const c = window.plat.mapa.map.getCenter(); return [c.lng, c.lat]; }")
    assert abs(c[0] + 34.9514) < 1e-6, c
    _capturar(page, "historico")
    # norte: rotaciona e volta com o botão e com a tecla
    page.evaluate("() => window.plat.mapa.map.jumpTo({ bearing: 45 })")
    page.click("#btn-norte")
    page.wait_for_function("() => Math.abs(window.plat.mapa.map.getBearing()) < 0.01", timeout=5000)
    page.evaluate("() => window.plat.mapa.map.jumpTo({ bearing: -60 })")
    page.keyboard.press("n")
    page.wait_for_function("() => Math.abs(window.plat.mapa.map.getBearing()) < 0.01", timeout=5000)
    _capturar(page, "norte")
    # tela cheia: controle presente e clique não dá erro (o chromium sem cabeça pode recusar o pedido — só o
    # controle e a ausência de erro são provados aqui)
    assert page.locator(".maplibregl-ctrl-fullscreen").count() == 1
    page.click(".maplibregl-ctrl-fullscreen")
    page.wait_for_timeout(300)
    _capturar(page, "tela_cheia")
    if page.evaluate("() => !!document.fullscreenElement"):
        page.keyboard.press("Escape")
    # minha localização: círculo de precisão e marcador aparecem na posição simulada
    page.click(".maplibregl-ctrl-geolocate")
    page.wait_for_selector(".maplibregl-user-location-dot", timeout=15000)
    page.wait_for_function("() => Math.abs(window.plat.mapa.map.getCenter().lat + 15.947475) < 0.01", timeout=15000)
    assert page.locator(".maplibregl-user-location-accuracy-circle").count() == 1
    _capturar(page, "minha_localizacao")
    # atalhos: D inicia medição, Esc limpa; ? abre a lista documentada
    page.keyboard.press("d")
    assert page.get_attribute("#btn-distancia", "aria-pressed") == "true"
    page.keyboard.press("Escape")
    assert page.get_attribute("#btn-distancia", "aria-pressed") == "false"
    page.keyboard.press("?")
    assert page.evaluate("() => document.getElementById('atalhos').open") is True
    assert page.locator("#atalhos-lista kbd").count() >= 14
    _capturar(page, "atalhos")
    mapa.esperar_status(404)
    mapa.verificar()
