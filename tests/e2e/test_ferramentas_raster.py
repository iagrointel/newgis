"""e2e do item L2-05-e: a tela /analise roda DUAS ferramentas raster sobre itens do inquilino — uma de
saída vetorial (estatísticas zonais) e uma de saída raster (reclassificar) — e a ficha do resultado mostra
a proveniência. Com captura de cada uma. Sem worker: o custo destes rasters pequenos fica abaixo do teto e
a execução é em processo."""

import mimetypes
import re
import tempfile
from pathlib import Path

import pytest

from tests.api.ferramentas import apoio, apoio_raster
from tests.e2e.apoio import Tela

ITEM = "L2-05-e-raster-basico"
WEB = Path(__file__).resolve().parents[2] / "web"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


class _Sessao:
    """A sessão de API do playwright com a mesma interface que o apoio de testes espera."""

    def __init__(self, admin_api):
        self.api = admin_api

    def post(self, caminho, json):
        r = self.api.post(caminho, data=json)
        return type("R", (), {"status_code": r.status, "text": r.text(), "json": r.json})()


def _tenant_id(env, slug: str) -> int:
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM plat.tenant_publico(%s)", (slug,))
            return cur.fetchone()["id"]
    finally:
        con.close()


@pytest.fixture
def cenario(env, admin_api):
    """Um raster de classes e uma camada de zonas no inquilino demo."""
    sessao = _Sessao(admin_api)
    criados = []
    with tempfile.TemporaryDirectory(prefix="zt-e2e-raster-") as tmp:
        arquivo = apoio_raster.gerar_classes(Path(tmp) / "classes.tif")
        raster = apoio_raster.semear(_tenant_id(env, "demo"), "demo", arquivo, "E2E uso do solo")
        criados.append(raster["id"])
        zonas = apoio_raster.criar_camada_poligonos(env, sessao, "demo", [
            ("norte", apoio_raster.quadrado(30, 30, 200, 150)),
            ("sul", apoio_raster.quadrado(300, 400, 220, 180)),
        ])
        criados.append(zonas["id"])
        yield raster, zonas, criados
    apoio.apagar_itens(env, "demo", criados)


def servir_estatico(rota):
    """Em produção quem serve `/static/` é o nginx, não a aplicação (deploy/nginx.conf e o script de
    homologação dizem isso com todas as letras). Numa trilha de desenvolvimento não há nginx na frente,
    então o próprio navegador de teste entrega os arquivos do diretório `web/` — o que se está medindo
    aqui é a TELA e a ferramenta, não a entrega de arquivo estático."""
    caminho = rota.request.url.split("/static/", 1)[1].split("?")[0]
    arquivo = (WEB / caminho).resolve()
    if not str(arquivo).startswith(str(WEB.resolve())) or not arquivo.is_file():
        rota.fulfill(status=404, body="")
        return
    tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    rota.fulfill(status=200, body=arquivo.read_bytes(), headers={"content-type": tipo})


def test_duas_ferramentas_raster_na_tela_com_proveniencia(page, base_url, credenciais_demo, cenario):
    slug, login, senha = credenciais_demo
    raster, zonas, criados = cenario
    tela = Tela(page, base_url)
    # fora do nginx o Origin do navegador nunca casa com PLAT_URL_PUBLICA: o cabeçalho sai só desta
    # chamada (a checagem em si é provada em tests/api).
    page.route("**/static/**", servir_estatico)
    page.route("**/api/ferramentas/*/executar", lambda rota: rota.fulfill(response=rota.fetch(
        headers={k: v for k, v in rota.request.headers.items() if k.lower() != "origin"})))
    tela.entrar(slug, login, senha, proximo="/analise")
    tela.ir("/analise", "pagina_analise_raster_ms")

    # 1. estatísticas zonais: entra camada + raster, sai camada
    assert page.locator("#ferramenta option[value='estatisticas_zonais']").count() == 1
    page.select_option("#ferramenta", "estatisticas_zonais")
    page.select_option("#formulario select[name='zonas']", zonas["id"])
    page.select_option("#formulario select[name='raster']", raster["id"])
    page.fill("#formulario input[name='titulo']", "E2E zonais")
    page.click("#formulario button[type='submit']")
    page.wait_for_selector("#resultado-link", timeout=60000)
    item_zonal = page.get_attribute("#execucao-resultado", "data-item-id")
    assert re.fullmatch(r"[0-9a-f-]{36}", item_zonal), item_zonal
    criados.append(item_zonal)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_zonais.png"))
    page.click("#resultado-link")
    page.wait_for_selector("body[data-pronto='1']", timeout=60000)
    page.wait_for_selector("[data-campo='proveniencia'] .proveniencia", timeout=60000)
    texto = page.text_content("[data-campo='proveniencia']")
    assert "estatisticas_zonais v1" in texto and raster["id"] in texto and zonas["id"] in texto
    page.locator("[data-campo='proveniencia']").scroll_into_view_if_needed()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_zonais_proveniencia.png"))

    # 2. reclassificar: entra raster, sai raster
    tela.ir("/analise", "pagina_analise_raster_2_ms")
    page.select_option("#ferramenta", "reclassificar_raster")
    page.select_option("#formulario select[name='raster']", raster["id"])
    page.fill("#formulario input[name='tabela']", "0-2:10;2-*:20")
    page.fill("#formulario input[name='titulo']", "E2E reclassificado")
    page.click("#formulario button[type='submit']")
    page.wait_for_selector("#resultado-link", timeout=60000)
    item_raster = page.get_attribute("#execucao-resultado", "data-item-id")
    assert re.fullmatch(r"[0-9a-f-]{36}", item_raster), item_raster
    criados.append(item_raster)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_reclassificar.png"))
    page.click("#resultado-link")
    page.wait_for_selector("body[data-pronto='1']", timeout=60000)
    page.wait_for_selector("[data-campo='proveniencia'] .proveniencia", timeout=60000)
    texto = page.text_content("[data-campo='proveniencia']")
    assert "reclassificar_raster v1" in texto and raster["id"] in texto
    page.locator("[data-campo='proveniencia']").scroll_into_view_if_needed()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_reclassificar_proveniencia.png"))
    tela.verificar()
