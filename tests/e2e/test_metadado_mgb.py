"""e2e do item L0-09-b-editor-iso-mgb: abre a aba Metadado de uma camada, preenche o essencial, valida (lista de
faltantes), salva, confere na página do item que o título mudou (sincronizado) e captura a tela. 0 erro de
console fora do 404 esperado da miniatura ausente."""

import pytest

from tests.e2e.apoio import RAIZ, sufixo  # noqa: F401 (RAIZ mantém paridade de import com os irmãos do pacote)
from tests.e2e.apoio_catalogo import TelaCatalogo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def api_catalogo_metadado(api_auth):
    faltam = [r for r in ("/api/itens", "/api/itens/{id}/metadado") if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L0-09-b-editor-iso-mgb)")
    return api_auth


def test_metadado_mgb_fluxo_completo(page, base_url, credenciais_demo, admin_api, api_catalogo_metadado, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    titulo = f"E2E camada mgb {s}"
    r = admin_api.post(
        "/api/itens",
        data={
            "tipo": "camada_vetorial",
            "titulo": titulo,
            "resumo": "resumo original",
            "tags": [],
            "dados": {
                "schema": "plat_trabalho", "tabela": "zt_mgb_inexistente", "geometria": "Point", "srid": 4326,
                "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
            },
        },
    )
    assert r.ok, r.text()
    item_id = r.json()["id"]
    try:
        tela = TelaCatalogo(page, base_url)
        tela.entrar(slug, admin_login, senha_admin, proximo=f"/conteudo/{item_id}")
        page.wait_for_selector("#item-abas", timeout=15000)
        page.click("#item-aba-metadado")
        page.wait_for_selector("#mgb-form", timeout=15000)
        tela.capturar("metadado_essencial")

        # falta ao menos organização/e-mail/licença/sistema de referência: valida antes de preencher
        page.click("#mgb-validar")
        page.wait_for_selector("#mgb-faltantes .faltantes", timeout=10000)
        faltando_antes = page.text_content("#mgb-faltantes")
        assert "organiza" in faltando_antes.lower() or "licen" in faltando_antes.lower()

        page.fill("#mgb-contato-org", "iAgroSat")
        page.fill("#mgb-contato-email", "mgb@exemplo.org")
        page.fill("#mgb-licenca", "CC BY 4.0")
        page.fill("#mgb-esp-xmin", "-50")
        page.fill("#mgb-esp-ymin", "-20")
        page.fill("#mgb-esp-xmax", "-40")
        page.fill("#mgb-esp-ymax", "-10")
        page.fill("#mgb-sr-codigo", "4326")
        page.fill("#mgb-sr-codespace", "EPSG")
        novo_titulo = f"{titulo} (MGB)"
        page.fill("#mgb-item-resumo", "resumo essencial preenchido")
        page.fill("#mgb-item-tags", "agro, mgb")

        page.click("#mgb-validar")
        page.wait_for_selector("#mgb-faltantes .ok", timeout=10000)
        tela.capturar("metadado_validado")

        page.click("#mgb-salvar")
        page.wait_for_selector("#mgb-aviso[data-tipo='ok']", timeout=15000)
        tela.capturar("metadado_salvo")

        # título sincronizado: muda pela Visão geral, confere que persistiu na página do item
        page.click("#item-aba-visao")
        page.wait_for_selector("[data-campo='titulo']", timeout=10000)
        page.click("[data-campo='titulo'] button.editar")
        dialogo = page.locator("#painel-editar dialog[open]")
        dialogo.wait_for(state="visible", timeout=10000)
        dialogo.locator("input[name='titulo']").fill(novo_titulo)
        dialogo.locator("button[type='submit']").click()
        page.wait_for_function(
            "esperado => document.querySelector('#item-titulo')?.textContent.trim() === esperado",
            arg=novo_titulo,
            timeout=10000,
        )

        page.click("#item-aba-metadado")
        page.wait_for_selector("#mgb-form", timeout=15000)
        tela.capturar("metadado_apos_titulo_sincronizado")

        r2 = admin_api.get(f"/api/itens/{item_id}/metadado")
        assert r2.ok, r2.text()
        assert r2.json()["campos"]["identificacao"]["titulo"] == novo_titulo
        assert r2.json()["campos"]["contato"]["organizacao"] == "iAgroSat"
        gravar_medidas_local = medida("L0-09-b-editor-iso-mgb")
        gravar_medidas_local(
            "e2e_fluxo_completo_passou", 1, "bool",
            "playwright chromium: preencher, validar, salvar, título sincronizado",
        )
    finally:
        admin_api.delete(f"/api/itens/{item_id}")
