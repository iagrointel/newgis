"""e2e /admin/atividade (item L0-07-e-relatorios): o admin de demo abre o painel, vê os totais, os gráficos SVG
(eventos por dia, acessos por dia, eventos por tipo) e a tabela dos 10 itens mais acessados (o item aberto pela
API nesta sessão aparece), pede um relatório pela tela (entra na fila: linha "na fila"/"gerando"/"pronto") e
cria e apaga uma agenda semanal. Captura L0-07-e-relatorios_atividade.png."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo, texto_aviso

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-07-e-relatorios"


def test_painel_atividade_relatorio_e_agenda(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    titulo = f"mapa atividade {sufixo()}"
    corpo = {"tipo": "mapa", "titulo": titulo, "dados": {"esquema_versao": 1, "corpo": {}}}
    r = admin_api.post("/api/itens", data=corpo)
    assert r.status == 201, r.text()
    item_id = r.json()["id"]
    agenda_id = None
    tela = Tela(page, base_url)
    try:
        for _ in range(3):
            assert admin_api.get(f"/api/itens/{item_id}").status == 200  # acessos contados no painel
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/atividade")
        tela.medidas["pagina_pronta_ms_atividade"] = tela.ir("/admin/atividade")
        page.wait_for_function("() => document.querySelectorAll('#kpis .kpi').length === 4", timeout=15000)
        page.wait_for_function("() => document.querySelectorAll('#grafico-dias rect.barra').length >= 1", timeout=15000)
        assert page.locator("#grafico-acessos rect.barra").count() >= 1
        assert page.locator("#grafico-tipos rect.barra").count() >= 1
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#tabela-top tbody td')].some(td => td.textContent === '{titulo}')",
            timeout=15000,
        )
        assert "limites declarados" in page.text_content("#relatorios-limites")
        # pedir um relatório pela tela: entra na lista (na fila / gerando / pronto, conforme o worker)
        page.select_option("#relatorio-tipo", "grupos")
        tela.esperar_status(429)  # 1 por tipo por hora: numa rodada repetida o pedido é recusado com a mensagem
        page.click("#relatorio-gerar")
        page.wait_for_selector("#aviso:not([hidden])", timeout=15000)
        aviso = texto_aviso(page)
        if "por hora" not in aviso:
            assert "na fila" in aviso, aviso
            page.wait_for_function("() => document.querySelectorAll('#tabela-relatorios tbody tr').length >= 1",
                                   timeout=15000)
        # agenda semanal criada e apagada pela tela
        page.select_option("#agenda-tipo", "atividade")
        page.select_option("#agenda-periodicidade", "semanal")
        page.fill("#agenda-hora", "8")
        page.click("#agenda-criar")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#tabela-agendas tbody td')]"
            ".some(td => td.textContent === '0 8 * * 1')",
            timeout=15000,
        )
        agendas = tela.api("GET", "/api/relatorios/agendas").json()["itens"]
        agenda_id = next(a["id"] for a in agendas
                         if a["cron"] == "0 8 * * 1" and a["parametros"]["tipo"] == "atividade")
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_atividade.png"), full_page=True)
        linha = page.locator("#tabela-agendas tbody tr", has_text="0 8 * * 1")
        linha.locator("button", has_text="Apagar").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").click()
        page.wait_for_function("() => document.querySelector('#aviso')?.textContent.includes('apagada')", timeout=15000)
        agenda_id = None
        tela.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (apoio.py Tela.ir)")
    finally:
        if agenda_id:
            admin_api.delete(f"/api/agendas/{agenda_id}")
        admin_api.delete(f"/api/itens/{item_id}")
