"""e2e do painel de ajuda por contexto (item L7-04-a-manual-capturas-geradas): toda tela com layout
declara data-ajuda="<chave>", o botão Ajuda abre o painel na seção da tela, Esc fecha, a busca do
painel devolve a seção certa para 20 perguntas (mesma função window.platAjuda.buscar que a interface
usa) e o seletor de idioma do painel troca pt-BR/en/es. Medidas: ajuda_abrir_ms, ajuda_busca_20_ms."""

import time

import pytest

from tests.e2e.apoio import Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

# 20 perguntas de usuário (termos do próprio manual) e a seção que tem de vir em primeiro lugar
PERGUNTAS = [
    ("versão", "inicio"),
    ("bloqueio", "entrar"),
    ("login", "entrar"),
    ("totp", "conta"),
    ("sessões abertas", "conta"),
    ("senha temporária", "usuarios"),
    ("convidar", "usuarios"),
    ("entrada por regra", "grupos"),
    ("participantes", "grupos"),
    ("privilégios", "papeis"),
    ("escopo", "tokens"),
    ("validade", "tokens"),
    ("auditoria", "log"),
    ("favoritos", "conteudo"),
    ("expurgar", "lixeira"),
    ("metadado", "conteudo-item"),
    ("retomar", "uploads"),
    ("cancelar", "tarefas"),
    ("pmtiles", "mapa"),
    ("arrastar", "construtor"),
]


def _secoes(page) -> dict[str, dict]:
    r = page.request.get("/static/dados/manual.json")
    assert r.status == 200, r.status
    return {s["id"]: s for s in r.json()["secoes"]}


def _abrir_painel(page, tela: Tela) -> None:
    page.click("#botao-ajuda")
    page.wait_for_selector("#painel-ajuda:not([hidden])", timeout=10000)
    page.wait_for_selector(".ajuda-item", timeout=10000)


def test_ajuda_por_contexto_telas_busca_e_idioma(page, base_url, credenciais_demo, medida):
    secoes = _secoes(page)
    slug, admin_login, senha_admin = credenciais_demo
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/")

        # caminhos concretos do manual (a ficha /conteudo/{id} é coberta pela validação estrutural)
        caminhos = sorted(
            (s["caminho"], s) for s in secoes.values()
            if "{" not in s["caminho"] and s["caminho"] != "/entrar"
        )
        assert len(caminhos) >= 13, [c for c, _ in caminhos]
        abriu_ms = None
        for caminho, secao in caminhos:
            tela.ir(caminho)
            assert page.get_attribute("body", "data-ajuda") == secao["id"], (caminho, secao["id"])
            t0 = time.perf_counter()
            _abrir_painel(page, tela)
            if abriu_ms is None:
                abriu_ms = round((time.perf_counter() - t0) * 1000, 1)
            atual = page.locator(".ajuda-item.atual")
            assert atual.count() == 1, (caminho, atual.count())
            # o botão da seção tem o título no 1º nó de texto e o resumo num <small> filho
            titulo_item = page.evaluate("document.querySelector('.ajuda-item.atual').childNodes[0].textContent.trim()")
            assert titulo_item == secao["titulo"], (caminho, titulo_item, secao["titulo"])
            assert page.locator("#ajuda-conteudo > h3:first-child").text_content().strip() == secao["titulo"]
            page.keyboard.press("Escape")
            page.wait_for_selector("#painel-ajuda", state="hidden", timeout=10000)

        # busca: 20 perguntas pela MESMA função que a interface usa, no navegador
        t0 = time.perf_counter()
        erros = page.evaluate(
            """(pares) => pares.flatMap(([consulta, esperado]) => {
                 const r = window.platAjuda.buscar(consulta, 'pt-BR');
                 if (!r.length) return [`${consulta}: sem resultado`];
                 if (r[0].secao.id !== esperado) return [`${consulta}: 1º=${r[0].secao.id} esperado=${esperado}`];
                 return [];
               })""",
            PERGUNTAS,
        )
        busca_20_ms = round((time.perf_counter() - t0) * 1000, 1)
        assert erros == [], erros

        # a mesma busca digitada de verdade no painel, na tela Conteúdo
        tela.ir("/conteudo")
        _abrir_painel(page, tela)
        page.fill("#ajuda-busca", "favoritos")
        page.wait_for_function(
            "() => document.querySelector('.ajuda-item') && document.querySelector('.ajuda-item')"
            ".childNodes[0].textContent.trim() === 'Conteúdo'", timeout=10000)

        # idioma: o seletor do painel troca o título da seção (en -> es -> pt-BR)
        page.select_option("#ajuda-idioma", "en")
        page.wait_for_function(
            "() => document.querySelector('#ajuda-conteudo > h3') &&"
            " document.querySelector('#ajuda-conteudo > h3').textContent.trim() === 'Content'", timeout=10000)
        page.select_option("#ajuda-idioma", "es")
        page.wait_for_function(
            "() => document.querySelector('#ajuda-conteudo > h3') &&"
            " document.querySelector('#ajuda-conteudo > h3').textContent.trim() === 'Contenido'", timeout=10000)
        page.select_option("#ajuda-idioma", "pt-BR")
        page.wait_for_function(
            "() => document.querySelector('#ajuda-conteudo > h3') &&"
            " document.querySelector('#ajuda-conteudo > h3').textContent.trim() === 'Conteúdo'", timeout=10000)

        # busca em en/es pelos campos traduzidos do manual (título e palavras)
        assert page.evaluate("window.platAjuda.buscar('trash', 'en')[0].secao.id") == "lixeira"
        assert page.evaluate("window.platAjuda.buscar('drag', 'en')[0].secao.id") == "construtor"
        assert page.evaluate("window.platAjuda.buscar('papelera', 'es')[0].secao.id") == "lixeira"
        assert page.evaluate("window.platAjuda.buscar('arrastrar', 'es')[0].secao.id") == "construtor"

        tela.verificar()
        gravar = medida("L7-04-a-manual-capturas-geradas")
        gravar("ajuda_abrir_ms", abriu_ms, "ms",
               "clique em #botao-ajuda até .ajuda-item visível no chromium do playwright")
        gravar("ajuda_busca_20_ms", busca_20_ms, "ms",
               "window.platAjuda.buscar com 20 perguntas no chromium do playwright")
    finally:
        try:
            page.evaluate("localStorage.removeItem('plat.idioma')")
        except Exception:
            pass
