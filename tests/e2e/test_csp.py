"""Item HARD-01 (docs/SEGURANCA.md seção 9; deploy/nginx.conf): a Content-Security-Policy que o nginx acrescenta não
pode barrar nada que a interface faz. Abre as telas principais numa aba nova cada (a anterior mantém fluxo de
eventos aberto e segura o evento `load`) e falha se o console do navegador registrar uma violação de CSP.
Contra a URL pública o cabeçalho vem do nginx real; contra um nginx renderizado de deploy/nginx.conf
(scripts/varredura_seguranca.py::renderizar_nginx) vem do modelo — os dois têm de passar."""

import pytest

TELAS = ["/", "/mapa", "/conteudo", "/tarefas", "/uploads", "/tokens", "/admin/usuarios", "/admin/grupos",
         "/admin/papeis", "/admin/log", "/eu", "/api/docs"]


@pytest.mark.lento
def test_csp_do_nginx_nao_barra_nenhuma_tela(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    violacoes: list[str] = []

    def observar(pg):
        def registrar(m):
            if "Content Security Policy" in m.text or "Refused to" in m.text:
                violacoes.append(m.text)

        pg.on("console", registrar)

    observar(page)
    page.goto(f"{base_url}/entrar?inquilino={slug}", wait_until="load")
    page.fill("input[name='login']", login)
    page.fill("input[name='senha']", senha)
    page.click("button[type='submit']")
    page.wait_for_timeout(2500)
    resposta = page.request.get(f"{base_url}/static/index.html")
    csp = resposta.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp, csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0], csp
    vistas = []
    for tela in TELAS:
        pg = page.context.new_page()
        observar(pg)
        pg.goto(f"{base_url}{tela}", wait_until="load", timeout=30000)
        pg.wait_for_timeout(2000)
        vistas.append(pg.url)
        pg.close()
    assert len(vistas) == len(TELAS)
    assert violacoes == [], violacoes
