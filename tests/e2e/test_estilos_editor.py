"""e2e do editor de simbologia (item L2-02-c) no visualizador real (MapLibre + Martin da trilha): cada tipo é
aplicado pelo navegador, pré-visualizado ao vivo, SALVO (item `estilo` ligado à camada) e capturado — 8
capturas: símbolo único, categoria (com "outros"), classes de cor, classes de tamanho, proporcional, mapa de
calor, agrupamento, efeitos + escala. Também: cortes do editor = cortes do L2-02-b, categorias > 200 viram 200 +
outros, desfazer/refazer, exportar valida na Style Spec, e reabrir a camada traz o estilo salvo."""

import json
from pathlib import Path

import pytest

from app.estilos import validador
from tests.api import estilos_apoio
from tests.e2e.apoio import Tela

ITEM = "L2-02-c-editor-simbologia-vetor"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="module")
def bancada(env):
    return estilos_apoio.criar(env)


def _tela(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # fora do nginx a URL pública é https e o Origin local nunca casa (CSRF): as escritas são refeitas pelo
    # contexto do playwright, sem o cabeçalho — a checagem em si é provada em tests/api
    def _sem_origin(rota):
        if rota.request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return rota.continue_()
        cabecalhos = {k: v for k, v in rota.request.headers.items() if k.lower() != "origin"}
        return rota.fulfill(response=rota.fetch(headers=cabecalhos))

    page.route("**/api/**", _sem_origin)
    tela.entrar(slug, login, senha, proximo="/mapa")
    tela.ir("/mapa", "pagina_mapa_ms")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    return tela


def _abrir_editor(page, titulo):
    linha = page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{titulo}"))').first
    caixa = linha.locator("input[type=checkbox]")
    if not caixa.is_checked():
        caixa.check()
    page.wait_for_timeout(200)
    linha.locator('button[data-acao="enquadrar"]').click()
    linha.locator('button[data-acao="estilo"]').click()
    page.wait_for_selector("#painel-estilo:not([hidden]) #estilo-tipo", timeout=10000)


def _esperar_previsualizacao(page, minimo=1):
    page.wait_for_function(
        f"() => Number(document.getElementById('painel-estilo').dataset.previsualizado || 0) >= {minimo}",
        timeout=15000)
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded() && window.plat.mapa.map.loaded()",
                           timeout=30000)
    page.wait_for_timeout(400)


def _salvar(page):
    page.evaluate("() => { const p = document.getElementById('painel-estilo'); delete p.dataset.salvo; }")
    page.click("#estilo-salvar")
    page.wait_for_function("() => document.getElementById('painel-estilo').dataset.salvo "
                           "|| document.getElementById('estilo-aviso').dataset.tipo === 'erro'", timeout=15000)
    assert page.get_attribute("#estilo-aviso", "data-tipo") == "ok", page.text_content("#estilo-aviso")
    return page.get_attribute("#painel-estilo", "data-salvo")


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho))
    assert caminho.stat().st_size > 20000, caminho
    return caminho


def _doc(page):
    return page.evaluate("() => window.plat.mapa.editor.documento()")


def _pintado(page, sufixo, propriedade):
    return page.evaluate(f"""() => {{ const id = 'plat-' + window.plat.mapa.editor.camadaId + '{sufixo}';
      const m = window.plat.mapa.map;
      return m.getLayer(id) ? m.getPaintProperty(id, '{propriedade}') : null; }}""")


def test_editor_aplica_salva_e_captura_os_oito_tipos(page, base_url, credenciais_demo, bancada, admin_api, medida):
    tela = _tela(page, base_url, credenciais_demo)
    previs = 0
    salvos = []
    try:
        # ---------- polígonos: símbolo único
        _abrir_editor(page, "poligonos")
        previs += 1
        _esperar_previsualizacao(page, previs)
        page.fill("#estilo-cor", "#2a9d8f")
        page.dispatch_event("#estilo-cor", "input")
        previs += 1
        _esperar_previsualizacao(page, previs)
        assert _pintado(page, "", "fill-color") == "#2a9d8f"
        salvos.append(_salvar(page))
        _capturar(page, "1_unico")

        # ---------- polígonos: categoria com outros (rampa qualitativa vinda do servidor)
        page.select_option("#estilo-tipo", "categoria")
        page.select_option("#estilo-campo", "uso")
        page.click("#estilo-sugerir-categorias")
        page.wait_for_selector("#estilo-categorias li", timeout=10000)
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or previs)
        _esperar_previsualizacao(page, previs)
        d = _doc(page)
        assert d["tipo"] == "categoria" and len(d["categorias"]) == 5 and d.get("outros") is None
        salvos.append(_salvar(page))
        _capturar(page, "2_categoria")

        # ---------- polígonos: classes de cor pelos cortes do L2-02-b
        page.select_option("#estilo-tipo", "classes")
        page.select_option("#estilo-campo", "area_ha")
        page.select_option("#estilo-metodo", "quantil")
        page.fill("#estilo-n_classes", "4")
        page.dispatch_event("#estilo-n_classes", "change")
        page.click("#estilo-sugerir-classes")
        page.wait_for_selector("#estilo-classes-lista li", timeout=10000)
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or previs)
        _esperar_previsualizacao(page, previs)
        d = _doc(page)
        r = admin_api.get(f"/api/camadas/{bancada['poligonos']['id']}/classes?campo=area_ha&metodo=quantil&n=4")
        cortes = r.json()["cortes"]
        assert [(c["min"], c["max"]) for c in d["classes"]] == [(cortes[i], cortes[i + 1]) for i in range(4)]
        assert json.loads(page.get_attribute("#painel-estilo", "data-cortes")) == cortes
        salvos.append(_salvar(page))
        _capturar(page, "3_classes_cor")

        # ---------- efeitos + escala no polígono (sombra, mistura registrada, faixa de escala)
        page.check("#estilo-sombra")
        page.fill("#estilo-escala_max", "8000000")
        page.dispatch_event("#estilo-escala_max", "change")
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or previs)
        _esperar_previsualizacao(page, previs)
        assert page.evaluate("() => !!window.plat.mapa.map.getLayer('plat-' + window.plat.mapa.editor.camadaId "
                             "+ '-sombra')")
        salvos.append(_salvar(page))
        _capturar(page, "4_efeitos_escala")

        # desfazer volta o documento anterior; refazer reaplica
        antes = _doc(page)
        page.click("#estilo-desfazer")
        assert _doc(page).get("escala_max") != antes.get("escala_max")
        page.click("#estilo-refazer")
        assert _doc(page) == antes

        # exportar: o documento exportado valida na Style Spec oficial
        exportado = page.evaluate("() => window.plat.mapa.editor.exportar()")
        validador._chamar_style_spec(json.loads(exportado)["corpo"]["maplibre"])
        page.click("#estilo-fechar")

        # ---------- linhas: classes de TAMANHO
        _abrir_editor(page, "linhas")
        page.select_option("#estilo-tipo", "classes")
        page.select_option("#estilo-campo", "extensao_km")
        page.check("#estilo-classes_de_tamanho")
        page.click("#estilo-sugerir-classes")
        page.wait_for_selector("#estilo-classes-lista li", timeout=10000)
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or 0)
        _esperar_previsualizacao(page, previs)
        d = _doc(page)
        assert all("tamanho" in c for c in d["classes"]) and d["classes"][0]["tamanho"] < d["classes"][-1]["tamanho"]
        largura = _pintado(page, "", "line-width")
        assert isinstance(largura, list) and largura[0] == "case"
        salvos.append(_salvar(page))
        _capturar(page, "5_classes_tamanho")
        page.click("#estilo-fechar")

        # ---------- pontos: categoria com > 200 valores → 200 + outros (polígonos e linhas desligados para a
        # captura mostrar os pontos, que estão abaixo deles na ordem de desenho)
        for outra in ("poligonos", "linhas"):
            page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{outra}"))').first.locator(
                "input[type=checkbox]").uncheck()
        page.wait_for_timeout(300)
        _abrir_editor(page, "pontos")
        page.select_option("#estilo-tipo", "categoria")
        page.select_option("#estilo-campo", "categoria")
        page.click("#estilo-sugerir-categorias")
        page.wait_for_selector("#estilo-categorias li", timeout=15000)
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or 0)
        _esperar_previsualizacao(page, previs)
        d = _doc(page)
        assert len(d["categorias"]) == 200 and d["outros"]["visivel"] is True
        assert page.get_attribute("#painel-estilo", "data-agrupados-em-outros") == "100"
        assert "100 valores" in page.text_content("#estilo-categorias-info")

        # ---------- pontos: proporcional
        page.select_option("#estilo-tipo", "proporcional")
        page.select_option("#estilo-campo", "valor")
        page.click("#estilo-sugerir-proporcional")
        page.wait_for_selector("#estilo-valor_max", timeout=10000)
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or 0)
        _esperar_previsualizacao(page, previs)
        assert _pintado(page, "", "circle-radius")[0] == "interpolate"
        salvos.append(_salvar(page))
        _capturar(page, "6_proporcional")

        # ---------- pontos: mapa de calor
        page.select_option("#estilo-tipo", "calor")
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or 0)
        _esperar_previsualizacao(page, previs)
        tipo_layer = page.evaluate(
            "() => window.plat.mapa.map.getLayer('plat-' + window.plat.mapa.editor.camadaId).type")
        assert tipo_layer == "heatmap"
        salvos.append(_salvar(page))
        _capturar(page, "7_calor")

        # ---------- pontos: agrupamento (clusters no tile pelo Martin)
        page.select_option("#estilo-tipo", "agrupamento")
        previs = int(page.get_attribute("#painel-estilo", "data-previsualizado") or 0)
        _esperar_previsualizacao(page, previs)
        page.wait_for_function("""() => { const m = window.plat.mapa.map;
          const id = 'plat-' + window.plat.mapa.editor.camadaId;
          return m.getLayer(id)
            && m.queryRenderedFeatures({ layers: [id] }).some((f) => f.properties.point_count > 1); }""",
                               timeout=30000)
        fonte = page.evaluate(
            "() => window.plat.mapa.map.getSource('plat-' + window.plat.mapa.editor.camadaId).tiles[0]")
        assert "_ag/" in fonte and "raio=40" in fonte
        salvos.append(_salvar(page))
        _capturar(page, "8_agrupamento")
        page.click("#estilo-fechar")

        # ---------- reabrir traz o estilo salvo (o visualizador desenha com ele)
        page.reload()
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_selector("#lista-camadas li", timeout=20000)
        _abrir_editor(page, "pontos")
        assert page.input_value("#estilo-tipo") == "agrupamento"
        ficha = admin_api.get(f"/api/mapa/camadas/{bancada['pontos']['id']}").json()
        assert ficha["estilo_id"] == salvos[-1] and ficha["agrupamento"] == {"raio_px": 40.0}
        # 422 esperados: pré-visualização de documento incompleto (tipo trocado antes de escolher campo/classificar)
        # mostra a mensagem no painel e segue; 404 = camada sem estilo ainda
        tela.esperar_status(404, 422)
        tela.verificar()
        for nome, valor in tela.medidas.items():
            medida(ITEM)(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        for sid in {s for s in salvos if s}:
            admin_api.delete(f"/api/itens/{sid}")
