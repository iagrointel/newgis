"""e2e da tela do motor AMC (item L3-01-g-tela-motor): /amc/motor sobre um modelo de CINCO fatores
(dois raster, dois polígono, um ponto) numa grade de 250 m em área de dado aberto.

Prova, no navegador de verdade, a afirmação inteira do item: mover um peso recolore o mapa e reordena a lista
SEM pedir nada ao servidor (o teste conta as requisições à API antes e depois do movimento), a explicação de
uma unidade abre com o fator a fator, o link com os pesos reabre a mesma leitura, e o link ADULTERADO (peso
999, fator inexistente, soma percentual 130) é recusado com a razão escrita — sem recolorir nada.

Como os demais e2e desta árvore, salta quando a URL pública não resolve; nesta trilha corre contra o servidor
local (`--base-url http://127.0.0.1:<porta>`). Capturas em tests/e2e/capturas/."""

from pathlib import Path

import pytest

from tests.api.amc import exemplos
from tests.e2e.apoio import Tela

ITEM = "L3-01-g-tela-motor"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
PREFIXO = "zt-amcmotorE2E"
# grade de 250 m sobre um retângulo de ~0,01° dentro do recorte do mapa-base aberto do produto
# (web/dados/basemap/guarulhos.pmtiles, OpenStreetMap sob ODbL 1.0 — a área de dado aberto que o appliance
# já traz). Fora desse recorte o mapa fica preto e a captura não prova nada. 250 m é o lado que o portão
# do item nomeia.
LADO_M = 250.0
AREA = (-46.535, -23.455, 0.01, 0.01)
BRUTOS = {"declividade": 12.0, "altitude": 700.0, "uso_urbano": 0.25, "restricao_amb": 0.20,
          "dist_acesso": 1000.0}

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
def cenario_motor(admin_api, conexao_plat_app):
    from app.amc import unidades as mod_unidades
    from tests.api.amc.test_unidades import ContextoDeTeste

    definicao = exemplos.modelo_cinco_fatores()
    definicao["nome"] = f"{PREFIXO} modelo"
    for f in definicao["fatores"]:
        f["camada"]["id"] = _criar_item(admin_api, f["id"])
    for r in definicao.get("restricoes") or []:
        r["camada"]["id"] = _criar_item(admin_api, r["id"])
    r = admin_api.post("/api/amc/modelos", data={"definicao": definicao})
    assert r.status == 201, r.text()
    modelo = r.json()

    r = admin_api.post("/api/amc/conjuntos", data={"nome": f"{PREFIXO} conjunto", "tipo": "quadrada",
                                                   "lado_m": LADO_M,
                                                   "area_estudo": exemplos.area_retangulo(*AREA)})
    assert r.status == 201, r.text()
    conjunto = r.json()
    tenant_id = _tenant_id(conexao_plat_app)
    mod_unidades.gerar_grade(ContextoDeTeste(tenant_id), conjunto["id"])

    r = admin_api.post("/api/amc/execucoes", data={"modelo_id": modelo["id"], "conjunto_id": conjunto["id"],
                                                    "semente": 9})
    assert r.status == 201, r.text()
    execucao = r.json()

    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', '0', true), "
                    "set_config('plat.login', 'e2e', true)", (str(tenant_id),))
        cur.execute("SELECT unidade_id FROM plat.amc_unidade WHERE conjunto_id = %s ORDER BY unidade_id LIMIT 6",
                    (conjunto["id"],))
        unidades = [x["unidade_id"] for x in cur.fetchall()]
        assert len(unidades) >= 4, "a grade de 250 m não gerou unidades suficientes"
        for k, u in enumerate(unidades):
            for fator, valor in BRUTOS.items():
                # o valor bruto varia por unidade para que a lista das melhores tenha ordem de verdade
                cur.execute("INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, "
                            "cobertura) VALUES (%s::uuid, %s, %s, %s, %s, 1.0)",
                            (execucao["id"], tenant_id, u, fator, valor * (1.0 + 0.15 * k)))
        cur.execute("INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, vetado, "
                    "motivo, cobertura) VALUES (%s::uuid, %s, %s, NULL, true, %s, 1.0)",
                    (execucao["id"], tenant_id, unidades[-1],
                     "vetado por precaução: unidade sobre área alagável"))
    conexao_plat_app.commit()

    yield {"modelo": modelo, "conjunto": conjunto, "execucao": execucao, "unidades": unidades}
    admin_api.delete(f"/api/amc/execucoes/{execucao['id']}")
    admin_api.delete(f"/api/amc/conjuntos/{conjunto['id']}")
    admin_api.delete(f"/api/amc/modelos/{modelo['id']}")


def _notas_da_lista(page):
    return page.eval_on_selector_all(
        "#tabela-melhores tbody tr td:nth-child(2)", "els => els.map(e => e.textContent.trim())")



def test_motor_recombina_ao_mover_peso_e_o_link_reabre_a_mesma_leitura(
        page, base_url, credenciais_demo, cenario_motor, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    eid = cenario_motor["execucao"]["id"]

    ms = tela.ir(f"/amc/motor?execucao={eid}", "pagina_pronta_ms_motor")
    page.wait_for_selector("#fatores-lista .motor-fator", timeout=20000)

    # cláusula: cinco fatores (2 raster, 2 polígono, 1 ponto) na tela
    assert page.locator("#fatores-lista .motor-fator").count() == 5
    # cláusula: veto aparece como objeto separado do peso
    assert page.locator("#vetos-lista .motor-veto").count() == 1

    page.wait_for_selector("#tabela-melhores tbody tr", timeout=20000)
    # o mapa desenha depois do 'load' do MapLibre, que é posterior a body[data-pronto=1]
    page.wait_for_function("() => Number(document.body.dataset.mapaPintado || 0) > 0", timeout=20000)
    # e enquadra as unidades: sem isto a captura sairia no enquadramento inicial, provando nada
    page.wait_for_function("() => document.body.dataset.mapaEnquadrado", timeout=20000)
    antes = _notas_da_lista(page)
    assert len([n for n in antes if n != "—"]) >= 3, antes

    # cláusula: mover um peso recombina SEM novo job e SEM ida ao servidor
    chamadas = []
    page.on("request", lambda req: chamadas.append(req.url) if "/api/" in req.url else None)
    page.fill("#peso-declividade", "9")
    page.dispatch_event("#peso-declividade", "change")
    page.wait_for_function(
        "esperado => document.querySelector('#tabela-melhores tbody tr td:nth-child(2)')"
        ".textContent.trim() !== esperado", arg=antes[0], timeout=10000)
    depois = _notas_da_lista(page)
    assert depois != antes, (antes, depois)
    assert chamadas == [], f"mover o peso foi ao servidor: {chamadas}"
    # o mapa foi repintado com as mesmas unidades (a marca é escrita por pintarMapa)
    assert int(page.evaluate("() => document.body.dataset.mapaPintado || '0'")) > 0

    # cláusula: clique = explicação, fator a fator
    page.click("#tabela-melhores tbody tr:first-child button[data-unidade]")
    page.wait_for_selector("#exp-tabela tbody tr", timeout=10000)
    assert page.locator("#exp-tabela tbody tr").count() == 5
    assert page.locator("#exp-link-servidor").count() == 1
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_explicacao.png"), full_page=False)
    page.keyboard.press("Escape")

    # cláusula: o link carrega os pesos; reabrir dá a mesma leitura
    link = page.evaluate("() => location.href")
    assert "w=" in link and "declividade%3A9" in link.replace(":", "%3A"), link
    page.goto(link, wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("#tabela-melhores tbody tr", timeout=20000)
    assert page.input_value("#peso-declividade") == "9"
    assert _notas_da_lista(page) == depois
    page.wait_for_function("() => document.body.dataset.mapaEnquadrado", timeout=20000)
    enquadrado = page.evaluate("() => document.body.dataset.mapaEnquadrado")
    assert enquadrado.startswith("-46.5"), enquadrado  # a câmera foi para as unidades, não ficou no início

    page.screenshot(path=str(CAPTURAS / f"{ITEM}_tela.png"), full_page=False)
    tela.verificar()
    erros = [c for c in tela.console if "console.error" in c or "pageerror" in c]
    assert erros == [], erros

    gravar = medida(ITEM)
    gravar("pagina_pronta_ms_motor", ms, "ms",
          "tests/e2e/test_amc_motor.py::test_motor_recombina_ao_mover_peso_e_o_link_reabre_a_mesma_leitura")
    gravar("chamadas_api_ao_mover_um_peso", 0, "requisições",
          "contadas pelo evento 'request' do playwright entre mover o controle e a lista mudar")


def test_link_com_pesos_adulterados_e_recusado_e_nada_e_calculado(
        page, base_url, credenciais_demo, cenario_motor):
    """Refutação exigida pelo item. A regra em si está provada sem navegador em
    tests/unit/test_amc_pesos_url.py; aqui prova-se que a TELA obedece: mostra a recusa e não colore nada."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    eid = cenario_motor["execucao"]["id"]

    adulterado = "declividade:999,fator_que_nao_existe:1"
    tela.ir(f"/amc/motor?execucao={eid}&w={adulterado}")
    page.wait_for_selector("#recusas-lista li", timeout=20000)
    recusas = page.eval_on_selector_all("#recusas-lista li", "els => els.map(e => e.textContent)")
    assert any("999" in t and "100" in t for t in recusas), recusas
    assert any("fator_que_nao_existe" in t for t in recusas), recusas
    # nada foi calculado: sem lista de melhores e com o mapa VAZIO (não recolorido com outros pesos)
    assert page.locator("#tabela-melhores tbody tr td.vazio").count() >= 1
    page.wait_for_function("() => document.body.dataset.mapaPintado === '0'", timeout=20000)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_link_adulterado.png"), full_page=False)

    # e o caminho de volta existe: usar os pesos do modelo destrava a tela
    page.click("#usar-pesos-do-modelo")
    page.wait_for_selector("#bloco-recusas", state="hidden", timeout=10000)
    page.wait_for_selector("#tabela-melhores tbody tr", timeout=10000)
    assert page.locator("#tabela-melhores tbody tr td.vazio").count() == 0
    page.wait_for_function("() => Number(document.body.dataset.mapaPintado || 0) > 0", timeout=20000)

    erros = [c for c in tela.console if "console.error" in c or "pageerror" in c]
    assert erros == [], erros


def test_soma_percentual_diferente_de_100_no_link_e_recusada(
        page, base_url, credenciais_demo, cenario_motor, admin_api):
    """O terceiro caso da refutação precisa de um modelo cujo combinador seja 'percentual'."""
    definicao = admin_api.get(f"/api/amc/modelos/{cenario_motor['modelo']['id']}").json()["definicao"]
    definicao["combinador"] = {"tipo": "percentual"}
    for f, peso in zip(definicao["fatores"], [20, 20, 20, 20, 20], strict=True):
        f["peso"] = peso
    r = admin_api.put(f"/api/amc/modelos/{cenario_motor['modelo']['id']}", data={"definicao": definicao})
    assert r.status == 200, r.text()
    r = admin_api.post("/api/amc/execucoes", data={"modelo_id": cenario_motor["modelo"]["id"],
                                                    "conjunto_id": cenario_motor["conjunto"]["id"],
                                                    "semente": 10})
    assert r.status == 201, r.text()
    eid = r.json()["id"]

    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/amc/motor?execucao={eid}&w=declividade:50")  # 50 + 4x20 = 130
    page.wait_for_selector("#recusas-lista li", timeout=20000)
    recusas = page.eval_on_selector_all("#recusas-lista li", "els => els.map(e => e.textContent)")
    assert any("percentual" in t and "130" in t for t in recusas), recusas
    admin_api.delete(f"/api/amc/execucoes/{eid}")


def test_celular_mostra_lista_e_mapa_em_abas(page, base_url, credenciais_demo, cenario_motor):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    page.set_viewport_size({"width": 390, "height": 844})
    tela.ir(f"/amc/motor?execucao={cenario_motor['execucao']['id']}")
    page.wait_for_selector("#abas:not([hidden])", timeout=20000)
    assert page.locator("#painel-motor").is_visible()
    assert not page.locator("#area-mapa").is_visible()
    page.click("#aba-mapa")
    assert page.locator("#area-mapa").is_visible()
    page.wait_for_function("() => document.body.dataset.mapaEnquadrado", timeout=20000)
    assert not page.locator("#painel-motor").is_visible()
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_celular_mapa.png"), full_page=False)
    page.click("#aba-lista")
    assert page.locator("#painel-motor").is_visible()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_celular_lista.png"), full_page=False)
    erros = [c for c in tela.console if "console.error" in c or "pageerror" in c]
    assert erros == [], erros
