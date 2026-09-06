"""Publicação sem cópia do acervo (item L6-01-b-view-so-leitura): view em `plat_acervo` com lista branca de
colunas, porteiro `plat.acervo_pode_ler` no WHERE, GRANT SELECT só da view a `plat_app`.

Cada cláusula do portão vira um teste aqui, e as provas negativas são feitas com a ROLE DA APLICAÇÃO
(`conexao_plat_app`), nunca como postgres: o que se afirma é que o BANCO recusa, não que a aplicação não
oferece rota. `plat.acervo_camada`/`plat.acervo_publicacao` são registros GLOBAIS escritos como postgres
(mesmo padrão do item L6-01-a) — a semeadura da camada de teste abaixo roda com essa mesma identidade.

Honestidade sobre a camada usada: `public.car_area_imovel` (7,36 mi de linhas, medido) é a tabela que o portão
nomeia. No registro VIVO desta casa a fonte `sfb-sicar-nacional-perimetros-e-camadas-do-car` está SEM licença
escrita, logo `acervo_sync.py` a classifica `pendente_de_licenca` e o publicador NÃO a publicaria hoje (regra
D17). O que estes testes medem é o MECANISMO de publicação e o porteiro; publicar CAR de verdade depende de o
item L6-01-g escrever a licença.

Consequência do item L6-01-e-assinatura-e-uso (desta mesma família): a rota POST de assinatura passou a exigir
licença curada da fonte e o aceite por clique do texto — e a fonte do CAR não tem licença curada (decisão
registrada do item L6-01-g), então a assinatura destes testes NÃO pode mais vir da API. Como o que este arquivo
mede é a view e o porteiro (que só olham a existência da linha em plat.acervo_assinatura), a assinatura passa a
ser semeada DIRETO no banco, como postgres — a mesma identidade que semeia o registro da camada — com o rótulo
honesto 'sem-licenca-curada' em licenca_tipo. A prova do aceite por clique com licença curada de verdade mora em
tests/api/test_acervo_assinatura_uso.py.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]
PUBLICAR = ROOT / "scripts" / "acervo_publicar.py"
ITEM = "L6-01-b-view-so-leitura"

CAMADA_ID = "sfb-sicar-nacional-perimetros-e-camadas-do-car/public.car_area_imovel"
VIEW = "public_car_area_imovel"
TABELA_ORIGEM = "public.car_area_imovel"
COLUNAS_BRANCAS = ["ogc_fid", "cod_imovel", "num_area", "municipio", "cod_estado", "ind_status", "ind_tipo"]
COLUNA_FORA_DA_LISTA = "dat_criaca"  # existe na tabela de origem e NÃO pode existir na view
# caixa de ~22 x 22 km sobre a Grande São Paulo: área com CAR de verdade nesta base
BBOX = "-46.6,-23.6,-46.4,-23.4"


def _schema() -> str:
    return os.environ.get("PLAT_SCHEMA", "plat")


def _psql(sql: str, *params: str) -> str:
    """psql como postgres — a identidade que escreve os registros do acervo (nunca plat_app)."""
    cmd = ["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_BANCO", "iagro_sat"),
           "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1"]
    for i, p in enumerate(params, start=1):
        cmd += ["-v", f"p{i}={p}"]
    r = subprocess.run(cmd + ["-c", sql], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _origem_existe() -> bool:
    return _psql("SELECT to_regclass('public.car_area_imovel') IS NOT NULL") == "t"


@pytest.fixture(scope="module")
def camada_publicada():
    """Semeia a linha do registro (como postgres, igual ao acervo_sync.py) e roda o publicador de verdade."""
    if not _origem_existe():
        pytest.skip("public.car_area_imovel não existe nesta base")
    s = _schema()
    # linhas_exatas vem de COUNT(*) AGORA, nunca de reltuples: o portão fala em "7,36 mi", que é a ESTIMATIVA
    # do catálogo; o número exato desta base, medido em 06/09/2026, é maior (a medida fica gravada).
    exatas = _psql("SELECT count(*) FROM public.car_area_imovel")
    estimadas = _psql("SELECT reltuples::bigint FROM pg_class WHERE oid = 'public.car_area_imovel'::regclass")
    _psql(
        f"""INSERT INTO {s}.acervo_camada (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela,
              coluna_geom, srid, tipo_geom, colunas_expostas, colunas_bloqueadas, linhas_exatas,
              linhas_contadas_em, linhas_estimadas, estado)
            VALUES ('{CAMADA_ID}', 'sfb-sicar-nacional-perimetros-e-camadas-do-car', 'vultr', 'iagro_sat',
              'public', 'car_area_imovel', 'geom', 4326, 'MULTIPOLYGON',
              ARRAY[{','.join(chr(39) + c + chr(39) for c in COLUNAS_BRANCAS)}], ARRAY[]::text[],
              {exatas}, current_date, {estimadas}, 'exposta')
            ON CONFLICT (acervo_camada_id) DO UPDATE SET estado = 'exposta',
              colunas_expostas = EXCLUDED.colunas_expostas, linhas_exatas = EXCLUDED.linhas_exatas,
              linhas_estimadas = EXCLUDED.linhas_estimadas"""
    )
    r = subprocess.run(
        ["sudo", "-u", "postgres", "python3", str(PUBLICAR), "--schema", s,
         "--banco", os.environ.get("PLAT_BANCO", "iagro_sat")],
        capture_output=True, text=True, timeout=300,
    )
    assert r.returncode == 0, r.stderr
    yield VIEW


def _assinar_direto_sql(tenant_slug: str = "demo") -> None:
    """Assinatura da camada de teste semeada DIRETO no banco (como postgres), não pelo clique da API — ver o
    cabeçalho do arquivo: desde L6-01-e a rota POST exige licença curada, que a fonte do CAR não tem. O
    porteiro `acervo_pode_ler` só olha a existência da linha, então o mecanismo continua provado de ponta a
    ponta. licenca_tipo 'sem-licenca-curada' confessa a origem da linha."""
    s = _schema()
    _psql(
        f"INSERT INTO {s}.acervo_assinatura(tenant_id, acervo_camada_id, assinado_por, "
        f"licenca_tipo, licenca_texto, licenca_url, licenca_sha256) "
        f"SELECT t.id, '{CAMADA_ID}', NULL, 'sem-licenca-curada', "
        f"'assinatura semeada por SQL para provar o porteiro (item L6-01-b); a fonte do CAR nao tem licenca "
        f"curada e o aceite por clique com licenca de verdade e provado no item L6-01-e', '', '' "
        f"FROM {s}.tenant t WHERE t.slug = '{tenant_slug}' "
        f"ON CONFLICT (tenant_id, acervo_camada_id) DO NOTHING"
    )


@pytest.fixture
def assinatura_a(camada_publicada, sessao_a):
    """Inquilino A (demo) com assinatura da camada (semeada por SQL, ver acima) e cancelamento pela API no
    fim — a assinatura é o objeto do portão."""
    _assinar_direto_sql("demo")
    yield
    sessao_a.delete(f"/api/acervo/camadas/{VIEW}/assinatura")


def _tenant_id(slug: str) -> int:
    """Lido como postgres: `plat.tenant` tem RLS por inquilino, e a conexão de teste ainda não tem contexto —
    é justamente o contexto que estes testes vão POR na mão para provar o porteiro."""
    return int(_psql(f"SELECT id FROM {_schema()}.tenant WHERE slug = '{slug}'"))


def _com_inquilino(conexao_plat_app, tenant_id: int):
    cur = conexao_plat_app.cursor()
    cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(tenant_id),))
    return cur


# ---------------------------------------------------------------- cláusula: a view existe e é lista branca

def test_view_publicada_tem_so_as_colunas_da_lista_branca(camada_publicada, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT view_nome, colunas, coluna_geom, security_invoker, security_barrier, schema_origem, "
            "tabela_origem FROM plat.acervo_publicacao WHERE acervo_camada_id = %s", (CAMADA_ID,))
        p = cur.fetchone()
    assert p is not None, "o publicador não registrou a camada"
    assert p["view_nome"] == VIEW
    assert set(p["colunas"]) == set(COLUNAS_BRANCAS) | {"geom"}
    assert COLUNA_FORA_DA_LISTA not in p["colunas"]

    esquema_views = f"{_schema()}_acervo"
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
            (esquema_views, VIEW))
        colunas = {r["column_name"] for r in cur.fetchall()}
    assert colunas == set(COLUNAS_BRANCAS) | {"geom"}, colunas
    assert COLUNA_FORA_DA_LISTA not in colunas


def test_publicador_e_idempotente(camada_publicada):
    """Rodar de novo não duplica linha nem quebra: o portão do item irmão (L6-01-a) vale igual aqui."""
    r = subprocess.run(
        ["sudo", "-u", "postgres", "python3", str(PUBLICAR), "--schema", _schema(),
         "--banco", os.environ.get("PLAT_BANCO", "iagro_sat")],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    n = _psql(f"SELECT count(*) FROM {_schema()}.acervo_publicacao WHERE acervo_camada_id = '{CAMADA_ID}'")
    assert n == "1"


# ------------------------------------------------- cláusula: nenhuma tabela public tem GRANT a plat_app

def test_nenhuma_tabela_public_tem_grant_direto_a_plat_app(conexao_plat_app):
    """Varredura de pg_class/aclexplode, como o portão pede: o papel da aplicação não tem privilégio NENHUM
    em `public` — nem SELECT. A leitura do acervo passa só pela view, cujo dono é o publicador."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT current_user AS u")
        papel = cur.fetchone()["u"]
        cur.execute(
            """SELECT n.nspname || '.' || c.relname AS objeto, a.privilege_type
                 FROM pg_class c
                 JOIN pg_namespace n ON n.oid = c.relnamespace,
                 LATERAL aclexplode(c.relacl) a
                WHERE n.nspname = 'public' AND a.grantee = %s::regrole""",
            (papel,))
        achados = [(r["objeto"], r["privilege_type"]) for r in cur.fetchall()]
    assert achados == [], achados


def test_banco_recusa_select_direto_na_tabela_de_origem(camada_publicada, conexao_plat_app):
    """Refutação do item, feita como plat_app: SELECT direto em public.car_area_imovel."""
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege) as e:
            cur.execute(f"SELECT count(*) FROM {TABELA_ORIGEM}")
    assert "car_area_imovel" in str(e.value)
    conexao_plat_app.rollback()


# ----------------------------------------------------- cláusula: só-leitura NO BANCO (não só na aplicação)

@pytest.mark.parametrize(
    "sql",
    [
        f"DELETE FROM {{v}} WHERE {COLUNAS_BRANCAS[0]} = -1",
        f"UPDATE {{v}} SET {COLUNAS_BRANCAS[1]} = 'x' WHERE {COLUNAS_BRANCAS[0]} = -1",
        f"INSERT INTO {{v}} ({COLUNAS_BRANCAS[0]}) VALUES (-1)",
    ],
    ids=["delete", "update", "insert"],
)
def test_banco_recusa_escrita_na_view(camada_publicada, conexao_plat_app, sql):
    """O portão fala de FeatureServer/applyEdits; a garantia que DÁ para provar hoje é a de baixo: a view não
    tem GRANT de escrita para plat_app, então o próprio Postgres recusa, com ou sem assinatura, com ou sem
    rota HTTP. Escrito com a role da aplicação (conexao_plat_app), não com postgres."""
    alvo = f'"{_schema()}_acervo"."{VIEW}"'
    tenant = _tenant_id("demo")
    cur = _com_inquilino(conexao_plat_app, tenant)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute(sql.format(v=alvo))
    conexao_plat_app.rollback()


def test_privilegios_da_view_sao_so_select(camada_publicada, conexao_plat_app):
    """Prova positiva do mesmo fato, lida do catálogo: o ACL da view para plat_app é exatamente {SELECT}."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT current_user AS u")
        papel = cur.fetchone()["u"]
        cur.execute(
            """SELECT a.privilege_type FROM pg_class c
                 JOIN pg_namespace n ON n.oid = c.relnamespace,
                 LATERAL aclexplode(c.relacl) a
                WHERE n.nspname = %s AND c.relname = %s AND a.grantee = %s::regrole""",
            (f"{_schema()}_acervo", VIEW, papel))
        privs = {r["privilege_type"] for r in cur.fetchall()}
    assert privs == {"SELECT"}, privs


# --------------------------------------------------------------- cláusula: sem assinatura, zero linha e 403

def test_sem_assinatura_a_view_devolve_zero_linha(camada_publicada, conexao_plat_app):
    """Refutação do item: a view sem assinatura. Não é 'a rota recusa': é a VIEW que não devolve linha."""
    alvo = f'"{_schema()}_acervo"."{VIEW}"'
    tenant = _tenant_id("demo2")  # demo2 nunca assina nesta suíte
    cur = _com_inquilino(conexao_plat_app, tenant)
    cur.execute(f"SELECT count(*) AS n FROM {alvo}")  # noqa: S608 — identificadores do registro, citados
    assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()


def test_porteiro_vira_filtro_de_uma_vez_e_nao_varre_a_tabela(camada_publicada, conexao_plat_app):
    """O que substitui security_barrier (ver o cabeçalho da migração): sem assinatura o plano nem executa a
    varredura. Prova estrutural, não de tempo — o tempo depende de cache."""
    alvo = f'"{_schema()}_acervo"."{VIEW}"'
    tenant = _tenant_id("demo2")
    cur = _com_inquilino(conexao_plat_app, tenant)
    cur.execute(
        f"EXPLAIN (ANALYZE, FORMAT JSON) SELECT * FROM {alvo} "  # noqa: S608 — identificadores do registro
        f"WHERE geom && ST_MakeEnvelope(-46.6, -23.6, -46.4, -23.4, 4326) LIMIT 100")
    plano = json.dumps(cur.fetchone()["QUERY PLAN"])
    conexao_plat_app.rollback()
    assert "One-Time Filter" in plano, plano[:800]
    assert '"Actual Loops": 0' in plano or '"Actual Rows": 0' in plano, plano[:800]


def test_api_403_sem_assinatura_e_200_com_assinatura(camada_publicada, sessao_a, sessao_b):
    """Inquilino B (demo2) sem assinatura: 403 em feições e em tile. Inquilino A com assinatura (semeada por
    SQL, ver o cabeçalho) passa a ler; cancelada pela API, a porta fecha na hora."""
    r = sessao_b.get(f"/api/acervo/camadas/{VIEW}/feicoes?bbox={BBOX}&limite=10")
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "sem_assinatura"
    r = sessao_b.get(f"/api/acervo/camadas/{VIEW}/tiles/10/379/580.mvt")
    assert r.status_code == 403, r.text

    _assinar_direto_sql("demo")
    try:
        r = sessao_a.get(f"/api/acervo/camadas/{VIEW}/feicoes?bbox={BBOX}&limite=10")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["type"] == "FeatureCollection"
        assert corpo["total"] >= 1, "a caixa de teste não achou nenhuma feição — escolha outra"
        prop = corpo["features"][0]["properties"]
        assert set(prop) == set(COLUNAS_BRANCAS), prop
        assert COLUNA_FORA_DA_LISTA not in prop
        # a assinatura de A não vaza para B
        r = sessao_b.get(f"/api/acervo/camadas/{VIEW}/feicoes?bbox={BBOX}&limite=10")
        assert r.status_code == 403, r.text
    finally:
        sessao_a.delete(f"/api/acervo/camadas/{VIEW}/assinatura")

    r = sessao_a.get(f"/api/acervo/camadas/{VIEW}/feicoes?bbox={BBOX}&limite=10")
    assert r.status_code == 403, "cancelar a assinatura tem de fechar a porta na hora"


def test_lista_de_camadas_mostra_assinatura_do_proprio_inquilino(camada_publicada, sessao_a, sessao_b):
    r = sessao_b.get("/api/acervo/camadas")
    assert r.status_code == 200, r.text
    de_b = {c["view_nome"]: c for c in r.json()["camadas"]}
    assert VIEW in de_b and de_b[VIEW]["assinada"] is False
    assert COLUNA_FORA_DA_LISTA not in de_b[VIEW]["colunas"]

    _assinar_direto_sql("demo")
    try:
        de_a = {c["view_nome"]: c for c in sessao_a.get("/api/acervo/camadas").json()["camadas"]}
        assert de_a[VIEW]["assinada"] is True
        de_b = {c["view_nome"]: c for c in sessao_b.get("/api/acervo/camadas").json()["camadas"]}
        assert de_b[VIEW]["assinada"] is False, "assinatura de A apareceu para B"
    finally:
        sessao_a.delete(f"/api/acervo/camadas/{VIEW}/assinatura")


def test_verbo_de_escrita_na_camada_publicada_e_405(camada_publicada, sessao_a):
    """Só-leitura também na superfície HTTP: não existe rota de escrita sobre a feição publicada."""
    for metodo, caminho in (
        ("post", f"/api/acervo/camadas/{VIEW}/feicoes"),
        ("put", f"/api/acervo/camadas/{VIEW}/feicoes"),
        ("delete", f"/api/acervo/camadas/{VIEW}/feicoes"),
        ("post", f"/api/acervo/camadas/{VIEW}/tiles/10/379/580.mvt"),
    ):
        r = getattr(sessao_a, metodo)(caminho)
        assert r.status_code == 405, (metodo, caminho, r.status_code, r.text)


# ------------------------------------------------------------------------- cláusula: ≤ 100 ms sobre 7,36 mi

def test_consulta_de_mapa_sobre_7_36_mi_em_ate_100_ms(camada_publicada, assinatura_a, sessao_a, medida):
    """Portão: 'inquilino A assina CAR e consulta de mapa sobre 7,36 mi de imóveis responde em ≤ 100 ms'.
    Mede o tempo de EXECUÇÃO no banco (mediana de 5), pela view, com o índice GiST da tabela ORIGINAL — é o
    número que o portão cobra. O tempo de ida e volta HTTP fica gravado à parte, sem virar cláusula: ele
    carrega serialização de GeoJSON e o cliente de teste, que o portão não menciona."""
    gravar = medida(ITEM)
    linhas = int(_psql(f"SELECT linhas_exatas FROM {_schema()}.acervo_camada WHERE acervo_camada_id = '{CAMADA_ID}'"))
    assert linhas >= 7_000_000, linhas

    alvo = f'"{_schema()}_acervo"."{VIEW}"'
    consulta = (
        f"SELECT ogc_fid, cod_imovel, num_area, ST_AsGeoJSON(geom) FROM {alvo} "
        f"WHERE geom && ST_MakeEnvelope(-46.6, -23.6, -46.4, -23.4, 4326) LIMIT 1000")
    con = psycopg2.connect(os.environ["PLAT_DSN"])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', %s, true)",
                        (_psql(f"SELECT id FROM {_schema()}.tenant WHERE slug = 'demo'"),))
            cur.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {consulta}")  # aquece o cache; não entra na mediana
            tempos = []
            for _ in range(5):
                cur.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {consulta}")
                tempos.append(cur.fetchone()[0][0]["Execution Time"])
    finally:
        con.rollback()
        con.close()
    mediana = sorted(tempos)[len(tempos) // 2]
    estimadas = int(_psql("SELECT reltuples::bigint FROM pg_class WHERE oid = 'public.car_area_imovel'::regclass"))
    gravar("linhas_da_tabela_original_count_exato", linhas, "linhas",
           "SELECT count(*) FROM public.car_area_imovel (índice-only, 196 ms) — não é reltuples")
    gravar("linhas_da_tabela_original_reltuples", estimadas, "linhas",
           "SELECT reltuples FROM pg_class — a estimativa de onde vem o '7,36 mi' do portão; nunca vai a documento")
    gravar("consulta_mapa_mediana_ms", round(mediana, 3), "ms",
           "mediana de 5 EXPLAIN ANALYZE da consulta por caixa envolvente na view, cache quente")
    assert mediana <= 100, (mediana, tempos)

    inicio = time.monotonic()
    r = sessao_a.get(f"/api/acervo/camadas/{VIEW}/feicoes?bbox={BBOX}&limite=1000")
    ms = (time.monotonic() - inicio) * 1000
    assert r.status_code == 200, r.text
    gravar("feicoes_http_ms", round(ms, 1), "ms",
           "GET /api/acervo/camadas/<view>/feicoes?bbox=... (inclui GeoJSON e cliente de teste; fora do portão)")


def test_tile_mvt_sai_com_bytes_para_quem_assina(camada_publicada, assinatura_a, sessao_a, medida):
    """A mesma view serve o tile. Martin não existe nesta máquina (porta 8151 reservada, ARQUITETURA seção 2);
    o que se prova aqui é o SQL que ele publicaria, com o porteiro dentro."""
    r = sessao_a.get(f"/api/acervo/camadas/{VIEW}/tiles/10/379/580.mvt")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    medida(ITEM)("tile_mvt_bytes", len(r.content), "bytes",
                 "GET /api/acervo/camadas/<view>/tiles/10/379/580.mvt com assinatura")
    assert len(r.content) > 0, "tile vazio: a caixa do tile não cobre feição nesta base"


# --------------------------------------------- refutação da própria hipótese do item, medida (não opinada)

def test_security_invoker_seria_negado_pelo_banco(camada_publicada, conexao_plat_app, medida):
    """A hipótese do item pedia `SECURITY INVOKER`. Aqui se PROVA por que não dá: uma view igual, só que com
    security_invoker = true, é negada a plat_app — porque o privilégio checado passa a ser o da TABELA DE
    ORIGEM, que o mesmo portão proíbe conceder. As duas cláusulas do portão não podem valer juntas; a que
    ficou de pé é 'nenhuma tabela public tem GRANT direto a plat_app'."""
    s = _schema()
    prova = f"{VIEW}_prova_invoker"
    _psql(
        f'CREATE OR REPLACE VIEW "{s}_acervo"."{prova}" WITH (security_invoker = true) AS '
        f"SELECT ogc_fid, geom FROM {TABELA_ORIGEM}; "
        f'ALTER VIEW "{s}_acervo"."{prova}" OWNER TO {s}_acervo_publicador; '
        f'GRANT SELECT ON "{s}_acervo"."{prova}" TO {s}_app'
    )
    try:
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege) as e:
                cur.execute(f'SELECT count(*) FROM "{s}_acervo"."{prova}"')  # noqa: S608 — nomes do teste
        conexao_plat_app.rollback()
    finally:
        _psql(f'DROP VIEW IF EXISTS "{s}_acervo"."{prova}"')
    assert "car_area_imovel" in str(e.value)
    medida(ITEM)("security_invoker_negado", 1, "booleano",
                 "CREATE VIEW WITH (security_invoker=true) + GRANT SELECT a plat_app -> permission denied "
                 "for table car_area_imovel")


def test_security_barrier_derrubaria_o_indice_gist(camada_publicada, conexao_plat_app, medida):
    """Segunda medida do cabeçalho da migração: com security_barrier, o `&&` de geometria (não leakproof) não
    desce até o índice e a consulta vira varredura sequencial das milhões de linhas. Aqui se mede o PLANO
    (EXPLAIN sem ANALYZE), não o tempo — rodar a varredura levaria minutos e não acrescentaria nada."""
    s = _schema()
    prova = f"{VIEW}_prova_barrier"
    _psql(
        f'CREATE OR REPLACE VIEW "{s}_acervo"."{prova}" WITH (security_barrier = true) AS '
        f"SELECT ogc_fid, geom FROM {TABELA_ORIGEM} "
        f"WHERE {s}.acervo_pode_ler('{CAMADA_ID}'); "
        f'ALTER VIEW "{s}_acervo"."{prova}" OWNER TO {s}_acervo_publicador; '
        f'GRANT SELECT ON "{s}_acervo"."{prova}" TO {s}_app'
    )
    try:
        cur = _com_inquilino(conexao_plat_app, _tenant_id("demo"))
        cur.execute(
            f'EXPLAIN (FORMAT JSON) SELECT ogc_fid FROM "{s}_acervo"."{prova}" '  # noqa: S608 — nomes do teste
            f"WHERE geom && ST_MakeEnvelope(-46.6, -23.6, -46.4, -23.4, 4326)")
        com_barrier = json.dumps(cur.fetchone()["QUERY PLAN"])
        alvo = f'"{s}_acervo"."{VIEW}"'
        cur.execute(
            f"EXPLAIN (FORMAT JSON) SELECT ogc_fid FROM {alvo} "  # noqa: S608 — identificadores do registro
            f"WHERE geom && ST_MakeEnvelope(-46.6, -23.6, -46.4, -23.4, 4326)")
        sem_barrier = json.dumps(cur.fetchone()["QUERY PLAN"])
        conexao_plat_app.rollback()
    finally:
        _psql(f'DROP VIEW IF EXISTS "{s}_acervo"."{prova}"')
    assert "Seq Scan" in com_barrier and "Index Scan" not in com_barrier, com_barrier[:600]
    assert "Index Scan" in sem_barrier, sem_barrier[:600]
    medida(ITEM)("security_barrier_perde_o_indice", 1, "booleano",
                 "EXPLAIN da mesma consulta em duas views iguais: com security_barrier sai Seq Scan, sem "
                 "barrier sai Index Scan no idx_car_area_imovel_geom")
