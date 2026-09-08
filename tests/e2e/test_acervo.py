"""e2e da tela /acervo (item L6-01-c-tela-acervo): o equivalente do Living Atlas sobre o acervo da casa.

Percorre o caminho inteiro pela tela, no navegador: filtro por domínio, busca por nome/órgão, cartão, ficha
completa, "adicionar ao meu mapa" e, em /mapa, a legenda com a atribuição obrigatória da licença. Também conta,
contra o banco, quantas fontes de "unidades de conservação" existem e quantas a tela mostra — a resposta certa
hoje é 5 e 0, porque nenhuma delas tem licença escrita (regra D17; item L6-01-g).

Servidor: uvicorn desta trilha (--base-url http://127.0.0.1:<porta>). A app NÃO serve /static/ (isso é do nginx
em produção, ver deploy/nginx.conf), então o contexto do navegador atende /static/ com os arquivos de web/ deste
worktree — é justamente o código deste item que se quer medir, e não o de produção.
"""

import mimetypes
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela

ITEM = "L6-01-c-tela-acervo"
WEB = (RAIZ / "web").resolve()

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

# `plat.acervo_licenca` (item L6-01-g) só é povoada por scripts/acervo_licenca_sync.py rodando como postgres, sem
# olhar PLAT_SCHEMA — em base de trilha ela nasce vazia. A linha semeada aqui é a MESMA que existe em produção
# para 'openstreetmap' (tipo ODbL, evidência real da página de copyright da OpenStreetMap Foundation): não se
# inventa licença nenhuma, reproduz-se o que a curadoria por HTTP já confirmou.
SEMENTE_ODBL = (
    "INSERT INTO {schema}.acervo_licenca"
    "(fonte_id, tipo, url_licenca, metodo, identificador_remoto, http_status, evidencia, confianca, verificado_em) "
    "VALUES ('openstreetmap', 'ODbL', 'https://www.openstreetmap.org/copyright', 'html_regex', NULL, 200, "
    "'<h3>OpenStreetMap licensing</h3> licenciado sob a Open Data Commons Open Database License (ODbL)', "
    "'página oficial de copyright/licença da OpenStreetMap Foundation.', now()) "
    "ON CONFLICT (fonte_id) DO NOTHING"
)


def _capturar(page, nome: str) -> Path:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_{nome}.png"
    page.screenshot(path=str(caminho), full_page=True)
    return caminho


def _psql(sql: str) -> str:
    r = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
         "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return r.stdout.strip()


@pytest.fixture
def licenca_curada_odbl(env):
    schema = env["PLAT_SCHEMA"]
    _psql(SEMENTE_ODBL.format(schema=schema))
    yield "openstreetmap"
    _psql(f"DELETE FROM {schema}.acervo_licenca WHERE fonte_id='openstreetmap'")


@pytest.fixture
def estatico_do_worktree(context):
    """/static/ atendido com os arquivos de web/ DESTE worktree (a app não serve estático; em produção é o nginx).
    Caminho normalizado e preso a web/: um ../ na URL devolve 404, nunca um arquivo de fora."""
    def rota(route, request):
        rel = unquote(urlparse(request.url).path)[len("/static/"):]
        alvo = (WEB / rel).resolve()
        if not str(alvo).startswith(str(WEB) + "/") or not alvo.is_file():
            route.fulfill(status=404, body="")
            return
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if alvo.suffix == ".js":
            tipo = "text/javascript"
        bytes_ = alvo.read_bytes()
        # o mapa-base é PMTiles: a biblioteca só lê por faixa de bytes (Range). Sem 206 aqui o mapa nunca
        # dispara 'load' e a tela /mapa não fica pronta — o nginx de produção faz exatamente isto.
        faixa = re.match(r"bytes=(\d+)-(\d*)", request.headers.get("range", "") or "")
        if faixa:
            ini = int(faixa.group(1))
            fim = int(faixa.group(2)) if faixa.group(2) else len(bytes_) - 1
            fim = min(fim, len(bytes_) - 1)
            pedaco = bytes_[ini:fim + 1]
            route.fulfill(status=206, body=pedaco, content_type=tipo, headers={
                "content-range": f"bytes {ini}-{fim}/{len(bytes_)}",
                "accept-ranges": "bytes",
                "content-length": str(len(pedaco)),
            })
            return
        route.fulfill(body=bytes_, content_type=tipo, headers={"accept-ranges": "bytes"})

    context.route("**/static/**", rota)
    yield
    context.unroute("**/static/**")


@pytest.fixture
def itens_criados(admin_api):
    ids: list[str] = []
    yield ids
    for iid in ids:
        admin_api.delete(f"/api/itens/{iid}")


def test_acervo_da_tela_ao_mapa(page, base_url, credenciais_demo, admin_api, env, medida,
                                estatico_do_worktree, licenca_curada_odbl, itens_criados):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)

    # ---------------------------------------------------------------- 1. a tela abre e lista o acervo visível
    tela.ir("/acervo", "pagina_pronta_ms_acervo")
    page.wait_for_selector("#grade .acervo-cartao")
    dominios_na_tela = page.locator("#dominio-filtro option").count() - 1  # menos a opção "todos os domínios"
    dominios_no_banco = int(_psql("SELECT count(DISTINCT dominio) FROM acervo.fonte"))
    assert dominios_na_tela == dominios_no_banco, (dominios_na_tela, dominios_no_banco)

    # ------------------------------------- 2. camada sem licença curada não aparece: a contagem contra o banco
    #    "unidades de conservação" existe no acervo (5 fontes) e NENHUMA tem licença escrita -> 0 na tela.
    uc_no_banco = int(_psql(
        "SELECT count(*) FROM acervo.fonte WHERE nome ILIKE '%unidades de conserva%'"
    ))
    uc_com_licenca = int(_psql(
        "SELECT count(*) FROM acervo.fonte WHERE nome ILIKE '%unidades de conserva%' "
        "AND licenca IS NOT NULL AND btrim(licenca) <> ''"
    ))
    page.fill("#busca input", "unidades de conservação")
    page.wait_for_function(
        "() => document.getElementById('grade').getAttribute('aria-busy') === 'false'"
        " && document.getElementById('contagem').textContent.trim() !== ''"
    )
    page.wait_for_function(
        "(n) => document.querySelectorAll('#grade .acervo-cartao').length === n", arg=uc_com_licenca
    )
    cartoes_uc = page.locator("#grade .acervo-cartao").count()
    assert cartoes_uc == uc_com_licenca == 0, (cartoes_uc, uc_com_licenca)
    assert uc_no_banco >= 1, uc_no_banco
    # nem o identificador da fonte escondida vaza no HTML da tela
    html = page.content()
    for fonte_id in _psql(
        "SELECT fonte_id FROM acervo.fonte WHERE nome ILIKE '%unidades de conserva%'"
    ).splitlines():
        assert fonte_id.strip() not in html, fonte_id

    # ------------------------------- 3. busca de uma fonte visível, ficha completa e atribuição obrigatória
    page.fill("#busca input", "OpenStreetMap")
    page.wait_for_selector("#grade .acervo-cartao[data-fonte-id='openstreetmap']")
    page.click("#grade .acervo-cartao[data-fonte-id='openstreetmap']")
    page.wait_for_selector("dialog[open] .acervo-ficha")
    ficha = page.text_content("dialog[open] .acervo-ficha")
    assert "ODbL" in ficha, ficha
    atribuicao = page.text_content("dialog[open] .acervo-atribuicao")
    assert "ODbL" in atribuicao and "atribuição obrigatória" in atribuicao.lower(), atribuicao
    captura_ficha = _capturar(page, "ficha")

    # ------------------------------------------------------------------- 4. adicionar ao meu mapa (sem cópia)
    antes = len(admin_api.get("/api/acervo/meu-mapa").json())
    page.click("dialog[open] button[data-id='adicionar']")
    page.wait_for_selector("#acervo-ver-no-mapa")
    camadas = admin_api.get("/api/acervo/meu-mapa").json()
    assert len(camadas) == antes + 1, (antes, camadas)
    novo = [c for c in camadas if c["fonte_id"] == "openstreetmap"]
    assert len(novo) == 1, camadas
    itens_criados.append(novo[0]["item_id"])
    assert novo[0]["licenca_curada_tipo"] == "ODbL", novo[0]
    # sem cópia de dado: o item é uma referência (modo "referenciada" no instantâneo gravado ao adicionar)
    detalhe = admin_api.get(f"/api/itens/{novo[0]['item_id']}").json()
    assert detalhe["dados"]["protocolo"] == "acervo", detalhe["dados"]
    assert detalhe["dados"]["parametros"]["modo"] == "referenciada", detalhe["dados"]

    # ------------------------------------------- 5. ver no mapa: a camada e a atribuição aparecem na legenda
    page.click("#acervo-ver-no-mapa")
    page.wait_for_selector("body[data-pronto='1']")
    assert urlparse(page.url).path == "/mapa", page.url
    page.wait_for_selector("#acervo-legenda:not([hidden]) li[data-fonte-id='openstreetmap']")
    legenda = page.text_content("#acervo-legenda li[data-fonte-id='openstreetmap']")
    assert "OpenStreetMap" in legenda and "ODbL" in legenda, legenda
    assert "atribuição obrigatória" in legenda.lower(), legenda
    captura_mapa = _capturar(page, "legenda_no_mapa")

    # ------------------------------------------------------- 6. responsivo: a mesma tela num visor de celular
    page.set_viewport_size({"width": 390, "height": 844})
    tela.ir("/acervo", "pagina_pronta_ms_acervo_celular")
    page.wait_for_selector("#grade .acervo-cartao")
    largura_corpo = page.evaluate("() => document.body.scrollWidth")
    largura_visor = page.evaluate("() => window.innerWidth")
    assert largura_corpo <= largura_visor + 1, (largura_corpo, largura_visor)
    colunas = page.evaluate(
        "() => getComputedStyle(document.getElementById('grade')).gridTemplateColumns.split(' ').length"
    )
    assert colunas == 1, colunas
    captura_celular = _capturar(page, "celular")
    # e o mapa com a legenda, no mesmo visor: a legenda não pode empurrar a página para fora da tela
    tela.ir("/mapa", "pagina_pronta_ms_mapa_celular")
    page.wait_for_selector("#acervo-legenda:not([hidden]) li[data-fonte-id='openstreetmap']")
    largura_corpo_mapa = page.evaluate("() => document.body.scrollWidth")
    assert largura_corpo_mapa <= largura_visor + 1, (largura_corpo_mapa, largura_visor)
    page.set_viewport_size({"width": 1280, "height": 800})

    # ------------------------------------------------------------- 7. 0 erro de console em todo o percurso
    tela.verificar()

    gravar = medida(ITEM)
    # tempo de tela só vale com a carga da máquina ao lado (regra do laço, 07/09): estes números são
    # informativos — nenhuma cláusula do portão deste item é de desempenho.
    carga = os.getloadavg()[0]
    ram_livre_gb = round(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024 ** 3, 1)
    gravar("carga_1min", round(carga, 2), "media de processos prontos", "os.getloadavg()[0] no fim da rodada")
    gravar("ram_livre_gb", ram_livre_gb, "GB", "SC_AVPHYS_PAGES * SC_PAGE_SIZE no fim da rodada")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/apoio.py Tela.ir)")
    gravar("dominios_no_filtro", dominios_na_tela, "contagem",
           "opções de #dominio-filtro (menos 'todos') == SELECT count(DISTINCT dominio) FROM acervo.fonte")
    gravar("unidades_de_conservacao_no_acervo", uc_no_banco, "contagem",
           "SELECT count(*) FROM acervo.fonte WHERE nome ILIKE '%unidades de conserva%'")
    gravar("unidades_de_conservacao_na_tela", cartoes_uc, "contagem",
           "cartões em #grade após buscar 'unidades de conservação' na tela /acervo")
    gravar("erros_de_console", len(tela.console), "contagem",
           "console.error + pageerror coletados pelo playwright em todo o percurso (tests/e2e/apoio.py Tela)")
    gravar("largura_do_corpo_em_390px", largura_corpo, "px",
           "document.body.scrollWidth da tela /acervo com o visor em 390x844 (sem barra horizontal)")
    gravar("largura_do_corpo_do_mapa_em_390px", largura_corpo_mapa, "px",
           "document.body.scrollWidth da tela /mapa com a legenda do acervo, visor 390x844")
    for nome, caminho in (("captura_ficha", captura_ficha), ("captura_legenda_no_mapa", captura_mapa),
                          ("captura_celular", captura_celular)):
        gravar(nome, caminho.name, "arquivo", f"page.screenshot em tests/e2e/capturas/{caminho.name}")
