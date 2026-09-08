"""e2e do motor de widgets (item L5-06-motor-widgets), no chromium do playwright contra a URL da trilha
(scripts/servir_local.py serve /static; o uvicorn cru não serve web/):

  * página publicada com 3 widgets carrega SÓ os 3 módulos citados (performance.getEntriesByType('resource'));
  * widget desconhecido e configuração fora do esquema viram caixa de erro nomeada, a página segue;
  * HTML em campo de texto fica inerte (textContent) e o console termina sem erro;
  * módulo apagado do disco (404 simulado por page.route) degrada para mensagem, nunca tela branca;
  * o mesmo módulo alterna chrome de edição (construtor) e publicação sem re-renderizar."""

from pathlib import Path

import pytest

ITEM = "L5-06-motor-widgets"
MODULOS_WIDGET = {"mapa.js", "legenda.js", "tabela.js", "texto.js", "botao.js", "filtro.js"}
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def console(page):
    """erros de console e de página; o teste decide o que é aceitável."""
    erros: list[str] = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    return erros


def abrir(page, base_url):
    page.goto(f"{base_url}/aplicativo")
    page.wait_for_selector('body[data-pronto="1"]')


def test_publicacao_carrega_so_os_tres_modulos_usados(page, base_url, medida, console):
    abrir(page, base_url)
    assert page.locator("plat-w-texto, plat-w-filtro, plat-w-tabela").count() == 3
    assert page.locator("plat-w-tabela tbody tr").count() == 2
    page.locator("plat-w-filtro input").fill("rios")
    assert page.locator("plat-w-tabela tbody tr").count() == 1

    recursos = page.evaluate("""() => performance.getEntriesByType('resource').map((r) => ({
      nome: new URL(r.name).pathname, bytes: r.transferSize || r.encodedBodySize || 0
    }))""")
    modulos = [r for r in recursos if "/static/js/widgets/" in r["nome"]]
    nomes_widget = {Path(r["nome"]).name for r in modulos} & MODULOS_WIDGET
    assert nomes_widget == {"tabela.js", "texto.js", "filtro.js"}
    assert console == []

    pintura = page.evaluate(
        "() => performance.getEntriesByType('paint').find((e) => e.name === 'first-contentful-paint')?.startTime || 0")
    bytes_widgets = sum(r["bytes"] for r in modulos if Path(r["nome"]).name in nomes_widget)
    gravar = medida(ITEM)
    gravar("primeira_pintura_ms", round(pintura, 1), "ms",
           "First Contentful Paint da página /aplicativo (tests/e2e/test_motor_widgets.py)")
    gravar("kb_por_widget", round(bytes_widgets / 1024 / len(nomes_widget), 2), "kB",
           "transferência média dos três módulos de widget usados em /aplicativo")


def test_widget_desconhecido_e_configuracao_invalida_mostram_erro_nomeado(page, base_url, console):
    abrir(page, base_url)
    mensagens = page.evaluate("""async () => {
      const { montarWidgets } = await import('/static/js/widgets/motor.js');
      const alvo = document.createElement('div'); document.body.append(alvo);
      await montarWidgets(alvo, {corpo: {nos: [
        {id: '01K4KX2Q0S0000000000000004', tipo: 'grafico-que-nao-existe', configuracao: {}},
        {id: '01K4KX2Q0S0000000000000005', tipo: 'texto', configuracao: {texto: 'x', html: '<b>x</b>'}}
      ], ligacoes: []}});
      return [...alvo.querySelectorAll('[role=alert]')].map((el) => el.textContent);
    }""")
    assert mensagens == [
        "Widget “grafico-que-nao-existe”: tipo desconhecido",
        "Widget “texto”: widget.01K4KX2Q0S0000000000000005.configuracao.html: campo desconhecido",
    ]
    assert console == []


def test_html_em_campo_de_texto_fica_inerte_e_console_sem_erro(page, base_url, console):
    abrir(page, base_url)
    malicioso = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script><b>negrito</b>'
    resultado = page.evaluate("""async (malicioso) => {
      const { montarWidgets } = await import('/static/js/widgets/motor.js');
      const alvo = document.createElement('div'); document.body.append(alvo);
      await montarWidgets(alvo, {corpo: {nos: [
        {id: '01K4KX2Q0S0000000000000006', tipo: 'texto', configuracao: {texto: malicioso}},
        {id: '01K4KX2Q0S0000000000000007', tipo: 'botao', configuracao: {rotulo: malicioso}},
        {id: '01K4KX2Q0S0000000000000008', tipo: 'tabela', configuracao: {
          colunas: [{campo: 'a', rotulo: malicioso}], linhas: [{a: malicioso}]}},
        {id: '01K4KX2Q0S0000000000000009', tipo: 'legenda', configuracao: {itens: [{rotulo: malicioso, cor: 'red'}]}},
      ], ligacoes: []}});
      await new Promise((r) => setTimeout(r, 100));
      return {
        xss: window.__xss ?? null,
        imagens: alvo.querySelectorAll('img, script, b').length,
        texto: alvo.querySelector('plat-w-texto p').textContent,
        celula: alvo.querySelector('plat-w-tabela td').textContent,
        rotulos: alvo.querySelectorAll('plat-w-botao button, plat-w-legenda button, plat-w-tabela th').length,
      };
    }""", malicioso)
    assert resultado["xss"] is None
    assert resultado["imagens"] == 0
    assert resultado["texto"] == malicioso
    assert resultado["celula"] == malicioso
    assert resultado["rotulos"] == 3
    assert console == []


def test_modulo_apagado_do_disco_degrada_para_mensagem(page, base_url, console):
    # o mesmo que `rm web/js/widgets/texto.js`: o navegador recebe 404 para o módulo e nada mais muda
    page.route("**/static/js/widgets/texto.js", lambda rota: rota.fulfill(status=404, body="apagado"))
    abrir(page, base_url)
    assert page.locator("plat-w-filtro, plat-w-tabela").count() == 2
    assert page.locator("plat-w-texto").count() == 0
    erro = page.locator('.plat-widget-erro[data-widget="texto"]')
    assert erro.count() == 1
    assert erro.text_content().startswith("Widget “texto”: módulo ./texto.js não carregou (")
    page.locator("plat-w-filtro input").fill("rios")
    assert page.locator("plat-w-tabela tbody tr").count() == 1
    # o único erro de console tolerado é o próprio 404 do módulo apagado
    assert [e for e in console if "texto.js" not in e and "status of 404" not in e] == []


def test_mesmo_modulo_alterna_chrome_de_edicao_e_publicacao(page, base_url, console):
    abrir(page, base_url)
    resultado = page.evaluate("""() => {
      const motor = window.plat.widgets;
      const grade = document.querySelector('.plat-widgets');
      const tabela = document.querySelector('plat-w-tabela');
      const antes = tabela.querySelector('table');
      const publicado = {edicao: grade.hasAttribute('data-edicao'), foco: tabela.hasAttribute('tabindex'),
        rotulo: getComputedStyle(tabela, '::before').content};
      motor.edicao(true);
      const editando = {edicao: grade.hasAttribute('data-edicao'), foco: tabela.getAttribute('tabindex'),
        aria: tabela.getAttribute('aria-label'), rotulo: getComputedStyle(tabela, '::before').content,
        contorno: getComputedStyle(tabela).outlineStyle};
      motor.edicao(false);
      const devolta = {edicao: grade.hasAttribute('data-edicao'), foco: tabela.hasAttribute('tabindex'),
        mesmaTabela: tabela.querySelector('table') === antes,
        mesmaInstancia: motor.instancias.get(tabela.dataset.noId) === tabela};
      return {publicado, editando, devolta};
    }""")
    assert resultado["publicado"] == {"edicao": False, "foco": False, "rotulo": "none"}
    assert resultado["editando"] == {
        "edicao": True, "foco": "0", "aria": "widget tabela", "rotulo": '"tabela"', "contorno": "dashed"}
    assert resultado["devolta"] == {"edicao": False, "foco": False, "mesmaTabela": True, "mesmaInstancia": True}
    assert console == []
