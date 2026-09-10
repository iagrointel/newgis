"""e2e do item UX-13-conexoes-sem-controle: as rotas de escrita POST /api/conexoes, PATCH /api/conexoes/{id} e
DELETE /api/conexoes/{id} têm controle na tela /conexoes (formulário de criar/editar e ação "apagar" da lista, com
confirmação) e os erros da API aparecem NOMEADOS no controle — nunca tela quebrada nem status cru (refutação):

1. lista: vazio (forjado, com a ação "nova conexão"), carregando, erro (500 forjado, "tentar de novo" e referência),
   negado (403 forjado), conteúdo;
2. POST pelo formulário: 403 sem_privilegio nomeia o privilégio na mensagem do formulário, 409 nome_existente cai no
   campo nome, 422 da validação (lista do pydantic) cai no campo apontado por `loc`, 422 config_grande_demais no campo
   config, 413 cota nomeada (todos forjados pela própria página); depois cria DE VERDADE e a linha aparece;
3. PATCH pelo formulário de edição: 403 sem_permissao nomeado, 422 url_insegura no campo endereço (forjados); depois
   salva DE VERDADE (nome novo na linha, conferido por GET);
4. DELETE pela ação da lista: diálogo de confirmação; 403 e 500 forjados nomeados no aviso da lista (role=alert, com
   referência); 404 forjado (apagada por outra pessoa) avisa e recarrega a lista; depois apaga DE VERDADE (linha
   some, GET dá 404);
5. axe 0 violações sérias (lista, formulário com erros, diálogo de apagar); 0 erro de console; capturas 390/1280;
   medidas em tests/medidas/UX-13-conexoes-sem-controle.json."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-13-conexoes-sem-controle"
LARGURAS = (390, 1280)
URL_404_ESTAVEL = "https://api.github.com/repos/inexistente-zt-e2e-ux13/tambem-inexistente"
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
    """derruba a próxima chamada `metodo` que case com `padrao` (as outras seguem para a API de verdade)."""
    restantes = {"n": vezes}

    def rota(route):
        if route.request.method != metodo or restantes["n"] <= 0:
            route.fallback()
            return
        restantes["n"] -= 1
        route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo),
                      headers={"X-Req-Id": corpo.get("req_id", "")})
    page.route(padrao, rota)
    return lambda: page.unroute(padrao, rota)


def _erro_campo(page, campo):
    sel = f"#conexao-form [data-campo='{campo}'] .erro-campo"
    page.wait_for_selector(sel)
    return page.text_content(sel) or ""


def _mensagem_form(page):
    sel = "#conexao-form plat-aviso:not([hidden])"
    page.wait_for_selector(sel)
    return page.text_content(sel) or ""


def _abrir_lista(tela, page):
    tela.ir("/conexoes", "pagina_pronta_ms_conexoes")
    page.wait_for_function("() => document.getElementById('lista').getAttribute('aria-busy') === 'false'")


def _preencher_nova(page, nome, url=URL_404_ESTAVEL):
    page.click("#conexao-nova")
    page.wait_for_selector("#conexao-form-caixa:not([hidden])")
    page.fill("#conexao-form input[name=nome]", nome)
    page.select_option("#conexao-form select[name=tipo]", "http")
    page.fill("#conexao-form input[name=url]", url)


def test_escrita_de_conexoes_nomeada_no_controle(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/conexoes")
    violacoes = {}
    estados = []
    nome = f"zt-ux13-{sufixo()}"
    criadas = []
    try:
        # ---------------------------------------------- 1. lista: vazio, erro, negado (forjados), conteúdo
        parar = _forjar(page, "**/api/conexoes", "GET", 200, {"itens": [], "total": 0})
        _abrir_lista(tela, page)
        page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
        assert page.locator("#lista-caixa").is_hidden()
        assert page.locator("#lista-estado button[data-acao='nova']").count() == 1
        estados.append("lista:vazio")
        _axe(page, "/conexoes vazia", violacoes)
        _capturar(page, "vazia")
        parar()
        parar = _forjar(page, "**/api/conexoes", "GET", 500,
                        {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux13-500"})
        tela.esperar_status(500)
        page.click("#lista-recarregar")
        page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
        texto = page.text_content("#lista-estado") or ""
        assert "banco indisponível (forjado)" in texto and "e2e-ux13-500" in texto, texto
        assert page.get_attribute("#lista-estado", "role") == "alert"
        estados.append("lista:erro")
        _capturar(page, "erro", (1280,))
        parar()
        parar = _forjar(page, "**/api/conexoes", "GET", 403,
                        {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.registrar_fonte",
                         "detalhe": {"exigido": "conteudo.registrar_fonte"}, "req_id": "e2e-ux13-403"})
        tela.esperar_status(403)
        page.click("#lista-estado button[data-acao='tentar']")
        page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
        assert "conteudo.registrar_fonte" in (page.text_content("#lista-estado") or "")
        estados.append("lista:negado")
        _capturar(page, "negada", (1280,))
        parar()
        page.click("#lista-recarregar")
        page.wait_for_function("() => document.getElementById('lista-estado').hidden "
                               "|| document.getElementById('lista-estado').getAttribute('tipo') === 'vazio'")
        estados.append("lista:conteudo")

        # ---------------------------------------------- 2. POST: erros nomeados no formulário, depois cria
        tela.esperar_status(409, 413, 422)  # forjados pela própria página, nos passos 2 e 3
        _preencher_nova(page, nome)
        parar = _forjar(page, "**/api/conexoes", "POST", 403,
                        {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.registrar_fonte",
                         "detalhe": {"exigido": "conteudo.registrar_fonte"}, "req_id": "e2e-ux13-403b"})
        page.click("#conexao-form button[type=submit]")
        texto = _mensagem_form(page)
        assert "conteudo.registrar_fonte" in texto and "403" not in texto, texto
        assert page.get_attribute("#conexao-form plat-aviso", "role") == "alert"
        estados.append("criar:negado")
        _capturar(page, "criar_negada", (1280,))
        parar()
        parar = _forjar(page, "**/api/conexoes", "POST", 409,
                        {"erro": "nome_existente", "mensagem": "já existe uma conexão com esse nome",
                         "req_id": "e2e-ux13-409"})
        page.click("#conexao-form button[type=submit]")
        texto = _erro_campo(page, "nome")
        assert "já existe" in texto and "409" not in texto, texto
        assert page.evaluate("() => document.activeElement.name") == "nome"
        estados.append("criar:erro:409")
        parar()
        parar = _forjar(page, "**/api/conexoes", "POST", 422,
                        {"erro": "validacao", "mensagem": "corpo inválido", "req_id": "e2e-ux13-422",
                         "detalhe": [{"loc": ["body", "url"], "msg": "endereço sem esquema reconhecido (forjado)",
                                      "type": "value_error"},
                                     {"loc": ["body", "nome"], "msg": "nome curto demais (forjado)",
                                      "type": "value_error"}]})
        page.click("#conexao-form button[type=submit]")
        assert "endereço sem esquema reconhecido (forjado)" in _erro_campo(page, "url")
        assert "nome curto demais (forjado)" in _erro_campo(page, "nome")
        assert "422" not in (page.text_content("#conexao-form") or "")
        estados.append("criar:erro:422")
        _axe(page, "/conexoes formulário com erros", violacoes)
        _capturar(page, "criar_422")
        parar()
        parar = _forjar(page, "**/api/conexoes", "POST", 422,
                        {"erro": "config_grande_demais", "mensagem": "config acima de 64 KiB",
                         "req_id": "e2e-ux13-422b"})
        page.click("#conexao-form button[type=submit]")
        assert "64 KiB" in _erro_campo(page, "config")
        estados.append("criar:erro:422:config")
        parar()
        parar = _forjar(page, "**/api/conexoes", "POST", 413,
                        {"erro": "cota_conexoes", "mensagem": "cota de conexões do inquilino atingida (50)",
                         "req_id": "e2e-ux13-413"})
        page.click("#conexao-form button[type=submit]")
        texto = _mensagem_form(page)
        assert "cota" in texto and "413" not in texto, texto
        estados.append("criar:erro:413")
        parar()
        with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/conexoes")) as resp:
            page.click("#conexao-form button[type=submit]")
        assert resp.value.status == 201, resp.value.text()
        cid = resp.value.json()["id"]
        criadas.append(cid)
        page.wait_for_selector("#conexao-form-caixa[hidden]", state="attached")
        linha = page.locator(f"#lista-corpo tr[data-id='{cid}']")
        linha.wait_for(timeout=10000)
        assert nome in linha.inner_text()
        assert "criada" in (page.text_content("#lista-aviso") or "")
        estados.append("criar:ok")
        _capturar(page, "criada", (1280,))

        # ------------------------------------------------------------ 3. PATCH: erros nomeados na edição, depois salva
        linha.locator("button.acao-editar").click()
        page.wait_for_selector("#conexao-form-caixa:not([hidden])")
        assert page.locator("#conexao-form select[name=tipo]").is_disabled()
        page.fill("#conexao-form input[name=nome]", f"{nome}-ed")
        parar = _forjar(page, "**/api/conexoes/*", "PATCH", 403,
                        {"erro": "sem_permissao", "mensagem": "só o dono da conexão ou conteudo.editar_tudo",
                         "req_id": "e2e-ux13-403c"})
        page.click("#conexao-form button[type=submit]")
        texto = _mensagem_form(page)
        assert "conteudo.editar_tudo" in texto and "403" not in texto, texto
        estados.append("editar:negado")
        _capturar(page, "editar_negada", (1280,))
        parar()
        parar = _forjar(page, "**/api/conexoes/*", "PATCH", 422,
                        {"erro": "url_insegura", "mensagem": "URL recusada: endereço interno (forjado)",
                         "detalhe": {"motivo": "endereço interno"}, "req_id": "e2e-ux13-422c"})
        page.click("#conexao-form button[type=submit]")
        texto = _erro_campo(page, "url")
        assert "endereço interno (forjado)" in texto and "422" not in texto, texto
        assert page.evaluate("() => document.activeElement.name") == "url"
        estados.append("editar:erro:422")
        parar()
        with page.expect_response(lambda r: r.request.method == "PATCH" and f"/api/conexoes/{cid}" in r.url) as resp:
            page.click("#conexao-form button[type=submit]")
        assert resp.value.status == 200, resp.value.text()
        page.wait_for_selector("#conexao-form-caixa[hidden]", state="attached")
        page.locator(f"#lista-corpo tr[data-id='{cid}']", has_text=f"{nome}-ed").wait_for(timeout=10000)
        r = admin_api.get(f"/api/conexoes/{cid}")
        assert r.status == 200 and r.json()["nome"] == f"{nome}-ed", r.text()
        estados.append("editar:ok")

        # ---------------------------------------------- 4. DELETE: confirmação, 403/500 nomeados, depois apaga
        linha = page.locator(f"#lista-corpo tr[data-id='{cid}']")
        parar = _forjar(page, "**/api/conexoes/*", "DELETE", 403,
                        {"erro": "sem_permissao", "mensagem": "só o dono da conexão ou conteudo.editar_tudo",
                         "req_id": "e2e-ux13-403d"})
        linha.locator("button.acao-apagar").click()
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for()
        assert f"{nome}-ed" in dialogo.inner_text()
        _axe(page, "/conexoes diálogo de apagar", violacoes)
        _capturar(page, "apagar_confirma", (1280,))
        dialogo.locator(".dialogo-botoes button.perigo").click()
        page.wait_for_selector("#lista-aviso[data-tipo='erro']:not([hidden])")
        texto = page.text_content("#lista-aviso") or ""
        assert "conteudo.editar_tudo" in texto and f"{nome}-ed" in texto and "403" not in texto, texto
        assert page.get_attribute("#lista-aviso", "role") == "alert"
        assert linha.count() == 1  # a linha continua: nada foi apagado
        estados.append("apagar:negado")
        _capturar(page, "apagar_negada", (1280,))
        parar()
        parar = _forjar(page, "**/api/conexoes/*", "DELETE", 500,
                        {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux13-500b"})
        linha.locator("button.acao-apagar").click()
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
        page.wait_for_function(
            "() => (document.getElementById('lista-aviso').textContent || '').includes('e2e-ux13-500b')")
        texto = page.text_content("#lista-aviso") or ""
        assert "banco indisponível (forjado)" in texto, texto
        estados.append("apagar:erro:500")
        parar()
        parar = _forjar(page, "**/api/conexoes/*", "DELETE", 404,
                        {"erro": "conexao_inexistente", "mensagem": "conexão inexistente", "req_id": "e2e-ux13-404"})
        tela.esperar_status(404)
        linha.locator("button.acao-apagar").click()
        with page.expect_response(lambda r: r.request.method == "GET" and r.url.endswith("/api/conexoes")):
            page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
        texto = page.text_content("#lista-aviso") or ""
        assert "já não existe" in texto and f"{nome}-ed" in texto and "404" not in texto, texto
        estados.append("apagar:ja_removida")
        parar()
        linha.locator("button.acao-apagar").click()
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
        page.wait_for_function("(id) => !document.querySelector(`#lista-corpo tr[data-id='${id}']`)",
                               arg=cid, timeout=10000)
        assert "apagada" in (page.text_content("#lista-aviso") or "")
        assert admin_api.get(f"/api/conexoes/{cid}").status == 404
        criadas.clear()
        estados.append("apagar:ok")
        _axe(page, "/conexoes lista ao fim", violacoes)
        _capturar(page, "apagada", (1280,))

        # ------------------------------------------------------------ 5. 0 erro de console; medidas
        tela.verificar()
        gravar = medida(ITEM)
        gravar("estados_provados", len(estados), "estados", "; ".join(estados))
        gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
               f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
        gravar("erros_de_console", 0, "erros",
               "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
        for nome_medida, valor in tela.medidas.items():
            gravar(nome_medida, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        for c in criadas:
            admin_api.delete(f"/api/conexoes/{c}")
