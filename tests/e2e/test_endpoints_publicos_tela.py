"""e2e playwright do catálogo de conectores públicos na tela /conexoes (item L6-02-m-catalogo-endpoints-brasil).
Cláusula do portão: "10 adicionados pela tela em e2e". Prova: a seção "conectores públicos prontos" lista só
entradas vivas (o `data-tipo` e a contagem batem com a API); clicar "adicionar" em 10 linhas cria 10 conexões
que aparecem na lista de conexões do inquilino sem recarregar a página à mão, cada uma com `config.procedencia`
vindo do catálogo; a seção "fora do ar" mostra as entradas mortas com o motivo. Pré-requisito: o catálogo já
semeado e testado nesta instalação (job `endpoints_publicos.retestar`); sem 10 vivos a suíte é pulada com a
razão escrita. 0 erro de console; capturas em tests/e2e/capturas/L6-02-m_*.png."""

from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L6-02-m-catalogo-endpoints-brasil"
QUANTOS = 10


class TelaCatalogo(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"L6-02-m_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_catalogo(rotas_api):
    faltam = [r for r in ("/api/conexoes", "/api/endpoints-publicos") if r not in rotas_api]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L6-02-m)")
    return rotas_api


def test_dez_conectores_adicionados_pela_tela(page, base_url, credenciais_demo, api_catalogo, medida):
    slug, admin_login, senha_admin = credenciais_demo
    tela = TelaCatalogo(page, base_url)
    criadas: list[str] = []
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/conexoes")
        vivos = tela.api("GET", "/api/endpoints-publicos?limite=500").json()
        if vivos["total"] < QUANTOS:
            pytest.skip(f"catálogo com {vivos['total']} vivos nesta instalação; rode o job endpoints_publicos.retestar")
        # começa sem conexão de catálogo para as 10 primeiras entradas (idempotência apagaria a prova de criação)
        alvos = vivos["itens"][:QUANTOS]
        existentes = tela.api("GET", "/api/conexoes").json()["itens"]
        for c in existentes:
            if any(c["tipo"] == a["tipo"] and c["url"] == a["url"] for a in alvos):
                assert tela.api("DELETE", f"/api/conexoes/{c['id']}").status == 204

        tela.medidas["pagina_conexoes_ms"] = tela.ir("/conexoes")
        page.wait_for_function(
            "() => document.querySelectorAll('#catalogo-corpo tr[data-endpoint]').length > 0", timeout=20000
        )
        assert page.locator("#catalogo-corpo tr[data-endpoint]").count() == vivos["total"]
        assert page.text_content("#catalogo-total").strip() == f"({vivos['total']})"
        fora = tela.api("GET", "/api/endpoints-publicos?limite=500&vivo=false").json()
        assert page.locator("#catalogo-fora-corpo tr[data-endpoint]").count() == fora["total"]
        if fora["total"]:
            page.click("#catalogo-fora summary")
            assert page.locator("#catalogo-fora-corpo .marcador.falha").first.inner_text().strip()
        tela.capturar("catalogo")

        antes = tela.api("GET", "/api/conexoes").json()["total"]
        for i, alvo in enumerate(alvos):
            linha = page.locator(f"#catalogo-corpo tr[data-endpoint='{alvo['id']}']")
            assert linha.get_attribute("data-tipo") == alvo["tipo"]
            linha.get_by_role("button", name="adicionar").click()
            page.wait_for_function(
                "(id) => document.querySelector(`#catalogo-corpo tr[data-endpoint='${id}'] button`)"
                "?.dataset?.resultado === 'criada'",
                arg=alvo["id"], timeout=20000,
            )
            page.wait_for_function(
                "(n) => document.querySelectorAll('#lista-corpo tr[data-id]').length >= n",
                arg=antes + i + 1, timeout=20000,
            )
        tela.capturar("dez_adicionados")

        depois = tela.api("GET", "/api/conexoes").json()
        assert depois["total"] == antes + QUANTOS
        novas = [c for c in depois["itens"] if any(c["tipo"] == a["tipo"] and c["url"] == a["url"] for a in alvos)]
        assert len(novas) == QUANTOS
        for c in novas:
            criadas.append(c["id"])
            ficha = tela.api("GET", f"/api/conexoes/{c['id']}").json()["config"]["procedencia"]
            assert ficha["fonte"] and ficha["comando_reexecucao"].startswith("GET ")
            assert "testado por HTTP" in ficha["metodo"]
            assert page.locator(f"#lista-corpo tr[data-id='{c['id']}']").count() == 1
        tela.medidas["conectores_adicionados_pela_tela"] = QUANTOS
        tela.verificar()
    finally:
        for cid in criadas:
            tela.api("DELETE", f"/api/conexoes/{cid}")
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms" if nome.endswith("_ms") else "conexões",
               "playwright chromium contra a URL da trilha (tests/e2e/test_endpoints_publicos_tela.py)")
