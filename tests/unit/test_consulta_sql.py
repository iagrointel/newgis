"""Validador da consulta SQL do cliente sobre o banco externo (item L6-02-j-bancos-externos, `app/conexao/
consulta_sql.py`). Portão: "consulta SQL recusa DDL/DML e exige LIMIT". Refutação: adversário tenta
`SELECT ...; DROP TABLE` e consulta sem LIMIT. Tudo aqui é recusado ANTES de qualquer conexão: o validador é
função pura sobre texto + lista branca."""

from __future__ import annotations

import pytest

from app import limites
from app.conexao import consulta_sql
from app.conexao.consulta_sql import ConsultaRecusada, validar

TABELAS = {"sedes_municipais", "municipios", "tabela_grande"}


def _recusa(sql: str, codigo: str, schema: str = "public"):
    with pytest.raises(ConsultaRecusada) as e:
        validar(sql, TABELAS, schema)
    assert e.value.codigo == codigo, (sql, e.value.codigo, e.value.mensagem)
    return e.value


def test_aceita_select_com_limit_e_devolve_tabelas():
    v = validar("SELECT nome, geom FROM sedes_municipais WHERE uf = 'BA' ORDER BY nome LIMIT 100 OFFSET 10", TABELAS,
                "public")
    assert v.limite == 100 and v.tabelas == ["sedes_municipais"]
    v = validar('select a.nome from public."sedes_municipais" a join municipios m on m.id = a.id limit 5', TABELAS,
                "public")
    assert v.limite == 5 and v.tabelas == ["sedes_municipais", "municipios"]


def test_aceita_cte_e_subconsulta_sobre_a_lista():
    v = validar(
        "WITH ba AS (SELECT * FROM sedes_municipais WHERE uf = 'BA') "
        "SELECT count(*) AS n FROM ba WHERE id IN (SELECT id FROM municipios) LIMIT 1",
        TABELAS, "public",
    )
    assert v.tabelas == ["sedes_municipais", "municipios"] and v.limite == 1


# adversário: "SELECT ...; DROP TABLE" e variantes de escrita em qualquer posição
@pytest.mark.parametrize("sql", [
    "SELECT 1 FROM sedes_municipais LIMIT 1; DROP TABLE sedes_municipais",
    "SELECT 1 FROM sedes_municipais LIMIT 1;",
    "SELECT * FROM sedes_municipais LIMIT 1 -- ; drop table x",
    "SELECT /* drop */ 1 FROM sedes_municipais LIMIT 1",
    "SELECT $$x$$ FROM sedes_municipais LIMIT 1",
])
def test_recusa_encadeamento_comentario_e_bloco(sql):
    _recusa(sql, "consulta_recusada")


@pytest.mark.parametrize("sql", [
    "DROP TABLE sedes_municipais",
    "DELETE FROM sedes_municipais LIMIT 1",
    "UPDATE sedes_municipais SET nome = 'x' LIMIT 1",
    "INSERT INTO sedes_municipais SELECT * FROM sedes_municipais LIMIT 1",
    "SELECT * INTO nova FROM sedes_municipais LIMIT 1",
    "SELECT * FROM sedes_municipais WHERE id IN (DELETE FROM municipios RETURNING id) LIMIT 1",
    "WITH x AS (UPDATE municipios SET nome = 'a' RETURNING *) SELECT * FROM x LIMIT 1",
    "SELECT * FROM sedes_municipais FOR UPDATE LIMIT 1",
    "CREATE TABLE z AS SELECT * FROM sedes_municipais LIMIT 1",
    "TRUNCATE sedes_municipais",
    "GRANT ALL ON sedes_municipais TO PUBLIC",
    "SELECT set_config('x', 'y', false) FROM sedes_municipais LIMIT 1",
    "SELECT * FROM sedes_municipais, LATERAL (SELECT 1 FOR SHARE) q LIMIT 1",
    "LOCK TABLE sedes_municipais",
    "EXPLAIN SELECT * FROM sedes_municipais LIMIT 1",
    "COPY sedes_municipais TO '/tmp/x'",
    "SELECT pg_sleep(30) FROM sedes_municipais LIMIT 1",
    "SELECT pg_read_file('/etc/passwd') FROM sedes_municipais LIMIT 1",
    "SELECT * FROM dblink('host=x', 'select 1') AS t(a int) LIMIT 1",
    "SELECT pg_terminate_backend(1) FROM sedes_municipais LIMIT 1",
    "SELECT current_setting('is_superuser') FROM sedes_municipais LIMIT 1",
])
def test_recusa_ddl_dml_e_funcoes_de_sistema(sql):
    e = _recusa(sql, "consulta_recusada")
    assert e.mensagem


def test_palavra_proibida_dentro_de_string_nao_conta():
    v = validar("SELECT nome FROM sedes_municipais WHERE nome = 'drop table' OR nome = 'it''s delete' LIMIT 3",
                TABELAS, "public")
    assert v.limite == 3
    # ';' é recusado mesmo dentro de string: "um comando só" é regra de forma, mais simples de auditar
    _recusa("SELECT nome FROM sedes_municipais WHERE nome = 'a; b' LIMIT 3", "consulta_recusada")


# refutação: consulta sem LIMIT (na tabela de 100 mi de linhas) nunca chega ao banco
@pytest.mark.parametrize("sql", [
    "SELECT * FROM tabela_grande",
    "SELECT * FROM tabela_grande WHERE valor > 0 ORDER BY id",
    "SELECT * FROM tabela_grande LIMIT ALL",
    "SELECT * FROM tabela_grande LIMIT 10 OFFSET 5 UNION SELECT * FROM tabela_grande",
    "SELECT * FROM (SELECT * FROM tabela_grande LIMIT 10) q",
])
def test_exige_limit_no_fim(sql):
    _recusa(sql, "limit_obrigatorio")


@pytest.mark.parametrize("n", [0, limites.CONEXAO_PG_CONSULTA_LINHAS_MAX + 1, 100_000_000])
def test_limit_dentro_do_teto(n):
    _recusa(f"SELECT * FROM tabela_grande LIMIT {n}", "limit_acima_do_teto")
    assert validar(f"SELECT * FROM tabela_grande LIMIT {limites.CONEXAO_PG_CONSULTA_LINHAS_MAX}", TABELAS,
                   "public").limite == limites.CONEXAO_PG_CONSULTA_LINHAS_MAX


def test_lista_branca_de_tabelas_e_schema():
    _recusa("SELECT * FROM pg_catalog.pg_authid LIMIT 1", "tabela_fora_da_lista")
    _recusa("SELECT * FROM pg_shadow LIMIT 1", "tabela_fora_da_lista")
    _recusa("SELECT * FROM information_schema.tables LIMIT 1", "tabela_fora_da_lista")
    _recusa("SELECT * FROM outro_schema.sedes_municipais LIMIT 1", "tabela_fora_da_lista")
    _recusa("SELECT * FROM sedes_municipais s JOIN segredos x ON x.id = s.id LIMIT 1", "tabela_fora_da_lista")
    _recusa("SELECT * FROM public.sedes_municipais LIMIT 1", "tabela_fora_da_lista", schema="outro")
    _recusa("SELECT 1 LIMIT 1", "consulta_recusada")  # sem tabela da conexão não há o que consultar
    _recusa("", "consulta_vazia")
    _recusa("SHOW ALL", "consulta_recusada")
    _recusa("SELECT " + "1+" * 3000 + "1 FROM sedes_municipais LIMIT 1", "consulta_longa")


def test_lista_de_palavras_cobre_o_que_o_item_nomeia():
    for p in ("insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "copy"):
        assert p in consulta_sql.PALAVRAS_PROIBIDAS
    for f in ("pg_sleep", "pg_read_file", "dblink", "lo_import"):
        assert f in consulta_sql.FUNCOES_PROIBIDAS
