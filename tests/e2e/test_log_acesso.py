"""e2e /admin/log (ADR 0002 seções 9 e 15.6): a tabela tem as linhas dos acessos desta sessão; filtro por status 2xx;
o link Exportar CSV aponta para /api/log?formato=csv e devolve text/csv; a aba Eventos lista o evento de entrar.
Captura L0-02-tenant-auth_log.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_log_filtro_csv_e_eventos(page, base_url, credenciais_demo, medida):
    slug, admin_login, senha_admin = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, admin_login, senha_admin, proximo="/admin/log")
    tela.medidas["pagina_pronta_ms_log"] = tela.ir("/admin/log")
    page.wait_for_function("() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1", timeout=15000)
    assert any("/api/eu" in c for c in page.locator("#tabela tbody td").all_text_contents())
    page.locator("#filtros select[name='status']").select_option("2xx")
    with page.expect_response(lambda r: "/api/log?" in r.url and "status=2xx" in r.url and "formato" not in r.url):
        page.click("#filtrar")
    page.wait_for_function("() => [...document.querySelectorAll('#tabela tbody .marcador')]"
                           ".every(m => m.textContent[0] === '2')", timeout=15000)
    marcadores = page.locator("#tabela tbody .marcador").all_text_contents()
    assert marcadores and all(m.strip().startswith("2") for m in marcadores), marcadores
    href = page.get_attribute("#exportar-csv", "href")
    assert href.startswith("/api/log?") and "formato=csv" in href and "status=2xx" in href, href
    csv = tela.api("GET", href)
    assert csv.status == 200 and csv.headers.get("content-type", "").startswith("text/csv"), csv.headers
    assert len(csv.text().splitlines()) >= 2
    tela.capturar("log")
    page.click("#aba-eventos")
    page.wait_for_function("() => document.querySelectorAll('#tabela-eventos tbody td:not(.vazio)').length >= 1",
                           timeout=15000)
    assert any("usuarios/entrar" in c for c in page.locator("#tabela-eventos tbody td").all_text_contents())
    tela.verificar()
    gravar_medidas(medida, tela)
