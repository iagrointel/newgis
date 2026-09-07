"""e2e do item L5-12-acessibilidade-i18n-construtores: acessibilidade e idioma da BASE dos construtores
(`web/js/editor/{documento,arrasto,esquema,paleta,editor,tela}.js`, item L5-08). O portão do item, cláusula
a cláusula:

1. axe-core (vendorizado em `tests/e2e/vendor/`, MPL-2.0, só para teste — nunca servido em /static nem
   referenciado pelo produto) sem violação `critical`/`serious` nas telas do construtor. Hoje só existe UMA
   tela concreta (`/construtor`, item L5-08), que abre item de tipo `app` OU `painel` — os dois testados
   aqui. O construtor de FORMULÁRIO (`L5-03-form-builder`) está `pendente` no laço: não existe tela para
   testar ainda. Isso não é lacuna deste item — a acessibilidade mora em `criarEditor()`, a primitiva
   COMPARTILHADA que o L5-03 vai reusar (mesmo comentário no cabeçalho de `editor.js`); testar a base é testar
   o que o formulário vai herdar de graça no dia em que existir.
2. e2e só por teclado: cria os 3 widgets (`grupo`, `texto`, `mapa`), liga uma ação (clique de `texto` abre
   `mapa`), salva e publica — tudo por `page.focus`/`page.keyboard`, nenhum `page.click`/`drag_and_drop`/
   `select_option`. "Criar app" é a montagem do DOCUMENTO do app pelo construtor (o item em si nasce pela
   API, como em `test_editor_arrasto.py`; criar o REGISTRO do item é tela do L0-03/catálogo, outro item).
3. troca de idioma do construtor sem recarregar: dispara `beforeunload`/nenhuma navegação, o dicionário troca
   e os textos mudam na mesma página.
4. "0 chave sem tradução" tem teste ESTÁTICO próprio em `tests/unit/test_i18n_construtor_paridade.py`
   (não precisa de navegador); aqui a MESMA garantia é medida ao vivo: nenhum texto cru de chave
   (`^[a-z0-9]+\\.[a-z0-9_.]+$`, o padrão de `test_i18n_cru.py`) aparece na tela em pt-BR, en ou es.

Refutação do adversário no mesmo arquivo: percorre a árvore de acessibilidade do playwright e lista todo
controle (button/input/select/[role=treeitem]/[role=group]) sem nome acessível — um achado reprova."""

import re

import pytest

from tests.e2e.apoio import RAIZ, Tela, sufixo

ITEM = "L5-12-acessibilidade-i18n-construtores"
AXE = RAIZ / "tests" / "e2e" / "vendor" / "axe-4.12.1.min.js"
CHAVE_CRUA = re.compile(r"^[a-z0-9]+\.[a-z0-9_.]+$")

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- apoio
def _criar_item(admin_api, titulo: str, tipo: str = "app") -> str:
    r = admin_api.post(
        "/api/itens",
        data={
            "tipo": tipo,
            "titulo": titulo,
            "dados": {"tipo": tipo, "esquema_versao": 2, "corpo": {"nos": [], "ligacoes": []}},
        },
    )
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _dados(admin_api, iid: str) -> dict:
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, (r.status, r.text())
    return r.json()["dados"]


def _abrir(tela: Tela, page, iid: str) -> None:
    tela.ir(f"/construtor?item={iid}")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    page.wait_for_selector("#tela", timeout=10000)


def _id_do_tipo(page, tipo: str) -> str:
    return page.get_attribute(f'[data-tipo="{tipo}"].no-editor', "data-no")


def _adicionar_por_teclado(page, tipo: str) -> None:
    page.focus(f'[data-adicionar="{tipo}"]')
    page.keyboard.press("Enter")


def _rodar_axe(page) -> list[dict]:
    page.add_script_tag(path=str(AXE))
    resultado = page.evaluate(
        "async () => { const r = await axe.run(document, {resultTypes: ['violations']}); return r.violations; }"
    )
    return resultado


def _textos_visiveis(page) -> str:
    return page.evaluate("() => document.body.innerText")


def _chaves_cruas(texto: str) -> list[str]:
    achadas = []
    for token in re.split(r"[\s,;:()\[\]{}\"']+", texto):
        if CHAVE_CRUA.match(token):
            achadas.append(token)
    return sorted(set(achadas))


# ---------------------------------------------------------------- cláusula 1: axe-core
@pytest.mark.parametrize("tipo", ["app", "painel"])
def test_axe_construtor_sem_violacao_critica_ou_seria(tipo, page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-axe-{tipo}-{sufixo()}", tipo=tipo)
    _abrir(tela, page, iid)
    _adicionar_por_teclado(page, "grupo")
    _adicionar_por_teclado(page, "texto")
    _adicionar_por_teclado(page, "mapa")
    violacoes = _rodar_axe(page)
    graves = [v for v in violacoes if v["impact"] in ("critical", "serious")]
    medida(ITEM)(
        f"axe_violacoes_criticas_serias_{tipo}", len(graves), "violações",
        f"axe.run() em /construtor?item=<{tipo}> com 3 widgets — resultTypes violations, filtro impact",
    )
    assert graves == [], [(v["id"], v["impact"], v["help"], [n["target"] for n in v["nodes"]]) for v in graves]
    tela.verificar()


# ---------------------------------------------------------------- cláusula 2: só teclado, fim a fim
def test_fluxo_so_teclado_criar_widgets_ligar_acao_publicar(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-teclado-full-{sufixo()}")
    _abrir(tela, page, iid)

    # 3 widgets, só teclado (botão "Adicionar" da paleta, foco + Enter — a alternativa de ponteiro único e
    # de teclado da WCAG 2.2 SC 2.5.7 que o L5-08 já construiu)
    _adicionar_por_teclado(page, "grupo")
    _adicionar_por_teclado(page, "texto")
    _adicionar_por_teclado(page, "mapa")
    texto_id = _id_do_tipo(page, "texto")
    mapa_id = _id_do_tipo(page, "mapa")

    # anúncio de posição (refutação do adversário pede exatamente este texto na região aria-live)
    mensagem = page.text_content("#editor-mensagem")
    assert "adicionado na posição" in mensagem, mensagem

    # seleciona "texto" pela árvore (foco + Enter, sem clique) para abrir o painel de Ações
    page.focus(f'[data-arvore="{texto_id}"]')
    page.keyboard.press("Enter")
    page.wait_for_selector("#acao-alvo", timeout=5000)

    # liga a ação por teclado: foca o select, digita o início do rótulo do alvo (type-ahead nativo do
    # <select>, sem mouse), Tab até o botão e Enter — nenhum select_option/click nesta função.
    page.focus("#acao-alvo")
    page.keyboard.type("Mapa")
    page.wait_for_function(
        "() => document.getElementById('acao-alvo').selectedOptions[0]?.textContent.startsWith('Mapa')",
        timeout=5000,
    )
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_selector("li:has-text('abre')", timeout=5000)

    # salva e publica, só teclado
    page.focus("#salvar")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
    )
    page.focus("#publicar")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.getElementById('aviso').textContent.includes('publicad')", timeout=10000
    )

    d = _dados(admin_api, iid)
    assert [n["tipo"] for n in d["corpo"]["nos"]] == ["grupo", "texto", "mapa"]
    ligacoes = d["corpo"]["ligacoes"]
    assert len(ligacoes) == 1 and ligacoes[0]["origem"] == texto_id and ligacoes[0]["alvo"] == mapa_id, ligacoes

    r = admin_api.get(f"/api/itens/{iid}")
    item = r.json()
    assert item["versao_publicada"] is not None and item["versao_publicada"] == item["versao_atual"], item
    medida(ITEM)(
        "fluxo_so_teclado_widgets_acao_publicar", 1, "fluxo completo",
        "criar 3 widgets + ligar ação + salvar + publicar, só page.focus/page.keyboard",
    )
    tela.verificar()


# ---------------------------------------------------------------- cláusula 3: troca de idioma sem recarregar
def test_troca_de_idioma_sem_recarregar(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-idioma-{sufixo()}")
    _abrir(tela, page, iid)

    # marca a carga ATUAL da página; um reload cria um "window" novo e o marcador desaparece
    page.evaluate("() => { window.__marca_sem_recarregar = true; }")
    assert page.text_content("#salvar") == "Salvar"

    page.select_option("#idioma-construtor", "en")
    page.wait_for_function("() => document.getElementById('salvar').textContent === 'Save'", timeout=5000)
    assert page.evaluate("() => window.__marca_sem_recarregar") is True, "a troca de idioma recarregou a página"
    assert page.text_content("#publicar") == "Publish"
    assert page.get_attribute("#tela", "aria-label") == "Screen"
    assert "html" == page.evaluate("() => document.documentElement.tagName.toLowerCase()")
    assert page.evaluate("() => document.documentElement.lang") == "en"

    page.select_option("#idioma-construtor", "es")
    page.wait_for_function("() => document.getElementById('salvar').textContent === 'Guardar'", timeout=5000)
    assert page.evaluate("() => window.__marca_sem_recarregar") is True
    assert page.evaluate("() => document.documentElement.lang") == "es"

    page.select_option("#idioma-construtor", "pt-BR")
    page.wait_for_function("() => document.getElementById('salvar').textContent === 'Salvar'", timeout=5000)
    assert page.evaluate("() => window.__marca_sem_recarregar") is True
    tela.verificar()


# ---------------------------------------------------------------- cláusula 4: 0 chave crua na tela, nos 3 idiomas
@pytest.mark.parametrize("idioma,item_texto", [("pt-BR", "Salvar"), ("en", "Save"), ("es", "Guardar")])
def test_nenhuma_chave_crua_no_construtor(idioma, item_texto, page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-cru-{idioma}-{sufixo()}")
    _abrir(tela, page, iid)
    if idioma != "pt-BR":
        page.select_option("#idioma-construtor", idioma)
        page.wait_for_function(f"() => document.getElementById('salvar').textContent === '{item_texto}'", timeout=5000)
    _adicionar_por_teclado(page, "grupo")
    _adicionar_por_teclado(page, "texto")
    grupo_id = _id_do_tipo(page, "grupo")
    page.focus(f'[data-arvore="{grupo_id}"]')
    page.keyboard.press("Enter")  # seleciona: abre Propriedades e Ações também
    cruas = _chaves_cruas(_textos_visiveis(page))
    assert cruas == [], (idioma, cruas)
    tela.verificar()


# ---------------------------------------------------------------- refutação do adversário: nome acessível
@pytest.mark.parametrize("tipo", ["app", "painel"])
def test_adversario_todo_controle_tem_nome_acessivel(tipo, page, base_url, credenciais_demo, admin_api):
    """Percorre a árvore de acessibilidade do playwright (a mesma que um leitor de tela consulta via
    plataforma de acessibilidade do SO) e lista todo controle interativo sem nome computado. Cobre os quatro
    painéis (paleta, tela, estrutura, propriedades) mais o painel de Ações deste item."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-adv-nome-{tipo}-{sufixo()}", tipo=tipo)
    _abrir(tela, page, iid)
    _adicionar_por_teclado(page, "grupo")
    _adicionar_por_teclado(page, "texto")
    _adicionar_por_teclado(page, "mapa")
    grupo_id = _id_do_tipo(page, "grupo")
    page.focus(f'[data-arvore="{grupo_id}"]')
    page.keyboard.press("Enter")  # com um item selecionado a árvore, propriedades e ações têm o máximo de controles

    seletor = "#editor-raiz button, #editor-raiz input, #editor-raiz select, #editor-raiz [role]"
    sem_nome = page.eval_on_selector_all(
        seletor,
        """els => els.filter(el => {
            const label = el.getAttribute('aria-label');
            const labelledby = el.getAttribute('aria-labelledby');
            const texto = (el.textContent || '').trim();
            const titulo = el.getAttribute('title');
            const temLabelFor = el.id && document.querySelector(`label[for="${el.id}"]`);
            const dentroDeLabel = el.closest('label');
            return !(label || labelledby || texto || titulo || temLabelFor || dentroDeLabel);
        }).map(el => el.outerHTML.slice(0, 140))""",
    )
    assert sem_nome == [], sem_nome
    tela.verificar()
