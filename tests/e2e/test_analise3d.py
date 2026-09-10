"""e2e da tela /analise3d (L2-09-d): login pela tela, as QUATRO análises rodadas pelos botões do painel
contra o backend de verdade (visada passa pelo varredor Python; viewshed pelo binário gdal_viewshed),
captura de CADA uma em tests/e2e/capturas/L2-09-d_analise3d_*.png e 0 erro de console.

Cláusula 5 do portão: "e2e com captura de cada" — a captura só existe depois da resposta chegar e ser
pintada (o teste espera o data-analise do painel de saída mudar para a análise pedida)."""

import time
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, credenciais

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L2-09-d-analise-3d-visibilidade"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # o e2e deste item roda contra uvicorn+nginx da TRILHA (127.0.0.1, certificado x509 autoassinado
    # gerado na hora — docs no handoff); o contexto aceita o certificado da casa de teste
    return {**browser_context_args, "ignore_https_errors": True}

# (id do botão no painel, valor de data-analise que o painel de saída assume, nome da captura)
ANALISES = [
    ("bt-visada", "visada", "visada"),
    ("bt-viewshed", "viewshed", "viewshed"),
    ("bt-perfil", "perfil", "perfil"),
    ("bt-sombra", "sombra", "sombra"),
]


def test_analise3d_rodar_as_quatro_e_capturar_cada(page, base_url, url_publica_resolve, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo")

    tela = Tela(page, base_url)
    tela.entrar(*("demo", *cred["demo"]), proximo="/analise3d")
    pagina_ms = tela.ir("/analise3d", "e2e_pagina_ms")
    assert page.text_content("#terreno-resumo").strip(), "terreno de exemplo não foi descrito na página"

    gravar = medida(ITEM)
    gravar("e2e_pagina_pronta_ms", pagina_ms, "ms", "goto('/analise3d') até body[data-pronto=1] no chromium")
    for botao, analise, nome in ANALISES:
        t0 = time.perf_counter()
        page.click(f"#{botao}")
        expressao = (
            "(() => { const s = document.getElementById('saida');"
            " return s && s.dataset.analise === '" + analise + "'; })()"
        )
        page.wait_for_function(expressao, timeout=30000)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        gravar(f"e2e_{analise}_ms", ms, "ms", f"clique em #{botao} até o painel pintar '{analise}'")
        aviso = (page.text_content("#saida-aviso") or "").strip()
        assert aviso == "", f"{analise} deixou aviso na tela: {aviso}"
        titulo = (page.text_content("#saida-titulo") or "").strip()
        assert titulo, f"{analise} sem título no painel de saída"
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_analise3d_{nome}.png"), full_page=True)

    # a última análise (sombra) tem de ter deixado o polígono desenhado no painel
    assert page.query_selector("#saida svg polygon") is not None, "sombra sem polígono no painel"
    tela.verificar()
