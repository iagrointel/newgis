"""e2e do item L2-05-c: a tela /analise gera o formulário de `resumir_dentro` a partir do manifesto, roda a
ferramenta sobre duas camadas pequenas do inquilino (custo abaixo do teto: em processo) e a ficha do item de
resultado mostra a proveniência com as DUAS entradas e o método que declara a contagem — com captura.
Sem worker: o caminho síncrono basta aqui.

Onde este teste roda: contra a URL servida pelo nginx (`make e2e --base-url $(URL_PUBLICA)`). Contra um
`uvicorn` solto da trilha ele NÃO roda, e não é defeito deste item: o servidor da aplicação não serve
`/static/*` (é o nginx que serve), então o JS da tela de login nunca carrega e `body[data-pronto="1"]` nunca
aparece. Medido em 07/09 na trilha il205csobre: este teste e o `tests/e2e/test_ferramentas.py` do item
L2-05-a falham na MESMA linha (`Tela.entrar`) com o mesmo estouro de relógio, e o registro do servidor mostra
404 em `/static/estilo/tokens.css`, `/static/style.css` e `/static/js/auth/login.js`."""

import re
from pathlib import Path

import pytest

from tests.api.ferramentas import apoio_vetor as av
from tests.e2e.apoio import Tela

ITEM = "L2-05-c-sobreposicao-agregacao"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ZONAS = [
    {"nome": "Z1", "valor": 1, "wkt": "POLYGON((-46.6 -23.5,-46.5 -23.5,-46.5 -23.4,-46.6 -23.4,-46.6 -23.5))"},
    {"nome": "Z2", "valor": 2, "wkt": "POLYGON((-46.5 -23.5,-46.4 -23.5,-46.4 -23.4,-46.5 -23.4,-46.5 -23.5))"},
]
PONTOS = [{"nome": "P1", "valor": 10, "wkt": "POINT(-46.55 -23.45)"},
          {"nome": "P2", "valor": 20, "wkt": "POINT(-46.45 -23.45)"}]


@pytest.fixture
def camadas(env, admin_api):
    class _Sessao:
        def post(self, caminho, json):
            r = admin_api.post(caminho, data=json)
            return type("R", (), {"status_code": r.status, "text": r.text(), "json": r.json})()

    sessao = _Sessao()
    zonas = av.criar_camada_wkt(env, sessao, ZONAS, "Polygon", rotulo="zonas e2e")
    pontos = av.criar_camada_wkt(env, sessao, PONTOS, "Point", rotulo="pontos e2e")
    criados = [zonas["id"], pontos["id"]]
    yield zonas, pontos, criados
    from tests.api.ferramentas import apoio

    apoio.apagar_itens(env, "demo", criados)


def test_formulario_roda_resumir_dentro_e_ficha_mostra_as_duas_entradas(page, base_url, credenciais_demo,
                                                                       camadas):
    slug, login, senha = credenciais_demo
    zonas, pontos, criados = camadas
    tela = Tela(page, base_url)
    # mesma ressalva do e2e do L2-05-a: fora do nginx o Origin do navegador nunca casa com PLAT_URL_PUBLICA
    page.route("**/api/ferramentas/*/executar", lambda rota: rota.fulfill(response=rota.fetch(
        headers={k: v for k, v in rota.request.headers.items() if k.lower() != "origin"})))
    tela.entrar(slug, login, senha, proximo="/analise")
    tela.ir("/analise", "pagina_analise_relacao_ms")
    assert page.locator("#ferramenta option[value='resumir_dentro']").count() == 1
    page.select_option("#ferramenta", "resumir_dentro")
    page.select_option("#formulario select[name='camada_poligonos']", zonas["id"])
    page.select_option("#formulario select[name='camada_resumir']", pontos["id"])
    page.fill("#formulario input[name='titulo']", "E2E resumir dentro")
    page.click("#formulario button[type='submit']")
    page.wait_for_selector("#resultado-link", timeout=30000)
    item_id = page.get_attribute("#execucao-resultado", "data-item-id")
    assert re.fullmatch(r"[0-9a-f-]{36}", item_id), item_id
    criados.append(item_id)
    page.click("#resultado-link")
    page.wait_for_selector("body[data-pronto='1']", timeout=60000)  # carga da máquina em 10 (07/09)
    page.wait_for_selector("[data-campo='proveniencia'] .proveniencia", timeout=20000)
    texto = page.text_content("[data-campo='proveniencia']")
    assert "resumir_dentro v1" in texto, texto
    for c in (zonas, pontos):
        assert c["id"] in texto, c["id"]
        assert page.locator(f"[data-campo='proveniencia'] a[href='/conteudo/{c['id']}']").count() == 1
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.locator("[data-campo='proveniencia']").scroll_into_view_if_needed()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_proveniencia.png"))
    tela.verificar()
