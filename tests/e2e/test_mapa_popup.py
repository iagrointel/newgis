"""e2e do popup em tempo de execução (item L2-01-d-popup-runtime), no navegador de verdade (chromium
do playwright). Cada teste aqui é uma cláusula literal do portão:

  * clique em ponto com 3 feições coincidentes mostra "1 de 3" e navega;
  * campo nulo aparece como "—", nunca "null"/"undefined";
  * número 1234567.891 aparece como "1.234.567,89" com 2 decimais configuradas;
  * data aparece no fuso do inquilino (America/Sao_Paulo e UTC dão textos diferentes);
  * popup em viewport 390 px abre como painel inferior (captura);
  * campo com HTML/script aparece como TEXTO, nunca executa (refutação do item);
  * 50 cliques rápidos sem consulta pendurada (refutação do item).

A geometria Multi + campo nulo (as outras duas cláusulas do portão) já são provadas em
`tests/e2e/test_mapa_web.py::test_janela_de_atributos_com_campo_nulo_e_geometria_multi`, que este item
ajustou para o novo DOM (paginador) sem duplicar o cenário; a expressão de área x ST_Area está em
`tests/api/test_mapa_popup_api.py` (mais barato medir tolerância numérica ali do que no navegador).

Depende da bancada `scripts/mapa_demo_popup.py criar` e do Martin no ar; sem uma das duas, SALTA."""

from pathlib import Path

import pytest

from tests.e2e.apoio import Tela
from tests.e2e.test_mapa_web import _esperar_feicoes, _ligar, martin_no_ar  # noqa: F401 (fixture reusada)

CAPTURAS = Path(__file__).resolve().parent / "capturas"
BANCADA_ITEM = "(L2-01-d"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def mapa(page, base_url, credenciais_demo, martin_no_ar):  # noqa: F811 (fixture importada de propósito)
    """Sessão aberta na tela /mapa, com a bancada DESTE item conferida (mesma família "(L2-01", filtro
    mais estrito para não depender da bancada do item-pai estar presente também)."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa_popup")
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas', { foco: false })")  # UX-04: painel na gaveta
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    titulos = page.locator(".camada-titulo").all_inner_texts()
    if not any(BANCADA_ITEM in t for t in titulos):
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_popup.py criar")
    page.wait_for_function("() => !!(window.plat && window.plat.org)", timeout=5000)
    return tela


def _clicar_no_ponto_coincidente(page):
    """Os fid 1/2/3 da bancada (scripts/mapa_demo_popup.py) estão na MESMA coordenada exata
    (-46.633, -23.55); aproxima até um pixel e clica no centro do mapa."""
    _ligar(page, "^mapa-popup ", enquadrar=False)  # âncora: casa a camada de pontos, nunca a "mapa-popup-area"
    page.evaluate("""() => {
      const m = window.plat.mapa;
      m.map.jumpTo({ center: [-46.633, -23.55], zoom: 16 });
    }""")
    _esperar_feicoes(page, 30000)
    caixa = page.locator("#mapa").bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)


def _texto_do_pager(page):
    return page.locator(".popup-pager-texto").inner_text().strip()


def _ir_para_pagina(page, n: int):
    """Anda para a página `n` do paginador clicando em "próxima feição". A ORDEM em que as feições
    coincidentes aparecem vem de `queryRenderedFeatures` do MapLibre, que não promete ordem de fid —
    por isso o teste anda por posição e lê o que há, nunca supõe qual fid está em qual página."""
    while True:
        atual = int(_texto_do_pager(page).split(" de ")[0])
        if atual == n:
            return
        page.locator('.popup-pager button[aria-label="próxima feição"]').click()
        page.wait_for_function(
            "(alvo) => document.querySelector('.popup-pager-texto').textContent.trim() !== alvo",
            arg=f"{atual} de 3")


def _celula(page, campo: str) -> str:
    return page.locator(f'.popup-tabela tr[data-campo="{campo}"] td').inner_text().strip()


def test_paginacao_entre_tres_feicoes_coincidentes(mapa, page):
    """Cláusula: clique em ponto com 3 feições coincidentes mostra "1 de 3" e navega."""
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector(".popup-plat .popup-pager", timeout=10000)
    assert _texto_do_pager(page) == "1 de 3"
    titulos = []
    for n in (1, 2, 3):
        _ir_para_pagina(page, n)
        assert _texto_do_pager(page) == f"{n} de 3"
        titulos.append(page.locator(".popup-conteudo h3").inner_text())
    # três feições distintas: pelo menos dois títulos diferentes entre si (uma delas tem nome nulo)
    assert len(set(titulos)) > 1, titulos
    mapa.verificar()


def test_campo_nulo_numero_grande_e_texto_bruto_nunca_executa(mapa, page):
    """Cláusulas: campo nulo aparece como "—" (nunca "null"/"undefined"); 1234567.891 vira
    "1.234.567,89" com 2 decimais configuradas; e a refutação do item — texto com HTML e script
    aparece como TEXTO, nunca vira elemento nem dispara alert()."""
    dialogos = []
    page.on("dialog", lambda d: (dialogos.append(d.message), d.dismiss()))
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)

    nomes, valores, observacoes = [], [], []
    for n in (1, 2, 3):
        _ir_para_pagina(page, n)
        page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
        nomes.append(_celula(page, "nome"))
        valores.append(_celula(page, "valor_numero"))
        observacoes.append(_celula(page, "obs_bruta"))
        conteudo = page.locator(".popup-conteudo").inner_text().lower()
        assert "null" not in conteudo, (n, conteudo)
        assert "undefined" not in conteudo, (n, conteudo)

    # a feição de nome nulo da bancada aparece como travessão, nunca vazia nem "null"
    assert "—" in nomes, nomes
    # a feição com valor_numero = 1234567.891 e 2 casas configuradas
    assert "1.234.567,89" in valores, valores
    # o texto cru com marcação aparece como TEXTO...
    assert any("<script>" in o for o in observacoes), observacoes
    # ...e nunca vira elemento de script nem dispara diálogo
    assert page.locator(".popup-tabela script").count() == 0
    assert dialogos == [], dialogos
    mapa.verificar()


def _gravar_fuso_do_demo(conexao_plat_app, fuso: str) -> None:
    """`tenant.config.fuso` não tem UI/rota pública ainda (`/api/org` não expõe esta chave — fronteira
    honesta desta trilha, ver handoff); a cláusula do portão pede o MESMO instante em dois fusos, e o
    jeito mais barato de provar isso é gravar a chave direto, como a bancada do item já faz."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(adm["tenant_id"]),))
        cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(adm["usuario_id"]),))
        cur.execute("UPDATE plat.tenant SET config = config || jsonb_build_object('fuso', %s::text) "
                    "WHERE id = plat.tenant_atual()", (fuso,))
    conexao_plat_app.commit()


def test_data_no_fuso_do_inquilino_utc_e_sao_paulo(mapa, page, conexao_plat_app):
    """A cláusula pede o MESMO instante em dois fusos. `tenant.config.fuso` muda direto no banco; a
    tela relê `/api/mapa/fuso` só ao abrir — recarrega a página entre as duas medições."""
    try:
        _gravar_fuso_do_demo(conexao_plat_app, "America/Sao_Paulo")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_function(
            "() => window.plat && window.plat.org && window.plat.org.fuso === 'America/Sao_Paulo'", timeout=5000)
        _clicar_no_ponto_coincidente(page)
        page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
        texto_sp = page.locator('.popup-tabela tr[data-campo="data_evento_ms"] td').inner_text().strip()

        _gravar_fuso_do_demo(conexao_plat_app, "UTC")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_function("() => window.plat && window.plat.org && window.plat.org.fuso === 'UTC'", timeout=5000)
        _clicar_no_ponto_coincidente(page)
        page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
        texto_utc = page.locator('.popup-tabela tr[data-campo="data_evento_ms"] td').inner_text().strip()

        assert texto_sp != texto_utc, (texto_sp, texto_utc)
    finally:
        # nunca deixa o inquilino de demonstração com fuso diferente do padrão para o resto da suíte
        _gravar_fuso_do_demo(conexao_plat_app, "America/Sao_Paulo")


def test_painel_acoplado_em_viewport_estreito(mapa, page):
    page.set_viewport_size({"width": 390, "height": 844})
    _clicar_no_ponto_coincidente(page)
    page.wait_for_selector("#popup-dock:not([hidden]) .popup-tabela", timeout=10000)
    assert page.locator(".maplibregl-popup").count() == 0  # nunca o popup flutuante nesta largura
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / "L2-01-d-popup-runtime_painel_acoplado.png"))
    page.locator(".popup-dock-fechar").click()
    # elemento com [hidden] nunca fica "visível": a espera é por presença no DOM
    page.wait_for_selector("#popup-dock[hidden]", state="attached", timeout=5000)
    mapa.verificar()


def test_cinquenta_cliques_rapidos_sem_consulta_pendurada(mapa, page):
    _ligar(page, "^mapa-popup ", enquadrar=False)  # âncora: casa a camada de pontos, nunca a "mapa-popup-area"
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-46.633, -23.55], zoom: 16 })")
    _esperar_feicoes(page, 30000)
    caixa = page.locator("#mapa").bounding_box()
    cx, cy = caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2
    for _ in range(50):
        page.mouse.click(cx, cy)
    page.wait_for_selector(".popup-plat .popup-tabela", timeout=10000)
    # nenhum "carregando…" pendurado 2 s depois do último clique (a última chamada teve tempo de responder)
    page.wait_for_timeout(2000)
    assert page.locator("td.carregando").count() == 0
    mapa.verificar()
