"""e2e do item L0-03-e-compartilhamento (playwright, chromium): no painel Compartilhar de um MAPA que usa uma camada
PRIVADA — compartilhar com grupo (membro do grupo passa a ler pela API), com o inquilino (a árvore mostra a camada
"abaixo do nível" com o aviso e a opção "elevar ao nível do mapa"; elevar é escolha explícita e só muda ao Aplicar)
e por link (abrir /c/<token> em contexto ANÔNIMO do playwright → 200 e a página mostra o mapa; revogar pela tela →
404 medido em ≤ 1 s; abrir de novo → a página anônima mostra o 404). Capturas L0-03-e_*.png em tests/e2e/capturas/.
Sem nginx na frente (uvicorn de trilha), o navegador passa pela frente de tests/e2e/frente_trilha.py."""

import contextlib
import re
import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo
from tests.e2e.frente_trilha import FrenteTrilha

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-03-e"
TOKEN_NA_URL = re.compile(r"/c/([0-9a-f]{64})")


class TelaCompartilhar(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


def _dialogo(page):
    return page.locator("#painel-compartilhar dialog[open]")


def _limpar_aviso(page, seletor):
    page.evaluate(f"() => document.querySelector('{seletor}')?.limpar()")


def _sessao_de(playwright, base_url, slug, login, senha_temporaria):
    """contexto de API de um usuário novo: login com a senha temporária e troca obrigatória."""
    ctx = playwright.request.new_context(base_url=base_url)
    r = ctx.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha_temporaria})
    assert r.status == 200 and "trocar_senha" in r.json()["usuario"]["pendencias"], r.text()
    nova = f"Senha-e2e-1{sufixo()}"
    assert ctx.put("/api/eu/senha", data={"atual": senha_temporaria, "nova": nova}).status == 204
    return ctx


def test_compartilhar_grupo_inquilino_arvore_e_link_anonimo(
    base_url, credenciais_demo, admin_api, playwright, browser, medida, env
):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    titulo_mapa = f"E2E mapa compartilhado {s}"
    dados_camada = {
        "schema": "plat_trabalho",
        "tabela": "zt_inexistente",
        "geometria": "Point",
        "srid": 4326,
        "campos": [{"nome": "a", "tipo": "text"}],
        "fonte": "hospedada",
    }
    r = admin_api.post(
        "/api/itens", data={"tipo": "camada_vetorial", "titulo": f"E2E camada privada {s}", "dados": dados_camada}
    )
    assert r.status == 201, r.text()
    camada_id = r.json()["id"]
    r = admin_api.post(
        "/api/itens",
        data={"tipo": "mapa", "titulo": titulo_mapa, "dados": {"esquema_versao": 1, "corpo": {"camadas": [camada_id]}}},
    )
    assert r.status == 201, r.text()
    mapa_id = r.json()["id"]
    r = admin_api.post("/api/grupos", data={"nome": f"Grupo E2E compartilhar {s}", "visibilidade": "inquilino"})
    assert r.status == 201, r.text()
    gid = r.json()["id"]
    login_membro = f"e2e_c_{s}"
    r = admin_api.post("/api/usuarios", data={"login": login_membro, "nome": "Membro E2E", "perfil": "visualizador"})
    assert r.status == 201, r.text()
    uid, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
    assert admin_api.post(f"/api/grupos/{gid}/membros", data={"usuario_id": uid}).status == 201
    membro = _sessao_de(playwright, base_url, slug, login_membro, temporaria)
    assert membro.post(f"/api/grupos/{gid}/aceitar", data={}).status == 200
    assert membro.get(f"/api/itens/{mapa_id}").status == 404  # privado: o membro ainda não vê (404, não 403)
    frente = FrenteTrilha.se_preciso(base_url, env["PLAT_URL_PUBLICA"])
    anon_ctx = None
    with frente or contextlib.nullcontext():
        url = frente.url if frente else base_url
        ctx = browser.new_context(base_url=url, locale="pt-BR", viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        tela = TelaCompartilhar(page, url)
        try:
            tela.entrar(slug, admin_login, senha_admin, proximo=f"/conteudo/{mapa_id}")
            tela.medidas["pagina_item_ms"] = tela.ir(f"/conteudo/{mapa_id}")
            page.wait_for_selector("#item-compartilhar", timeout=15000)
            page.click("#item-compartilhar")
            d = _dialogo(page)
            d.locator("#compartilhar-aplicar").wait_for(timeout=15000)
            # 1. grupo: marcar, aplicar; o membro do grupo passa a ler o mapa (a camada privada continua 404)
            d.locator(f"#grupo-{gid}").check()
            _limpar_aviso(page, "#compartilhar-aviso")
            d.locator("#compartilhar-aplicar").click()
            page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
            est = tela.api("GET", f"/api/itens/{mapa_id}/compartilhamento").json()
            assert [g["id"] for g in est["grupos"]] == [gid] and est["acesso"] == "privado"
            assert (
                membro.get(f"/api/itens/{mapa_id}").status == 200
                and membro.get(f"/api/itens/{camada_id}").status == 404
            )
            # a camada privada, com o mapa em grupo, já aparece abaixo do nível
            aviso_deps = d.locator("#compartilhar-dependencias-aviso")
            assert aviso_deps.is_visible()
            tela.capturar("grupo")
            # 2. inquilino: a árvore avisa (camada privada abaixo de "inquilino") e oferece "elevar ao nível do mapa"
            d.locator("#acesso-inquilino").check()
            linha = d.locator(f"#compartilhar-dependencias tr[data-dependencia='{camada_id}']")
            assert "abaixo" in (linha.get_attribute("class") or "")
            assert aviso_deps.is_visible() and "inquilino" in aviso_deps.text_content()
            caixa = linha.locator("input[type='checkbox']")
            assert caixa.get_attribute("aria-label") == "elevar ao nível do mapa" and not caixa.is_checked()
            tela.capturar("arvore_aviso")
            # sem marcar: só o mapa muda de nível; a camada continua privada (nada em silêncio)
            _limpar_aviso(page, "#compartilhar-aviso")
            d.locator("#compartilhar-aplicar").click()
            page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
            assert tela.api("GET", f"/api/itens/{mapa_id}").json()["acesso"] == "inquilino"
            assert tela.api("GET", f"/api/itens/{camada_id}").json()["acesso"] == "privado"
            assert aviso_deps.is_visible()
            # marcar (botão "marcar todas as que posso elevar") e aplicar: a camada sobe ao nível do mapa e o aviso some
            d.locator("#compartilhar-elevar-todas").click()
            assert caixa.is_checked()
            _limpar_aviso(page, "#compartilhar-aviso")
            d.locator("#compartilhar-aplicar").click()
            page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
            assert tela.api("GET", f"/api/itens/{camada_id}").json()["acesso"] == "inquilino"
            page.wait_for_selector("#compartilhar-dependencias-aviso", state="hidden", timeout=5000)
            assert "abaixo" not in (linha.get_attribute("class") or "")
            assert membro.get(f"/api/itens/{camada_id}").status == 200
            tela.capturar("arvore_elevada")
            # 3. link: criar pela tela, abrir em contexto ANÔNIMO do navegador → 200 e a página mostra o mapa
            d.locator("#link-novo").click()
            d.locator("#link-form button[type='submit']").click()
            page.wait_for_selector("#link-url", timeout=15000)
            token = TOKEN_NA_URL.search(page.text_content("#link-url")).group(1)
            tela.capturar("link")
            anon_ctx = browser.new_context(base_url=url, locale="pt-BR", viewport={"width": 1280, "height": 800})
            pg = anon_ctx.new_page()
            anon = TelaCompartilhar(pg, url)
            r = anon_ctx.request.get(f"/api/compartilhado/{token}")
            assert r.status == 200 and r.json()["item"]["id"] == mapa_id and "login" not in r.json()["item"]["dono"]
            anon.medidas["pagina_link_anonimo_ms"] = anon.ir(f"/c/{token}")
            pg.wait_for_selector("#item:not([hidden]) h2", timeout=15000)
            assert pg.text_content("#item h2").strip() == titulo_mapa
            assert "null" not in pg.text_content("#item")  # filho nulo virava o texto "null" (visto na captura)
            assert pg.locator("#lateral").text_content().strip() == ""  # sem sessão, sem barra lateral
            anon.capturar("anonimo_200")
            # 4. revogar pela tela: 404 em ≤ 1 s (medido do clique e da confirmação do servidor)
            _limpar_aviso(page, "#compartilhar-aviso")
            t_clique = time.perf_counter()
            d.locator("#links-tabela button", has_text="Revogar").first.click()
            page.wait_for_selector("#compartilhar-aviso[data-tipo='ok']", timeout=15000)
            t_ok = time.perf_counter()
            r = anon_ctx.request.get(f"/api/compartilhado/{token}")
            fim = time.perf_counter()
            tela.medidas["revogacao_clique_ate_404_e2e_ms"] = round((fim - t_clique) * 1000, 1)
            tela.medidas["revogacao_ate_404_e2e_ms"] = round((fim - t_ok) * 1000, 1)
            assert r.status == 404 and r.json()["erro"] == "link_invalido", r.text()
            assert tela.medidas["revogacao_ate_404_e2e_ms"] <= 1000
            page.wait_for_function(
                "() => (document.querySelector('#links-tabela tbody tr')?.textContent || '').includes('revogado')",
                timeout=15000,
            )
            # 5. abrir de novo: a página anônima mostra o 404 (sem cache: a resposta é no-store)
            anon.esperar_status(404)
            anon.ir(f"/c/{token}")
            pg.wait_for_selector("#aviso[data-tipo='erro']", timeout=15000)
            assert "404" in pg.text_content("#aviso") and pg.locator("#item").is_hidden()
            anon.capturar("anonimo_404")
            anon.verificar()
            page.keyboard.press("Escape")
            page.wait_for_selector("#painel-compartilhar dialog[open]", state="detached", timeout=5000)
            tela.verificar()
            gravar = medida(ITEM)
            for nome, valor in {**tela.medidas, **anon.medidas}.items():
                gravar(nome, valor, "ms", "playwright chromium 1280x800 (tests/e2e/test_compartilhamento.py)")
        finally:
            if anon_ctx is not None:
                anon_ctx.close()
            ctx.close()
            membro.dispose()
            for iid in (mapa_id, camada_id):
                admin_api.delete(f"/api/itens/{iid}")
            admin_api.delete(f"/api/grupos/{gid}")
            admin_api.delete(f"/api/usuarios/{uid}")
