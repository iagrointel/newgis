"""Item L5-01-c-widgets-dado no navegador: app com fonte de CAMADA (300 pontos, 3 categorias) — tabela paginada e
ordenada no servidor, gráfico agregado no servidor (barra por categoria, soma; histograma), filtro por valores
únicos COMBINADO com a seleção no mapa por mensagens (a tabela mostra a interseção), consulta por atributo,
seleção por atributo, informação da feição, lista com modelo de texto e expressão, exportação CSV que respeita o
filtro ativo (download lido) e adicionar dado temporário a uma fonte em memória. A camada vem da mesma
`FabricaCamada` dos testes de API (tabela real com RLS) e é apagada no fim."""

from __future__ import annotations

import csv
import io
import json
import secrets

import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_ogc_features_crs_cql2 import _criar_com_retentativa
from tests.api.test_rls import contexto, ids_por_slug
from tests.e2e.apoio import CAPTURAS, Tela

ITEM = "L5-01-c-widgets-dado"
N = 300
CAT = ["A", "B", "C"]


def _ulid(n: int) -> str:
    return "01K6" + str(n).zfill(22)


F1, F2, V1, V3, V2 = _ulid(1), _ulid(2), _ulid(3), _ulid(4), _ulid(5)
W = {n: _ulid(10 + i) for i, n in enumerate(["mapa", "tabela", "grafico", "hist", "filtro", "lista", "info",
    "selecao", "consulta", "adicionar", "tabela2"])}
M = {n: _ulid(30 + i) for i, n in enumerate(["filtro_v1", "filtro_v3", "mapa_v3", "consulta_v3", "grafico_v3"])}


def _categoria(i: int) -> str:
    return CAT[i % 3]


@pytest.fixture
def camada(conexao_plat_app):
    fabrica = FabricaCamada(conexao_plat_app)
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_plat_app, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"}, {"nome": "valor",
            "tipo": "double precision"}],
        geometria="Point",
    )
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (geom, nome, categoria, valor) '
            "SELECT ST_SetSRID(ST_MakePoint(-50 + (i %% 20) * 0.1, -25 + (i / 20) * 0.1), 4674), 'Ponto ' || i, "
            "(%s::text[])[1 + i %% 3], i * 1.5 FROM generate_series(1, %s) i", (CAT, N))
    conexao_plat_app.commit()
    yield {"id": item_id, "dados": dados}
    fabrica.limpar()


def _documento(camada_id: str) -> dict:
    no = lambda nome, tipo, col, lin, larg, alt, cfg: {  # noqa: E731
        "id": W[nome], "tipo": tipo, "posicao": {"coluna": col, "linha": lin, "largura": larg,
            "altura": alt}, "configuracao": cfg}
    return {
        "tipo": "app", "esquema_versao": 3,
        "corpo": {
            "nos": [
                no("mapa", "mapa", 1, 1, 6, 2, {"vista": V1, "campo_rotulo": "nome", "altura": 240}),
                no("filtro", "filtro", 7, 1, 3, 1, {"vista": V1, "campo": "categoria", "modo": "valores",
                    "rotulo": "Categoria"}),
                no("selecao", "selecao", 10, 1, 3, 1, {"vista": V1, "campo": "categoria"}),
                no("consulta", "consulta", 7, 2, 6, 1, {"vista": V3}),
                no("tabela", "tabela", 1, 3, 6, 2, {"vista": V3, "linhas_por_pagina": 10,
                                                    "colunas": [{"campo": "nome", "rotulo": "Nome"},
                                                        {"campo": "categoria", "rotulo": "Cat"}, {"campo": "valor",
                                                            "rotulo": "Valor"}]}),
                no("grafico", "grafico", 7, 3, 3, 1, {"vista": V1, "tipo": "barra", "campo": "categoria",
                    "agregacao": "soma", "campo_valor": "valor", "titulo": "soma por categoria"}),
                no("hist", "grafico", 10, 3, 3, 1, {"vista": V1, "tipo": "histograma", "campo": "valor", "faixas": 5}),
                no("lista", "lista", 7, 4, 3, 1, {"vista": V3, "modelo": "{nome} ({categoria}) {= $valor * 2 }",
                    "linhas_por_pagina": 5}),
                no("info", "info-feicao", 10, 4, 3, 1, {"vista": V3}),
                no("adicionar", "adicionar-dado", 1, 5, 6, 1, {"vista": V2}),
                no("tabela2", "tabela", 7, 5, 6, 1, {"vista": V2, "linhas_por_pagina": 10, "exportar": False}),
            ],
            "ligacoes": [],
            "fontes": [
                {"id": F1, "nome": "pontos", "origem": {"tipo": "item", "item_id": camada_id},
                 "campos": [{"nome": "nome", "tipo": "texto"}, {"nome": "categoria", "tipo": "texto"},
                     {"nome": "valor", "tipo": "decimal"}, {"nome": "geometria", "tipo": "geometria"}]},
                {"id": F2, "nome": "embutida", "origem": {"tipo": "embutida", "feicoes": [
                    {"type": "Feature", "id": 1, "properties": {"nome": "x", "k": 1}}, {"type": "Feature", "id": 2,
                        "properties": {"nome": "y", "k": 2}},
                    {"type": "Feature", "id": 3, "properties": {"nome": "z", "k": 3}}]},
                 "campos": [{"nome": "nome", "tipo": "texto"}, {"nome": "k", "tipo": "inteiro"}]},
            ],
            "vistas": [
                {"id": V1, "nome": "mapa", "fonte": F1, "filtro": None, "selecao": [], "ordenacao": [], "campos": None},
                {"id": V3, "nome": "tabela", "fonte": F1, "filtro": None, "selecao": [],
                    "ordenacao": [{"campo": "nome", "direcao": "asc"}], "campos": None},
                {"id": V2, "nome": "temporaria", "fonte": F2, "filtro": None, "selecao": [], "ordenacao": [],
                    "campos": None},
            ],
            "mensagens": [
                {"id": M["filtro_v1"], "gatilho": {"origem": W["filtro"], "evento": "filtro_mudou"},
                    "acoes": [{"alvo": V1, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
                {"id": M["filtro_v3"], "gatilho": {"origem": W["filtro"], "evento": "filtro_mudou"},
                    "acoes": [{"alvo": V3, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
                {"id": M["mapa_v3"], "gatilho": {"origem": W["mapa"], "evento": "selecao_mudou"},
                    "acoes": [{"alvo": V3, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
                {"id": M["consulta_v3"], "gatilho": {"origem": W["consulta"], "evento": "filtro_mudou"},
                    "acoes": [{"alvo": V3, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
                {"id": M["grafico_v3"], "gatilho": {"origem": W["grafico"], "evento": "filtro_mudou"},
                    "acoes": [{"alvo": V3, "acao": "filtrar", "parametros": {}, "relacao": {"tipo": "mesma_fonte"}}]},
            ],
        },
    }


_CELULA_VALOR = "() => document.querySelector(\"{tab} tbody tr td:nth-child(3)\").textContent === '{texto}'"


def _total(page, seletor):
    return int(page.get_attribute(seletor, "data-total"))


def _esperar_total(page, seletor, n, timeout=15000):
    page.wait_for_function(f"() => document.querySelector(\"{seletor}\").dataset.total === '{n}'", timeout=timeout)


def test_widgets_de_dado_sobre_camada(page, base_url, credenciais_demo, admin_api, camada, medida, tmp_path):
    tela = Tela(page, base_url)
    tela.entrar(*credenciais_demo)
    r = admin_api.post("/api/itens", data={"tipo": "app", "titulo": f"e2e widgets dado {secrets.token_hex(2)}",
        "dados": _documento(camada["id"])})
    assert r.status == 201, r.text()
    iid = r.json()["id"]
    try:
        tela.ir(f"/aplicativo?item={iid}", "pagina_pronta_ms_aplicativo_widgets_dado")
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        tab = f"plat-tabela[data-no-id='{W['tabela']}']"
        _esperar_total(page, tab, N)
        assert page.get_attribute(tab, "data-paginas") == "30" and page.get_attribute(tab, "data-linhas") == "10"
        # 1. gráfico agregado no servidor: 3 categorias, soma da B = soma de i*1.5 com i%3==1
        graf = f"plat-grafico[data-no-id='{W['grafico']}']"
        page.wait_for_selector(f"{graf}[data-pronto='1'][data-grupos='3']", timeout=15000)
        dados = page.evaluate(f"() => document.querySelector(\"{graf}\").dados")
        soma_b = sum(i * 1.5 for i in range(1, N + 1) if _categoria(i) == "B")
        assert next(g for g in dados if g["valor"] == "B")["medida"] == pytest.approx(soma_b)
        hist = f"plat-grafico[data-no-id='{W['hist']}']"
        page.wait_for_selector(f"{hist}[data-pronto='1'][data-grupos='5']", timeout=15000)
        faixas = page.evaluate(f"() => document.querySelector(\"{hist}\").dados")
        assert sum(f["n"] for f in faixas) == N and faixas[0]["de"] == 1.5 and faixas[-1]["ate"] == N * 1.5
        # 2. seleção por atributo (ids no servidor) e informação da feição
        sel = f"plat-selecao[data-no-id='{W['selecao']}']"
        page.fill(f"{sel} .selecao-cql2", "categoria = 'C'")
        page.click(f"{sel} .selecao-atributo")
        page.wait_for_function(f"() => document.querySelector(\"{sel}\").dataset.selecionados === '100'", timeout=15000)
        page.click(f"{sel} .selecao-limpar")
        page.wait_for_function(f"() => document.querySelector(\"{sel}\").dataset.selecionados === '0'", timeout=5000)
        page.click(f"{tab} tbody tr[data-id='1']")
        info = f"plat-info-feicao[data-no-id='{W['info']}']"
        page.wait_for_selector(f"{info}[data-id='1']", timeout=5000)
        assert page.text_content(f"{info} dd[data-campo='nome']") == "Ponto 1"
        # 3. lista com modelo e expressão (ordenada por nome: 'Ponto 1', 'Ponto 10', ...)
        lista = f"plat-lista[data-no-id='{W['lista']}']"
        page.wait_for_selector(f"{lista} li[data-id='1'][aria-selected='true']", timeout=5000)
        assert page.text_content(f"{lista} li[data-id='1']") == "Ponto 1 (B) 3"
        # 4. consulta por atributo -> mensagem filtra a vista da tabela
        cons = f"plat-consulta[data-no-id='{W['consulta']}']"
        page.select_option(f"{cons} .consulta-campo", "valor")
        page.select_option(f"{cons} .consulta-operador", ">")
        page.fill(f"{cons} .consulta-valor", "300")
        page.click(f"{cons} .consulta-executar")
        _esperar_total(page, tab, 100)
        page.click(f"{cons} .consulta-limpar")
        _esperar_total(page, tab, N)
        # 5. filtro por valores únicos (carregados do servidor) combinado com a seleção no mapa
        filtro = f"plat-filtro[data-no-id='{W['filtro']}']"
        page.wait_for_selector(f"{filtro}[data-valores='3']", timeout=10000)
        page.select_option(f"{filtro} select", "B")
        _esperar_total(page, tab, 100)
        page.wait_for_selector(f"{graf}[data-grupos='1']", timeout=15000)
        mapa = f"plat-mapa[data-no-id='{W['mapa']}']"
        page.click(f"{mapa} .feicao[data-id='1']")                       # B
        page.click(f"{mapa} .feicao[data-id='4']", modifiers=["Shift"])  # B
        _esperar_total(page, tab, 2)                                      # filtro (B) AND seleção {1, 4}
        assert page.text_content(f"{tab} tbody tr td:nth-child(1)") == "Ponto 1"
        page.select_option(f"{filtro} select", "C")                      # C AND {1, 4} = vazio: os filtros se combinam
        _esperar_total(page, tab, 0)
        page.select_option(f"{filtro} select", "")                       # sem filtro de categoria: só a seleção do mapa
        _esperar_total(page, tab, 2)
        page.click(f"{mapa} svg", position={"x": 2, "y": 2})           # limpa a seleção -> tira só o filtro do mapa
        _esperar_total(page, tab, N)
        page.select_option(f"{filtro} select", "B")
        _esperar_total(page, tab, 100)
        # 6. ordenar pelo cabeçalho (no servidor) e paginar
        page.click(f"{tab} th[data-campo='valor']")
        page.wait_for_selector(f"{tab} th[data-campo='valor'][aria-sort='ascending']", timeout=10000)
        page.wait_for_function(_CELULA_VALOR.format(tab=tab, texto="1,5"), timeout=10000)
        page.click(f"{tab} th[data-campo='valor']")
        page.wait_for_selector(f"{tab} th[data-campo='valor'][aria-sort='descending']", timeout=10000)
        maior_b = max(i * 1.5 for i in range(1, N + 1) if _categoria(i) == "B")
        texto_maior = str(int(maior_b)) if maior_b == int(maior_b) else f"{maior_b:.1f}".replace(".", ",")
        page.wait_for_function(_CELULA_VALOR.format(tab=tab, texto=texto_maior), timeout=10000)
        page.click(f"{tab} .tabela-proxima")
        page.wait_for_function(f"() => document.querySelector(\"{tab}\").dataset.pagina === '2'", timeout=10000)
        # 7. exportação CSV respeita o filtro ativo (categoria = B): 100 linhas + cabeçalho
        with page.expect_download(timeout=20000) as dl:
            page.click(f"{tab} .tabela-exportar-csv")
        caminho = tmp_path / "exportado.csv"
        dl.value.save_as(str(caminho))
        linhas = list(csv.reader(io.StringIO(caminho.read_text(encoding="utf-8-sig"))))
        assert linhas[0] == ["Nome", "Cat", "Valor"] and len(linhas) == 101 and {lin[1] for lin in linhas[1:]} == {"B"}
        # 8. adicionar dado temporário numa fonte em memória
        tab2 = f"plat-tabela[data-no-id='{W['tabela2']}']"
        _esperar_total(page, tab2, 3)
        add = f"plat-adicionar-dado[data-no-id='{W['adicionar']}']"
        novo = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": 9, "properties": {"nome": "novo",
            "k": 9}, "geometry": None},
                                                          {"type": "Feature", "id": 10,
                                                              "properties": {"nome": "outro",
                                                                  "k": 10}, "geometry": None}]}
        page.set_input_files(f"{add} .adicionar-arquivo", {"name": "novo.geojson", "mimeType": "application/geo+json",
            "buffer": json.dumps(novo).encode()})
        page.click(f"{add} .adicionar-carregar")
        _esperar_total(page, tab2, 5)
        assert page.get_attribute(add, "data-adicionados") == "2"
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_aplicativo.png"), full_page=True)
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (apoio.py Tela.ir)")
        p95 = page.evaluate(f"() => window.plat.widgets.fontes.get('{F1}').servidor.p95()")
        gravar("e2e_consulta_featureserver_p95_ms", round(p95, 1), "ms",
            "FonteServidor.p95() no navegador: todas as consultas ao FeatureServer durante o fluxo e2e (300 pontos)")
        gravar("e2e_widgets_dado", 1, "fluxo",
               "tests/e2e/test_widgets_dado.py: tabela, gráfico, histograma, filtro e mapa combinados, consulta, "
               "seleção, info, lista, CSV, adicionar dado")
    finally:
        admin_api.delete(f"/api/itens/{iid}")
