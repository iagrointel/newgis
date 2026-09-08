"""e2e do item UX-08-telas-rede-de-utilidades-e-motor, na parte que o tronco sustenta hoje: os painéis "Motor"
(motor multicritério de grades aninhadas, L3-19 — fecha UX-21) e "Rotas" (rota, isócrona e matriz sobre o OSRM do
recorte — fecha UX-19) dentro do chrome único do visualizador (UX-04). O traçado de rede de utilidades (montante/
jusante, controladores) NÃO está no tronco: vive nos ramos L4 da fila (wt/il402bmonta, il402cisola, il402dlacos,
il404acontr, il405depane, il418redesi, il401datrib) e fica registrado no handoff como parte não coberta.

1. Motor: área de estudo criada da vista atual do mapa (o retângulo de 1,9 km × 1,9 km do teste de API do L3-19),
   dois fatores (fino 50 m e grosso 1.000 m) com amostras geradas sobre a área, macro de 1 km com aprovação top 50 %
   → relatório por fator; refino micro de 250 m só nas aprovadas → o fator grosso vem marcado "escala grosseira" com a
   explicação; as células pintam o mapa (4 macro; 2 aprovadas × 16 = 32 micro) e o clique numa célula explica nota,
   cobertura e aprovação; capturas 390/1280; axe sem violação séria;
2. refutação análoga à do item: rodar sem área e sem fator mostra o motivo no painel, nunca painel vazio;
3. Rotas: rota entre dois pontos conhecidos do recorte (linha no mapa, distância e duração), isócrona de 5 min
   (polígono), matriz 2 × 1 (tabela); erro nomeado quando o serviço não responde (503 interceptado); capturas; axe."""

import json
import math

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-08"
CENTRO = (-46.60, -23.50)
LADO_M = 1900.0
M_POR_GRAU_LAT = 111_320.0
M_POR_GRAU_LON = 111_320.0 * math.cos(math.radians(CENTRO[1]))
MEIA_LON = (LADO_M / 2) / M_POR_GRAU_LON
MEIA_LAT = (LADO_M / 2) / M_POR_GRAU_LAT
CENTRO_GUARULHOS = "-46.5330, -23.4628"
PERTO_GRU = "-46.4730, -23.4356"


def _capturar(page, nome, larguras=(390, 1280)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"))
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def _entrar_no_mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def _abrir(page, painel):
    page.evaluate("(p) => window.plat.mapa.abrirPainel(p, { foco: false })", painel)
    page.wait_for_selector(f"#painel-{painel}:not([hidden])", timeout=5000)


def _fonte_tem(page, fonte):
    return page.evaluate(
        "(f) => { const s = window.plat.mapa.map.getSource(f); return s ? (s._data?.features?.length ?? 1) : 0; }",
        fonte,
    )


# ---------------------------------------------------------------- 1 e 2. motor


def test_motor_area_fatores_macro_micro_e_explicacao(page, base_url, credenciais_demo, api_auth):
    if "/api/multiescala/conjuntos" not in api_auth:
        pytest.skip("backend sem /api/multiescala no OpenAPI")
    s = sufixo()
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    tela.esperar_status(422)
    conjunto_id = None
    fatores = []
    try:
        _abrir(page, "motor")
        _axe(page, "motor vazio")
        _sem_chave_crua(page)
        # refutação: rodar sem área e sem fator mostra o motivo no painel
        page.click("#motor-rodar")
        page.wait_for_selector("#motor-rodar-estado[tipo='erro']:not([hidden])")
        assert "área" in (page.text_content("#motor-rodar-estado") or "")
        # área de estudo = vista atual, enquadrada no retângulo do L3-19
        page.evaluate(
            "([o, s, e, n]) => window.plat.mapa.map.fitBounds([[o, s], [e, n]], { padding: 0, duration: 0 })",
            [CENTRO[0] - MEIA_LON, CENTRO[1] - MEIA_LAT, CENTRO[0] + MEIA_LON, CENTRO[1] + MEIA_LAT],
        )
        page.wait_for_timeout(300)
        page.fill("#motor-area-nome", f"zt-ux08 estudo {s}")
        page.click("#motor-area-criar")
        page.wait_for_function(
            "(n) => [...document.querySelectorAll('#motor-area option')].some(o => o.textContent === n)",
            arg=f"zt-ux08 estudo {s}",
            timeout=15000,
        )
        conjunto_id = page.input_value("#motor-area")
        assert conjunto_id
        assert _fonte_tem(page, "plat-motor-area") == 1
        assert "m ×" in (page.text_content("#motor-area-info") or "")
        # dois fatores com amostras geradas sobre a área
        for nome, res, valor in ((f"zt-ux08 fino {s}", "50", "10"), (f"zt-ux08 grosso {s}", "1000", "20")):
            page.locator("#motor-fatores details").evaluate("d => { d.open = true; }")
            page.fill("#motor-fator-nome", nome)
            page.fill("#motor-fator-res", res)
            page.click("#motor-fator-criar")
            li = page.locator("#motor-fatores-lista li", has_text=nome)
            li.wait_for(timeout=15000)
            fatores.append(li.get_attribute("data-fator"))
            li.locator("button[data-amostras]").click()
            li.locator("input[type=number]").fill(valor)
            li.locator("button[data-amostras-grade]").click()
            assert len((li.locator("textarea").input_value() or "").splitlines()) == 36
            li.locator("button[data-amostras-enviar]").click()
            page.wait_for_function(
                "(id) => (document.querySelector(`li[data-fator=\"${id}\"] plat-estado`)?.textContent || '')"
                ".includes('36 amostras')",
                arg=fatores[-1],
                timeout=15000,
            )
        # fator grosso pesa o dobro
        grosso = fatores[1]
        page.locator(f"#motor-peso-{grosso}").evaluate(
            "r => { r.value = 2; r.dispatchEvent(new Event('input', { bubbles: true })); }"
        )
        _capturar(page, "motor_fatores")
        # macro de 1 km, aprovação top 50 %
        page.fill("#motor-resolucao", "1000")
        page.select_option("#motor-aprovacao-tipo", "top_pct")
        page.fill("#motor-aprovacao-valor", "50")
        page.click("#motor-rodar")
        page.wait_for_selector(".motor-execucao[data-nivel='macro']", timeout=30000)
        assert page.locator(".motor-execucao[data-nivel='macro'] .motor-relatorio-fatores li").count() == 2
        page.wait_for_function("() => window.plat.mapa.map.getSource('plat-motor-macro')", timeout=15000)
        assert _fonte_tem(page, "plat-motor-macro") == 4
        assert not page.locator("#motor-refinar").is_disabled()
        # micro de 250 m só nas aprovadas: 2 × (1000/250)² = 32 células; o fator de 1 km vem "escala grosseira"
        page.fill("#motor-resolucao-micro", "250")
        page.click("#motor-refinar")
        page.wait_for_selector(".motor-execucao[data-nivel='micro']", timeout=30000)
        assert page.locator(".motor-execucao[data-nivel='micro'] li.grosseira").count() == 1
        assert "grosso" in page.locator(".motor-execucao[data-nivel='micro'] li.grosseira").inner_text()
        assert "não de dado próprio" in page.locator(".motor-execucao[data-nivel='micro'] li.grosseira").inner_text()
        page.wait_for_function("() => window.plat.mapa.map.getSource('plat-motor-micro')", timeout=15000)
        assert _fonte_tem(page, "plat-motor-micro") == 32
        _axe(page, "motor relatório")
        _sem_chave_crua(page)
        _capturar(page, "motor_resultado")
        # clique numa célula explica nota, cobertura e aprovação
        page.wait_for_timeout(500)
        ponto = page.evaluate(
            "([lon, lat]) => { const p = window.plat.mapa.map.project([lon, lat]); return [p.x, p.y]; }",
            [CENTRO[0] - MEIA_LON * 0.5, CENTRO[1] - MEIA_LAT * 0.5],
        )
        caixa = page.locator("#mapa").bounding_box()
        page.mouse.click(caixa["x"] + ponto[0], caixa["y"] + ponto[1])
        page.wait_for_selector(".motor-popup", timeout=5000)
        assert "nota" in (page.text_content(".motor-popup") or "")
        _capturar(page, "motor_celula", larguras=(1280,))
        tela.verificar()
    finally:
        for fid in fatores:
            tela.api("DELETE", f"/api/multiescala/fatores/{fid}")
        if conjunto_id:
            tela.api("DELETE", f"/api/multiescala/conjuntos/{conjunto_id}")


# ---------------------------------------------------------------- 3. rotas


def test_rotas_rota_isocrona_matriz_e_erro_nomeado(page, base_url, credenciais_demo, api_auth):
    if "/api/rota" not in api_auth:
        pytest.skip("backend sem /api/rota no OpenAPI")
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    _abrir(page, "rotas")
    _axe(page, "rotas vazio")
    _sem_chave_crua(page)
    # sem pontos: o motivo aparece no painel
    page.click("#rotas-calcular-rota")
    page.wait_for_selector("#rotas-estado[tipo='erro']:not([hidden])")
    # rota
    page.fill("#rotas-origem", CENTRO_GUARULHOS)
    page.press("#rotas-origem", "Tab")
    page.fill("#rotas-destino", PERTO_GRU)
    page.press("#rotas-destino", "Tab")
    page.click("#rotas-calcular-rota")
    page.wait_for_selector("#rotas-saida .rotas-resumo", timeout=30000)
    resumo_rota = page.text_content("#rotas-saida .rotas-resumo") or ""
    assert "km" in resumo_rota and "min" in resumo_rota
    assert _fonte_tem(page, "plat-rotas-rota") >= 1
    assert page.locator("#rotas-saida .rotas-proveniencia").count() == 1
    _axe(page, "rota")
    _capturar(page, "rotas_rota")
    # isócrona de 5 min
    page.click("[data-modo='isocrona']")
    page.fill("#rotas-ponto", CENTRO_GUARULHOS)
    page.press("#rotas-ponto", "Tab")
    page.fill("#rotas-minutos", "5")
    page.click("#rotas-calcular-isocrona")
    page.wait_for_function("() => window.plat.mapa.map.getSource('plat-rotas-isocrona')", timeout=60000)
    assert "5" in (page.text_content("#rotas-saida .rotas-resumo") or "")
    _capturar(page, "rotas_isocrona", larguras=(1280,))
    # matriz 2 × 1
    page.click("[data-modo='matriz']")
    origens = page.locator(".rotas-conjunto").nth(0)
    destinos = page.locator(".rotas-conjunto").nth(1)
    for p in (CENTRO_GUARULHOS, PERTO_GRU):
        origens.locator("input").fill(p)
        origens.locator("button[data-acrescentar]").click()
    destinos.locator("input").fill(PERTO_GRU)
    destinos.locator("button[data-acrescentar]").click()
    assert origens.locator("li").count() == 2 and destinos.locator("li").count() == 1
    page.click("#rotas-calcular-matriz")
    page.wait_for_selector("#rotas-saida table tbody tr", timeout=60000)
    assert page.locator("#rotas-saida table tbody tr").count() == 2
    assert "min" in (page.text_content("#rotas-saida table tbody td") or "")
    _axe(page, "matriz")
    _capturar(page, "rotas_matriz", larguras=(1280,))
    # serviço fora do ar: erro nomeado com tentar de novo, nunca painel vazio
    tela.esperar_status(503)
    page.route(
        "**/api/rota",
        lambda r: r.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps(
                {"erro": "osrm_fora", "mensagem": "OSRM não respondeu (provocado)", "req_id": "e2e-ux08-ref"}
            ),
        ),
    )
    page.click("[data-modo='rota']")
    page.click("#rotas-calcular-rota")
    page.wait_for_selector("#rotas-estado[tipo='erro']:not([hidden])")
    assert "serviço de rotas" in (page.text_content("#rotas-estado") or "")
    assert page.locator("#rotas-estado button", has_text="tentar de novo").count() == 1
    page.unroute("**/api/rota")
    _capturar(page, "rotas_erro", larguras=(1280,))
    page.click("#rotas-limpar")
    assert _fonte_tem(page, "plat-rotas-rota") == 0
    tela.verificar()
