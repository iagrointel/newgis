"""e2e das INTERAÇÕES do painel (item L2-06-c-acoes-seletores-filtros-cruzados) contra o painel de
exemplo da própria trilha (uvicorn solto na porta do item, `--base-url https://127.0.0.1:8181`).

Portão medido NA TELA, com a contagem de cada cláusula conferida contra SQL direto na tabela da camada:
1. o seletor de categoria filtra indicador, gráfico, tabela e mapa ao mesmo tempo (contagens por SQL);
2. clicar numa barra do gráfico filtra a lista (o rodapé da lista mostra o total filtrado);
3. clicar numa linha da lista aproxima o mapa (zoom) e "filtrar pela extensão" muda o indicador —
   a contagem nova é o COUNT(*) dentro da caixa lida de `data-extensao`, conferida por SQL;
5. a URL copiada com o seletor aplicado reabre, noutra aba, com o mesmo seletor sem interação;
7. captura de cada estado em tests/e2e/capturas/.

Os ids dos elementos são os da semente (declaração literal em
`db/migracoes/20260909T0045_painel_seletor_mensagens.sql`): e2 indicador de ocorrências, e4 gráfico,
e5 tabela, e6 indicador de água, e7 seletor, e8 mapa, e9 lista."""

import re
from pathlib import Path

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela

ITEM = "L2-06-c-acoes-seletores-filtros-cruzados"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

E2_INDICADOR = "01JPA1NEKEXEMPK0EKEM00000B"
E4_GRAFICO = "01JPA1NEKEXEMPK0EKEM00000D"
E5_TABELA = "01JPA1NEKEXEMPK0EKEM00000E"
E6_AGUA = "01JPA1NEKEXEMPK0EKEM00000F"
E7_SELETOR = "01JPA1NEKEXEMPK0EKEM00000G"
E8_MAPA = "01JPA1NEKEXEMPK0EKEM00000H"
E9_LISTA = "01JPA1NEKEXEMPK0EKEM00000J"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """TLS autoassinado do uvicorn da trilha (ver tests/e2e/test_painel.py — mesmo arranjo)."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve):
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


def _sql(env, painel_exemplo, consulta, params=None):
    """A verdade fora da tela e fora da API: COUNT(*) direto na tabela física, numa conexão única —
    a tabela de camada tem RLS forçada por inquilino (`tenant_id = tenant_atual()`), então o contexto
    tem de estar gravado na MESMA conexão da consulta."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute("SELECT tenant_id FROM plat.auth_login('demo', 'admin')")
            tenant = cur.fetchone()["tenant_id"]
            cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(tenant),))
            cur.execute("SELECT id FROM plat.usuario WHERE ativo ORDER BY id LIMIT 1")
            cur.execute("SELECT set_config('plat.usuario_id', %s, true)", (str(cur.fetchone()["id"]),))
            cur.execute(
                "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id = %s",
                (painel_exemplo["camada_id"],),
            )
            r = cur.fetchone()
            assert r is not None, "camada da semente invisível com o contexto do inquilino demo"
            cur.execute(consulta.format(t=f'"{r["schema"]}"."{r["tabela"]}"'), params or ())
            return [dict(x) for x in cur.fetchall()]
    finally:
        con.close()


def _indicador(page, el_id) -> str:
    return page.locator(f'.painel-el[data-id="{el_id}"] .painel-indicador-valor').text_content().strip()


def _esperar_indicador(page, el_id, valor: str) -> None:
    page.wait_for_function(
        "([id, v]) => { const e = document.querySelector(`.painel-el[data-id='${id}'] "
        ".painel-indicador-valor`); return e && e.textContent.trim() === v; }",
        arg=[el_id, valor],
        timeout=15000,
    )


# ---------------------------------------------------------------- cláusula 1: o seletor filtra tudo
def test_seletor_de_categoria_filtra_indicador_grafico_tabela_e_mapa(
    page, base_url, credenciais_demo, painel_exemplo, env, medida
):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")
    page.wait_for_function(
        "() => [...document.querySelectorAll('.painel-indicador-valor')].some(e => e.textContent.trim() === '120')"
    )

    # contagens de referência, direto na tabela (cada categoria tem exatamente 30 das 120)
    n_agua = _sql(env, painel_exemplo, "SELECT count(*) AS v FROM {t} WHERE categoria = 'agua'")[0]["v"]
    n_via = _sql(env, painel_exemplo, "SELECT count(*) AS v FROM {t} WHERE categoria = 'via'")[0]["v"]
    n_pontos_agua = _sql(env, painel_exemplo,
                         "SELECT count(*) AS v FROM {t} WHERE categoria = 'agua' AND geom IS NOT NULL")[0]["v"]
    assert (n_agua, n_via) == (30, 30)

    seletor = page.locator(f'.painel-el[data-id="{E7_SELETOR}"] select.painel-seletor-controle')
    assert seletor.count() == 1
    opcoes = seletor.locator("option").all_text_contents()
    for c in ("agua", "energia", "via", "limpeza"):
        assert c in opcoes, (c, opcoes)

    # --- escolhe 'agua': indicador, gráfico, tabela e mapa mudam JUNTOS (uma mensagem, cinco alvos)
    seletor.select_option("agua")
    _esperar_indicador(page, E2_INDICADOR, "30")
    assert _indicador(page, E2_INDICADOR) == "30" == str(n_agua)
    # o indicador da fonte de água soma o filtro do seletor por atributo (30 de 30: nada some)
    _esperar_indicador(page, E6_AGUA, "30")
    barras = page.locator(f'.painel-el[data-id="{E4_GRAFICO}"] [data-chave]')
    assert barras.count() == 1 and barras.first.get_attribute("data-chave") == "agua"
    linhas_tabela = page.locator(f'.painel-el[data-id="{E5_TABELA}"] tbody tr')
    assert 1 <= linhas_tabela.count() <= 8  # max_linhas da semente
    for i in range(linhas_tabela.count()):
        primeira = linhas_tabela.nth(i).locator("td").first.text_content().strip()
        assert primeira == "agua", (i, primeira)
    pontos = page.locator(f'.painel-el[data-id="{E8_MAPA}"] circle.painel-mapa-ponto')
    assert pontos.count() == n_pontos_agua == 30
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_1_seletor_agua.png"), full_page=True)

    # --- escolhe 'via': o indicador comum vira 30, e o de água (f2 é categoria='agua') mostra ZERO —
    # o filtro cruza com o da fonte, não substitui (via ∩ agua = 0, conferido em SQL); 0 é contagem
    # legítima, não "sem dado", por isso o elemento NÃO marca data-vazio
    seletor.select_option("via")
    _esperar_indicador(page, E2_INDICADOR, "30")
    _esperar_indicador(page, E6_AGUA, "0")
    assert _indicador(page, E6_AGUA) == "0"
    assert (page.locator(f'.painel-el[data-id="{E6_AGUA}"]').get_attribute("data-vazio") or "") != "1"
    rodape = page.locator(f'.painel-el[data-id="{E5_TABELA}"] .painel-rodape-tabela').text_content().strip()
    assert re.search(r"de 30 registro\(s\)$", rodape), rodape
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_1_seletor_via_agua_vazio.png"), full_page=True)

    # --- 'todos' limpa: volta a 120/120
    seletor.select_option("")
    _esperar_indicador(page, E2_INDICADOR, "120")
    _esperar_indicador(page, E6_AGUA, "30")
    tela.verificar()
    grava = medida(ITEM)
    grava("e2e_seletor_filtra_quatro_elementos", 4, "elementos",
          "tests/e2e/test_painel_interacoes.py::test_seletor_de_categoria_filtra_indicador_grafico_tabela_e_mapa "
          "(indicador comum, indicador de água por atributo, gráfico, tabela e mapa = 5 alvos da mensagem m1)")


# ---------------------------------------------------------------- cláusula 2: barra do gráfico filtra a lista
def test_clique_na_barra_do_grafico_filtra_a_lista(page, base_url, credenciais_demo, painel_exemplo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")
    page.wait_for_function(
        "() => document.querySelectorAll('.painel-lista-item').length > 0", timeout=20000
    )
    barra = page.locator(f'.painel-el[data-id="{E4_GRAFICO}"] [data-chave="agua"]').first
    barra.click()
    # a lista tem 10 por página: com o filtro da barra o TOTAL mostrado vira 30 (todas as 'agua') —
    # espera explícita: a atualização da lista é uma requisição depois do clique, não é síncrona
    page.wait_for_function(
        "([id]) => { const r = document.querySelector(`.painel-el[data-id='${id}'] "
        ".painel-paginacao-texto`); return r && /· 30 registro\\(s\\)$/.test(r.textContent.trim()); }",
        arg=[E9_LISTA],
        timeout=15000,
    )
    texto = page.locator(f'.painel-el[data-id="{E9_LISTA}"] .painel-paginacao-texto').text_content().strip()
    assert re.search(r"· 30 registro\(s\)$", texto), texto
    barra_marca = page.locator(f'.painel-el[data-id="{E4_GRAFICO}"] [data-chave="agua"]').first
    assert "painel-selecionado" in (barra_marca.get_attribute("class") or "")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_2_barra_filtra_lista.png"), full_page=True)
    tela.verificar()


# ---------------------------------------------------------------- cláusula 3: linha da lista -> zoom -> extensão
def test_linha_da_lista_aproxima_o_mapa_e_a_extensao_filtra_o_indicador(
    page, base_url, credenciais_demo, painel_exemplo, env
):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")
    mapa = page.locator(f'.painel-el[data-id="{E8_MAPA}"] svg.painel-mapa')
    mapa.wait_for(state="visible", timeout=20000)
    extensao_antes = mapa.get_attribute("data-extensao")

    item = page.locator(f'.painel-el[data-id="{E9_LISTA}"] .painel-lista-item[data-id="0"]').first
    item.click()
    page.wait_for_function(
        "([id, antes]) => { const s = document.querySelector(`.painel-el[data-id='${id}'] svg.painel-mapa`);"
        "return s && s.getAttribute('data-extensao') && s.getAttribute('data-extensao') !== antes; }",
        arg=[E8_MAPA, extensao_antes],
        timeout=15000,
    )
    caixa_texto = mapa.get_attribute("data-extensao")
    caixa = [float(v) for v in caixa_texto.split(",")]
    assert len(caixa) == 4 and caixa[2] > caixa[0] and caixa[3] > caixa[1]
    # o mapa aproximou: a caixa nova é menor que o envelope cheio dos 120 pontos
    antes = [float(v) for v in extensao_antes.split(",")]
    assert (caixa[2] - caixa[0]) * (caixa[3] - caixa[1]) < (antes[2] - antes[0]) * (antes[3] - antes[1])

    page.locator(f'.painel-el[data-id="{E8_MAPA}"] [data-acao="filtrar-extensao"]').click()
    esperado = _sql(
        env, painel_exemplo,
        "SELECT count(*) AS v FROM {t} "
        "WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
        tuple(caixa),
    )[0]["v"]
    assert 0 < esperado < 120, esperado
    _esperar_indicador(page, E2_INDICADOR, str(esperado))
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_3_extensao_filtra_indicador.png"), full_page=True)

    # limpar a extensão devolve o painel inteiro
    page.locator(f'.painel-el[data-id="{E8_MAPA}"] [data-acao="limpar-extensao"]').click()
    _esperar_indicador(page, E2_INDICADOR, "120")
    tela.verificar()


# ---------------------------------------------------------------- cláusula 5: URL copiada reabre com o estado
def test_url_copiada_reabre_com_os_mesmos_seletores(page, context, base_url, credenciais_demo, painel_exemplo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/paineis/{painel_exemplo['painel_id']}")
    page.wait_for_function(
        "() => [...document.querySelectorAll('.painel-indicador-valor')].some(e => e.textContent.trim() === '120')"
    )
    seletor = page.locator(f'.painel-el[data-id="{E7_SELETOR}"] select.painel-seletor-controle')
    seletor.select_option("agua")
    _esperar_indicador(page, E2_INDICADOR, "30")
    url_copiada = page.url
    assert "v.v" in url_copiada, url_copiada  # parâmetro v.v:<id da vista> (estado_url.js)

    # outra aba, NENHUMA interação: só abrir a URL copiada
    pagina2 = context.new_page()
    tela2 = Tela(pagina2, base_url)
    pagina2.goto(url_copiada, wait_until="domcontentloaded")
    pagina2.wait_for_selector(".painel-el", timeout=20000)
    _esperar_indicador(pagina2, E2_INDICADOR, "30")
    seletor2 = pagina2.locator(f'.painel-el[data-id="{E7_SELETOR}"] select.painel-seletor-controle')
    assert seletor2.input_value() == "agua"
    tela2.verificar()
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina2.screenshot(path=str(CAPTURAS / f"{ITEM}_5_url_reabre.png"), full_page=True)
    pagina2.close()
    tela.verificar()
