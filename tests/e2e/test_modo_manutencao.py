"""e2e playwright da faixa do modo de manutenção (item L7-33-modo-somente-leitura) contra a URL interna:
liga o modo GLOBAL pela CLI (`scripts/plat`, role do worker — a mesma usada pelos testes de API), abre
`/entrar` (a tela que qualquer um vê, mesmo sem sessão) e prova que a faixa aparece com o motivo; desliga
e prova que ela some. Captura em tests/e2e/capturas/L7-33-modo-somente-leitura_*.png; 0 erro de console.

P1 do laço (funciona no navegador, com captura) fechado por este arquivo — as demais cláusulas do portão
(bloqueio de escrita, job pendente/rodando, CLI/trilha, refutação do OpenAPI) estão em
tests/api/jobs/test_modo_manutencao.py, que não abre navegador."""

import os
import subprocess
import time
from pathlib import Path

import pytest

CAPTURAS = Path(__file__).resolve().parent / "capturas"
RAIZ = Path(__file__).resolve().parents[2]
PLAT = RAIZ / "scripts" / "plat"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _plat(*args: str) -> None:
    r = subprocess.run([str(PLAT), *args], cwd=RAIZ, env=os.environ.copy(),
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, f"plat {' '.join(args)} falhou: {r.stderr}"


def test_faixa_aparece_ligado_e_some_desligado(page, base_url, url_publica_resolve, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    erros = []
    page.on("console", lambda m: erros.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    motivo = "e2e L7-33: prova de faixa no navegador"
    try:
        _plat("modo", "ligar", "--motivo", motivo, "--retry-after", "5")

        t0 = time.perf_counter()
        page.goto("/entrar", wait_until="domcontentloaded")
        page.wait_for_selector("#faixa-modo", timeout=15000)
        ligada_ms = round((time.perf_counter() - t0) * 1000, 1)

        texto = page.text_content("#faixa-modo")
        assert motivo in texto, texto
        assert page.is_visible("#faixa-modo")

        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / "L7-33-modo-somente-leitura_ligado.png"), full_page=True)
    finally:
        _plat("modo", "desligar", "--motivo", "e2e L7-33: fim da prova")

    page.goto("/entrar", wait_until="domcontentloaded")
    page.wait_for_selector("body", timeout=15000)
    page.wait_for_function("() => document.getElementById('faixa-modo') === null", timeout=15000)
    page.screenshot(path=str(CAPTURAS / "L7-33-modo-somente-leitura_desligado.png"), full_page=True)

    assert erros == [], erros

    gravar = medida("L7-33-modo-somente-leitura")
    gravar("faixa_visivel_apos_goto_ms", ligada_ms, "ms",
           "goto('/entrar') até #faixa-modo visível, com o modo global ligado, no chromium do playwright")
