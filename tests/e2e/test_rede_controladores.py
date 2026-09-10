"""e2e da FICHA DO CONTROLADOR (cláusula 4 do portão do item L4-04-a-controladores-e-tiers).

A tela `/redes/controladores` mostra a tabela de subredes da rede escolhida (nome, tier, estado limpa/suja,
elementos do último traçado e os controladores) e, ao clicar num controlador, abre a FICHA: dispositivo,
terminal, tier, subrede, papel, origem da marcação e o nó que ele ocupa na topologia corrente. O teste
também usa as duas ações do ciclo de vida na própria tela: atualizar a subrede (ela vira `limpa`) e remover
o controlador (a linha some da tabela).

A rede de teste é criada pela API antes de abrir a tela, no formato da BDGD (um alimentador com o disjuntor
de saída e um transformador de distribuição), e apagada no fim."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-04-a-controladores-e-tiers"
PORTA = 8316  # porta desta trilha (o prompt do item)
URL_TESTE = f"http://127.0.0.1:{PORTA}"
CTMT = "1_E2E_1"
LON0, LAT0, D = 33.0, 12.0, 0.001


@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com `web/` em /static — mesma montagem do e2e da rede simples: os e2e do
    repositório correm contra a URL interna servida por nginx, que roda o código de `master`, não o do ramo."""
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import app as aplicacao
    from app.settings import settings

    object.__setattr__(settings, "PLAT_URL_PUBLICA", URL_TESTE)
    servidor_asgi = Starlette(routes=[
        Mount("/static", StaticFiles(directory=str(RAIZ / "web")), name="estaticos"),
        Mount("/", aplicacao),
    ])
    config = uvicorn.Config(servidor_asgi, host="127.0.0.1", port=PORTA, log_level="warning")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.time() + 30
    while not servidor.started and time.time() < limite:
        time.sleep(0.1)
    if not servidor.started:
        pytest.skip(f"o servidor de teste não subiu na porta {PORTA}")
    yield URL_TESTE
    servidor.should_exit = True
    thread.join(timeout=20)


def _rede_com_controladores(tela) -> str:
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l404a-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    a, b, c = (LON0, LAT0), (LON0 + D, LAT0), (LON0 + 2 * D, LAT0)
    at = {"ctmt": CTMT, "sub": "E2E"}
    for corpo in (
        {"grupo": "chave_de_media_tensao", "tipo_codigo": 4, "lon": a[0], "lat": a[1], "atributos": at},
        {"grupo": "transformador_de_distribuicao", "tipo_codigo": 1, "lon": c[0], "lat": c[1],
         "atributos": {"cod_id": "TR-E2E"}},
    ):
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", corpo).status == 201
    for corpo in (
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(a), list(b)],
         "atributos": at},
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(b), list(c)],
         "atributos": at},
        {"grupo": "trecho_de_baixa_tensao", "tipo_codigo": 1,
         "coordenadas": [list(c), [c[0], c[1] + D]], "atributos": {"cod_id": "BT-E2E"}},
    ):
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", corpo).status == 201
    assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar").status == 201
    r = tela.api("POST", f"/api/rede/{rid}/controladores/importar")
    assert r.status == 200, r.text()
    assert r.json()["alimentadores_por_dispositivo"] == 1, r.text()
    return rid


def test_ficha_do_controlador_na_tela(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/controladores")
    rid = _rede_com_controladores(tela)
    try:
        tela.ir("/redes/controladores", "abrir_controladores_ms")
        assert page.title().startswith("Controladores de subrede")

        page.select_option("#rede", rid)
        page.wait_for_selector("#subredes table", timeout=30000)
        # duas subredes: o alimentador (média tensão) e a de baixa tensão do transformador
        assert page.get_attribute("#subredes", "data-total") == "2"
        assert page.locator("#subredes tbody tr").count() == 2
        assert page.locator("#subredes td.estado-suja").count() == 2

        page.click(f"#subredes button.controlador:has-text('{CTMT}')")
        page.wait_for_selector("#ficha:not([hidden])", timeout=30000)
        assert page.text_content("#f-nome").strip() == CTMT
        assert page.text_content("#f-subrede").strip() == CTMT
        assert "Média tensão" in page.text_content("#f-tier")
        assert "hierarquico" in page.text_content("#f-tier")
        assert page.text_content("#f-tipo").strip() == "Disjuntor"
        assert page.text_content("#f-terminal").strip() == "2"
        assert page.text_content("#f-papel").strip() == "fonte"
        assert page.text_content("#f-origem").strip() == "dispositivo"
        assert len(page.text_content("#f-no").strip()) == 36, "a ficha mostra o nó da topologia corrente"

        page.click("#atualizar-subrede")
        page.wait_for_selector("#subredes td.estado-limpa", timeout=30000)
        assert page.locator("#subredes td.estado-limpa").count() == 1

        page.click(f"#subredes button.controlador:has-text('{CTMT}')")
        page.wait_for_selector("#ficha:not([hidden])", timeout=30000)
        page.click("#remover-controlador")
        page.wait_for_function("document.querySelector('#subredes').dataset.total === '1'", timeout=30000)
        assert page.locator("#subredes tbody tr").count() == 1

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_controladores_ms", tela.medidas["abrir_controladores_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
