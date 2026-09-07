"""e2e /status (item L0-06-e-status): a página abre no navegador SEM sessão, mostra os serviços, o histórico,
os números e o log de correções, e o cabeçalho da resposta traz X-Robots-Tag noindex. Captura em
tests/e2e/capturas/L0-06-e-status_pagina.png."""

import mimetypes
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

WEB = Path(__file__).resolve().parents[2] / "web"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
ITEM = "L0-06-e-status"


@pytest.fixture(autouse=True)
def estatico_do_disco(page):
    """Em produção o nginx serve /static/ direto do disco (a aplicação não serve estático). Contra o uvicorn da
    trilha esse pedaço não existe, então o próprio navegador é apontado para os MESMOS arquivos do repositório:
    o JS e o CSS que rodam aqui são os que serão publicados, não um substituto."""

    def servir(route, request):
        caminho = WEB / request.url.split("/static/", 1)[1].split("?")[0]
        if caminho.is_file() and WEB in caminho.resolve().parents:
            tipo = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
            route.fulfill(status=200, body=caminho.read_bytes(), content_type=tipo)
        else:
            route.fulfill(status=404, body=b"")

    page.route("**/static/**", servir)


def test_status_abre_sem_sessao_com_todos_os_campos(page, base_url):
    tela = Tela(page, base_url)
    tela.ir("/status")
    page.wait_for_selector("#tabela-servicos tbody tr", timeout=15000)

    servicos = page.eval_on_selector_all(
        "#tabela-servicos tbody tr td:first-child", "els => els.map(e => e.textContent)"
    )
    assert set(servicos) == {"api", "banco", "worker", "martin", "titiler", "garage"}, servicos
    assert page.locator("#numeros dt").count() >= 10
    assert "estado geral" in page.inner_text("#geral-texto")
    assert page.inner_text("#rodape").startswith("retrato de ")
    assert page.locator("#correcoes li").count() >= 1
    assert page.locator("form").count() == 0

    r = page.request.get(f"{base_url}/status")
    assert r.status == 200 and r.headers.get("x-robots-tag", "").startswith("noindex")
    j = page.request.get(f"{base_url}/api/status")
    assert j.status in (200, 503) and j.headers.get("x-robots-tag", "").startswith("noindex")
    corpo = j.json()
    for campo in ("servicos", "fila", "migracoes", "backup", "ensaio_restauracao", "disco", "bucket",
                  "certificado", "historico", "disponibilidade_mes", "correcoes"):
        assert campo in corpo, campo

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_pagina.png"), full_page=True)
