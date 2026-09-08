"""e2e do item L2-06-b-elementos-basicos: cada elemento do painel desenhado no navegador, com CAPTURA PRÓPRIA.

Cláusulas do portão provadas aqui (as de número contra SQL direto estão em tests/api/paineis/test_painel_elementos.py):
1. cada elemento por e2e com captura — um painel com os DOZE tipos (cabeçalho, texto, indicador, indicador de uma
   feição, legenda, serial de barras com duas séries, serial de linhas por mês com fuso, pizza/rosca, tabela,
   tabela agrupada com subtotal e total, mapa, detalhes, texto rico, lista paginada), captura do painel inteiro e
   de cada elemento separadamente;
2. o número que a tela mostra é o número que o servidor mandou: a soma da coluna do gráfico de barras e o total da
   tabela agrupada são conferidos contra a contagem da própria camada (120);
3. lista de 10 mil feições paginada, com o tempo POR PÁGINA medido no navegador (portão: <= 300 ms);
4. mapa como elemento filtra os outros pela extensão: o mapa lê uma vista com filtro CQL2 (`valor < 1000`), e o
   botão "filtrar pela extensão" leva a lista das 10 mil para exatamente as 999 que caem na caixa;
5. estado "sem dado" explícito em todo elemento com fonte (filtro global que não casa) — nunca quadro em branco
   nem zero inventado; e 0 erro de console em toda a sessão.

Roda contra a URL da PRÓPRIA trilha (uvicorn com TLS autoassinado), como tests/e2e/test_painel.py:
`--base-url https://127.0.0.1:84NN`."""

import time
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.e2e.apoio import Tela, sufixo

ITEM = "L2-06-b-elementos-basicos"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

# ids ULID válidos (Crockford, sem I/L/O/U) — um por fonte e por elemento
BASE = "01JPA1NEKEXEMPK0F0NTE0000"
CHAVES = ("fonte", "fonte10k", "fonte10kbaixo", "cabecalho", "texto", "indicador", "umafeicao", "legenda",
          "barras", "linhas_mes", "pizza", "tabela", "agrupada", "mapa", "detalhes", "rico", "lista")
IDS = {nome: BASE + c for nome, c in zip(CHAVES, "0123456789ABCDEFG", strict=True)}
# elementos com fonte: os que têm de mostrar "sem dado" quando o filtro não casa
COM_FONTE = ("indicador", "umafeicao", "barras", "linhas_mes", "pizza", "tabela", "agrupada", "mapa",
             "detalhes", "rico", "lista")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """O uvicorn desta trilha usa certificado autoassinado (ver tests/e2e/test_painel.py)."""
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


def _contexto(cur, tenant_id, usuario_id, login="admin"):
    """Contexto de RLS da sessão (o mesmo que a API põe em cada requisição): sem ele, o INSERT em
    plat.item da camada de dez mil viola a política de linha do inquilino."""
    cur.execute("SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
                "set_config('plat.login', %s, false)", (str(tenant_id), str(usuario_id), login))


@pytest.fixture(scope="module")
def camadas(env):
    """A camada de exemplo da demo (120 ocorrências) e uma camada de DEZ MIL feições em grade regular:
    `valor` = i, ponto em (-46 + (i%100)/1000, -23 + (i/100)/1000) — a grade torna a extensão do mapa uma
    conta exata (as 999 primeiras linhas ocupam as 10 primeiras faixas de latitude)."""
    if not env.get("PLAT_DSN"):
        pytest.skip("sem PLAT_DSN")
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    tabela = "c_" + uuid.uuid4().hex[:16]
    item10k = str(uuid.uuid4())
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute("SELECT plat.semente_demo_habilitada() AS ligada")
            if not cur.fetchone()["ligada"]:
                pytest.skip("plat.ambiente.semear_demo = false nesta instalação")
            cur.execute("SELECT camada_id, painel_id FROM plat.painel_exemplo_semear('demo')")
            exemplo = cur.fetchone()
            cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('demo', 'admin')")
            r = cur.fetchone()
            tenant_id, adm = r["tenant_id"], r["usuario_id"]
            _contexto(cur, tenant_id, adm)
            cur.execute("SELECT plat.camada_schema_garantir('demo')")
            cur.execute(f'CREATE TABLE "d_demo"."{tabela}" (fid bigserial PRIMARY KEY, '
                        f'geom geometry(Point,4326), rotulo text, grupo text, valor numeric)')
            cur.execute(
                f'INSERT INTO "d_demo"."{tabela}" (geom, rotulo, grupo, valor) '
                "SELECT ST_SetSRID(ST_MakePoint(-46 + (i % 100) * 0.001, -23 + (i / 100) * 0.001), 4326), "
                "'linha ' || i, 'g' || (i % 5), i FROM generate_series(1, 10000) AS i"
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)", ("d_demo", tabela, "Point", adm))
            dados = {"schema": "d_demo", "tabela": tabela, "geometria": "Point", "srid": 4326,
                     "fonte": "hospedada",
                     "campos": [{"nome": "rotulo", "tipo": "text"}, {"nome": "grupo", "tipo": "text"},
                                {"nome": "valor", "tipo": "numeric"}]}
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, "
                "modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'inquilino', %s, %s)",
                (item10k, tenant_id, f"zt L2-06-b dez mil {sufixo()}", adm,
                 psycopg2.extras.Json(dados), adm, adm))
        con.commit()
        yield {"camada_id": str(exemplo["camada_id"]), "camada10k": item10k, "tabela10k": tabela}
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('demo', 'admin')")
            r = cur.fetchone()
            _contexto(cur, r["tenant_id"], r["usuario_id"])
            cur.execute(f'DROP TABLE IF EXISTS "d_demo"."{tabela}" CASCADE')
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (item10k,))
        con.commit()
    finally:
        con.close()


def _el(chave, tipo, x, y, w, h, titulo, opcoes, fonte):
    e = {"id": IDS[chave], "tipo": tipo, "x": x, "y": y, "largura": w, "altura": h, "titulo": titulo,
         "opcoes": opcoes}
    if fonte:
        e["fonte"] = IDS[fonte]
    return e


def _documento(camada_id: str, camada10k: str) -> dict:
    return {
        "tipo": "painel", "esquema_versao": 3,
        "corpo": {
            "grade": {"colunas": 12, "linha_px": 36},
            "tema": {"modo": "claro"},
            "fontes": [
                {"id": IDS["fonte"], "nome": "ocorrências", "camada": {"ref": camada_id},
                 "campos": ["categoria", "valor", "registrado_em", "descricao"], "limite": 200},
                {"id": IDS["fonte10k"], "nome": "dez mil", "camada": {"ref": camada10k},
                 "campos": ["rotulo", "grupo", "valor"], "limite": 1000},
                {"id": IDS["fonte10kbaixo"], "nome": "dez mil (valor < 1000)", "camada": {"ref": camada10k},
                 "campos": ["rotulo", "grupo", "valor"], "limite": 1000,
                 "filtro": {"op": "<", "args": [{"property": "valor"}, 1000]}},
            ],
            "filtros": [
                {"id": BASE + "H", "campo": "categoria", "tipo": "categoria", "titulo": "categoria"},
                {"id": BASE + "J", "campo": "grupo", "tipo": "categoria", "titulo": "grupo"},
            ],
            "elementos": [
                _el("cabecalho", "cabecalho", 0, 0, 12, 2, "",
                    {"titulo": "Painel de elementos", "subtitulo": "todos os tipos do L2-06-b",
                     "mostrar_atualizacao": True}, None),
                _el("texto", "texto", 0, 2, 3, 3, "texto",
                    {"texto": "elemento de texto simples, sem fonte de dado"}, None),
                _el("indicador", "indicador", 3, 2, 3, 3, "soma do valor",
                    {"estatistica": "soma", "campo": "valor", "casas": 0, "sufixo": "un",
                     "faixas": [{"ate": 100, "cor": "#c0392b"}, {"de": 100, "cor": "#2f7d5b"}]}, "fonte"),
                _el("umafeicao", "indicador", 6, 2, 3, 3, "maior valor",
                    {"modo": "uma_feicao", "campo": "valor", "campos": ["categoria", "valor"],
                     "campos_detalhe": ["categoria", "valor"],
                     "ordenacao": {"campo": "valor", "direcao": "desc"}}, "fonte"),
                _el("legenda", "legenda", 9, 2, 3, 3, "legenda",
                    {"itens": [{"rotulo": "água", "cor": "#5b8fd9"},
                               {"rotulo": "energia", "cor": "#d98a2b"}]}, None),
                _el("barras", "serial", 0, 5, 6, 6, "por categoria",
                    {"forma": "barras", "grupo": "categoria",
                     "series": [{"estatistica": "contagem", "rotulo": "ocorrências"},
                                {"estatistica": "soma", "campo": "valor", "rotulo": "soma do valor"}]}, "fonte"),
                _el("linhas_mes", "serial", 6, 5, 6, 6, "por mês",
                    {"forma": "linhas",
                     "faixa_data": {"campo": "registrado_em", "granularidade": "mes",
                                    "fuso": "America/Sao_Paulo"},
                     "series": [{"estatistica": "contagem", "rotulo": "ocorrências"}]}, "fonte"),
                _el("pizza", "pizza", 0, 11, 4, 6, "fatias por categoria",
                    {"grupo": "categoria", "estatistica": "contagem", "rosca": True}, "fonte"),
                _el("tabela", "tabela", 4, 11, 4, 6, "linhas",
                    {"campos": ["categoria", "valor"], "max_linhas": 10}, "fonte"),
                _el("agrupada", "tabela", 8, 11, 4, 6, "por categoria (com total)",
                    {"grupos": ["categoria"],
                     "series": [{"estatistica": "contagem", "rotulo": "n"},
                                {"estatistica": "media", "campo": "valor", "rotulo": "média"}]}, "fonte"),
                _el("mapa", "mapa", 0, 17, 6, 7, "mapa (valor < 1000)",
                    {"campos": ["rotulo", "valor"], "max_pontos": 1000,
                     "modelo_titulo": "{rotulo}"}, "fonte10kbaixo"),
                _el("detalhes", "detalhes", 6, 17, 3, 7, "detalhes",
                    {"campos": ["categoria", "valor", "descricao"],
                     "ordenacao": {"campo": "valor", "direcao": "desc"}}, "fonte"),
                _el("rico", "texto_rico", 9, 17, 3, 7, "texto rico",
                    {"texto": "**maior valor**: {valor} em *{categoria}*",
                     "campos": ["categoria", "valor"],
                     "ordenacao": {"campo": "valor", "direcao": "desc"}}, "fonte"),
                _el("lista", "lista", 0, 24, 12, 8, "lista de dez mil",
                    {"campos": ["rotulo", "grupo", "valor"], "por_pagina": 25, "icone": "•",
                     "modelo_titulo": "{rotulo}", "modelo_detalhe": "grupo {grupo} · valor {valor}",
                     "ordenacao": {"campo": "valor", "direcao": "asc"}}, "fonte10k"),
            ],
        },
    }


@pytest.fixture
def painel(page, base_url, credenciais_demo, camadas):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    r = tela.api("POST", "/api/itens", {"tipo": "painel", "titulo": f"zt L2-06-b {sufixo()}",
                                        "dados": _documento(camadas["camada_id"], camadas["camada10k"])})
    assert r.status == 201, r.text()
    painel_id = r.json()["id"]
    yield {"tela": tela, "id": painel_id, **camadas}
    tela.api("DELETE", f"/api/itens/{painel_id}")


def _capturar(page, nome, larguras=(1280,)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def caixa(page, chave):
    return page.locator(f'.painel-el[data-id="{IDS[chave]}"]')


def _texto(page, chave):
    return caixa(page, chave).inner_text()


def _esperar_pintado(page, chaves=COM_FONTE, vazio="0"):
    """Espera cada elemento com fonte declarar o estado esperado; ao estourar, diz QUAL elemento ficou para
    trás e com que texto (diagnóstico legível em vez de "timeout")."""
    try:
        page.wait_for_function(
            "([ids, v]) => ids.every((id) => { const e = document.querySelector(`.painel-el[data-id='${id}']`);"
            " return e && e.dataset.vazio === v; })",
            arg=[[IDS[k] for k in chaves], vazio], timeout=40000)
    except Exception:
        estado = {k: (caixa(page, k).get_attribute("data-vazio"), caixa(page, k).inner_text()[:120])
                  for k in chaves}
        faltam = {k: v for k, v in estado.items() if v[0] != vazio}
        raise AssertionError(f"elementos que não chegaram a data-vazio={vazio}: {faltam}") from None


def test_todos_os_elementos_desenham_com_os_numeros_do_servidor(page, painel, medida):
    tela = painel["tela"]
    tela.ir(f"/paineis/{painel['id']}", "pagina_pronta_ms_painel_elementos")
    _esperar_pintado(page)
    desenhados = []

    # 1. cabeçalho: título, subtítulo e hora da atualização
    texto = _texto(page, "cabecalho")
    assert "Painel de elementos" in texto and "atualizado" in texto, texto
    desenhados.append("cabecalho")

    # 2. texto simples e legenda (elementos sem fonte)
    assert "texto simples" in _texto(page, "texto")
    assert caixa(page, "legenda").locator("li").count() == 2
    desenhados += ["texto", "legenda"]

    # 3. indicador: formato com sufixo e cor da faixa aplicada pelo valor
    valor = caixa(page, "indicador").locator(".painel-indicador-valor")
    assert "un" in valor.inner_text(), valor.inner_text()
    assert "color" in (valor.get_attribute("style") or ""), valor.get_attribute("style")
    desenhados.append("indicador")

    # 4. indicador de UMA FEIÇÃO: o maior valor, com a tabela dos campos da feição
    umafeicao = caixa(page, "umafeicao")
    assert umafeicao.locator("table tbody tr").count() == 2
    desenhados.append("indicador_uma_feicao")

    # 5. serial de barras com DUAS séries + tabela equivalente ligada por aria-describedby; a soma da coluna
    #    de contagem é a contagem da camada inteira (120), isto é: o número da tela é o do servidor
    svg = caixa(page, "barras").locator("svg.grafico")
    assert svg.locator("rect.barra[data-serie='1']").count() > 0, "segunda série não desenhou"
    descrito = svg.get_attribute("aria-describedby")
    assert descrito and page.locator(f"#{descrito}").count() == 1
    linhas = page.locator(f"#{descrito} tbody tr")
    assert linhas.count() == 4, linhas.count()
    # a tabela equivalente abre num <details> — abre-se aqui, que é como quem lê a tela confere os números
    caixa(page, "barras").locator("details.painel-equivalente summary").first.click()
    contagens = [int(v.replace(".", "")) for v in
                 page.locator(f"#{descrito} tbody tr td:nth-child(2)").all_inner_texts()]
    assert sum(contagens) == 120, contagens
    desenhados.append("serial_barras")

    # 6. serial de LINHAS por mês (faixa de data com fuso do inquilino, agrupada no servidor)
    assert caixa(page, "linhas_mes").locator("svg.grafico path.linha").count() >= 1
    desenhados.append("serial_linhas_mes")

    # 7. pizza/rosca: uma fatia por categoria
    assert caixa(page, "pizza").locator("svg path.fatia").count() == 4
    desenhados.append("pizza")

    # 8. tabela simples (10 linhas de 120) e tabela AGRUPADA com subtotal por grupo e total conferido
    assert caixa(page, "tabela").locator("tbody tr").count() == 10
    assert "de 120" in caixa(page, "tabela").locator(".painel-rodape-tabela").inner_text()
    agrupada = caixa(page, "agrupada")
    assert agrupada.locator("tbody tr").count() == 4
    subtotais = [int(v.replace(".", "")) for v in
                 agrupada.locator("tbody tr td.num:nth-child(2)").all_inner_texts()]
    total = agrupada.locator("tfoot td.num").first.inner_text()
    assert int(total.replace(".", "")) == 120 == sum(subtotais), (total, subtotais)
    desenhados += ["tabela", "tabela_agrupada"]

    # 9. mapa (pontos com centroide vindo do servidor), detalhes e texto rico com {campos}
    assert caixa(page, "mapa").locator("svg.painel-mapa circle").count() > 0
    assert caixa(page, "detalhes").locator("dt").count() == 3
    rico = caixa(page, "rico")
    assert "maior valor" in rico.inner_text() and rico.locator("strong").count() == 1
    desenhados += ["mapa", "detalhes", "texto_rico"]

    # 10. lista paginada das dez mil
    lista = caixa(page, "lista")
    assert lista.locator("li.painel-lista-item").count() == 25
    assert "10.000" in lista.inner_text(), lista.inner_text()
    desenhados.append("lista")

    # captura do painel inteiro (larga e estreita) e UMA CAPTURA POR ELEMENTO
    _capturar(page, "painel", (1280, 390))
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for chave in CHAVES[3:]:
        caixa(page, chave).screenshot(path=str(CAPTURAS / f"{ITEM}_elemento_{chave}.png"))

    tela.verificar()
    gravar = medida(ITEM)
    gravar("elementos_desenhados", len(desenhados), "elementos", "; ".join(desenhados))
    gravar("capturas_por_elemento", len(CHAVES[3:]), "capturas",
           f"tests/e2e/capturas/{ITEM}_elemento_*.png")
    for nome, v in tela.medidas.items():
        gravar(nome, v, "ms", "goto até body[data-pronto=1] no chromium do playwright")


def test_lista_de_dez_mil_pagina_dentro_de_300_ms_por_pagina(page, painel, medida):
    tela = painel["tela"]
    tela.ir(f"/paineis/{painel['id']}")
    lista = caixa(page, "lista")
    page.wait_for_selector(f'.painel-el[data-id="{IDS["lista"]}"] li.painel-lista-item', timeout=40000)
    assert "10.000" in lista.inner_text()
    primeiro = lista.locator(".painel-lista-titulo").first.inner_text()
    tempos = []
    for pagina in range(2, 8):
        t0 = time.perf_counter()
        lista.locator("button[data-acao='proxima']").click()
        page.wait_for_function(
            "([id, p]) => (document.querySelector(`.painel-el[data-id='${id}'] .painel-paginacao-texto`)"
            "?.textContent || '').startsWith(`página ${p} `)", arg=[IDS["lista"], pagina], timeout=20000)
        tempos.append(round((time.perf_counter() - t0) * 1000, 1))
    assert lista.locator("li.painel-lista-item").count() == 25
    assert lista.locator(".painel-lista-titulo").first.inner_text() != primeiro
    _capturar(page, "lista_paginada")
    lista.locator("button[data-acao='anterior']").click()
    page.wait_for_function(
        "(id) => (document.querySelector(`.painel-el[data-id='${id}'] .painel-paginacao-texto`)"
        "?.textContent || '').startsWith('página 6 ')", arg=IDS["lista"], timeout=20000)
    tela.verificar()

    ordenados = sorted(tempos)
    p95 = ordenados[max(0, round(0.95 * len(ordenados)) - 1)]
    gravar = medida(ITEM)
    gravar("lista_10mil_pagina_ms_p95", p95, "ms",
           "clique em 'próxima' até a página seguinte pintada; lista de 10.000 feições, 6 páginas medidas "
           "no navegador (tests/e2e/test_painel_elementos.py)")
    gravar("lista_10mil_pagina_ms_max", max(tempos), "ms", "pior página da mesma medição")
    assert p95 <= 300, tempos


def test_mapa_como_elemento_filtra_os_outros_pela_extensao(page, painel, medida):
    """O mapa lê a vista `valor < 1000` (999 pontos numa grade regular); a extensão desses pontos, aplicada
    como filtro do painel, leva a lista das 10 mil às MESMAS 999 — a conta é exata por construção da grade."""
    tela = painel["tela"]
    tela.ir(f"/paineis/{painel['id']}")
    _esperar_pintado(page)
    lista = caixa(page, "lista")
    assert "10.000" in lista.inner_text()
    caixa(page, "mapa").locator("button[data-acao='filtrar-extensao']").click()
    page.wait_for_function(
        "(id) => (document.querySelector(`.painel-el[data-id='${id}'] .painel-paginacao-texto`)"
        "?.textContent || '').includes('999 registro(s)')", arg=IDS["lista"], timeout=30000)
    assert page.locator("#painel-grade").get_attribute("data-extensao"), "a extensão não entrou no filtro"
    _capturar(page, "extensao_filtra")
    caixa(page, "mapa").locator("button[data-acao='limpar-extensao']").click()
    page.wait_for_function(
        "(id) => (document.querySelector(`.painel-el[data-id='${id}'] .painel-paginacao-texto`)"
        "?.textContent || '').includes('10.000 registro(s)')", arg=IDS["lista"], timeout=30000)
    tela.verificar()
    medida(ITEM)("extensao_do_mapa_linhas", 999, "feições",
                 "lista de 10.000 recortada pela extensão dos 999 pontos do mapa (vista valor < 1000)")


def test_sem_dado_explicito_em_todo_elemento_com_fonte(page, painel):
    """Filtro global que não casa em nenhuma das duas camadas: todo elemento com fonte mostra "sem dado" —
    nunca um quadro em branco, nunca um zero inventado (refutação do adversário)."""
    tela = painel["tela"]
    tela.ir(f"/paineis/{painel['id']}")
    _esperar_pintado(page)
    page.fill(f"#painel-filtro-{BASE}H", "nao-existe-zt")
    page.fill(f"#painel-filtro-{BASE}J", "nao-existe-zt")
    _esperar_pintado(page, vazio="1")
    for chave in COM_FONTE:
        assert caixa(page, chave).locator(".painel-sem-dado").count() == 1, chave
    _capturar(page, "sem_dado")
    tela.verificar()
