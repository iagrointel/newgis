"""e2e do item L2-03-edicao: edição de feições no mapa, sobre o visualizador do L2-01-mapa-web e a API
transacional do L2-03-a. Cada teste é uma cláusula do portão, provada no navegador de verdade (chromium do
playwright).

Depende da bancada `scripts/edicao_demo_camadas.py criar` (duas camadas pequenas e editáveis: pontos e
linhas, separadas da bancada de 1 milhão do L2-01) e do Martin no ar. Sem uma das duas, SALTA."""

import httpx
import pytest

from tests.e2e.apoio import Tela

ITEM = "L2-03-edicao"
MARTIN = "http://127.0.0.1:8241"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="module")
def martin_no_ar():
    try:
        httpx.get(f"{MARTIN}/catalog", timeout=5)
    except httpx.HTTPError as e:
        pytest.skip(f"Martin (edição) fora do ar em {MARTIN}: {e}")


@pytest.fixture
def mapa(page, base_url, credenciais_demo, martin_no_ar):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa_edicao")
    page.wait_for_selector("#edicao-camada", timeout=20000)
    opcoes = page.locator("#edicao-camada option").all_inner_texts()
    if not any("edicao-pontos" in o for o in opcoes):
        pytest.skip("bancada do item ausente: rode scripts/edicao_demo_camadas.py criar")
    return tela


def _selecionar_camada(page, trecho):
    valor = page.evaluate(
        """(trecho) => {
             const sel = document.getElementById('edicao-camada');
             const opt = [...sel.options].find((o) => o.textContent.includes(trecho));
             sel.value = opt.value;
             sel.dispatchEvent(new Event('change'));
             return opt.value;
           }""", trecho)
    page.wait_for_timeout(150)
    return valor


def _clicar_modo(page, rotulo):
    page.locator(f'#edicao-painel button:text-is("{rotulo}")').click()


def _ligar_no_mapa(page, trecho):
    """Selecionar (modo do e2e) precisa da camada DESENHADA (queryRenderedFeatures) — ligar é uma ação
    separada de "escolher para editar" (o painel Camadas decide o que aparece, o painel Edição decide o
    que se pode mexer). Ver test_mapa_web.py::_ligar (mesmo padrão do L2-01)."""
    linha = page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{trecho}"))').first
    caixa = linha.locator('input[type=checkbox]')
    if not caixa.is_checked():
        caixa.check()
    linha.locator('button[data-acao="enquadrar"]').click()
    page.wait_for_timeout(400)
    # "enquadrar" ajusta o bbox sem margem: um ponto no canto pode cair embaixo do seletor de mapa-base
    # (painel sobreposto no topo do mapa) — afastar um passo de zoom dá folga (achado deste arquivo de e2e)
    page.evaluate("() => window.plat.mapa.map.zoomOut(1, { duration: 0 })")
    page.wait_for_timeout(200)
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=15000)


def _clicar_no_mapa_em(page, lon, lat):
    # map.project() devolve pixel relativo ao CONTÊINER do mapa, não à página inteira (o mapa fica ao
    # lado do painel); somar o retângulo do #mapa dá a coordenada de página que page.mouse.click precisa.
    p = page.evaluate(
        """(c) => {
             const map = window.plat.mapa.map;
             const pt = map.project(c);
             const r = map.getContainer().getBoundingClientRect();
             return { x: r.left + pt.x, y: r.top + pt.y };
           }""", [lon, lat])
    page.mouse.click(p["x"], p["y"])


def _limpar_saida(page):
    """#edicao-saida é reescrito (nunca reinicia): esperar "salvo" de novo sem limpar antes pode achar o
    texto da AÇÃO ANTERIOR (mesma palavra) e seguir cedo demais — achado deste arquivo de e2e."""
    page.evaluate("() => { document.getElementById('edicao-saida').textContent = ''; }")


def _aguardar_edicoes(page, n=1):
    page.wait_for_function(
        "(n) => document.querySelectorAll('#lista-camadas li').length > 0", n, timeout=5000
    )


# ---------------------------------------------------------------- criar
def test_criar_ponto_com_formulario_e_dominio(mapa, page):
    _selecionar_camada(page, "edicao-pontos")
    _clicar_modo(page, "Ponto")
    _clicar_no_mapa_em(page, -46.545, -23.465)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    # domínio no navegador: valor fora da lista não aparece nem pode ser digitado (é <select>)
    opcoes_categoria = page.locator('.edicao-form select[name="categoria"] option').all_inner_texts()
    assert set(opcoes_categoria) >= {"A", "B", "C"}

    # obrigatório: submeter sem "nome" mostra o erro no navegador e NÃO chama a API
    n_respostas_antes = len(mapa.respostas)
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_selector(".edicao-erros li", timeout=5000)
    assert len(mapa.respostas) == n_respostas_antes  # nada foi enviado

    page.fill('.edicao-form input[name="nome"]', "criado no e2e")
    page.select_option('.edicao-form select[name="categoria"]', "B")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function(
        "() => (document.getElementById('edicao-saida').textContent || '').length > 0", timeout=10000
    )
    assert "salvo" in page.text_content("#edicao-saida")
    mapa.verificar()


def test_criar_linha_com_dois_pontos(mapa, page):
    _selecionar_camada(page, "edicao-linhas")
    _clicar_modo(page, "Linha")
    _clicar_no_mapa_em(page, -46.58, -23.49)
    _clicar_no_mapa_em(page, -46.55, -23.49)
    page.locator('#edicao-painel button:text-is("Concluir")').click()
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    page.fill('.edicao-form input[name="nome"]', "linha do e2e")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function(
        "() => (document.getElementById('edicao-saida').textContent || '').length > 0", timeout=10000
    )
    assert "salvo" in page.text_content("#edicao-saida")
    mapa.verificar()


# ---------------------------------------------------------------- domínio/obrigatório no SERVIDOR (não só
# no navegador — refutação do item-pai, reconferida aqui direto pela API, sem passar pela tela)
def test_dominio_e_obrigatorio_recusados_pelo_servidor_sem_passar_pela_tela(mapa, page):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    r = mapa.api("POST", f"/api/camadas/{camada_id}/edicoes", corpo={
        "adicionar": [{"atributos": {"nome": "x", "categoria": "Z"},
                       "geometria": {"type": "Point", "coordinates": [-46.5, -23.5]}}],
        "atualizar": [], "apagar": [],
    })
    mapa.esperar_status(422)
    assert r.status == 422
    assert r.json()["erro"] == "fora_do_dominio"

    r2 = mapa.api("POST", f"/api/camadas/{camada_id}/edicoes", corpo={
        "adicionar": [{"atributos": {"categoria": "A"}, "geometria": {"type": "Point", "coordinates": [-46.5, -23.5]}}],
        "atualizar": [], "apagar": [],
    })
    mapa.esperar_status(422)
    assert r2.status == 422
    assert r2.json()["erro"] == "campo_obrigatorio"


# ---------------------------------------------------------------- mover, editar atributo, apagar, desfazer
def test_selecionar_editar_atributo_e_apagar(mapa, page):
    """Cria a PRÓPRIA feição (em vez de mexer em "ponto um" da bancada): apagar é destrutivo e outro teste
    do arquivo (edição em lote) depende dos 3 pontos originais continuarem existindo."""
    _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _clicar_modo(page, "Ponto")
    _clicar_no_mapa_em(page, -46.526, -23.464)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    page.fill('.edicao-form input[name="nome"]', "ponto um")
    page.select_option('.edicao-form select[name="categoria"]', "A")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)
    # _religar() (desligar+ligar a camada) troca de fonte/token: esperar o tile novo terminar de carregar
    # antes de clicar de novo no mesmo pixel, senão o clique cai num instante em que nada está desenhado ali
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(300)

    _clicar_modo(page, "Ponto")  # sai do modo adicionar (o botão alterna: liga/desliga)
    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.526, -23.464)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    valor_inicial = page.input_value('.edicao-form input[name="nome"]')
    assert valor_inicial == "ponto um"

    page.fill('.edicao-form input[name="nome"]', "ponto um editado")
    _limpar_saida(page)
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)

    # histórico mostra a mudança e permite restaurar
    page.wait_for_selector(".edicao-historico li", timeout=10000)
    itens_hist = page.locator(".edicao-historico li").all_inner_texts()
    assert any("atualizar" in i for i in itens_hist)
    # a lista vem mais recente primeiro (atualizar, inserir); restaurar a "inserir" volta ao nome original
    page.locator('.edicao-historico li:has-text("inserir") button:text-is("restaurar")').click()
    page.wait_for_function(
        "() => document.getElementById('edicao-saida').textContent.includes('restaurado')", timeout=10000
    )
    assert page.input_value('.edicao-form input[name="nome"]') == "ponto um"

    apagar_btn = page.locator('#edicao-painel button:text-is("Apagar")')
    _limpar_saida(page)
    apagar_btn.click()
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)
    assert page.locator(".edicao-form").count() == 0 or page.locator('.edicao-form input[name="nome"]').count() == 0
    mapa.verificar()


# ---------------------------------------------------------------- mover vértice por arrasto
def test_mover_vertice_por_arrasto_salva_a_nova_coordenada(mapa, page):
    """Cria a PRÓPRIA feição (mesmo motivo do teste de apagar: não mexer nos 3 pontos da bancada)."""
    camada_id = _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _clicar_modo(page, "Ponto")
    _clicar_no_mapa_em(page, -46.529, -23.466)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    page.fill('.edicao-form input[name="nome"]', "ponto arrastavel")
    page.select_option('.edicao-form select[name="categoria"]', "A")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)
    page.wait_for_function("() => window.plat.mapa.map.areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(300)

    _clicar_modo(page, "Ponto")  # sai do modo adicionar
    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.529, -23.466)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    globalid = [*page.evaluate("() => [...window.plat.mapa.edicao.selecionadas.keys()]")][0]

    origem = page.evaluate(
        """(c) => {
             const map = window.plat.mapa.map; const pt = map.project(c);
             const r = map.getContainer().getBoundingClientRect();
             return { x: r.left + pt.x, y: r.top + pt.y };
           }""", [-46.529, -23.466])
    destino = page.evaluate(
        """(c) => {
             const map = window.plat.mapa.map; const pt = map.project(c);
             const r = map.getContainer().getBoundingClientRect();
             return { x: r.left + pt.x, y: r.top + pt.y };
           }""", [-46.5265, -23.4675])
    page.mouse.move(origem["x"], origem["y"])
    page.mouse.down()
    page.mouse.move(destino["x"], destino["y"], steps=5)
    page.mouse.up()
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)

    r = mapa.api("GET", f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status == 200, r.text()
    lon = r.json()["geometria"]["coordinates"][0]
    assert lon == pytest.approx(-46.5265, abs=0.002), lon  # moveu de verdade, não ficou no lugar
    mapa.verificar()


# ---------------------------------------------------------------- edição concorrente (versão otimista)
def test_edicao_concorrente_duas_sessoes_a_segunda_nao_sobrescreve_em_silencio(
    mapa, page, browser, base_url, credenciais_demo
):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    r = mapa.api("GET", f"/api/mapa/camadas/{camada_id}")
    assert r.status == 200
    _ligar_no_mapa(page, "edicao-pontos")
    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.528, -23.458)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    slug, login, senha = credenciais_demo
    contexto2 = browser.new_context(base_url=base_url)
    pagina2 = contexto2.new_page()
    tela2 = Tela(pagina2, base_url)
    tela2.entrar(slug, login, senha)
    tela2.ir("/mapa", "pagina_pronta_ms_mapa_edicao_b")
    _selecionar_camada(pagina2, "edicao-pontos")
    _ligar_no_mapa(pagina2, "edicao-pontos")
    pagina2.locator('#edicao-painel button:text-is("Selecionar")').click()
    _clicar_no_mapa_em(pagina2, -46.528, -23.458)
    pagina2.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    # sessão B salva primeiro
    pagina2.fill('.edicao-form input[name="nome"]', "mudado pela sessao b")
    pagina2.click('.edicao-form button[type="submit"]')
    pagina2.wait_for_function(
        "() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000
    )

    # sessão A ainda tem a versão velha: salva por cima e recebe o AVISO de conflito, nunca sobrescreve calada
    page.fill('.edicao-form input[name="nome"]', "mudado pela sessao a")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function(
        "() => (document.getElementById('edicao-saida').textContent || '').length > 0", timeout=10000
    )
    assert "outra sessão" in page.text_content("#edicao-saida")

    r2 = mapa.api("GET", f"/api/mapa/camadas/{camada_id}")
    assert r2.status == 200
    tela2.verificar()
    contexto2.close()


# ---------------------------------------------------------------- edição em lote
def test_edicao_em_lote_dois_selecionados(mapa, page):
    _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.533, -23.462)  # ponto um
    page.wait_for_selector('.edicao-form select[name="categoria"]', timeout=10000)
    # o primeiro clique dispara religar/redesenho de vértices; um instante depois o segundo clique (com
    # shift) pode cair no meio desse trabalho e o MapLibre não reportar a feição em queryRenderedFeatures
    # ainda (achado deste arquivo de e2e) — uma pausa curta evita a corrida.
    page.wait_for_timeout(300)
    page.keyboard.down("Shift")
    _clicar_no_mapa_em(page, -46.520, -23.470)  # ponto tres, shift+clique acumula a seleção
    page.keyboard.up("Shift")
    page.wait_for_function("() => window.plat.mapa.edicao.selecionadas.size === 2", timeout=5000)
    assert page.evaluate("() => window.plat.mapa.edicao.selecionadas.size") == 2

    page.select_option('.edicao-form select[name="categoria"]', "B")
    page.locator('.edicao-form button:text-is("Aplicar às selecionadas")').click()
    page.wait_for_function("() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000)

    r = mapa.api("GET", f"/api/mapa/camadas/{_selecionar_camada(page, 'edicao-pontos')}")
    assert r.status == 200
    mapa.verificar()
