"""e2e do item L5-01-e-acoes-configuraveis (portão): o app "seleção no mapa → filtra tabela → gráfico → lista" é
montado SÓ pelo painel "Ações" do widget no construtor (nenhuma mensagem vem pronta no documento), com captura em
cada passo; a ação "exportar" do usuário gera um arquivo só com as feições FILTRADAS; erro nomeado no painel
(gatilho repetido, condição com campo inexistente). Os widgets e as fontes/vistas vêm pela API (é o que o L5-07 e o
L5-08 já provam); a "lista" é a tabela das escolas (o widget lista/cartões dedicado é o L5-01-c, em curso).
Servidor: tests/e2e/frente_estatica.py (Origin reescrito), sem nginx nem Martin."""

import csv
import io
import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo
from tests.e2e.test_app_fontes_vistas import _enviar_geojson, _escolas, _item_arquivo, _municipios, _ulid

ITEM = "L5-01-e-acoes-configuraveis"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]
UFS = ["SP", "RJ", "MG"]
_N_ACOES = "() => document.querySelectorAll('#lista-acoes li[data-mensagem]').length === {n}"
_LINHAS = "() => document.querySelectorAll('[data-tipo=tabela]')[{i}].querySelectorAll('tbody tr').length === {n}"
_PRIMEIRA = ("() => document.querySelectorAll('[data-tipo=tabela]')[0]"
             ".querySelector('tbody tr td').textContent === '{t}'")


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


def _documento_sem_mensagens(mun_id: str, esc_id: str) -> dict:
    F1, F2, V1, V2, V3, W_MAPA, W_TAB, W_GRAF, W_LISTA = (_ulid(i) for i in range(201, 210))
    return {
        "tipo": "app", "esquema_versao": 3,
        "corpo": {
            "nos": [
                {"id": W_MAPA, "tipo": "mapa", "largura_colunas": 6,
                 "posicao": {"coluna": 1, "linha": 1, "largura": 6, "altura": 2},
                 "configuracao": {"vista": V1, "rotulo": "municípios", "campo_rotulo": "nome", "altura": 260}},
                {"id": W_TAB, "tipo": "tabela", "largura_colunas": 6,
                 "posicao": {"coluna": 7, "linha": 1, "largura": 6, "altura": 1},
                 "configuracao": {"vista": V2, "colunas": [{"campo": "nome", "rotulo": "Município"},
                                                            {"campo": "uf", "rotulo": "UF"}]}},
                {"id": W_GRAF, "tipo": "grafico", "largura_colunas": 6,
                 "posicao": {"coluna": 7, "linha": 2, "largura": 6, "altura": 1},
                 "configuracao": {"vista": V2, "campo": "uf", "titulo": "por UF"}},
                {"id": W_LISTA, "tipo": "tabela", "largura_colunas": 12,
                 "posicao": {"coluna": 1, "linha": 3, "largura": 12, "altura": 1},
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
            "mensagens": [],
        },
    }


def _adicionar_acao(page, evento, alvo, acao, relacao=None, campo_origem=None, campo_alvo=None, condicao=None):
    page.select_option("#acao-evento", evento)
    page.select_option("#acao-alvo", alvo)
    page.select_option("#acao-acao", acao)
    if relacao is not None:
        page.select_option("#acao-relacao", relacao)
    if campo_origem:
        page.select_option("#acao-campo-origem", campo_origem)
    if campo_alvo:
        page.select_option("#acao-campo-alvo", campo_alvo)
    page.fill("#acao-condicao", condicao or "")
    page.click("#acao-adicionar")


def test_app_montado_so_pelo_painel_de_acoes_e_exportacao_filtrada(page, playwright, base_url, credenciais_demo,
                                                                   admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    r = admin_api.post("/api/tokens", data={"nome": f"e2e-l501e-{s}", "escopos": ["admin:inquilino"]})
    assert r.status == 201, r.text()
    token, token_id = r.json()["token"], r.json()["id"]
    criados = []
    estados = []
    try:
        mun = _enviar_geojson(playwright, base_url, token, "municipios.geojson", _municipios())
        esc = _enviar_geojson(playwright, base_url, token, "escolas.geojson", _escolas())
        mun_id = _item_arquivo(admin_api, f"e2e municípios {s}", mun, "municipios.geojson")
        esc_id = _item_arquivo(admin_api, f"e2e escolas {s}", esc, "escolas.geojson")
        criados += [mun_id, esc_id]
        r = admin_api.post("/api/itens", data={"tipo": "app", "titulo": f"e2e app ações {s}",
                                               "dados": _documento_sem_mensagens(mun_id, esc_id)})
        assert r.status == 201, r.text()
        app_id = r.json()["id"]
        criados.append(app_id)
        V2, V3, W_MAPA, W_TAB, W_GRAF, W_LISTA = (_ulid(i) for i in (204, 205, 206, 207, 208, 209))

        tela = Tela(page, base_url)
        tela.entrar(slug, admin_login, senha_admin, proximo=f"/construtor?item={app_id}")
        tela.medidas["pagina_pronta_ms_construtor"] = tela.ir(f"/construtor?item={app_id}")
        page.wait_for_selector(f".no-editor[data-no='{W_MAPA}']", timeout=15000)

        # ---------------------------------------------- 1. mapa: seleção → filtra a vista da tabela/gráfico
        page.click(f".no-editor[data-no='{W_MAPA}']")
        page.wait_for_selector("#painel-acoes[data-no='" + W_MAPA + "']", timeout=10000)
        assert page.locator("#lista-acoes li").count() == 1  # "nenhuma ação" ainda
        eventos = page.locator("#acao-evento option").all_inner_texts()
        assert "selecao_mudou" in eventos and "extensao_mudou" in eventos and "filtro_mudou" not in eventos, eventos
        _adicionar_acao(page, "selecao_mudou", V2, "filtrar", relacao="mesma_fonte")
        page.wait_for_function(_N_ACOES.format(n=1), timeout=10000)
        estados.append("mapa->tabela:filtrar")
        _capturar(page, "1_mapa_filtra_tabela")
        # gatilho repetido: mesma origem/evento/alvo/ação de novo → recusado nomeado, nada entra
        _adicionar_acao(page, "selecao_mudou", V2, "filtrar", relacao="mesma_fonte")
        page.wait_for_selector("#acao-erro:not([hidden])", timeout=10000)
        assert page.get_attribute("#acao-erro", "data-regra") == "gatilho_repetido", page.text_content("#acao-erro")
        assert page.locator("#lista-acoes li[data-mensagem]").count() == 1
        estados.append("gatilho_repetido:recusado")
        _capturar(page, "2_gatilho_repetido")
        # condição com campo inexistente → recusada nomeada (campo_inexistente)
        _adicionar_acao(page, "selecao_mudou", W_GRAF, "piscar", condicao="estado = 'SP'")
        page.wait_for_function("() => document.querySelector('#acao-erro').dataset.regra === 'campo_inexistente'",
                               timeout=10000)
        assert page.locator("#lista-acoes li[data-mensagem]").count() == 1
        estados.append("condicao_campo_inexistente:recusada")
        # ---------------------------------------------- 2. mapa: seleção → gráfico pisca (com condição válida)
        _adicionar_acao(page, "selecao_mudou", W_GRAF, "piscar", condicao="uf = 'MG'")
        page.wait_for_function(_N_ACOES.format(n=2), timeout=10000)
        assert page.get_attribute("#acao-erro", "hidden") is not None
        estados.append("mapa->grafico:piscar(condicao)")
        _capturar(page, "3_mapa_pisca_grafico")
        # ------------------------------------------------------------ 3. mapa: seleção → lista (escolas) por atributo
        _adicionar_acao(page, "selecao_mudou", V3, "filtrar", relacao="atributo", campo_origem="cod",
                        campo_alvo="cod_mun")
        page.wait_for_function(_N_ACOES.format(n=3), timeout=10000)
        estados.append("mapa->lista:filtrar(atributo)")
        _capturar(page, "4_mapa_filtra_lista")
        # ------------------------------------------------------------ 4. tabela: clique na linha → mapa dá zoom
        page.click(f".no-editor[data-no='{W_TAB}']")
        page.wait_for_selector("#painel-acoes[data-no='" + W_TAB + "']", timeout=10000)
        _adicionar_acao(page, "clique", W_MAPA, "zoom")
        page.wait_for_function(_N_ACOES.format(n=1), timeout=10000)
        estados.append("tabela->mapa:zoom")
        _capturar(page, "5_tabela_zoom_mapa")
        page.click("#salvar")
        page.wait_for_function("() => document.getElementById('estado-salvo').textContent.startsWith('gravado')",
                               timeout=15000)
        dados = admin_api.get(f"/api/itens/{app_id}").json()["dados"]
        msgs = dados["corpo"]["mensagens"]
        assert len(msgs) == 2, msgs  # 1 mensagem do mapa (3 ações) + 1 da tabela (1 ação)
        assert sorted(len(m["acoes"]) for m in msgs) == [1, 3], msgs
        assert any(a.get("parametros", {}).get("condicao") for m in msgs for a in m["acoes"]), msgs

        # ------------------------------------------------------------ 5. aplicativo publicado: a cadeia funciona
        tela.medidas["pagina_pronta_ms_aplicativo"] = tela.ir(f"/aplicativo?item={app_id}")
        page.wait_for_function("() => document.querySelectorAll('plat-mapa .feicao').length === 12", timeout=15000)
        tabelas = page.locator("[data-tipo='tabela']")
        assert tabelas.nth(0).locator("tbody tr").count() == 12 and tabelas.nth(1).locator("tbody tr").count() == 24
        page.locator("plat-mapa .feicao[data-id='5']").click()  # cod 5, UF MG (5 % 3 = 2)
        page.wait_for_function(_LINHAS.format(i=0, n=1), timeout=15000)
        assert page.locator("plat-grafico .barra").count() == 1
        assert page.locator("plat-grafico[data-piscando='1']").count() == 1  # condição uf = 'MG' satisfeita
        page.wait_for_function(_LINHAS.format(i=1, n=3), timeout=15000)
        assert page.locator("#avisos-barramento p").count() == 0
        estados.append("app:selecao->tabela->grafico->lista")
        _capturar(page, "6_aplicativo_cadeia")
        # condição não satisfeita: cod 4 (UF RJ, 4 % 3 = 1) filtra a tabela mas NÃO pisca o gráfico
        page.wait_for_function("() => !document.querySelector('plat-grafico[data-piscando]')", timeout=5000)
        page.locator("plat-mapa .feicao[data-id='4']").click()
        page.wait_for_function(_PRIMEIRA.format(t="Município 4"), timeout=15000)
        assert page.locator("plat-grafico[data-piscando='1']").count() == 0
        estados.append("app:condicao_nao_satisfeita")
        # tabela → mapa zoom: clicar na linha muda a extensão do mapa
        extensao_antes = page.get_attribute("plat-mapa", "data-extensao")
        tabelas.nth(0).locator("tbody tr").first.click()
        page.wait_for_function("(antes) => document.querySelector('plat-mapa').dataset.extensao !== antes",
                               arg=extensao_antes, timeout=10000)
        estados.append("app:tabela->mapa:zoom")

        # ------------------------------------------------------------ 6. ações do usuário: exportar só as filtradas
        # (página reaberta sem estado: o zoom a um ponto deixou o mapa numa extensão minúscula)
        tela.ir(f"/aplicativo?item={app_id}")
        page.wait_for_function("() => document.querySelectorAll('plat-mapa .feicao').length === 12", timeout=15000)
        tabelas = page.locator("[data-tipo='tabela']")
        page.locator("plat-mapa .feicao[data-id='5']").click()
        page.wait_for_function(_PRIMEIRA.format(t="Município 5"), timeout=15000)
        tabelas.nth(0).locator("details.widget-acoes summary").click()
        with page.expect_download() as dl:
            tabelas.nth(0).locator("button[data-acao-usuario='exportar_csv']").click()
        caminho = dl.value.path()
        linhas = list(csv.reader(io.StringIO(open(caminho, encoding="utf-8").read()), delimiter=";"))
        assert linhas[0] == ["cod", "nome", "uf"] and len(linhas) == 2, linhas
        assert linhas[1] == ["5", "Município 5", "MG"], linhas
        assert dl.value.suggested_filename == "lista.csv"
        with page.expect_download() as dl2:
            tabelas.nth(0).locator("button[data-acao-usuario='exportar_geojson']").click()
        geo = json.load(open(dl2.value.path(), encoding="utf-8"))
        assert geo["type"] == "FeatureCollection" and len(geo["features"]) == 1, geo
        assert geo["features"][0]["properties"]["cod"] == 5
        assert geo["features"][0]["geometry"]["type"] == "Point"
        estados.append("usuario:exportar_csv+geojson(filtradas)")
        _capturar(page, "7_exportar")
        # zoom à seleção e ver na tabela pelo mapa; criar item no catálogo com a seleção (resposta nomeada)
        page.locator("plat-mapa details.widget-acoes summary").click()
        ext = page.get_attribute("plat-mapa", "data-extensao")
        page.locator("plat-mapa button[data-acao-usuario='zoom_selecao']").click()
        page.wait_for_function("(a) => document.querySelector('plat-mapa').dataset.extensao !== a", arg=ext,
                               timeout=10000)
        # o zoom repinta o mapa e o menu volta fechado: abrir de novo
        page.locator("plat-mapa details.widget-acoes summary").click()
        page.locator("plat-mapa button[data-acao-usuario='criar_item']").click()
        page.wait_for_function(
            "() => (document.querySelector('plat-mapa .widget-acoes-saida').textContent || '').length > 0",
            timeout=15000)
        saida = page.text_content("plat-mapa .widget-acoes-saida") or ""
        # 201 com o tipo `selecao` (quando a instalação o tem) ou o erro NOMEADO da API (`codigo: mensagem`)
        assert "item criado" in saida or ":" in saida, saida
        if "item criado" in saida:
            criados.append(page.get_attribute("plat-mapa", "data-item-criado"))
            tela.esperar_status()
        else:
            tela.esperar_status(422)
        estados.append("usuario:zoom+criar_item")
        _capturar(page, "8_acoes_usuario")
        tela.verificar()
        gravar = medida(ITEM)
        gravar("passos_provados", len(estados), "passos", "; ".join(estados))
        gravar("erros_de_console", 0, "erros", "Tela.verificar")
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        for iid in reversed(criados):
            if iid:
                admin_api.delete(f"/api/itens/{iid}")
        admin_api.delete(f"/api/tokens/{token_id}")
