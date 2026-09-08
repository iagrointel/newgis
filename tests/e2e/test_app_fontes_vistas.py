"""e2e do item L5-07-fontes-vistas-mensagens no chromium do playwright, contra a frente de teste sem nginx
(tests/e2e/frente_estatica.py serve /static/):

1. seleção no mapa filtra tabela e gráfico: 3 widgets (mapa, tabela, gráfico) sobre 2 VISTAS da MESMA fonte
   (um item `arquivo` GeoJSON com 12 municípios sintéticos, enviado por token de serviço); clicar numa feição do
   mapa muda a seleção da vista do mapa, a mensagem `selecao_mudou -> filtrar` refiltra a vista da tabela e do
   gráfico (1 linha, 1 barra);
2. filtro por atributo entre fontes DIFERENTES com relação declarada: uma segunda fonte (escolas, `cod_mun`) e
   uma tabela sobre ela; a mesma seleção no mapa filtra as escolas do município clicado (relação
   atributo cod -> cod_mun);
3. a URL copiada reabre com o mesmo filtro e a mesma seleção (novo contexto de navegador);
4. no construtor, mensagem entre fontes diferentes SEM relação é recusada com mensagem (`#mensagem-erro`,
   regra `relacao_ausente`) e não entra na lista; com relação por atributo entra; captura.
Latência p95 gatilho->ação com 10 mil feições é medida em node (tests/unit/test_app_modelo.py)."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L5-07-fontes-vistas-mensagens"
UFS = ["SP", "RJ", "MG"]


_LINHAS_TABELA = ("() => document.querySelectorAll('[data-tipo=tabela]')[{i}]"
                  ".querySelectorAll('tbody tr').length === {n}")

def _ulid(n: int) -> str:
    return "01K5" + str(n).zfill(22)


def _municipios() -> dict:
    feats = []
    for i in range(1, 13):
        feats.append({"type": "Feature", "id": i, "properties": {"cod": i, "nome": f"Município {i}", "uf": UFS[i % 3]},
                      "geometry": {"type": "Point", "coordinates": [-48 + (i % 4) * 0.5, -22 + (i // 4) * 0.5]}})
    return {"type": "FeatureCollection", "features": feats}


def _escolas() -> dict:
    feats = []
    n = 0
    for cod in range(1, 13):
        for k in range(cod % 3 + 1):
            n += 1
            feats.append({"type": "Feature", "id": n, "properties": {"cod_mun": cod, "escola": f"Escola {cod}-{k}"}})
    return {"type": "FeatureCollection", "features": feats}


def _enviar_geojson(playwright, base_url, token: str, nome: str, geojson: dict) -> dict:
    ctx = playwright.request.new_context(base_url=base_url)
    try:
        r = ctx.post("/api/arquivos?classe=arquivo", data=json.dumps(geojson).encode("utf-8"),
                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/geo+json"})
        assert r.status == 201, r.text()
        return r.json()
    finally:
        ctx.dispose()


def _item_arquivo(admin_api, titulo: str, obj: dict, nome: str) -> str:
    dados = {"chave": obj["chave"], "sha256": obj["sha256"], "bytes": obj["bytes"],
             "content_type": obj["content_type"], "nome_original": nome}
    r = admin_api.post("/api/itens", data={"tipo": "arquivo", "titulo": titulo, "dados": dados})
    assert r.status == 201, r.text()
    return r.json()["id"]


def _documento(mun_id: str, esc_id: str) -> dict:
    F1, F2, V1, V2, V3, W_MAPA, W_TAB, W_GRAF, W_TAB2, M1, M2 = (_ulid(i) for i in range(101, 112))
    return {
        "tipo": "app", "esquema_versao": 3,
        "corpo": {
            "nos": [
                {"id": W_MAPA, "tipo": "mapa", "posicao": {"coluna": 1, "linha": 1, "largura": 6, "altura": 2},
                 "configuracao": {"vista": V1, "rotulo": "municípios", "campo_rotulo": "nome", "altura": 260}},
                {"id": W_TAB, "tipo": "tabela", "posicao": {"coluna": 7, "linha": 1, "largura": 6, "altura": 1},
                 "configuracao": {"vista": V2, "colunas": [{"campo": "nome", "rotulo": "Município"},
                                                            {"campo": "uf", "rotulo": "UF"}]}},
                {"id": W_GRAF, "tipo": "grafico", "posicao": {"coluna": 7, "linha": 2, "largura": 6, "altura": 1},
                 "configuracao": {"vista": V2, "campo": "uf", "titulo": "por UF"}},
                {"id": W_TAB2, "tipo": "tabela", "posicao": {"coluna": 1, "linha": 3, "largura": 12, "altura": 1},
                 "configuracao": {"vista": V3, "colunas": [{"campo": "escola", "rotulo": "Escola"},
                                                            {"campo": "cod_mun", "rotulo": "Município"}]}},
            ],
            "ligacoes": [],
            "fontes": [
                {"id": F1, "nome": "municipios", "origem": {"tipo": "item", "item_id": mun_id},
                 "campos": [{"nome": "cod", "tipo": "inteiro"}, {"nome": "nome", "tipo": "texto"},
                            {"nome": "uf", "tipo": "texto"}, {"nome": "geometria", "tipo": "geometria"}]},
                {"id": F2, "nome": "escolas", "origem": {"tipo": "item", "item_id": esc_id},
                 "campos": [{"nome": "cod_mun", "tipo": "inteiro"}, {"nome": "escola", "tipo": "texto"}]},
            ],
            "vistas": [
                {"id": V1, "nome": "mapa", "fonte": F1, "filtro": None, "selecao": [], "ordenacao": [], "campos": None},
                {"id": V2, "nome": "lista", "fonte": F1, "filtro": None, "selecao": [],
                 "ordenacao": [{"campo": "cod", "direcao": "asc"}], "campos": None},
                {"id": V3, "nome": "escolas", "fonte": F2, "filtro": None, "selecao": [], "ordenacao": [],
                 "campos": None},
            ],
            "mensagens": [
                {"id": M1, "gatilho": {"origem": W_MAPA, "evento": "selecao_mudou"},
                 "acoes": [{"alvo": V2, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}},
                           {"alvo": W_GRAF, "acao": "piscar", "parametros": {}}]},
                {"id": M2, "gatilho": {"origem": W_MAPA, "evento": "selecao_mudou"},
                 "acoes": [{"alvo": V3, "acao": "filtrar", "parametros": {},
                            "relacao": {"tipo": "atributo", "campo_origem": "cod", "campo_alvo": "cod_mun",
                                        "operador": "in"}}]},
            ],
        },
    }


def test_selecao_no_mapa_filtra_tabela_grafico_e_outra_fonte_e_url_reabre(
    page, browser, browser_context_args, playwright, base_url, credenciais_demo, admin_api, medida,
):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    r = admin_api.post("/api/tokens", data={"nome": f"e2e-l507-{s}", "escopos": ["admin:inquilino"]})
    assert r.status == 201, r.text()
    token = r.json()["token"]
    token_id = r.json()["id"]
    criados = []
    try:
        mun = _enviar_geojson(playwright, base_url, token, "municipios.geojson", _municipios())
        esc = _enviar_geojson(playwright, base_url, token, "escolas.geojson", _escolas())
        mun_id = _item_arquivo(admin_api, f"e2e municípios {s}", mun, "municipios.geojson")
        esc_id = _item_arquivo(admin_api, f"e2e escolas {s}", esc, "escolas.geojson")
        criados += [mun_id, esc_id]
        corpo_app = {"tipo": "app", "titulo": f"e2e app fontes {s}", "dados": _documento(mun_id, esc_id)}
        r = admin_api.post("/api/itens", data=corpo_app)
        assert r.status == 201, r.text()
        app_id = r.json()["id"]
        criados.append(app_id)

        tela = Tela(page, base_url)
        tela.entrar(slug, admin_login, senha_admin, proximo=f"/aplicativo?item={app_id}")
        tela.medidas["pagina_pronta_ms_aplicativo"] = tela.ir(f"/aplicativo?item={app_id}")
        page.wait_for_function("() => document.querySelectorAll('plat-mapa .feicao').length === 12", timeout=15000)
        assert page.locator("[data-tipo='tabela']").nth(0).locator("tbody tr").count() == 12
        page.wait_for_selector("plat-grafico[data-pronto='1'][data-grupos='3']", timeout=15000)
        assert page.locator("[data-tipo='tabela']").nth(1).locator("tbody tr").count() == 24
        assert page.locator("#avisos-barramento p").count() == 0
        # 1. clique na feição cod=5 (UF RJ, 5 % 3 = 2 -> MG): tabela 1 linha, gráfico 1 barra, gráfico piscou
        page.locator("plat-mapa .feicao[data-id='5']").click()
        page.wait_for_function(_LINHAS_TABELA.format(i=0, n=1), timeout=15000)
        assert page.locator("[data-tipo='tabela']").nth(0).locator("tbody tr td").nth(0).text_content() == "Município 5"
        page.wait_for_selector("plat-grafico[data-grupos='1']", timeout=15000)
        assert page.evaluate("() => document.querySelector('plat-grafico').dados[0].valor") == UFS[5 % 3]
        assert page.locator("plat-mapa .feicao.selecionada").count() == 1
        # 2. relação por atributo entre fontes diferentes: escolas do município 5 (5 % 3 + 1 = 3 escolas)
        page.wait_for_function(_LINHAS_TABELA.format(i=1, n=3), timeout=15000)
        cod_mun = page.locator("[data-tipo='tabela']").nth(1).locator("tbody tr td:nth-child(2)").all_text_contents()
        assert all(td == "5" for td in cod_mun)
        # 3. a URL carrega o estado das 3 vistas; copiar e abrir noutro navegador reabre igual
        page.wait_for_function("() => location.search.includes('v.')", timeout=15000)
        url = page.url
        assert url.count("v.01K5") == 3, url
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_aplicativo.png"), full_page=True)
        ctx2 = browser.new_context(**browser_context_args)
        try:
            page2 = ctx2.new_page()
            tela2 = Tela(page2, base_url)
            tela2.entrar(slug, admin_login, senha_admin, proximo="/conta")
            page2.goto(url, wait_until="domcontentloaded")
            page2.wait_for_selector("body[data-pronto='1']", timeout=20000)
            page2.wait_for_function("() => document.querySelectorAll('plat-mapa .feicao').length === 12", timeout=15000)
            assert page2.locator("[data-tipo='tabela']").nth(0).locator("tbody tr").count() == 1
            assert page2.locator("[data-tipo='tabela']").nth(1).locator("tbody tr").count() == 3
            assert page2.locator("plat-mapa .feicao.selecionada").get_attribute("data-id") == "5"
            assert page2.locator("#avisos-barramento p").count() == 0  # o estado restaurado não redispara mensagens
            tela2.verificar()
        finally:
            ctx2.close()
        # 4. construtor: mensagem entre fontes diferentes sem relação é recusada com mensagem; com relação entra
        tela.ir(f"/construtor?item={app_id}")
        page.wait_for_selector("#painel-dados", timeout=15000)
        page.click("#painel-dados summary")  # painel recolhido por padrão
        assert page.locator("#lista-mensagens li").count() == 2
        assert page.get_attribute("#painel-dados", "data-erros") == "0"
        V3 = _ulid(105)
        W_MAPA = _ulid(106)
        page.select_option("#form-mensagem select[name='origem']", W_MAPA)
        page.select_option("#form-mensagem select[name='evento']", "clique")
        page.select_option("#form-mensagem select[name='alvo']", V3)
        page.select_option("#form-mensagem select[name='acao']", "filtrar")
        page.select_option("#form-mensagem select[name='relacao']", "")
        page.click("#mensagem-adicionar")
        page.wait_for_selector("#mensagem-erro:not([hidden])", timeout=10000)
        assert "exigem relação declarada" in page.text_content("#mensagem-erro")
        assert page.get_attribute("#mensagem-erro", "data-regra") == "relacao_ausente"
        assert page.locator("#lista-mensagens li").count() == 2
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_construtor.png"), full_page=True)
        # tipo que não casa (texto x inteiro) também é recusado
        page.select_option("#form-mensagem select[name='relacao']", "atributo")
        page.fill("#form-mensagem input[name='campo_origem']", "nome")
        page.fill("#form-mensagem input[name='campo_alvo']", "cod_mun")
        page.click("#mensagem-adicionar")
        page.wait_for_function("() => document.querySelector('#mensagem-erro').dataset.regra === 'relacao_tipos'",
                               timeout=10000)
        assert page.locator("#lista-mensagens li").count() == 2
        page.fill("#form-mensagem input[name='campo_origem']", "cod")
        page.click("#mensagem-adicionar")
        page.wait_for_function("() => document.querySelectorAll('#lista-mensagens li').length === 3", timeout=10000)
        assert page.get_attribute("#mensagem-erro", "hidden") is not None
        page.click("#salvar")
        page.wait_for_function("() => document.getElementById('estado-salvo').textContent.startsWith('gravado')",
                               timeout=15000)
        dados = admin_api.get(f"/api/itens/{app_id}").json()["dados"]
        assert len(dados["corpo"]["mensagens"]) == 3 and dados["esquema_versao"] == 3
        tela.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (apoio.py Tela.ir)")
        gravar("e2e_selecao_mapa_filtra_tabela_grafico_e_outra_fonte", 1, "fluxo",
               "tests/e2e/test_app_fontes_vistas.py: 12 municípios, 24 escolas, 3 vistas, 2 fontes")
    finally:
        for iid in reversed(criados):
            admin_api.delete(f"/api/itens/{iid}")
        admin_api.delete(f"/api/tokens/{token_id}")
