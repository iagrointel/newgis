"""e2e da cláusula "e2e" do item L4-02-d-lacos-e-caminho-curto, pela tela `/redes/tracado`
(a tela de resultado de traçado do item irmão L4-02-f, que ganhou o tipo `caminho_curto` e o campo
`destino` neste item; `lacos` e `isolados` já estavam na lista dela).

A MESMA rede (quadrado de MT com uma subestação num vértice, uma UC no vértice oposto e um banco de
capacitores sem ligação) percorre os três tipos novos PELA TELA, no chromium:

1. `tipo=lacos`   → a tela mostra 1 laço e as 4 linhas do quadrado na tabela (a resposta ganhou
   `elementos` de topo neste item — as feições únicas de todos os laços — que é o que a tela e as
   agregações leem);
2. `tipo=isolados` → a tabela mostra o banco de capacitores sem caminho à fonte, e a subestação
   (a própria fonte) NÃO aparece;
3. `tipo=caminho_curto` → origem no campo `feicao`, destino no campo novo `destino`; a tabela mostra
   os 2 trechos do caminho mais curto entre vértices opostos do quadrado.

A rede é criada pela API antes de abrir a tela e apagada no fim. Padrão de servidor próprio do e2e do
item irmão (uvicorn na porta da trilha, `web/` em /static), porque os e2e do repositório contra a URL
interna rodam o código de `master`, não o do ramo.
"""

import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-02-d-lacos-e-caminho-curto"
PORTA = 8347  # porta desta trilha; conferida livre com `ss -ltn` antes de subir
URL_TESTE = f"http://127.0.0.1:{PORTA}"
LON0, LAT0, D = 41.0, 16.0, 0.001


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


def _rede(tela) -> dict:
    """Quadrado de MT (laço de 4 trechos) + subestação (fonte) num vértice + UC no vértice oposto +
    banco de capacitores isolado. Devolve os ids que o teste usa."""
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l402d-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    a = (LON0, LAT0)
    b = (LON0 + D, LAT0)
    c = (LON0 + D, LAT0 + D)
    d = (LON0, LAT0 + D)
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos",
                 {"tipo_codigo": 1, "grupo": "subestacao", "lon": a[0], "lat": a[1]})
    assert r.status == 201, r.text()
    se = r.json()["id"]
    linhas = []
    for p0, p1 in ((a, b), (b, c), (c, d), (d, a)):
        r = tela.api("POST", f"/api/rede/{rid}/feicoes/linhas", {
            "tipo_codigo": 1, "grupo": "trecho_de_media_tensao",
            "coordenadas": [[p0[0], p0[1]], [p1[0], p1[1]]]})
        assert r.status == 201, r.text()
        linhas.append(r.json()["id"])
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos",
                 {"tipo_codigo": 2, "grupo": "unidade_consumidora", "lon": c[0], "lat": c[1]})
    assert r.status == 201, r.text()
    uc = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos",
                 {"tipo_codigo": 1, "grupo": "banco_de_capacitores", "lon": 90.0, "lat": 90.0})
    assert r.status == 201, r.text()
    isolado = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/topologia/habilitar", {})
    assert r.status == 201, r.text()
    return {"rid": rid, "se": se, "uc": uc, "isolado": isolado, "linhas": linhas}


def _tracar_pela_tela(page, rid, tipo, feicao=None, destino=None) -> list[str]:
    """Seleciona rede/tipo na tela, preenche o que houver, clica TRAÇAR e devolve os ids de feição das
    linhas da tabela de resultado."""
    page.select_option("#rede", rid)
    page.select_option("#tipo", tipo)
    page.fill("#feicao", feicao or "")
    page.fill("#destino", destino or "")
    page.click("#tracar")
    page.wait_for_selector("#resultado table tbody tr", timeout=30000)
    return page.locator("#resultado tbody tr").evaluate_all(
        "(trs) => trs.map((tr) => tr.dataset.feicao)")


def test_lacos_isolados_e_caminho_curto_pela_tela(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha, proximo="/redes/tracado")
    rede = _rede(tela)
    rid = rede["rid"]
    try:
        tela.ir("/redes/tracado", "abrir_tracado_ms")
        assert page.title().startswith("Resultado de traçado")

        # 1. laços: 1 laço (o quadrado), formado pelas 4 linhas de MT
        feicoes = _tracar_pela_tela(page, rid, "lacos")
        assert page.get_attribute("#resultado", "data-total") == "1"
        assert sorted(feicoes) == sorted(rede["linhas"]), feicoes
        tela.capturar("lacos")

        # 2. isolados: o banco de capacitores sem ligação aparece; a fonte, nunca
        feicoes = _tracar_pela_tela(page, rid, "isolados")
        assert rede["isolado"] in feicoes, feicoes
        assert rede["se"] not in feicoes, "a própria fonte nunca é isolada"
        tela.capturar("isolados")

        # 3. caminho mais curto SE → UC (vértices opostos): 2 trechos do quadrado
        feicoes = _tracar_pela_tela(page, rid, "caminho_curto", feicao=rede["se"], destino=rede["uc"])
        assert len(feicoes) == 2, feicoes
        assert set(feicoes) <= set(rede["linhas"]), feicoes
        tela.capturar("caminho_curto")

        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_tracado_ms", tela.medidas["abrir_tracado_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
