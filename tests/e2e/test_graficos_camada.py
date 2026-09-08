"""e2e do item L2-01-i-graficos-de-camada na tela /mapa (chromium do playwright), sobre a bancada
`scripts/mapa_demo_camadas.py criar` (1 mi de pontos com categoria/valor; 5.000 polígonos com campos nulos):

  * os 5 tipos de gráfico desenhados a partir do painel, com captura de cada um (portão); cada barra da soma por
    categoria confere com SQL direto na tabela da camada; SVG ≤ 40 kB; a tabela oculta tem as mesmas linhas;
  * clique na barra seleciona no mapa: a contagem mostrada é a contagem da barra, é a do SQL com o mesmo filtro, e
    a camada de destaque entra no estilo do MapLibre com a expressão equivalente (portão); histograma idem por faixa;
  * o gráfico reage ao filtro digitado, ao evento plat:filtro-camada e à extensão visível;
  * exportação PNG (imagem não vazia) e CSV (mesmas linhas), gráfico guardado e reaberto após recarregar a tela;
  * refutação: campo com 3.750 categorias distintas vira N maiores + outros; campo todo nulo (filtro) dá gráfico
    vazio com mensagem; nenhuma resposta da rota de gráfico passa de 1 MB; 0 erro de console.

Não depende do Martin: a seleção é provada pela contagem do servidor e pela camada de destaque no estilo — os
tiles podem responder 404 nesta trilha (declarado em esperar_status)."""

import csv
import io
from pathlib import Path

import pytest
from PIL import Image

from tests.e2e.apoio import Tela

ITEM = "L2-01-i-graficos-de-camada"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
BANCADA = "(L2-01"
TETO_RESPOSTA = 1_000_000
TETO_SVG = 40 * 1024

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture
def mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.tamanhos = []
    page.on("response", lambda r: tela.tamanhos.append(
        (r.url, len(r.body()) if "/grafico" in r.url and r.status == 200 else 0)))
    # o servidor local (scripts/servir_local.py) não é a URL pública da trilha: a guarda de CSRF compara o Origin com
    # PLAT_URL_PUBLICA e recusaria o POST do navegador (403 origem_invalida). Como no e2e do L2-01-f, a chamada
    # de gráfico sai sem Origin — o chromium ignora a remoção de cabeçalho em continue_, por isso fetch+fulfill.
    def sem_origin(rota):
        cab = {k: v for k, v in rota.request.headers.items() if k.lower() != "origin"}
        rota.fulfill(response=rota.fetch(headers=cab))
    page.route("**/api/camadas/*/grafico", sem_origin)
    tela.entrar(slug, login, senha)
    tela.esperar_status(404, 503)  # tiles: o Martin pode não conhecer a trilha (404/503); o gráfico não depende deles
    tela.ir("/mapa", "pagina_mapa_ms")
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    titulos = page.locator(".camada-titulo").all_inner_texts()
    if not any(BANCADA in t for t in titulos):
        pytest.skip("bancada do item ausente: rode scripts/mapa_demo_camadas.py criar")
    yield tela
    page.unroute_all(behavior="ignoreErrors")


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.locator("#bloco-graficos").scroll_into_view_if_needed()
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"))


def _ligar(page, trecho):
    linha = page.locator(f'#lista-camadas li:has(.camada-titulo:text-matches("{trecho}"))').first
    caixa = linha.locator("input[type=checkbox]")
    if not caixa.is_checked():
        caixa.check()
    page.wait_for_timeout(300)
    linha.locator('button[data-acao="grafico"]').click()
    page.wait_for_timeout(200)
    return linha


def _gerar(page, tipo, campo, campo_y=None, estatistica="count", faixas=None, filtro=None, granularidade=None):
    page.select_option("#grafico-tipo", tipo)
    page.select_option("#grafico-campo", campo)
    if tipo in ("barras", "pizza", "linha"):
        page.select_option("#grafico-estatistica", estatistica)
    if campo_y:
        page.select_option("#grafico-campo-y", campo_y)
    if faixas:
        page.fill("#grafico-faixas", str(faixas))
    if granularidade:
        page.select_option("#grafico-granularidade", granularidade)
    page.fill("#grafico-filtro", filtro or "")
    page.click("#grafico-gerar")
    page.wait_for_selector("#grafico-area svg", timeout=30000)
    page.wait_for_function("() => !document.getElementById('graficos').dataset.ocupado", timeout=30000)
    return page.evaluate("() => window.plat.mapa.graficos.dados")


def _tabela(page):
    return page.evaluate("""() => {
      const t = document.getElementById('grafico-tabela');
      return { cabecalho: [...t.querySelectorAll('thead th')].map((x) => x.textContent),
               linhas: [...t.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent)),
               n: Number(t.dataset.linhas) };
    }""")


def _svg_bytes(page):
    return page.evaluate("() => new TextEncoder().encode(new XMLSerializer().serializeToString("
                         "document.querySelector('#grafico-area svg'))).length")


def _tabela_da_camada(page, titulo):
    r = page.request.get(f"{page.url.split('/mapa')[0]}/api/mapa/camadas")
    assert r.ok
    ficha = next(c for c in r.json()["camadas"] if titulo in c["titulo"])
    r = page.request.get(f"{page.url.split('/mapa')[0]}/api/itens/{ficha['id']}")
    assert r.ok, r.text()
    d = r.json()["dados"]
    return ficha["id"], f'"{d["schema"]}"."{d["tabela"]}"'


def _sql(conexao_plat_app, sql, params=()):
    """SQL direto como plat_app NO CONTEXTO do admin de demo: as tabelas da bancada têm RLS por inquilino
    (`tenant_id = plat.tenant_atual()`), sem o contexto a mesma consulta devolve zero linhas."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
                    "set_config('plat.login', 'admin', false)", (str(adm["tenant_id"]), str(adm["usuario_id"])))
        cur.execute(sql, params)
        return cur.fetchall()


def test_cinco_tipos_com_captura_e_barras_iguais_ao_sql(mapa, page, conexao_plat_app):
    _ligar(page, "1mi")
    _, tabela = _tabela_da_camada(page, "mapa-1mi")

    d = _gerar(page, "barras", "categoria", campo_y="valor", estatistica="sum")
    mao = {r["categoria"]: float(r["s"])
           for r in _sql(conexao_plat_app, f"SELECT categoria, sum(valor) AS s FROM {tabela} GROUP BY 1")}
    assert {b["chave"]: b["valor"] for b in d["series"]} == pytest.approx(mao)
    assert page.locator("#grafico-area rect.barra").count() == 4 and _svg_bytes(page) <= TETO_SVG
    tb = _tabela(page)
    assert tb["cabecalho"] == ["categoria", "n", "sum_valor"] and tb["n"] == 4 and len(tb["linhas"]) == 4
    _capturar(page, "barras")

    d = _gerar(page, "pizza", "categoria")
    contagem = {r["categoria"]: int(r["n"])
                for r in _sql(conexao_plat_app, f"SELECT categoria, count(*) AS n FROM {tabela} GROUP BY 1")}
    assert {b["chave"]: b["n"] for b in d["series"]} == contagem
    assert page.locator("#grafico-area path.fatia").count() == 4 and _svg_bytes(page) <= TETO_SVG
    _capturar(page, "pizza")

    d = _gerar(page, "histograma", "valor", faixas=10)
    assert len(d["series"]) == 10 and sum(s["n"] for s in d["series"]) == d["total"] - d["nulos"] == 1_000_000
    assert page.locator("#grafico-area rect.barra").count() == 10 and _svg_bytes(page) <= TETO_SVG
    _capturar(page, "histograma")

    d = _gerar(page, "dispersao", "valor", campo_y="valor")
    assert d["regressao"]["a"] == pytest.approx(1.0) and d["regressao"]["b"] == pytest.approx(0.0, abs=1e-6)
    assert d["regressao"]["r2"] == pytest.approx(1.0) and d["regressao"]["n"] == 1_000_000 and d["amostra"] is True
    assert page.locator("#grafico-area line.regressao").count() == 1 and _svg_bytes(page) <= TETO_SVG
    _capturar(page, "dispersao")

    # linha por data: a bancada não tem campo de data; a camada de polígonos também não — o tipo é provado no
    # navegador contra uma camada de teste com datas criada pelo próprio teste (mesmo caminho da API)
    assert page.locator("#grafico-tipo option[value=linha]").count() == 1
    assert "sem data" not in page.text_content("#grafico-saida")
    mapa.verificar()
    assert all(tam <= TETO_RESPOSTA for _, tam in mapa.tamanhos), mapa.tamanhos


def test_linha_por_data_em_camada_com_datas(mapa, page, conexao_plat_app, admin_api):
    """camada temporária em plat_trabalho com 900 linhas datadas (12 meses, 1/30 sem data) — o tipo 'linha'
    desenha uma faixa por mês, a série bate com o SQL por mês no fuso, e o clique numa faixa seleciona a contagem."""
    # nome c_*: é o padrão das camadas hospedadas e o que a ficha do mapa usa para considerar a camada servível
    # (a função de tile não existe aqui; os tiles respondem 404/503, já declarados — o gráfico não os usa)
    tabela = "c_zt_e2e_linha"
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS plat_trabalho.{tabela}")
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (fid serial PRIMARY KEY, quando timestamptz, "
                    f"valor double precision, geom geometry(Point, 4326))")
        cur.execute(f"INSERT INTO plat_trabalho.{tabela}(quando, valor, geom) "
                    f"SELECT CASE WHEN g % 30 = 0 THEN NULL ELSE "
                    f"('2026-01-01 12:00-03'::timestamptz + (g % 360) * interval '1 day') END, g % 17, "
                    f"ST_SetSRID(ST_MakePoint(-46.6 + (g % 30) * 0.001, -23.5 + (g / 30) * 0.001), 4326) "
                    f"FROM generate_series(1, 900) g")
    conexao_plat_app.commit()
    r = admin_api.post("/api/itens", data={"tipo": "camada_vetorial", "titulo": "zt e2e linha (L2-01-i)", "dados": {
        "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326, "fonte": "hospedada",
        "campos": [{"nome": "quando", "tipo": "timestamp"}, {"nome": "valor", "tipo": "double precision"}]}})
    assert r.status == 201, r.text()
    item = r.json()["id"]
    try:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page.wait_for_selector("#lista-camadas li", timeout=20000)
        # a camada existe no catálogo mas não tem função de tile: não liga na árvore (o TileJSON falha), então
        # entra no painel pelo mesmo caminho que o botão ▥ usa (abrir por id); o gráfico não precisa dos tiles
        assert page.evaluate("(id) => window.plat.mapa.graficos.abrir(id)", item) is True
        d = _gerar(page, "linha", "quando", estatistica="avg", campo_y="valor", granularidade="mes")
        mao = _sql(conexao_plat_app, f"SELECT date_trunc('month', quando AT TIME ZONE 'America/Sao_Paulo') AS f, "
                                     f"count(*) AS n, avg(valor) AS v FROM plat_trabalho.{tabela} "
                                     f"GROUP BY 1 ORDER BY 1")
        assert len(d["series"]) == len(mao) == 13 and d["nulos"] == 30
        for s, m in zip(d["series"], mao, strict=True):
            assert s["n"] == m["n"] and (m["f"] is None) == (s["chave"] is None)
            if m["f"] is not None:
                assert s["valor"] == pytest.approx(float(m["v"]))
        assert page.locator("#grafico-area circle.ponto").count() == 12 and _svg_bytes(page) <= TETO_SVG
        _capturar(page, "linha")
        page.locator("#grafico-area circle.ponto").nth(2).click()
        page.wait_for_function("() => window.plat.mapa.graficos.selecao !== null", timeout=15000)
        sel = page.evaluate("() => window.plat.mapa.graficos.selecao")
        assert sel["n"] == d["series"][2]["n"]
    finally:
        admin_api.put(f"/api/itens/{item}", data={"protegido": False})
        admin_api.delete(f"/api/itens/{item}?cascata=true")
        with conexao_plat_app.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS plat_trabalho.{tabela}")
        conexao_plat_app.commit()
    mapa.verificar()


def test_clique_na_barra_seleciona_a_mesma_contagem_no_mapa(mapa, page, conexao_plat_app):
    _ligar(page, "1mi")
    _, tabela = _tabela_da_camada(page, "mapa-1mi")
    d = _gerar(page, "barras", "categoria")
    barra = page.locator("#grafico-area rect.barra").nth(1)
    chave = barra.get_attribute("data-chave")
    esperado = next(b["n"] for b in d["series"] if b["chave"] == chave)
    barra.click()
    page.wait_for_function("() => window.plat.mapa.graficos.selecao !== null", timeout=15000)
    sel = page.evaluate("() => window.plat.mapa.graficos.selecao")
    n_sql = _sql(conexao_plat_app, f"SELECT count(*) AS n FROM {tabela} WHERE categoria = %s", (chave,))[0]["n"]
    assert sel["n"] == esperado == n_sql
    assert sel["filtro"] == f"categoria = '{chave}'" and sel["maplibre"] == ["==", ["get", "categoria"], chave]
    texto = page.text_content("#grafico-saida")
    assert f"{esperado:,}".replace(",", ".") in texto and chave in texto
    destaque = page.evaluate("""() => window.plat.mapa.map.getStyle().layers
      .filter((l) => l.id.startsWith('plat-sel-'))
      .map((l) => ({ id: l.id, filter: l.filter,
                     cor: l.paint && (l.paint['circle-color'] || l.paint['fill-color']) }))""")
    assert len(destaque) >= 1 and destaque[0]["filter"] == ["==", ["get", "categoria"], chave]
    assert destaque[0]["cor"] == "#ffd54a"
    assert page.locator("#grafico-area rect.barra[fill='#ffd54a']").count() == 1
    _capturar(page, "selecao_barra")

    # histograma: a faixa clicada seleciona o intervalo [de, ate) — e a última fecha em ate
    d = _gerar(page, "histograma", "valor", faixas=5)
    faixa = page.locator("#grafico-area rect.barra").nth(4)
    de, ate = float(faixa.get_attribute("data-de")), float(faixa.get_attribute("data-ate"))
    faixa.click()
    page.wait_for_function("() => window.plat.mapa.graficos.selecao "
                           "&& window.plat.mapa.graficos.selecao.filtro.includes('>=')", timeout=15000)
    sel = page.evaluate("() => window.plat.mapa.graficos.selecao")
    n_sql = _sql(conexao_plat_app, f"SELECT count(*) AS n FROM {tabela} WHERE valor >= %s AND valor <= %s",
                 (de, ate))[0]["n"]
    assert sel["n"] == d["series"][4]["n"] == n_sql
    _capturar(page, "selecao_histograma")

    page.click("#grafico-limpar-selecao")
    restantes = page.evaluate("() => window.plat.mapa.map.getStyle().layers"
                              ".filter((l) => l.id.startsWith('plat-sel-')).length")
    assert restantes == 0
    mapa.verificar()


def test_reage_a_filtro_extensao_e_evento_externo(mapa, page, conexao_plat_app):
    _ligar(page, "1mi")
    _, tabela = _tabela_da_camada(page, "mapa-1mi")
    d = _gerar(page, "barras", "categoria", filtro="valor > 90 AND categoria <> 'sul'")
    mao = {r["categoria"]: int(r["n"]) for r in _sql(conexao_plat_app,
           f"SELECT categoria, count(*) AS n FROM {tabela} WHERE valor > 90 AND categoria <> 'sul' GROUP BY 1")}
    assert {b["chave"]: b["n"] for b in d["series"]} == mao and len(mao) == 3
    # evento do construtor de filtro (L2-01-h) muda o filtro e regera
    page.evaluate("""() => { const id = window.plat.mapa.graficos.camadaId;
      document.dispatchEvent(new CustomEvent('plat:filtro-camada',
        { detail: { camada: id, filtro: "categoria = 'sul'" } })); }""")
    page.wait_for_function("() => window.plat.mapa.graficos.dados "
                           "&& window.plat.mapa.graficos.dados.series.length === 1", timeout=15000)
    assert page.input_value("#grafico-filtro") == "categoria = 'sul'"
    # extensão visível: enquadra um pedaço do Brasil; a contagem cai e é a do ST_Intersects com a mesma caixa
    page.fill("#grafico-filtro", "")
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-47.9, -15.8], zoom: 6 })")
    page.check("#grafico-extensao")
    # gerar() marca data-ocupado de forma síncrona: esperar pelo fim é esperar a resposta NOVA, não a anterior
    page.click("#grafico-gerar")
    page.wait_for_function("() => !document.getElementById('graficos').dataset.ocupado", timeout=30000)
    d = page.evaluate("() => window.plat.mapa.graficos.dados")
    caixa = page.evaluate("() => { const b = window.plat.mapa.map.getBounds(); "
                          "return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; }")
    n_sql = _sql(conexao_plat_app, f"SELECT count(*) AS n FROM {tabela} "
                                   f"WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))", caixa)[0]["n"]
    assert 0 < d["total"] == n_sql < 1_000_000
    # mover o mapa regera sozinho
    page.evaluate("() => window.plat.mapa.map.jumpTo({ center: [-47.9, -15.8], zoom: 4 })")
    page.wait_for_function(f"() => window.plat.mapa.graficos.dados.total > {d['total']}", timeout=30000)
    _capturar(page, "filtro_extensao")
    mapa.verificar()


def test_exporta_png_e_csv_e_guarda_por_camada(mapa, page):
    _ligar(page, "1mi")
    d = _gerar(page, "barras", "categoria", campo_y="valor", estatistica="avg")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    with page.expect_download(timeout=30000) as espera:
        page.click("#grafico-png")
    png = CAPTURAS / f"{ITEM}_exportado.png"
    espera.value.save_as(str(png))
    with Image.open(png) as im:
        assert im.size == (960, 660)
        cores = len(im.convert("RGB").getcolors(maxcolors=1_000_000) or [])
    assert cores > 20, cores
    with page.expect_download(timeout=30000) as espera:
        page.click("#grafico-csv")
    texto = Path(espera.value.path()).read_text(encoding="utf-8-sig")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert linhas[0] == ["categoria", "n", "avg_valor"] and len(linhas) == 1 + 4 + 2
    assert {linha[0] for linha in linhas[1:5]} == {b["chave"] for b in d["series"]}
    # guardar, recarregar a tela: o gráfico volta sozinho ao abrir a camada
    page.click("#grafico-salvar")
    assert page.locator("#grafico-salvos li").count() == 1
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("#lista-camadas li", timeout=20000)
    _ligar(page, "1mi")
    page.wait_for_selector("#grafico-area svg", timeout=30000)
    page.wait_for_function("() => window.plat.mapa.graficos.dados "
                           "&& window.plat.mapa.graficos.dados.estatistica === 'avg'", timeout=30000)
    assert page.locator("#grafico-area rect.barra").count() == 4
    _capturar(page, "guardado")
    mapa.verificar()


def test_refutacao_muitas_categorias_campo_nulo_e_resposta_pequena(mapa, page, conexao_plat_app):
    _ligar(page, "poligonos")
    _, tabela = _tabela_da_camada(page, "mapa-poligonos")
    distintos = _sql(conexao_plat_app, f"SELECT count(DISTINCT nome) AS n FROM {tabela}")[0]["n"]
    assert distintos >= 3000
    d = _gerar(page, "barras", "nome")
    assert len(d["series"]) == 50 and d["truncado"] is True and d["outros"]["categorias"] == distintos + 1 - 50
    assert page.locator("#grafico-area rect.barra").count() == 51 and _svg_bytes(page) <= TETO_SVG
    assert "outros" in page.text_content("#grafico-saida")
    _capturar(page, "muitas_categorias")
    # campo todo nulo dentro do filtro: gráfico vazio com mensagem, sem erro
    d = _gerar(page, "histograma", "area_ha", faixas=10, filtro="area_ha IS NULL")
    assert d["series"] == [] and d["nulos"] == d["total"] > 0
    assert "sem valores" in page.text_content("#grafico-area svg")
    d = _gerar(page, "pizza", "classe", filtro="classe IS NULL")
    assert [b["chave"] for b in d["series"]] == [None]
    _capturar(page, "campo_nulo")
    mapa.verificar()
    assert mapa.tamanhos and all(tam <= TETO_RESPOSTA for _, tam in mapa.tamanhos), max(mapa.tamanhos,
                                                                                         key=lambda x: x[1])
