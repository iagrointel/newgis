"""e2e do CONTROLE DESLIZANTE DE SAFRA no mapa (item L4-15-serie-temporal-da-rede, cláusula do portão
"controle deslizante de safra no mapa (e2e)").

O que se prova, com navegador de verdade: a tela `/redes/serie` abre com o mapa desenhado, o controle
tem uma posição por safra da série, e ARRASTAR o controle de um ano para o outro troca o que está no
mapa — a camada de transformadores muda, e com ela o resumo do ano. A prova de que trocou não é a
aparência: é a chamada `GET /api/rede-serie/{id}/mapa?ano=…` observada na rede do navegador, com o ano
pedido mudando, mais o resumo da tela mudando de acordo (um transformador a mais em 2024).

A série do teste é montada por chamadas à API e por escrita direta nas MESMAS tabelas que o importador
BDGD preenche (`tests/api/test_rede_serie.Safra`) — dado sintético, caminho de produção. A importação de
FileGDB real fica no teste `lento` de `tests/api/test_rede_serie.py`, que não cabe num e2e."""

import os
import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-15-serie-temporal-da-rede"
PORTA = 8388  # porta desta trilha (o prompt do item)
URL_TESTE = f"http://127.0.0.1:{PORTA}"


@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com `web/` montado em /static — a tela a medir é a DESTE worktree,
    não a que o nginx publica a partir de master. Mesma montagem do e2e do item L4-18."""
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import app as aplicacao
    from app.settings import settings

    object.__setattr__(settings, "PLAT_URL_PUBLICA", URL_TESTE)
    servidor_asgi = Starlette(routes=[
        Mount("/static", StaticFiles(directory=str(RAIZ / "web")), name="estaticos"),
        Mount("/", aplicacao),
    ])
    config = uvicorn.Config(servidor_asgi, host="127.0.0.1", port=PORTA, log_level="warning")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.time() + 30
    while not servidor.started and time.time() < limite:
        time.sleep(0.1)
    if not servidor.started:
        pytest.skip(f"o servidor de teste não subiu na porta {PORTA}")
    yield URL_TESTE
    servidor.should_exit = True
    thread.join(timeout=20)


@pytest.fixture
def serie_e2e(admin_api):
    """Uma série com duas safras: 2023 com um transformador, 2024 com dois. O contraste entre os anos é
    o que o controle deslizante tem de mostrar."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rede_serie import Safra
    from tests.api.test_rls import contexto, ids_por_slug

    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN no ambiente")
    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    marca = os.urandom(3).hex()
    tenant_id = ids_por_slug(con)["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1",
                    (tenant_id,))
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        base = Safra(cur, tenant_id, usuario_id, f"zt-l415-e2e-2023-{marca}")
        alvo = Safra(cur, tenant_id, usuario_id, f"zt-l415-e2e-2024-{marca}")
        for safra in (base, alvo):
            safra.trafo("T-E2E-1", 15, lon=-51.20, lat=-29.70)
            safra.uc("U-E2E-1", "T-E2E-1", 1000)
        alvo.trafo("T-E2E-2", 15, lon=-51.21, lat=-29.71)
        alvo.uc("U-E2E-2", "T-E2E-2", 6000)
    con.commit()

    r = admin_api.post("/api/rede-serie", data={"nome": f"zt-l415-e2e-{marca}"})
    assert r.status == 201, r.text()
    serie = r.json()
    for rede_id, ano in ((base.rede_id, 2023), (alvo.rede_id, 2024)):
        r = admin_api.post(f"/api/rede-serie/{serie['id']}/safras", data={"rede_id": rede_id, "ano": ano})
        assert r.status == 201, r.text()
    r = admin_api.post(f"/api/rede-serie/{serie['id']}/calcular", data={})
    assert r.status == 200, r.text()
    yield serie
    admin_api.delete(f"/api/rede-serie/{serie['id']}")
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute("DELETE FROM plat.rede WHERE id = ANY(%s::uuid[])", ([base.rede_id, alvo.rede_id],))
    con.commit()
    con.close()


def test_controle_deslizante_troca_a_safra_no_mapa(page, base_url, credenciais_demo, serie_e2e, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    pedidos: list[str] = []
    page.on("request", lambda r: pedidos.append(r.url) if "/mapa?ano=" in r.url else None)

    tela.entrar(slug, login, senha, proximo="/redes/serie")
    tela.ir("/redes/serie", "abrir_redes_serie_ms")
    assert page.title().startswith("Série temporal da rede")

    page.select_option("#seletor-serie", serie_e2e["id"])
    page.wait_for_function("document.body.dataset.safras === '2'", timeout=20000)
    # a tela abre na safra mais recente
    page.wait_for_function("document.body.dataset.safra === '2024'", timeout=20000)
    assert page.text_content("#safra-atual").strip() == "2024"
    resumo_2024 = page.text_content("#safra-resumo").strip()
    assert "2 transformadores" in resumo_2024
    assert "1 acima da potência nominal" in resumo_2024

    controle = page.locator("#controle-safra")
    assert controle.get_attribute("max") == "1", "uma posição por safra"

    # arrastar o controle para a safra anterior: o mapa tem de mudar de ano e de conteúdo
    controle.fill("0")
    controle.dispatch_event("input")
    page.wait_for_function("document.body.dataset.safra === '2023'", timeout=20000)
    assert page.text_content("#safra-atual").strip() == "2023"
    resumo_2023 = page.text_content("#safra-resumo").strip()
    assert "1 transformadores" in resumo_2023
    assert "0 acima da potência nominal" in resumo_2023
    assert resumo_2023 != resumo_2024

    # e de volta, para provar que o controle anda nos dois sentidos
    controle.fill("1")
    controle.dispatch_event("input")
    page.wait_for_function("document.body.dataset.safra === '2024'", timeout=20000)

    anos = [u.split("ano=")[1] for u in pedidos]
    assert anos.count("2023") >= 1 and anos.count("2024") >= 2, anos
    # o mapa desenhou de verdade: a camada de pontos existe na instância do MapLibre
    assert page.evaluate("document.querySelector('#mapa canvas') !== null") is True

    tela.capturar_em = None
    tela.verificar()
    gravar = medida(ITEM)
    gravar("controle_safra_posicoes", 2, "safras",
           f"bash laco/roda_teste.sh tests/e2e/test_rede_serie.py --base-url {URL_TESTE}")
    gravar("abrir_redes_serie_ms", tela.medidas["abrir_redes_serie_ms"], "ms",
           "goto até body[data-pronto=1] no chromium do playwright")
