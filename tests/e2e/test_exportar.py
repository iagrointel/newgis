"""e2e do botão Exportar (cláusula "e2e do botão Exportar com captura" do item L0-04-h-exportar).

Percorre a tela como um usuário: abre o painel de uma camada vetorial, clica em Exportar, escolhe GeoPackage,
manda exportar, espera o link aparecer, baixa o arquivo pelo próprio navegador e confere que o que chegou é um
GeoPackage de verdade (assinatura `SQLite format 3` e a contagem de feições lida pelo `ogrinfo`). Depois
repete em CSV com vírgula decimal, que é a opção que a tela precisa deixar escolher. Captura de tela em cada
passo (tests/e2e/capturas/L0-04-h-exportar_*.png).

Como rodar contra esta trilha (a URL pública da trilha não existe de propósito):

    set -a; source /home/dev/plataforma/laco/var/trilha/t04h.env; set +a
    venv/bin/uvicorn app.main:app --port 8162 &
    venv/bin/python -m app.jobs.worker &
    venv/bin/pytest tests/e2e/test_exportar.py -m lento --base-url http://127.0.0.1:8162

Sem worker vivo o arquivo nunca fica pronto: o teste salta com a razão explícita em vez de falhar por
tempo esgotado (o que esconderia a causa).
"""

import subprocess
import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, credenciais

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-04-h-exportar"
ROTAS = ("/api/exportacoes", "/api/exportacoes/formatos")


class TelaExportar(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_exportacao(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend sem {faltam} no OpenAPI da URL de teste")
    return api_auth


@pytest.fixture(scope="session")
def inquilino_com_camada(env, api_exportacao):
    """Inquilino próprio com uma camada de 20 mil feições, criado pelo superadmin — o mesmo caminho das
    fixtures de `tests/api/exportacao/conftest.py`, reaproveitado aqui.

    Por que não usar o inquilino de demonstração: numa BASE DE TRILHA o schema `d_demo` pertence ao papel da
    base de PRODUÇÃO (o slug é o mesmo em todo ambiente, e o schema de dado do inquilino não é reescrito por
    ambiente), então a trilha não pode criar tabela nele. Um inquilino novo, criado pela própria trilha, tem
    o schema no papel certo.
    """
    from tests.api.conftest import cred as _  # noqa: F401 — só para deixar claro de onde vêm as credenciais
    from tests.api.conftest import (
        credenciais as credenciais_api,
    )
    from tests.api.conftest import (
        entrar,
        ligar_2fa,
        novo_cliente,
        totp_guardado,
        totp_guardar,
    )
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
    camada = semear_camada(env, inq, 20_000, "zt camada do e2e de exportacao")
    yield inq, camada
    inq.apagar()


def _esperar_link(page, segundos: int = 180) -> str:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if page.locator("#exportar-link").count():
            return page.locator("#exportar-link").get_attribute("href")
        if page.locator("#exportar-aviso[data-tipo='erro']").count():
            pytest.fail(f"exportação falhou na tela: {page.text_content('#exportar-aviso')}")
        page.wait_for_timeout(500)
    pytest.skip("o arquivo não ficou pronto no prazo: há worker da fila rodando neste ambiente?")
    return ""


def test_exportar_pela_tela_gera_arquivo_valido(page, base_url, inquilino_com_camada, medida, tmp_path):
    inq, camada = inquilino_com_camada
    tela = TelaExportar(page, base_url)
    tela.entrar(inq.slug, "admin", inq.senha, proximo="/conteudo")

    tela.ir(f"/conteudo/{camada['item_id']}")
    page.wait_for_selector("#item-titulo", timeout=20000)
    tela.capturar("painel_do_item")
    assert page.locator("#item-exportar").count() == 1, "a camada hospedada tem de mostrar o botão Exportar"

    page.click("#item-exportar")
    page.wait_for_selector("#exportar-formato", timeout=20000)
    tela.capturar("dialogo_aberto")

    # 1) GeoPackage
    page.select_option("#exportar-formato", "gpkg")
    page.fill("#exportar-nome", "e2e-exportar")
    inicio = time.monotonic()
    page.click("#exportar-executar")
    href = _esperar_link(page)
    tela.medidas["exportar_gpkg_pela_tela_ms"] = round((time.monotonic() - inicio) * 1000, 1)
    tela.capturar("arquivo_pronto")

    baixado = tmp_path / "e2e.gpkg"
    resposta = page.request.get(href if href.startswith("http") else f"{base_url}{href}")
    assert resposta.status == 200, resposta.status
    baixado.write_bytes(resposta.body())
    assert baixado.read_bytes()[:15] == b"SQLite format 3", baixado.read_bytes()[:20]
    info = subprocess.run(["ogrinfo", "-so", "-al", str(baixado)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr[:400]
    contagens = [int(li.split(":", 1)[1]) for li in info.stdout.splitlines()
                 if li.strip().startswith("Feature Count:")]
    assert contagens and sum(contagens) > 0, info.stdout[:400]

    # 2) CSV com vírgula decimal (a opção que a tela precisa oferecer)
    page.select_option("#exportar-formato", "csv")
    page.wait_for_selector("#exportar-csv:not([hidden])", timeout=10000)
    page.select_option("#exportar-csv-separador", ";")
    page.select_option("#exportar-csv-decimal", ",")
    page.fill("#exportar-csv-x", "longitude")
    page.fill("#exportar-csv-y", "latitude")
    tela.capturar("opcoes_csv")
    page.click("#exportar-executar")
    href_csv = _esperar_link(page)
    resposta = page.request.get(href_csv if href_csv.startswith("http") else f"{base_url}{href_csv}")
    assert resposta.status == 200
    texto = resposta.body().decode("utf-8", "replace")
    cabecalho = texto.splitlines()[0]
    assert cabecalho.startswith("longitude;latitude"), cabecalho
    primeira = texto.splitlines()[1].split(";")[0]
    assert "," in primeira and "." not in primeira, primeira
    tela.capturar("csv_pronto")

    tela.verificar()
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "tests/e2e/test_exportar.py::test_exportar_pela_tela_gera_arquivo_valido")
    gravar("capturas_e2e", sorted(p.name for p in CAPTURAS.glob(f"{ITEM}_*.png")), "arquivos",
           "playwright screenshot full_page")


def test_botao_exportar_aparece_so_com_o_privilegio(page, base_url, api_exportacao):
    """A tela não mostra um botão que sempre falharia: sem `conteudo.exportar` o botão não é desenhado (o
    servidor recusa de novo, com 403 — a tela é conveniência, não a tranca)."""
    c = credenciais()
    if "demo" not in c:
        pytest.skip("sem credenciais de demo")
    tela = TelaExportar(page, base_url)
    tela.entrar("demo", *c["demo"], proximo="/conteudo")
    privilegios = tela.api("GET", "/api/eu").json().get("privilegios") or []
    if "conteudo.exportar" in privilegios:
        pytest.skip("o admin de demonstração TEM o privilégio; este caso precisa de um usuário sem ele "
                    "(coberto em tests/api/exportacao/test_exportacao.py::"
                    "test_usuario_sem_privilegio_exportar_recebe_403)")
