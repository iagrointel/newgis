"""e2e playwright do item L2-10-b-relacionamentos, contra a URL passada em --base-url.

Prova a cláusula do portão que só se prova no navegador: "popup mostra os relacionados (e2e com
captura) e navega para o registro". A classe de relacionamento (quadra 1:N lote, composto) e as
feições são gravadas pela MESMA classe `Camada`/`Inquilino` dos testes de API (tabela PostGIS de
verdade em `d_<inquilino>`, INSERT como `plat_app`), no mesmo banco que o servidor sob teste lê — o
navegador só faz o que um usuário faria: abrir a tela de domínios da quadra, clicar em "Relacionados"
na linha da quadra, ver o lote listado no popup, clicar no link e cair na tela de domínios do lote
com a linha certa destacada.

Capturas em tests/e2e/capturas/L2-10-b-relacionamentos_*.png.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import credenciais as credenciais_api
from tests.api.conftest import entrar as entrar_api
from tests.api.conftest import ligar_2fa, novo_cliente, totp_guardado, totp_guardar
from tests.api.test_dominios_subtipos import Camada, Inquilino
from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-10-b-relacionamentos"
ROTAS = ("/api/relacionamentos", "/api/camadas/{item_id}/relacionamentos",
         "/api/camadas/{item_id}/relacionados/{rel}")


class TelaRelacionamentos(Tela):
    def capturar(self, nome: str) -> Path:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Mesmo motivo do L2-10-a: o servidor da trilha é um uvicorn com certificado autoassinado."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve) -> set[str]:
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


@pytest.fixture
def api_relacionamentos(rotas_api):
    faltam = [r for r in ROTAS if r.replace("{item_id}", "{item_id}").replace("{rel}", "{rel}") not in rotas_api]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item {ITEM})")
    return rotas_api


@pytest.fixture
def superadmin(api_relacionamentos):
    c = credenciais_api()
    if "plataforma" not in c:
        pytest.skip("sem credenciais do inquilino plataforma (rode install.sh)")
    login, senha = c["plataforma"]
    cliente = novo_cliente()
    r = entrar_api(cliente, "plataforma", login, senha, totp_guardado("plataforma"))
    assert r.status_code == 200 and r.json()["ok"] is True, (r.status_code, r.text)
    if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
        segredo, _ = ligar_2fa(cliente)
        totp_guardar("plataforma", login, segredo)
    return cliente


@pytest.fixture
def cenario(superadmin, env):
    """Inquilino novo com duas camadas (quadra, lote) e uma classe 1:N composta entre elas, mais uma
    quadra com 1 lote gravado — o mínimo para o popup ter o que mostrar."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    inq = Inquilino(superadmin)
    quadras = lotes = None
    try:
        quadras = Camada(con, inq, [{"nome": "nome", "tipo": "text"}])
        lotes = Camada(con, inq, [{"nome": "quadra_globalid", "tipo": "uuid"}, {"nome": "endereco", "tipo": "text"}])
        s = inq.admin

        r = s.post("/api/relacionamentos", json={
            "origem_item_id": quadras.item_id, "destino_item_id": lotes.item_id,
            "cardinalidade": "1:N", "chave_origem": "globalid", "chave_destino": "quadra_globalid",
            "composto": True, "nome_direto": "lotes", "nome_inverso": "quadra",
        })
        assert r.status_code == 200, r.text

        quadras.contexto()
        with quadras.con.cursor() as cur:
            cur.execute(
                f"INSERT INTO {quadras.esquema}.{quadras.tabela} (geom, nome) "
                f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), 'Quadra 7 e2e') RETURNING fid, globalid"
            )
            fid_quadra, globalid_quadra = cur.fetchone().values()
        quadras.con.commit()

        lotes.contexto()
        with lotes.con.cursor() as cur:
            cur.execute(
                f"INSERT INTO {lotes.esquema}.{lotes.tabela} (geom, quadra_globalid, endereco) "
                f"VALUES (ST_SetSRID(ST_MakePoint(-46.5, -23.5), 4326), %s, 'Rua e2e, 77') RETURNING fid",
                (str(globalid_quadra),),
            )
            fid_lote = cur.fetchone()["fid"]
        lotes.con.commit()

        yield inq, quadras, lotes, fid_quadra, fid_lote
    finally:
        if lotes is not None:
            lotes.apagar()
        if quadras is not None:
            quadras.apagar()
        inq.apagar()
        con.rollback()
        con.close()


def test_popup_mostra_relacionados_e_navega_para_o_registro(page, base_url, cenario, medida):
    inq, quadras, lotes, fid_quadra, fid_lote = cenario
    tela = TelaRelacionamentos(page, base_url)
    try:
        tela.entrar(inq.slug, "admin", inq.senha, proximo=f"/camadas/{quadras.item_id}/dominios")
        tela.medidas["pagina_dominios_quadra_ms"] = tela.ir(f"/camadas/{quadras.item_id}/dominios")
        page.wait_for_selector("#tabela-feicoes tbody tr")
        tela.capturar("tabela_quadras")

        # 1. a linha da quadra tem o botão "Relacionados" (só aparece quando a camada tem classe)
        botao = f'#tabela-feicoes tbody tr[data-fid="{fid_quadra}"] button.link'
        page.wait_for_selector(botao)
        page.click(botao)

        # 2. o popup abre e mostra o lote ligado, com link para o registro
        page.wait_for_selector("#popup-relacionados dialog[open]")
        page.wait_for_selector(f'#popup-relacionados a[href*="/camadas/{lotes.item_id}/dominios?fid={fid_lote}"]')
        texto_popup = page.text_content("#popup-relacionados .relacionados-corpo") or ""
        assert "lotes (1)" in texto_popup, texto_popup
        tela.capturar("popup_relacionados")

        # 3. clicar no link navega para a tela da camada de destino, com a linha certa destacada
        link = f'#popup-relacionados a[href*="/camadas/{lotes.item_id}/dominios?fid={fid_lote}"]'
        with page.expect_navigation():
            page.click(link)
        page.wait_for_selector("body[data-pronto='1']")
        page.wait_for_selector(f'#tabela-feicoes tbody tr[data-fid="{fid_lote}"].destaque')
        tela.capturar("navegou_para_o_lote_destacado")

        grava = medida(ITEM)
        grava("popup_mostra_relacionado_e_navega", True, "bool",
             "e2e: clicar em Relacionados na quadra -> popup lista o lote -> clicar no link navega para "
             "/camadas/{lote}/dominios?fid=N com a linha .destaque")

        tela.verificar()
        for nome, valor in tela.medidas.items():
            grava(nome, valor, "ms", "playwright chromium (tests/e2e/test_relacionamentos.py) com --base-url próprio")
    finally:
        tela.sair()
