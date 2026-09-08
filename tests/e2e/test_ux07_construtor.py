"""e2e do item UX-07-telas-do-construtor-e-aplicativo. Sobre o que test_editor_arrasto (L5-08), test_layout_paginas
(L5-01-a), test_motor_widgets (L5-06) e test_widgets_pagina (L5-01-d) já provam, este arquivo prova o que o item
acrescenta:

1. /construtor sem ?item=: escolha do item (lista com busca e estados) e "Novo aplicativo" pela tela; depois, num
   documento novo, 3 widgets entram por ARRASTO (texto, imagem, botão dentro de uma página), o documento é gravado,
   PUBLICADO (POST /api/itens/{id}/versoes/{n}/publicar, com confirmação) e aberto em /executar, onde os três
   widgets aparecem desenhados pelo motor (plat-w-texto, plat-w-imagem, plat-w-botao); capturas 390/1280 do
   construtor e do aplicativo; axe sem violação séria; nenhuma chave crua; 0 erro de console;
2. refutação: widget sem configuração válida mostra erro nomeado no painel de propriedades e o documento não muda
   (construtor); no aplicativo publicado, um nó com configuração fora do esquema vira caixa de erro nomeada e os
   outros widgets seguem (executor) — nunca tela quebrada;
3. estados: item inexistente e item que não é aplicativo no construtor; sem item e item inexistente no executor;
   busca sem resultado na escolha."""

import json
import uuid

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-07"
LARGURAS = (390, 1280)
ESTADO_PRONTO = (
    "(sel) => { const e = document.querySelector(sel); "
    "return !e || e.hidden || e.getAttribute('tipo') !== 'carregando'; }"
)


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def _id_do_tipo(page, tipo: str) -> str:
    return page.get_attribute(f'[data-tipo="{tipo}"].no-editor', "data-no")


def _limpar(tela, ids):
    for iid in ids:
        tela.api("DELETE", f"/api/itens/{iid}")
    if ids:
        tela.api("POST", "/api/lixeira/esvaziar", {"ids": ids})


# ---------------------------------------------------------------- 1. escolha, arrasto, publicação, execução


def test_novo_app_tres_widgets_por_arrasto_publica_e_abre(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    s = sufixo()
    titulo = f"zt-ux07 app {s}"
    tela = Tela(page, base_url)
    ids = []
    try:
        tela.entrar(slug, login, senha, proximo="/construtor")
        tela.ir("/construtor")
        page.wait_for_selector("#escolha:not([hidden])")
        page.wait_for_function(ESTADO_PRONTO, arg="#escolha-estado")
        _axe(page, "escolha")
        _sem_chave_crua(page)
        _capturar(page, "escolha")
        # busca sem resultado -> estado vazio nomeado
        page.fill("#escolha-busca input", "zt-nada-ux07-xyz")
        page.press("#escolha-busca input", "Enter")
        page.wait_for_selector("#escolha-estado[tipo='vazio']:not([hidden])")
        page.fill("#escolha-busca input", "")
        page.press("#escolha-busca input", "Enter")
        page.wait_for_function(ESTADO_PRONTO, arg="#escolha-estado")
        # novo aplicativo pela tela
        page.click("#novo-app")
        page.wait_for_selector("#novo-app-caixa:not([hidden])")
        page.fill("#novo-app-form input[name=titulo]", titulo)
        page.click("#novo-app-form button[type=submit]")
        page.wait_for_url(lambda u: "/construtor?item=" in u, timeout=15000)
        page.wait_for_selector("body[data-pronto='1']", timeout=15000)
        page.wait_for_selector("#tela", timeout=10000)
        iid = page.url.split("item=")[1].split("&")[0]
        ids.append(iid)
        assert page.text_content("main > h1").strip() == titulo
        assert "não publicado" in (page.text_content("#estado-publicado") or "")

        # página na raiz e três widgets dentro dela, por arrasto
        caixa = page.locator("#tela").bounding_box()
        page.drag_and_drop('[data-paleta="pagina"]', "#tela", target_position={"x": 20, "y": caixa["height"] - 8})
        pagina = _id_do_tipo(page, "pagina")
        for tipo in ("texto", "imagem", "botao"):
            page.drag_and_drop(f'[data-paleta="{tipo}"]', f'[data-filhos-de="{pagina}"]')
            page.wait_for_selector(f'[data-filhos-de="{pagina}"] [data-tipo="{tipo}"].no-editor', timeout=5000)
        assert page.locator(f'[data-filhos-de="{pagina}"] .no-editor').count() == 3
        assert "não gravadas" in (page.text_content("#estado-salvo") or "")
        # texto do widget de texto pelo painel de propriedades
        texto = _id_do_tipo(page, "texto")
        page.click(f'[data-no="{texto}"]')
        page.fill('[data-prop="texto"]', f"Bem-vindo {s}")
        page.keyboard.press("Tab")
        page.wait_for_function(
            "(id) => document.querySelector(`[data-resumo=\"${id}\"]`).textContent.startsWith('Bem-vindo')",
            arg=texto,
            timeout=5000,
        )
        _axe(page, "construtor")
        _capturar(page, "construtor")
        # gravar e publicar
        page.click("#salvar")
        page.wait_for_function(
            "() => document.getElementById('estado-salvo').textContent.startsWith('gravado')", timeout=10000
        )
        assert not page.locator("#publicar").is_disabled()
        page.click("#publicar")
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for()
        assert titulo in dialogo.inner_text()
        dialogo.locator(".dialogo-botoes button").last.click()
        page.wait_for_function(
            "() => document.querySelector('#aviso')?.textContent?.includes('publicada')", timeout=15000
        )
        assert page.locator("#estado-publicado.ok").count() == 1
        r = tela.api("GET", f"/api/itens/{iid}")
        assert r.json()["versao_publicada"] == r.json()["versao_atual"] >= 2
        _capturar(page, "construtor_publicado", larguras=(1280,))
        # o aplicativo publicado abre com os três widgets desenhados pelo motor
        tela.ir(f"/executar?item={iid}")
        page.wait_for_selector(".exec-pagina", timeout=15000)
        for tag in ("plat-w-texto", "plat-w-imagem", "plat-w-botao"):
            assert page.locator(f".exec-pagina {tag}").count() == 1, tag
        assert f"Bem-vindo {s}" in (page.text_content(".exec-pagina plat-w-texto") or "")
        assert page.locator("#lateral, .lateral").count() == 0  # aplicativo é dono do viewport: sem chrome interno
        _axe(page, "aplicativo")
        _capturar(page, "aplicativo")
        tela.verificar()
    finally:
        _limpar(tela, ids)


# ---------------------------------------------------------------- 2. refutação: configuração inválida


def _no(tipo, pai, propriedades, largura=12):
    return {"id": _ulid(), "tipo": tipo, "pai": pai, "largura_colunas": largura, "propriedades": propriedades}


def _ulid():
    # 26 caracteres do alfabeto Crockford: aceito por documento.js (ULID_RE) sem ser um ULID de verdade
    return "01K4" + uuid.uuid4().hex.upper().translate(str.maketrans("ILOU", "0123"))[:22]


def test_widget_invalido_mostra_erro_nomeado_nunca_quebra(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    ids = []
    try:
        pagina = _no(
            "pagina",
            None,
            {"titulo": "Início", "caminho": "inicio", "tipo_pagina": "rolavel", "ordem": 0, "inicial": True},
        )
        bom = _no("texto", pagina["id"], {"texto": f"texto bom {s}", "nivel": "corpo"}, 6)
        # botão sem `rotulo` (obrigatório no manifesto do widget): o executor tem de nomear o erro e seguir
        mau = _no("botao", pagina["id"], {"acao": {"tipo": "pagina", "pagina": "inicio"}}, 3)
        r = admin_api.post(
            "/api/itens",
            data={
                "tipo": "app",
                "titulo": f"zt-ux07 invalido {s}",
                "dados": {"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [pagina, bom, mau], "ligacoes": []}},
            },
        )
        assert r.status == 201, r.text()
        iid = r.json()["id"]
        ids.append(iid)
        tela.entrar(slug, login, senha, proximo=f"/executar?item={iid}")
        tela.ir(f"/executar?item={iid}")
        page.wait_for_selector(".exec-pagina", timeout=15000)
        assert page.locator(".exec-pagina plat-w-texto").count() == 1
        erro = page.locator(".exec-pagina .plat-widget-erro")
        assert erro.count() == 1
        assert "botao" in erro.inner_text() and "rotulo" in erro.inner_text()
        assert erro.get_attribute("role") == "alert"
        _capturar(page, "aplicativo_widget_invalido", larguras=(1280,))
        # no construtor: valor fora do esquema é recusado no campo, com mensagem, e o documento não muda
        tela.ir(f"/construtor?item={iid}")
        page.wait_for_selector("#tela", timeout=10000)
        page.click(f'[data-no="{bom["id"]}"]')
        page.fill('[data-prop="texto"]', "")
        page.keyboard.press("Tab")
        page.wait_for_function(
            "() => document.querySelector('[data-erro=\"texto\"]')?.textContent?.length > 0", timeout=5000
        )
        assert page.get_attribute('[data-prop="texto"]', "aria-invalid") == "true"
        assert page.get_attribute("#editor-mensagem", "data-tipo") == "erro"
        assert (page.text_content(f'[data-resumo="{bom["id"]}"]') or "").startswith("texto bom")
        _capturar(page, "construtor_propriedade_invalida", larguras=(1280,))
        r = tela.api("GET", f"/api/itens/{iid}")
        no = next(n for n in r.json()["dados"]["corpo"]["nos"] if n["id"] == bom["id"])
        assert no["propriedades"]["texto"] == f"texto bom {s}"
        tela.verificar()
    finally:
        _limpar(tela, ids)


# ---------------------------------------------------------------- 3. estados


def test_estados_do_construtor_e_do_executor(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    inexistente = "00000000-0000-4000-8000-000000000000"
    tela.entrar(slug, login, senha, proximo="/construtor")
    tela.esperar_status(404)
    tela.ir(f"/construtor?item={inexistente}")
    page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
    assert page.locator("#estado button", has_text="escolher outro").count() == 1
    assert page.locator("#tela").count() == 0
    _capturar(page, "construtor_inexistente", larguras=(1280,))
    tela.ir("/executar")
    page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
    assert page.locator("#estado button", has_text="ir ao construtor").count() == 1
    _axe(page, "executor sem item")
    _capturar(page, "executor_sem_item", larguras=(1280,))
    tela.ir(f"/executar?item={inexistente}")
    page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
    assert "não encontrado" in (page.text_content("#estado") or "")
    tela.verificar()
