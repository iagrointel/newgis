"""e2e do diálogo de impressão (item L2-12-b-layouts-elementos-exportacao): painel Layout do visualizador —
escolhe o modelo A3 completo, ajusta o título e um elemento por formulário, pede a prévia (PNG na tela), acrescenta
e remove elemento, grava o layout como item e como modelo do inquilino, e dispara a exportação por job (o link só
aparece quando o worker roda; sem worker o teste prova a fila e a tarefa nomeada). Erro nomeado: elemento fora do
papel volta 422 apontando o elemento. Capturas 390/1280, axe 0 sérias, console limpo, sem chave crua."""

from __future__ import annotations

import json

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
ITEM = "L2-12-b"


def _capturar(page, nome, larguras=(390, 1280)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"))
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    page.mouse.move(0, 0)
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def test_dialogo_de_impressao_previa_gravar_e_exportar(page, base_url, credenciais_demo, api_auth):
    if "/api/layouts/modelos" not in api_auth:
        pytest.skip("backend sem /api/layouts no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    # camada da bancada ligada, se houver (a prévia sem quadro não depende dela)
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas', { foco: false })")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    ids = page.evaluate("() => window.plat.mapa.catalogo.disponiveis.filter(f => f.servivel).map(f => f.id)")
    if ids:
        page.evaluate("(id) => window.plat.mapa.catalogo.ligar(id)", ids[0])
    page.keyboard.press("y")  # atalho do painel Layout
    page.wait_for_selector("#painel-layout:not([hidden])", timeout=5000)
    page.wait_for_function("() => document.querySelectorAll('#lay-modelo option').length >= 4", timeout=15000)
    page.wait_for_selector("#lay-doc-estado[tipo='vazio']:not([hidden])")
    _axe(page, "layout vazio")
    page.select_option("#lay-modelo", "a3-paisagem-completo")
    page.wait_for_selector("#lay-elementos li[data-tipo='mapa']", timeout=10000)
    assert page.locator("#lay-elementos li").count() == 9
    assert page.input_value("#lay-papel") == "A3" and page.input_value("#lay-orientacao") == "paisagem"
    s = sufixo()
    page.fill("#lay-nome", f"Layout e2e {s}")
    page.dispatch_event("#lay-nome", "change")
    # ajusta o título por formulário e o quadro para escala fixa
    page.fill("#lay-elementos li[data-tipo='titulo'] input[type='text']", f"Impressao e2e {s}")
    page.select_option("#lay-elementos li[data-tipo='mapa'] select", "escala")
    page.wait_for_selector("#lay-elementos li[data-tipo='mapa'] input[type='number'][min='100']")
    page.fill("#lay-elementos li[data-tipo='mapa'] input[type='number'][min='100']", "25000")
    _sem_chave_crua(page)
    _capturar(page, "dialogo_elementos")
    # prévia (quadros em cinza: instantânea)
    page.click("#lay-previa")
    page.wait_for_selector("#lay-previa-img:not([hidden])", timeout=60000)
    assert page.evaluate("() => document.querySelector('#lay-previa-img').naturalWidth") > 100
    assert "1:25.000" in (page.text_content("#lay-saida") or "")
    _axe(page, "prévia")
    _capturar(page, "dialogo_previa")
    # refutação: elemento fora do papel → 422 nomeado no elemento
    page.select_option("#lay-novo-tipo", "texto")
    page.click("#lay-novo")
    novo = page.locator("#lay-elementos li").last
    novo.locator("input[data-campo='x']").fill("900")
    novo.locator("input[data-campo='x']").dispatch_event("input")
    page.click("#lay-previa")
    page.wait_for_selector("#lay-doc-estado[tipo='erro']:not([hidden])", timeout=30000)
    assert "elementos[9]" in (page.text_content("#lay-doc-estado") or "")
    assert page.locator("#lay-elementos li.invalido").count() == 1
    _capturar(page, "dialogo_erro_nomeado", larguras=(1280,))
    novo.locator("button[data-remover]").click()
    assert page.locator("#lay-elementos li").count() == 9
    # gravar como item e como modelo do inquilino
    page.click("#lay-salvar")
    page.wait_for_function(
        "() => (document.querySelector('#lay-doc-estado').textContent || '').includes('gravado')", timeout=15000
    )
    item_id = page.input_value("#lay-existente")
    assert item_id
    page.click("#lay-salvar-modelo")
    page.wait_for_function(
        "() => (document.querySelector('#lay-doc-estado').textContent || '').includes('modelo')", timeout=15000
    )
    page.wait_for_function(
        "(n) => [...document.querySelectorAll('#lay-modelo option')].some(o => o.textContent.includes(n))",
        arg=f"Layout e2e {s}",
        timeout=15000,
    )
    try:
        # exportação: entra na fila como tarefa nomeada; o link aparece quando o worker conclui
        page.select_option("#lay-formato", "pdf")
        page.fill("#lay-dpi", "96")
        page.click("#lay-exportar")
        page.wait_for_selector("#lay-tarefa", timeout=30000)
        href = page.get_attribute("#lay-tarefa", "href") or ""
        assert href.startswith("/tarefas/")
        job = tela.api("GET", f"/api/{href.lstrip('/').replace('tarefas', 'jobs', 1)}").json()
        assert job["tipo"] == "layout.exportar" and job["parametros"]["formato"] == "pdf"
        try:
            page.wait_for_selector("#lay-link", timeout=120000)
            link = page.get_attribute("#lay-link", "href")
            r = tela.api("GET", link)
            assert r.status == 200 and r.body()[:5] == b"%PDF-"
            _capturar(page, "dialogo_exportado", larguras=(1280,))
        except Exception:  # noqa: BLE001 — sem worker na trilha o job fica na fila: registrado, não fingido
            estado = tela.api("GET", f"/api/jobs/{job['id']}").json()["estado"]
            assert estado in ("pendente", "rodando"), estado
        tela.api("POST", f"/api/jobs/{job['id']}/cancelar")
        _axe(page, "exportação")
        tela.verificar()
    finally:
        tela.api("DELETE", f"/api/itens/{item_id}")
        modelos = tela.api("GET", "/api/itens?tipo=layout&limite=100").json().get("itens", [])
        for m in modelos:
            if f"Layout e2e {s}" in (m.get("titulo") or ""):
                tela.api("DELETE", f"/api/itens/{m['id']}")
