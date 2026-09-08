"""e2e da coleção (L5-04-c-temas-capa-colecao): leitora /colecao com 3 itens navegáveis sem recarregar a
página; publicar por link citando camada privada avisa e o botão "corrigir" recria o link incluindo; `og:`
só na página pública /c/<token>; anônimo com o link parcial vê o aviso do que ficou fora (refutação), nunca
um leitor vazio sem dizer por quê."""

import json
from pathlib import Path

import pytest

from app.settings import settings
from tests.e2e.apoio import Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ROTAS_COLECAO = ("/api/itens", "/api/itens/{id}/links", "/api/compartilhado/{token}")

# contra uvicorn puro o /static/ é do nginx em produção: aqui a rota do playwright serve web/ do próprio
# worktree (mesmo contrato de caminho), para a página carregar o CSS e os módulos ES
RAIZ_WEB = Path(__file__).resolve().parents[2] / "web"
# e o CSRF de escrita sob cookie (ADR 0002 5.3) exige Origin = PLAT_URL_PUBLICA: o navegador manda a origem
# da página (127.0.0.1:8181), então a escrita feita pelo JavaScript da página reemite com a origem pública
PUBLICA = settings.PLAT_URL_PUBLICA.rstrip("/")


def _servir_estaticos(page):
    def cumprir(rota):
        rel = rota.request.url.split("/static/", 1)[1].split("?")[0]
        caminho = RAIZ_WEB / rel
        if caminho.is_file():
            rota.fulfill(path=str(caminho))
        else:
            rota.fulfill(status=404, body="")
    page.route("**/static/**", cumprir)


def _reescrer_origem(page):
    def reemitir(rota):
        if rota.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            cabecalhos = {**rota.request.headers, "origin": PUBLICA}
            rota.fulfill(response=rota.fetch(headers=cabecalhos))
        else:
            rota.continue_()
    page.route("**/api/**", reemitir)


@pytest.fixture(scope="session")
def api_colecao(api_auth):
    faltam = [r for r in ROTAS_COLECAO if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (rotas do ADR 0004)")
    return api_auth


def _criar(admin_api, base_url, corpo):
    r = admin_api.post(
        f"{base_url}/api/itens",
        data=json.dumps(corpo),
        headers={"Content-Type": "application/json"},
    )
    assert r.status == 201, r.text()
    return r.json()


def test_colecao_fluxo_completo(
    page, browser, base_url, credenciais_demo, admin_api, api_colecao, medida
):
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    criados = []
    try:
        filhos = []
        for i in range(3):
            f = _criar(
                admin_api,
                base_url,
                {
                    "tipo": "app",
                    "titulo": f"E2E colecao app {s} {i}",
                    "dados": {"tipo": "app", "esquema_versao": 1, "corpo": {}},
                },
            )
            filhos.append(f)
            criados.append(f["id"])
        camada = _criar(
            admin_api,
            base_url,
            {
                "tipo": "camada_vetorial",
                "titulo": f"E2E colecao camada privada {s}",
                "dados": {
                    "schema": "plat_trabalho",
                    "tabela": "zt_inexistente",
                    "geometria": "Point",
                    "srid": 4326,
                    "campos": [{"nome": "a", "tipo": "text"}],
                    "fonte": "hospedada",
                },
            },
        )
        criados.append(camada["id"])
        colecao = _criar(
            admin_api,
            base_url,
            {
                "tipo": "colecao",
                "titulo": f"E2E colecao {s}",
                "dados": {
                    "tipo": "colecao",
                    "esquema_versao": 1,
                    "corpo": {
                        "capa": {"titulo": f"Coleção {s}", "subtitulo": "três peças navegáveis"},
                        "itens": [{"item_id": f["id"], "rotulo": f"peça {i}"} for i, f in enumerate(filhos)]
                        + [{"item_id": camada["id"], "rotulo": "camada privada"}],
                    },
                },
            },
        )
        criados.append(colecao["id"])

        # ----- leitora interna: 3 itens navegáveis, sem recarregar a página
        _servir_estaticos(page)
        _reescrer_origem(page)
        tela.entrar(slug, login, senha, proximo=f"/colecao?item={colecao['id']}")
        page.wait_for_selector("#leitor:not([hidden])", timeout=15000)
        page.wait_for_selector("#colecao-ficha article", timeout=10000)
        page.evaluate("() => { window.__marcanavegacao = 'aqui'; }")
        # o admin lê os 3 apps E a camada citada (4 fichas); o anônimo, só o que entrar no link
        assert page.text_content("#colecao-contador").strip() == "1 de 4"
        assert page.text_content("#colecao-ficha h3").strip() == "peça 0"
        t0 = page.evaluate("() => performance.now()")
        page.click("#colecao-proximo")
        page.wait_for_function("() => document.getElementById('colecao-contador').textContent.trim() === '2 de 4'")
        page.click("#colecao-proximo")
        page.wait_for_function("() => document.getElementById('colecao-contador').textContent.trim() === '3 de 4'")
        assert page.text_content("#colecao-ficha h3").strip() == "peça 2"
        page.click("#colecao-proximo")
        page.wait_for_function("() => document.getElementById('colecao-contador').textContent.trim() === '4 de 4'")
        assert page.text_content("#colecao-ficha h3").strip() == "camada privada"
        assert page.evaluate("() => window.__marcanavegacao") == "aqui"  # sem recarregar
        assert page.evaluate("() => performance.getEntriesByType('navigation').length") == 1
        page.click("#colecao-anterior")
        page.wait_for_function("() => document.getElementById('colecao-contador').textContent.trim() === '3 de 4'")
        pagina_ms = round(page.evaluate("() => performance.now()") - t0, 1)

        # ----- publicar por link citando camada privada: o link nasce MINIMALISTA (só a coleção),
        # avisa nomeando o que ficou fora e oferece corrigir; corrigir inclui tudo o que é citado
        page.click("#botao-link")
        page.wait_for_selector("#link-publico", timeout=15000)
        page.wait_for_selector("#aviso-link[data-tipo='erro']", timeout=10000)
        assert "4 item(ns) citado(s)" in page.text_content("#aviso-link")
        url_parcial = page.get_attribute("#link-publico", "href")
        assert url_parcial and "/c/" in url_parcial
        page.click("#botao-corrigir")
        page.wait_for_selector("#aviso-link[data-tipo='ok']", timeout=15000)
        assert page.locator("#botao-corrigir").count() == 0
        url_corrigido = page.get_attribute("#link-publico", "href")
        assert url_corrigido != url_parcial
        tok_dentro = url_corrigido.rsplit("/c/", 1)[1]

        # ----- og: só na página pública
        rp = page.request.get(f"{base_url}/c/{tok_dentro}")
        texto = rp.text()
        assert rp.status == 200 and 'meta property="og:title"' in texto, rp.status
        ri = page.request.get(f"{base_url}/colecao")
        assert ri.status == 200 and "og:title" not in ri.text()

        # ----- refutação: anônimo com o link PARCIAL (3 apps, camada de fora) vê o aviso do que
        # ficou fora, nunca um leitor vazio sem dizer por quê
        r = admin_api.post(
            f"{base_url}/api/itens/{colecao['id']}/links",
            data=json.dumps({"itens_incluidos": [f["id"] for f in filhos]}),
            headers={"Content-Type": "application/json"},
        )
        assert r.status == 201, r.text()
        assert [a["titulo"] for a in r.json()["avisos"]] == [f"E2E colecao camada privada {s}"]
        tok_parcial = r.json()["token"]
        anon = browser.new_context(locale="pt-BR")
        p2 = anon.new_page()
        _servir_estaticos(p2)
        erros = []
        p2.on("pageerror", lambda e: erros.append(str(e)))
        p2.goto(f"{base_url}/c/{tok_parcial}", wait_until="domcontentloaded")
        p2.wait_for_selector("#leitor-colecao:not([hidden])", timeout=15000)
        aviso = (p2.text_content("#aviso") or "").strip()
        assert "1 item(ns) citado(s) pela coleção não está(ão) no link" in aviso, aviso
        corpo2 = p2.text_content("#leitor-colecao")
        assert "fora do link: camada privada" in corpo2, corpo2
        assert p2.text_content("#colecao-contador").strip() == "1 de 3"  # anônimo: só os 3 apps do link
        assert erros == [], erros
        anon.close()

        gravar = medida("L5-04-c-temas-capa-colecao")
        gravar(
            "navegacao_3_cliques_ms",
            pagina_ms,
            "ms",
            "PLAT_GRAVAR_MEDIDAS=1 bash laco/roda_teste.sh tests/e2e/test_colecao.py --base-url http://127.0.0.1:8181",
        )
        tela.verificar()
    finally:
        for iid in reversed(criados):  # coleção primeiro: os filhos só apagam sem quem os cita
            admin_api.delete(f"{base_url}/api/itens/{iid}")
