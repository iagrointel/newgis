"""e2e /paineis/{id} e /c/{token} (item L2-06-a-modelo-painel-fontes). Prova: painel de exemplo (6
elementos, 2 fontes — `plat.painel_exemplo_semear`, migração `20260906T2145_documento_painel.sql`) abre
com first-contentful-paint <= 1.500 ms; em viewport 390 px a grade empilha (captura); filtro global muda
a contagem mostrada; link compartilhado abre em contexto anônimo do navegador e nega depois de revogado.

Roda contra a URL da PRÓPRIA trilha (uvicorn solto na porta do item, `PLAT_SERVIR_STATIC_DEV=1` — sem
nginx na frente, servindo web/ em /static/ direto do disco só para este cenário isolado): passe
`--base-url http://127.0.0.1:<porta>` ao pytest. Sem isso, `url_publica_resolve` é falso e a suíte pula
inteira (nunca reprova por engano contra um domínio que não existe de propósito, ver trilha_ambiente.sh)."""

import re
import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela

ITEM = "L2-06-a-modelo-painel-fontes"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Só neste arquivo: a trilha isolada sobe o próprio uvicorn com TLS autoassinado (settings.py exige
    `https://` em PLAT_URL_PUBLICA — sem isso o CSRF de app/auth/sessao.py::checar_escrita_sob_cookie
    rejeita todo POST/PUT/DELETE de sessão com `origem_invalida`, já que a origem do navegador nunca bate
    com um domínio de produção). Não altera tests/e2e/conftest.py: outros arquivos continuam validando TLS."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve) -> set[str]:
    """Mesma coisa que tests/e2e/conftest.py::rotas_api, mas com `verify=False` — o certificado do
    uvicorn desta trilha é autoassinado (ver `browser_context_args` acima); só este arquivo, não muda o
    comportamento padrão (que continua verificando TLS de verdade contra a URL pública real)."""
    import httpx

    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    try:
        r = httpx.get(f"{base_url}/api/openapi.json", timeout=15, verify=False)
    except httpx.HTTPError as e:
        pytest.skip(f"{base_url}/api/openapi.json inacessível: {e}")
    if r.status_code != 200:
        pytest.skip(f"{base_url}/api/openapi.json devolveu {r.status_code}")
    return set(r.json().get("paths", {}))


@pytest.fixture(scope="module")
def painel_exemplo(env):
    if not env.get("PLAT_DSN"):
        pytest.skip("sem PLAT_DSN")
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute("SELECT plat.semente_demo_habilitada() AS ligada")
            if not cur.fetchone()["ligada"]:
                pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
            cur.execute("SELECT camada_id, painel_id FROM plat.painel_exemplo_semear('demo')")
            r = cur.fetchone()
        con.commit()
        yield {"camada_id": str(r["camada_id"]), "painel_id": str(r["painel_id"])}
    finally:
        con.close()


def test_painel_primeira_pintura_e_empilhamento_em_tela_estreita(page, base_url, credenciais_demo, painel_exemplo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)

    painel_id = painel_exemplo["painel_id"]
    pronto_ms = tela.ir(f"/paineis/{painel_id}", "pagina_pronta_ms_painel")

    page.wait_for_selector(".painel-el", timeout=20000)
    assert page.locator(".painel-el").count() == 6

    pintura = page.evaluate(
        "() => { const e = performance.getEntriesByType('paint')"
        ".find(p => p.name === 'first-contentful-paint'); return e ? e.startTime : null; }"
    )
    assert pintura is not None, "sem first-contentful-paint"

    # o indicador de contagem mostra 120 (as 120 ocorrências sintéticas, sem filtro)
    page.wait_for_function(
        "() => document.querySelectorAll('.painel-indicador-valor').length > 0 "
        "&& [...document.querySelectorAll('.painel-indicador-valor')].some(e => e.textContent.trim() === '120')"
    )

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_desktop.png"), full_page=True)

    # viewport estreito (390 px, cláusula literal do portão): a grade colapsa para 1 coluna — todo
    # elemento cai na MESMA coluna de bounding box (medido pela posição x, não por CSS computado, prova
    # de verdade do layout renderizado)
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)
    xs = [round(box["x"]) for box in (page.locator(".painel-el").nth(i).bounding_box() for i in range(6))]
    assert len(set(xs)) == 1, f"elementos não empilharam em 390px: x = {xs}"
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_390px.png"), full_page=True)

    tela.verificar()
    gravar = medida(ITEM)
    gravar("primeira_pintura_painel_ms", round(pintura, 1), "ms",
           "first-contentful-paint de /paineis/{id} com o painel de exemplo (6 elementos, chromium)")
    gravar("pagina_painel_pronta_ms", pronto_ms, "ms", "goto('/paineis/{id}') até body[data-pronto=1]")
    assert pintura <= 1500, f"primeira pintura {pintura:.0f} ms > 1.500 ms (portão do item)"


def test_filtro_global_muda_a_contagem_na_tela(page, base_url, credenciais_demo, painel_exemplo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")

    page.wait_for_function(
        "() => [...document.querySelectorAll('.painel-indicador-valor')].some(e => e.textContent.trim() === '120')"
    )
    campo = page.locator('.painel-filtro input[data-campo="categoria"]')
    assert campo.count() == 1
    campo.fill("energia")
    page.wait_for_function(
        "() => { const els = [...document.querySelectorAll('.painel-indicador-valor')]; "
        "return els.length && !els.some(e => e.textContent.trim() === '120'); }",
        timeout=10000,
    )
    valor = page.locator(".painel-indicador-valor").first.text_content().strip()
    assert re.match(r"^\d[\d.]*$", valor) and valor != "120"
    tela.verificar()


def test_link_compartilhado_abre_anonimo_e_nega_apos_revogar(page, context, base_url, credenciais_demo, painel_exemplo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    painel_id = painel_exemplo["painel_id"]

    r = page.request.post(
        f"{base_url}/api/itens/{painel_id}/links", data={"nome": "zt-painel-e2e", "itens_incluidos": []}
    )
    assert r.ok, r.text()
    link = r.json()

    # aba NOVA, sem cookie nenhum: contexto anônimo de verdade
    pagina_anon = context.new_page()
    tela_anon = Tela(pagina_anon, base_url)
    pagina_anon.goto(f"{base_url}/c/{link['token']}", wait_until="domcontentloaded")
    pagina_anon.wait_for_selector(".painel-el", timeout=20000)
    assert pagina_anon.locator(".painel-el").count() == 6
    tela_anon.verificar()
    pagina_anon.close()

    r_rev = page.request.delete(f"{base_url}/api/itens/{painel_id}/links/{link['id']}")
    assert r_rev.status == 204

    pagina_negada = context.new_page()
    pagina_negada.goto(f"{base_url}/c/{link['token']}", wait_until="domcontentloaded")
    pagina_negada.wait_for_selector("#aviso:not([hidden])", timeout=10000)
    corpo = pagina_negada.text_content("#aviso")
    assert corpo and corpo.strip() != ""
    assert pagina_negada.locator(".painel-el").count() == 0
    pagina_negada.close()

    tela.verificar()


def test_adversario_50_elementos_agrupa_requisicao_por_fonte(page, base_url, credenciais_demo, painel_exemplo):
    """Refutação exigida do item: um painel com 50 elementos espalhados em só 3 fontes tem que gerar 3
    POSTs de dado por ciclo de atualização (um por FONTE), nunca 50 (um por elemento) — a prova é o
    NÚMERO DE REQUISIÇÕES de rede, não o número de linhas que o servidor executa dentro de cada uma."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)

    from app.catalogo.documento import gerar_ulid

    camada_id = painel_exemplo["camada_id"]
    fontes_ids = [gerar_ulid() for _ in range(3)]
    fontes = [
        {"id": fid, "nome": f"fonte {fid}", "camada": {"ref": camada_id}, "campos": ["categoria", "valor"], "limite": 50}
        for fid in fontes_ids
    ]
    elementos = []
    for i in range(50):
        eid = gerar_ulid()
        fonte = fontes_ids[i % 3]
        elementos.append({
            "id": eid, "tipo": "indicador", "titulo": f"e{i}", "fonte": fonte,
            "x": (i % 12), "y": i // 12, "largura": 1, "altura": 1,
            "opcoes": {"agregacao": "soma", "campo": "valor"},
        })
    corpo = {
        "grade": {"colunas": 12, "linha_px": 20}, "tema": {"modo": "claro"},
        "fontes": fontes, "elementos": elementos, "filtros": [], "parametros_url": [],
    }
    r = page.request.post(
        f"{base_url}/api/itens",
        data={"tipo": "painel", "titulo": "zt-painel-50-elementos", "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}},
    )
    assert r.ok, r.text()
    painel_id = r.json()["id"]

    requisicoes_dados = []
    page.on("request", lambda req: requisicoes_dados.append(req.url) if req.method == "POST" and "/paineis/fontes/" in req.url else None)

    tela.ir(f"/paineis/{painel_id}")
    page.wait_for_function(
        "() => document.querySelectorAll('.painel-indicador-valor').length === 50 "
        "&& [...document.querySelectorAll('.painel-el [data-papel=corpo]')].every(e => !e.hasAttribute('aria-busy'))",
        timeout=15000,
    )

    assert len(requisicoes_dados) == 3, f"esperava 3 requisições (uma por fonte), veio {len(requisicoes_dados)}: {requisicoes_dados}"
    assert len({u.rsplit('/', 2)[1] for u in requisicoes_dados}) == 3  # 3 fonte_id distintos, não 50

    tela.verificar()
    page.request.delete(f"{base_url}/api/itens/{painel_id}")
