"""e2e /conteudo (ADR 0004 seção 15; item L0-03-catalogo): abas e vistas com captura, criar pasta e item pela tela,
editar título e tags em linha, compartilhar com o inquilino e por link (link anônimo 200 → revogar → 404), busca por
campo (com erro de sintaxe no cliente), favoritar, mover para pasta, apagar → lixeira → restaurar (mesmo uuid) →
apagar agora; 0 erro de console; medidas primeira_pintura_conteudo_ms, pagina_conteudo_ms e soma_modulos_kb.
Salta enquanto o OpenAPI da URL interna não lista as rotas do catálogo."""

import json
import re

import pytest

from tests.e2e.apoio import RAIZ, sufixo
from tests.e2e.apoio_catalogo import ROTAS_CATALOGO, TelaCatalogo, gravar_medidas_catalogo
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

TOKEN_NA_URL = re.compile(r"/c/([A-Za-z0-9_-]+)")


@pytest.fixture(scope="session")
def api_catalogo(api_auth):
    faltam = [r for r in ROTAS_CATALOGO if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (rotas do ADR 0004)")
    return api_auth


def _dialogo_aberto(page, id_):
    return page.locator(f"#{id_} dialog[open]")


def _limpar_aviso(page, seletor="#aviso"):
    """o aviso guarda o estado da ação anterior; limpar antes de esperar o 'ok' da próxima evita esperar um ok velho."""
    page.evaluate(f"() => document.querySelector('{seletor}')?.limpar()")


def test_conteudo_fluxo_completo(page, base_url, credenciais_demo, admin_api, api_catalogo, playwright, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    titulo = f"E2E mapa {s}"
    titulo_novo = f"E2E mapa {s} editado"
    nome_pasta = f"E2E pasta {s}"
    tela = TelaCatalogo(page, base_url)
    item_id = pasta_id = None
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")
        tela.medidas["pagina_conteudo_ms"] = tela.ir("/conteudo")
        fcp = tela.primeira_pintura_ms()
        tela.medidas["primeira_pintura_conteudo_ms"] = fcp if fcp is not None else tela.medidas["pagina_conteudo_ms"]
        tela.medidas["soma_modulos_kb"] = tela.soma_modulos_kb()
        assert tela.medidas["soma_modulos_kb"] <= 400, tela.medidas
        assert page.locator("#aba-meus[aria-selected='true']").count() == 1
        tela.capturar("lista")
        # vistas
        page.click("#vista-grade")
        page.wait_for_selector("#lista[data-vista='grade']", timeout=10000)
        tela.capturar("grade")
        page.click("#vista-lista")
        page.wait_for_selector("#lista[data-vista='lista']", timeout=10000)
        tela.capturar("vista_lista")
        page.click("#vista-tabela")
        page.wait_for_selector("#lista[data-vista='tabela']", timeout=10000)
        # pasta pela tela
        page.click("#pasta-nova")
        d = page.locator("plat-dialogo dialog[open]").last
        d.locator("input[name='nome']").fill(nome_pasta)
        _limpar_aviso(page, "#aviso")
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        arvore = tela.api("GET", "/api/pastas/arvore").json()
        planas = arvore if isinstance(arvore, list) else arvore.get("itens", [])
        pasta_id = next((p["id"] for p in planas if p["nome"] == nome_pasta), None)
        assert pasta_id, planas
        assert page.locator("#pastas .no[aria-current='true']", has_text=nome_pasta).count() == 1
        # de volta à raiz para criar o item fora da pasta (mover depois)
        page.locator("#pastas .no").first.click()
        # item pela tela: Novo item > Mapa em branco
        page.click("#novo-item")
        page.click("#novo-mapa")
        d = _dialogo_aberto(page, "painel-novo")
        d.locator("input[name='titulo']").fill(titulo)
        _limpar_aviso(page, "#aviso")
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        page.wait_for_selector("#painel dialog[open] #item-titulo", timeout=15000)
        assert page.text_content("#painel dialog[open] #item-titulo").strip() == titulo
        item_id = page.text_content("#painel dialog[open] #item-uuid").strip()
        assert re.fullmatch(r"[0-9a-f-]{36}", item_id), item_id
        assert page.url.endswith(f"/conteudo/{item_id}")
        tela.capturar("detalhe")
        # editar título em linha
        page.click("#painel dialog[open] button[data-campo='titulo']")
        d = _dialogo_aberto(page, "painel-editar")
        d.locator("input[name='titulo']").fill(titulo_novo)
        d.locator("button[type='submit']").click()
        page.wait_for_function(
            f"() => document.querySelector('#item-titulo')?.textContent.trim() === {json.dumps(titulo_novo)}",
            timeout=15000)
        # tags em linha
        page.click("#painel dialog[open] button[data-campo='tags']")
        page.fill("#tags-entrada", "ibge, e2e")
        page.click("#tags-salvar")
        page.wait_for_function(
            "() => document.querySelectorAll('#painel dialog[open] [data-campo=tags] .chip').length >= 2",
            timeout=15000)
        it = tela.api("GET", f"/api/itens/{item_id}").json()
        assert it["titulo"] == titulo_novo and sorted(it["tags"]) == ["e2e", "ibge"], it
        # a lista reflete a edição
        assert page.locator("#lista .titulo-item", has_text=titulo_novo).count() == 1
        # compartilhar: inquilino + link
        page.click("#item-compartilhar")
        d = _dialogo_aberto(page, "painel-compartilhar")
        d.locator("#acesso-inquilino").check()
        _limpar_aviso(page, "#compartilhar-aviso")
        d.locator("#compartilhar-aplicar").click()
        page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
        d.locator("#link-novo").click()
        d.locator("#link-form button[type='submit']").click()
        page.wait_for_selector("#link-url", timeout=15000)
        url_link = page.text_content("#link-url").strip()
        token = TOKEN_NA_URL.search(url_link).group(1)
        tela.capturar("compartilhar")
        anon = playwright.request.new_context(base_url=base_url)
        try:
            assert anon.get(f"/api/compartilhado/{token}").status == 200
            _limpar_aviso(page, "#compartilhar-aviso")
            d.locator("#links-tabela button", has_text="Revogar").first.click()
            page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
            assert anon.get(f"/api/compartilhado/{token}").status == 404
        finally:
            anon.dispose()
        page.keyboard.press("Escape")
        page.wait_for_selector("#painel-compartilhar dialog[open]", state="detached", timeout=5000)
        assert tela.api("GET", f"/api/itens/{item_id}").json()["acesso"] == "inquilino"
        # fechar o painel do item (URL volta a /conteudo)
        page.locator("#painel dialog[open] .fechar-x").click()
        page.wait_for_url(lambda u: u.rstrip("/").endswith("/conteudo"), timeout=10000)
        # busca por campo
        page.fill("#busca input", f"titulo:{s} tipo:mapa")
        page.press("#busca input", "Enter")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#lista .titulo-item')]"
            f".some(a => a.textContent.includes({json.dumps(s)}))", timeout=15000)
        tela.capturar("busca")
        page.fill("#busca input", "foo:bar")
        page.press("#busca input", "Enter")
        page.wait_for_selector("#busca-erro:not([hidden])", timeout=5000)
        page.fill("#busca input", f"zzz{s}semresultado")
        page.press("#busca input", "Enter")
        page.wait_for_selector("#lista .vazio", timeout=15000)
        tela.capturar("vazio")
        page.fill("#busca input", "")
        page.press("#busca input", "Enter")
        page.wait_for_function("() => !document.querySelector('#lista .vazio')", timeout=15000)
        # favoritar pela linha e ver na aba Favoritos
        linha = page.locator("#lista tr", has_text=titulo_novo)
        linha.locator("button.favorito").click()
        page.wait_for_function(
            f"() => document.querySelector('#lista tr[data-id={json.dumps(item_id)}] button.favorito')"
            "?.getAttribute('aria-pressed') === 'true'", timeout=10000)
        page.click("#aba-favoritos")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=15000)
        tela.capturar("favoritos")
        page.click("#aba-inquilino")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=15000)
        tela.capturar("inquilino")
        page.click("#aba-meus")
        page.wait_for_selector(f"#lista tr[data-id='{item_id}']", timeout=15000)
        # mover para a pasta pelo menu do item
        page.locator(f"#lista tr[data-id='{item_id}'] .titulo-item").click()
        page.wait_for_selector("#painel dialog[open] #item-mais", timeout=15000)
        page.click("#item-mais")
        page.click("#item-mover")
        d = page.locator("plat-dialogo dialog[open]").last
        _limpar_aviso(page, "#item-aviso")
        d.locator("select[name='pasta_id']").select_option(pasta_id)
        d.locator("button[type='submit']").click()
        page.wait_for_selector("#item-aviso[data-tipo='ok']", timeout=15000)
        it = tela.api("GET", f"/api/itens/{item_id}").json()
        assert it["pasta"] and it["pasta"]["id"] == pasta_id and it["id"] == item_id, it
        # apagar -> lixeira -> restaurar (mesmo uuid) -> apagar de novo -> apagar agora
        _limpar_aviso(page, "#aviso")
        page.click("#item-mais")
        page.click("#item-apagar")
        page.wait_for_selector("#painel-editar dialog[open] .dialogo-botoes button", timeout=15000)
        page.locator("#painel-editar dialog[open] .dialogo-botoes button", has_text="Apagar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        tela.esperar_status(404)
        assert tela.api("GET", f"/api/itens/{item_id}").status == 404
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({json.dumps(titulo_novo)})", timeout=15000)
        assert page.locator("#lixeira-tabela tbody tr", has_text=titulo_novo).count() == 1
        tela.capturar("lixeira")
        _limpar_aviso(page, "#aviso")
        page.locator("#lixeira-tabela tbody tr", has_text=titulo_novo).locator("button", has_text="Restaurar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        it = tela.api("GET", f"/api/itens/{item_id}").json()
        assert it["id"] == item_id and it["acesso"] == "inquilino", it
        assert tela.api("DELETE", f"/api/itens/{item_id}").status == 204
        page.click("#aba-meus")
        page.click("#aba-lixeira")
        page.wait_for_selector(f"#lixeira-tabela tbody tr:has-text({json.dumps(titulo_novo)})", timeout=15000)
        linha_lix = page.locator("#lixeira-tabela tbody tr", has_text=titulo_novo)
        _limpar_aviso(page, "#aviso")
        linha_lix.locator("button", has_text="Apagar agora").click()
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button", has_text="Apagar agora").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        item_id = None
        tela.verificar()
        gravar_medidas_catalogo(medida, tela)
    finally:
        if item_id:
            admin_api.delete(f"/api/itens/{item_id}")
            admin_api.post("/api/lixeira/esvaziar", data={"ids": [item_id]})
        if pasta_id:
            admin_api.delete(f"/api/pastas/{pasta_id}")


def test_conteudo_sem_chave_crua(page, base_url, credenciais_demo, api_catalogo):
    """nenhum texto visível de /conteudo, /conteudo/lixeira e do painel do item é chave crua do dicionário."""
    slug, admin_login, senha_admin = credenciais_demo
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    chaves, espacos = set(dic), {k.split(".")[0] for k in dic}
    tela = TelaCatalogo(page, base_url)
    tela.entrar(slug, admin_login, senha_admin, proximo="/conteudo")
    r = tela.api("GET", "/api/privilegios")
    privilegios = {p["nome"] for p in r.json()} if r.status == 200 else set()
    problemas = {}
    tela.ir("/conteudo")
    page.click("#busca-ajuda-botao")
    page.click("#coluna-filtros summary") if not page.locator("#coluna-filtros[open]").count() else None
    problemas["/conteudo"] = _cruas(_texto(page), chaves, espacos, privilegios)
    page.click("#aba-lixeira")
    page.wait_for_selector("#lixeira-area:not([hidden])", timeout=10000)
    problemas["/conteudo/lixeira"] = _cruas(_texto(page), chaves, espacos, privilegios)
    page.click("#aba-meus")
    primeiro = page.locator("#lista .titulo-item").first
    if primeiro.count():
        primeiro.click()
        page.wait_for_selector("#painel dialog[open] #item-abas", timeout=15000)
        for aba in ("dados", "config", "versoes", "relacoes", "compartilhamento"):
            page.click(f"#item-aba-{aba}")
            problemas[f"/conteudo/<id>#{aba}"] = _cruas(_texto(page), chaves, espacos, privilegios)
    ruins = {k: v for k, v in problemas.items() if v}
    assert ruins == {}, ruins
    tela.verificar()
