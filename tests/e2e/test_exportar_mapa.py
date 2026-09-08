"""e2e do item L2-01-l: o botão Exportar DENTRO do mapa e a imagem do mapa com legenda e atribuição.

Duas cláusulas do portão, as duas de tela:

  * "PNG contém a legenda e a atribuição (captura comparada)" — o mesmo mapa é composto duas vezes, com
    e sem legenda/atribuição, e as duas imagens são comparadas pixel a pixel: as cores da legenda
    aparecem só na primeira, e a faixa da atribuição difere entre as duas. Comparar contra uma imagem
    guardada não serviria (o mapa muda com o dado); comparar as duas composições entre si serve.
  * "e2e do botão com captura" — o usuário liga a camada, escolhe formato e CRS, manda exportar, o link
    aparece e o arquivo baixado é lido pelo ogrinfo. Captura de tela em cada passo.

Como rodar contra esta trilha:

    set -a; source /home/dev/plataforma/laco/var/trilha/il201lexpor.env; set +a
    venv/bin/uvicorn app.main:app --port 8303 &
    venv/bin/python -m app.jobs.worker &   # com PLAT_WORKER_URL=http://127.0.0.1:83NN
    venv/bin/pytest tests/e2e/test_exportar_mapa.py -m lento --base-url http://127.0.0.1:8303

Sem worker vivo o arquivo nunca fica pronto e o teste SALTA com essa razão, em vez de falhar por tempo
esgotado (que esconderia a causa). O Martin não é preciso: sem ele a camada não pinta tile, mas a ficha,
a legenda e a exportação — que é o que este arquivo mede — não dependem de tile.
"""

import base64
import datetime
import io
import os
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-01-l-exportacao-do-mapa"
ROTAS = ("/api/exportacoes", "/api/mapa/camadas/{id}/estilo", "/api/mapa/camadas/{id}/feicoes/{fid}")


class TelaMapa(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Numa BASE DE TRILHA o servidor sobe com certificado próprio (a plataforma recusa
    `PLAT_URL_PUBLICA` que não seja https, e a guarda de CSRF compara a Origin com ela). Só aqui, e só
    para o certificado: nenhuma outra checagem é afrouxada."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def api_do_item(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend sem {faltam} no OpenAPI da URL de teste")
    return api_auth


@pytest.fixture(scope="module")
def inquilino_com_camada(env, api_do_item):
    """Inquilino próprio com uma camada de 2 mil pontos — o mesmo caminho do e2e do L0-04-h (o schema
    `d_demo` pertence ao papel da base de produção e a trilha não escreve nele)."""
    from tests.api.conftest import credenciais as credenciais_api
    from tests.api.conftest import entrar, ligar_2fa, novo_cliente, totp_guardado, totp_guardar
    from tests.api.exportacao.conftest import InquilinoDeExportacao, semear_camada

    c = credenciais_api()
    if "plataforma" not in c:
        pytest.skip("sem credenciais do inquilino técnico `plataforma` neste ambiente")
    login, senha = c["plataforma"]
    plat = novo_cliente()
    r = entrar(plat, "plataforma", login, senha, totp_guardado("plataforma"))
    if r.status_code != 200:
        pytest.skip(f"não foi possível entrar como superadmin neste ambiente: {r.status_code}")
    if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
        segredo, _codigos = ligar_2fa(plat)
        totp_guardar("plataforma", login, segredo)
    inq = InquilinoDeExportacao(plat)
    camada = semear_camada(env, inq, 2_000, "zt camada do e2e do mapa")
    yield inq, camada
    inq.apagar()


@pytest.fixture
def mapa(page, base_url, inquilino_com_camada):
    inq, camada = inquilino_com_camada
    tela = TelaMapa(page, base_url)
    tela.entrar(inq.slug, "admin", inq.senha)
    tela.ir("/mapa", "pagina_pronta_ms_mapa")
    page.wait_for_selector('body[data-pronto="1"]', timeout=30000)
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas', { foco: false })")  # UX-04: painel na gaveta
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    linha = page.locator('#lista-camadas li:has(.camada-titulo:text-matches("e2e do mapa"))').first
    caixa = linha.locator("input[type=checkbox]")
    if not caixa.is_checked():
        caixa.check()
    page.evaluate("() => window.plat.mapa.abrirPainel('exportar', { foco: false })")  # UX-04: painel na gaveta
    page.wait_for_selector("#exp-camada", timeout=20000)
    return tela, inq, camada


def _compor_no_navegador(page, com_legenda: bool) -> Image.Image:
    """Compõe a imagem do mapa DENTRO da página (o mesmo caminho do botão PNG) e devolve o bitmap."""
    dados = page.evaluate(
        """async (comLegenda) => {
            const mod = await import('/static/js/mapa/impressao.js');
            const { map, catalogo } = window.plat.mapa;
            const legenda = comLegenda
              ? catalogo.ativas.map((id) => catalogo.ficha(id)).filter(Boolean)
                  .flatMap((f) => f.legenda || []).slice(0, 12)
              : [];
            const { canvas } = mod.compor(map, {
              titulo: 'Mapa do e2e',
              atribuicao: comLegenda ? '© colaboradores do OpenStreetMap — ODbL 1.0' : '',
              legenda,
            });
            return canvas.toDataURL('image/png');
        }""",
        com_legenda,
    )
    return Image.open(io.BytesIO(base64.b64decode(dados.split(",", 1)[1]))).convert("RGB")


def _cores(imagem: Image.Image) -> set[tuple[int, int, int]]:
    return {cor for _n, cor in imagem.getcolors(maxcolors=1 << 22) or []}


def test_png_do_mapa_traz_a_legenda_e_a_atribuicao(mapa, medida):
    """Cláusula: "PNG contém a legenda e a atribuição (captura comparada)"."""
    tela, _inq, _camada = mapa
    page = tela.page
    cores_legenda = page.evaluate(
        """() => { const { catalogo } = window.plat.mapa;
             return catalogo.ativas.map((id) => catalogo.ficha(id)).filter(Boolean)
               .flatMap((f) => f.legenda || []).map((e) => e.cor); }"""
    )
    assert cores_legenda, "a camada ligada tem de trazer legenda do servidor"

    com = _compor_no_navegador(page, True)
    sem = _compor_no_navegador(page, False)
    assert com.size == sem.size, (com.size, sem.size)
    (CAPTURAS / f"{ITEM}_png_com_legenda.png").parent.mkdir(parents=True, exist_ok=True)
    com.save(CAPTURAS / f"{ITEM}_png_com_legenda.png")
    sem.save(CAPTURAS / f"{ITEM}_png_sem_legenda.png")

    presentes = _cores(com)
    ausentes = _cores(sem)
    for cor in cores_legenda:
        rgb = tuple(int(cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        assert rgb in presentes, f"a cor {cor} da legenda não aparece na imagem composta"
        assert rgb not in ausentes, f"a cor {cor} aparece mesmo SEM legenda: a comparação não prova nada"

    # a atribuição vive na faixa de informação, abaixo do mapa: as duas imagens têm de diferir ali
    faixa = (0, com.height - 20, com.width // 2, com.height)
    diferentes = sum(1 for a, b in zip(com.crop(faixa).getdata(), sem.crop(faixa).getdata(), strict=True) if a != b)
    assert diferentes > 50, f"a faixa da atribuição é igual nas duas imagens ({diferentes} pixels diferentes)"

    medida(ITEM)("png_legenda_e_atribuicao",
                 {"classes_na_legenda": len(cores_legenda), "pixels_da_atribuicao": diferentes,
                  "largura": com.width, "altura": com.height},
                 "pixels comparados entre a composição com e sem legenda/atribuição",
                 "tests/e2e/test_exportar_mapa.py::test_png_do_mapa_traz_a_legenda_e_a_atribuicao")


def _esperar_link(page, segundos: int = 180) -> str:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        page.evaluate("() => window.plat.mapa.abrirPainel('exportar', { foco: false })")  # UX-04: painel na gaveta
        if page.locator("#exp-link").count():
            return page.locator("#exp-link").get_attribute("href")
        page.wait_for_timeout(500)
    pytest.skip("o arquivo não ficou pronto no prazo: há worker da fila rodando neste ambiente?")
    return ""


def test_botao_exportar_do_mapa_gera_arquivo_no_crs_pedido(mapa, medida, tmp_path):
    """Cláusula: "e2e do botão com captura". Percorre a tela como usuário: camada ligada, formato
    GeoPackage, EPSG:31983, exportar, esperar o link, baixar e reabrir com o ogrinfo."""
    tela, _inq, _camada = mapa
    page = tela.page
    tela.capturar("bloco_exportar")
    page.evaluate("() => window.plat.mapa.abrirPainel('exportar', { foco: false })")  # UX-04: painel na gaveta
    page.select_option("#exp-formato", "gpkg")
    page.fill("#exp-crs", "31983")
    inicio = time.monotonic()
    page.click("#btn-exportar")
    href = _esperar_link(page)
    tela.medidas["exportar_do_mapa_ms"] = round((time.monotonic() - inicio) * 1000, 1)
    tela.capturar("arquivo_pronto")

    resposta = page.request.get(href if href.startswith("http") else f"{tela.base_url}{href}")
    assert resposta.status == 200, resposta.status
    baixado = tmp_path / "mapa.gpkg"
    baixado.write_bytes(resposta.body())
    assert baixado.read_bytes()[:15] == b"SQLite format 3", baixado.read_bytes()[:20]
    info = subprocess.run(["ogrinfo", "-so", "-al", str(baixado)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr[:400]
    assert 'ID["EPSG",31983]' in info.stdout, info.stdout[:600]
    contagens = [int(li.split(":", 1)[1]) for li in info.stdout.splitlines()
                 if li.strip().startswith("Feature Count:")]
    assert contagens and sum(contagens) == 2000, info.stdout[:400]
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "tests/e2e/test_exportar_mapa.py::"
                                  "test_botao_exportar_do_mapa_gera_arquivo_no_crs_pedido")
    # tempo sem a carga da máquina ao lado não vale como prova (regra do laço, 07/09)
    gravar("carga_da_maquina_na_medida",
           {"carga_1min": os.getloadavg()[0],
            "ram_livre_gb": round(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30, 1),
            "medido_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
           "carga de 1 min e RAM livre no instante da medida acima", "os.getloadavg / os.sysconf")


def test_formato_de_crs_preso_desabilita_o_campo_e_declara_a_perda(mapa):
    """A tela não deixa pedir o impossível: com GeoJSON o campo de EPSG fica desligado e a perda do
    formato aparece escrita, antes de exportar."""
    tela, _inq, _camada = mapa
    page = tela.page
    page.evaluate("() => window.plat.mapa.abrirPainel('exportar', { foco: false })")  # UX-04: painel na gaveta
    page.select_option("#exp-formato", "geojson")
    assert page.locator("#exp-crs").is_disabled()
    assert "EPSG:4326" in page.text_content("#exp-perda")
    page.select_option("#exp-formato", "dxf")
    assert "atributo" in page.text_content("#exp-perda")
    tela.capturar("perda_declarada")
    page.select_option("#exp-formato", "gpkg")
    assert not page.locator("#exp-crs").is_disabled()
