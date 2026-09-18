"""e2e do montante/jusante PELA TELA (cláusula e2e do portão do item L4-02-b-montante-jusante).

A tela `/redes/tracado` oferece `montante` e `jusante` no mesmo seletor dos outros traçados. O teste
percorre, pelo navegador, os três comportamentos que o item promete:

1. JUSANTE pela tela: na cadeia SE — transformador — UC com a subestação marcada como controlador de
   subrede, o jusante da subestação é a cadeia inteira, e a tabela da tela confere, feição a feição, com o
   que a API responde para o mesmo pedido;
2. MONTANTE pela tela: o montante da unidade de consumo chega à subestação (o controlador declarado);
3. INDETERMINADO pela tela: num triângulo de média tensão (laço), o traçado não inventa sentido — a tabela
   fica vazia e a situação da tela diz o porquê (a mensagem da API), nunca "traçado concluído".

As redes são criadas pela API antes de abrir a tela e apagadas no fim."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-02-b-montante-jusante"
PORTA = 8344  # porta desta trilha; conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"
LON0, LAT0, D = 44.0, 15.0, 0.001


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


def _ponto(tela, rid, lon, lat, grupo):
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos",
                 {"tipo_codigo": 1, "grupo": grupo, "lon": lon, "lat": lat})
    assert r.status == 201, r.text()
    return r.json()["id"]


def _linha(tela, rid, coordenadas, grupo):
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/linhas",
                 {"tipo_codigo": 1, "grupo": grupo, "coordenadas": coordenadas})
    assert r.status == 201, r.text()
    return r.json()["id"]


def _rede_vazia(tela, rotulo):
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l402b-{rotulo}-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()
    return rid


def _rede_com_controlador(tela):
    """Cadeia SE — transformador — UC com a subestação como controlador de subrede (fonte) no tier de
    média tensão. Devolve (rid, ids)."""
    rid = _rede_vazia(tela, "cadeia")
    a, b, c = (LON0, LAT0), (LON0 + D, LAT0), (LON0 + 2 * D, LAT0)
    se = _ponto(tela, rid, *a, "subestacao")
    l1 = _linha(tela, rid, [list(a), list(b)], "trecho_de_media_tensao")
    transf = _ponto(tela, rid, *b, "transformador_de_distribuicao")
    l2 = _linha(tela, rid, [list(b), list(c)], "trecho_de_baixa_tensao")
    uc = _ponto(tela, rid, *c, "ponto_de_iluminacao_publica")
    r = tela.api("POST", f"/api/rede/{rid}/topologia/habilitar", {})
    assert r.status == 201, r.text()
    r = tela.api("POST", f"/api/rede/{rid}/controlador",
                 {"feicao_id": se, "subrede": f"zt-e2e-{sufixo()}", "tier": "media_tensao",
                  "papel": "fonte", "nome": "zt-e2e-alimentador"})
    assert r.status == 201, r.text()
    return rid, {"se": se, "l1": l1, "transf": transf, "l2": l2, "uc": uc}


def _tracar_na_tela(page, rid, tipo, feicao_id):
    page.select_option("#rede", rid)
    page.select_option("#tipo", tipo)
    page.fill("#feicao", feicao_id)
    page.click("#tracar")
    page.wait_for_selector("#resultado table", timeout=30000)
    return {x for x in page.locator("#resultado tbody tr").evaluate_all(
        "trs => trs.map(tr => tr.dataset.feicao)")}


def test_montante_e_jusante_pela_tela(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/tracado")
    rid, ids = _rede_com_controlador(tela)
    try:
        tela.ir("/redes/tracado", "abrir_tracado_ms")
        assert page.title().startswith("Resultado de traçado")

        # jusante da subestação (o controlador): a cadeia inteira, e igual à resposta da API
        na_tela = _tracar_na_tela(page, rid, "jusante", ids["se"])
        r = tela.api("POST", f"/api/rede/{rid}/tracar",
                     {"tipo": "jusante", "pontos_partida": [{"feicao_id": ids["se"]}]})
        assert r.status == 200, r.text()
        na_api = {e["feicao_id"] for e in r.json()["elementos"]}
        assert r.json()["origem_direcao"] == "controlador" and r.json()["direcao"] == "definida", r.json()
        assert na_tela == na_api == {ids["se"], ids["l1"], ids["transf"], ids["l2"], ids["uc"]}, na_tela
        assert page.get_attribute("#situacao", "data-direcao") == "definida"

        # montante da unidade de consumo: a cadeia de volta até o controlador
        na_tela = _tracar_na_tela(page, rid, "montante", ids["uc"])
        assert ids["se"] in na_tela and ids["transf"] in na_tela, na_tela
        assert na_tela == {ids["se"], ids["l1"], ids["transf"], ids["l2"], ids["uc"]}, na_tela

        tela.capturar_em = None
        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_tracado_ms", tela.medidas["abrir_tracado_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")


def test_laco_na_tela_diz_indeterminado(page, base_url, credenciais_demo):
    """Triângulo de média tensão com controlador num vértice: dois caminhos até o controlador, então o
    traçado não escolhe — a tela mostra a mensagem de indeterminado e a tabela vazia, nunca um sentido."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/tracado")
    rid = _rede_vazia(tela, "laco")
    try:
        a, b, c = (LON0, LAT0), (LON0 + D, LAT0), (LON0 + D / 2, LAT0 + D)
        se = _ponto(tela, rid, *a, "subestacao")
        _linha(tela, rid, [list(a), list(b)], "trecho_de_media_tensao")
        _linha(tela, rid, [list(b), list(c)], "trecho_de_media_tensao")
        _linha(tela, rid, [list(c), list(a)], "trecho_de_media_tensao")
        assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar", {}).status == 201
        r = tela.api("POST", f"/api/rede/{rid}/controlador",
                     {"feicao_id": se, "subrede": f"zt-e2e-{sufixo()}", "tier": "media_tensao",
                      "papel": "fonte", "nome": "zt-e2e-laco"})
        assert r.status == 201, r.text()

        tela.ir("/redes/tracado")
        page.select_option("#rede", rid)
        page.select_option("#tipo", "jusante")
        page.fill("#feicao", se)
        page.click("#tracar")
        page.wait_for_function(
            "() => document.querySelector('#situacao').dataset.direcao === 'indeterminado'", timeout=30000)
        assert page.get_attribute("#resultado", "data-total") == "0"
        assert page.locator("#resultado tbody tr").count() == 0
        assert len(page.text_content("#situacao").strip()) > 20  # a mensagem da API, não "traçado concluído"
        assert page.is_disabled("#selecionar") and page.is_disabled("#exportar")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
