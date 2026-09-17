"""e2e do editor de ficha da imagem (item L1-27): abrir /imagens/{id}/ficha, ver o aviso da regra D17 num item
sem licença escrita, preencher a ficha pela TELA, gravar, e conferir que o cartão de licença passa a mostrar a
atribuição e a liberar o link público. Depois, pela mesma tela, trocar para a licença comercial e conferir que
o cartão volta a dizer que o link público está bloqueado.

A lista de licenças do seletor tem de vir da API (a tela não escreve licença nenhuma): o teste confere que as
opções do campo são exatamente as de GET /api/imagens/licencas.

Salta enquanto a URL interna não publicar as rotas do item no OpenAPI (é o mesmo padrão dos outros e2e da casa:
a suíte de trilha não tem nginx servindo /static/, então o editor só é exercitado onde a aplicação está de pé).
"""

import pytest

from tests.e2e.apoio import Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ROTAS = ("/api/imagens/licencas", "/api/imagens/{item_id}/ficha", "/api/itens")

FICHA = {
    "plataforma": "sentinel-2b",
    "instrumentos": "msi",
    "gsd": "10",
    "data_aquisicao": "2026-05-01T13:00:00Z",
    "fornecedor": "agência de teste interno",
    "atribuicao": "atribuição de teste interno",
    "nuvem_pct": "3.2",
}


@pytest.fixture(scope="session")
def api_ficha(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (rotas do item L1-27)")
    return api_auth


@pytest.fixture
def raster_de_teste(admin_api):
    r = admin_api.post("/api/itens", data={
        "tipo": "raster", "titulo": f"E2E imagem {sufixo()}",
        "dados": {"colecao": "sem-colecao", "stac_id": "sem-item", "perfil": "visual",
                  "origem": "copiado", "srid_nativo": 4326},
    })
    assert r.status == 201, r.text()
    item = r.json()
    yield item
    admin_api.delete(f"/api/itens/{item['id']}?forcado=true")


def test_editor_de_ficha_da_imagem(page, base_url, credenciais_demo, api_ficha, raster_de_teste, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    caminho = f"/imagens/{raster_de_teste['id']}/ficha"
    tela.entrar(slug, login, senha, proximo=caminho)
    tela.medidas["pagina_ficha_ms"] = tela.ir(caminho)
    # `pronto()` marca a tela assim que os módulos carregam; o cartão só se preenche depois das duas
    # chamadas à API (licenças e ficha), por isso o e2e espera o cartão, não só o corpo pronto
    page.wait_for_selector("#form-ficha [name='licenca']", timeout=20000)

    # 1. item sem ficha: o aviso da regra D17 aparece e o link público está bloqueado
    aviso = (page.text_content("#aviso-licenca") or "").strip()
    assert "não vendável" in aviso, aviso
    assert (page.text_content("#ficha-licenca-rotulo") or "").strip() == "sem licença escrita"
    assert "bloqueado" in (page.text_content("#ficha-link-publico") or "")

    # 2. o seletor de licença é a tabela da API, item por item, na mesma ordem
    da_api = admin_api.get("/api/imagens/licencas").json()["licencas"]
    na_tela = page.eval_on_selector(
        "#form-ficha [name='licenca']", "el => [...el.options].map(o => ({valor: o.value, rotulo: o.textContent}))"
    )
    assert [o["valor"] for o in na_tela] == [lic["codigo"] for lic in da_api]
    assert [o["rotulo"] for o in na_tela] == [lic["rotulo"] for lic in da_api]

    # 3. preencher pela TELA e gravar com uma licença livre que exige atribuição
    for nome, valor in FICHA.items():
        page.fill(f"#form-ficha [name='{nome}']", valor)
    page.select_option("#form-ficha [name='licenca']", "cc-by-4.0")
    page.select_option("#form-ficha [name='fonte']", "upload")
    page.click("#form-ficha button[type=submit]")
    page.wait_for_selector("#ficha-link-publico:text-matches('permitido')", timeout=20000)

    # 4. a ficha mostra a atribuição e a licença gravadas
    assert (page.text_content("#ficha-atribuicao") or "").strip() == FICHA["atribuicao"]
    assert (page.text_content("#ficha-licenca-rotulo") or "").strip() == "CC BY 4.0"
    assert "autorizada" in (page.text_content("#ficha-redistribuicao") or "")
    tela.capturar("ficha_livre")

    # 5. o metadado ISO 19115-2 do item sai pela ligação da própria tela e é um MI_Metadata
    iso = page.get_attribute("#ficha-iso", "href")
    assert iso.endswith("perfil=imagem"), iso
    r = tela.api("GET", iso)
    assert r.status == 200, r.text()
    assert "MI_Metadata" in r.text()

    # 6. trocar para licença comercial pela tela: o link público volta a ficar bloqueado
    page.select_option("#form-ficha [name='licenca']", "comercial-eula")
    page.click("#form-ficha button[type=submit]")
    page.wait_for_selector("#ficha-link-publico:text-matches('bloqueado')", timeout=20000)
    assert "não autorizada" in (page.text_content("#ficha-redistribuicao") or "")
    tela.capturar("ficha_comercial")

    # 7. e o servidor recusa o link público desse item (a tela não é a única guarda)
    tela.esperar_status(400)
    recusa = tela.api("POST", f"/api/itens/{raster_de_teste['id']}/links", {"nome": "e2e"})
    assert recusa.status == 400, recusa.text()
    assert recusa.json()["erro"] == "licenca_sem_redistribuicao"

    tela.verificar()
