"""e2e do item L5-15-vista-movel-responsivo (depende de L5-08-editor-arrasto, commit c93a08a): vista móvel do
"app publicado" — reflow automático OU vista móvel manual, mais pré-visualização por dispositivo no construtor
e arrasto por TOQUE (Pointer Events, D1 do item: o HTML5 DnD nunca dispara em toque — achado do L5-08).

O portão do item, cláusula a cláusula:

1. e2e em 3 viewports (Pixel 7, iPad, 1440) do MESMO app (`/visualizar?item=<id>`): sem rolagem horizontal
   em nenhuma, mapa sempre visível (bounding box > 0), tabela vira lista SÓ na faixa ≤ 600 px (Pixel 7 —
   iPad em retrato já é 810 px, acima do corte "Dashboards" citado na hipótese, e continua tabela);
2. vista móvel configurada manualmente (`corpo.vista_movel.manual = true`) prevalece sobre o reflow: um nó de
   raiz oculto não aparece no DOM em nenhuma leitura, e a ordem vem de `vista_movel.nos[id].ordem`, não da
   ordem do documento;
3. construtor em tablet (iPad, `has_touch`) arrasta um widget da paleta até a tela só por TOQUE (Pointer
   Events, sem HTML5 DnD) e a alternativa por menu ("Adicionar" + árvore) também monta o mesmo tipo de nó;
4. capturas das 3 vistas em tests/e2e/capturas/L5-15-vista-movel-responsivo_*.png.

Refutação do adversário (mesmo arquivo, `test_adversario_360x640_sem_widget_cortado`): abre o app publicado em
360×640 (o corte da hipótese "Dashboards") num documento SEM vista móvel manual e confere que os três widgets
de raiz (mapa, tabela, texto) continuam presentes e com bounding box positivo — 0 cortado, 0 inacessível.
"""

import pytest

from tests.e2e.apoio import RAIZ, Tela, sufixo

ITEM = "L5-15-vista-movel-responsivo"
CAPTURAS = RAIZ / "tests" / "e2e" / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- apoio
def _criar_app(admin_api, titulo: str, nos: list[dict], vista_movel: dict | None = None) -> str:
    corpo = {"nos": nos, "ligacoes": []}
    if vista_movel is not None:
        corpo["vista_movel"] = vista_movel
    r = admin_api.post("/api/itens", data={
        "tipo": "app", "titulo": titulo,
        "dados": {"tipo": "app", "esquema_versao": 3, "corpo": corpo},
    })
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _ulid(n: int) -> str:
    """ULID sintético só para o teste montar `nos` sem passar pelo editor (a mesma forma que
    web/js/editor/documento.js::gerarUlid produz: 26 caracteres Crockford, primeiro em 0-7)."""
    return f"01ARZ3NDEKTSV4RRFFQ69G5FA{n}"[:26]


def _doc_padrao() -> list[dict]:
    return [
        {
            "id": _ulid(1), "tipo": "mapa", "pai": None, "largura_colunas": 8,
            "propriedades": {"zoom": 12, "mostrar_escala": True},
        },
        {
            "id": _ulid(2), "tipo": "tabela", "pai": None, "largura_colunas": 4,
            "propriedades": {"linhas_por_pagina": 25},
        },
        {
            "id": _ulid(3), "tipo": "texto", "pai": None, "largura_colunas": 12,
            "propriedades": {"texto": "Painel de teste", "nivel": "titulo"},
        },
    ]


def _sem_rolagem_horizontal(page) -> bool:
    return page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")


def _capturar(page, nome: str) -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


# ---------------------------------------------------------------- cláusula 1 + 4
def test_tres_viewports_sem_rolagem_e_mapa_visivel(
    playwright, browser, base_url, credenciais_demo, admin_api, medida,
):
    slug, login, senha = credenciais_demo
    iid = _criar_app(admin_api, f"zt-3vp-{sufixo()}", _doc_padrao())
    grava = medida(ITEM)

    casos = [
        ("pixel7", playwright.devices["Pixel 7"], True),   # (nome, device, tabela_deve_ser_lista)
        ("ipad", playwright.devices["iPad (gen 7)"], False),
        ("desktop1440", {"viewport": {"width": 1440, "height": 900}, "is_mobile": False, "has_touch": False}, False),
    ]
    for nome, device, tabela_lista in casos:
        ctx = browser.new_context(**device, locale="pt-BR", base_url=base_url)
        page = ctx.new_page()
        tela = Tela(page, base_url)
        tela.entrar(slug, login, senha)
        t0 = page.evaluate("() => performance.now()")
        tela.ir(f"/visualizar?item={iid}")
        page.wait_for_selector('[data-tipo="mapa"]', timeout=10000)
        ms = page.evaluate("(t0) => performance.now() - t0", t0)

        assert _sem_rolagem_horizontal(page), f"{nome}: rolagem horizontal"
        mapa_caixa = page.locator('[data-tipo="mapa"]').bounding_box()
        mapa_com_area = mapa_caixa is not None and mapa_caixa["width"] > 0 and mapa_caixa["height"] > 0
        assert mapa_com_area, f"{nome}: mapa sem bounding box"
        assert page.locator('[data-tipo="mapa"]').is_visible(), f"{nome}: mapa não visível"

        tem_lista = page.locator("ul.v-tabela-lista").count() > 0
        tem_tabela = page.locator("table.v-tabela").count() > 0
        if tabela_lista:
            assert tem_lista and not tem_tabela, f"{nome}: tabela deveria virar lista"
        else:
            assert tem_tabela and not tem_lista, f"{nome}: tabela deveria continuar tabela"

        _capturar(page, nome)
        tela.verificar()
        grava(
            f"sem_rolagem_horizontal_{nome}", 1 if _sem_rolagem_horizontal(page) else 0, "bool",
            f"scrollWidth <= clientWidth em {nome}",
        )
        grava(
            f"carregamento_{nome}_ms", round(ms, 1), "ms",
            f"goto /visualizar?item até o mapa aparecer, viewport {nome}",
        )
        ctx.close()


# ---------------------------------------------------------------- cláusula 2
def test_vista_movel_manual_prevalece_sobre_reflow(playwright, browser, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    nos = _doc_padrao()  # ordem natural: mapa(1), tabela(2), texto(3)
    vista_movel = {
        "manual": True,
        "nos": {
            _ulid(2): {"oculto": True},               # tabela: some no celular
            _ulid(3): {"ordem": 0},                    # texto: vem ANTES do mapa (que não tem override -> ordem 1000+i)
        },
    }
    iid = _criar_app(admin_api, f"zt-manual-{sufixo()}", nos, vista_movel)

    ctx = browser.new_context(**playwright.devices["Pixel 7"], locale="pt-BR", base_url=base_url)
    page = ctx.new_page()
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/visualizar?item={iid}")
    page.wait_for_selector('[data-tipo="texto"]', timeout=10000)

    # tabela oculta: NÃO está no DOM (nem como <table> nem como <ul>) — prevalece sobre o reflow, que a
    # mostraria como lista
    assert page.locator('[data-tipo="tabela"]').count() == 0, "override 'oculto' não prevaleceu"
    # ordem: texto (ordem 0) antes do mapa (sem override, fica depois de qualquer ordem explícita)
    tipos_na_tela = page.eval_on_selector_all("#vista-raiz > [data-no]", "els => els.map(e => e.dataset.tipo)")
    assert tipos_na_tela == ["texto", "mapa"], tipos_na_tela
    assert _sem_rolagem_horizontal(page)
    _capturar(page, "manual_prevalece")
    tela.verificar()
    ctx.close()


# ---------------------------------------------------------------- cláusula 3
def test_construtor_tablet_arrasta_por_toque_e_por_menu(
    playwright, browser, base_url, credenciais_demo, admin_api, medida,
):
    slug, login, senha = credenciais_demo
    ctx = browser.new_context(**playwright.devices["iPad (gen 7)"], locale="pt-BR", base_url=base_url)
    page = ctx.new_page()
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_app(admin_api, f"zt-toque-tablet-{sufixo()}", [])
    tela.ir(f"/construtor?item={iid}")
    page.wait_for_selector("#tela", timeout=10000)

    # 3a. arrasto por TOQUE de verdade (Pointer Events, pointerType 'touch'): paleta "mapa" -> tela vazia.
    # HTML5 DnD nunca dispara em toque (achado do L5-08) — por isso a gravação inteira do gesto é feita por
    # PointerEvent sintético com pointerType explícito, igual ao que um dedo real dispara no Chromium móvel.
    t0 = page.evaluate("() => performance.now()")
    moveu = page.evaluate(
        """
        async () => {
          const origem = document.querySelector('[data-paleta="mapa"]');
          const alvo = document.querySelector('#tela');
          const rOrig = origem.getBoundingClientRect();
          const rAlvo = alvo.getBoundingClientRect();
          const x0 = rOrig.x + rOrig.width / 2, y0 = rOrig.y + rOrig.height / 2;
          const x1 = rAlvo.x + rAlvo.width / 2, y1 = rAlvo.y + rAlvo.height - 8;
          const disparar = (alvoEl, tipo, x, y) => alvoEl.dispatchEvent(new PointerEvent(tipo, {
            pointerId: 1, pointerType: 'touch', clientX: x, clientY: y, bubbles: true, cancelable: true,
          }));
          disparar(origem, 'pointerdown', x0, y0);
          await new Promise((r) => setTimeout(r, 20));
          // passos intermediários: sem isso o limiar de 8px nunca é ultrapassado com um só salto
          for (let i = 1; i <= 6; i += 1) {
            const x = x0 + (x1 - x0) * (i / 6), y = y0 + (y1 - y0) * (i / 6);
            disparar(document, 'pointermove', x, y);
            await new Promise((r) => setTimeout(r, 16));
          }
          disparar(document, 'pointerup', x1, y1);
          await new Promise((r) => setTimeout(r, 20));
          return true;
        }
        """
    )
    assert moveu is True
    page.wait_for_selector('[data-tipo="mapa"].no-editor', timeout=5000)
    ms_toque = page.evaluate("(t0) => performance.now() - t0", t0)
    mapa_id = page.get_attribute('[data-tipo="mapa"].no-editor', "data-no")
    assert mapa_id, "arrasto por toque não criou o nó de mapa"

    # 3b. a alternativa por MENU (botão "Adicionar", sem gesto nenhum) também monta o mesmo tipo de nó —
    # mesma alternativa de ponteiro único que o L5-08 já prova para os outros construtores.
    page.tap('[data-adicionar="tabela"]')
    page.wait_for_selector('[data-tipo="tabela"].no-editor', timeout=5000)

    page.click("#salvar")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000,
    )
    d = admin_api.get(f"/api/itens/{iid}").json()["dados"]
    tipos = [n["tipo"] for n in d["corpo"]["nos"]]
    assert tipos == ["mapa", "tabela"], tipos

    _capturar(page, "construtor_tablet_toque")
    tela.verificar()
    medida(ITEM)(
        "arrasto_por_toque_ms", round(ms_toque, 1), "ms",
        "PointerEvent sintético pointerType=touch, paleta mapa -> #tela, iPad (gen 7)",
    )
    ctx.close()


# ---------------------------------------------------------------- refutação do adversário
def test_adversario_360x640_sem_widget_cortado(browser, base_url, credenciais_demo, admin_api):
    """360x640 é o corte citado na hipótese do item ('Dashboards': ≤ 600 px carrega móvel). Documento SEM
    vista móvel manual: o reflow automático não pode esconder nem cortar nenhum dos três nós de raiz."""
    slug, login, senha = credenciais_demo
    iid = _criar_app(admin_api, f"zt-adv-360-{sufixo()}", _doc_padrao())

    ctx = browser.new_context(
        viewport={"width": 360, "height": 640}, locale="pt-BR", base_url=base_url, has_touch=True, is_mobile=True,
    )
    page = ctx.new_page()
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/visualizar?item={iid}")
    page.wait_for_selector('[data-tipo="texto"]', timeout=10000)

    cortado = []
    for tipo in ("mapa", "tabela", "texto"):
        loc = page.locator(f'[data-tipo="{tipo}"]')
        if loc.count() == 0:
            cortado.append(f"{tipo}: ausente")
            continue
        caixa = loc.bounding_box()
        visivel = loc.is_visible()
        dentro_da_largura = caixa is not None and caixa["x"] >= -1 and caixa["x"] + caixa["width"] <= 360 + 1
        if not visivel or caixa is None or caixa["width"] <= 0 or caixa["height"] <= 0 or not dentro_da_largura:
            cortado.append(f"{tipo}: visivel={visivel} caixa={caixa}")
    assert cortado == [], cortado
    assert _sem_rolagem_horizontal(page)
    _capturar(page, "adversario_360x640")
    tela.verificar()
    ctx.close()
