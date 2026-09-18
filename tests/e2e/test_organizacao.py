"""e2e /admin/organizacao (item L0-07-a-configuracoes-org): o admin altera pela TELA o nome, a cor, o mapa
padrão e um bloco da página inicial do inquilino, mais o banner e o termo de acesso — e o resultado aparece
na entrada (marca na barra lateral + bloco montado), no mapa (vista padrão nova) e na tela de login ANTES da
senha (banner e termo como texto puro: HTML injetado aparece escrito, nunca vira marcação).

O logotipo fica de fora desta prova: a instância Garage da trilha não existe nesta bancada (toda trilha tem
PLAT_GARAGE_ADMIN_TOKEN vazio), então o caminho feliz de upload não é provável aqui — a recusa de logo > 1 MB,
que acontece ANTES de tocar o armazenamento, está provada em tests/api/test_org_config.py.

Capturas: L0-07-a-configuracoes-org_entrada.png, _mapa.png e _login_avisos.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-07-a-configuracoes-org"


def _corpo(org: dict) -> dict:
    """Corpo full-replace do PUT /api/org (mesmo contrato do PUT /api/org/ldap) para restaurar o inquilino."""
    return {
        "nome": org["nome"],
        "cor": org["cor"],
        "resumo": org["resumo"],
        "contato": org["contato"],
        "contatos_admin": list(org["contatos_admin"]),
        "idioma_padrao": org["idioma_padrao"],
        "unidades": org["regional"]["unidades"],
        "formato_data": org["regional"]["formato_data"],
        "formato_numero_data": org["regional"]["formato_numero_data"],
        "centro": org["mapa"]["centro"],
        "zoom": org["mapa"]["zoom"],
        "basemap": org["mapa"]["basemap"],
        "extent": org["mapa"]["extent"],
        "srid_padrao": org["mapa"]["srid_padrao"],
        "pagina_inicial": [dict(b) for b in org["pagina_inicial"]],
        "galeria_destaque": org["galeria_destaque"],
        "banner_aviso": org["banner_aviso"],
        "termo_acesso": org["termo_acesso"],
        "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"],
        "auth": dict(org["auth"]),
    }


def test_configuracoes_org_na_entrada_no_mapa_e_no_login(page, base_url, credenciais_demo, admin_api, medida):
    slug, login, senha = credenciais_demo
    r0 = admin_api.get("/api/org")
    assert r0.status == 200, r0.text()
    original = r0.json()

    marca = f"Demo E2E {sufixo()}"
    cor = "#1a7f4b"
    bloco_texto = f"aviso e2e {sufixo()} com <b>html</b> que não pode virar marcação"
    banner = f"manutenção <b>{sufixo()}</b> nesta sexta às 22h"
    termo = "ao entrar você declara ciência das regras internas de uso"

    tela = Tela(page, base_url, item=ITEM)
    try:
        tela.entrar(slug, login, senha)
        tela.medidas["pagina_pronta_ms_org"] = tela.ir("/admin/organizacao")

        # 1) identidade: nome + cor principal
        page.fill("#form-identidade [name='nome']", marca)
        page.fill("#form-identidade [name='cor']", cor)
        with page.expect_response(lambda r: r.url.endswith("/api/org") and r.request.method == "PUT" and r.ok):
            page.click("#form-identidade button[type='submit']")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)

        # 2) mapa padrão: centro dentro do recorte do pmtiles (bbox -46.62,-23.53,-46.42,-23.38) + zoom
        page.fill("#form-mapa [name='centro_lon']", "-46.55")
        page.fill("#form-mapa [name='centro_lat']", "-23.47")
        page.fill("#form-mapa [name='zoom']", "12")
        with page.expect_response(lambda r: r.url.endswith("/api/org") and r.request.method == "PUT" and r.ok):
            page.click("#form-mapa button[type='submit']")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)

        # 3) página inicial: limpar blocos herdados de outras corridas da trilha e gravar UM bloco de texto
        while page.locator("#blocos-lista fieldset.bloco-edit").count():
            page.locator("#blocos-lista fieldset.bloco-edit .bloco-remover").first.click()
        page.select_option("#bloco-add-tipo", "texto")
        page.click("#bloco-adicionar")
        fs = page.locator("#blocos-lista fieldset.bloco-edit").last
        fs.locator(".bloco-titulo").fill("Aviso e2e")
        fs.locator(".bloco-texto").fill(bloco_texto)
        with page.expect_response(lambda r: r.url.endswith("/api/org") and r.request.method == "PUT" and r.ok):
            page.click("#blocos-salvar")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)

        # 4) banner e termo de acesso (com tentativa de injeção de HTML no banner)
        page.fill("#form-avisos [name='banner_aviso']", banner)
        page.fill("#form-avisos [name='termo_acesso']", termo)
        with page.expect_response(lambda r: r.url.endswith("/api/org") and r.request.method == "PUT" and r.ok):
            page.click("#form-avisos button[type='submit']")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)

        # prova 1 — entrada: marca nova na barra lateral e bloco montado com texto puro
        tela.medidas["pagina_pronta_ms_entrada"] = tela.ir("/")
        assert page.locator("#marca-inquilino").inner_text() == marca
        chip = page.locator("#marca-cor")
        assert chip.count() == 1 and chip.get_attribute("title") == cor
        bloco = page.locator("#inicio-blocos .bloco-texto")
        assert bloco.count() == 1
        assert bloco_texto in (bloco.inner_text() or "")
        assert page.locator("#inicio-blocos .bloco-texto b").count() == 0
        tela.capturar("entrada")

        # prova 2 — mapa: abre na vista padrão nova do inquilino
        tela.medidas["pagina_pronta_ms_mapa"] = tela.ir("/mapa")
        coord = page.locator("#coordenadas").inner_text()
        assert "-23.47000, -46.55000" in coord, coord
        assert "z12.0" in coord, coord
        # tiles do primeiro quadro já pintaram antes da captura (o mesmo cuidado do test_mapa.py: sem a pausa
        # a captura pega o quadro do fundo só, ainda sem tile)
        page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
        page.wait_for_timeout(1500)
        tela.capturar("mapa")

        # prova 3 — login ANTES da senha: banner e termo escritos, injeção sem virar elemento
        tela.sair()
        tela.medidas["pagina_pronta_ms_login"] = tela.ir(f"/entrar?inquilino={slug}")
        b = page.locator("#org-banner")
        assert b.is_visible()
        assert banner in (b.text_content() or "")
        assert page.locator("#org-banner b").count() == 0
        tm = page.locator("#org-termo")
        assert tm.is_visible()
        assert termo in (tm.text_content() or "")
        tela.capturar("login_avisos")

        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        admin_api.put("/api/org", data=_corpo(original))
