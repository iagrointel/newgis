"""e2e dos 10 exemplos do SDK JavaScript (item L7-08-c-sdk-js): cada página em /static/sdk/exemplos/NN_x.html abre
no Chromium com a CSP estrita da própria página (`default-src 'none'`), o teste chama `window.exemplo.main(url,
inquilino, login, senha)` — o MESMO código do formulário — e exige `data-resultado='ok'`, 0 erro de console, 0
violação de CSP (`securitypolicyviolation`, refutação do item) e 0 resposta >= 400 fora das esperadas (os exemplos
05 e 08 provocam 401/403/404 de propósito). Os dois exemplos de mapa também têm o canvas capturado e conferido
(mais de uma cor = desenhou). Exemplo 06 precisa de um worker da fila vivo (o e2e de produção tem o plat-worker;
em trilha, `venv/bin/python -m app.jobs.worker`). Capturas em tests/e2e/capturas/L7-08-c_*.png."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.test_mapa import _cores_distintas

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L7-08-c-sdk-js"
EXEMPLOS = {
    "01_login": (),
    "02_listar_itens": (),
    "03_criar_atualizar_apagar": (),
    "04_paginacao": (),
    "05_tokens_de_servico": (401,),  # token revogado: 401 token_revogado é a prova
    "06_jobs": (),
    "07_compartilhamento": (),
    "08_erros_e_escopo": (403, 404),  # escopo insuficiente e item inexistente, de propósito
    "09_mapa_extensao": (),
    "10_catalogo_no_mapa": (),
}
COM_MAPA = ("09_mapa_extensao", "10_catalogo_no_mapa")


def _rodar(page, base_url, credenciais, nome, esperados):
    slug, login, senha = credenciais
    tela = Tela(page, base_url)
    tela.esperar_status(*esperados)
    t0 = time.perf_counter()
    page.goto(f"/static/sdk/exemplos/{nome}.html", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    pronto_ms = round((time.perf_counter() - t0) * 1000, 1)
    assert page.get_attribute("body", "data-exemplo") == nome
    t1 = time.perf_counter()
    resultado = page.evaluate(
        "([u, i, l, s]) => window.exemplo.main(u, i, l, s)"
        ".then(r => ({ok: true, r}), e => ({ok: false, e: String(e)}))",
        [base_url, slug, login, senha],
    )
    exemplo_ms = round((time.perf_counter() - t1) * 1000, 1)
    saida = page.text_content("#saida")
    assert resultado["ok"], f"{nome}: {resultado.get('e')}\n{saida}"
    assert page.get_attribute("body", "data-resultado") == "ok", saida
    violacoes = page.evaluate("() => window.exemplo.violacoes")
    assert violacoes == [], f"{nome}: violação de CSP {violacoes}"
    return tela, saida, {"pagina_pronta_ms": pronto_ms, "exemplo_ms": exemplo_ms}


@pytest.mark.parametrize("nome", list(EXEMPLOS))
def test_exemplo_roda_no_navegador_com_csp(page, base_url, credenciais_demo, api_auth, nome, medida):
    tela, saida, tempos = _rodar(page, base_url, credenciais_demo, nome, EXEMPLOS[nome])
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    if nome in COM_MAPA:
        page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
        page.wait_for_timeout(800)
        caminho = CAPTURAS / f"L7-08-c_{nome}.png"
        page.locator("#mapa").screenshot(path=str(caminho))
        cores = _cores_distintas(caminho)
        assert cores > 50, (nome, cores)
        medida(ITEM)(f"cores_na_captura_{nome[:2]}", cores, "contagem", f"PIL getcolors() sobre {caminho.name}")
    else:
        page.screenshot(path=str(CAPTURAS / f"L7-08-c_{nome}.png"), full_page=True)
    tela.verificar()  # 0 erro de console, 0 resposta >= 400 não esperada
    gravar = medida(ITEM)
    for k, v in tempos.items():
        gravar(f"{k}_{nome[:2]}", v, "ms", f"{nome}.html no chromium do playwright (tests/e2e/test_sdk_js.py)")
    assert "revogado" in saida


def test_adversario_token_revogado_tem_mensagem_exata(page, base_url, credenciais_demo, api_auth):
    """Refutação: "usa token revogado e confere a mensagem". A mensagem que o SDK entrega é a da API, sem tradução
    solta: tipo `token_revogado`, status 401, título com o instante da revogação."""
    tela, saida, _ = _rodar(page, base_url, credenciais_demo, "05_tokens_de_servico", (401,))
    linha = next(li for li in saida.splitlines() if li.startswith("token revogado:"))
    assert linha.startswith("token revogado: 401 token_revogado — \"token revogado em "), linha
    tela.verificar()


def test_adversario_csp_bloqueia_script_inline_de_verdade(page, base_url, api_auth):
    """A CSP das páginas de exemplo não é decorativa: um script inline injetado na página é bloqueado e a página
    registra a violação em window.exemplo.violacoes — o mesmo registro que os 10 testes acima exigem vazio."""
    page.goto("/static/sdk/exemplos/01_login.html", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.evaluate(
        "() => { const s = document.createElement('script'); s.textContent = 'window.__vazou = 1'; "
        "document.body.append(s); }"
    )
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__vazou") is None
    violacoes = page.evaluate("() => window.exemplo.violacoes")
    assert violacoes and violacoes[0].startswith("script-src"), violacoes


def test_capturas_dos_dez_exemplos_existem():
    faltam = [n for n in EXEMPLOS if not (Path(CAPTURAS) / f"L7-08-c_{n}.png").exists()]
    assert faltam == [], faltam
