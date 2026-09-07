from pathlib import Path

import pytest

ITEM = "L5-06-motor-widgets"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_publicacao_carrega_so_os_tres_modulos_usados(page, base_url, medida):
    page.goto(f"{base_url}/aplicativo")
    page.wait_for_selector('body[data-pronto="1"]')
    assert page.locator("plat-texto, plat-filtro, plat-tabela").count() == 3
    assert page.locator("plat-tabela tbody tr").count() == 2
    page.locator("plat-filtro input").fill("rios")
    assert page.locator("plat-tabela tbody tr").count() == 1

    recursos = page.evaluate("""() => performance.getEntriesByType('resource').map((r) => ({
      nome: new URL(r.name).pathname, bytes: r.transferSize || r.encodedBodySize || 0
    }))""")
    modulos = [r for r in recursos if "/static/js/widgets/" in r["nome"]]
    nomes_widget = {Path(r["nome"]).name for r in modulos} & {
        "mapa.js", "legenda.js", "tabela.js", "texto.js", "botao.js", "filtro.js"
    }
    assert nomes_widget == {"tabela.js", "texto.js", "filtro.js"}

    pintura = page.evaluate("() => performance.getEntriesByType('paint').find((e) => e.name === 'first-contentful-paint')?.startTime || 0")
    bytes_widgets = sum(r["bytes"] for r in modulos if Path(r["nome"]).name in nomes_widget)
    gravar = medida(ITEM)
    gravar("primeira_pintura_ms", round(pintura, 1), "ms", "First Contentful Paint da página /aplicativo")
    gravar("kb_por_widget", round(bytes_widgets / 1024 / len(nomes_widget), 2), "kB", "transferência média dos três módulos usados")


def test_widget_desconhecido_e_configuracao_invalida_mostram_erro_nomeado(page, base_url):
    page.goto(f"{base_url}/aplicativo")
    page.wait_for_selector('body[data-pronto="1"]')
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
