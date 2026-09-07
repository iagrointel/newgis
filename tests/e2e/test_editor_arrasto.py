"""e2e do item L5-08-editor-arrasto: as primitivas de edição compartilhadas pelos construtores da linha L5.

O portão do item, cláusula a cláusula:

1. o MESMO layout de 5 componentes é montado duas vezes — uma só por arrasto (HTML5 Drag and Drop, mais o
   arrasto da alça de largura por Pointer Events), outra só por teclado e menus — e os dois documentos
   gravados pelo servidor são idênticos. `_canonico` troca cada ULID por `n1..nN` na ordem de profundidade,
   e só isso: o ULID é aleatório por construção (L5_CONCEITO D2, id gerado na criação), então comparar id a
   id compararia o gerador de números aleatórios, não o editor. Tudo o mais (tipo, pai, ordem, largura em
   colunas, propriedades, ligações) é comparado como o servidor gravou;
2. redimensionar por arrasto grava COLUNA, não pixel: a alça é arrastada por −4 larguras de coluna e o
   documento passa de 8 para 4, sem nenhuma chave em px;
3. a árvore reflete o aninhamento (aria-level e data-pai de cada nó);
4. o painel de propriedades recusa valor fora do esquema (zoom 99 num campo `maximum: 22`): mensagem no
   campo e documento inalterado depois de salvar;
5. sem biblioteca de arrasto embarcada — conferido em web/vendor/VERSOES.txt e nos imports dos módulos;
6. 0 erro de console em todos os caminhos.

Refutação do adversário no mesmo arquivo: soltar um contêiner dentro de um descendente dele, soltar fora da
tela, e montar tudo só com toque (viewport Pixel 7, sem nenhum gesto de arrasto).
"""

import json
import re
import time

import pytest

from tests.e2e.apoio import RAIZ, Tela, sufixo

ITEM = "L5-08-editor-arrasto"
EDITOR = RAIZ / "web" / "js" / "editor"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


# ---------------------------------------------------------------- apoio
def _criar_item(admin_api, titulo: str) -> str:
    r = admin_api.post(
        "/api/itens",
        data={
            "tipo": "app",
            "titulo": titulo,
            "dados": {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [], "ligacoes": []}},
        },
    )
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _dados(admin_api, iid: str) -> dict:
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, (r.status, r.text())
    return r.json()["dados"]


def _canonico(dados: dict) -> dict:
    """Mesma forma canônica de web/js/editor/documento.js::canonico, reimplementada aqui de propósito: se o
    teste chamasse a função do editor, um defeito na função passaria despercebido nos dois lados."""
    nos = dados["corpo"]["nos"]
    filhos = {}
    for n in nos:
        filhos.setdefault(n.get("pai"), []).append(n)
    ordem = []

    def desce(pai):
        for n in filhos.get(pai, []):
            ordem.append(n)
            desce(n["id"])

    desce(None)
    assert len(ordem) == len(nos), "há nó fora da árvore (pai inexistente)"
    mapa = {n["id"]: f"n{i + 1}" for i, n in enumerate(ordem)}
    return {
        "tipo": dados["tipo"],
        "esquema_versao": dados["esquema_versao"],
        "nos": [
            {
                "id": mapa[n["id"]],
                "tipo": n["tipo"],
                "pai": mapa.get(n.get("pai")),
                "largura_colunas": n["largura_colunas"],
                "propriedades": n.get("propriedades", {}),
            }
            for n in ordem
        ],
        "ligacoes": dados["corpo"].get("ligacoes", []),
    }


def _abrir(tela: Tela, page, iid: str) -> None:
    tela.ir(f"/construtor?item={iid}")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    page.wait_for_selector("#tela", timeout=10000)


def _salvar(page) -> None:
    page.click("#salvar")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
    )


def _largura_coluna(page) -> float:
    return page.evaluate(
        "() => { const g = document.getElementById('tela');"
        " const vao = parseFloat(getComputedStyle(g).columnGap) || 8;"
        " return (g.clientWidth + vao) / 12; }"
    )


def _id_do_tipo(page, tipo: str) -> str:
    return page.get_attribute(f'[data-tipo="{tipo}"].no-editor', "data-no")


# ---------------------------------------------------------------- cláusula 1 (central) + 2 + 3 + 6
def _montar_por_arrasto(page) -> None:
    caixa = page.locator("#tela").bounding_box()
    fundo = {"x": 20, "y": caixa["height"] - 8}
    page.drag_and_drop('[data-paleta="grupo"]', "#tela", target_position=fundo)
    grupo = _id_do_tipo(page, "grupo")
    page.drag_and_drop('[data-paleta="texto"]', f'[data-filhos-de="{grupo}"]')
    page.drag_and_drop('[data-paleta="imagem"]', f'[data-filhos-de="{grupo}"]')
    caixa = page.locator("#tela").bounding_box()
    fundo = {"x": 20, "y": caixa["height"] - 8}
    page.drag_and_drop('[data-paleta="mapa"]', "#tela", target_position=fundo)
    caixa = page.locator("#tela").bounding_box()
    page.drag_and_drop('[data-paleta="tabela"]', "#tela", target_position={"x": 20, "y": caixa["height"] - 8})

    # largura por ARRASTO da alça (Pointer Events): −4 colunas no mapa (8 -> 4)
    mapa = _id_do_tipo(page, "mapa")
    col = _largura_coluna(page)
    alca = page.locator(f'[data-alca="{mapa}"]').bounding_box()
    page.mouse.move(alca["x"] + alca["width"] / 2, alca["y"] + alca["height"] / 2)
    page.mouse.down()
    page.mouse.move(alca["x"] + alca["width"] / 2 - 4 * col, alca["y"] + alca["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_selector(f'[data-no="{mapa}"][data-colunas="4"]', timeout=5000)

    # propriedade por mouse
    texto = _id_do_tipo(page, "texto")
    page.click(f'[data-no="{texto}"]')
    page.fill('[data-prop="texto"]', "Bem-vindo")
    page.keyboard.press("Tab")
    page.wait_for_function(
        "(id) => document.querySelector(`[data-resumo=\"${id}\"]`).textContent === 'Bem-vindo'", arg=texto, timeout=5000
    )


def _montar_por_teclado(page) -> None:
    def adicionar(tipo):
        page.focus(f'[data-adicionar="{tipo}"]')
        page.keyboard.press("Enter")

    adicionar("grupo")
    adicionar("texto")     # entra no contêiner selecionado
    adicionar("imagem")    # entra no mesmo contêiner (pai do selecionado)
    adicionar("mapa")
    mapa = _id_do_tipo(page, "mapa")
    page.focus(f'[data-arvore="{mapa}"]')
    page.keyboard.press("Alt+ArrowLeft")   # desaninha: vai para o fim da raiz
    page.wait_for_selector(f'[data-arvore="{mapa}"][data-pai=""]', timeout=5000)
    adicionar("tabela")

    page.focus(f'[data-arvore="{mapa}"]')
    for _ in range(4):
        page.keyboard.press("Shift+ArrowLeft")   # 8 -> 4 colunas
        page.focus(f'[data-arvore="{mapa}"]')
    page.wait_for_selector(f'[data-no="{mapa}"][data-colunas="4"]', timeout=5000)

    texto = _id_do_tipo(page, "texto")
    page.focus(f'[data-arvore="{texto}"]')
    page.keyboard.press("Enter")               # seleciona pela árvore
    page.focus('[data-prop="texto"]')
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("Bem-vindo")
    page.keyboard.press("Tab")
    page.wait_for_function(
        "(id) => document.querySelector(`[data-resumo=\"${id}\"]`).textContent === 'Bem-vindo'", arg=texto, timeout=5000
    )


def test_arrasto_e_teclado_produzem_o_mesmo_documento(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    grava = medida(ITEM)

    id_arrasto = _criar_item(admin_api, f"zt-arrasto-{sufixo()}")
    _abrir(tela, page, id_arrasto)
    t0 = time.perf_counter()
    _montar_por_arrasto(page)
    ms_arrasto = round((time.perf_counter() - t0) * 1000, 1)
    _salvar(page)
    d1 = _dados(admin_api, id_arrasto)
    tela.capturar("tela_arrasto")

    id_teclado = _criar_item(admin_api, f"zt-teclado-{sufixo()}")
    _abrir(tela, page, id_teclado)
    t0 = time.perf_counter()
    _montar_por_teclado(page)
    ms_teclado = round((time.perf_counter() - t0) * 1000, 1)
    _salvar(page)
    d2 = _dados(admin_api, id_teclado)

    c1, c2 = _canonico(d1), _canonico(d2)
    assert c1 == c2, json.dumps({"arrasto": c1, "teclado": c2}, ensure_ascii=False, indent=1)
    assert len(c1["nos"]) == 5, c1
    assert [n["tipo"] for n in c1["nos"]] == ["grupo", "texto", "imagem", "mapa", "tabela"], c1
    # cláusula 2: largura em coluna, nunca pixel — nem no documento inteiro
    assert [n["largura_colunas"] for n in c1["nos"]] == [12, 6, 4, 4, 6], c1
    assert "px" not in json.dumps(d1, ensure_ascii=False)
    # aninhamento gravado
    assert c1["nos"][1]["pai"] == "n1" and c1["nos"][2]["pai"] == "n1" and c1["nos"][3]["pai"] is None

    # cláusula 3: a árvore reflete o aninhamento (nível 2 para os dois filhos, 1 para os três da raiz).
    # `aria-level` mora no `<li role=listitem>` que envolve o botão (item L5-12: `role=button` não admite
    # `aria-level`, e a estrutura deixou de se anunciar como `role=tree`/`treeitem` — ver o cabeçalho de
    # web/js/editor/editor.js), não no `[data-arvore]` em si; o valor e o aninhamento são os mesmos de antes.
    niveis = page.eval_on_selector_all(
        "[data-arvore]",
        "els => els.map(e => [e.closest('.arvore-linha').getAttribute('aria-level'), e.dataset.pai !== ''])",
    )
    assert niveis == [["1", False], ["2", True], ["2", True], ["1", False], ["1", False]], niveis

    tela.verificar()
    grava("nos_no_layout", len(c1["nos"]), "nós", "e2e: layout de 5 componentes montado pelos dois caminhos")
    grava("diferenca_arrasto_teclado", 0, "campos", "json.dumps(canonico(arrasto)) == json.dumps(canonico(teclado))")
    grava("montagem_por_arrasto_ms", ms_arrasto, "ms", "5 componentes + redimensionar + propriedade, só arrasto")
    grava("montagem_por_teclado_ms", ms_teclado, "ms", "o mesmo layout só por teclado e menus")


# ---------------------------------------------------------------- cláusula 4
def test_propriedade_fora_do_esquema_e_recusada(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-esquema-{sufixo()}")
    _abrir(tela, page, iid)

    page.focus('[data-adicionar="mapa"]')
    page.keyboard.press("Enter")
    mapa = _id_do_tipo(page, "mapa")
    page.fill('[data-prop="zoom"]', "99")       # esquema: integer, maximum 22
    page.keyboard.press("Tab")
    assert "máximo 22" in page.text_content('[data-erro="zoom"]')
    assert page.get_attribute('[data-prop="zoom"]', "aria-invalid") == "true"

    page.fill('[data-prop="zoom"]', "12")
    page.keyboard.press("Tab")
    assert page.text_content('[data-erro="zoom"]').strip() == ""

    _salvar(page)
    d = _dados(admin_api, iid)
    no = next(n for n in d["corpo"]["nos"] if n["id"] == mapa)
    assert no["propriedades"]["zoom"] == 12, no      # o 99 nunca entrou no documento
    tela.verificar()


# ---------------------------------------------------------------- refutação do adversário
def test_adversario_ciclo_e_solta_fora(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-adv-{sufixo()}")
    _abrir(tela, page, iid)

    # contêiner externo com um contêiner dentro
    page.focus('[data-adicionar="grupo"]')
    page.keyboard.press("Enter")
    fora = _id_do_tipo(page, "grupo")
    page.focus('[data-adicionar="grupo"]')
    page.keyboard.press("Enter")
    todos = page.eval_on_selector_all('[data-tipo="grupo"].no-editor', "e => e.map(x => x.dataset.no)")
    dentro = next(i for i in todos if i != fora)

    # 1) arrastar o de fora para dentro do de dentro (ciclo) — recusado, documento intacto
    page.drag_and_drop(f'[data-no="{fora}"] > .no-cabecalho', f'[data-filhos-de="{dentro}"]')
    assert page.get_attribute(f'[data-arvore="{fora}"]', "data-pai") == ""
    assert "dentro de si" in page.text_content("#editor-mensagem")

    # 2) soltar fora da tela (na barra lateral, que não é alvo) — nada muda
    antes = page.eval_on_selector_all("[data-arvore]", "e => e.map(x => x.dataset.no)")
    page.drag_and_drop('[data-paleta="texto"]', "#lateral")
    assert page.eval_on_selector_all("[data-arvore]", "e => e.map(x => x.dataset.no)") == antes

    # 3) o menu de mover NÃO oferece destino dentro do próprio nó
    destinos = page.eval_on_selector_all(f'[data-mover-para="{fora}"] option', "o => o.map(x => x.value)")
    assert dentro not in destinos and fora not in destinos, destinos

    _salvar(page)
    d = _dados(admin_api, iid)
    assert len(d["corpo"]["nos"]) == 2
    tela.verificar()


def test_so_toque_pixel7_monta_o_layout(playwright, browser, base_url, credenciais_demo, admin_api):
    """Sem nenhum gesto de arrasto (o HTML5 DnD não dispara em toque): paleta por toque, menu 'mover para' e
    botões de largura. É a alternativa de ponteiro único da WCAG 2.2 SC 2.5.7."""
    slug, login, senha = credenciais_demo
    ctx = browser.new_context(**playwright.devices["Pixel 7"], locale="pt-BR", base_url=base_url)
    page = ctx.new_page()
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    iid = _criar_item(admin_api, f"zt-toque-{sufixo()}")
    _abrir(tela, page, iid)

    page.tap('[data-adicionar="grupo"]')
    grupo = _id_do_tipo(page, "grupo")
    page.tap('[data-adicionar="texto"]')
    texto = _id_do_tipo(page, "texto")
    assert page.get_attribute(f'[data-arvore="{texto}"]', "data-pai") == grupo
    page.tap('[data-adicionar="mapa"]')
    mapa = _id_do_tipo(page, "mapa")
    page.select_option(f'[data-mover-para="{mapa}"]', "")
    page.tap(f'[data-mover="{mapa}"]')
    assert page.get_attribute(f'[data-arvore="{mapa}"]', "data-pai") == ""
    for _ in range(4):
        page.tap(f'[data-largura-menos="{mapa}"]')
    page.wait_for_selector(f'[data-no="{mapa}"][data-colunas="4"]', timeout=5000)

    _salvar(page)
    d = _dados(admin_api, iid)
    assert [n["tipo"] for n in d["corpo"]["nos"]] == ["grupo", "texto", "mapa"]
    assert next(n for n in d["corpo"]["nos"] if n["tipo"] == "mapa")["largura_colunas"] == 4
    tela.verificar()
    ctx.close()


# ---------------------------------------------------------------- cláusula 5 (0 kB de biblioteca de arrasto)
def test_sem_biblioteca_de_arrasto(medida):
    versoes = (RAIZ / "web" / "vendor" / "VERSOES.txt").read_text(encoding="utf-8").lower()
    for nome in ("sortable", "dnd", "dragula", "interact", "gridstack", "muuri", "draggable"):
        assert nome not in versoes, f"{nome} apareceu em VERSOES.txt sem decisão do item"
    bytes_editor = 0
    for arq in sorted(EDITOR.glob("*.js")):
        texto = arq.read_text(encoding="utf-8")
        assert "/static/vendor/" not in texto, arq
        assert not re.search(r"^import .*vendor", texto, re.M), arq
        assert "?v=" not in texto, f"{arq}: import com ?v= cria duas instâncias do módulo"
        bytes_editor += len(texto.encode("utf-8"))
    medida(ITEM)("biblioteca_de_arrasto_bytes", 0, "bytes", "web/vendor/VERSOES.txt sem SortableJS/dnd-kit/GridStack")
    medida(ITEM)("editor_proprio_bytes", bytes_editor, "bytes", "soma de web/js/editor/*.js (código próprio)")
