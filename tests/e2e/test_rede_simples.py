"""e2e da rede simples (cláusula 1 do portão do item L4-18-rede-simples-trace-network): criar uma rede simples
a partir de DUAS camadas do inquilino em ≤ 3 cliques.

Como se conta o clique, para que o número não seja retórica: o teste embrulha `page.click` e
`page.select_option` num contador e conta TODA interação com o mouse ou com um campo de escolha — escolher a
camada de linhas, escolher a de pontos e clicar no botão. Digitar nome ou abrir os ajustes não entra na conta
porque o teste NÃO os usa: a tela tem de funcionar com os valores padrão.

O que a tela faz numa chamada só (`POST /api/rede/simples`) é conferido pelo resultado que aparece nela: nº de
trechos, de junções, de nós e de arestas da topologia."""

import os
import threading
import time

import pytest
import uvicorn

from tests.e2e.apoio import RAIZ, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L4-18-rede-simples-trace-network"
SCHEMA_DADO = "d_demo"
TAB_LINHAS = "zt_l418_e2e_trechos"
TAB_PONTOS = "zt_l418_e2e_juncoes"
CAMPOS_LINHA = ["nome", "sentido"]
CAMPOS_PONTO = ["nome"]
A, B, C, D = (0.01, 0.0), (0.011, 0.0), (0.012, 0.0), (0.011, 0.001)
TRECHOS = [
    {"nome": "e1", "sentido": "jusante", "coordenadas": [A, B]},
    {"nome": "e2", "sentido": "jusante", "coordenadas": [D, B]},
    {"nome": "e3", "sentido": "jusante", "coordenadas": [B, C]},
]
PONTOS = [{"nome": n, "lon": p[0], "lat": p[1]} for n, p in (("A", A), ("B", B), ("C", C), ("D", D))]
PORTA = 8309  # porta desta trilha (o prompt do item)
URL_TESTE = f"http://127.0.0.1:{PORTA}"



@pytest.fixture(scope="session")
def base_url():
    """Servidor próprio da trilha, com os arquivos de `web/` montados em /static.

    Os e2e do repositório correm contra a URL interna servida por nginx, que é quem publica /static — e essa
    URL roda o código de `master`, não o do ramo. Para MEDIR a tela deste item é preciso subir a aplicação
    DESTE worktree; como o uvicorn sozinho não serve /static, o servidor de teste é a aplicação embrulhada
    num Starlette com `StaticFiles` na frente. Nada disso muda a aplicação: é montagem de teste."""
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import app as aplicacao
    from app.settings import settings

    # A guarda de CSRF compara o cabeçalho Origin com PLAT_URL_PUBLICA (app/auth/sessao.py). O navegador do
    # teste fala com 127.0.0.1, então sem este ajuste toda escrita da tela viria 403. Não dá para fazer isso
    # por variável de ambiente: `settings` recusa URL que não comece com https. Ajuste local do processo de
    # teste, na instância única de configuração.
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


class Contador:
    """Embrulha a página do playwright para contar cliques e escolhas."""

    def __init__(self, page):
        self.page = page
        self.n = 0
        self._click = page.click
        self._select = page.select_option

    def click(self, *a, **kw):
        self.n += 1
        return self._click(*a, **kw)

    def select_option(self, *a, **kw):
        self.n += 1
        return self._select(*a, **kw)


@pytest.fixture
def camadas_e2e(admin_api):
    """As duas camadas do inquilino demo: as tabelas no schema de dado (por psycopg2, como a ingestão faria) e
    os itens de catálogo (pela API, com o cookie do admin)."""
    import psycopg2
    import psycopg2.extras

    from tests.api.apoio_camada_teste import criar_tabela_linhas, criar_tabela_pontos

    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN no ambiente (a tela precisa de camadas de verdade no inquilino)")
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = True
    try:
        criar_tabela_linhas(con, SCHEMA_DADO, TAB_LINHAS, TRECHOS, CAMPOS_LINHA)
        criar_tabela_pontos(con, SCHEMA_DADO, TAB_PONTOS, PONTOS, CAMPOS_PONTO)
    finally:
        con.close()

    marca = sufixo()
    ids = {}
    for chave, titulo, tabela, geom, campos in (
        ("linha", f"zt-e2e-l418-linhas-{marca}", TAB_LINHAS, "MultiLineString", CAMPOS_LINHA),
        ("ponto", f"zt-e2e-l418-pontos-{marca}", TAB_PONTOS, "Point", CAMPOS_PONTO),
    ):
        r = admin_api.post("/api/itens", data={
            "tipo": "camada_vetorial", "titulo": titulo,
            "dados": {"schema": SCHEMA_DADO, "tabela": tabela, "geometria": geom, "srid": 4326,
                      "campos": [{"nome": c, "tipo": "text"} for c in campos], "fonte": "hospedada"}})
        assert r.status == 201, r.text()
        ids[chave] = (r.json()["id"], titulo)
    yield ids
    for iid, _titulo in ids.values():
        admin_api.delete(f"/api/itens/{iid}")


def test_cria_rede_simples_em_ate_tres_cliques(page, base_url, credenciais_demo, camadas_e2e, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/redes/simples")
    tela.ir("/redes/simples", "abrir_redes_simples_ms")
    assert page.title().startswith("Nova rede simples")

    contador = Contador(page)
    contador.select_option("#camada-linha", camadas_e2e["linha"][0])
    contador.select_option("#camada-ponto", camadas_e2e["ponto"][0])
    contador.click("#criar")
    page.wait_for_selector("#r-nos", timeout=30000)

    assert contador.n <= 3, f"a criação levou {contador.n} interações"
    assert page.text_content("#r-trechos").strip() == str(len(TRECHOS))
    assert page.text_content("#r-juncoes").strip() == str(len(PONTOS))
    assert page.text_content("#r-nos").strip() == "4"
    assert page.text_content("#r-arestas").strip() == str(len(TRECHOS))
    rede_id = page.get_attribute("#resultado", "data-rede-id")
    assert rede_id

    # a rede criada pela tela traça de verdade: a jusante de A alcança B e C, nunca D
    r = tela.api("POST", f"/api/rede/{rede_id}/tracar",
                 {"tipo": "jusante", "pontos_partida": [{"lon": A[0], "lat": A[1], "tolerancia_m": 1.0}]})
    assert r.status == 200, r.text()
    assert r.json()["nos_alcancados"] == 3

    tela.capturar_em = None
    tela.verificar()
    gravar = medida(ITEM)
    gravar("criar_rede_simples_cliques", contador.n, "interações",
           "bash laco/roda_teste.sh tests/e2e/test_rede_simples.py --base-url http://127.0.0.1:8309")
    gravar("abrir_redes_simples_ms", tela.medidas["abrir_redes_simples_ms"], "ms",
           "goto até body[data-pronto=1] no chromium do playwright")
    tela.api("DELETE", f"/api/rede/{rede_id}")
