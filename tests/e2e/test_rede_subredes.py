"""e2e do botão de atualização de subrede (cláusula do portão do item L4-04-b-atualizar-e-exportar-subrede).

A tela `/redes/controladores` ganhou neste item três coisas: a coluna do comprimento da linha agregada da
subrede, o link de exportação por subrede e o botão que enfileira a atualização em LOTE das subredes sujas.
Este teste faz o caminho inteiro no navegador:

  1. abre a tela e escolhe a rede;
  2. clica no controlador, abre a ficha e usa o botão `atualizar` — a linha da tabela passa de `suja` para
     `limpa` e o comprimento deixa de ser vazio (é a prova de que a SubnetLine foi gerada);
  3. clica em `atualizar subredes sujas` — a resposta é um job enfileirado, e o aviso traz o identificador;
  4. segue o link de exportação e confere que o JSON tem os elementos da subrede.

Roda contra um servidor próprio da trilha (porta do item), com `web/` em /static — os e2e do repositório
correm contra a URL interna servida por nginx, que roda o código de `master`, não o do ramo."""

import json
import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-04-b-atualizar-e-exportar-subrede"
PORTA = 8338  # porta desta trilha (o prompt do item)
URL_TESTE = f"http://127.0.0.1:{PORTA}"
CTMT = "1_E2B_1"
LON0, LAT0, D = 35.0, 16.0, 0.001


@pytest.fixture(scope="session")
def base_url():
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


def _rede(tela) -> str:
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l404b-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    a, b, c = (LON0, LAT0), (LON0 + D, LAT0), (LON0 + 2 * D, LAT0)
    at = {"ctmt": CTMT, "sub": "E2B"}
    for corpo in (
        {"grupo": "chave_de_media_tensao", "tipo_codigo": 4, "lon": a[0], "lat": a[1], "atributos": at},
        {"grupo": "transformador_de_distribuicao", "tipo_codigo": 1, "lon": c[0], "lat": c[1],
         "atributos": {"cod_id": "TR-E2B"}},
    ):
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", corpo).status == 201
    for corpo in (
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(a), list(b)],
         "atributos": at},
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(b), list(c)],
         "atributos": at},
        {"grupo": "trecho_de_baixa_tensao", "tipo_codigo": 1,
         "coordenadas": [list(c), [c[0], c[1] + D]], "atributos": {"cod_id": "BT-E2B"}},
    ):
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", corpo).status == 201
    assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar").status == 201
    r = tela.api("POST", f"/api/rede/{rid}/controladores/importar")
    assert r.status == 200, r.text()
    assert r.json()["alimentadores_por_dispositivo"] == 1, r.text()
    return rid


def test_botao_atualizar_e_exportacao_na_tela(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/controladores")
    rid = _rede(tela)
    try:
        tela.ir("/redes/controladores", "abrir_subredes_ms")
        page.select_option("#rede", rid)
        page.wait_for_selector("#subredes table", timeout=30000)
        assert page.locator("#subredes td.estado-suja").count() == 2

        page.click(f"#subredes button.controlador:has-text('{CTMT}')")
        page.wait_for_selector("#ficha:not([hidden])", timeout=30000)
        page.click("#atualizar-subrede")
        page.wait_for_selector("#subredes td.estado-limpa", timeout=30000)
        assert page.locator("#subredes td.estado-limpa").count() == 1
        comprimento = page.locator("#subredes tbody tr td.comprimento").first.text_content().strip()
        assert float(comprimento) > 0, "a linha agregada da subrede tem comprimento medido"

        page.click("#atualizar-sujas")
        page.wait_for_function(
            "document.querySelector('#aviso').textContent.toLowerCase().includes('job')", timeout=30000)
        aviso = page.text_content("#aviso").strip()
        assert "job" in aviso.lower(), aviso

        link = page.get_attribute(f"#subredes a.exportar[data-subrede-nome='{CTMT}']", "href")
        assert link.endswith(f"/subrede/{CTMT}/exportar?tier=media_tensao"), link
        exportado = tela.api("GET", link)
        assert exportado.status == 200, exportado.text()
        doc = json.loads(exportado.text())
        assert doc["subrede"]["nome"] == CTMT and doc["elementos"], doc["subrede"]

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_subredes_ms", tela.medidas["abrir_subredes_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
