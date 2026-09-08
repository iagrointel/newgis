"""e2e do item UX-12-categorias-sem-controle: as rotas de escrita PUT /api/categorias e POST /api/categorias/importar
têm controle na tela /admin/categorias, com os quatro estados do sistema de design (UX-01):

1. lista: carregando (esqueleto), conteúdo, erro (500 forjado pela própria página, "tentar de novo"), negado (403
   forjado); vazio provado com a árvore de um inquilino sem categorias (forjado) e a ação "importar modelo";
2. PUT /api/categorias pelo editor: cria raiz + filha, reordena, salva DE VERDADE e confere por GET; erros da API
   nomeados no controle — 409 categoria_em_uso lista os caminhos com itens, 422 limite_categorias com os números,
   403 negado (forjados) — nunca "422" cru nem tela quebrada (refutação);
3. POST /api/categorias/importar pelo botão: importa ISO 19115 DE VERDADE (19 criadas ou já existentes), toast e
   contagem; 403 forjado vira negado;
4. axe 0 violações sérias (lista, erro, editor com nós); 0 erro de console; capturas 390/1280; medidas em
   tests/medidas/UX-12-categorias-sem-controle.json. A árvore original do inquilino é restaurada ao fim (PUT)."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-12-categorias-sem-controle"
LARGURAS = (390, 1280)
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def _axe(page, onde, acumulado):
    graves = serias(page)
    acumulado[onde] = len(graves)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _forjar(page, padrao, metodo, status, corpo, vezes=1):
    restantes = {"n": vezes}

    def rota(route):
        if route.request.method != metodo or restantes["n"] <= 0:
            route.fallback()
            return
        restantes["n"] -= 1
        route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    page.route(padrao, rota)
    return lambda: page.unroute(padrao, rota)


def _sem_extras(no):
    return {"id": no["id"], "nome": no["nome"], "codigo": no.get("codigo"),
            "filhas": [_sem_extras(f) for f in no["filhas"]]}


@pytest.fixture
def arvore_original(admin_api):
    r = admin_api.get("/api/categorias")
    assert r.status == 200, r.text()
    original = r.json()["arvore"]
    yield original
    # restaura: nós criados pelo teste (sem itens) somem; os originais ficam com os mesmos ids
    r = admin_api.put("/api/categorias", data={"arvore": [_sem_extras(n) for n in original]})
    assert r.status == 200, r.text()


def _abrir(tela, page):
    tela.ir("/admin/categorias", "pagina_pronta_ms_categorias")
    page.wait_for_function("() => !document.getElementById('categorias-estado').getAttribute('aria-busy') "
                           "|| document.getElementById('categorias-estado').getAttribute('aria-busy') === 'false'")


def test_estados_editor_e_importacao(page, base_url, credenciais_demo, admin_api, medida, arvore_original):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    violacoes = {}
    estados = []

    # ------------------------------------------------------------ 1. lista: vazio (forjado), erro, negado, conteúdo
    parar = _forjar(page, "**/api/categorias", "GET", 200, {"arvore": [], "total": 0, "maximo": 200})
    _abrir(tela, page)
    page.wait_for_selector("#categorias-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#categorias-estado button[data-acao='importar']").count() == 1
    estados.append("lista:vazio")
    _axe(page, "/admin/categorias vazia", violacoes)
    _capturar(page, "vazia")
    parar()
    parar = _forjar(page, "**/api/categorias", "GET", 500,
                    {"erro": "erro_forjado", "mensagem": "falha forjada pelo teste", "req_id": "e2e-500"})
    tela.esperar_status(500)
    page.click("#recarregar")
    page.wait_for_selector("#categorias-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#categorias-estado")
    assert "falha forjada pelo teste" in texto and "e2e-500" in texto, texto
    estados.append("lista:erro")
    _axe(page, "/admin/categorias em erro", violacoes)
    _capturar(page, "erro", (1280,))
    parar()
    parar = _forjar(page, "**/api/categorias", "GET", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.categorias",
                     "req_id": "e2e-403"})
    tela.esperar_status(403)
    page.click("#categorias-estado button[data-acao='tentar']")
    page.wait_for_selector("#categorias-estado[tipo='negado']:not([hidden])")
    assert "conteudo.categorias" in page.text_content("#categorias-estado")
    estados.append("lista:negado")
    _capturar(page, "negada", (1280,))
    parar()
    page.click("#recarregar")  # sem nada sujo, recarrega direto: a árvore real do inquilino
    page.wait_for_function("() => document.getElementById('categorias-estado').hidden "
                           "|| document.getElementById('categorias-estado').getAttribute('tipo') === 'vazio'")
    estados.append("lista:conteudo")

    # ------------------------------------------------------------ 2. editor: raiz + filha, reordenar, salvar de verdade
    nome_raiz = f"zt ux12 {sufixo()}"
    page.click("#nova-raiz")
    page.wait_for_function("() => document.getElementById('salvar').disabled === false")
    ultimo = page.locator("#arvore > li.categoria").last
    ultimo.locator("input.categoria-nome").fill(nome_raiz)
    ultimo.locator("button[data-nova-filha]").click()
    page.wait_for_selector("#arvore > li.categoria:last-child .categorias-sub li")
    page.locator("#arvore > li.categoria").last.locator(".categorias-sub input.categoria-nome") \
        .fill(f"{nome_raiz} filha")
    # sobe a nova raiz uma posição (fica antes da penúltima), se houver mais de uma
    n_raizes = page.locator("#arvore > li.categoria").count()
    if n_raizes > 1:
        page.locator("#arvore > li.categoria").last.locator("button[aria-label='subir']").click()
        page.wait_for_function("(nome) => [...document.querySelectorAll("
                               "'#arvore > li.categoria > .categoria-linha input')].at(-2).value === nome",
                               arg=nome_raiz)
    _axe(page, "/admin/categorias editor", violacoes)
    _capturar(page, "editor")
    # erros forjados no salvar, nomeados no controle
    parar = _forjar(page, "**/api/categorias", "PUT", 409,
                    {"erro": "categoria_em_uso",
                     "mensagem": "categoria com itens não se remove; tire-a dos itens antes",
                     "detalhe": [{"id": "x", "caminho": "Geologia / Solos", "itens": 7}], "req_id": "e2e-409"})
    tela.esperar_status(409)
    page.click("#salvar")
    page.wait_for_selector("#salvar-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#salvar-estado")
    assert "Geologia / Solos" in texto and "7 item" in texto and "e2e-409" in texto, texto
    estados.append("salvar:erro:409")
    _capturar(page, "salvar_409", (1280,))
    parar()
    parar = _forjar(page, "**/api/categorias", "PUT", 422,
                    {"erro": "limite_categorias", "mensagem": "no máximo 200 categorias por inquilino",
                     "detalhe": {"total": 201, "maximo": 200}, "req_id": "e2e-422"})
    tela.esperar_status(422)
    page.click("#salvar-estado button[data-acao='tentar']")
    page.wait_for_function("() => (document.getElementById('salvar-estado').textContent || '').includes('e2e-422')")
    texto = page.text_content("#salvar-estado")
    assert "201 de 200" in texto and "no máximo 200" in texto, texto
    estados.append("salvar:erro:422")
    _capturar(page, "salvar_422", (1280,))
    parar()
    parar = _forjar(page, "**/api/categorias", "PUT", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.categorias",
                     "req_id": "e2e-403b"})
    tela.esperar_status(403)
    page.click("#salvar")
    page.wait_for_selector("#salvar-estado[tipo='negado']:not([hidden])")
    assert "conteudo.categorias" in page.text_content("#salvar-estado")
    estados.append("salvar:negado")
    parar()
    # salvar de verdade
    page.click("#salvar")
    page.wait_for_function("() => document.getElementById('estado-edicao').textContent.includes('gravadas')")
    r = admin_api.get("/api/categorias")
    assert r.status == 200
    raizes = {n["nome"]: n for n in r.json()["arvore"]}
    assert nome_raiz in raizes and [f["nome"] for f in raizes[nome_raiz]["filhas"]] == [f"{nome_raiz} filha"]
    if n_raizes > 1:
        nomes = [n["nome"] for n in r.json()["arvore"]]
        assert nomes.index(nome_raiz) == len(nomes) - 2
    estados.append("salvar:ok")
    _capturar(page, "salvo", (1280,))

    # ------------------------------------------------------------ 3. importar modelo ISO 19115 (real) e 403 forjado
    parar = _forjar(page, "**/api/categorias/importar", "POST", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.categorias",
                     "req_id": "e2e-403c"})
    page.select_option("#modelo", "iso19115")
    page.click("#importar")
    page.wait_for_selector("#salvar-estado[tipo='negado']:not([hidden])")
    estados.append("importar:negado")
    parar()
    antes = admin_api.get("/api/categorias").json()["total"]
    page.click("#importar")
    page.wait_for_function("() => document.getElementById('importado').textContent.includes('iso19115')")
    texto = page.text_content("#importado")
    depois = admin_api.get("/api/categorias").json()
    codigos = {n.get("codigo") for n in depois["arvore"]}
    assert all(f"iso19115:{c}" in codigos for c in ("farming", "biota", "boundaries")), codigos
    assert depois["total"] >= antes
    assert "19" in texto, texto  # 19 criadas + 0 existentes, ou 0 criadas + 19 existentes
    estados.append("importar:ok")
    _axe(page, "/admin/categorias importada", violacoes)
    _capturar(page, "importada")

    # ------------------------------------------------------------ 4. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
