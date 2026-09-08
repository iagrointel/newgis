"""e2e da TELA de resultado de traçado (item L4-02-f-resultados-e-exportacao).

A tela `/redes/tracado` traça sobre a rede escolhida e dá ao resultado as quatro saídas do portão: a tabela
com as agregações ao lado (por tipo de ativo e por nível de tensão), o botão SELECIONAR (a seleção marca as
linhas e diz quantas), o botão SALVAR COMO CAMADA (item de catálogo com procedência) e o botão EXPORTAR
(CSV, GeoJSON ou GeoPackage). Embaixo, o histórico dos últimos traçados, cada um com REPETIR.

O teste percorre o caminho inteiro pela tela e confere, ao fim, pela API, que a camada salva pela tela é a
mesma que a API devolve, com a procedência dentro. A rede é criada pela API antes de abrir a tela e apagada
no fim, junto com o item de catálogo que a tela criou."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-02-f-resultados-e-exportacao"
PORTA = 8341  # porta desta trilha; conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"
LON0, LAT0, D = 38.0, 13.0, 0.001


@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com `web/` em /static — mesma montagem do e2e dos itens irmãos: os e2e do
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


def _rede(tela) -> tuple[str, str]:
    """Rede mínima com o pacote elétrica-BR: disjuntor de saída, um trecho de média tensão e um
    transformador. Devolve (id da rede, id do disjuntor)."""
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l402f-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    at = {"ctmt": "1_E2E_1", "sub": "E2E"}
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", {
        "tipo_codigo": 4, "grupo": "chave_de_media_tensao", "lon": LON0 - D, "lat": LAT0,
        "atributos": {**at, "cod_id": "DJ1", "estado": "fechado"}})
    assert r.status == 201, r.text()
    disjuntor = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", {
        "tipo_codigo": 1, "grupo": "trecho_de_media_tensao", "fase_bitmask": 7,
        "coordenadas": [[LON0 - D, LAT0], [LON0, LAT0]],
        "atributos": {**at, "cod_id": "MT0", "comp": 10, "fas_con": "ABC"}})
    assert r.status == 201, r.text()
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", {
        "tipo_codigo": 1, "grupo": "transformador_de_distribuicao", "lon": LON0, "lat": LAT0,
        "atributos": {**at, "cod_id": "TR1", "pot_nom": 75}})
    assert r.status == 201, r.text()
    r = tela.api("POST", f"/api/rede/{rid}/topologia/habilitar", {})
    assert r.status == 201, r.text()
    return rid, disjuntor


def test_resultado_na_tela_vira_selecao_camada_arquivo_e_historico(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/tracado")
    rid, disjuntor = _rede(tela)
    item_id = None
    try:
        tela.ir("/redes/tracado", "abrir_tracado_ms")
        assert page.title().startswith("Resultado de traçado")

        page.select_option("#rede", rid)
        page.select_option("#tipo", "conectado")
        page.fill("#feicao", disjuntor)
        page.fill("#terminal", "2")
        page.click("#tracar")
        page.wait_for_selector("#resultado table tbody tr", timeout=30000)
        total = int(page.get_attribute("#resultado", "data-total"))
        assert total >= 3, total  # o terminal do disjuntor, o trecho e o transformador

        # o painel lateral traz as duas agregações do portão, e a soma de cada uma é o total
        page.wait_for_selector("#por_tipo tr", timeout=30000)
        soma_tipo = sum(int(x) for x in page.locator("#por_tipo td.contagem").all_text_contents())
        soma_nivel = sum(int(x) for x in page.locator("#por_nivel td.contagem").all_text_contents())
        assert soma_tipo == total and soma_nivel == total, (soma_tipo, soma_nivel, total)

        # botão 1: selecionar
        page.click("#selecionar")
        page.wait_for_function(
            "() => document.querySelector('#resultado').dataset.selecionados !== '0'", timeout=30000)
        assert int(page.get_attribute("#resultado", "data-selecionados")) == total
        assert page.locator("#resultado tbody tr[aria-selected='true']").count() == total

        # botão 2: exportar (o arquivo é gerado pelo navegador; a tela grava tamanho e formato)
        page.select_option("#formato", "geojson")
        page.click("#exportar")
        page.wait_for_function(
            "() => document.querySelector('#situacao').dataset.formato === 'geojson'", timeout=30000)
        assert int(page.get_attribute("#situacao", "data-bytes")) > 0

        # botão 3: salvar como camada
        page.fill("#titulo", f"zt-e2e camada {sufixo()}")
        page.click("#camada")
        page.wait_for_function(
            "() => !!document.querySelector('#situacao').dataset.item", timeout=30000)
        item_id = page.get_attribute("#situacao", "data-item")

        # a camada salva pela tela é a que a API devolve, com a procedência dentro
        r = tela.api("GET", f"/api/itens/{item_id}")
        assert r.status == 200, r.text()
        item = r.json()
        assert item["tipo"] == "camada_tracado"
        assert item["dados"]["procedencia"]["rede_id"] == rid
        assert item["dados"]["procedencia"]["pontos_partida"][0]["feicao_id"] == disjuntor
        assert item["dados"]["procedencia"]["topologia_construido_em"]
        assert item["dados"]["contagem"] == total

        # histórico: o traçado da tela está lá e o botão repetir devolve a mesma contagem
        page.wait_for_selector("#historico tr[data-execucao]", timeout=30000)
        primeira = page.locator("#historico tr[data-execucao]").first
        execucao = primeira.get_attribute("data-execucao")
        primeira.locator("button.repetir").click()
        page.wait_for_function(
            f"() => document.querySelector('#situacao').dataset.repetido === '{execucao}'", timeout=30000)
        assert int(page.get_attribute("#resultado", "data-total")) == total
        assert int(page.get_attribute("#historico", "data-total")) >= 2

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_tracado_ms", tela.medidas["abrir_tracado_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        if item_id:
            tela.api("DELETE", f"/api/itens/{item_id}")
        tela.api("DELETE", f"/api/rede/{rid}")
