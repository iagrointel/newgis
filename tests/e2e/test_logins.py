"""e2e /admin/logins (item L0-08-e-mapeamento-provisionamento): o admin de demo vê o provedor OIDC criado pela
API na lista, abre as regras, escolhe 'só por convite', acrescenta uma regra 'gis-editores' -> editor com um grupo
interno, salva e a API devolve o que a tela gravou; a tabela de paridade com a Esri está na tela. Captura
L0-08-e-mapeamento-provisionamento_logins.png. Não precisa do Keycloak: só a configuração."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-08-e-mapeamento-provisionamento"


def test_tela_logins_regras(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    r = admin_api.post("/api/grupos", data={"nome": f"e2e-logins-{s}"})
    assert r.status == 201, r.text()
    grupo_id = r.json()["id"]
    r = admin_api.post("/api/org/oidc", data={
        "habilitado": True, "rotulo": f"Entrar com o IdP e2e {s}", "ordem": 5,
        "issuer": "https://idp-e2e.invalido/realms/teste", "client_id": f"cliente-e2e-{s}",
        "escopos": "openid profile email", "atributo_grupos": "groups", "perfil_padrao": "visualizador",
        "mapa_grupo_perfil": {},
    })
    assert r.status == 201, r.text()
    provedor_id = r.json()["id"]
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/logins")
        tela.medidas["pagina_pronta_ms_logins"] = tela.ir("/admin/logins")
        page.wait_for_function(
            "() => [...document.querySelectorAll('#tabela tbody td')]"
            f".some(td => td.textContent === 'Entrar com o IdP e2e {s}')",
            timeout=15000,
        )
        assert page.locator("#paridade tbody tr").count() >= 6
        linha = page.locator("#tabela tbody tr", has_text=f"Entrar com o IdP e2e {s}")
        linha.locator("button", has_text="Regras").click()
        page.wait_for_selector("#form-regras", timeout=15000)
        page.select_option("#r-criacao", "convite")
        page.click("#regra-nova")
        regra = page.locator("#regras tbody tr.regra").last
        regra.locator("input[name='valor']").fill("gis-editores")
        regra.locator("select[name='perfil']").select_option("editor")
        regra.locator(f".grupos input[value='{grupo_id}']").check()
        page.fill("#r-pasta", "Pessoal de {login}")
        page.click("#regras-salvar")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_logins.png"), full_page=True)
        logins = tela.api("GET", "/api/org/logins").json()["provedores"]
        p = next(x for x in logins if x["tipo"] == "oidc" and x["id"] == provedor_id)
        assert p["provisionamento"]["criacao"] == "convite" and p["provisionamento"]["pasta"] == "Pessoal de {login}"
        regra = p["provisionamento"]["mapa"]["gis-editores"]
        assert regra == {"perfil": "editor", "papel_id": None, "grupos": [grupo_id]}
        assert p["mapa_grupo_perfil"] == {"gis-editores": "editor"}
        page.wait_for_function(
            "() => [...document.querySelectorAll('#tabela tbody td')]"
            ".some(td => td.textContent === 'só por convite prévio')",
            timeout=15000,
        )
        tela.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (apoio.py Tela.ir)")
    finally:
        admin_api.delete(f"/api/org/oidc/{provedor_id}")
        admin_api.delete(f"/api/grupos/{grupo_id}")
