"""Portão do item L2-01-k-desenho-anotacoes, cláusula "anotação ... salva e reaberta", medida PELA TELA.

O que o tronco já tem medido em outro lugar (e por isso NÃO se repete aqui): os 7 tipos de desenho,
o halo do texto, "promover a camada" e o desenho salvo/reaberto idêntico estão em
`tests/e2e/test_l201k_desenho.py`; o ciclo criar/editar/resolver/apagar da ANOTAÇÃO, com os erros
interceptados, está em `tests/e2e/test_ux23_selecao_anotacoes_pacote.py`.

O que faltava e este arquivo mede: a anotação **sobrevive ao recarregamento da página** — ou seja, ela
está no servidor e volta pela tela, não só na memória do navegador daquela sessão. Par obrigatório:

  * positivo — anotação criada, página recarregada do zero, a anotação volta com o texto e o autor;
  * negativo — a anotação apagada NÃO volta depois do mesmo recarregamento (sem isso, uma tela que
    mostrasse qualquer coisa passaria no positivo).

E, no mesmo passo, o desenho feito na tela e salvo volta junto (é o documento do mapa que guarda os
dois), com o texto da anotação tratado como TEXTO: HTML digitado pelo usuário aparece literal, nunca
interpretado.

Como rodar contra uma trilha (nunca contra plat.iagrointel.com, que é produção):

    set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
    venv/bin/python -m uvicorn tests.e2e.frente_estatica:app --port <porta>
    venv/bin/pytest tests/e2e/test_mapa_desenho.py -m lento --base-url http://127.0.0.1:<porta>
"""

from __future__ import annotations

import pytest

from tests.e2e.apoio import Tela, escrita_do_navegador_sem_origin, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-01-k-desenho-anotacoes"
HTML_CRU = "<b>não interpretar</b>"


def _esperar_js(page, expressao, timeout_ms=15000):
    """wait_for_function sem eval na página: a CSP do documento (script-src com nonce, sem unsafe-eval)
    barra o predicado-string do playwright; page.evaluate vai por CDP e não passa pela CSP."""
    import time

    fim = time.monotonic() + timeout_ms / 1000
    while True:
        if page.evaluate(expressao):
            return
        if time.monotonic() > fim:
            raise AssertionError(f"expressão não ficou verdadeira em {timeout_ms} ms: {expressao}")
        time.sleep(0.1)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Numa BASE DE TRILHA o servidor sobe com certificado próprio: a plataforma exige `PLAT_URL_PUBLICA`
    em https (e o CSP manda `upgrade-insecure-requests`, que aborta todo fetch em http). Só o certificado
    é ignorado; nenhuma outra checagem é afrouxada."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture
def mapa(page, base_url, credenciais_demo, api_auth):
    if "/api/anotacoes" not in api_auth:
        pytest.skip("backend sem /api/anotacoes no OpenAPI da URL de teste")
    slug, login, senha = credenciais_demo
    # salvar o desenho e enviar a anotação gravam pelo JS DA PÁGINA; numa bancada de trilha o Origin do
    # navegador nunca é PLAT_URL_PUBLICA (ver apoio.escrita_do_navegador_sem_origin).
    escrita_do_navegador_sem_origin(page)
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def _camada_ligada(page, tela) -> str:
    """Liga a primeira camada servível da bancada e devolve o id — a anotação é sempre de uma FEIÇÃO de
    camada, então sem camada não há alvo (o teste salta dizendo isso, em vez de falhar por seletor).

    O 503 e o 502 dos ladrilhos são DECLARADOS: a trilha não sobe a infra de tiles (PLAT_DSN_LEITOR/Martin,
    item L2-01-b — ver app/tiles/rotas.py), então a camada liga mas não pinta. Sem PLAT_DSN_LEITOR a rota
    responde 503 `leitor_nao_configurado`; quando o Martin existe mas não conhece o schema da trilha, a
    resposta é 502 `martin_indisponivel`/`martin_erro` (app/tiles/martin_cliente.py) — mesma ausência de
    infra, outro código. O que este teste mede é a persistência da anotação (camada_id, fid), que não
    depende do ladrilho chegar."""
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas', { foco: false })")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    ids = page.evaluate(
        "() => window.plat.mapa.catalogo.disponiveis.filter(f => f.servivel).map(f => f.id)"
    )
    if not ids:
        pytest.skip("nenhuma camada servível nesta base: sem feição, não há alvo de anotação")
    tela.esperar_status(502, 503)
    page.evaluate("(id) => window.plat.mapa.catalogo.ligar(id)", ids[0])
    return ids[0]


def _abrir_anotacoes(page, camada_id: str, fid: str) -> None:
    """Abre o painel no alvo pela API DA TELA (`painel.abrir`), o mesmo caminho que o clique no mapa usa —
    clicar no pixel exato de uma feição da bancada seria sorteio, e o que se mede aqui é a persistência."""
    page.evaluate("() => window.plat.mapa.abrirPainel('anotacoes', { foco: false })")
    page.evaluate("([c, f]) => window.plat.mapa.painelAnotacoes.abrir(c, f)", [camada_id, fid])
    _esperar_js(
        page,
        "() => { const e = document.querySelector('#anotacoes-estado'); "
        "return !e.hidden ? e.getAttribute('tipo') !== 'carregando' : true; }",
    )


def _desenhar_ponto(page) -> None:
    page.evaluate("() => window.plat.mapa.abrirPainel('desenho', { foco: false })")
    page.click('[data-desenho="ponto"]')
    canvas = page.locator("#mapa canvas")
    caixa = canvas.bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_timeout(250)


def test_anotacao_e_desenho_voltam_depois_de_recarregar_a_pagina(mapa, page, base_url):
    assert page.evaluate("() => !!(window.plat && window.plat.mapa && window.plat.mapa.abrirPainel)"), (
        "a tela /mapa não expõe window.plat.mapa.abrirPainel: sem painel de desenho/anotação não há o que medir"
    )
    camada_id = _camada_ligada(page, mapa)
    fid = "1"
    s = sufixo()
    texto = f"nota de portao {s} {HTML_CRU}"

    grupo = mapa.api("POST", "/api/grupos", {"nome": f"zt-l201k-{s}"})
    grupo_id = grupo.json().get("id") if grupo.status == 201 else None
    if not grupo_id:
        pytest.skip(f"sem grupo para anotar (POST /api/grupos = {grupo.status}); a anotação exige grupo")

    _desenhar_ponto(page)
    page.evaluate("() => window.plat.mapa.abrirPainel('desenho', { foco: false })")
    page.click("#btn-desenho-salvar")
    _esperar_js(page, "!!window.plat.mapa.mapaId")
    mapa_id = page.evaluate("window.plat.mapa.mapaId")
    desenho_antes = page.evaluate("JSON.stringify(window.plat.mapa.desenho.lista())")

    _abrir_anotacoes(page, camada_id, fid)
    page.wait_for_selector("#anotacao-texto", timeout=15000)
    if page.locator("#btn-anotacao-enviar").is_disabled():
        pytest.skip("usuário de demonstração sem grupo: a anotação exige grupo (RLS de visibilidade)")
    page.fill("#anotacao-texto", texto)
    page.click("#btn-anotacao-enviar")
    page.wait_for_selector(f"#lista-anotacoes li:has-text('nota de portao {s}')", timeout=15000)
    anotacao_id = page.get_attribute("#lista-anotacoes li", "data-anotacao")
    assert anotacao_id

    try:
        # --- recarrega a página do zero: o que voltar veio do servidor
        page.goto(f"{base_url}/mapa?mapa={mapa_id}", wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
        _esperar_js(
            page,
            "() => window.plat && window.plat.mapa && window.plat.mapa.desenho.lista().length > 0",
            timeout_ms=20000,
        )
        desenho_depois = page.evaluate("JSON.stringify(window.plat.mapa.desenho.lista())")
        # a ida e volta pelo servidor reordena as CHAVES do JSON (jsonb); a comparação é do conteúdo
        import json as _json

        def _canonico(txt):
            return sorted(
                ((f["id"], _json.dumps(f["geometry"], sort_keys=True),
                  _json.dumps(f["properties"], sort_keys=True)) for f in _json.loads(txt)),
            )

        assert _canonico(desenho_depois) == _canonico(desenho_antes), (
            "o desenho salvo não voltou igual ao reabrir o mapa"
        )

        _abrir_anotacoes(page, camada_id, fid)
        item = page.locator(f"#lista-anotacoes li[data-anotacao='{anotacao_id}']")
        item.wait_for(timeout=15000)
        assert texto in (item.text_content() or ""), item.text_content()
        # o HTML digitado é TEXTO, nunca marcação: nenhum <b> foi criado dentro da anotação
        assert item.locator("b").count() == 0
        mapa.capturar("anotacao_reaberta")

        # --- par negativo: apagada, não volta (a confirmação é <plat-dialogo>, não dialog nativo)
        item.locator("[data-acao='apagar']").click()
        page.locator("plat-dialogo button[data-id='ok']").click()
        page.wait_for_selector(f"#lista-anotacoes li[data-anotacao='{anotacao_id}']", state="detached",
                               timeout=15000)
        anotacao_id_apagada, anotacao_id = anotacao_id, None

        page.goto(f"{base_url}/mapa?mapa={mapa_id}", wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
        _abrir_anotacoes(page, camada_id, fid)
        page.wait_for_timeout(1500)
        assert page.locator(f"#lista-anotacoes li[data-anotacao='{anotacao_id_apagada}']").count() == 0
    finally:
        if anotacao_id:
            mapa.api("DELETE", f"/api/anotacoes/{anotacao_id}")
        mapa.api("DELETE", f"/api/itens/{mapa_id}")
        mapa.api("DELETE", f"/api/grupos/{grupo_id}")
    mapa.verificar()
