"""Item L7-03-e, no navegador de verdade: com a CSP ligada as páginas carregam sem violação de política, e
embutir em iframe só funciona a partir de origem que o inquilino autorizou.

Este módulo NÃO usa a URL pública (os demais e2e usam): ele sobe a aplicação DESTA árvore num servidor
próprio, porque o que se prova nasce em app/cabecalhos.py e a instalação pública só passa a ter isso quando
o dono instalar o deploy/ deste item. O `/static/` é servido pelo mesmo processo (em produção é o nginx),
o que não muda o que se mede aqui: o que decide é a CSP do DOCUMENTO.
"""

import contextlib
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import uvicorn

PORTA_APP = 8321
PORTA_SITIO = 8322  # o "sítio do cliente" que embute o mapa
BASE_APP = f"http://127.0.0.1:{PORTA_APP}"
ORIGEM_SITIO = f"http://127.0.0.1:{PORTA_SITIO}"
PAGINA_DO_SITIO = (
    "<!doctype html><meta charset='utf-8'><title>sitio</title>"
    f"<iframe id='embutido' src='{BASE_APP}/mapa?inquilino=demo' width='800' height='600'></iframe>"
)


def _porta_livre(porta: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


@pytest.fixture(scope="module")
def servidor_app(env):
    """uvicorn da própria árvore, com /static/ montado (em produção quem serve é o nginx)."""
    if not _porta_livre(PORTA_APP):
        pytest.skip(f"porta {PORTA_APP} ocupada nesta máquina")
    from fastapi.staticfiles import StaticFiles

    from app.main import ROOT, app

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    config = uvicorn.Config(app, host="127.0.0.1", port=PORTA_APP, log_level="warning")
    servidor = uvicorn.Server(config)
    linha = threading.Thread(target=servidor.run, daemon=True)
    linha.start()
    for _ in range(100):
        with contextlib.suppress(httpx.HTTPError):
            if httpx.get(f"{BASE_APP}/saude", timeout=2).status_code == 200:
                break
        time.sleep(0.2)
    else:
        servidor.should_exit = True
        pytest.skip("a aplicação da trilha não subiu em 20 s")
    yield BASE_APP
    servidor.should_exit = True
    linha.join(timeout=10)


@pytest.fixture(scope="module")
def servidor_sitio():
    if not _porta_livre(PORTA_SITIO):
        pytest.skip(f"porta {PORTA_SITIO} ocupada nesta máquina")

    class Mao(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — nome exigido pela biblioteca padrão
            corpo = PAGINA_DO_SITIO.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", PORTA_SITIO), Mao)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield ORIGEM_SITIO
    httpd.shutdown()


@pytest.fixture
def origens_de_demo(conexao_plat_app):
    """Grava config.origens_embutidas do inquilino demo e limpa no fim (mesma gravação do PUT /api/org)."""
    from app import cabecalhos
    from tests.api.test_rls import ids_por_slug

    def gravar(origens: list[str]):
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(ids_por_slug(conexao_plat_app)["demo"]),))
            cur.execute(
                "UPDATE plat.tenant SET config = config || jsonb_build_object('origens_embutidas', %s::jsonb) "
                "WHERE id = plat.tenant_atual()",
                (json.dumps(origens),),
            )
        conexao_plat_app.commit()
        cabecalhos.esquecer_origens()

    yield gravar
    gravar([])


def _erros_de_console(page) -> list[str]:
    achados: list[str] = []
    page.on("console", lambda m: achados.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: achados.append(str(e)))
    return achados


@pytest.mark.parametrize("rota", ["/entrar", "/mapa", "/api/docs"])
def test_pagina_sem_violacao_de_csp_no_navegador(page, servidor_app, rota):
    erros = _erros_de_console(page)
    page.goto(servidor_app + rota, wait_until="networkidle")
    violacoes = [e for e in erros if "Content Security Policy" in e or "Refused to" in e]
    assert not violacoes, violacoes


def test_swagger_ui_desenha_com_csp_ligada(page, servidor_app):
    """Se o nonce do script de arranque não casasse, a página abriria em branco — e é isso que se mede."""
    page.goto(servidor_app + "/api/docs", wait_until="networkidle")
    page.wait_for_selector(".swagger-ui .info", timeout=15000)
    assert page.locator(".swagger-ui").count() == 1


def test_embutir_de_origem_autorizada_funciona(page, servidor_app, servidor_sitio, origens_de_demo):
    origens_de_demo([ORIGEM_SITIO])
    erros = _erros_de_console(page)
    page.goto(servidor_sitio, wait_until="networkidle")
    quadro = page.frame_locator("#embutido")
    quadro.locator("body").wait_for(timeout=15000)
    assert quadro.locator("#mapa, body").count() >= 1
    assert not [e for e in erros if "Refused to display" in e or "frame-ancestors" in e], erros


def test_embutir_de_origem_nao_autorizada_e_bloqueado(page, servidor_app, servidor_sitio, origens_de_demo):
    origens_de_demo([])
    erros = _erros_de_console(page)
    page.goto(servidor_sitio, wait_until="networkidle")
    page.wait_for_timeout(1500)
    recusa = [e for e in erros if "Refused to display" in e or "frame-ancestors" in e]
    assert recusa, f"o navegador deveria ter recusado o iframe; console: {erros}"
