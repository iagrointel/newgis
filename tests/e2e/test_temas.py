"""e2e do item L5-10-temas-marca: a marca (tema) em vigor nas telas.

O portão do item, cláusula a cláusula (o que é de TELA está aqui; o cálculo dos 10 pares de contraste
e a recusa de injeção por FORMATO têm suíte unitária e de API próprias):

1. trocar tema NÃO recarrega a página — marcador em `window` sobrevive à troca no seletor flutuante e
   `performance` registra uma única navegação;
2. tema com contraste abaixo de 4,5:1 mostra aviso na tela (tabela calculada no navegador) e o tema
   gravado volta do servidor COM os avisos;
3. app publicado HERDA o tema do inquilino e o `corpo.tema` do documento SOBREPÕE (medido pelo token
   `--t-espacamento-grande`, distinto em cada tema da prova: inquilino 33px, prado 26px, lâmina 28px);
4. tema exportável/importável como JSON (ida e volta fiel no campo JSON do editor);
5. documento sem tema nenhum renderiza com o padrão da plataforma.

Refutação do adversário no mesmo arquivo: importa JSON com `url(javascript:…)` no editor (o editor
aceita importar — quem valida é o servidor) e grava; o PUT volta 422 `tema_invalido`, o aviso na tela
nomeia a recusa e o tema do inquilino permanece o anterior (nada foi gravado).

Como a app não serve /static/ sozinha (o nginx fica na frente) e este e2e precisa do CÓDIGO DESTE
worktree, roda como o `make homolog` roda o seu: backend deste worktree no ar antes do pytest (uvicorn
na porta 8680-8689, reservada da linha L5, com o ambiente da trilha) e `--base-url` apontando para ele:

    source /home/dev/plataforma/laco/var/trilha/swl510.env
    venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8687 --no-access-log &
    venv/bin/pytest tests/e2e/test_temas.py -m lento --base-url http://127.0.0.1:8687

`/static/**` é cumprido pelo próprio teste com os arquivos do `web/` DESTE worktree via `page.route` —
a mesma árvore que o teste valida, sem nginx novo e sem tocar configuração de serviço.
"""

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-10-temas-marca"
RAIZ = Path(__file__).resolve().parents[2]

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


def _tema_do_inquilino() -> dict:
    """Tema completo, sem aviso de contraste, com `espacamento.grande` = 33px (o token-distintivo da prova:
    nenhum padrão da casa usa 33px)."""
    return {
        "claro": {
            "cores": {
                "fundo": "#eef1f0", "superficie": "#ffffff", "texto": "#12181a",
                "texto_suave": "#4d5b57", "acento": "#8f4f10", "texto_sobre_acento": "#fff6ec",
                "borda": "#ccd4d1", "sucesso": "#2f7a4c", "erro": "#a83c2e",
            },
            "espacamento": {"grande": "33px"},
        },
    }


def _tema_baixo_contraste() -> dict:
    """Mesma estrutura com `texto` cinza médio: fica abaixo de 4,5:1 sobre fundo e superfície."""
    tema = _tema_do_inquilino()
    tema["claro"]["cores"]["texto"] = "#8a8a8a"
    return tema


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    primeiro = secrets.choice("01234567")
    resto = "".join(secrets.choice(_CROCKFORD) for _ in range(25))
    return primeiro + resto


def _corpo_um_texto() -> dict:
    """Documento de app mínimo com UMA página e um texto (o executor precisa de página inicial para render)."""
    pagina = _ulid()
    texto = _ulid()
    return {
        "nos": [
            {"id": pagina, "tipo": "pagina", "pai": None, "largura_colunas": 12,
             "propriedades": {"titulo": "Inicial", "caminho": "inicial", "tipo_pagina": "rolavel",
                              "ordem": 0, "oculta": False, "inicial": True}},
            {"id": texto, "tipo": "texto", "pai": pagina, "largura_colunas": 12,
             "propriedades": {"texto": "Corpo de prova do tema", "nivel": "corpo"}},
        ],
        "ligacoes": [],
    }


def _criar_app(api_admin, titulo: str, tema) -> str:
    corpo = _corpo_um_texto()
    if tema is not None:
        corpo["tema"] = tema
    r = api_admin.post(
        "/api/itens",
        data=json.dumps({"tipo": "app", "titulo": titulo,
                         "dados": {"tipo": "app", "esquema_versao": 3, "corpo": corpo}}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


# ---------------------------------------------------------------- /static deste worktree

@pytest.fixture
def servir_estaticos(page):
    """Cumpre `/static/**` com os arquivos do `web/` DESTE worktree (a app não serve estáticos sozinha;
    o nginx que faria isso serve a árvore mesclada, não a deste teste). Recurso ausente = 404 cumprido,
    que o `Tela.verificar()` acusa como qualquer outro.

    Como a página aqui nasce em `http://127.0.0.1:<porta>` (não há nginx declarando a origem da casa), as
    escritas do navegador levam Origin com a porta do banco de prova e a checagem CSRF (ADR 0002 seção
    5.3) devolveria 403 `origem_invalida`. Nas requisições da PÁGINA a `PUT /api/org/tema` o Origin é
    reescrito para PLAT_URL_PUBLICA do ambiente — exatamente o valor que a página carregada do domínio da
    plataforma teria em produção (o contexto `playwright.request` de preparação não envia Origin e não
    precisa disso)."""
    raiz_web = (RAIZ / "web").resolve()
    url_publica = os.environ.get("PLAT_URL_PUBLICA", "")

    def cumprir(route):
        caminho = urlparse(route.request.url).path
        arquivo = (raiz_web / caminho[len("/static/"):]).resolve()
        if not str(arquivo).startswith(str(raiz_web)) or not arquivo.is_file():
            route.fulfill(status=404, content_type="text/plain", body="estático não está no worktree")
            return
        route.fulfill(status=200, body=arquivo.read_bytes(),
                      content_type=CONTENT_TYPES.get(arquivo.suffix, "application/octet-stream"))

    def com_origem_da_casa(route):
        # `continue_` não substitui Origin (medido); `fetch` com o cabeçalho reescrito sim, e a resposta
        # volta para a página por `fulfill(response=...)` (status, corpo e cabeçalhos originais).
        cabecalhos = {**route.request.headers}
        if url_publica:
            cabecalhos["origin"] = url_publica
        route.fulfill(response=route.fetch(headers=cabecalhos))

    page.route("**/static/**", cumprir)
    page.route("**/api/org/tema", com_origem_da_casa)
    # o navegador pede /favicon.ico por conta própria; a app não responde por ele e o 404 não é do item
    page.route("**/favicon.ico", lambda route: route.fulfill(status=200, content_type="image/x-icon", body=b""))
    yield


@pytest.fixture
def api_admin(playwright, base_url, credenciais_demo):
    """Contexto de API autenticado como admin de demo contra o backend do teste; no fim, remove o tema do
    inquilino para a prova seguinte começar sem marca."""
    slug, login, senha = credenciais_demo
    ctx = playwright.request.new_context(base_url=base_url)
    r = ctx.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha})
    assert r.status == 200 and r.json().get("ok") is True, (r.status, r.text())
    yield ctx
    ctx.put("/api/org/tema", data=json.dumps({"tema": None}), headers={"Content-Type": "application/json"})
    ctx.dispose()


def _tema_visto(page) -> dict:
    return page.evaluate(
        """() => {
            const raiz = document.getElementById('raiz-execucao');
            return {
                grande: getComputedStyle(raiz).getPropertyValue('--t-espacamento-grande').trim(),
                origem: raiz.dataset.temaOrigem || null,
            };
        }"""
    )


# ---------------------------------------------------------------- cláusulas 1, 3 e 5 na tela do app

def test_app_herda_inquilino_documento_sobrepoe_e_troca_sem_recarga(
    page, base_url, credenciais_demo, api_admin, servir_estaticos
):
    slug, login, senha = credenciais_demo
    r = api_admin.put("/api/org/tema", data=json.dumps({"tema": _tema_do_inquilino()}),
                      headers={"Content-Type": "application/json"})
    assert r.status == 200, r.text()
    sem_tema = _criar_app(api_admin, f"zt-tema-herda-{sufixo()}", None)
    com_tema = _criar_app(api_admin, f"zt-tema-prado-{sufixo()}", {"id": "prado"})

    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)

    # cláusula 3, primeira metade: app SEM tema herda o tema do inquilino (33px, origem declarada)
    tela.ir(f"/executar?item={sem_tema}")
    page.wait_for_selector('[data-papel="seletor-tema"]', timeout=15000)
    assert _tema_visto(page) == {"grande": "33px", "origem": "inquilino"}

    # cláusula 1: trocar tema no seletor flutuante NÃO recarrega a página
    page.evaluate("() => { window.__plat_e2e_tema = 42; }")
    page.select_option('[data-papel="seletor-tema"]', "tema-lamina")
    page.wait_for_function(
        "() => document.getElementById('raiz-execucao').dataset.temaOrigem === 'seletor'", timeout=5000
    )
    assert _tema_visto(page) == {"grande": "28px", "origem": "seletor"}
    prova = page.evaluate(
        "() => ({ marca: window.__plat_e2e_tema, nave: performance.getEntriesByType('navigation').length })"
    )
    assert prova == {"marca": 42, "nave": 1}, prova

    # voltar a "seguir o documento" re-resolve a cadeia (cai de novo no inquilino), ainda sem recarregar
    page.select_option('[data-papel="seletor-tema"]', "")
    page.wait_for_function(
        "() => document.getElementById('raiz-execucao').dataset.temaOrigem === 'inquilino'", timeout=5000
    )
    assert _tema_visto(page)["grande"] == "33px"

    # cláusula 3, segunda metade: o documento SOBREPÕE o inquilino (prado = 26px vence os 33px)
    tela.ir(f"/executar?item={com_tema}")
    page.wait_for_selector('[data-papel="seletor-tema"]', timeout=15000)
    assert _tema_visto(page) == {"grande": "26px", "origem": "documento"}

    # cláusula 5: sem tema de inquilino e sem tema no documento → padrão da plataforma (24px)
    r = api_admin.put("/api/org/tema", data=json.dumps({"tema": None}),
                      headers={"Content-Type": "application/json"})
    assert r.status == 200, r.text()
    tela.ir(f"/executar?item={sem_tema}")
    page.wait_for_selector('[data-papel="seletor-tema"]', timeout=15000)
    assert _tema_visto(page) == {"grande": "24px", "origem": "padrao"}

    tela.verificar()


# ---------------------------------------------------------------- cláusulas 2 e 4 + refutação no editor

def test_editor_calcula_contraste_avisa_exporta_e_recusa_injecao(
    page, base_url, credenciais_demo, api_admin, servir_estaticos
):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/temas")

    # cláusula 4: importa JSON, exporta de volta — ida e volta fiel
    tema = _tema_baixo_contraste()
    page.fill("#json", json.dumps(tema))
    page.click("#importar")
    page.wait_for_selector("#contraste-saida table", timeout=5000)
    page.click("#exportar")
    assert json.loads(page.input_value("#json")) == tema

    # cláusula 2: o editor calcula os pares no navegador e mostra o aviso dos que ficam abaixo de 4,5:1
    abaixo = page.locator("#contraste-saida .tema-par-aviso")
    assert abaixo.count() >= 3  # texto/fundo, texto/superficie e texto_suave/fundo, no mínimo
    resumo = (page.locator("#contraste-saida p.tema-par-aviso").text_content() or "").strip()
    assert "abaixo de 4,5:1" in resumo, resumo

    # gravar no inquilino: o tema é ACEITO e o aviso o acompanha no servidor (GET /api/temas)
    page.click("#inquilino-salvar")
    page.wait_for_function(
        "() => (document.getElementById('inquilino-aviso').textContent || '').includes('aviso')", timeout=5000
    )
    corpo = api_admin.get("/api/temas").json()
    assert corpo["inquilino"]["tema"] == tema
    assert len(corpo["inquilino"]["avisos"]) >= 1

    # refutação: o adversário importa JSON com injeção (o editor aceita importar — quem valida é o
    # servidor) e grava: 422 tema_invalido, aviso na tela e o tema do inquilino permanece o anterior
    injetado = _tema_do_inquilino()
    injetado["claro"]["cores"]["fundo"] = "url(javascript:alert(1))"
    page.fill("#json", json.dumps(injetado))
    page.click("#importar")
    page.wait_for_function(
        "() => document.getElementById('json').value.includes('url(javascript:')", timeout=5000
    )
    tela.esperar_status(422)
    page.click("#inquilino-salvar")
    page.wait_for_function(
        "() => (document.getElementById('inquilino-aviso').textContent || '').includes('recusou')", timeout=5000
    )
    corpo = api_admin.get("/api/temas").json()
    assert corpo["inquilino"]["tema"] == tema, "a injeção não pode substituir o tema em vigor"
    assert "url(javascript:" not in json.dumps(corpo["inquilino"]["tema"])

    tela.verificar()
