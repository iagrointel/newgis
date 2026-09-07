"""Tabela de atributos por camada (item L2-01-g-tabela-atributos), contra Postgres real.

A camada de teste é montada pelo MESMO caminho físico da ingestão: tabela em `d_demo` (schema do inquilino,
migração 029) preparada por `plat.camada_preparar()` — a função de produção que instala a RLS FORCE, o índice
GIST, os gatilhos de versão e as colunas obrigatórias — e publicada como item `camada_vetorial` pela API do
catálogo. O que NÃO se usa aqui é o job de ingestão (ogr2ogr): ele exige um trabalhador em execução, que a
base de trilha não tem, e o que este item precisa provar é a leitura da tabela, não o carregamento dela.

Cada teste cria a sua tabela com nome aleatório e a solta no fim. `d_demo` é compartilhado entre trilhas: nada
é apagado por padrão de nome, só o nome exato que este teste criou nesta rodada.

Os testes de contagem e estatística comparam a resposta da API com SQL escrito à mão na mesma base — se as
duas discordam, o teste falha, que é o ponto: a tabela não pode mostrar um número que a camada não tem."""

import secrets

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE

ITEM = "L2-01-g-tabela-atributos"

CAMPOS = [
    {"nome": "municipio", "tipo": "text", "alias": "Município"},
    {"nome": "classe", "tipo": "text", "alias": "Classe de cobertura"},
    {"nome": "area_ha", "tipo": "float8", "alias": "Área (ha)"},
]
CLASSES = ("floresta", "pastagem", "agricultura", "água")


def _conexao(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login('demo', 'admin')")
        r = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
                    "set_config('plat.login', 'admin', false)", (str(r["tenant_id"]), str(r["usuario_id"])))
    return con, r["usuario_id"]


def _criar_camada(sessao, env, feicoes: int, indexar: list[str] | None = None):
    """(item_id, schema, tabela, fecha) — tabela real em d_demo, preparada como a ingestão prepara."""
    tabela = "c_" + secrets.token_hex(8)
    con, usuario_id = _conexao(env)
    with con.cursor() as cur:
        cur.execute(
            f'CREATE TABLE d_demo."{tabela}" (fid serial PRIMARY KEY, municipio text, classe text, '
            f"area_ha double precision, geom geometry(MultiPolygon, 4674))"
        )
        cur.execute(
            f'INSERT INTO d_demo."{tabela}" (municipio, classe, area_ha, geom) '
            f"SELECT 'Município ' || i, (ARRAY{list(CLASSES)!r})[1 + (i %% {len(CLASSES)})], "
            f"CASE WHEN i %% 10 = 0 THEN NULL ELSE i * 1.5 END, "
            f"ST_Multi(ST_MakeEnvelope(-46.8 + (i %% 100) * 0.01, -23.7 + (i / 100.0) * 0.0001, "
            f"-46.79 + (i %% 100) * 0.01, -23.69 + (i / 100.0) * 0.0001, 4674)) "
            f"FROM generate_series(1, %s) i", (feicoes,))
        # o índice de ordenação vai ANTES de camada_preparar: a função acrescenta colunas com valor padrão,
        # o que reescreve a tabela, e um índice criado depois dessa reescrita não foi usado pelo planejador
        # nesta base (MEDIDO: varredura sequencial com ordenação top-N em vez de percurso do índice).
        if indexar:
            colunas = ", ".join(f'"{c}"' for c in indexar)
            cur.execute(f'CREATE INDEX ON d_demo."{tabela}" ({colunas})')
        cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                    ("d_demo", tabela, 4674, "MultiPolygon", usuario_id))
        cur.execute(f'ANALYZE d_demo."{tabela}"')

    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": f"{PREFIXO_TESTE} tabela de atributos",
        "dados": {"schema": "d_demo", "tabela": tabela, "geometria": "MultiPolygon", "srid": 4674,
                  "campos": CAMPOS, "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    def fechar():
        try:
            with con.cursor() as cur:
                cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (item_id,))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (item_id,))
                cur.execute(f'DROP TABLE IF EXISTS d_demo."{tabela}"')
        finally:
            con.close()

    return item_id, "d_demo", tabela, fechar


@pytest.fixture
def camada(sessao_a, env):
    """80 feições — o suficiente para paginar em 50, ordenar e conferir contagem contra o banco."""
    item_id, _schema, _tabela, fechar = _criar_camada(sessao_a, env, 80)
    try:
        yield item_id
    finally:
        fechar()


def _contexto_admin(con, slug="demo"):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        r = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                    "set_config('plat.login', 'admin', true)", (str(r["tenant_id"]), str(r["usuario_id"])))


def _fisica(con, item_id):
    with con.cursor() as cur:
        cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id=%s::uuid",
                    (item_id,))
        r = cur.fetchone()
    return r["s"], r["t"]


def base(item_id):
    return f"/api/camadas/{item_id}/tabela"


# ---------------------------------------------------------------- colunas, alias, vista
def test_colunas_traz_alias_tipo_e_chave(sessao_a, camada):
    r = sessao_a.get(f"{base(camada)}/colunas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["chave"] == "fid" and corpo["tem_geometria"] is True
    nomes = [c["nome"] for c in corpo["colunas"]]
    assert "fid" in nomes and "geom" not in nomes, nomes
    for c in corpo["colunas"]:
        assert c["alias"] and c["tipo"] in ("texto", "numero", "data", "logico", "uuid", "outro")


def test_coluna_oculta_pela_vista_some_da_api_de_colunas_mas_fica_na_vista(sessao_a, camada):
    alvo = [c["nome"] for c in sessao_a.get(f"{base(camada)}/colunas").json()["colunas"] if c["nome"] != "fid"][0]
    r = sessao_a.put(f"{base(camada)}/vista", json={"colunas": [{"nome": alvo, "oculta": True}]})
    assert r.status_code == 200, r.text

    colunas = sessao_a.get(f"{base(camada)}/colunas").json()["colunas"]
    assert alvo not in [c["nome"] for c in colunas], "coluna oculta apareceu na API de colunas"
    linhas = sessao_a.post(f"{base(camada)}/linhas", json={}).json()
    assert alvo not in [c["nome"] for c in linhas["colunas"]]
    assert all(alvo not in linha["valores"] for linha in linhas["linhas"]), "valor da coluna oculta veio na linha"

    vista = sessao_a.get(f"{base(camada)}/vista").json()["colunas"]
    escondida = [c for c in vista if c["nome"] == alvo]
    assert escondida and escondida[0]["oculta"] is True, "sem a vista não há como desfazer o ocultamento"

    assert sessao_a.put(f"{base(camada)}/vista", json={"colunas": []}).status_code == 200
    assert alvo in [c["nome"] for c in sessao_a.get(f"{base(camada)}/colunas").json()["colunas"]]


def test_largura_e_alias_persistem_entre_pedidos(sessao_a, camada, cred):
    from tests.api.conftest import _sessao_admin

    r = sessao_a.put(f"{base(camada)}/vista", json={
        "colunas": [{"nome": "fid", "largura": 320, "alias": "identificador"}]})
    assert r.status_code == 200, r.text
    # sessão NOVA (cookie novo): é o equivalente de recarregar a página — a largura não vive no navegador
    outra = _sessao_admin(cred, "demo")
    colunas = outra.get(f"{base(camada)}/colunas").json()["colunas"]
    fid = [c for c in colunas if c["nome"] == "fid"][0]
    assert fid["largura"] == 320 and fid["alias"] == "identificador"
    assert sessao_a.put(f"{base(camada)}/vista", json={"colunas": []}).status_code == 200


def test_vista_recusa_coluna_inexistente_e_largura_absurda(sessao_a, camada):
    assert sessao_a.put(f"{base(camada)}/vista", json={"colunas": [{"nome": "nao_existe"}]}).status_code == 422
    assert sessao_a.put(f"{base(camada)}/vista",
                        json={"colunas": [{"nome": "fid", "largura": 99999}]}).status_code == 422


def test_dominio_da_coluna_chega_a_quem_desenha_a_celula(sessao_a, camada):
    r = sessao_a.put(f"{base(camada)}/vista", json={
        "colunas": [{"nome": "fid", "dominio": {"1": "primeira feição", "2": "segunda feição"}}]})
    assert r.status_code == 200, r.text
    colunas = sessao_a.post(f"{base(camada)}/linhas", json={}).json()["colunas"]
    fid = [c for c in colunas if c["nome"] == "fid"][0]
    assert fid["dominio"] == {"1": "primeira feição", "2": "segunda feição"}
    assert sessao_a.put(f"{base(camada)}/vista", json={"colunas": []}).status_code == 200


# ---------------------------------------------------------------- paginação, ordenação, contagem
@pytest.mark.parametrize("por_pagina", [50, 200, 1000])
def test_paginacao_no_servidor_nas_tres_paginas(sessao_a, camada, por_pagina):
    r = sessao_a.post(f"{base(camada)}/linhas", json={"pagina": 1, "por_pagina": por_pagina})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == 80
    assert len(corpo["linhas"]) == min(80, por_pagina)


def test_paginas_nao_repetem_nem_pulam_linha(sessao_a, camada):
    p1 = sessao_a.post(f"{base(camada)}/linhas", json={"pagina": 1, "por_pagina": 50}).json()
    p2 = sessao_a.post(f"{base(camada)}/linhas", json={"pagina": 2, "por_pagina": 50}).json()
    ids = [linha["id"] for linha in p1["linhas"]] + [linha["id"] for linha in p2["linhas"]]
    assert len(ids) == 80 and len(set(ids)) == 80


def test_por_pagina_fora_da_lista_e_422(sessao_a, camada):
    assert sessao_a.post(f"{base(camada)}/linhas", json={"por_pagina": 51}).status_code == 422
    assert sessao_a.post(f"{base(camada)}/linhas", json={"por_pagina": 100000}).status_code == 422


def test_ordenacao_por_coluna_inverte_de_verdade(sessao_a, camada):
    asc = sessao_a.post(f"{base(camada)}/linhas",
                        json={"ordenar_por": "fid", "ordem": "asc", "por_pagina": 50}).json()
    desc = sessao_a.post(f"{base(camada)}/linhas",
                         json={"ordenar_por": "fid", "ordem": "desc", "por_pagina": 50}).json()
    assert [linha["id"] for linha in asc["linhas"]] == sorted(linha["id"] for linha in asc["linhas"])
    assert desc["linhas"][0]["id"] > asc["linhas"][0]["id"]


@pytest.mark.parametrize("ordenar_por", [
    "coluna_que_nao_existe", "fid; DROP TABLE plat.item", "(SELECT 1)", 'fid" ,"geom', "geom",
])
def test_ordenar_por_invalido_e_422_nao_500(sessao_a, camada, ordenar_por):
    r = sessao_a.post(f"{base(camada)}/linhas", json={"ordenar_por": ordenar_por})
    assert r.status_code == 422, (ordenar_por, r.status_code, r.text)
    assert r.json()["erro"] in ("coluna_invalida", "validacao")


def test_contagem_exibida_bate_com_count_sob_o_mesmo_filtro(sessao_a, camada, conexao_plat_app):
    colunas = sessao_a.get(f"{base(camada)}/colunas").json()["colunas"]
    texto = [c["nome"] for c in colunas if c["tipo"] == "texto"]
    assert texto, colunas
    coluna = texto[0]

    _contexto_admin(conexao_plat_app)
    schema, tabela = _fisica(conexao_plat_app, camada)
    with conexao_plat_app.cursor() as cur:
        cur.execute(f'SELECT "{coluna}" AS v FROM "{schema}"."{tabela}" WHERE "{coluna}" IS NOT NULL LIMIT 1')
        alguma = cur.fetchone()
    assert alguma, "a camada de teste não tem nenhum valor de texto"
    termo = alguma["v"][:6]

    corpo = sessao_a.post(f"{base(camada)}/linhas", json={"busca": termo, "por_pagina": 1000}).json()
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'SELECT count(*) AS n FROM "{schema}"."{tabela}" '
            f'WHERE public.unaccent(lower("{coluna}"::text)) LIKE public.unaccent(%s)',
            (f"%{termo.lower()}%",),
        )
        direto = cur.fetchone()["n"]
    assert corpo["total"] >= direto and corpo["total"] > 0
    assert len(corpo["linhas"]) == min(corpo["total"], 1000)
    # a busca varre TODAS as colunas de texto, por isso o total pode ser maior que o de uma coluna só;
    # nenhuma linha devolvida pode estar fora do filtro, e é isso que a contagem tem de refletir
    assert corpo["total"] == len(corpo["linhas"])


def test_busca_sem_resultado_devolve_zero_e_lista_vazia(sessao_a, camada):
    corpo = sessao_a.post(f"{base(camada)}/linhas", json={"busca": "zzz-nao-existe-zzz"}).json()
    assert corpo["total"] == 0 and corpo["linhas"] == [] and corpo["paginas"] == 0


# ---------------------------------------------------------------- seleção e extensão do mapa
def test_selecao_de_tres_feicoes_deixa_tres_linhas(sessao_a, camada):
    todas = sessao_a.post(f"{base(camada)}/linhas", json={"por_pagina": 50}).json()["linhas"]
    tres = [linha["id"] for linha in todas[:3]]
    corpo = sessao_a.post(f"{base(camada)}/linhas", json={"fids": tres}).json()
    assert corpo["total"] == 3
    assert sorted(linha["id"] for linha in corpo["linhas"]) == sorted(tres)


def test_filtro_pela_extensao_do_mapa_reduz_e_bate_com_o_banco(sessao_a, camada, conexao_plat_app):
    inteira = sessao_a.post(f"{base(camada)}/linhas", json={"geometria": True, "por_pagina": 1000}).json()
    assert all(linha["geometria"] for linha in inteira["linhas"])
    pontos = [c for linha in inteira["linhas"] for c in _pontos(linha["geometria"])]
    xs = sorted(p[0] for p in pontos)
    ys = sorted(p[1] for p in pontos)
    meio = [xs[0], ys[0], xs[len(xs) // 2], ys[len(ys) // 2]]

    dentro = sessao_a.post(f"{base(camada)}/linhas", json={"bbox": meio, "por_pagina": 1000}).json()
    assert 0 < dentro["total"] <= inteira["total"]

    _contexto_admin(conexao_plat_app)
    schema, tabela = _fisica(conexao_plat_app, camada)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados->>'srid' AS srid FROM plat.item WHERE id=%s::uuid", (camada,))
        srid = int(cur.fetchone()["srid"])
        cur.execute(
            f'SELECT count(*) AS n FROM "{schema}"."{tabela}" '
            f"WHERE ST_Intersects(geom, ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4326), {srid}))", meio)
        assert cur.fetchone()["n"] == dentro["total"]


def _pontos(geometria):
    saida = []

    def juntar(c):
        if c and isinstance(c[0], (int, float)):
            saida.append(c)
        else:
            for p in c:
                juntar(p)

    juntar(geometria["coordinates"])
    return saida


def test_bbox_incoerente_e_422(sessao_a, camada):
    assert sessao_a.post(f"{base(camada)}/linhas", json={"bbox": [10, 10, 5, 20]}).status_code == 422
    assert sessao_a.post(f"{base(camada)}/linhas", json={"bbox": [1, 2, 3]}).status_code == 422


# ---------------------------------------------------------------- estatísticas
def test_estatisticas_batem_com_sql_direto(sessao_a, camada, conexao_plat_app):
    colunas = sessao_a.get(f"{base(camada)}/colunas").json()["colunas"]
    numericas = [c["nome"] for c in colunas if c["tipo"] == "numero"]
    assert numericas, colunas
    r = sessao_a.post(f"{base(camada)}/estatisticas", json={})
    assert r.status_code == 200, r.text
    api = r.json()["colunas"]
    assert set(api) == set(numericas)

    _contexto_admin(conexao_plat_app)
    schema, tabela = _fisica(conexao_plat_app, camada)
    for nome in numericas:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                f'SELECT count("{nome}") AS contagem, sum("{nome}"::numeric) AS soma, '
                f'avg("{nome}"::numeric) AS media, min("{nome}") AS minimo, max("{nome}") AS maximo, '
                f'count(*) FILTER (WHERE "{nome}" IS NULL) AS nulos FROM "{schema}"."{tabela}"')
            direto = cur.fetchone()
        for chave in ("contagem", "nulos"):
            assert api[nome][chave] == direto[chave], (nome, chave)
        for chave in ("soma", "media", "minimo", "maximo"):
            a, b = api[nome][chave], direto[chave]
            if a is None or b is None:
                assert a == b, (nome, chave)
            else:
                assert abs(float(a) - float(b)) < 1e-6, (nome, chave, a, b)


def test_estatisticas_seguem_o_mesmo_filtro_da_tabela(sessao_a, camada):
    todas = sessao_a.post(f"{base(camada)}/linhas", json={"por_pagina": 50}).json()["linhas"]
    tres = [linha["id"] for linha in todas[:3]]
    est = sessao_a.post(f"{base(camada)}/estatisticas", json={"fids": tres}).json()["colunas"]
    assert est["fid"]["contagem"] == 3
    assert est["fid"]["soma"] == sum(tres)


def test_estatisticas_de_coluna_nao_numerica_e_422(sessao_a, camada):
    colunas = sessao_a.get(f"{base(camada)}/colunas").json()["colunas"]
    texto = [c["nome"] for c in colunas if c["tipo"] == "texto"]
    assert texto
    r = sessao_a.post(f"{base(camada)}/estatisticas", json={"colunas": [texto[0]]})
    assert r.status_code == 422 and r.json()["erro"] == "coluna_nao_numerica"


# ---------------------------------------------------------------- isolamento e erros de contrato
def test_camada_de_outro_inquilino_e_404(sessao_b, camada):
    for rota, metodo in (("colunas", "get"), ("vista", "get")):
        assert getattr(sessao_b, metodo)(f"{base(camada)}/{rota}").status_code == 404
    assert sessao_b.post(f"{base(camada)}/linhas", json={}).status_code == 404
    assert sessao_b.post(f"{base(camada)}/estatisticas", json={}).status_code == 404


def test_sem_sessao_e_401(cliente, camada):
    assert cliente.get(f"{base(camada)}/colunas").status_code == 401


def test_item_que_nao_e_camada_e_409(sessao_a, camada):
    """Qualquer item que não seja camada vetorial: 409 nao_e_camada, nunca 500 nem 200 com tabela alheia."""
    r = sessao_a.get("/api/itens?limite=50")
    assert r.status_code == 200, r.text
    outros = [i["id"] for i in r.json()["itens"] if i["tipo"] != "camada_vetorial"]
    if not outros:
        pytest.skip("a base desta trilha só tem itens de camada vetorial")
    resp = sessao_a.get(f"{base(outros[0])}/colunas")
    assert resp.status_code == 409 and resp.json()["erro"] == "nao_e_camada", resp.text


def test_item_inexistente_e_404(sessao_a):
    assert sessao_a.get(f"{base('00000000-0000-0000-0000-000000000000')}/colunas").status_code == 404
