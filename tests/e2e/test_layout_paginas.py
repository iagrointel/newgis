"""e2e do item L5-01-a-layout-paginas: páginas e layout do app sobre as primitivas de arrasto do L5-08.

O portão do item, cláusula a cláusula:

1. app com 2 páginas (tela cheia com mapa central + rolável) navegável por menu, com cabeçalho e painel
   lateral recolhível — TUDO criado só por arrasto (as propriedades de texto/enum/booleano são preenchidas
   pelo painel gerado do esquema, mesma convenção do e2e do L5-08: a ESTRUTURA nasce de HTML5 Drag and Drop,
   nunca de uma chamada de API pelo teste);
2. grade responsiva mantém proporção: dois filhos da grade guardam a MESMA razão de largura em dois viewports
   bem diferentes (1200 px e 600 px) — CSS Grid com `fr` garante isso por definição, o teste MEDE, não confia;
3. janela modal abre por botão e fecha por Esc (`<dialog>` nativo: `showModal()`/Esc do próprio navegador);
4. a URL muda por página (querystring `?pagina=<caminho>`, sem recarregar) e reabre na página certa depois de
   um F5 de verdade.

Refutação do adversário no mesmo arquivo: 6 níveis de linha/coluna aninhados (construídos direto pela API,
onde o arrasto já não acrescenta nada novo à prova) mais um item ao lado da árvore, redimensionados em três
larguras de viewport — reprova se algum nível zerar de tamanho, ficar oculto, ou o documento estourar
horizontalmente.
"""

import json
import secrets
import time

import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-01-a-layout-paginas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    """ULID de FORMATO válido (^[0-7][0-9A-HJKMNP-TV-Z]{25}$) — só precisa satisfazer o regex do servidor
    (`ULID_RE` em app/catalogo/documento.py); não precisa ser cronologicamente ordenável para este teste."""
    primeiro = secrets.choice("01234567")
    resto = "".join(secrets.choice(_CROCKFORD) for _ in range(25))
    return primeiro + resto


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


def _gravar_dados(admin_api, iid: str, corpo: dict) -> None:
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, (r.status, r.text())
    versao = r.json()["versao_atual"]
    r = admin_api.patch(
        f"/api/itens/{iid}",
        data={"dados": {"tipo": "app", "esquema_versao": 2, "corpo": corpo}, "versao_atual": versao},
    )
    assert r.status == 200, (r.status, r.text())


def _dados(admin_api, iid: str) -> dict:
    r = admin_api.get(f"/api/itens/{iid}")
    assert r.status == 200, (r.status, r.text())
    return r.json()["dados"]


def _abrir_construtor(tela: Tela, page, iid: str) -> None:
    tela.ir(f"/construtor?item={iid}")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    page.wait_for_selector("#tela", timeout=10000)


def _abrir_executor(tela: Tela, page, iid: str, pagina: str | None = None) -> None:
    caminho = f"/executar?item={iid}" + (f"&pagina={pagina}" if pagina else "")
    tela.ir(caminho)
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)


def _salvar(page) -> None:
    page.click("#salvar")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
    )


def _ids_do_tipo(page, tipo: str) -> list[str]:
    """ids de todos os nós desse tipo NA ORDEM em que aparecem na tela do construtor (ordem de profundidade,
    igual à ordem da lista do documento — ver documento.js::emProfundidade)."""
    return page.eval_on_selector_all(f'.no-editor[data-tipo="{tipo}"]', "els => els.map(e => e.dataset.no)")


def _soltar_no_fundo(page, tipo_paleta: str) -> None:
    caixa = page.locator("#tela").bounding_box()
    page.drag_and_drop(f'[data-paleta="{tipo_paleta}"]', "#tela", target_position={"x": 20, "y": caixa["height"] - 8})


def _soltar_dentro(page, tipo_paleta: str, pai_id: str) -> None:
    """Solta no FUNDO do contêiner alvo (mesma técnica de `_soltar_no_fundo`), nunca no centro dele: quando
    o contêiner já tem filho, o centro geométrico cai POR CIMA do filho existente (que preenche a largura
    inteira), e o `drop` do HTML5 é entregue ao elemento mais profundo sob o ponteiro — o filho, não o
    contêiner-alvo — fazendo o novo nó entrar um nível mais fundo do que o pedido."""
    alvo = f'[data-filhos-de="{pai_id}"]'
    caixa = page.locator(alvo).bounding_box()
    page.drag_and_drop(
        f'[data-paleta="{tipo_paleta}"]', alvo, target_position={"x": 10, "y": max(4, caixa["height"] - 4)}
    )


def _selecionar(page, no_id: str) -> None:
    page.click(f'[data-no="{no_id}"] > .no-cabecalho')


def _definir_texto(page, no_id: str, campo: str, valor: str) -> None:
    _selecionar(page, no_id)
    seletor = f'[data-prop="{campo}"]'
    page.fill(seletor, "")
    page.fill(seletor, valor)
    page.keyboard.press("Tab")


def _definir_select(page, no_id: str, campo: str, valor: str) -> None:
    _selecionar(page, no_id)
    page.select_option(f'[data-prop="{campo}"]', valor)


def _definir_checkbox(page, no_id: str, campo: str, marcado: bool) -> None:
    _selecionar(page, no_id)
    if marcado:
        page.check(f'[data-prop="{campo}"]')
    else:
        page.uncheck(f'[data-prop="{campo}"]')


def _definir_largura(page, no_id: str, colunas: int) -> None:
    _selecionar(page, no_id)
    page.fill("#prop-largura", str(colunas))
    page.keyboard.press("Tab")


# ---------------------------------------------------------------- construção (cláusula 1: só por arrasto)
def _montar_app_por_arrasto(page) -> dict:
    # página 1: Central, tela cheia, com cabeçalho+menu e um mapa
    _soltar_no_fundo(page, "pagina")
    central = _ids_do_tipo(page, "pagina")[0]
    _soltar_dentro(page, "cabecalho", central)
    cab_central = _ids_do_tipo(page, "cabecalho")[0]
    _soltar_dentro(page, "menu", cab_central)
    _soltar_dentro(page, "mapa", central)
    mapa_id = _ids_do_tipo(page, "mapa")[0]

    # página 2: Detalhes, rolável, com cabeçalho+menu, painel lateral, grade (2 filhos) e janela
    _soltar_no_fundo(page, "pagina")
    detalhes = _ids_do_tipo(page, "pagina")[1]
    _soltar_dentro(page, "cabecalho", detalhes)
    cab_detalhes = _ids_do_tipo(page, "cabecalho")[1]
    _soltar_dentro(page, "menu", cab_detalhes)

    _soltar_dentro(page, "painel_lateral", detalhes)
    painel_id = _ids_do_tipo(page, "painel_lateral")[0]
    _soltar_dentro(page, "texto", painel_id)
    texto_lateral = _ids_do_tipo(page, "texto")[0]

    _soltar_dentro(page, "grade", detalhes)
    grade_id = _ids_do_tipo(page, "grade")[0]
    _soltar_dentro(page, "texto", grade_id)
    texto_grade = _ids_do_tipo(page, "texto")[1]
    _soltar_dentro(page, "imagem", grade_id)
    imagem_grade = _ids_do_tipo(page, "imagem")[0]

    _soltar_dentro(page, "janela", detalhes)
    janela_id = _ids_do_tipo(page, "janela")[0]
    _soltar_dentro(page, "texto", janela_id)
    texto_janela = _ids_do_tipo(page, "texto")[2]

    # propriedades (painel gerado do esquema — mesma convenção do e2e do L5-08)
    _definir_texto(page, central, "caminho", "central")
    _definir_texto(page, central, "titulo", "Central")
    _definir_select(page, central, "tipo_pagina", "tela_cheia")
    _definir_checkbox(page, central, "inicial", True)

    _definir_texto(page, detalhes, "caminho", "detalhes")
    _definir_texto(page, detalhes, "titulo", "Detalhes")
    _definir_texto(page, detalhes, "ordem", "1")

    _definir_texto(page, texto_lateral, "texto", "Barra lateral")
    _definir_texto(page, texto_janela, "texto", "Conteudo da janela")

    _definir_texto(page, grade_id, "colunas", "3")
    _definir_largura(page, texto_grade, 8)
    _definir_largura(page, imagem_grade, 4)

    return {
        "central": central, "detalhes": detalhes, "mapa": mapa_id, "painel_lateral": painel_id,
        "grade": grade_id, "texto_grade": texto_grade, "imagem_grade": imagem_grade, "janela": janela_id,
    }


# ---------------------------------------------------------------- teste principal
def test_paginas_e_layout_por_arrasto(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    grava = medida(ITEM)

    iid = _criar_item(admin_api, f"zt-paginas-{sufixo()}")
    _abrir_construtor(tela, page, iid)

    t0 = time.perf_counter()
    ids = _montar_app_por_arrasto(page)
    ms_montagem = round((time.perf_counter() - t0) * 1000, 1)
    _salvar(page)
    tela.capturar("construtor_paginas")

    dados = _dados(admin_api, iid)
    nos = dados["corpo"]["nos"]
    assert "px" not in json.dumps(dados, ensure_ascii=False)
    tipos_por_id = {n["id"]: n["tipo"] for n in nos}
    assert tipos_por_id[ids["central"]] == "pagina"
    assert tipos_por_id[ids["detalhes"]] == "pagina"
    grava("construtor_montagem_ms", ms_montagem, "ms", "test_paginas_e_layout_por_arrasto")

    # ---- cláusula 1: 2 páginas navegáveis por menu, cabeçalho + painel lateral recolhível
    _abrir_executor(tela, page, iid)
    pagina_ativa = page.locator(".exec-pagina")
    assert pagina_ativa.get_attribute("data-pagina") == "central"
    assert "exec-pagina-tela-cheia" in pagina_ativa.get_attribute("class")
    assert page.locator(".exec-cabecalho").count() >= 1
    assert page.locator(".exec-mapa").count() == 1

    links = [
        tuple(x)
        for x in page.eval_on_selector_all(
            ".exec-menu a", "els => els.map(e => [e.dataset.irPagina, e.getAttribute('aria-current')])"
        )
    ]
    assert ("central", "page") in links, links
    assert ("detalhes", None) in links, links

    page.click('.exec-menu a[data-ir-pagina="detalhes"]')
    page.wait_for_selector('.exec-pagina[data-pagina="detalhes"]', timeout=5000)
    assert "pagina=detalhes" in page.url
    assert "exec-pagina-rolavel" in page.locator(".exec-pagina").get_attribute("class")
    assert page.locator(".exec-painel-lateral").count() == 1

    # painel lateral recolhível
    envolucro = page.locator(".exec-painel-lateral-envolucro")
    assert "recolhido" not in envolucro.get_attribute("class")
    alternar = page.locator(f'[data-painel-lateral-alternar="{ids["painel_lateral"]}"]')
    alternar.click()
    page.wait_for_function(
        "() => document.querySelector('.exec-painel-lateral-envolucro').classList.contains('recolhido')",
        timeout=5000,
    )
    assert page.locator(".exec-painel-lateral").get_attribute("aria-hidden") == "true"
    alternar.click()
    page.wait_for_function(
        "() => !document.querySelector('.exec-painel-lateral-envolucro').classList.contains('recolhido')",
        timeout=5000,
    )

    # ---- cláusula 4: URL muda por página e reabre na certa depois de F5
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    assert page.locator(".exec-pagina").get_attribute("data-pagina") == "detalhes"
    grava("url_persiste_apos_f5", 1, "bool", "test_paginas_e_layout_por_arrasto")

    # ---- cláusula 2: grade responsiva mantém proporção (8:4 = 2:1) em dois viewports
    def _razao():
        a = page.locator(f'[data-no="{ids["texto_grade"]}"]').bounding_box()["width"]
        b = page.locator(f'[data-no="{ids["imagem_grade"]}"]').bounding_box()["width"]
        return a / b

    page.set_viewport_size({"width": 1200, "height": 800})
    razao_larga = _razao()
    page.set_viewport_size({"width": 600, "height": 800})
    razao_estreita = _razao()
    grava("grade_razao_larga", round(razao_larga, 3), "razao", "test_paginas_e_layout_por_arrasto")
    grava("grade_razao_estreita", round(razao_estreita, 3), "razao", "test_paginas_e_layout_por_arrasto")
    assert abs(razao_larga - 2.0) < 0.2, razao_larga
    assert abs(razao_estreita - 2.0) < 0.2, razao_estreita
    assert abs(razao_larga - razao_estreita) < 0.1, (razao_larga, razao_estreita)
    page.set_viewport_size({"width": 1280, "height": 800})

    # ---- cláusula 3: janela modal abre por botão e fecha por Esc
    dialogo = page.locator(f'dialog[data-janela="{ids["janela"]}"]')
    assert dialogo.get_attribute("open") is None
    page.click(f'[data-janela-abrir="{ids["janela"]}"]')
    page.wait_for_selector(f'dialog[data-janela="{ids["janela"]}"][open]', timeout=5000)
    assert "Conteudo da janela" in dialogo.inner_text()
    page.keyboard.press("Escape")
    page.wait_for_function(
        "(id) => !document.querySelector(`dialog[data-janela=\"${id}\"]`).hasAttribute('open')",
        arg=ids["janela"],
        timeout=5000,
    )

    tela.verificar()


# ---------------------------------------------------------------- refutação do adversário
def test_adversario_seis_niveis_linha_coluna_sem_overflow_ou_widget_oculto(
    page, base_url, credenciais_demo, admin_api, medida
):
    """6 níveis alternando linha/coluna, com um irmão ao lado do primeiro nível, redimensionado em 3
    larguras de viewport (1280, 800, 320 — a última bem mais estreita que qualquer widget de conteúdo).
    Construído direto pela API (a estrutura já não testa NADA do arrasto que os testes acima não testem; o
    que se mede aqui é o executor sob aninhamento adverso, não a montagem)."""
    item_teste = "test_adversario_seis_niveis_linha_coluna_sem_overflow_ou_widget_oculto"
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    grava = medida(ITEM)

    pagina_id = _ulid()
    irmao_id = _ulid()
    tipos = ["linha", "coluna", "linha", "coluna", "linha", "coluna"]
    niveis = [_ulid() for _ in tipos]
    folha_id = _ulid()

    propriedades_pagina = {
        "titulo": "Aninhado", "caminho": "aninhado", "tipo_pagina": "rolavel",
        "ordem": 0, "oculta": False, "inicial": True,
    }
    nos = [
        {"id": pagina_id, "tipo": "pagina", "pai": None, "largura_colunas": 12, "propriedades": propriedades_pagina},
        {"id": irmao_id, "tipo": "texto", "pai": pagina_id, "largura_colunas": 4,
         "propriedades": {"texto": "Irmao do nivel 1", "nivel": "corpo"}},
    ]
    pai = pagina_id
    for i, (tipo_no, no_id) in enumerate(zip(tipos, niveis, strict=True)):
        propriedades = {"alinhar": "inicio"}
        nos.append({"id": no_id, "tipo": tipo_no, "pai": pai, "largura_colunas": 12 - i, "propriedades": propriedades})
        pai = no_id
    nos.append({"id": folha_id, "tipo": "texto", "pai": pai, "largura_colunas": 12,
                "propriedades": {"texto": "Folha no nivel 6", "nivel": "corpo"}})

    iid = _criar_item(admin_api, f"zt-adversario-{sufixo()}")
    _gravar_dados(admin_api, iid, {"nos": nos, "ligacoes": []})
    _abrir_executor(tela, page, iid)

    todos_ids = niveis + [irmao_id, folha_id]
    for largura in (1280, 800, 320):
        page.set_viewport_size({"width": largura, "height": 900})
        page.wait_for_timeout(60)  # reflow do navegador antes de medir (sem espera fixa longa, só 1 quadro)
        medidas = page.evaluate(
            """(ids) => ids.map((id) => {
                const el = document.querySelector(`[data-no="${id}"]`);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return { id, w: r.width, h: r.height, display: cs.display, visibility: cs.visibility };
            })""",
            todos_ids,
        )
        for m in medidas:
            assert m is not None, ("nó desapareceu do DOM", largura)
            assert m["display"] != "none", (m, largura)
            assert m["visibility"] != "hidden", (m, largura)
            assert m["w"] > 0 and m["h"] > 0, (m, largura, "widget oculto (largura ou altura zero)")
        estouro = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        grava(f"adversario_estouro_px_{largura}", estouro, "px", item_teste)
        assert estouro <= 1, (estouro, largura, "overflow horizontal com 6 níveis de linha/coluna")

    tela.verificar()
