"""e2e da tela de ISOLAMENTO (cláusula do portão do item L4-02-c-isolamento: "captura mostrando os
dispositivos destacados em cor própria").

A rede é criada pela API antes de abrir a tela (subestação — chave — fusível — trecho com falha — chave —
transformador — carga), a tela traça o isolamento do ponto com falha e o teste confere, sem olhar figura:

  * a tabela traz UM dispositivo a abrir, o fusível;
  * o resumo traz clientes/transformadores/km;
  * a camada de dispositivos do mapa está pintada com `circle-color` = a cor do dispositivo, e essa cor é
    DIFERENTE da cor da camada do trecho isolado — é isso que "cor própria" quer dizer, e é lido do próprio
    MapLibre (`getPaintProperty`), não da folha de estilo;
  * a captura sai em tests/e2e/capturas/ com o mapa já desenhado.

Porta 8342: a deste turno (o prompt do item)."""

import math
import re
import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-02-c-isolamento"
PORTA = 8342
URL_TESTE = f"http://127.0.0.1:{PORTA}"
LON0, LAT0, PASSO = 40.000, 11.000, 0.001
# 4,9 cm em grau de longitude nesta latitude: a folga entre a ponta do trecho e o dispositivo.
FOLGA = 0.049 / (111_320.0 * math.cos(math.radians(LAT0)))


@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com `web/` em /static — os e2e do repositório correm contra a URL interna
    servida por nginx, que roda o código de `master`, não o do ramo (mesma montagem do e2e do L4-04-a)."""
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


def _capturar(page, nome: str):
    """A captura desta tela, com o nome do ITEM no arquivo (`Tela.capturar` carimba o item do L0-02)."""
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho), full_page=True)
    return caminho


def _cores_do_modulo() -> tuple[str, str]:
    """As duas cores saem do próprio módulo da tela (nunca digitadas duas vezes)."""
    fonte = (RAIZ / "web" / "js" / "rede" / "isolamento.js").read_text(encoding="utf-8")
    isolado = re.search(r"COR_ISOLADO = '([^']+)'", fonte).group(1)
    dispositivo = re.search(r"COR_DISPOSITIVO = '([^']+)'", fonte).group(1)
    return isolado, dispositivo


def _x(i: int) -> float:
    return LON0 + i * PASSO


def _rede_com_falha(tela) -> tuple[str, str]:
    from app.rede_utilidades import instalados

    r = tela.api("POST", "/api/rede", {"nome": f"zt-e2e-l402c-{sufixo()}", "disciplina": "eletrica"})
    assert r.status == 201, r.text()
    rid = r.json()["id"]
    r = tela.api("POST", f"/api/rede/{rid}/pacote", instalados.bruto("eletrica-br").decode("utf-8"),
                 {"Content-Type": "application/json"})
    assert r.status == 201, r.text()

    # cada dispositivo de dois terminais fica ENTRE dois trechos que não se tocam: as pontas dos trechos
    # param a 4,9 cm dele (dentro da tolerância padrão de 5 cm da rede, e a 9,8 cm uma da outra, fora dela),
    # senão os dois trechos se ligariam direto e o dispositivo seria atravessado sem existir — o mesmo
    # cuidado do teste de API do item irmão L4-02-a.
    def ponto(lon, tipo_codigo, grupo, atributos=None):
        corpo = {"grupo": grupo, "tipo_codigo": tipo_codigo, "lon": lon, "lat": LAT0}
        if atributos:
            corpo["atributos"] = atributos
        r = tela.api("POST", f"/api/rede/{rid}/feicoes/pontos", corpo)
        assert r.status == 201, r.text()
        return r.json()["id"]

    def linha(a, b, grupo="trecho_de_media_tensao"):
        r = tela.api("POST", f"/api/rede/{rid}/feicoes/linhas",
                     {"grupo": grupo, "tipo_codigo": 1, "coordenadas": [[a, LAT0], [b, LAT0]]})
        assert r.status == 201, r.text()
        return r.json()["id"]

    ponto(_x(0), 1, "subestacao")
    ponto(_x(1), 1, "chave_de_media_tensao", {"estado": "fechado"})
    fusivel = ponto(_x(3), 2, "chave_de_media_tensao", {"estado": "fechado"})
    ponto(_x(5), 1, "chave_de_media_tensao", {"estado": "fechado"})
    ponto(_x(6), 1, "transformador_de_distribuicao")
    ponto(_x(7), 1, "ponto_de_iluminacao_publica")
    dispositivos_de_dois_terminais = {1, 3, 5}
    for i in range(7):
        a = _x(i) + (FOLGA if i in dispositivos_de_dois_terminais else 0.0)
        b = _x(i + 1) - (FOLGA if (i + 1) in dispositivos_de_dois_terminais else 0.0)
        linha(a, b, "trecho_de_baixa_tensao" if i == 6 else "trecho_de_media_tensao")
    assert tela.api("POST", f"/api/rede/{rid}/topologia/habilitar").status == 201
    return rid, fusivel


def test_isolamento_na_tela_com_dispositivos_em_cor_propria(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    cor_isolado, cor_dispositivo = _cores_do_modulo()
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/isolamento")
    rid, fusivel = _rede_com_falha(tela)
    try:
        tela.ir("/redes/isolamento", "abrir_isolamento_ms")
        assert page.title().startswith("Isolamento")

        page.select_option("#rede", rid)
        page.fill("#lon", str(_x(4)))
        page.fill("#lat", str(LAT0))
        page.fill("#tolerancia", "1")
        page.click("#tracar")
        page.wait_for_function("document.querySelector('#dispositivos').dataset.total === '1'", timeout=30000)

        assert page.locator("#dispositivos tbody tr").count() == 1
        assert page.locator(f"#dispositivos tr[data-feicao='{fusivel}']").count() == 1
        assert page.get_attribute("#dispositivos", "data-isolavel") == "1"
        assert page.locator("#resumo:not([hidden])").count() == 1
        assert page.text_content("#r-elementos").strip() != "0"

        cores = page.evaluate(
            "() => { const m = window.__mapa_isolamento; return m ? ["
            "  m.getPaintProperty('dispositivos-ponto', 'circle-color'),"
            "  m.getPaintProperty('isolados-linha', 'line-color')] : null; }")
        assert cores == [cor_dispositivo, cor_isolado], cores
        assert cor_dispositivo != cor_isolado
        pontos = page.evaluate(
            "() => window.__mapa_isolamento.getSource('dispositivos')._data.features.length")
        assert pontos == 1, pontos

        caminho = _capturar(page, "dispositivos")
        assert caminho.exists() and caminho.stat().st_size > 0

        tela.verificar()
        gravar = medida(ITEM)
        gravar("abrir_isolamento_ms", tela.medidas["abrir_isolamento_ms"], "ms",
               "goto até body[data-pronto=1] no chromium do playwright")
    finally:
        tela.api("DELETE", f"/api/rede/{rid}")
