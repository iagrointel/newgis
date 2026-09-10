"""e2e da atualização viva (item L2-06-d-atualizacao-viva-sse): o dado muda no banco e o painel mostra o
número novo SEM recarregar a página.

Prova exigida pelo portão (e refutação do item-pai). O painel de exemplo tem `atualizacao_s = 0` nas duas
fontes, ou seja, NÃO tem intervalo de atualização nenhum: se o número mudar na tela, mudou por causa do
empurrão (gatilho → NOTIFY → SSE → refetch só da fonte afetada). Confirma-se ainda que a página é a MESMA
(nenhum recarregamento aconteceu no meio) por uma marca posta no `window` antes da edição.

Roda contra a URL da PRÓPRIA trilha (uvicorn solto com TLS autoassinado); sem `--base-url` a suíte pula,
como o resto de tests/e2e."""

import time
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela

ITEM = "L2-06-d-atualizacao-viva-sse"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
ELEMENTO_SOMA = "01JPA1NEKEXEMPK0EKEM00000C"  # indicador "soma do valor" da semente (fonte de ocorrências)

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """O uvicorn da trilha usa certificado autoassinado (ver o cabeçalho de tests/e2e/test_painel.py)."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve) -> set[str]:
    """Igual ao de tests/e2e/conftest.py, com `verify=False`: o certificado do uvicorn desta trilha é
    autoassinado (mesma exceção local que tests/e2e/test_painel.py já faz; não muda o padrão da suíte)."""
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


def _conectar(env):
    """Conexão `plat_app` com o contexto de inquilino posto. A tabela física da camada tem RLS por inquilino
    (`plat.camada_preparar`): sem o contexto, o SELECT volta vazio e o UPDATE toca ZERO linhas — em silêncio,
    sem erro. Foi exatamente esse silêncio que fez este teste falhar dizendo "a soma não mudou"."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false)",
                    (str(adm["tenant_id"]), str(adm["usuario_id"])))
    return con


def _tabela(env, camada_id: str) -> tuple[str, str]:
    con = _conectar(env)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id = %s::uuid",
                        (camada_id,))
            r = cur.fetchone()
        assert r is not None, f"camada {camada_id} não visível"
        return r["s"], r["t"]
    finally:
        con.close()


def _somar_ao_primeiro(env, camada_id: str, delta: int) -> None:
    """Uma edição de verdade na tabela física da camada, em outra conexão — como faria a API de edição."""
    schema, tabela = _tabela(env, camada_id)
    con = _conectar(env)
    try:
        with con.cursor() as cur:
            cur.execute(f'UPDATE "{schema}"."{tabela}" SET valor = valor + %s '
                        f'WHERE fid = (SELECT min(fid) FROM "{schema}"."{tabela}")', (delta,))
            assert cur.rowcount == 1, f"a edição tocou {cur.rowcount} linhas (RLS ou tabela vazia)"
    finally:
        con.close()


def test_painel_reflete_a_soma_nova_sem_recarregar(page, base_url, credenciais_demo, painel_exemplo, env):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")

    soma = page.locator(f'.painel-el[data-id="{ELEMENTO_SOMA}"] .painel-indicador-valor')
    soma.wait_for(timeout=20000)
    # espera o fluxo estar DE PÉ antes de editar: editar antes da conexão abrir é uma corrida do teste, não
    # do produto (a edição de verdade acontece com o painel já aberto, e a reconexão tem o seu próprio
    # caminho — ver `aoVivo` em web/js/vivo/assinatura.js)
    page.wait_for_selector('#painel-atualizado[data-vivo="1"]', timeout=20000)
    antes = soma.inner_text().strip()
    assert antes and antes != "—", antes

    # marca a instância da página: se algum recarregamento acontecer, a marca some
    page.evaluate("() => { window.__marcaVivo = 'sem-recarregar'; }")

    delta = 12345
    _somar_ao_primeiro(env, painel_exemplo["camada_id"], delta)
    try:
        depois = antes
        limite = time.monotonic() + 25
        while time.monotonic() < limite:
            depois = soma.inner_text().strip()
            if depois != antes:
                break
            page.wait_for_timeout(250)
        assert depois != antes, f"a soma não mudou na tela em 25 s (antes={antes!r}, agora={depois!r})"
        assert page.evaluate("() => window.__marcaVivo") == "sem-recarregar", "a página recarregou"

        def numero(texto: str) -> float:
            return float(texto.replace(".", "").replace(",", "."))

        assert round(numero(depois) - numero(antes)) == delta, (antes, depois)

        marcador = page.locator("#painel-atualizado")
        assert marcador.is_visible(), "o cabeçalho não mostrou a hora da última atualização"
        assert marcador.inner_text().strip().startswith("atualizado às"), marcador.inner_text()

        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_soma_atualizada.png"), full_page=True)
    finally:
        _somar_ao_primeiro(env, painel_exemplo["camada_id"], -delta)  # a demo volta ao estado da semente
    tela.verificar()
