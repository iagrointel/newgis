"""e2e /crs (item L2-17-crs-transformacoes): lista curada aparece primeiro nos DOIS seletores (origem e
destino) — checagem ESTRUTURAL do DOM (a máquina não faz captura confiável de tela; regra da casa), 0
erro de console, e um fluxo real de transformação (SAD69 -> SIRGAS2000 na Praça da Sé, dentro da
cobertura da grade) mostra o resultado e qual transformação foi usada."""

from pathlib import Path

import pytest

from app.crs.curada import CURADA
from tests.e2e.apoio import Tela

ITEM = "L2-17-crs-transformacoes"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_pagina_crs_seletores_curada_primeiro(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    ms = tela.ir("/crs", "pagina_pronta_ms_crs")

    page.wait_for_selector("#lista-corpo tr", timeout=20000)
    page.wait_for_function(
        "document.querySelectorAll('#origem option').length > 100", timeout=20000
    )

    epsgs_curados_esperados = [str(e.epsg) for e in CURADA]
    n = len(epsgs_curados_esperados)

    for seletor_id in ("origem", "destino"):
        valores = page.eval_on_selector_all(f"#{seletor_id} option", "els => els.map(e => e.value)")
        assert valores[:n] == epsgs_curados_esperados, (seletor_id, valores[:n])
        # os curados no seletor têm a estrela ★ (mesmo texto que o item pede como "marcados")
        textos = page.eval_on_selector_all(f"#{seletor_id} option", "els => els.map(e => e.textContent)")
        assert all("★" in t for t in textos[:n]), (seletor_id, textos[:n])
        assert not any("★" in t for t in textos[n:n + 5]), (seletor_id, textos[n:n + 5])

    linhas_curadas = page.eval_on_selector_all(
        "#lista-corpo tr", "els => els.map(e => e.dataset.curada)"
    )
    assert linhas_curadas[:n] == ["1"] * n, linhas_curadas[:n]
    assert "0" in linhas_curadas[n:]

    # fluxo real: SAD69 (4618) -> SIRGAS2000 (4674), ponto na Praça da Sé (dentro da cobertura da grade)
    page.select_option("#origem", "4618")
    page.select_option("#destino", "4674")
    page.fill("#lon", "-46.6333")
    page.fill("#lat", "-23.5505")
    page.click("#form-transformar button[type=submit]")
    page.wait_for_selector("#resultado:not([hidden])", timeout=10000)
    transformacao = page.text_content("#resultado-transformacao")
    assert "SAD69" in transformacao, transformacao
    cobertura = page.text_content("#resultado-cobertura")
    assert cobertura.strip() == "dentro_da_grade", cobertura

    tela.verificar()
    medida("L2-17-crs-transformacoes")(
        "pagina_pronta_ms_crs", ms, "ms",
        "playwright chromium contra a URL interna (tests/e2e/test_crs.py)",
    )


def test_pagina_crs_transformacao_fora_da_cobertura_declara_alternativa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/crs")
    page.wait_for_function("document.querySelectorAll('#origem option').length > 100", timeout=20000)

    page.select_option("#origem", "4618")
    page.select_option("#destino", "4674")
    page.fill("#lon", "-58.4")
    page.fill("#lat", "-34.6")
    # fora da grade não é erro: o serviço cai na alternativa e devolve 200 com isso declarado
    page.click("#form-transformar button[type=submit]")
    page.wait_for_selector("#resultado:not([hidden])", timeout=10000)
    cobertura = page.text_content("#resultado-cobertura")
    assert cobertura.strip() == "fora_da_grade_usou_parametros", cobertura
    transformacao = page.text_content("#resultado-transformacao")
    assert "sem grade" in transformacao, transformacao
