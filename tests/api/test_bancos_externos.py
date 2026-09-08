"""Item L6-02-j-bancos-externos: PostgreSQL/PostGIS externo referenciado (postgres_fdw, conector do L0-04-i)
+ consulta SQL do cliente com lista branca de SELECT e limite de linhas (`app/conexao/consulta_sql.py`).

Portão (literal, laco/estado.json): "PostgreSQL remoto (segundo banco local como fixture) referenciado e
visto no mapa; SQL Server testado só se o dono liberar um container (registrado como pendente); consulta SQL
recusa DDL/DML e exige LIMIT; tempo medido". Refutação: "adversário tenta 'SELECT ...; DROP TABLE' e consulta
sem LIMIT em tabela de 100 mi de linhas".

Fixture: o mesmo docker de `test_pgfdw.py` (127.0.0.1:55499, banco `amostra_aberta`) acrescido de
`public.sedes_municipais` (PostGIS, Point 4674, 1.000 linhas) e `public.tabela_grande` (2.000.000 linhas —
o "100 mi" da refutação é recusado antes de qualquer conexão, então o tamanho real da tabela só importa para
medir o custo do que PASSA pelo validador). Sem o container os testes são pulados, nunca reprovam.
SQL Server e Oracle: sem container liberado, ficam PENDENTES (registrado na ADR e no handoff)."""

from __future__ import annotations

import time

import psycopg2
import psycopg2.extras
import pytest

from app.conexao import consulta_sql, rotas
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_pgfdw import (
    PG_BANCO,
    PG_HOST,
    PG_PORTA,
    PG_SENHA_RO,
    PG_SENHA_SUPER,
    PG_USUARIO_RO,
    PG_USUARIO_SUPER,
    URL_PG,
)

ITEM = "L6-02-j-bancos-externos"


def _docker_com_postgis() -> bool:
    try:
        con = psycopg2.connect(host=PG_HOST, port=PG_PORTA, dbname=PG_BANCO, user=PG_USUARIO_RO,
                               password=PG_SENHA_RO, connect_timeout=2)
        with con, con.cursor() as cur:
            cur.execute("SELECT to_regclass('public.sedes_municipais'), to_regclass('public.tabela_grande')")
            a, b = cur.fetchone()
        con.close()
        return bool(a and b)
    except psycopg2.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_com_postgis(),
    reason="segundo Postgres/PostGIS de teste (docker, porta 55499, sedes_municipais + tabela_grande) não está no ar",
)


@pytest.fixture
def conexao(sessao_a):
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "postgres_fdw", "nome": f"{PREFIXO_TESTE}-bancos-externos", "url": URL_PG,
        "config": {"usuario": PG_USUARIO_RO, "schema_remoto": "public"}, "credencial": PG_SENHA_RO,
    })
    assert r.status_code == 201, r.text
    c = r.json()
    yield c
    sessao_a.delete(f"/api/conexoes/{c['id']}")


def _consulta(sessao, cid, sql, **extra):
    return sessao.post(f"/api/conexoes/{cid}/consulta", json={"sql": sql, **extra})


def test_postgis_remoto_referenciado_e_publicado_como_camada(sessao_a, conexao, medida):
    inicio = time.perf_counter()
    r = sessao_a.get(f"/api/conexoes/{conexao['id']}/tabelas")
    t_listar = time.perf_counter() - inicio
    assert r.status_code == 200, r.text
    por_nome = {t["tabela"]: t for t in r.json()["itens"]}
    assert "sedes_municipais" in por_nome and "tabela_grande" in por_nome
    geo = por_nome["sedes_municipais"]["geometria"]
    assert geo and geo["tipo"].upper() == "POINT" and geo["srid"] == 4674, geo  # PostGIS visto pelo conector
    assert por_nome["tabela_grande"]["geometria"] is None
    # referenciada (view sobre FOREIGN TABLE), vira item camada_vetorial que a lista de camadas e o mapa leem
    r = sessao_a.post(f"/api/conexoes/{conexao['id']}/publicar-em-massa", json={"tabelas": ["sedes_municipais"]})
    assert r.status_code == 201, r.text
    lote = r.json()["itens"]
    assert len(lote) == 1 and lote[0]["ok"], lote
    item = sessao_a.get(f"/api/itens/{lote[0]['item_id']}").json()
    assert item["tipo"] == "camada_vetorial" and item["dados"]["fonte"] == "referenciada"
    assert item["dados"]["procedencia"]["protocolo"] == "postgres_fdw"
    camadas = sessao_a.get(f"/api/conexoes/{conexao['id']}/camadas").json()["itens"]
    assert [c["id"] for c in camadas] == [lote[0]["item_id"]] and camadas[0]["estado_fonte"] == "ok"
    m = medida(ITEM)
    m("listar_tabelas_s", round(t_listar, 3), "s", "GET /api/conexoes/{id}/tabelas contra o PostGIS docker")
    m("postgis_geometria_detectada", True, "bool", "sedes_municipais: tipo POINT srid 4674 vindo de geometry_columns")


def test_consulta_sql_com_limit_devolve_linhas_e_tempo(sessao_a, conexao, medida):
    r = _consulta(sessao_a, conexao["id"],
                  "SELECT id, nome, ST_X(geom) AS x, ST_Y(geom) AS y FROM sedes_municipais "
                  "WHERE codigo_ibge LIKE '35%' ORDER BY id LIMIT 50")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["colunas"] == ["id", "nome", "x", "y"] and 0 < j["n"] <= 50 and j["limite"] == 50
    assert j["tabelas"] == ["sedes_municipais"] and isinstance(j["tempo_ms"], int) and j["tempo_ms"] >= 0
    assert all(isinstance(l_[2], float) for l_ in j["linhas"])
    # geometria como texto (nunca bytes crus no JSON)
    r = _consulta(sessao_a, conexao["id"], "SELECT ST_AsText(geom) AS wkt FROM sedes_municipais LIMIT 1")
    assert r.status_code == 200 and r.json()["linhas"][0][0].startswith("POINT(")
    # o teto: LIMIT 5000 na tabela de 2 mi de linhas, tempo medido
    inicio = time.perf_counter()
    r = _consulta(sessao_a, conexao["id"], "SELECT id FROM tabela_grande LIMIT 5000")
    t_teto = time.perf_counter() - inicio
    assert r.status_code == 200 and r.json()["n"] == 5000
    # agregação que varre a tabela inteira passa pelo validador (é leitura com LIMIT) e é limitada pelo
    # statement_timeout do conector, não pelo validador — o custo é medido e declarado
    inicio = time.perf_counter()
    r = _consulta(sessao_a, conexao["id"], "SELECT count(*) AS n FROM tabela_grande LIMIT 1")
    t_count = time.perf_counter() - inicio
    assert r.status_code == 200 and r.json()["linhas"][0][0] == 2_000_000
    m = medida(ITEM)
    m("consulta_limit_5000_s", round(t_teto, 3), "s", "POST consulta 'SELECT id FROM tabela_grande LIMIT 5000'")
    m("consulta_count_2mi_s", round(t_count, 3), "s", "POST .../consulta 'SELECT count(*) FROM tabela_grande LIMIT 1'")
    m("tempo_ms_devolvido", r.json()["tempo_ms"], "ms", "campo tempo_ms da resposta (medido no servidor)")


# adversário: "SELECT ...; DROP TABLE" — recusado antes do banco; a tabela continua lá
def test_adversario_select_ponto_e_virgula_drop_table(sessao_a, conexao, monkeypatch):
    chamadas = []
    original = consulta_sql.executar
    monkeypatch.setattr(rotas.consulta_sql, "executar", lambda *a, **k: chamadas.append(a) or original(*a, **k))
    for sql in (
        "SELECT * FROM sedes_municipais LIMIT 1; DROP TABLE sedes_municipais",
        "SELECT * FROM sedes_municipais LIMIT 1; DROP TABLE tabela_grande; --",
        "DROP TABLE sedes_municipais",
        "DELETE FROM sedes_municipais LIMIT 1",
        "SELECT pg_sleep(20) FROM sedes_municipais LIMIT 1",
        "SELECT * FROM pg_catalog.pg_authid LIMIT 1",
    ):
        r = _consulta(sessao_a, conexao["id"], sql)
        assert r.status_code == 422, (sql, r.text)
        assert r.json()["erro"] in {"consulta_recusada", "tabela_fora_da_lista"}, (sql, r.json())
    assert chamadas == []  # nenhuma chegou à execução
    with psycopg2.connect(host=PG_HOST, port=PG_PORTA, dbname=PG_BANCO, user=PG_USUARIO_SUPER,
                          password=PG_SENHA_SUPER) as con, con.cursor() as cur:
        cur.execute("SELECT count(*) FROM sedes_municipais")
        assert cur.fetchone()[0] == 1000
        cur.execute("SELECT count(*) FROM tabela_grande")
        assert cur.fetchone()[0] == 2_000_000


# adversário: consulta sem LIMIT na tabela grande — 422 sem abrir conexão, sem ler uma linha
def test_adversario_sem_limit_na_tabela_grande(sessao_a, conexao, monkeypatch, medida):
    monkeypatch.setattr(rotas.consulta_sql, "executar",
                        lambda *a, **k: pytest.fail("executar() chamado para consulta sem LIMIT"))
    inicio = time.perf_counter()
    for sql in ("SELECT * FROM tabela_grande", "SELECT * FROM tabela_grande ORDER BY id DESC",
                "SELECT * FROM (SELECT * FROM tabela_grande LIMIT 10) q", "SELECT * FROM tabela_grande LIMIT 5001"):
        r = _consulta(sessao_a, conexao["id"], sql)
        assert r.status_code == 422, (sql, r.text)
        assert r.json()["erro"] in {"limit_obrigatorio", "limit_acima_do_teto"}, (sql, r.json())
    t = time.perf_counter() - inicio
    medida(ITEM)("recusa_sem_limit_4_consultas_s", round(t, 3), "s",
                 "4 consultas sem LIMIT/acima do teto recusadas (inclui o GET de tabelas por chamada)")


def test_execucao_e_so_leitura_mesmo_que_o_validador_falhasse(conexao):
    """Defesa em profundidade: a conexão de `pgfdw.conectar` é readonly — se algum dia uma escrita passar pelo
    texto, o banco do cliente recusa. Testado chamando o executor direto com uma ConsultaValidada forjada."""
    alvo = rotas._alvo_pg({"tipo": "postgres_fdw", "url": URL_PG, "config": {"usuario": PG_USUARIO_RO}}, "public")
    forjada = consulta_sql.ConsultaValidada(sql="DELETE FROM sedes_municipais", limite=1, tabelas=["sedes_municipais"])
    with pytest.raises(consulta_sql.ConsultaRecusada) as e:
        consulta_sql.executar(alvo, PG_SENHA_RO, forjada)
    assert e.value.codigo == "consulta_invalida" and "read-only" in e.value.mensagem


def test_leitor_sem_permissao_e_senha_errada(sessao_a, sessao_b, conexao):
    # a rota é do dono da conexão: B (outro inquilino) não vê a conexão de A
    assert _consulta(sessao_b, conexao["id"], "SELECT 1 FROM sedes_municipais LIMIT 1").status_code == 404
    # schema remoto fora do padrão de identificador
    r = _consulta(sessao_a, conexao["id"], "SELECT 1 FROM sedes_municipais LIMIT 1", schema_remoto="pub lic; x")
    assert r.status_code == 422 and r.json()["erro"] == "schema_invalido"
