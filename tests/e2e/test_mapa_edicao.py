"""e2e do item L2-03-edicao: edição de feições no SIG (`/sig`), sobre a API transacional do L2-03-a.

Por que `/sig` e não `/mapa`: a página `/mapa` virou só mapa-base e o módulo `web/js/mapa/edicao.js` ficou
órfão lá (achado que derrubou este item duas vezes); em `/sig` o MESMO módulo está ligado de fábrica
(`window.plat.sig.edicao`, painel `#painel-edicao`). Cada teste é uma cláusula do portão, provada no
navegador de verdade (chromium do playwright).

Depende da bancada `scripts/edicao_demo_camadas.py criar` (duas camadas pequenas e editáveis: pontos e
linhas, separadas da bancada de 1 milhão do L2-01) e do Martin no ar. Sem uma das duas, SALTA.

Anexos: esta máquina não tem a instância de Garage das trilhas (unidade plataforma-garage-trilhas ausente,
token vazio de propósito — laco/trilha_ambiente.sh). O que se prova na tela é a BORDA: painel de anexos
montado na seleção + recusa de tipo pelo servidor na sessão da página. O caminho feliz de armazenamento
(objeto gravado/lido) fica na fronteira honesta do relatório do item."""

import base64

import httpx
import pytest

from tests.e2e.apoio import Tela, texto_aviso

ITEM = "L2-03-edicao"
MARTIN = "http://127.0.0.1:8241"
CENTRO = [-46.53, -23.46]  # Guarulhos: área da bancada (3 pontos + 1 linha)

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(scope="module")
def martin_no_ar():
    try:
        httpx.get(f"{MARTIN}/catalog", timeout=5)
    except httpx.HTTPError as e:
        pytest.skip(f"Martin (edição) fora do ar em {MARTIN}: {e}")


def _desligar_tudo(page):
    """TODA camada ativa de fábrica (`arvore.ativarPadrao`), não só raster: o inquilino demo é compartilhado
    entre trilhas e uma camada densa de pontos ALHEIA ficava ativa no fundo — com a aderência ligada
    (tolerância 12 px), o clique de CRIAR puxava para um vértice dela e o ponto nascia em outra coordenada;
    o clique de selecionar, na coordenada original, não achava feição nenhuma (achado deste retarget,
    medido por captura). Desligar tudo também elimina os 502 de tile raster alheio."""
    page.evaluate("""
      () => {
        const { catalogo } = window.plat.sig;
        for (const id of [...catalogo.ativas]) catalogo.desligar(id);
      }
    """)


def _abrir_painel_edicao(page):
    """Abre o painel Edição e o ancora no RODAPÉ esquerdo: flutuante, a posição de fábrica (68px,16px) cobre
    o centro-esquerda do mapa onde vários cliques deste arquivo caem (achado do retarget /sig)."""
    if page.evaluate("() => document.getElementById('painel-edicao').hidden"):
        page.click('button[data-painel="edicao"]')
        page.wait_for_function("() => !document.getElementById('painel-edicao').hidden", timeout=10000)
    page.evaluate("""() => {
        const p = document.getElementById('painel-edicao');
        p.style.left = '4px'; p.style.top = '330px'; p.style.maxHeight = '370px'; p.style.overflow = 'auto';
    }""")
    page.wait_for_selector("#edicao-camada", timeout=10000)


@pytest.fixture
def sig(page, base_url, credenciais_demo, martin_no_ar):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # 502 aqui é SEMPRE tile raster de outra trilha no inquilino demo compartilhado (ver test_comparar.py)
    tela.esperar_status(502)
    tela.entrar(slug, login, senha)
    tela.ir("/sig", "pagina_pronta_ms_sig_edicao")
    page.wait_for_function(
        "() => window.plat.sig && window.plat.sig.catalogo.disponiveis.length > 0", timeout=20000
    )
    _desligar_tudo(page)
    page.evaluate(f"() => window.plat.sig.map.jumpTo({{ center: {CENTRO}, zoom: 14 }})")
    _abrir_painel_edicao(page)
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
    separada de "escolher para editar". Liga pela árvore (painel Camadas, que flutua à DIREITA), fecha o
    painel para liberar a área de clique e enquadra a extensão da camada com folga à esquerda (o painel
    Edição fica embaixo à esquerda)."""
    if page.evaluate("() => document.getElementById('painel-camadas').hidden"):
        page.click('button[data-painel="camadas"]')
        page.wait_for_function("() => !document.getElementById('painel-camadas').hidden", timeout=5000)
    linha = page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{trecho}"))').first
    caixa = linha.locator('input[type=checkbox]')
    if not caixa.is_checked():
        caixa.check()
    page.click('button[data-painel="camadas"]')
    page.wait_for_function("() => document.getElementById('painel-camadas').hidden", timeout=5000)
    # esperar a fonte/camada de estilo existir de verdade antes de medir qualquer pixel (corrida do
    # tilejson assíncrono: areTilesLoaded vale true "cedo demais" quando ainda não há tile nenhum)
    page.wait_for_function(
        """(trecho) => {
             const { catalogo, map } = window.plat.sig;
             const f = catalogo.disponiveis.find((x) => x.titulo.includes(trecho));
             return f && catalogo.ativas.includes(f.id)
                    && catalogo.idsDeEstilo(f.id).some((idc) => map.getLayer(idc));
           }""", arg=trecho, timeout=15000,
    )
    page.evaluate(
        """() => {
             // área FIXA de trabalho, não a extensão gravada da camada: a extensão é estática (3 pontos da
             // bancada) e feições criadas pelo teste FORA dela caíam projetadas debaixo do trilho de
             // ícones/painel (medido por captura: clique em x≈51 px, em cima do trilho, nada selecionava)
             window.plat.sig.map.fitBounds([[-46.552, -23.476], [-46.508, -23.448]],
               { padding: { left: 420, top: 60, right: 60, bottom: 60 }, duration: 0 });
           }""",
    )
    page.wait_for_function("() => window.plat.sig.map.areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(300)


def _pixel_da_pagina(page, lon, lat, dx=0, dy=0):
    # map.project() devolve pixel relativo ao CONTÊINER do mapa, não à página inteira; somar o retângulo
    # do #mapa dá a coordenada de página que page.mouse.click precisa. dx/dy deslocam em pixels (snap).
    return page.evaluate(
        """([c, dx, dy]) => {
             const map = window.plat.sig.map;
             const pt = map.project(c);
             const r = map.getContainer().getBoundingClientRect();
             return { x: r.left + pt.x + dx, y: r.top + pt.y + dy };
           }""", [[lon, lat], dx, dy])


def _clicar_no_mapa_em(page, lon, lat):
    p = _pixel_da_pagina(page, lon, lat)
    page.mouse.click(p["x"], p["y"])


def _limpar_saida(page):
    """#edicao-saida é reescrito (nunca reinicia): esperar "salvo" de novo sem limpar antes pode achar o
    texto da AÇÃO ANTERIOR (mesma palavra) e seguir cedo demais — achado deste arquivo de e2e."""
    page.evaluate("() => { document.getElementById('edicao-saida').textContent = ''; }")


def _esperar_salvo(page):
    page.wait_for_function(
        "() => document.getElementById('edicao-saida').textContent.includes('salvo')", timeout=10000
    )


def _criar_ponto(page, lon, lat, nome, categoria="A"):
    """Cria um ponto pela tela e espera o tile novo carregar (o _religar pós-gravação troca fonte/token)."""
    _clicar_modo(page, "Ponto")
    _clicar_no_mapa_em(page, lon, lat)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    page.fill('.edicao-form input[name="nome"]', nome)
    page.select_option('.edicao-form select[name="categoria"]', categoria)
    _limpar_saida(page)
    page.click('.edicao-form button[type="submit"]')
    _esperar_salvo(page)
    page.wait_for_function("() => window.plat.sig.map.areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(300)
    _clicar_modo(page, "Ponto")  # sai do modo adicionar (o botão alterna: liga/desliga)


def _criar_linha(page, pontos, nome):
    _clicar_modo(page, "Linha")
    for lon, lat in pontos:
        _clicar_no_mapa_em(page, lon, lat)
    page.locator('#edicao-painel button:text-is("Concluir")').click()
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    page.fill('.edicao-form input[name="nome"]', nome)
    _limpar_saida(page)
    page.click('.edicao-form button[type="submit"]')
    _esperar_salvo(page)
    page.wait_for_function("() => window.plat.sig.map.areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(300)
    _clicar_modo(page, "Linha")  # sai do modo adicionar (o botão alterna: liga/desliga; salvar NÃO sai)


# ---------------------------------------------------------------- criar
def test_criar_ponto_com_formulario_e_dominio(sig, page):
    _selecionar_camada(page, "edicao-pontos")
    _clicar_modo(page, "Ponto")
    _clicar_no_mapa_em(page, -46.536, -23.456)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    # domínio no navegador: valor fora da lista não aparece nem pode ser digitado (é <select>)
    opcoes_categoria = page.locator('.edicao-form select[name="categoria"] option').all_inner_texts()
    assert set(opcoes_categoria) >= {"A", "B", "C"}

    # obrigatório: submeter sem "nome" mostra o erro no navegador e NÃO chama a API
    n_respostas_antes = len(sig.respostas)
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_selector(".edicao-erros li", timeout=5000)
    assert len(sig.respostas) == n_respostas_antes  # nada foi enviado

    page.fill('.edicao-form input[name="nome"]', "criado no e2e")
    page.select_option('.edicao-form select[name="categoria"]', "B")
    page.click('.edicao-form button[type="submit"]')
    _esperar_salvo(page)
    sig.verificar()


def test_criar_linha_com_dois_pontos(sig, page):
    _selecionar_camada(page, "edicao-linhas")
    _criar_linha(page, [(-46.534, -23.457), (-46.526, -23.457)], "linha do e2e")
    sig.verificar()


# ---------------------------------------------------------------- domínio/obrigatório no SERVIDOR (não só
# no navegador — refutação do item-pai, reconferida aqui direto pela API, sem passar pela tela)
def test_dominio_e_obrigatorio_recusados_pelo_servidor_sem_passar_pela_tela(sig, page):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    sig.esperar_status(422)
    r = sig.api("POST", f"/api/camadas/{camada_id}/edicoes", corpo={
        "adicionar": [{"atributos": {"nome": "x", "categoria": "Z"},
                       "geometria": {"type": "Point", "coordinates": [-46.5, -23.5]}}],
        "atualizar": [], "apagar": [],
    })
    assert r.status == 422
    assert r.json()["erro"] == "fora_do_dominio"

    r2 = sig.api("POST", f"/api/camadas/{camada_id}/edicoes", corpo={
        "adicionar": [{"atributos": {"categoria": "A"}, "geometria": {"type": "Point", "coordinates": [-46.5, -23.5]}}],
        "atualizar": [], "apagar": [],
    })
    assert r2.status == 422
    assert r2.json()["erro"] == "campo_obrigatorio"


# ---------------------------------------------------------------- mover, editar atributo, apagar, histórico
def test_selecionar_editar_atributo_e_apagar(sig, page):
    """Cria a PRÓPRIA feição (em vez de mexer em "ponto um" da bancada): apagar é destrutivo e outro teste
    do arquivo (edição em lote) depende dos 3 pontos originais continuarem existindo."""
    _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _criar_ponto(page, -46.539, -23.459, "ponto um")

    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.539, -23.459)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    valor_inicial = page.input_value('.edicao-form input[name="nome"]')
    assert valor_inicial == "ponto um"

    page.fill('.edicao-form input[name="nome"]', "ponto um editado")
    _limpar_saida(page)
    page.click('.edicao-form button[type="submit"]')
    _esperar_salvo(page)

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

    _limpar_saida(page)
    page.locator('#edicao-painel button:text-is("Apagar")').click()
    _esperar_salvo(page)
    assert page.locator('.edicao-form input[name="nome"]').count() == 0
    sig.verificar()


# ---------------------------------------------------------------- mover vértice por arrasto
def test_mover_vertice_por_arrasto_salva_a_nova_coordenada(sig, page):
    """Cria a PRÓPRIA feição (mesmo motivo do teste de apagar: não mexer nos 3 pontos da bancada)."""
    camada_id = _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _criar_ponto(page, -46.524, -23.466, "ponto arrastavel")

    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.524, -23.466)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    globalid = [*page.evaluate("() => [...window.plat.sig.edicao.selecionadas.keys()]")][0]

    # o marcador de vértice só vira alvo de mousedown DEPOIS da próxima pintura — sem esta espera o
    # mouse.down cai antes do paint, arrastando fica null e o arrasto vira um clique vazio (corrida medida)
    page.wait_for_function(
        """(c) => { const map = window.plat.sig.map;
             return map.queryRenderedFeatures(map.project(c), { layers: ['plat-edicao-vertices'] }).length > 0; }""",
        arg=[-46.524, -23.466], timeout=10000,
    )
    origem = _pixel_da_pagina(page, -46.524, -23.466)
    destino = _pixel_da_pagina(page, -46.5215, -23.4675)
    _limpar_saida(page)  # o "salvo" da criação ainda está na tela: sem limpar, a espera abaixo é vazia
    page.mouse.move(origem["x"], origem["y"])
    page.mouse.down()
    page.mouse.move(destino["x"], destino["y"], steps=5)
    page.mouse.up()
    _esperar_salvo(page)

    r = sig.api("GET", f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status == 200, r.text()
    lon = r.json()["geometria"]["coordinates"][0]
    assert lon == pytest.approx(-46.5215, abs=0.002), lon  # moveu de verdade, não ficou no lugar
    sig.verificar()


# ---------------------------------------------------------------- dividir e unir (tela + servidor)
def test_dividir_linha_em_duas_e_apagar_original(sig, page):
    camada_id = _selecionar_camada(page, "edicao-linhas")
    _ligar_no_mapa(page, "edicao-linhas")
    _criar_linha(page, [(-46.538, -23.467), (-46.522, -23.467)], "para dividir")
    _clicar_modo(page, "Linha")  # sai do modo adicionar (ficou ligado depois do salvar)

    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.530, -23.467)  # meio da linha nova
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    globalid = [*page.evaluate("() => [...window.plat.sig.edicao.selecionadas.keys()]")][0]

    _clicar_modo(page, "Dividir")
    _limpar_saida(page)
    _clicar_no_mapa_em(page, -46.526, -23.467)  # ponto de corte, longe das pontas (sem snap)
    _esperar_salvo(page)

    sig.esperar_status(404)
    r = sig.api("GET", f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status == 404  # a original foi apagada e substituída pelas duas partes
    assert page.evaluate("() => window.plat.sig.edicao.pilha.length") >= 1  # divisão entrou na pilha
    sig.verificar()


def test_unir_duas_linhas_em_uma(sig, page):
    camada_id = _selecionar_camada(page, "edicao-linhas")
    _ligar_no_mapa(page, "edicao-linhas")
    # a união de linhas DISJUNTAS vira MultiLineString e a camada (LineString) recusa com 422 — o par
    # aqui se toca na ponta (como no teste de API test_unir_duas_linhas_conectadas_vira_uma): a aderência
    # padrão crava o primeiro vértice de B EXATAMENTE no fim de A
    _criar_linha(page, [(-46.545, -23.463), (-46.540, -23.463)], "para unir a")
    # antes de desenhar B, a linha A tem de estar RENDERIZADA na ponta: o primeiro vértice de B só é
    # cravado EXATAMENTE no fim de A pela aderência se A já estiver pintada — sem esta espera a corrida
    # tile-novo × clique deixava um gap sub-pixel entre as pontas e o ST_LineMerge do servidor devolvia
    # MultiLineString (422, sem "salvo") de forma intermitente (medido: isolado passava, na suíte falhava)
    page.wait_for_function(
        """(c) => { const { map, catalogo, edicao } = window.plat.sig;
             const ids = catalogo.idsDeEstilo(edicao.camadaId).filter((i) => map.getLayer(i));
             return map.queryRenderedFeatures(map.project(c), { layers: ids }).length > 0; }""",
        arg=[-46.540, -23.463], timeout=10000,
    )
    _criar_linha(page, [(-46.540, -23.463), (-46.535, -23.463)], "para unir b")

    _clicar_modo(page, "Selecionar")
    # seleção pelo MÉTODO PÚBLICO do módulo (documentado "também usada pelo e2e"), com os ids lidos da
    # pilha de desfazer — NUNCA por clique: rodadas anteriores da suíte deixam cópias destas mesmas
    # linhas (e a linha UNIDA, que cobre os dois pontos de clique) empilhadas nestas coordenadas, e o
    # clique pega a feição do topo da renderização, nem sempre o par recém-criado — unir o par errado
    # (sobreposto) virava 422 e o "salvo" nunca chegava (floco medido: isolado passava, na suíte falhava)
    ids = page.evaluate(
        """() => window.plat.sig.edicao.pilha
             .map((p) => p.desfazer && p.desfazer[0] && p.desfazer[0].apagar)
             .filter(Boolean).slice(-2)"""
    )
    assert len(ids) == 2, ids
    page.evaluate(
        """(ids) => window.plat.sig.edicao.selecionar(ids[0], false)
             .then(() => window.plat.sig.edicao.selecionar(ids[1], true))""", ids)
    page.wait_for_function("() => window.plat.sig.edicao.selecionadas.size === 2", timeout=5000)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    _limpar_saida(page)
    page.locator('#edicao-painel button:text-is("Unir selecionadas")').click()
    _esperar_salvo(page)

    sig.esperar_status(404)
    for gid in ids:
        r = sig.api("GET", f"/api/camadas/{camada_id}/feicoes/{gid}")
        assert r.status == 404  # as duas origens viraram uma feição só
    sig.verificar()


# ---------------------------------------------------------------- desfazer/refazer (pilha local + histórico
# do servidor: apagar pela porta única, restaurar pelo histórico com o MESMO globalid)
def test_desfazer_e_refazer_criacao_de_ponto(sig, page):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _criar_ponto(page, -46.524, -23.454, "vai e volta")

    # o registrador lê o histórico DEPOIS do "salvo": esperar o botão habilitar, não só a mensagem
    page.wait_for_function("() => !document.getElementById('edicao-desfazer').disabled", timeout=10000)
    globalid = page.evaluate("() => window.plat.sig.edicao.pilha.at(-1).desfazer[0].apagar")
    assert globalid

    _limpar_saida(page)
    page.click("#edicao-desfazer")
    page.wait_for_function(
        "() => document.getElementById('edicao-saida').textContent.includes('desfeita')", timeout=10000
    )
    sig.esperar_status(404)
    r = sig.api("GET", f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status == 404  # desfeito: a feição sumiu do servidor

    _limpar_saida(page)
    page.click("#edicao-refazer")
    page.wait_for_function(
        "() => document.getElementById('edicao-saida').textContent.includes('refeita')", timeout=10000
    )
    r2 = sig.api("GET", f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r2.status == 200  # refeito: MESMO globalid de volta, com os atributos
    assert r2.json()["atributos"]["nome"] == "vai e volta"
    sig.verificar()


# ---------------------------------------------------------------- aderência (snap) a vértice existente
def test_aderencia_ligada_puxa_para_o_vertice_e_desligada_grava_o_clique_cru(sig, page):
    _selecionar_camada(page, "edicao-linhas")
    _ligar_no_mapa(page, "edicao-pontos")  # a aderência mira TODA camada ativa, não só a editada
    _clicar_modo(page, "Linha")
    _clicar_no_mapa_em(page, -46.540, -23.455)  # primeiro vértice, longe de tudo

    # "ponto um" da bancada em (-46.533, -23.462): clique a ~6 px, dentro da tolerância de 12 px
    p = _pixel_da_pagina(page, -46.533, -23.462, dx=5, dy=4)
    page.mouse.click(p["x"], p["y"])
    p2 = page.evaluate("() => window.plat.sig.edicao.rascunho.at(-1)")
    # o alvo da aderência é o vértice RENDERIZADO (tile vetorial quantizado na grade de 4096 — ~1,1e-5°
    # por unidade em z13), não o valor exato do banco: 2e-5 cobre a grade e separa do clique cru (~6e-4°)
    assert p2[0] == pytest.approx(-46.533, abs=2e-5), p2
    assert p2[1] == pytest.approx(-23.462, abs=2e-5), p2

    # aderência desligada: o MESMO procedimento perto do "ponto dois" grava a coordenada crua do clique
    page.uncheck("#edicao-aderir")
    p = _pixel_da_pagina(page, -46.528, -23.458, dx=5, dy=4)
    page.mouse.click(p["x"], p["y"])
    p3 = page.evaluate("() => window.plat.sig.edicao.rascunho.at(-1)")
    assert abs(p3[0] - (-46.528)) > 1e-6 or abs(p3[1] - (-23.458)) > 1e-6, p3
    sig.verificar()


# ---------------------------------------------------------------- anexos (borda: painel + recusa de tipo;
# caminho feliz de armazenamento exige o Garage de trilhas, ausente nesta máquina — fronteira honesta)
def test_anexos_painel_na_selecao_e_recusa_de_tipo_pelo_servidor(sig, page):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    _ligar_no_mapa(page, "edicao-pontos")
    _criar_ponto(page, -46.521, -23.461, "com anexo")

    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.521, -23.461)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)
    globalid = [*page.evaluate("() => [...window.plat.sig.edicao.selecionadas.keys()]")][0]

    # painel de anexos montado na seleção: lista + input de arquivo + botão de envio (o input é IRMÃO da
    # ul.edicao-anexos dentro do bloco, não filho — por isso o seletor ancora no painel, não na lista)
    page.wait_for_selector("#painel-edicao input[type=file]", timeout=10000)

    # recusa de tipo: envio PELA TELA de um .js — o servidor responde 415 e o aviso global mostra a mensagem
    sig.esperar_status(415)
    page.set_input_files("#painel-edicao input[type=file]", {
        "name": "script.js", "mimeType": "application/javascript", "buffer": b"alert(1)",
    })
    page.locator('#painel-edicao button:text-is("Enviar anexo")').click()
    page.wait_for_function(
        "() => (document.getElementById('aviso').textContent || '').includes('tipo de anexo')", timeout=10000
    )
    assert "tipo de anexo" in texto_aviso(page)

    # mesma recusa, confirmada na sessão da página sem passar pela tela (borda é o servidor, nunca o form)
    r = sig.api("POST", f"/api/camadas/{camada_id}/feicoes/{globalid}/anexos",
                corpo={"nome": "x.js", "content_type": "application/javascript",
                       "conteudo": base64.b64encode(b"alert(1)").decode("ascii")})
    assert r.status == 415
    assert r.json()["erro"] == "tipo_nao_permitido"

    # recusa de tamanho: acima de ANEXO_TAMANHO_MAX (7 MiB) o servidor responde 422 anexo_grande, e o 413
    # genérico do corpo NÃO dispara antes (o teto foi dimensionado para o inchaço de base64 — L2-03-a)
    from app import limites
    grande = b"\x89PNG\r\n\x1a\n" + b"0" * (limites.ANEXO_TAMANHO_MAX + 10_000)
    sig.esperar_status(422)
    r2 = sig.api("POST", f"/api/camadas/{camada_id}/feicoes/{globalid}/anexos",
                 corpo={"nome": "grande.png", "content_type": "image/png",
                        "conteudo": base64.b64encode(grande).decode("ascii")})
    assert r2.status == 422
    assert r2.json()["erro"] == "anexo_grande"
    sig.verificar()


# ---------------------------------------------------------------- edição concorrente (versão otimista)
def test_edicao_concorrente_duas_sessoes_a_segunda_nao_sobrescreve_em_silencio(
    sig, page, browser, base_url, credenciais_demo
):
    camada_id = _selecionar_camada(page, "edicao-pontos")
    r = sig.api("GET", f"/api/mapa/camadas/{camada_id}")
    assert r.status == 200
    _ligar_no_mapa(page, "edicao-pontos")
    _clicar_modo(page, "Selecionar")
    _clicar_no_mapa_em(page, -46.528, -23.458)
    page.wait_for_selector('.edicao-form input[name="nome"]', timeout=10000)

    slug, login, senha = credenciais_demo
    # MESMAS opções do browser_context_args do conftest (a fixture não vale para contextos criados à mão):
    # sem locale pt-BR a tela renderiza em inglês e os botões por rótulo ("Selecionar") nunca resolvem
    contexto2 = browser.new_context(base_url=base_url, locale="pt-BR",
                                    viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
    pagina2 = contexto2.new_page()
    tela2 = Tela(pagina2, base_url)
    tela2.esperar_status(502)
    tela2.entrar(slug, login, senha)
    tela2.ir("/sig", "pagina_pronta_ms_sig_edicao_b")
    pagina2.wait_for_function(
        "() => window.plat.sig && window.plat.sig.catalogo.disponiveis.length > 0", timeout=20000
    )
    _desligar_tudo(pagina2)
    pagina2.evaluate(f"() => window.plat.sig.map.jumpTo({{ center: {CENTRO}, zoom: 14 }})")
    _abrir_painel_edicao(pagina2)
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
    sig.esperar_status(409)
    page.fill('.edicao-form input[name="nome"]', "mudado pela sessao a")
    page.click('.edicao-form button[type="submit"]')
    page.wait_for_function(
        "() => (document.getElementById('edicao-saida').textContent || '').length > 0", timeout=10000
    )
    assert "outra sessão" in page.text_content("#edicao-saida")

    r2 = sig.api("GET", f"/api/mapa/camadas/{camada_id}")
    assert r2.status == 200
    tela2.verificar()
    contexto2.close()


# ---------------------------------------------------------------- edição em lote
def test_edicao_em_lote_dois_selecionados(sig, page):
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
    page.wait_for_function("() => window.plat.sig.edicao.selecionadas.size === 2", timeout=5000)
    assert page.evaluate("() => window.plat.sig.edicao.selecionadas.size") == 2

    page.select_option('.edicao-form select[name="categoria"]', "B")
    page.locator('.edicao-form button:text-is("Aplicar às selecionadas")').click()
    _esperar_salvo(page)

    r = sig.api("GET", f"/api/mapa/camadas/{_selecionar_camada(page, 'edicao-pontos')}")
    assert r.status == 200
    sig.verificar()
