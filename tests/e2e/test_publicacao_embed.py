"""e2e do item L5-14-publicacao-links-embed: (3) `<iframe>` num domínio externo só carrega quando esse
domínio está na lista do app (`Content-Security-Policy: frame-ancestors`, aplicada pelo NAVEGADOR — não é
suficiente checar o cabeçalho, tem que ver o navegador obedecer); (4) a exportação estática abre por
`file://` com o mesmo conteúdo, sem nenhuma chamada de rede. Cria os próprios dados pela API (`admin_api`)
e não depende de sessão para ver `/p/...` (a página é anônima por link)."""

import http.server
import socketserver
import tempfile
import threading
from pathlib import Path

import pytest

from tests.e2e.apoio import sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _montar_app(admin_api):
    from app.catalogo.documento import gerar_ulid

    s = sufixo()
    dados_camada = {
        "schema": "plat_trabalho", "tabela": f"zt_{s}", "geometria": "Point", "srid": 4326,
        "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada",
    }
    camada = admin_api.post(
        "/api/itens", data={"tipo": "camada_vetorial", "titulo": f"E2E camada {s}", "dados": dados_camada}
    ).json()
    dados_mapa = {"esquema_versao": 1, "corpo": {"camadas": [camada["id"]]}}
    mapa = admin_api.post("/api/itens", data={"tipo": "mapa", "titulo": f"E2E mapa {s}", "dados": dados_mapa}).json()
    no_id = gerar_ulid()
    corpo_app = {"nos": [{"id": no_id, "tipo": "visor_mapa"}], "mapas": [mapa["id"]]}
    dados_app = {"tipo": "app", "esquema_versao": 2, "corpo": corpo_app}
    app = admin_api.post(
        "/api/itens", data={"tipo": "app", "titulo": f"E2E aplicativo publicado {s}", "dados": dados_app}
    ).json()
    return camada, mapa, app


@pytest.fixture
def _servidor_estatico():
    """Serve um diretório temporário num socket 127.0.0.1:<porta livre> — a origem "externa" do teste de
    iframe. Porta 0 = o SO escolhe uma livre (evita colisão com outra trilha, regra do brief 06/09)."""
    diretorio = tempfile.mkdtemp(prefix="zt_publicacao_embed_")

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=diretorio, **kw)

        def log_message(self, *a):  # silencioso: não polui a saída do pytest
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    porta = httpd.server_address[1]
    fio = threading.Thread(target=httpd.serve_forever, daemon=True)
    fio.start()
    yield diretorio, porta
    httpd.shutdown()
    httpd.server_close()


def test_iframe_so_carrega_no_dominio_permitido(page, admin_api, base_url, _servidor_estatico):
    diretorio, porta = _servidor_estatico
    origem_externa = f"http://127.0.0.1:{porta}"
    _, _, app = _montar_app(admin_api)
    s = sufixo()
    slug = f"e2e-embed-{s}"
    r_pub = admin_api.post(
        f"/api/itens/{app['id']}/publicacao", data={"slug": slug, "dominios_permitidos": [origem_externa]}
    )
    assert r_pub.status == 201, r_pub.text()
    tok = admin_api.post(f"/api/itens/{app['id']}/links", data={}).json()["token"]
    url_publicada = f"{base_url}/p/demo/{slug}?link={tok}"

    Path(diretorio, "permitido.html").write_text(
        f'<!doctype html><html><body><iframe id="alvo" src="{url_publicada}"></iframe></body></html>',
        encoding="utf-8",
    )
    Path(diretorio, "negado.html").write_text(
        f'<!doctype html><html><body><iframe id="alvo" src="{url_publicada}"></iframe></body></html>',
        encoding="utf-8",
    )

    # domínio NA lista: o iframe carrega o documento publicado de verdade
    page.goto(f"{origem_externa}/permitido.html")
    frame = page.frame_locator("#alvo")
    frame.locator("h1").wait_for(timeout=8000)
    assert app["titulo"] in (frame.locator("h1").inner_text() or "")

    # muda o app para NÃO permitir mais esta origem (revoga o domínio, não o link) e testa de novo
    admin_api.post(f"/api/itens/{app['id']}/publicacao", data={"slug": slug, "dominios_permitidos": ["https://outro-dominio.exemplo.org"]})
    page2 = page.context.new_page()
    page2.goto(f"{origem_externa}/negado.html")
    bloqueado = False
    try:
        page2.frame_locator("#alvo").locator("h1").wait_for(timeout=4000)
    except Exception:
        bloqueado = True
    if not bloqueado:
        # o navegador não içou exceção de navegação, mas o corpo não pode ter carregado: confere vazio
        conteudo = page2.frame_locator("#alvo").locator("body").inner_text()
        bloqueado = app["titulo"] not in conteudo
    assert bloqueado, "o iframe carregou o app publicado de uma origem FORA da lista de domínios permitidos"
    page2.close()

    admin_api.delete(f"/api/itens/{app['id']}/publicacao")


def test_exportacao_estatica_abre_por_file(page, admin_api, tmp_path):
    _, _, app = _montar_app(admin_api)
    s = sufixo()
    slug = f"e2e-export-{s}"
    r_pub = admin_api.post(f"/api/itens/{app['id']}/publicacao", data={"slug": slug})
    assert r_pub.status == 201, r_pub.text()
    r_exp = admin_api.get(f"/api/itens/{app['id']}/publicacao/exportacao")
    assert r_exp.status == 200, r_exp.text()
    caminho = tmp_path / f"publicacao-{slug}.html"
    caminho.write_bytes(r_exp.body())

    falhas = []
    page.on("requestfailed", lambda req: falhas.append(req.url))
    pedidos = []
    page.on("request", lambda req: pedidos.append(req.url))
    page.goto(caminho.as_uri())
    assert app["titulo"] in page.locator("h1").inner_text()
    assert "nós do documento (1)" in page.content()
    dados = page.evaluate("() => JSON.parse(document.getElementById('dados-publicados').textContent).titulo")
    assert dados == app["titulo"]
    # abriu por file://: nenhum pedido de rede (nem para o próprio host da API)
    externos = [u for u in pedidos if not u.startswith("file://")]
    assert not externos, f"a exportação chamou rede: {externos}"

    admin_api.delete(f"/api/itens/{app['id']}/publicacao")
