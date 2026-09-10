"""e2e /admin/auditoria (item L7-20): a tela lista a trilha do inquilino, filtra por USUÁRIO e por PERÍODO,
exporta CSV e JSON, e mostra a retenção com o nome do agendamento de expurgo. Nenhum botão apaga linha: a
trilha é append-only e a tela tem de dizer isso.

Captura L7-20-trilha-auditoria_auditoria.png; 0 erro de console (cláusula P1).
"""

import pytest

from tests.e2e.apoio_auditoria import TelaAuditoria, gravar_medidas_auditoria

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_tela_auditoria_filtra_por_usuario_e_periodo(page, base_url, credenciais_demo, medida):
    slug, admin_login, senha_admin = credenciais_demo
    tela = TelaAuditoria(page, base_url)
    tela.entrar(slug, admin_login, senha_admin, proximo="/admin/auditoria")
    tela.medidas["pagina_pronta_ms_auditoria"] = tela.ir("/admin/auditoria")

    # a entrada desta sessão já é um ato de negócio: a tabela abre com pelo menos essa linha
    page.wait_for_function("() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1",
                           timeout=15000)
    textos = page.locator("#tabela tbody td").all_text_contents()
    assert any("usuarios/entrar" in c for c in textos), textos[:20]

    # o menu lateral leva à tela (a tela existe para quem tem org.log_ver)
    assert page.locator("#lateral a[href='/admin/auditoria']").count() == 1

    # retenção: cartão visível para quem administra, com o nome do job de expurgo no rodapé
    page.wait_for_selector("#retencao:not([hidden])", timeout=15000)
    assert page.input_value("#retencao-dias") == "730"
    rodape = page.locator("#rodape").inner_text()
    assert "730" in rodape and "_auditoria_expurgo" in rodape, rodape

    # FILTRO POR PERÍODO: 24 h
    page.locator("#filtros select[name='periodo']").select_option("1")
    with page.expect_response(lambda r: "/api/auditoria?" in r.url and "formato" not in r.url):
        page.click("#filtrar")
    page.wait_for_function("() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1",
                           timeout=15000)

    # FILTRO POR USUÁRIO: o próprio admin da sessão
    seletor_usuario = page.locator("#filtros select[name='ator_id']")
    assert seletor_usuario.count() == 1, "a tela precisa do filtro por usuário"
    opcao = seletor_usuario.locator(f"option:text-is('{admin_login}')")
    assert opcao.count() == 1, f"o filtro por usuário não tem {admin_login}"
    valor_admin = opcao.get_attribute("value")
    seletor_usuario.select_option(valor_admin)
    with page.expect_response(lambda r: "/api/auditoria?" in r.url and f"ator_id={valor_admin}" in r.url):
        page.click("#filtrar")
    page.wait_for_function(
        "(login) => { const l = [...document.querySelectorAll('#tabela tbody tr')];"
        " return l.length >= 1 && l.every(tr => tr.innerText.includes(login)); }",
        arg=admin_login, timeout=15000)

    # um usuário que não é o da sessão: a tabela esvazia (a trilha é por ator, não um filtro decorativo)
    outros = [o for o in seletor_usuario.locator("option").all()
              if (o.get_attribute("value") or "") not in ("", valor_admin)]
    if outros:
        seletor_usuario.select_option(outros[0].get_attribute("value"))
        with page.expect_response(lambda r: "/api/auditoria?" in r.url and "ator_id=" in r.url):
            page.click("#filtrar")
        page.wait_for_timeout(500)
        linhas = page.locator("#tabela tbody tr").count()
        assert linhas == 0 or admin_login not in page.locator("#tabela tbody").inner_text()
        seletor_usuario.select_option(valor_admin)
        with page.expect_response(lambda r: "/api/auditoria?" in r.url):
            page.click("#filtrar")
        page.wait_for_function("() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1",
                               timeout=15000)

    tela.capturar("auditoria")

    # exportação: os dois links carregam os filtros e a resposta é o arquivo, não a página
    href_csv = page.get_attribute("#exportar-csv", "href")
    assert href_csv.startswith("/api/auditoria?") and "formato=csv" in href_csv, href_csv
    assert f"ator_id={valor_admin}" in href_csv, href_csv
    csv = tela.api("GET", href_csv)
    assert csv.status == 200 and csv.headers.get("content-type", "").startswith("text/csv"), csv.headers
    assert csv.text().splitlines()[0].startswith("id,em,ator_id,ator_login"), csv.text()[:120]
    assert int(csv.headers["x-plat-linhas"]) >= 1

    href_json = page.get_attribute("#exportar-json", "href")
    assert "formato=json_export" in href_json, href_json
    jse = tela.api("GET", href_json)
    assert jse.status == 200 and jse.json()["total"] == len(jse.json()["itens"])

    # a tela NÃO oferece apagar linha (append-only tem de aparecer na interface, não só no banco).
    # #tabela é excluída do texto: ela mostra DADO da trilha, e um ato de negócio legítimo se chama
    # "usuarios/apagar" — string igual à palavra proibida, mas é conteúdo auditado, não um botão de apagar.
    fora_da_tabela = page.evaluate(
        "() => { const c = document.querySelector('#principal').cloneNode(true);"
        " const t = c.querySelector('#tabela'); if (t) t.remove(); return c.innerText; }"
    ).lower()
    assert "apagar" not in fora_da_tabela and "excluir" not in fora_da_tabela, fora_da_tabela[:400]

    tela.verificar()
    gravar_medidas_auditoria(medida, tela)
