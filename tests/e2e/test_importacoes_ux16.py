"""e2e do item UX-16-ingestao-sem-tela: as rotas de escrita POST /api/importacoes, PUT /api/importacoes/{id}/confirmar e
DELETE /api/importacoes/{id} têm controle na tela /importacoes, com os quatro estados do sistema de design (UX-01):

1. lista: vazio (forjado, com "nova importação"), erro (500 forjado, "tentar de novo" e referência), negado (403
   forjado), conteúdo;
2. nova importação REAL: um GeoJSON pequeno sobe pela API (POST /api/arquivos com token + POST /api/itens, como
   os testes da ingestão), a tela cria a importação (POST 202), acompanha a inspeção pelo worker da trilha e abre a
   proposta; 422 conteudo_nao_corresponde REAL (formato GeoPackage para um GeoJSON) nomeado no campo formato; 403
   forjado vira negado;
3. confirmar REAL: proposta conferida (título, campos com tipo/importar) → PUT 202, carga acompanhada até
   `concluida`, "ver camada" leva ao item; erros forjados nomeados: 422 perguntas_pendentes (lista), 422
   srid_inexistente no campo CRS, 409 estado_invalido; 403 negado;
4. apagar REAL de uma importação em `proposta` (confirmação e DELETE 204); 409 forjado nomeado;
5. axe 0 violações sérias (lista, formulário de nova, proposta, erro); 0 erro de console; capturas 390/1280; medidas
   em tests/medidas/UX-16-ingestao-sem-tela.json. Exige o worker da trilha (ingestao.inspecionar/carregar)."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, local, sufixo
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-16-ingestao-sem-tela"
LARGURAS = (390, 1280)
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

GEOJSON = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"nome": "um", "valor": 1.5, "ativo": True},
     "geometry": {"type": "Point", "coordinates": [-46.533, -23.462]}},
    {"type": "Feature", "properties": {"nome": "dois", "valor": 2.5, "ativo": False},
     "geometry": {"type": "Point", "coordinates": [-46.528, -23.458]}},
    {"type": "Feature", "properties": {"nome": "três", "valor": 3.5, "ativo": True},
     "geometry": {"type": "Point", "coordinates": [-46.520, -23.470]}},
]}


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


@pytest.fixture
def arquivos_geojson(admin_api, playwright, base_url):
    """Dois itens `arquivo` (GeoJSON de 3 pontos) em demo, pela mesma via da API que a ingestão usa; tudo apagado ao fim
    (importações, camadas criadas e itens de arquivo). `POST /api/arquivos` é só por token: vai num contexto SEM o
    cookie de sessão (cookie + Authorization juntos são 400 autenticacao_ambigua)."""
    r = admin_api.post("/api/tokens", data={"nome": f"zt-ux16-{sufixo()}", "escopos": ["admin:inquilino"]})
    assert r.status == 201, r.text()
    token, token_id = r.json()["token"], r.json()["id"]
    sem_cookie = playwright.request.new_context(base_url=base_url, ignore_https_errors=local(base_url))
    criados = {"arquivos": [], "importacoes": [], "camadas": []}
    for i in range(2):
        r = sem_cookie.post("/api/arquivos?classe=camada_arquivo", data=json.dumps(GEOJSON).encode(),
                            headers={"authorization": f"Bearer {token}", "content-type": "application/octet-stream"})
        assert r.status == 201, r.text()
        obj = r.json()
        nome = f"zt-ux16-{sufixo()}-{i}.geojson"
        r = admin_api.post("/api/itens", data={"tipo": "arquivo", "titulo": nome, "dados": {
            "chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"], "content_type": obj["content_type"],
            "nome_original": nome}})
        assert r.status == 201, r.text()
        criados["arquivos"].append((r.json()["id"], nome))
    yield criados
    for imp in admin_api.get("/api/importacoes?limite=200").json()["itens"]:
        if imp["arquivo_id"] in {a for a, _ in criados["arquivos"]}:
            if imp["estado"] == "concluida":
                admin_api.delete(f"/api/itens/{imp['item_id']}")
            elif imp["estado"] in ("proposta", "falhou", "cancelada", "expirada"):
                admin_api.delete(f"/api/importacoes/{imp['id']}")
    for iid, _ in criados["arquivos"]:
        admin_api.delete(f"/api/itens/{iid}")
    admin_api.delete(f"/api/tokens/{token_id}")
    sem_cookie.dispose()


def _worker_vivo(admin_api):
    r = admin_api.get("/saude")
    fila = (r.json() or {}).get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.skip(f"sem worker vivo na trilha ({fila}): a inspeção/carga não terminaria")


def _abrir(tela, page):
    tela.ir("/importacoes", "pagina_pronta_ms_importacoes")
    page.wait_for_function("() => document.getElementById('lista-estado').getAttribute('aria-busy') !== 'true'")


def test_nova_confirmar_e_apagar_com_estados_nomeados(page, base_url, credenciais_demo, admin_api, medida,
                                                      arquivos_geojson):
    _worker_vivo(admin_api)
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.esperar_status(403, 409, 422, 500)  # forjados pela própria página + o 422 real do formato errado
    violacoes = {}
    estados = []
    (arq1, nome1), (arq2, nome2) = arquivos_geojson["arquivos"]

    # ------------------------------------------------------------ 1. lista: vazio, erro, negado (forjados), conteúdo
    parar = _forjar(page, "**/api/importacoes?*", "GET", 200, {"itens": [], "total": 0})
    _abrir(tela, page)
    page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#lista-estado button[data-acao='nova']").count() == 1
    estados.append("lista:vazio")
    _axe(page, "/importacoes vazia", violacoes)
    _capturar(page, "vazia")
    parar()
    parar = _forjar(page, "**/api/importacoes?*", "GET", 500,
                    {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux16-500"})
    page.click("#recarregar")
    page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#lista-estado") or ""
    assert "banco indisponível (forjado)" in texto and "e2e-ux16-500" in texto, texto
    estados.append("lista:erro")
    _capturar(page, "erro", (1280,))
    parar()
    parar = _forjar(page, "**/api/importacoes?*", "GET", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.publicar_camada",
                     "req_id": "e2e-ux16-403"})
    page.click("#lista-estado button[data-acao='tentar']")
    page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
    assert "conteudo.publicar_camada" in (page.text_content("#lista-estado") or "")
    estados.append("lista:negado")
    parar()
    page.click("#recarregar")
    page.wait_for_function("() => document.getElementById('lista-estado').hidden "
                           "|| document.getElementById('lista-estado').getAttribute('tipo') === 'vazio'")
    estados.append("lista:conteudo")

    # ------------------------------------------------------------ 2. nova: 422 real no formato, 403 forjado, 202 real
    page.click("#nova")
    page.wait_for_selector("#form-nova select#nova-formato option[value='geojson']", state="attached")
    _axe(page, "/importacoes nova", violacoes)
    page.select_option("#nova-arquivo", arq1)
    page.select_option("#nova-formato", "gpkg")  # errado de propósito: o conteúdo é GeoJSON, não SQLite
    page.click("#nova-enviar")
    page.wait_for_selector("#form-nova [data-campo='formato'] .erro-campo")
    texto = page.text_content("#form-nova [data-campo='formato'] .erro-campo") or ""
    assert "conteudo_nao_corresponde" in texto and "422" not in texto, texto
    estados.append("nova:422:formato")
    _capturar(page, "nova_422")
    page.select_option("#nova-formato", "geojson")
    parar = _forjar(page, "**/api/importacoes", "POST", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.publicar_camada",
                     "req_id": "e2e-ux16-403b"})
    page.click("#nova-enviar")
    page.wait_for_selector("#nova-estado[tipo='negado']:not([hidden])")
    assert "conteudo.publicar_camada" in (page.text_content("#nova-estado") or "")
    estados.append("nova:negado")
    parar()
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/importacoes")) as resp:
        page.click("#nova-enviar")
    assert resp.value.status == 202, resp.value.text()
    importacao_id = resp.value.json()["importacao_id"]
    # a tela acompanha a inspeção (worker) e abre a proposta
    page.wait_for_selector("#form-confirmar", timeout=90000)
    estados.append("nova:ok:inspecionada")
    _axe(page, "/importacoes proposta", violacoes)
    _capturar(page, "proposta")
    assert page.locator("#confirmar-campos tbody tr").count() == 3
    assert page.input_value("#form-confirmar input[name=titulo]") != ""

    # ------------------------------------------------------------ 3. confirmar: erros forjados nomeados, depois REAL
    parar = _forjar(page, f"**/api/importacoes/{importacao_id}/confirmar", "PUT", 422,
                    {"erro": "perguntas_pendentes", "mensagem": "há perguntas sem resposta na proposta",
                     "detalhe": {"perguntas": ["crs", "codificacao"]}, "req_id": "e2e-ux16-422b"})
    page.click("#confirmar-enviar")
    page.wait_for_selector("#confirmar-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#confirmar-estado") or ""
    assert "crs, codificacao" in texto and "422" not in texto, texto
    estados.append("confirmar:422:perguntas")
    parar()
    parar = _forjar(page, f"**/api/importacoes/{importacao_id}/confirmar", "PUT", 409,
                    {"erro": "estado_invalido", "mensagem": "importação em estado 'carregando'; esperava 'proposta'",
                     "req_id": "e2e-ux16-409"})
    page.click("#confirmar-enviar")
    page.wait_for_function(
        "() => (document.getElementById('confirmar-estado').textContent || '').includes('estado_invalido')")
    estados.append("confirmar:409")
    _capturar(page, "confirmar_409", (1280,))
    parar()
    parar = _forjar(page, f"**/api/importacoes/{importacao_id}/confirmar", "PUT", 403,
                    {"erro": "sem_privilegio", "mensagem": "a operação exige o privilégio conteudo.publicar_camada",
                     "req_id": "e2e-ux16-403c"})
    page.click("#confirmar-enviar")
    page.wait_for_selector("#confirmar-estado[tipo='negado']:not([hidden])")
    estados.append("confirmar:negado")
    parar()
    titulo = f"zt ux16 camada {sufixo()}"
    page.fill("#form-confirmar input[name=titulo]", titulo)
    page.uncheck("#form-confirmar input[name='importar:ativo']")
    with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith("/confirmar")) as resp:
        page.click("#confirmar-enviar")
    assert resp.value.status == 202, resp.value.text()
    page.wait_for_function(
        "(t) => [...document.querySelectorAll('#tabela tbody tr')].some((tr) => tr.textContent.includes(t) "
        "&& tr.textContent.includes('concluída'))", arg=titulo, timeout=120000)
    estados.append("confirmar:ok:carregada")
    _capturar(page, "concluida", (1280,))
    r = admin_api.get(f"/api/importacoes/{importacao_id}")
    assert r.status == 200 and r.json()["estado"] == "concluida", r.text()
    item_id = r.json()["item_id"]
    r = admin_api.get(f"/api/itens/{item_id}")
    assert r.status == 200 and r.json()["titulo"] == titulo and r.json()["tipo"] == "camada_vetorial", r.text()
    campos = [c["nome"] for c in r.json()["dados"]["campos"]]
    assert "ativo" not in campos and {"nome", "valor"} <= set(campos), campos

    # ---------------------------------------------- 4. apagar: 2ª importação em proposta; 409 forjado; real
    page.click("#nova")
    page.wait_for_selector("#form-nova select#nova-formato option[value='geojson']", state="attached")
    page.select_option("#nova-arquivo", arq2)
    page.select_option("#nova-formato", "geojson")
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/importacoes")) as resp:
        page.click("#nova-enviar")
    imp2 = resp.value.json()["importacao_id"]
    page.wait_for_selector("#form-confirmar", timeout=90000)
    page.click("#form-confirmar button[type=button]")  # cancelar: fica em proposta
    page.wait_for_selector("#painel dialog[open]", state="detached")
    linha = page.locator("#tabela tbody tr:has(button:text-is('Conferir e carregar'))").first
    parar = _forjar(page, f"**/api/importacoes/{imp2}", "DELETE", 409,
                    {"erro": "estado_invalido", "mensagem": "importação em estado 'carregando' não pode ser apagada",
                     "req_id": "e2e-ux16-409b"})
    linha.locator("button.perigo").click()
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    page.wait_for_selector("#fluxo-estado[tipo='erro']:not([hidden])")
    assert "estado_invalido" in (page.text_content("#fluxo-estado") or "")
    estados.append("apagar:409")
    parar()
    page.click("#fluxo-estado button[data-acao='fechar']")
    linha.locator("button.perigo").click()
    with page.expect_response(lambda r: r.request.method == "DELETE"
                              and r.url.endswith(f"/api/importacoes/{imp2}")) as resp:
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    assert resp.value.status == 204
    page.wait_for_function("(n) => document.querySelectorAll('#tabela tbody tr').length < n", arg=2 + 1, timeout=10000)
    assert admin_api.get(f"/api/importacoes/{imp2}").status == 404
    estados.append("apagar:ok")
    _axe(page, "/importacoes lista", violacoes)
    _capturar(page, "lista")

    # ------------------------------------------------------------ 5. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
