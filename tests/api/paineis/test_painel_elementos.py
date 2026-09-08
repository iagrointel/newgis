"""Portão do item L2-06-b-elementos-basicos: os elementos do painel pedem os seus números ao motor de agregação
do L2-06-e (`app.estatistica.agregacao`, via `app.paineis.dados`), e cada número devolvido pela API é conferido
contra SQL DIRETO na tabela da camada — a cláusula do portão e a refutação do adversário ("confere que soma/média
do indicador bate com SQL direto", "fonte com 0 linhas, campo só-nulo e categoria com 3.000 valores").

Camada de exemplo (`plat.painel_exemplo_semear`): 120 ocorrências determinísticas, 4 categorias, `valor` numeric,
`registrado_em` timestamptz, ponto em EPSG:4326. As camadas de fronteira (0 linhas, campo só-nulo, 3.000 categorias)
são criadas aqui pela mesma via da ingestão e apagadas ao fim."""

import psycopg2.extras
import pytest

from tests.api.paineis.conftest import FONTE_AGUA, FONTE_OCORRENCIAS
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-06-b-elementos-basicos"
FUSO = "America/Sao_Paulo"


def _admin(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    return ids["demo"], adm


def _tabela_exemplo(conexao_plat_app):
    _admin(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item "
            "WHERE tipo = 'camada_vetorial' AND dados->>'semente' = 'painel_exemplo' LIMIT 1"
        )
        r = cur.fetchone()
    return r["schema"], r["tabela"]


def _sql(conexao_plat_app, consulta, params=None):
    """Uma verdade só: a consulta roda direto na tabela física, fora da API."""
    schema, tabela = _tabela_exemplo(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(consulta.format(t=f'"{schema}"."{tabela}"'), params or ())
        linhas = [dict(x) for x in cur.fetchall()]
    conexao_plat_app.rollback()
    return linhas


def _pedir(sessao, painel_id, pedidos, filtro=None, fonte=FONTE_OCORRENCIAS):
    r = sessao.post(f"/api/itens/{painel_id}/paineis/fontes/{fonte}/dados",
                    json={"pedidos": pedidos, "filtro_execucao": filtro or {}})
    return r


# ---------------------------------------------------------------- indicador: toda estatística contra SQL
@pytest.mark.parametrize(
    ("estatistica", "sql"),
    [
        ("contagem", "SELECT count(*) AS v FROM {t}"),
        ("soma", "SELECT sum(valor) AS v FROM {t}"),
        ("media", "SELECT avg(valor) AS v FROM {t}"),
        ("minimo", "SELECT min(valor) AS v FROM {t}"),
        ("maximo", "SELECT max(valor) AS v FROM {t}"),
        ("contagem_distinta", "SELECT count(DISTINCT categoria) AS v FROM {t}"),
    ],
)
def test_indicador_bate_com_sql_direto(sessao_a, painel_exemplo_demo, conexao_plat_app, estatistica, sql):
    campo = "categoria" if estatistica == "contagem_distinta" else ("valor" if estatistica != "contagem" else None)
    pedido = {"agregacao": "indicador", "estatistica": estatistica}
    if campo:
        pedido["campo"] = campo
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"i": pedido})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["i"]
    assert api["tipo"] == "numero"
    esperado = _sql(conexao_plat_app, sql)[0]["v"]
    esperado = float(esperado) if esperado is not None else None
    assert api["valor"] == pytest.approx(esperado), (estatistica, api["valor"], esperado)


def test_indicador_percentil_bate_com_sql_direto(sessao_a, painel_exemplo_demo, conexao_plat_app):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"p": {"agregacao": "indicador", "estatistica": "percentil", "campo": "valor", "percentil": 90}})
    assert r.status_code == 200, r.text
    esperado = _sql(conexao_plat_app,
                    "SELECT percentile_cont(0.9) WITHIN GROUP (ORDER BY valor) AS v FROM {t}")[0]["v"]
    assert r.json()["resultados"]["p"]["valor"] == pytest.approx(float(esperado))


def test_indicador_uma_feicao_traz_a_linha_e_nao_um_agregado(sessao_a, painel_exemplo_demo, conexao_plat_app):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"f": {"agregacao": "uma_feicao", "campos": ["categoria", "valor"],
                      "ordenacao": {"campo": "valor", "direcao": "desc"}}})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["f"]
    assert api["tipo"] == "feicao"
    esperado = _sql(conexao_plat_app, "SELECT categoria, valor FROM {t} ORDER BY valor DESC LIMIT 1")[0]
    assert api["valores"]["categoria"] == esperado["categoria"]
    assert api["valores"]["valor"] == pytest.approx(float(esperado["valor"]))



def test_indicador_e_barras_batem_com_sql_em_um_painel_de_CINCO_fontes(
    sessao_a, painel_exemplo_demo, conexao_plat_app,
):
    """Cláusula literal do portão: "soma/média/contagem do indicador e das barras batem com SQL direto
    (teste com 5 fontes)". Um painel com CINCO vistas sobre a mesma camada — uma sem filtro e uma por
    categoria —, e para cada uma a contagem, a soma e a média do indicador, mais a série de barras por
    categoria, conferidas contra a MESMA consulta em SQL com o WHERE da vista."""
    categorias = [x["categoria"] for x in
                  _sql(conexao_plat_app, "SELECT DISTINCT categoria FROM {t} ORDER BY 1")]
    assert len(categorias) >= 4, categorias
    camada = {"ref": painel_exemplo_demo["camada_id"]}
    fontes = [{"id": "01JPA1NEKEXEMPK0F0NTE0001A", "nome": "todas", "camada": camada,
               "campos": ["categoria", "valor"]}]
    for i, categoria in enumerate(categorias[:4]):
        fontes.append({"id": f"01JPA1NEKEXEMPK0F0NTE0002{i}", "nome": f"só {categoria}",
                       "camada": {"ref": painel_exemplo_demo["camada_id"]}, "campos": ["categoria", "valor"],
                       "filtro": {"op": "=", "args": [{"property": "categoria"}, categoria]}})
    corpo = {"grade": {"colunas": 12, "linha_px": 36}, "fontes": fontes,
             "elementos": [{"id": f"01JPA1NEKEXEMPK0F0NTE0003{i}", "tipo": "indicador", "x": 0, "y": i,
                            "largura": 3, "altura": 3, "fonte": f["id"], "opcoes": {"agregacao": "contagem"}}
                           for i, f in enumerate(fontes)]}
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-b cinco fontes",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}})
    assert r.status_code == 201, r.text
    painel_id = r.json()["id"]
    try:
        for i, fonte in enumerate(fontes):
            onde = "" if i == 0 else " WHERE categoria = %s"
            params = () if i == 0 else (categorias[i - 1],)
            r = _pedir(sessao_a, painel_id, {
                "c": {"agregacao": "indicador", "estatistica": "contagem"},
                "s": {"agregacao": "indicador", "estatistica": "soma", "campo": "valor"},
                "m": {"agregacao": "indicador", "estatistica": "media", "campo": "valor"},
                "b": {"agregacao": "serie", "grupo": "categoria",
                      "series": [{"estatistica": "contagem"}, {"estatistica": "soma", "campo": "valor"}]},
            }, fonte=fonte["id"])
            assert r.status_code == 200, (fonte["nome"], r.text)
            res = r.json()["resultados"]
            esperado = _sql(conexao_plat_app,
                            "SELECT count(*) AS c, sum(valor) AS s, avg(valor) AS m FROM {t}" + onde, params)[0]
            assert res["c"]["valor"] == esperado["c"], fonte["nome"]
            assert res["s"]["valor"] == pytest.approx(float(esperado["s"])), fonte["nome"]
            assert res["m"]["valor"] == pytest.approx(float(esperado["m"])), fonte["nome"]
            barras = _sql(conexao_plat_app,
                          "SELECT categoria, count(*) AS c, sum(valor) AS s FROM {t}" + onde
                          + " GROUP BY 1", params)
            # compara por CATEGORIA, não por posição: com contagens empatadas a ordem entre iguais é livre
            por_categoria = {chave: (res["b"]["series"][0]["valores"][j], res["b"]["series"][1]["valores"][j])
                             for j, chave in enumerate(res["b"]["chaves"])}
            assert set(por_categoria) == {x["categoria"] for x in barras}, fonte["nome"]
            for x in barras:
                c_api, s_api = por_categoria[x["categoria"]]
                assert c_api == x["c"] and s_api == pytest.approx(float(x["s"])), (fonte["nome"], x["categoria"])
            # a soma das barras é o indicador: a tela nunca precisa somar nada
            assert sum(res["b"]["series"][0]["valores"]) == res["c"]["valor"], fonte["nome"]
        # as quatro vistas por categoria somam a vista sem filtro (prova de que os filtros não se sobrepõem)
        total = 0
        for fonte in fontes[1:]:
            r = _pedir(sessao_a, painel_id, {"c": {"agregacao": "indicador", "estatistica": "contagem"}},
                       fonte=fonte["id"])
            total += r.json()["resultados"]["c"]["valor"]
        assert total == _sql(conexao_plat_app, "SELECT count(*) AS c FROM {t}")[0]["c"]
    finally:
        sessao_a.delete(f"/api/itens/{painel_id}")


# ---------------------------------------------------------------- gráfico serial: categoria, data e séries
def test_serie_por_categoria_com_duas_series_bate_com_sql(sessao_a, painel_exemplo_demo, conexao_plat_app):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"s": {
        "agregacao": "serie", "grupo": "categoria", "ordenacao": "-s0",
        "series": [{"estatistica": "contagem"}, {"estatistica": "soma", "campo": "valor"}],
    }})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["s"]
    assert api["tipo"] == "serie" and len(api["series"]) == 2
    esperado = _sql(conexao_plat_app,
                    "SELECT categoria, count(*) AS n, sum(valor) AS s FROM {t} GROUP BY categoria ORDER BY 2 DESC")
    assert api["chaves"] == [linha["categoria"] for linha in esperado]
    assert api["series"][0]["valores"] == [linha["n"] for linha in esperado]
    assert api["series"][1]["valores"] == pytest.approx([float(linha["s"]) for linha in esperado])


def test_serie_por_mes_usa_o_fuso_do_inquilino_e_bate_com_sql(sessao_a, painel_exemplo_demo, conexao_plat_app):
    """Fronteira de mês: o agrupamento é `date_trunc('month', x AT TIME ZONE fuso)` no Postgres — o mesmo
    instante cai em meses diferentes conforme o fuso, e é o servidor que decide (o navegador nunca reagrupa)."""
    pedido = {"agregacao": "serie", "series": [{"estatistica": "contagem"}],
              "faixa_data": {"campo": "registrado_em", "granularidade": "mes", "fuso": FUSO}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"s": pedido})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["s"]
    esperado = _sql(conexao_plat_app,
                    "SELECT (date_trunc('month', registrado_em AT TIME ZONE %s) AT TIME ZONE %s) AS faixa, "
                    "count(*) AS n FROM {t} GROUP BY 1 ORDER BY 1", (FUSO, FUSO))
    assert len(api["chaves"]) == len(esperado) and api["series"][0]["valores"] == [x["n"] for x in esperado]
    # o MESMO pedido noutro fuso pode mover linhas de mês: prova de que o fuso é do servidor, não do cliente
    outro = dict(pedido)
    outro["faixa_data"] = {**pedido["faixa_data"], "fuso": "Pacific/Kiritimati"}
    r2 = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"s": outro})
    assert r2.status_code == 200, r2.text
    esperado2 = _sql(conexao_plat_app,
                     "SELECT (date_trunc('month', registrado_em AT TIME ZONE %s) AT TIME ZONE %s) AS faixa, "
                     "count(*) AS n FROM {t} GROUP BY 1 ORDER BY 1",
                     ("Pacific/Kiritimati", "Pacific/Kiritimati"))
    assert r2.json()["resultados"]["s"]["series"][0]["valores"] == [x["n"] for x in esperado2]



def test_serie_por_mes_com_filtro_de_execucao_nao_troca_o_fuso_pelo_valor_do_filtro(
    sessao_a, painel_exemplo_demo, conexao_plat_app,
):
    """Regressão do e2e do L2-06-b: gráfico por mês MAIS filtro global. Os `%s` do SQL aparecem na ordem
    SELECT (fuso, fuso), WHERE (valor do filtro), GROUP BY (fuso, fuso); montar a lista de parâmetros na
    ordem de descoberta (where primeiro) ligava o valor do filtro ao `AT TIME ZONE` e o Postgres reprovava
    com `column ... must appear in the GROUP BY clause` — o painel inteiro caía em 500 ao filtrar."""
    pedido = {"agregacao": "serie", "series": [{"estatistica": "contagem"}],
              "faixa_data": {"campo": "registrado_em", "granularidade": "mes", "fuso": FUSO}}
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"s": pedido}, filtro={"categoria": "agua"})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["s"]
    esperado = _sql(conexao_plat_app,
                    "SELECT (date_trunc('month', registrado_em AT TIME ZONE %s) AT TIME ZONE %s) AS faixa, "
                    "count(*) AS n FROM {t} WHERE categoria = %s GROUP BY 1 ORDER BY 1", (FUSO, FUSO, "agua"))
    assert api["series"][0]["valores"] == [x["n"] for x in esperado]
    assert sum(api["series"][0]["valores"]) < 120, "o filtro não recortou nada — o teste não prova o conserto"
    # filtro que não casa: série vazia, nunca erro
    r2 = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"s": pedido},
                filtro={"categoria": "nao-existe-zt"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["resultados"]["s"]["chaves"] == []


# ---------------------------------------------------------------- tabela agrupada com subtotal e total
def test_tabela_agrupada_com_subtotal_e_total_geral_batem_com_sql(sessao_a, painel_exemplo_demo, conexao_plat_app):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"t": {
        "agregacao": "grupos", "grupos": ["categoria"],
        "series": [{"estatistica": "contagem"}, {"estatistica": "media", "campo": "valor"}],
    }})
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["t"]
    assert api["tipo"] == "grupos"
    esperado = _sql(conexao_plat_app, "SELECT categoria, count(*) AS n, avg(valor) AS m FROM {t} "
                                      "GROUP BY categoria ORDER BY 2 DESC")
    assert [linha["categoria"] for linha in api["linhas"]] == [x["categoria"] for x in esperado]
    assert [linha["s0"] for linha in api["linhas"]] == [x["n"] for x in esperado]
    # o TOTAL geral é uma agregação própria, não a soma das linhas: a média geral não é a média das médias
    total_sql = _sql(conexao_plat_app, "SELECT count(*) AS n, avg(valor) AS m FROM {t}")[0]
    assert api["total"]["s0"] == total_sql["n"]
    assert api["total"]["s1"] == pytest.approx(float(total_sql["m"]))
    # (que o total é agregação PRÓPRIA, e não a média das médias, se prova onde os grupos são
    # desbalanceados — aqui os 4 têm 30 linhas cada e as duas contas coincidiriam:
    # ver test_total_nao_e_media_das_medias_em_grupos_desbalanceados)


# ---------------------------------------------------------------- lista paginada e total
def test_lista_pagina_com_total_e_sem_repetir_linha(sessao_a, painel_exemplo_demo, conexao_plat_app):
    vistos = []
    for pagina in range(3):
        r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"l": {
            "agregacao": "linhas", "campos": ["categoria", "valor"], "limite": 25,
            "deslocamento": pagina * 25, "total": True,
            "ordenacao": {"campo": "valor", "direcao": "asc"},
        }})
        assert r.status_code == 200, r.text
        api = r.json()["resultados"]["l"]
        assert api["total"] == 120 and api["limite"] == 25 and api["deslocamento"] == pagina * 25
        assert len(api["linhas"]) == 25
        vistos += [(linha["categoria"], linha["valor"]) for linha in api["linhas"]]
    esperado = _sql(conexao_plat_app, "SELECT categoria, valor FROM {t} ORDER BY valor ASC LIMIT 75")
    assert vistos == [(x["categoria"], float(x["valor"])) for x in esperado]


# ---------------------------------------------------------------- mapa: geometria e extensão como filtro
def test_mapa_traz_centroide_e_a_extensao_filtra_as_outras_fontes(sessao_a, painel_exemplo_demo, conexao_plat_app):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"m": {"agregacao": "linhas", "campos": ["categoria"], "limite": 500, "geometria": True}})
    assert r.status_code == 200, r.text
    linhas = r.json()["resultados"]["m"]["linhas"]
    assert linhas and all("__lon" in x and "__lat" in x for x in linhas)
    lons = sorted(x["__lon"] for x in linhas)
    lats = sorted(x["__lat"] for x in linhas)
    meio = [lons[0], lats[0], lons[len(lons) // 2], lats[len(lats) // 2]]
    caixa = ",".join(f"{v:.6f}" for v in meio)
    r2 = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"c": {"agregacao": "contagem"}},
                filtro={"__extensao": caixa})
    assert r2.status_code == 200, r2.text
    dentro_api = r2.json()["resultados"]["c"]["valor"]
    dentro_sql = _sql(conexao_plat_app,
                      "SELECT count(*) AS n FROM {t} WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)",
                      tuple(meio))[0]["n"]
    assert dentro_api == dentro_sql
    assert 0 < dentro_api < 120, dentro_api  # a extensão realmente recorta
    r3 = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"c": {"agregacao": "contagem"}},
                filtro={"__extensao": "-1,-1,1,1"})
    assert r3.status_code == 200 and r3.json()["resultados"]["c"]["valor"] == 0


def test_extensao_invalida_e_recusada_nomeada(sessao_a, painel_exemplo_demo):
    for valor, erro in (("1,2,3", "extensao_invalida"), ("a,b,c,d", "extensao_invalida"),
                        ("-200,0,10,10", "extensao_fora_do_mundo")):
        r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"c": {"agregacao": "contagem"}},
                   filtro={"__extensao": valor})
        assert r.status_code == 422 and r.json()["erro"] == erro, (valor, r.status_code, r.text)


# ---------------------------------------------------------------- refutação: 0 linhas, só-nulo, 3.000 categorias
@pytest.fixture
def camada_fronteira(conexao_plat_app, sessao_a):
    """Camada com os três casos do adversário na MESMA tabela: `vazio` (nenhuma linha quando filtrado),
    `so_nulo` (coluna inteira NULL) e `muitas` (3.000 categorias distintas)."""
    import uuid

    tenant_id, adm = _admin(conexao_plat_app)
    schema, tabela = "d_demo", "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT plat.camada_schema_garantir('demo')")
        cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, '
                    f'geom geometry(Point,4326), rotulo text, so_nulo numeric, grupo text, '
                    f'familia text, peso numeric)')
        cur.execute(
            f'INSERT INTO "{schema}"."{tabela}" (geom, rotulo, so_nulo, grupo, familia, peso) '
            "SELECT ST_SetSRID(ST_MakePoint(-46 + (i % 100) * 0.01, -23 + (i / 100) * 0.01), 4326), "
            "'r' || i, NULL, 'g' || i, CASE WHEN i <= 10 THEN 'a' ELSE 'b' END, i "
            "FROM generate_series(1, 3000) AS i"
        )
        cur.execute("SELECT plat.camada_preparar(%s, %s, 4326, %s, %s)", (schema, tabela, "Point", adm))
        dados = {"schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4326, "fonte": "hospedada",
                 "campos": [{"nome": "rotulo", "tipo": "text"}, {"nome": "so_nulo", "tipo": "numeric"},
                            {"nome": "grupo", "tipo": "text"}, {"nome": "familia", "tipo": "text"},
                            {"nome": "peso", "tipo": "numeric"}]}
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'inquilino', %s, %s)",
            (item_id, tenant_id, "zt L2-06-b fronteira", adm,
             psycopg2.extras.Json(dados), adm, adm),
        )
    conexao_plat_app.commit()
    # painel com uma fonte apontando para essa camada
    corpo = {"grade": {"colunas": 12, "linha_px": 36},
             "fontes": [{"id": "01JPA1NEKEXEMPK0F0NTE0000C", "nome": "fronteira",
                         "camada": {"ref": item_id},
                         "campos": ["rotulo", "so_nulo", "grupo", "familia", "peso"]}],
             "elementos": [{"id": "01JPA1NEKEXEMPK0F0NTE0000E", "tipo": "indicador", "x": 0, "y": 0,
                            "largura": 3, "altura": 3, "fonte": "01JPA1NEKEXEMPK0F0NTE0000C",
                            "opcoes": {"agregacao": "contagem"}}]}
    r = sessao_a.post("/api/itens", json={"tipo": "painel", "titulo": "zt L2-06-b fronteira",
                                          "dados": {"tipo": "painel", "esquema_versao": 3, "corpo": corpo}})
    assert r.status_code == 201, r.text
    painel_id = r.json()["id"]
    yield {"painel_id": painel_id, "fonte": "01JPA1NEKEXEMPK0F0NTE0000C", "schema": schema, "tabela": tabela}
    sessao_a.delete(f"/api/itens/{painel_id}")
    _admin(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
        cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (item_id,))
    conexao_plat_app.commit()


def test_refutacao_fonte_vazia_campo_so_nulo_e_categoria_com_3000_valores(sessao_a, camada_fronteira):
    painel_id, fonte = camada_fronteira["painel_id"], camada_fronteira["fonte"]
    # 1. fonte com 0 linhas (filtro que não casa): contagem 0, soma/média NULO — nunca zero inventado
    r = _pedir(sessao_a, painel_id, {
        "c": {"agregacao": "indicador", "estatistica": "contagem"},
        "s": {"agregacao": "indicador", "estatistica": "soma", "campo": "so_nulo"},
        "cat": {"agregacao": "serie", "grupo": "grupo", "series": [{"estatistica": "contagem"}]},
        "lin": {"agregacao": "linhas", "campos": ["rotulo"], "limite": 10, "total": True},
    }, filtro={"rotulo": "nao-existe-zt"}, fonte=fonte)
    assert r.status_code == 200, r.text
    res = r.json()["resultados"]
    assert res["c"]["valor"] == 0
    assert res["s"]["valor"] is None
    assert res["cat"]["chaves"] == [] and res["cat"]["series"][0]["valores"] == []
    assert res["lin"]["linhas"] == [] and res["lin"]["total"] == 0
    # 2. campo só-nulo: contagem de linhas 3.000, soma/média/mín/máx NULO, contagem do campo 0
    r = _pedir(sessao_a, painel_id, {
        "linhas": {"agregacao": "indicador", "estatistica": "contagem"},
        "naonulos": {"agregacao": "indicador", "estatistica": "contagem", "campo": "so_nulo"},
        "media": {"agregacao": "indicador", "estatistica": "media", "campo": "so_nulo"},
        "max": {"agregacao": "indicador", "estatistica": "maximo", "campo": "so_nulo"},
    }, fonte=fonte)
    assert r.status_code == 200, r.text
    res = r.json()["resultados"]
    assert res["linhas"]["valor"] == 3000 and res["naonulos"]["valor"] == 0
    assert res["media"]["valor"] is None and res["max"]["valor"] is None
    # 3. categoria com 3.000 valores: com limite baixo o corte é NOMEADO (422), nunca silencioso
    r = _pedir(sessao_a, painel_id,
               {"g": {"agregacao": "serie", "grupo": "grupo", "series": [{"estatistica": "contagem"}],
                      "limite": 20}}, fonte=fonte)
    assert r.status_code == 422 and r.json()["erro"] == "grupos_demais", r.text
    # com limite suficiente, vêm todas as 3.000 (o teto do motor é 10 mil grupos)
    r = _pedir(sessao_a, painel_id,
               {"g": {"agregacao": "serie", "grupo": "grupo", "series": [{"estatistica": "contagem"}],
                      "limite": 500}}, fonte=fonte)
    assert r.status_code == 422 and r.json()["erro"] == "grupos_demais"


def test_total_nao_e_media_das_medias_em_grupos_desbalanceados(sessao_a, camada_fronteira, conexao_plat_app):
    """`familia` tem 10 linhas em 'a' e 2.990 em 'b': a média geral (peso) difere muito da média das médias —
    é o que separa um total agregado no servidor de uma soma feita no navegador."""
    painel_id, fonte = camada_fronteira["painel_id"], camada_fronteira["fonte"]
    r = _pedir(sessao_a, painel_id, {"t": {
        "agregacao": "grupos", "grupos": ["familia"],
        "series": [{"estatistica": "contagem"}, {"estatistica": "media", "campo": "peso"}],
    }}, fonte=fonte)
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["t"]
    assert sorted(linha["s0"] for linha in api["linhas"]) == [10, 2990]
    medias = [float(linha["s1"]) for linha in api["linhas"]]
    media_das_medias = sum(medias) / len(medias)
    esperado = (3000 + 1) / 2  # média de 1..3000
    assert api["total"]["s1"] == pytest.approx(esperado)
    assert abs(media_das_medias - esperado) > 100, (media_das_medias, esperado)


def test_campo_fora_da_fonte_recusado_em_todo_tipo_novo(sessao_a, painel_exemplo_demo):
    for pedido in (
        {"agregacao": "indicador", "estatistica": "soma", "campo": "fid"},
        {"agregacao": "serie", "grupo": "fid", "series": [{"estatistica": "contagem"}]},
        {"agregacao": "grupos", "grupos": ["fid"], "series": [{"estatistica": "contagem"}]},
        {"agregacao": "serie", "faixa_data": {"campo": "fid", "granularidade": "mes"},
         "series": [{"estatistica": "contagem"}]},
    ):
        r = _pedir(sessao_a, painel_exemplo_demo["painel_id"], {"x": pedido})
        assert r.status_code == 422 and r.json()["erro"] == "campo_fora_da_fonte", (pedido, r.text)


def test_estatistica_desconhecida_e_nomeada(sessao_a, painel_exemplo_demo):
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"x": {"agregacao": "indicador", "estatistica": "mediana_ponderada", "campo": "valor"}})
    assert r.status_code == 422 and r.json()["erro"] == "estatistica_invalida", r.text
    assert "mediana_ponderada" in r.json()["mensagem"]


def test_fonte_com_filtro_fixo_continua_valendo_nos_tipos_novos(sessao_a, painel_exemplo_demo, conexao_plat_app):
    """A fonte `agua` tem filtro fixo `categoria = 'agua'`: a série por categoria dela só pode ter essa chave."""
    r = _pedir(sessao_a, painel_exemplo_demo["painel_id"],
               {"s": {"agregacao": "serie", "grupo": "categoria", "series": [{"estatistica": "contagem"}]}},
               fonte=FONTE_AGUA)
    assert r.status_code == 200, r.text
    api = r.json()["resultados"]["s"]
    assert api["chaves"] == ["agua"]
    esperado = _sql(conexao_plat_app, "SELECT count(*) AS n FROM {t} WHERE categoria = 'agua'")[0]["n"]
    assert api["series"][0]["valores"] == [esperado]
