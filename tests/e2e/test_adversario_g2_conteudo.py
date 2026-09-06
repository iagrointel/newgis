"""Achado de tela do adversário do grupo G2 (item L0-03-f, com efeito em L0-03-k).

Sequência medida em 06/09/2026 contra a base isolada da trilha adv2 (11.005 itens no inquilino demo):
abrir Conteúdo → abrir o painel de filtros → marcar uma faceta → limpar os filtros → clicar na estrela
da linha do item. O PUT /api/favoritos/{id} responde 204 e o servidor GRAVA o favorito, mas a lista é
recarregada por um GET /api/itens que já estava em voo e a linha volta com aria-pressed="false": a tela
mostra o item como NÃO favoritado. O clique seguinte manda outro PUT (não o DELETE que o usuário quer),
ou seja, a tela também não desfavorita. O e2e do próprio repositório para nisto
(tests/e2e/test_conteudo.py:181, determinístico em duas execuções).

Turno de conserto (trilha g2fix): a marca xfail saiu; o teste agora exige que a tela e o servidor concordem.

Este teste sobe sozinho o contexto do navegador (certificado autoassinado do harness local é aceito) e
é pulado quando não há --base-url apontando para uma instância viva.
"""

import time

import httpx
import pytest

RAIZ = "#lista tr[data-id='%s'] button.favorito"


@pytest.fixture
def credenciais_demo_adv2():
    import os
    from pathlib import Path

    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or "tests/credenciais.txt")
    if not caminho.exists():
        pytest.skip(f"sem {caminho}")
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        p = linha.split()
        if len(p) >= 3 and p[0] == "demo":
            return p[1], " ".join(p[2:])
    pytest.skip("sem linha de demo nas credenciais")


@pytest.fixture
def pagina_adv2(browser, base_url):
    try:
        httpx.get(f"{base_url}/saude", timeout=10, verify=False)
    except Exception as e:  # noqa: BLE001 — sem instância viva não há o que medir
        pytest.skip(f"{base_url} inacessível: {e}")
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, ignore_https_errors=True, locale="pt-BR")
    pagina = ctx.new_page()
    yield pagina
    ctx.close()


# ACHADO G2-9 (consertado): o clique na estrela registrava o favorito no servidor, mas a resposta de um
# GET /api/itens pedido ANTES do clique chegava depois e repintava a linha com o estado velho — a tela mostrava
# o contrário do que o servidor guardou e o clique seguinte repetia o PUT em vez de desfavoritar. Conserto em
# web/js/catalogo/contexto.js (marcaFavoritos/marcarFavoritoLocal/aplicarFavoritosLocais) e lista.js: a intenção
# é registrada antes da chamada, com número de ordem, e a lista reconcilia toda resposta pedida antes dela.
# O teste continua segurando a resposta do GET por 2 s para a corrida acontecer sempre.
def test_g2_9_favorito_na_lista_apos_ciclo_de_filtro(pagina_adv2, base_url, credenciais_demo_adv2):
    pagina, (login, senha) = pagina_adv2, credenciais_demo_adv2
    pagina.goto(f"{base_url}/entrar?inquilino=demo&proximo=/conteudo", wait_until="domcontentloaded")
    pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
    pagina.fill("#login", login)
    pagina.fill("#senha", senha)
    pagina.click("#entrar")
    pagina.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
    pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
    titulo = f"zt adv2 favorito {int(time.time())}"
    iid = pagina.evaluate(
        """async (t) => {
             const r = await fetch('/api/itens', {method: 'POST', headers: {'content-type': 'application/json'},
               body: JSON.stringify({tipo: 'mapa', titulo: t, dados: {esquema_versao: 1, corpo: {}}})});
             return (await r.json()).id; }""",
        titulo,
    )
    pagina.goto(f"{base_url}/conteudo", wait_until="domcontentloaded")
    pagina.wait_for_selector("body[data-pronto='1']", timeout=20000)
    pagina.wait_for_selector(f"#lista tr[data-id='{iid}']", timeout=20000)
    if not pagina.locator("#coluna-filtros[open]").count():
        pagina.click("#coluna-filtros summary")
    pagina.wait_for_selector("#filtros section.faceta input[type=checkbox]", timeout=20000)
    faceta = pagina.locator("#filtros section.faceta").first
    faceta.locator("input[type=checkbox]").first.check()
    pagina.wait_for_selector("#filtros .filtros-ativos .chip", timeout=15000)
    # a corrida é de tempo: para medi-la sempre, a resposta do GET /api/itens de "limpar filtros" é
    # segurada por 2 s (só a resposta; o pedido sai igual) e a estrela é clicada dentro dessa janela.
    def _segurar(rota):
        time.sleep(2)
        rota.continue_()

    pagina.route("**/api/itens?*", _segurar)
    pagina.click("#filtros-limpar")
    pagina.locator(RAIZ % iid).click()
    pagina.wait_for_timeout(5000)
    pagina.unroute("**/api/itens?*")
    no_servidor = pagina.evaluate(
        "async (i) => { const r = await fetch('/api/favoritos'); const j = await r.json(); "
        "return j.itens.some(x => x.id === i); }",
        iid,
    )
    na_tela = pagina.get_attribute(RAIZ % iid, "aria-pressed")
    assert (na_tela == "true") == no_servidor, f"tela diz aria-pressed={na_tela}, servidor diz favorito={no_servidor}"
