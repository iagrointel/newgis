"""e2e playwright (chromium do playwright) contra a URL interna: a página inicial mostra versão e saúde,
0 erro de console, captura em tests/e2e/capturas/L0-01-repo_inicio.png, medida primeira_pintura_ms."""

import re
import time
from pathlib import Path

import pytest

CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_pagina_inicial_mostra_versao_e_saude(page, base_url, url_publica_resolve, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    erros = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    respostas = {}
    page.on("response", lambda r: respostas.setdefault(r.url, r.status))

    t0 = time.perf_counter()
    page.goto("/", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=15000)
    pronto_ms = round((time.perf_counter() - t0) * 1000, 1)

    versao_tela = page.text_content("#versao-numero").strip()
    git_tela = page.text_content("#versao-git").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", versao_tela), versao_tela
    assert re.fullmatch(r"[0-9a-f]{7,12}", git_tela), git_tela
    assert page.text_content("#saude-estado").strip() == "ok"
    assert '"banco": "ok"' in page.text_content("#saude-json")

    api = page.request.get(f"{base_url}/api/versao").json()
    assert api["versao"] == versao_tela and api["git_sha"] == git_tela

    pintura = page.evaluate(
        "() => { const e = performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint');"
        " return e ? e.startTime : null; }"
    )
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / "L0-01-repo_inicio.png"), full_page=True)

    assert erros == [], erros
    ruins = {u: s for u, s in respostas.items() if s >= 400}
    assert ruins == {}, ruins

    gravar = medida("L0-01-repo")
    gravar("pagina_pronta_ms", pronto_ms, "ms", "goto('/') até body[data-pronto=1] no chromium do playwright")
    if pintura is not None:
        gravar("primeira_pintura_ms", round(pintura, 1), "ms",
               "performance.getEntriesByType('paint') first-contentful-paint no chromium do playwright")
