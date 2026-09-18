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

from tests.e2e.apoio import Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-01-k-desenho-anotacoes"
HTML_CRU = "<b>não interpretar</b>"


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
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def _camada_ligada(page) -> str:
    """Liga a primeira camada servível da bancada e devolve o id — a anotação é sempre de uma FEIÇÃO de
    camada, então sem camada não há alvo (o teste salta dizendo isso, em vez de falhar por seletor)."""
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas', { foco: false })")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    ids = page.evaluate(
        "() => window.plat.mapa.catalogo.disponiveis.filter(f => f.servivel).map(f => f.id)"
    )
    if not ids:
        pytest.skip("nenhuma camada servível nesta base: sem feição, não há alvo de anotação")
    page.evaluate("(id) => window.plat.mapa.catalogo.ligar(id)", ids[0])
    return ids[0]


def _abrir_anotacoes(page, camada_id: str, fid: str) -> None:
    """Abre o painel no alvo pela API DA TELA (`painel.abrir`), o mesmo caminho que o clique no mapa usa —
    clicar no pixel exato de uma feição da bancada seria sorteio, e o que se mede aqui é a persistência."""
    page.evaluate("() => window.plat.mapa.abrirPainel('anotacoes', { foco: false })")
    page.evaluate("([c, f]) => window.plat.mapa.painelAnotacoes.abrir(c, f)", [camada_id, fid])
    page.wait_for_function(
        "() => { const e = document.querySelector('#anotacoes-estado'); "
        "return !e.hidden ? e.getAttribute('tipo') !== 'carregando' : true; }",
        timeout=15000,
    )


def _desenhar_ponto(page) -> None:
    page.evaluate("() => window.plat.mapa.abrirPainel('desenho', { foco: false })")
    page.click('[data-desenho="ponto"]')
    canvas = page.locator("#mapa canvas")
    caixa = canvas.bounding_box()
    page.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    page.wait_for_timeout(250)


@pytest.mark.xfail(
    strict=True,
    reason="MEDIDO 17/09 em master: a tela /mapa NÃO tem os painéis. `web/mapa.html` tem 55 linhas e carrega "
           "só `web/js/mapa/mapa.js` (133 linhas, item L2-01-a, mapa-base PMTiles); `web/js/mapa/desenho.js` e "
           "`web/js/mapa/anotacoes.js` existem no repositório mas NINGUÉM os importa, e não há "
           "`window.plat.mapa`/`abrirPainel`. Por isso este e2e — e os vizinhos test_l201k_desenho.py e "
           "test_ux23_selecao_anotacoes_pacote.py, que erram do mesmo jeito — não medem nada hoje. O xfail é "
           "estrito de propósito: no dia em que a tela ganhar os painéis, ele vira FALHA e a marca sai.",
)
def test_anotacao_e_desenho_voltam_depois_de_recarregar_a_pagina(mapa, page, base_url):
    assert page.evaluate("() => !!(window.plat && window.plat.mapa && window.plat.mapa.abrirPainel)"), (
        "a tela /mapa não expõe window.plat.mapa.abrirPainel: sem painel de desenho/anotação não há o que medir"
    )
    camada_id = _camada_ligada(page)
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
    page.wait_for_function("window.plat.mapa.mapaId", timeout=15000)
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
        page.wait_for_function(
            "() => window.plat && window.plat.mapa && window.plat.mapa.desenho.lista().length > 0",
            timeout=20000,
        )
        desenho_depois = page.evaluate("JSON.stringify(window.plat.mapa.desenho.lista())")
        assert desenho_depois == desenho_antes, "o desenho salvo não voltou igual ao reabrir o mapa"

        _abrir_anotacoes(page, camada_id, fid)
        item = page.locator(f"#lista-anotacoes li[data-anotacao='{anotacao_id}']")
        item.wait_for(timeout=15000)
        assert texto in (item.text_content() or ""), item.text_content()
        # o HTML digitado é TEXTO, nunca marcação: nenhum <b> foi criado dentro da anotação
        assert item.locator("b").count() == 0
        mapa.capturar("anotacao_reaberta")

        # --- par negativo: apagada, não volta
        page.once("dialog", lambda d: d.accept())
        item.locator("[data-acao='apagar']").click()
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
