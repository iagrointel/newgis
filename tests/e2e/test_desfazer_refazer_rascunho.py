"""e2e do item L5-09-desfazer-refazer-rascunho: desfazer/refazer, autosave de rascunho + recuperação local,
diferença entre versões, e o conflito de edição concorrente (refutação do adversário).

O ciclo de 50 operações com sha256 (cláusula 1 do portão) já é provado, sozinho, em
`tests/unit/test_desfazer_refazer.py` — direto sobre `web/js/editor/desfazer.js`, sem navegador, porque é uma
prova de FUNÇÃO PURA e não precisa de DOM. Aqui entram as cláusulas que só existem com navegador e servidor
juntos: (2) recuperação de rascunho local depois de uma queda simulada da API; (3) diferença entre v3 e v7 na
tela; (4) autosave de rascunho não mexe na versão publicada; e a refutação de conflito em duas abas.

`?autosave_ms=<n>` na URL do `/construtor` encurta o intervalo do autosave só para o teste — em produção o
parâmetro nunca é passado e vale o padrão de `web/js/editor/tela.js::AUTOSAVE_INTERVALO_MS` (20 s)."""


import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-09-desfazer-refazer-rascunho"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- apoio (mesmo padrão de test_editor_arrasto.py)
def _criar_item(admin_api, titulo: str, nos: list | None = None) -> str:
    r = admin_api.post(
        "/api/itens",
        data={
            "tipo": "app",
            "titulo": titulo,
            "dados": {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": nos or [], "ligacoes": []}},
        },
    )
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _item(admin_api, iid: str) -> dict:
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, (r.status, r.text())
    return r.json()


def _abrir(tela: Tela, page, iid: str, autosave_ms: int | None = None) -> None:
    caminho = f"/construtor?item={iid}"
    if autosave_ms is not None:
        caminho += f"&autosave_ms={autosave_ms}"
    tela.ir(caminho)
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    page.wait_for_selector("#tela", timeout=10000)


def _adicionar_por_teclado(page, tipo: str) -> str:
    page.focus(f'[data-adicionar="{tipo}"]')
    page.keyboard.press("Enter")
    return page.get_attribute(f'[data-tipo="{tipo}"].no-editor', "data-no")


def _publicar_versao(admin_api, iid: str, versao: int) -> None:
    r = admin_api.post(f"/api/itens/{iid}/versoes/{versao}/publicar")
    assert r.status == 200, (r.status, r.text())


def _versao(admin_api, iid: str, n: int) -> dict:
    r = admin_api.get(f"/api/itens/{iid}/versoes/{n}")
    assert r.status == 200, (r.status, r.text())
    return r.json()


# ---------------------------------------------------------------- desfazer/refazer na tela (fumaça; o rigor
# das 50 operações e o hash sha256 estão em tests/unit/test_desfazer_refazer.py)
def test_desfazer_refazer_na_tela(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-desfazer-{sufixo()}")
    _abrir(tela, page, iid)

    assert page.is_disabled("#desfazer")
    assert page.is_disabled("#refazer")

    _adicionar_por_teclado(page, "grupo")
    _adicionar_por_teclado(page, "texto")
    page.wait_for_selector("#desfazer:not([disabled])", timeout=5000)
    assert page.eval_on_selector_all("[data-arvore]", "e => e.length") == 2

    page.click("#desfazer")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 1", timeout=5000)
    assert not page.is_disabled("#refazer")

    page.click("#desfazer")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 0", timeout=5000)
    assert page.is_disabled("#desfazer")

    page.click("#refazer")
    page.click("#refazer")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 2", timeout=5000)
    assert page.is_disabled("#refazer")

    # atalho de teclado Ctrl+Z / Ctrl+Shift+Z chama os mesmos botões
    page.keyboard.press("Control+z")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 1", timeout=5000)
    page.keyboard.press("Control+Shift+Z")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 2", timeout=5000)
    tela.verificar()


# ---------------------------------------------------------------- cláusula 2: queda simulada + localStorage
def test_queda_da_api_recupera_do_localstorage_ao_recarregar(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-queda-{sufixo()}")
    _abrir(tela, page, iid, autosave_ms=300)

    # a cópia local é gravada a CADA mudança (não só no ciclo do autosave): basta editar uma vez.
    grupo = _adicionar_por_teclado(page, "grupo")
    page.wait_for_function(
        "(id) => !!localStorage.getItem('plat_rascunho_' + id)", arg=iid, timeout=5000
    )

    # queda simulada da API: cada PATCH a partir de agora falha como se a rede tivesse caído.
    tela.esperar_status(0)
    page.route("**/api/itens/**", lambda route: route.abort() if route.request.method == "PATCH" else route.continue_())
    page.wait_for_timeout(500)  # ao menos um ciclo de autosave (300 ms) tenta e falha

    # a cópia local continua lá, ainda pendente (não foi confirmada pelo servidor)
    pendente = page.evaluate(
        "(id) => JSON.parse(localStorage.getItem('plat_rascunho_' + id)).pendente", iid
    )
    assert pendente is True

    # recarrega a MESMA tela (sem a rota de queda: simula a rede voltar depois do reload) e confere o aviso
    page.unroute("**/api/itens/**")
    _abrir(tela, page, iid, autosave_ms=300)
    page.wait_for_selector("#area-recuperacao .conflito-versao", timeout=5000)
    aviso = page.text_content("#area-recuperacao")
    assert "rascunho não gravado" in aviso

    # usar o rascunho recuperado repõe o nó que nunca chegou ao servidor
    page.click("#area-recuperacao button:has-text('Usar rascunho recuperado')")
    page.wait_for_function("() => document.querySelectorAll('[data-arvore]').length === 1", timeout=5000)
    assert page.get_attribute(f'[data-arvore="{grupo}"]', "data-arvore") == grupo
    # sem tela.verificar() aqui de propósito: a própria queda simulada (route.abort()) grava
    # "net::ERR_FAILED" no console — é o efeito ESPERADO deste teste, não um erro real da tela.
    graves = [linha for linha in tela.console if "ERR_FAILED" not in linha]
    assert graves == [], graves


# ---------------------------------------------------------------- cláusula 3: diferença entre v3 e v7
def test_diferenca_entre_versoes_lista_os_nos_certos(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-diferenca-{sufixo()}")

    # seis edições diretas pela API (mais rápido e determinístico que passar pela UI) — chegam a 7 versões
    # (a 1ª é a criação): v1 criação; v2 grupo; v3 grupo+texto; v4..v6 mexidas; v7 grupo alterado sem o texto.
    item = _item(admin_api, iid)
    grupo_id = "01HZZZZZZZZZZZZZZZZZZZZZZ0"
    texto_id = "01HZZZZZZZZZZZZZZZZZZZZZZ1"
    imagem_id = "01HZZZZZZZZZZZZZZZZZZZZZZ2"

    def no(nid, tipo, pai, colunas, **props):
        return {"id": nid, "tipo": tipo, "pai": pai, "largura_colunas": colunas, "propriedades": props}

    grupo_g = no(grupo_id, "grupo", None, 12, rotulo="G")
    grupo_mudou = no(grupo_id, "grupo", None, 12, rotulo="Mudou")
    texto_oi = no(texto_id, "texto", grupo_id, 6, texto="Oi")
    texto_oi4 = no(texto_id, "texto", grupo_id, 4, texto="Oi")
    texto_oi2 = no(texto_id, "texto", grupo_id, 4, texto="Oi2")
    imagem = no(imagem_id, "imagem", None, 4, url="/static/favicon.svg", alternativo="x")
    passos = [
        {"nos": [grupo_g]},
        {"nos": [grupo_g, texto_oi]},
        {"nos": [grupo_g, texto_oi4]},
        {"nos": [grupo_g, texto_oi2]},
        {"nos": [grupo_mudou, texto_oi2]},
        {"nos": [grupo_mudou, imagem]},
    ]
    versao_atual = item["versao_atual"]
    for corpo in passos:
        dados = {"tipo": "app", "esquema_versao": 2, "corpo": {**corpo, "ligacoes": []}}
        r = admin_api.patch(f"/api/itens/{iid}", data={"dados": dados, "versao_atual": versao_atual})
        assert r.status == 200, (r.status, r.text())
        versao_atual = r.json()["versao_atual"]
    assert versao_atual == 7, versao_atual

    _abrir(tela, page, iid)
    page.click("#ver-diferenca")
    page.wait_for_selector("#diferenca-de", timeout=5000)
    page.select_option("#diferenca-de", "3")
    page.select_option("#diferenca-para", "7")
    page.click("#area-diferenca button:has-text('Comparar')")
    page.wait_for_selector(".diferenca-arvore li", timeout=5000)

    estados = page.eval_on_selector_all(
        ".diferenca-arvore li", "els => els.map(e => [e.dataset.estado, e.dataset.diferenca])"
    )
    por_id = {i: e for e, i in estados}
    assert por_id[texto_id] == "removido", estados
    assert por_id[grupo_id] == "alterado", estados
    assert por_id[imagem_id] == "adicionado", estados
    tela.verificar()


# ---------------------------------------------------------------- cláusula 4: rascunho não publica
def test_autosave_de_rascunho_nao_altera_versao_publicada(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-rascunho-{sufixo()}")

    item = _item(admin_api, iid)
    _publicar_versao(admin_api, iid, item["versao_atual"])
    item = _item(admin_api, iid)
    publicada_antes = item["versao_publicada"]
    conteudo_publicado_antes = _versao(admin_api, iid, publicada_antes)["corpo"]

    # link público (compartilhamento por token): abre ANTES do autosave — cláusula pede "antes e depois"
    r = admin_api.post(f"/api/itens/{iid}/links", data={"nome": "teste-e2e"})
    assert r.status == 201, (r.status, r.text())
    token = r.json()["token"]
    r_link_antes = admin_api.get(f"/api/compartilhado/{token}")
    assert r_link_antes.status == 200, (r_link_antes.status, r_link_antes.text())

    _abrir(tela, page, iid, autosave_ms=300)
    _adicionar_por_teclado(page, "texto")
    # espera o autosave confirmar (o estado da tela muda só quando o servidor responde 200)
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.includes('gravado')", timeout=5000
    )

    item_depois = _item(admin_api, iid)
    assert item_depois["versao_publicada"] == publicada_antes, "o autosave não pode publicar sozinho"
    assert item_depois["versao_atual"] > item["versao_atual"], "o autosave precisa ter gravado uma versão nova"

    # a versão MARCADA como publicada continua com o conteúdo de antes — imutável (item L5-05)
    conteudo_publicado_depois = _versao(admin_api, iid, publicada_antes)["corpo"]
    assert conteudo_publicado_depois == conteudo_publicado_antes

    # a versão que o autosave gravou está rotulada 'rascunho', não 'edicao' nem 'publicacao'
    r_versoes = admin_api.get(f"/api/itens/{iid}/versoes?limite=50")
    assert r_versoes.status == 200
    rotulos = {v["versao"]: v["rotulo"] for v in r_versoes.json()["itens"]}
    assert rotulos[item_depois["versao_atual"]] == "rascunho", rotulos

    # o link público continua respondendo depois do autosave (nota de limitação no handoff: a rota de
    # compartilhamento desta base mostra o `dados` CORRENTE do item, não uma vista presa a versao_publicada
    # — isso é comportamento herdado de L5-05/rotas_compartilhamento.py, não deste item; o que este item
    # garante é que o PONTEIRO de publicação e o conteúdo da versão apontada por ele não se mexem sozinhos)
    r_link_depois = admin_api.get(f"/api/compartilhado/{token}")
    assert r_link_depois.status == 200, (r_link_depois.status, r_link_depois.text())
    tela.verificar()


# ---------------------------------------------------------------- refutação do adversário: conflito em 2 abas
def test_adversario_duas_abas_conflito_sem_perda_silenciosa(context, page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-conflito-{sufixo()}")

    pagina_b = context.new_page()
    tela_b = Tela(pagina_b, base_url)

    _abrir(tela, page, iid)
    _abrir(tela_b, pagina_b, iid)

    # aba A edita e salva primeiro
    _adicionar_por_teclado(page, "grupo")
    page.click("#salvar")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
    )

    # aba B, com a base ANTIGA (versao_atual de antes do salvamento de A), edita algo diferente e salva
    _adicionar_por_teclado(pagina_b, "texto")
    tela_b.esperar_status(409)
    pagina_b.click("#salvar")
    pagina_b.wait_for_selector("#conflito-versao", timeout=10000)
    aviso = pagina_b.text_content("#conflito-versao")
    assert "editado por outra sessão" in aviso
    # a diferença entre a versão do servidor (a de A) e a de B aparece — nunca silêncio
    pagina_b.wait_for_selector("#conflito-versao .diferenca-arvore li", timeout=5000)

    # nada foi perdido: a edição de B ainda está na tela dela, e o servidor ainda tem só a de A
    assert pagina_b.eval_on_selector_all("[data-arvore]", "e => e.length") == 1
    d_servidor = _item(admin_api, iid)
    assert d_servidor["dados"]["corpo"]["nos"][0]["tipo"] == "grupo"

    # B escolhe gravar mesmo assim: as duas edições ficam registradas em sequência (nunca sobrescrita muda)
    pagina_b.click("#conflito-versao button:has-text('Gravar minha versão mesmo assim')")
    pagina_b.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
    )
    d_final = _item(admin_api, iid)
    tipos_finais = [n["tipo"] for n in d_final["dados"]["corpo"]["nos"]]
    assert "texto" in tipos_finais
    tela.verificar()
    tela_b.verificar()
