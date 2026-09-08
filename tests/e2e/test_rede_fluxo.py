"""e2e das camadas do fluxo de potência no mapa (cláusula do portão do item L4-07-fluxo-de-potencia).

A tela `/redes/fluxo` escolhe a rede e o alimentador, declara os parâmetros, manda analisar e desenha o
resultado em três camadas do MapLibre: tensão (ponto por barra e fase), corrente e carregamento (a linha do
trecho). Este teste faz o caminho inteiro no navegador:

  1. abre a tela e escolhe a rede e o alimentador;
  2. clica em `analisar` e espera a tarja de convergência aparecer — que é a regra dura do item: nenhum
     número aparece sem o estado de convergência ao lado;
  3. confere, PERGUNTANDO AO MAPA (`map.getLayer` / `querySourceFeatures`), que as três camadas existem
     e têm feições — não basta o servidor ter respondido;
  4. desmarca uma camada e confere que ela some do mapa.

Roda contra um servidor próprio da trilha (porta do item), com `web/` em /static — os e2e do repositório
correm contra a URL interna servida por nginx, que roda o código de `master`, não o do ramo."""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-07-fluxo-de-potencia"
PORTA = 8460  # a 8197 do prompt estava OCUPADA por outra trilha (conferido com `ss -ltn`)
URL_TESTE = f"http://127.0.0.1:{PORTA}"
CTMT = "1_E4F_1"
LON0, LAT0, D = 36.0, 15.0, 0.001
GRANDEZAS = ("tensao", "corrente", "carregamento")


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
    """Um alimentador mínimo mas COMPLETO: chave de saída (que dá a tensão nominal), dois trechos de média
    tensão, transformador com potência e perdas, trecho de baixa e uma unidade consumidora com energia."""
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l407-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    a, b, c = (LON0, LAT0), (LON0 + D, LAT0), (LON0 + 2 * D, LAT0)
    e = (LON0 + 2 * D, LAT0 + D)
    comum = {"ctmt": CTMT, "sub": "E4F"}
    pontos = (
        {"grupo": "chave_de_media_tensao", "tipo_codigo": 4, "lon": a[0], "lat": a[1],
         "atributos": {**comum, "unsemt_p_n_ope": "F", "unsemt_cod_id": "CH-E4F", "ten_nom": "49"}},
        {"grupo": "transformador_de_distribuicao", "tipo_codigo": 1, "lon": c[0], "lat": c[1],
         "atributos": {"cod_id": "TR-E4F", "pot_nom": 75.0, "ten_lin_se": "15",
                       "per_fer": 150.0, "per_tot": 1100.0}},
        {"grupo": "unidade_consumidora", "tipo_codigo": 1, "lon": e[0], "lat": e[1] + D,
         "atributos": {"cod_id": "UC-E4F", "ene_sum": 3600.0}},
    )
    for corpo in pontos:
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", corpo).status == 201
    linhas = (
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(a), list(b)],
         "atributos": {**comum, "cod_id": "MT-1"}},
        {"grupo": "trecho_de_media_tensao", "tipo_codigo": 1, "coordenadas": [list(b), list(c)],
         "atributos": {**comum, "cod_id": "MT-2"}},
        {"grupo": "trecho_de_baixa_tensao", "tipo_codigo": 1, "coordenadas": [list(c), list(e)],
         "atributos": {"cod_id": "BT-1"}},
        {"grupo": "ramal_de_ligacao", "tipo_codigo": 1,
         "coordenadas": [list(e), [e[0], e[1] + D]], "atributos": {"cod_id": "RL-1"}},
    )
    for corpo in linhas:
        assert tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", corpo).status == 201
    assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar").status == 201
    r = tela.api("POST", f"/api/rede/{rid}/controladores/importar")
    assert r.status == 200, r.text()
    r = tela.api("PUT", f"/api/rede/{rid}/tier/media_tensao/propagadores",
                 {"propagadores": ["ctmt_ten_nom"]})
    assert r.status == 200, r.text()
    # a atualização em LOTE é job, e a trilha não tem worker: aqui a subrede é atualizada uma a uma, pelo
    # mesmo caminho síncrono que o botão da tela de controladores usa.
    subredes = tela.api("GET", f"/api/rede/{rid}/subredes?limite=50").json()["itens"]
    for s in subredes:
        r = tela.api("POST", f"/api/rede/{rid}/subredes/{s['id']}/atualizar", {})
        assert r.status == 200, r.text()
    return rid


def test_camadas_de_tensao_corrente_e_carregamento_no_mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/fluxo")
    rid = _rede(tela)
    try:
        subredes = tela.api("GET", f"/api/rede/{rid}/subredes?limite=50").json()["itens"]
        assert any(s["nome"] == CTMT and s["atualizado_em"] for s in subredes), subredes

        tela.ir("/redes/fluxo", "abrir_fluxo_ms")
        page.wait_for_selector("#rede", timeout=30000)
        page.select_option("#rede", rid)
        page.wait_for_function(
            "() => document.querySelectorAll('#alimentador option').length > 0", timeout=30000)
        page.select_option("#alimentador", CTMT)
        page.select_option("#modo", "hora")
        page.click("#analisar")

        # 1. a tarja de convergência aparece ANTES de qualquer camada, e diz que convergiu
        page.wait_for_selector("#convergencia", timeout=120000)
        assert page.get_attribute("#convergencia", "data-convergiu") == "1", \
            page.text_content("#convergencia")
        assert "convergiu" in page.text_content("#convergencia").lower()
        assert page.text_content("#f-parametros").strip().startswith("{")
        assert page.text_content("#f-topologia").strip() not in ("", "—")

        # 2. as três camadas existem NO MAPA e têm feição — perguntado ao próprio MapLibre
        page.wait_for_function(
            "() => ['tensao','corrente','carregamento'].every("
            "  (g) => window.__mapa && window.__mapa.getLayer('fluxo-' + g))", timeout=120000)
        for grandeza in GRANDEZAS:
            contagem = page.evaluate(
                "(g) => window.__mapa.getSource('fluxo-' + g)._data.features.length", grandeza)
            assert contagem > 0, grandeza
            tipo = page.evaluate("(g) => window.__mapa.getLayer('fluxo-' + g).type", grandeza)
            assert tipo == ("circle" if grandeza == "tensao" else "line"), (grandeza, tipo)

        # 3. desmarcar uma camada a tira do mapa
        page.uncheck("#ver-corrente")
        page.wait_for_function(
            "() => window.__mapa.getLayoutProperty('fluxo-corrente', 'visibility') === 'none'",
            timeout=30000)
        assert page.evaluate(
            "() => window.__mapa.getLayoutProperty('fluxo-tensao', 'visibility') !== 'none'")

        tela.capturar_em = None
        tela.verificar()
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
