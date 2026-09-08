"""e2e da seleção bidirecional entre diagrama e mapa (cláusula do portão do item
L4-04-d-diagrama-esquematico).

A tela `/redes/diagrama` mostra o mesmo alimentador duas vezes: à esquerda o ESQUEMA (o grafo no espaço do
diagrama) e à direita o MAPA (os mesmos nós na coordenada de verdade). Este teste faz o caminho inteiro no
navegador e prova a cláusula nos DOIS sentidos:

  1. abre a tela, escolhe a rede e o diagrama; os nós aparecem nos dois quadros;
  2. clica num nó do ESQUEMA — o nó correspondente do MAPA fica selecionado, e a ficha mostra a feição de
     origem (é a ida: selecionar no diagrama seleciona no mapa);
  3. clica em OUTRO nó, agora pelo MAPA — o nó correspondente do ESQUEMA fica selecionado (é a volta);
  4. troca o desenho no seletor — o número de nós e de ligações não muda (layout só reposiciona);
  5. segue o link de exportação e confere que o SVG sai com uma figura de verdade.

Roda contra um servidor próprio da trilha (porta conferida livre com `ss -ltn` antes de escolher), com
`web/` em /static — os e2e do repositório correm contra a URL interna servida por nginx, que roda o código
de `master`, não o do ramo."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-04-d-diagrama-esquematico"
PORTA = 8443  # porta desta trilha; conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"
CTMT = "1_E2D_1"
LON0, LAT0, D = 41.0, 21.0, 0.001
TRECHOS = 6


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


def _rede_com_diagrama(tela) -> tuple[str, str]:
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l404d-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    atributos = {"ctmt": CTMT, "sub": "E2D"}
    assert tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", {
        "grupo": "chave_de_media_tensao", "tipo_codigo": 4, "lon": LON0, "lat": LAT0,
        "atributos": {**atributos, "unsemt_fas_con": "ABC"}}).status == 201
    for i in range(TRECHOS):
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", {
            "grupo": "trecho_de_media_tensao", "tipo_codigo": 1,
            "coordenadas": [[LON0 + i * D, LAT0], [LON0 + (i + 1) * D, LAT0]],
            "atributos": {**atributos, "cod_id": f"MT{i}-{CTMT}"}}).status == 201
    assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar").status == 201
    r = tela.api("POST", f"/api/rede/{rid}/controladores/importar")
    assert r.status == 200, r.text()
    r = tela.api("GET", f"/api/rede/{rid}/subredes?limite=500")
    alvo = {s["nome"]: s for s in r.json()["itens"]}[CTMT]
    assert tela.api("POST", f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status == 200

    r = tela.api("POST", f"/api/rede/{rid}/diagrama", {
        "nome": "alimentador do e2e",
        "origem": {"tipo": "subrede", "subrede": CTMT, "tier": "media_tensao"}})
    assert r.status == 201, r.text()
    return rid, r.json()["id"]


def test_selecao_casa_entre_o_diagrama_e_o_mapa(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/diagrama")
    rid, did = _rede_com_diagrama(tela)
    try:
        doc = tela.api("GET", f"/api/rede/{rid}/diagrama/{did}").json()
        # dois nós COM coordenada (os dois quadros mostram o mesmo nó) e distintos entre si
        com_mapa = [n["chave"] for n in doc["nos"] if n["lon"] is not None]
        assert len(com_mapa) >= 2, doc["nos"]
        primeiro, segundo = com_mapa[0], com_mapa[1]

        tela.ir("/redes/diagrama", "abrir_diagrama_ms")
        page.select_option("#rede", rid)
        page.wait_for_function("document.querySelectorAll('#diagrama-escolhido option').length > 1",
                               timeout=30000)
        page.select_option("#diagrama-escolhido", did)
        page.wait_for_selector(".no-esquema", timeout=30000)
        assert page.locator(".no-esquema").count() == len(doc["nos"])
        assert page.locator(".no-mapa").count() == len(com_mapa)
        assert "consistente" in (page.text_content("#estado-diagrama") or "")

        # ida: clicar no ESQUEMA acende o mapa
        page.click(f'.no-esquema[data-chave="{primeiro}"]')
        page.wait_for_selector("#ficha:not([hidden])", timeout=30000)
        assert page.locator(f'.no-mapa[data-chave="{primeiro}"].selecionado').count() == 1
        assert page.locator(".marcador-no.selecionado").count() == 2, "o mesmo nó, nos dois quadros"
        assert (page.text_content("#no-rotulo") or "").strip()

        # volta: clicar no MAPA acende o esquema
        page.click(f'.no-mapa[data-chave="{segundo}"]')
        page.wait_for_selector(f'.no-esquema[data-chave="{segundo}"].selecionado', timeout=30000)
        assert page.locator(f'.no-esquema[data-chave="{primeiro}"].selecionado').count() == 0
        assert page.locator(".marcador-no.selecionado").count() == 2

        # trocar o desenho não muda o grafo
        page.select_option("#layout", "radial")
        page.wait_for_function(
            "document.querySelector('#aviso') && !document.querySelector('#aviso').hidden", timeout=30000)
        page.wait_for_selector(".no-esquema", timeout=30000)
        assert page.locator(".no-esquema").count() == len(doc["nos"])
        contagem = page.text_content("#contagem-diagrama") or ""
        assert str(len(doc["nos"])) in contagem and str(len(doc["arestas"])) in contagem

        link = page.get_attribute("#exportar-svg", "href")
        assert link.endswith("?formato=svg"), link
        svg = tela.api("GET", link)
        assert svg.status == 200 and svg.text().startswith("<svg "), svg.text()[:200]

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_diagrama_ms", tela.medidas["abrir_diagrama_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
