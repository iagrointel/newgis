"""e2e do painel de explicação do motor AMC (item L3-01-f-explicacao): /amc/explicacao/<execucao_id>/<unidade_id>
renderiza a tabela fator → valor bruto → transformação → favorabilidade → peso → contribuição, com captura real
do navegador. Como os demais e2e desta árvore (ver tests/e2e/test_mapa.py), salta quando PLAT_URL_PUBLICA da
trilha não resolve (a URL de trilha é deliberadamente inválida, ver laco/trilha_ambiente.sh) — corre de verdade
em homologação/CI, onde a URL pública é real. Captura em tests/e2e/capturas/L3-01-f-explicacao_painel.png."""

from pathlib import Path

import pytest

from tests.api.amc import exemplos
from tests.api.amc.test_amc_adversario_api import contexto
from tests.e2e.apoio import Tela

ITEM = "L3-01-f-explicacao"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
PREFIXO = "zt-amcexplE2E"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _tenant_id(conexao_plat_app, slug="demo") -> int:
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
        return cur.fetchone()["tenant_id"]


def _criar_item(admin_api, titulo: str) -> str:
    r = admin_api.post("/api/itens", data={"tipo": "mapa", "titulo": f"{PREFIXO} {titulo}",
                                           "dados": {"esquema_versao": 1, "corpo": {}}})
    assert r.status == 201, r.text()
    return r.json()["id"]


@pytest.fixture
def cenario_explicacao(admin_api, conexao_plat_app):
    from app.amc import unidades as mod_unidades

    class _ContextoDeTeste:
        def __init__(self, tenant_id):
            self.tenant_id = tenant_id

    definicao = exemplos.modelo_valido()
    definicao["nome"] = f"{PREFIXO} modelo"
    definicao["fatores"][0]["camada"]["id"] = _criar_item(admin_api, "raster")
    definicao["fatores"][1]["camada"]["id"] = _criar_item(admin_api, "vias")
    definicao["restricoes"][0]["camada"]["id"] = _criar_item(admin_api, "alagavel")
    r = admin_api.post("/api/amc/modelos", data={"definicao": definicao})
    assert r.status == 201, r.text()
    modelo = r.json()

    r = admin_api.post("/api/amc/conjuntos", data={"nome": f"{PREFIXO} conjunto", "tipo": "quadrada",
                                                   "lado_m": 500.0,
                                                   "area_estudo": exemplos.area_retangulo(-49.30, -16.70, 0.01, 0.01)})
    assert r.status == 201, r.text()
    conjunto = r.json()
    tenant_id = _tenant_id(conexao_plat_app)
    mod_unidades.gerar_grade(_ContextoDeTeste(tenant_id), conjunto["id"])

    r = admin_api.post("/api/amc/execucoes", data={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"],
                                                    "semente": 3})
    assert r.status == 201, r.text()
    execucao = r.json()

    contexto(conexao_plat_app, tenant_id)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT unidade_id FROM plat.amc_unidade WHERE conjunto_id = %s LIMIT 1", (conjunto["id"],))
        unidade = cur.fetchone()["unidade_id"]
        cur.execute(
            "INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, cobertura) "
            "VALUES (%s::uuid, %s, %s, 'declividade', 12.0, 1.0), (%s::uuid, %s, %s, 'dist_via', 1000.0, 1.0)",
            (execucao["id"], tenant_id, unidade, execucao["id"], tenant_id, unidade))
        cur.execute(
            "INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, cobertura) "
            "VALUES (%s::uuid, %s, %s, 60.0, 1.0)", (execucao["id"], tenant_id, unidade))
    conexao_plat_app.commit()

    yield {"execucao": execucao, "unidade": unidade}
    admin_api.delete(f"/api/amc/execucoes/{execucao['id']}")
    admin_api.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    admin_api.delete(f"/api/amc/modelos/{modelo['id']}")


def test_painel_explicacao_mostra_tabela_e_soma(page, base_url, credenciais_demo, cenario_explicacao, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)

    execucao_id = cenario_explicacao["execucao"]["id"]
    unidade_id = cenario_explicacao["unidade"]
    tela.ir(f"/amc/explicacao/{execucao_id}/{unidade_id}", "pagina_pronta_ms_explicacao")

    page.wait_for_selector("#tabela-corpo tr", timeout=20000)
    linhas = page.locator("#tabela-corpo tr")
    assert linhas.count() >= 2  # os dois fatores do modelo de exemplo

    resumo = page.locator("#resumo-lista").inner_text()
    assert "combinador" in resumo.lower()

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho_captura = CAPTURAS / f"{ITEM}_painel.png"
    page.screenshot(path=str(caminho_captura), full_page=True)

    erros_inesperados = [c for c in tela.console if "console.error" in c or "pageerror" in c]
    assert erros_inesperados == [], erros_inesperados

    gravar = medida(ITEM)
    gravar("pagina_pronta_ms_explicacao", tela.medidas.get("pagina_pronta_ms_explicacao"), "ms",
          "tests/e2e/test_amc_explicacao.py::test_painel_explicacao_mostra_tabela_e_soma, Tela.ir")
