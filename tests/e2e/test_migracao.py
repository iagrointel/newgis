"""e2e playwright da tela /migracao (item L2-08-a-leitor-portal-inventario): a tela de CONEXÃO com o Portal e
o RELATÓRIO de inventário, com capturas em tests/e2e/capturas/L2-08-a-leitor-portal-inventario_*.png.

O portal do outro lado é o servidor de mentira de `tests/migracao/portal_falso.py` — a prova contra um Portal
real depende da credencial do parceiro (decisão D20 do dono), ver `tests/migracao/PORTAL_DE_TESTE.md`.

Como rodar (a trilha não tem nginx nem worker próprios):

    set -a; source /home/dev/plataforma/laco/var/trilha/l208a.env; set +a
    openssl req -x509 -newkey rsa:2048 -nodes -keyout var/e2e/chave.pem -out var/e2e/cert.pem \\
      -days 30 -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"
    PLAT_URL_PUBLICA=https://127.0.0.1:8169 venv/bin/python -m uvicorn tests.e2e.servidor_local:app \\
      --host 127.0.0.1 --port 8169 --ssl-keyfile var/e2e/chave.pem --ssl-certfile var/e2e/cert.pem &
    venv/bin/pytest tests/e2e/test_migracao.py --base-url https://127.0.0.1:8169

Três coisas que este arquivo faz por conta própria, e o porquê de cada uma (custaram tempo, ficam escritas):
  1. **TLS mesmo em 127.0.0.1.** A defesa de CSRF (`app/auth/sessao.py::checar_escrita_sob_cookie`) compara o
     `Origin` do navegador com `PLAT_URL_PUBLICA`, e `PLAT_URL_PUBLICA` só aceita `https://`. Sem TLS, todo
     POST feito PELA TELA volta 403 — e é justamente o botão da tela que se quer provar.
  2. **Contexto de navegador próprio** (`ignore_https_errors`), em vez do `page` do pytest-playwright: o
     certificado é assinado por ele mesmo.
  3. **Fixtures próprias**, sem `api_auth`: aquele fixture pergunta o OpenAPI com `httpx` verificando o
     certificado e pularia a suíte inteira aqui.
"""

import httpx
import pytest

from tests.e2e.apoio import CAPTURAS, Tela, credenciais, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-08-a-leitor-portal-inventario"
ROTA = "/api/migracao/inventarios"


class TelaMigracao(Tela):
    def capturar(self, nome: str):
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="module")
def api_no_ar(base_url) -> str:
    try:
        r = httpx.get(f"{base_url}/api/openapi.json", timeout=15, verify=False)  # noqa: S501 — certificado próprio
    except httpx.HTTPError as e:
        pytest.skip(f"{base_url}/api/openapi.json inacessível ({e}); veja o cabeçalho deste arquivo")
    if r.status_code != 200 or ROTA not in r.json().get("paths", {}):
        pytest.skip(f"{base_url} sem {ROTA} no OpenAPI")
    return base_url


@pytest.fixture
def pagina(browser, api_no_ar):
    ctx = browser.new_context(base_url=api_no_ar, locale="pt-BR", viewport={"width": 1280, "height": 900},
                              ignore_https_errors=True)
    p = ctx.new_page()
    yield p
    ctx.close()


def test_tela_de_conexao_e_de_inventario(pagina, base_url, env, medida):
    from app.migracao import tarefas as tarefas_migracao
    from tests.api.test_migracao_inventario import CtxFalso, _conexao_direta
    from tests.api.test_rls import ids_por_slug
    from tests.migracao.portal_falso import PortalFalso, acervo

    cred = credenciais()
    if "demo" not in cred:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo")
    admin_login, senha_admin = cred["demo"]
    s = sufixo()
    tela = TelaMigracao(pagina, base_url)
    conexao_id = inventario_id = None
    with PortalFalso() as portal:
        try:
            tela.entrar("demo", admin_login, senha_admin, proximo="/migracao")
            r = tela.api("POST", "/api/conexoes",
                         {"tipo": "esri_rest", "nome": f"zt-e2e-portal-{s}", "url": portal.base})
            assert r.status == 201, r.text()
            conexao_id = r.json()["id"]

            # 1. tela de conexão: a conexão recém-registrada aparece na escolha, com a URL do portal
            tela.medidas["pagina_migracao_ms"] = tela.ir("/migracao")
            pagina.wait_for_function(
                "(nome) => [...document.querySelectorAll('#conexao option')].some(o => o.textContent === nome)",
                arg=f"zt-e2e-portal-{s}", timeout=15000)
            pagina.select_option("#conexao", label=f"zt-e2e-portal-{s}")
            assert portal.base in pagina.locator("#conexao-url").inner_text()
            tela.capturar("conexao")

            # 2. o botão da tela enfileira a leitura; a tarefa roda neste processo (a trilha não tem worker)
            pagina.click("#inventariar")
            pagina.wait_for_function(
                "() => document.querySelectorAll('#lista-corpo tr[data-id]').length > 0", timeout=20000)
            inventario_id = pagina.locator("#lista-corpo tr[data-id]").first.get_attribute("data-id")
            tela.capturar("lista_enfileirada")

            job_id = tela.api("GET", f"/api/migracao/inventarios/{inventario_id}").json()["job_id"]
            eu = tela.api("GET", "/api/eu").json()
            con = _conexao_direta(env)
            try:
                tenant_id = ids_por_slug(con)["demo"]
            finally:
                con.rollback()
                con.close()
            tarefas_migracao.migracao_inventariar(
                CtxFalso(tenant_id, eu["id"], job_id), inventario_id=inventario_id)

            # 3. relatório na tela: resumo, tabela por tipo, tabela de itens e o botão de CSV
            tela.ir(f"/migracao?inventario={inventario_id}")
            pagina.wait_for_function(
                "() => document.querySelectorAll('#por-tipo-corpo tr').length > 0", timeout=20000)
            esperado = len(acervo()["itens"])
            assert pagina.locator("#itens-corpo tr").count() == esperado
            assert str(esperado) in pagina.locator("#resumo").inner_text()
            assert "migra" in pagina.locator("#por-tipo-corpo").inner_text()
            assert pagina.locator("#csv").get_attribute("href").endswith("relatorio.csv")
            tela.capturar("relatorio")

            # 4. o CSV baixa de verdade, com o mesmo cookie da tela
            r_csv = tela.api("GET", f"/api/migracao/inventarios/{inventario_id}/relatorio.csv")
            assert r_csv.status == 200
            assert r_csv.text().count("\r\n") >= esperado

            tela.verificar()  # 0 erro de console
        finally:
            if inventario_id:
                tela.api("DELETE", f"/api/migracao/inventarios/{inventario_id}")
            if conexao_id:
                tela.api("DELETE", f"/api/conexoes/{conexao_id}")

    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "playwright chromium contra a API da trilha (tests/e2e/test_migracao.py)")
