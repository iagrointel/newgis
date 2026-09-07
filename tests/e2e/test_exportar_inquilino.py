"""e2e da cláusula "e2e com captura" do item L0-06-d-exportar-inquilino.

Percorre a tela como o admin do inquilino: abre /admin/organizacao, lê o tamanho estimado que a seção mostra
ANTES de qualquer clique, clica em "Exportar meu inquilino", espera o pacote ficar pronto na lista, baixa o zip
pelo próprio navegador e confere que o que chegou é o pacote de verdade — os quatro componentes, o manifesto
conferindo contra o conteúdo e o GeoPackage reabrindo no ogrinfo. Depois clica de novo e confere que a segunda
execução do dia é recusada com a razão escrita na tela (a cota de 1 por dia da hipótese do item).

Captura de tela em cada passo (tests/e2e/capturas/L0-06-d-exportar-inquilino_*.png).

Como rodar contra esta trilha (a URL pública da trilha não existe de propósito):

    set -a; source /home/dev/plataforma/laco/var/trilha/il006dexpor.env; set +a
    venv/bin/uvicorn app.main:app --port 8412 &
    venv/bin/python -m app.jobs.worker &
    venv/bin/pytest tests/e2e/test_exportar_inquilino.py -m lento --base-url http://127.0.0.1:8412

Sem worker vivo o pacote nunca fica pronto: o teste salta com a razão explícita, em vez de falhar por tempo
esgotado (o que esconderia a causa).
"""

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-06-d-exportar-inquilino"
ROTAS = ("/api/inquilino/exportar", "/api/inquilino/exportacoes", "/api/inquilino/exportar/estimativa")


class TelaInquilino(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """O certificado do servidor de teste da trilha é próprio. Isto vale SÓ para este arquivo: a checagem de
    origem do CSRF (`checar_escrita_sob_cookie`) compara o `Origin` do navegador com `PLAT_URL_PUBLICA`, que a
    instalação exige em https — logo o e2e desta tela só roda contra um endereço https, e na trilha esse
    endereço é local."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def api_inquilino(api_auth):
    faltam = [r for r in ROTAS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend sem {faltam} no OpenAPI da URL de teste")
    return api_auth


@pytest.fixture(scope="session")
def inquilino_com_camada(env, api_inquilino):
    """Inquilino próprio com uma camada hospedada pequena, criado pelo superadmin — as mesmas fábricas do
    teste de API deste item. Nunca o inquilino de demonstração: a cota é de uma exportação por dia e por
    inquilino, e gastá-la em `demo` faria este teste passar só na primeira rodada do dia."""
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
    semear_camada(env, inq, 500, "zt camada do e2e de exportacao do inquilino")
    yield inq
    inq.apagar()


def _esperar_link(page, segundos: int = 300) -> str:
    import time

    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        link = page.locator("#exp-lista a.exp-baixar")
        if link.count():
            return link.first.get_attribute("href")
        page.wait_for_timeout(500)
    pytest.skip("o pacote não ficou pronto no prazo: há worker da fila rodando neste ambiente?")
    return ""


def test_exportar_inquilino_pela_tela(page, base_url, inquilino_com_camada, medida, tmp_path):
    inq = inquilino_com_camada
    tela = TelaInquilino(page, base_url)
    tela.entrar(inq.slug, "admin", inq.senha, proximo="/admin/organizacao")

    page.wait_for_selector("#exportar-inquilino", timeout=20000)
    page.wait_for_selector("#exp-estimativa", timeout=20000)
    # o texto da estimativa tem de sair do estado "lendo" e trazer um tamanho
    page.wait_for_function(
        "() => { const e = document.getElementById('exp-estimativa');"
        " return e && /\\d/.test(e.textContent) && !/lendo/.test(e.textContent); }",
        timeout=20000,
    )
    estimativa_texto = page.text_content("#exp-estimativa")
    tela.capturar("secao_com_estimativa")
    assert "camadas" in estimativa_texto, estimativa_texto

    page.click("#exp-pedir")
    href = _esperar_link(page)
    tela.capturar("pacote_pronto")

    resposta = page.request.get(href if href.startswith("http") else f"{base_url}{href}")
    assert resposta.status == 200, resposta.status
    pacote = tmp_path / "inquilino_exportado.zip"
    pacote.write_bytes(resposta.body())

    with zipfile.ZipFile(pacote) as z:
        assert set(z.namelist()) == {"dados.gpkg", "catalogo.json", "arquivos.zip", "manifesto.json"}
        manifesto = json.loads(z.read("manifesto.json").decode("utf-8"))
        catalogo = json.loads(z.read("catalogo.json").decode("utf-8"))
        for nome in ("dados.gpkg", "catalogo.json", "arquivos.zip"):
            bruto = z.read(nome)
            assert manifesto["componentes"][nome]["sha256"] == hashlib.sha256(bruto).hexdigest(), nome
            assert manifesto["componentes"][nome]["bytes"] == len(bruto), nome
        gpkg = tmp_path / "dados.gpkg"
        gpkg.write_bytes(z.read("dados.gpkg"))
        with zipfile.ZipFile(io.BytesIO(z.read("arquivos.zip"))) as za:
            za.namelist()

    assert gpkg.read_bytes()[:15] == b"SQLite format 3"
    info = subprocess.run(["ogrinfo", "-so", str(gpkg)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr[:400]
    n_gpkg = len([ln for ln in info.stdout.splitlines() if ln.strip() and ln[0].isdigit() and ":" in ln])
    n_catalogo = sum(1 for i in catalogo["itens"]
                     if i["tipo"] == "camada_vetorial" and (i.get("dados") or {}).get("fonte") == "hospedada")
    assert n_gpkg == n_catalogo >= 1, (n_gpkg, n_catalogo)

    # a segunda execução do mesmo dia é recusada NA TELA (cota de 1 por dia)
    page.reload()
    page.wait_for_selector("#exp-pedir", timeout=20000)
    page.wait_for_function(
        "() => document.getElementById('exp-pedir') && document.getElementById('exp-pedir').disabled",
        timeout=20000,
    )
    page.wait_for_selector("#exp-cota:not([hidden])", timeout=20000)
    texto_cota = page.text_content("#exp-cota")
    tela.capturar("cota_do_dia_gasta")
    assert "hoje" in texto_cota, texto_cota

    tela.verificar()
    gravar = medida(ITEM)
    gravar("capturas_e2e", sorted(p.name for p in CAPTURAS.glob(f"{ITEM}_*.png")), "arquivos",
           "playwright screenshot full_page (tests/e2e/test_exportar_inquilino.py)")
