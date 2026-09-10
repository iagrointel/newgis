"""e2e playwright dos chamados (item L7-13-a-chamados) contra a URL interna.

Prova (portão literal, cláusulas de interface): cliente abre chamado pelo botão "reportar" presente na tela
com captura do canvas do mapa virando anexo, operador (superadmin) responde pelo painel de TODOS os inquilinos,
cliente vê o banner e o tempo de primeira resposta MEDIDO na linha, cliente comenta e fecha; anexo com sufixo
malicioso é recusado na própria tela (a recusa no servidor, 415/422, está provada em tests/api/test_chamados.py);
chamado de outro inquilino não aparece na tela do cliente (a prova por API com dois inquilinos temporários
também está na suíte de API). 0 erro de console; nenhuma resposta >= 400."""

import re
from urllib.parse import urlparse

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela, credenciais

ITEM = "L7-13-a-chamados"
COOKIE = "plat_sessao"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """A bancada da trilha serve TLS com certificado autoassinado (nginx próprio do item); o navegador da suíte
    não pode reprovar esse certificado. As telas e os contextos extras deste arquivo também declaram a mesma
    tolerância."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def chamados_disponivel(base_url, url_publica_resolve, playwright):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    req = playwright.request.new_context(base_url=base_url, ignore_https_errors=True)
    try:
        r = req.get("/api/openapi.json")
        caminhos = r.json().get("paths", {}) if r.ok else {}
    finally:
        req.dispose()
    if "/api/chamados" not in caminhos or "/api/plataforma/chamados" not in caminhos:
        pytest.skip("o backend ainda não publicou as rotas de chamado no OpenAPI")
    return True


@pytest.fixture(scope="session")
def sessao_plataforma_e2e(env, chamados_disponivel):
    """Sessão do admin do inquilino técnico `plataforma` pelas funções SECURITY DEFINER (sem senha, sem TOTP na
    mão): o mesmo caminho de tests/e2e/test_tarefas.py. O login por tela exigiria o segundo fator."""
    from tests import jobs_sessao

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        r = jobs_sessao.criar_sessao(con, "plataforma", "admin")
        con.commit()
        return r
    finally:
        con.close()


def _pagina_operador(browser, base_url, token) -> tuple:
    """Segundo contexto do playwright com o cookie do operador (superadmin): painel /admin/chamados."""
    ctx = browser.new_context(base_url=base_url, locale="pt-BR", viewport={"width": 1280, "height": 800},
                              ignore_https_errors=True)
    u = urlparse(base_url)
    ctx.add_cookies([{"name": COOKIE, "value": token, "domain": u.hostname, "path": "/",
                      "httpOnly": True, "secure": u.scheme == "https", "sameSite": "Lax"}])
    return ctx, Tela(ctx.new_page(), base_url)


def _fechar_dialogo(page) -> None:
    """O botão de rodapé do <plat-dialogo> se chama "fechar"; não é o "Fechar chamado" do cliente (esse tem
    classe perigo e fica no corpo). Clique no de texto exato "fechar"."""
    page.locator("plat-dialogo .dialogo-botoes button", has_text=re.compile("^fechar$", re.I)).first.click()


def test_fluxo_cliente_abre_operador_responde_cliente_ve_e_fecha(page, browser, base_url, credenciais_demo,
                                                                 chamados_disponivel, sessao_plataforma_e2e,
                                                                 medida, tmp_path):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    # título único por rodada: a lista do inquilino pode ter chamados de rodadas anteriores
    titulo = (f"o mapa não carrega a camada do e2e de chamados "
              f"({page.evaluate('Math.random().toString(36).slice(2,8)')})")

    # cliente entra e abre o chamado pelo botão presente em toda tela, com captura marcada
    tela.entrar(slug, login, senha, proximo="/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    page.wait_for_timeout(1500)  # tiles do primeiro quadro, como em test_mapa.py
    assert page.locator("#reportar").count() == 1
    page.click("#reportar")
    page.wait_for_selector("#chamado-titulo", timeout=10000)
    assert page.is_checked("#chamado-captura")
    page.fill("#chamado-titulo", titulo)
    page.fill("#chamado-descricao", "aberto pelo e2e do item L7-13-a-chamados; o próprio teste o fecha no fim")
    page.select_option("#chamado-severidade", "alta")
    page.locator("form.formulario button[type=submit]").click()
    page.wait_for_selector("#chamado-titulo", state="detached", timeout=20000)

    # a captura do canvas virou anexo do chamado; SLA de severidade alta declarado (prova pela API, mesmo cookie)
    r = tela.api("GET", "/api/chamados")
    assert r.status == 200
    meu = next(c for c in r.json() if c["titulo"] == titulo)
    assert meu["estado"] == "aberto" and meu["sla_primeira_resposta_horas"] == 8
    detalhe = tela.api("GET", f"/api/chamados/{meu['id']}").json()
    assert [a["nome"] for a in detalhe["anexos"]] == ["captura.png"]
    assert detalhe["anexos"][0]["bytes"] > 1000  # o canvas capturou quadro real, não um PNG de cabeçalho só

    # a tela /chamados lista com o prazo declarado enquanto não há resposta
    tela.ir("/chamados", "pagina_pronta_ms_chamados")
    linha = page.locator("#lista-corpo tr", has_text=titulo)
    assert linha.count() == 1
    assert "sem resposta (prazo de 8 h)" in linha.inner_text()

    # operador (superadmin) vê o chamado do inquilino na fila de TODOS e responde
    ctx_op, tela_op = _pagina_operador(browser, base_url, sessao_plataforma_e2e[0])
    page_op = tela_op.page
    try:
        tela_op.ir("/admin/chamados", "pagina_pronta_ms_painel")
        linha_op = page_op.locator("#lista-corpo tr", has_text=titulo)
        assert linha_op.count() == 1 and re.search(r"\bdemo\b", linha_op.inner_text())
        assert "sem resposta" in linha_op.inner_text()
        linha_op.locator("button", has_text="ver").click()
        page_op.wait_for_selector("#chamado-resposta", timeout=10000)
        page_op.fill("#chamado-resposta",
                     "recebemos o relato; a correção da camada entra na próxima janela de manutenção")
        page_op.locator("plat-dialogo button", has_text="Responder").click()
        page_op.wait_for_selector(".conversa .comentario", timeout=10000)
        assert "recebemos o relato" in page_op.locator(".conversa").inner_text()
        _fechar_dialogo(page_op)

        # cliente recarrega: banner de resposta e tempo de primeira resposta MEDIDO com a etiqueta do SLA
        tela.ir("/chamados")
        banner = page.locator("#banner-chamados a")
        banner.wait_for(timeout=10000)
        assert re.search(r"o suporte respondeu o chamado nº \d+\.", banner.inner_text())
        linha = page.locator("#lista-corpo tr", has_text=titulo)
        assert "respondeu em" in linha.inner_text() and "dentro do prazo" in linha.inner_text()

        # cliente abre o detalhe: anexo malicioso recusado na própria tela (sufixo fora da lista, sem 4xx);
        # comenta; fecha o diálogo
        linha.locator("button", has_text="ver").click()
        page.wait_for_selector("#chamado-novo-anexo", timeout=10000)
        exe = tmp_path / "e2e_camada.exe"
        exe.write_bytes(b"MZ\x90\x00" + b"\x00" * 64)
        page.locator("#chamado-novo-anexo").set_input_files(str(exe))
        page.wait_for_function(
            "() => (document.getElementById('lista-aviso')?.textContent || '').includes('não aceito')",
            timeout=10000)
        page.fill("#chamado-novo-comentario", "confirmo que a tela voltou ao normal")
        page.locator("plat-dialogo button", has_text="Comentar").click()
        page.wait_for_selector(".conversa .comentario", timeout=10000)
        assert "confirmo que a tela voltou" in page.locator(".conversa").inner_text()
        _fechar_dialogo(page)

        # operador resolve
        tela_op.ir("/admin/chamados")
        linha_op = page_op.locator("#lista-corpo tr", has_text=titulo)
        linha_op.locator("button", has_text="ver").click()
        page_op.wait_for_selector("#chamado-novo-estado", timeout=10000)
        page_op.select_option("#chamado-novo-estado", "resolvido")
        page_op.locator("plat-dialogo button", has_text="Mudar estado").click()
        # o detalhe reaberto não exibe marcador de estado; a LISTA (recarregada pelo módulo) é quem mostra
        page_op.locator("#lista-corpo tr", has_text=titulo).locator(
            "span.marcador", has_text=re.compile("^resolvido$", re.I)).wait_for(timeout=10000)
        _fechar_dialogo(page_op)

        # cliente vê o banner de resolvido, abre o detalhe e fecha o chamado
        tela.ir("/chamados")
        banner = page.locator("#banner-chamados a")
        banner.wait_for(timeout=10000)
        assert re.search(r"o chamado nº \d+ foi resolvido\.", banner.inner_text())
        linha = page.locator("#lista-corpo tr", has_text=titulo)
        assert "resolvido" in linha.inner_text()
        linha.locator("button", has_text="ver").click()
        page.wait_for_selector("#chamado-novo-comentario", timeout=10000)
        page.locator("plat-dialogo button.perigo", has_text="Fechar chamado").click()
        # o <dialog> nativo esconde o corpo ao fechar; o conteúdo continua no DOM — espere escondido
        page.wait_for_selector("#chamado-novo-comentario", state="hidden", timeout=10000)
        linha = page.locator("#lista-corpo tr", has_text=titulo)
        assert "fechado" in linha.inner_text()
    finally:
        ctx_op.close()

    tela.capturar("fluxo")
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] (tests/e2e/apoio.py Tela.ir)")
    tela.verificar()


def test_chamado_de_outro_inquilino_nao_aparece_na_tela(page, browser, base_url, credenciais_demo,
                                                        chamados_disponivel):
    """Cláusula de UI da refutação: o chamado do inquilino demo não aparece para o admin de demo2 (por API a
    RLS já está provada com dois inquilinos temporários em tests/api/test_chamados.py)."""
    outros = credenciais()
    if "demo2" not in outros:
        pytest.skip("credenciais sem o inquilino demo2 (rode install.sh)")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/chamados")
    titulo = f"chamado exclusivo do inquilino demo ({tela.page.evaluate('Math.random().toString(36).slice(2,8)')})"
    r = tela.api("POST", "/api/chamados", corpo={
        "titulo": titulo, "descricao": "prova de invisibilidade entre inquilinos na tela",
        "severidade": "baixa", "contexto": {"tela": "/chamados"},
    })
    corpo = r.json() if r.status == 201 else {}
    try:
        assert r.status == 201, r.text

        ctx_b = browser.new_context(base_url=base_url, locale="pt-BR",
                                    viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
        try:
            tela_b = Tela(ctx_b.new_page(), base_url)
            tela_b.entrar("demo2", *outros["demo2"], proximo="/chamados")
            tela_b.page.wait_for_selector("#lista-corpo tr", timeout=20000)
            assert tela_b.page.locator("#lista-corpo tr", has_text=titulo).count() == 0
            # e a tela dele lista os chamados DELE normalmente (não é tela quebrada, é RLS)
            r_b = tela_b.api("GET", "/api/chamados")
            assert r_b.status == 200 and all(titulo not in (c.get("titulo") or "") for c in r_b.json())
            tela_b.verificar()
        finally:
            ctx_b.close()
    finally:
        if corpo.get("id") and corpo.get("estado") != "fechado":
            tela.api("POST", f"/api/chamados/{corpo['id']}/fechar", corpo={})
    tela.verificar()
