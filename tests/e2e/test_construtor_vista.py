"""e2e playwright da tela /vista-de-camada (item `L5-32-vistas-de-camada`) contra a URL interna real (nginx
na frente do uvicorn, porque a aplicação não serve /static/ sozinha — mesma razão do e2e do L5-31).

Prova a cláusula "vista com filtro e 3 campos ocultos criada pela tela": a camada-mãe é criada pela tela do
L5-31, os três campos vão para a área "ocultos" (dois por arrasto HTML5 real, um por clique — a alternativa
de teclado), o filtro é digitado e a vista é criada. Depois a própria tela mostra o que a vista PUBLICA,
lido de GET /api/vistas/{id}: nenhum dos três ocultos pode aparecer ali. 0 erro de console."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L5-32-vistas-de-camada"
OCULTOS = ["cpf_do_produtor", "salario", "observacao_interna"]


def _capturar(page, nome: str) -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


@pytest.fixture(scope="session")
def api_vista(api_auth):
    faltam = [r for r in ("/api/camadas/{camada_id}/vistas", "/api/vistas/{vista_id}") if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item {ITEM})")
    return api_auth


def _criar_camada_mae(page, tela, titulo: str) -> None:
    page.goto(f"{tela.base_url}/construtor-camada")
    page.fill("#camada-titulo", titulo)
    page.select_option("#camada-geometria", "Point")
    for nome, tipo in [("nome", "text"), ("uf", "text"), ("cpf_do_produtor", "text"),
                       ("salario", "double precision"), ("observacao_interna", "text")]:
        page.click(f"#paleta .chip-tipo[data-tipo='{tipo}']")
        linhas = page.locator("#zona-campos .campo-linha")
        linhas.nth(linhas.count() - 1).locator("input[data-campo='nome']").fill(nome)
    page.click("#criar-camada")
    page.wait_for_selector("#aviso[data-tipo='ok']", timeout=20000)


def test_vista_com_filtro_e_tres_campos_ocultos_criada_pela_tela(page, base_url, credenciais_demo, api_vista):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/construtor-camada")

    titulo_mae = f"zt e2e mae {sufixo()}"
    _criar_camada_mae(page, tela, titulo_mae)

    page.goto(f"{base_url.rstrip('/')}/vista-de-camada")
    page.wait_for_selector("#zona-visiveis .campo-linha")
    page.select_option("#vista-camada", label=titulo_mae)
    page.wait_for_function(
        "() => document.querySelectorAll('#zona-visiveis .campo-linha').length >= 5", timeout=15000)
    _capturar(page, "campos_da_mae")

    page.fill("#vista-titulo", f"zt e2e vista {sufixo()}")
    page.fill("#vista-filtro", "uf = 'SP'")

    # dois por arrasto real (dragstart/dragover/drop nativos), um por clique
    for nome in OCULTOS[:2]:
        page.locator(f"#zona-visiveis .chip-tipo[data-campo='{nome}']").drag_to(page.locator("#zona-ocultos"))
        page.wait_for_selector(f"#zona-ocultos .chip-tipo[data-campo='{nome}']")
    page.click(f"#zona-visiveis .chip-tipo[data-campo='{OCULTOS[2]}']")
    page.wait_for_function(
        "() => document.querySelectorAll('#zona-ocultos .campo-linha').length === 3", timeout=15000)
    _capturar(page, "tres_campos_ocultos")

    tela.esperar_status(201)
    page.click("#criar-vista")
    page.wait_for_selector("#aviso[data-tipo='ok']", timeout=20000)
    page.wait_for_selector("#resultado-cartao:not([hidden])", timeout=20000)

    resumo = page.text_content("#resultado-resumo")
    assert "3 oculto" in resumo, resumo
    assert "uf = 'SP'" in resumo, resumo
    publicados = page.text_content("#resultado-corpo")
    for oculto in OCULTOS:
        assert oculto not in publicados, f"{oculto} apareceu entre os campos publicados pela vista"
    _capturar(page, "vista_criada")

    tela.verificar()
