"""e2e do item UX-09-ferramentas-e-tarefas, na parte que o tronco sustenta: a tela /ferramentas é o catálogo dos
tipos de tarefa que o backend publica (GET /api/jobs/tipos) com o formulário GERADO do esquema de parâmetros de
cada tipo. As ferramentas GP no vocabulário Esri (L2-05-a) não existem em ramo nenhum e ficam declaradas no handoff.

1. catálogo: cartões por grupo com custo (memória, tempo, pesada, perfil mínimo) e número de parâmetros; busca;
   as de diagnóstico (`prova.*`, `jobs.*`) só aparecem com a caixa ligada; ferramenta inexistente na URL = estado
   nomeado; filtro sem resultado = vazio com "limpar filtros";
2. execução: `prova.progresso` com 4 passos em 2 s → tarefa criada, progresso ao vivo (SSE ou polling), log com
   linhas, estado final "concluído", ligação para /tarefas/<id>; cancelar aparece só enquanto roda;
3. refutação: parâmetro fora do limite (duracao_s 9999 > 3600) é recusado NO NAVEGADOR com o motivo no campo, sem
   chamada; o 422 do servidor (interceptado com a forma [{campo, mensagem}]) volta ao campo certo;
4. estados: catálogo com 500 → erro com "tentar de novo"; visualizador (sem jobs.executar) vê a página "sem
   permissão" do exigirSessao; capturas 390/1280; axe 0 sérias; console limpo; sem chave crua."""

import json
import os
import re
from urllib.parse import urlparse

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-09"
LARGURAS = (390, 1280)
COOKIE = "plat_sessao"
# nomes de tipo de tarefa parecem chaves de dicionário (prefixo.nome); não são texto traduzível
EXTRAS_CRU = frozenset({"prova", "jobs", "catalogo", "conexoes", "exportacao", "ingestao", "uploads", "mapa",
                        "analise", "multiescala", "importacao"})


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(EXTRAS_CRU))
    # nomes de tipo (catalogo.exportar_lista) e de parâmetro com ponto são identificadores, não texto
    cruas = [c for c in cruas if not re.fullmatch(r"[a-z_]+\.[a-z_]+", c)]
    assert cruas == [], cruas


def _entrar(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    return tela


# ---------------------------------------------------------------- 1. catálogo


def test_catalogo_grupos_busca_diagnostico_e_estados(page, base_url, credenciais_demo, api_auth):
    if "/api/jobs/tipos" not in api_auth:
        pytest.skip("backend sem /api/jobs/tipos no OpenAPI")
    tela = _entrar(page, base_url, credenciais_demo)
    tela.ir("/ferramentas")
    page.wait_for_selector("#catalogo-lista:not([hidden]) .ferramenta-cartao", timeout=15000)
    r = tela.api("GET", "/api/jobs/tipos")
    tipos = [t for t in r.json() if not t.get("somente_sistema")]
    visiveis = [t for t in tipos if not (t["nome"].startswith("prova.") or t["nome"].startswith("jobs."))]
    assert page.locator(".ferramenta-cartao").count() == len(visiveis)
    assert page.locator(".ferramenta-cartao[data-tipo^='prova.']").count() == 0
    assert page.locator("#lateral nav a[href='/ferramentas']").count() == 1
    # custo declarado em texto: memória, tempo e perfil mínimo de um tipo conhecido
    cartao = page.locator(".ferramenta-cartao", has=page.locator(".mono", has_text=visiveis[0]["nome"])).first
    ajuda = cartao.locator(".ajuda").text_content() or ""
    assert f"{visiveis[0]['memoria_mb']} MB" in ajuda and "perfil mínimo" in ajuda, ajuda
    _axe(page, "catálogo")
    _sem_chave_crua(page)
    _capturar(page, "catalogo")
    # diagnóstico ligado: os prova.* entram, com marcador
    page.check("#catalogo-diagnostico")
    page.wait_for_selector(".ferramenta-cartao[data-tipo='prova.progresso']")
    assert page.locator(".ferramenta-cartao").count() == len(tipos)
    assert page.locator(".ferramenta-cartao[data-tipo='prova.progresso'] .marcador").count() == 1
    # busca reduz; sem resultado = vazio com "limpar filtros" que devolve tudo
    page.fill("#catalogo-busca input", "progresso")
    page.wait_for_function("() => document.querySelectorAll('.ferramenta-cartao').length === 1", timeout=5000)
    page.fill("#catalogo-busca input", "zzz-nao-existe")
    page.wait_for_selector("#catalogo-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#catalogo-lista").is_hidden()
    _capturar(page, "catalogo_vazio_filtro", larguras=(1280,))
    page.click("#catalogo-estado button")
    page.wait_for_function("(n) => document.querySelectorAll('.ferramenta-cartao').length === n", arg=len(tipos))
    # ferramenta inexistente pela URL: estado nomeado, formulário sem campos
    tela.ir("/ferramentas?tipo=nao.existe")
    page.wait_for_selector("#ferramenta:not([hidden]) #ferramenta-estado[tipo='vazio']:not([hidden])")
    assert "nao.existe" in (page.text_content("#ferramenta-estado") or "")
    assert page.locator("#ferramenta-form input").count() == 0
    _axe(page, "inexistente")
    # catálogo com erro do servidor: estado de erro com "tentar de novo", que recarrega
    page.route(
        "**/api/jobs/tipos",
        lambda r: r.fulfill(
            status=500, content_type="application/json",
            body=json.dumps({"erro": "provocado", "mensagem": "falha provocada", "req_id": "e2e-ux09-ref"}),
        ),
    )
    tela.esperar_status(500)
    tela.ir("/ferramentas")
    page.wait_for_selector("#catalogo-estado[tipo='erro']:not([hidden])")
    assert "e2e-ux09-ref" in (page.text_content("#catalogo-estado") or "")
    assert page.locator("#catalogo-lista").is_hidden()
    _capturar(page, "catalogo_erro", larguras=(1280,))
    page.unroute("**/api/jobs/tipos")
    page.click("#catalogo-estado button")
    page.wait_for_selector("#catalogo-lista:not([hidden]) .ferramenta-cartao", timeout=15000)
    tela.verificar()


# ---------------------------------------------------------------- 2 e 3. execução e refutação


def test_executar_prova_progresso_ao_vivo_e_parametro_recusado(page, base_url, credenciais_demo, api_auth):
    if "/api/jobs/tipos" not in api_auth:
        pytest.skip("backend sem /api/jobs/tipos no OpenAPI")
    tela = _entrar(page, base_url, credenciais_demo)
    tela.ir("/ferramentas?tipo=prova.progresso")
    page.wait_for_selector("#ferramenta:not([hidden]) #ferramenta-form input[name='duracao_s']", timeout=15000)
    assert page.locator(".ferramenta-cartao.selecionada[data-tipo='prova.progresso']").count() == 1
    # o formulário nasce do esquema: limites como atributos, padrão preenchido, ajuda com a descrição
    duracao = page.locator("#ferramenta-form input[name='duracao_s']")
    assert duracao.get_attribute("max") == "3600" and duracao.get_attribute("min") == "0"
    assert duracao.input_value() == "300"
    assert page.locator("#ferramenta-form input[name='passos']").input_value() == "60"
    assert "≤ 3600" in (page.locator("#ferramenta-form .ajuda").first.text_content() or "")
    _axe(page, "formulário gerado")
    _sem_chave_crua(page)
    _capturar(page, "formulario")
    # refutação: fora do limite é recusado no navegador, com o motivo no campo e SEM chamada à API
    chamadas = []
    page.on("request", lambda req: chamadas.append(req.url) if req.method == "POST" and "/api/jobs" in req.url else 0)
    page.fill("#ferramenta-form input[name='duracao_s']", "9999")
    page.click("#ferramenta-form button[type=submit]")
    page.wait_for_selector("#ferramenta-form input[name='duracao_s'][aria-invalid='true']")
    assert "3600" in (page.text_content("#ferramenta-form .erro-campo") or "")
    assert chamadas == []
    _capturar(page, "parametro_recusado", larguras=(1280,))
    # 422 do servidor (forma [{campo, mensagem}] de app/jobs/servico.py) volta ao campo certo
    page.route(
        "**/api/jobs",
        lambda r: r.fulfill(
            status=422, content_type="application/json",
            body=json.dumps({"erro": "parametros_invalidos", "mensagem": "parâmetros inválidos para prova.progresso",
                             "detalhe": [{"campo": "passos", "mensagem": "provocado: passos demais"}],
                             "req_id": "e2e-ux09-422"}),
        ),
    )
    tela.esperar_status(422)
    page.fill("#ferramenta-form input[name='duracao_s']", "2")
    page.click("#ferramenta-form button[type=submit]")
    page.wait_for_selector("#ferramenta-form input[name='passos'][aria-invalid='true']")
    assert "passos demais" in (page.text_content("#ferramenta-form .erro-campo") or "")
    assert page.locator("#execucao").is_hidden()
    page.unroute("**/api/jobs")
    # execução real: 4 passos em 2 s, progresso ao vivo, log, estado final, ligação para a tarefa
    page.fill("#ferramenta-form input[name='passos']", "4")
    page.fill("#ferramenta-form input[name='chave']", f"zt-ux09-{sufixo()}")
    page.click("#ferramenta-form button[type=submit]")
    page.wait_for_selector("#execucao:not([hidden])", timeout=15000)
    href = page.get_attribute("#execucao-tarefa", "href") or ""
    assert href.startswith("/tarefas/"), href
    job_id = href.rsplit("/", 1)[1]
    assert page.locator("#execucao-cancelar:not([hidden])").count() == 1
    page.wait_for_function(
        "() => document.querySelector('#execucao-estado').classList.contains('concluido')", timeout=60000
    )
    assert page.get_attribute("#execucao-progresso", "aria-valuenow") == "100"
    assert page.locator("#execucao-log li").count() >= 1
    assert page.locator("#execucao-cancelar").is_hidden()
    assert page.locator("#execucao-erro").is_hidden()
    j = tela.api("GET", f"/api/jobs/{job_id}").json()
    assert j["estado"] == "concluido" and j["tipo"] == "prova.progresso", j
    _axe(page, "execução concluída")
    _sem_chave_crua(page)
    _capturar(page, "execucao_concluida")
    # o mesmo formulário roda de novo (uma execução por vez no painel; a anterior segue em /tarefas)
    page.fill("#ferramenta-form input[name='duracao_s']", "30")
    page.fill("#ferramenta-form input[name='passos']", "30")
    page.fill("#ferramenta-form input[name='chave']", f"zt-ux09-b-{sufixo()}")
    page.click("#ferramenta-form button[type=submit]")
    page.wait_for_function(
        "(h) => (document.querySelector('#execucao-tarefa').getAttribute('href') || '') !== h", arg=href, timeout=15000
    )
    page.wait_for_selector("#execucao-cancelar:not([hidden])")
    page.click("#execucao-cancelar")
    page.wait_for_selector("plat-dialogo:not([hidden]) button", timeout=5000)
    page.click("plat-dialogo button.perigo, plat-dialogo button.primario")
    page.wait_for_function(
        "() => ['cancelado', 'concluido'].some(c => document.querySelector('#execucao-estado').classList.contains(c))",
        timeout=60000,
    )
    _capturar(page, "execucao_cancelada", larguras=(1280,))
    tela.verificar()


# ---------------------------------------------------------------- 4. visualizador


@pytest.fixture
def cookie_visualizador(credenciais_demo):
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN no ambiente (rode com o .env da trilha carregado)")
    from tests import jobs_sessao

    con = jobs_sessao.conectar(dsn)
    login = f"zt-ux09-vis-{sufixo()}"
    try:
        _, tenant_id, admin_id = jobs_sessao.criar_sessao(con)
        uid = jobs_sessao.criar_usuario_temporario(con, tenant_id, admin_id, login, "visualizador")
        token = jobs_sessao.sessao_de_usuario(con, tenant_id, uid, login)
        con.commit()
        yield token
    finally:
        try:
            jobs_sessao.apagar_usuario_temporario(con, tenant_id, admin_id, login)
            con.commit()
        finally:
            con.close()


def test_visualizador_sem_jobs_executar_ve_sem_permissao(page, base_url, cookie_visualizador):
    u = urlparse(base_url)
    page.context.add_cookies([{
        "name": COOKIE, "value": cookie_visualizador, "domain": u.hostname, "path": "/",
        "httpOnly": True, "secure": u.scheme == "https", "sameSite": "Lax",
    }])
    tela = Tela(page, base_url)
    tela.ir("/ferramentas")
    page.wait_for_selector("main.sem-permissao")
    assert page.locator("main.sem-permissao a[href='/']").count() == 1
    assert page.locator("#lateral nav a[href='/ferramentas']").count() == 0
    _axe(page, "sem permissão")
    _capturar(page, "negado", larguras=(1280,))
    tela.verificar()
