"""e2e do item L2-05-a: a tela /analise gera o formulário do manifesto do buffer, roda a ferramenta sobre uma camada
pequena do inquilino (custo abaixo do teto: em processo) e a ficha do item de resultado mostra a proveniência
(ferramenta, versão, parâmetros, entrada com sha256) — com captura. Sem worker: o caminho síncrono basta aqui."""

import re
from pathlib import Path

import pytest

from tests.api.ferramentas import apoio
from tests.e2e.apoio import Tela

ITEM = "L2-05-a-catalogo-ferramentas-gpserver"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def camada(env, admin_api):
    """camada de pontos do inquilino demo, criada pelo mesmo apoio dos testes de API (a sessão é o contexto de
    API do playwright)."""

    class _Sessao:
        def post(self, caminho, json):
            r = admin_api.post(caminho, data=json)
            return type("R", (), {"status_code": r.status, "text": r.text(), "json": r.json})()

    c = apoio.criar_camada(env, _Sessao(), "demo")
    criados = [c["id"]]
    yield c, criados
    apoio.apagar_itens(env, "demo", criados)


def test_formulario_roda_buffer_e_ficha_mostra_proveniencia(page, base_url, credenciais_demo, camada):
    slug, login, senha = credenciais_demo
    c, criados = camada
    tela = Tela(page, base_url)
    # fora do nginx (servidor local http://127.0.0.1:<porta>), o Origin do navegador nunca casa com PLAT_URL_PUBLICA
    # (obrigatoriamente https): o cabeçalho é retirado só desta chamada; a checagem em si é provada em tests/api.
    # (o Chromium não deixa `continue_` tirar o Origin: o pedido é refeito pelo contexto do playwright, sem ele)
    page.route("**/api/ferramentas/*/executar", lambda rota: rota.fulfill(response=rota.fetch(
        headers={k: v for k, v in rota.request.headers.items() if k.lower() != "origin"})))
    tela.entrar(slug, login, senha, proximo="/analise")
    tela.ir("/analise", "pagina_analise_ms")
    assert page.locator("#ferramenta option[value='buffer']").count() == 1
    page.select_option("#formulario select[name='camada']", c["id"])
    page.fill("#formulario input[name='distancia']", "75")
    page.select_option("#formulario select[name='distancia__unidade']", "esriMeters")
    page.fill("#formulario input[name='titulo']", "E2E buffer 75 m")
    page.click("#formulario button[type='submit']")
    page.wait_for_selector("#resultado-link", timeout=30000)
    item_id = page.get_attribute("#execucao-resultado", "data-item-id")
    assert re.fullmatch(r"[0-9a-f-]{36}", item_id), item_id
    criados.append(item_id)
    assert "em processo" in page.text_content("#execucao-resultado")
    page.click("#resultado-link")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("[data-campo='proveniencia'] .proveniencia", timeout=20000)
    texto = page.text_content("[data-campo='proveniencia']")
    assert "buffer v1" in texto and "75" in texto and c["id"] in texto and "sha256" in texto
    assert page.locator(f"[data-campo='proveniencia'] a[href='/conteudo/{c['id']}']").count() == 1
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.locator("[data-campo='proveniencia']").scroll_into_view_if_needed()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_proveniencia.png"))
    tela.verificar()
