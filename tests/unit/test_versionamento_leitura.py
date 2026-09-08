"""Unidade do montador de relação versionada (item L2-13-a, app/versionamento/leitura.py).

O que se verifica aqui sem banco: os nomes de schema/tabela nunca entram no SQL sem passar pelo padrão
que os define (é texto interpolado, não parâmetro — se a validação cair, vira injeção), a relação tem as
três pernas que a regra da Esri exige, e o número de marcadores `%s` bate com o número de parâmetros
devolvidos (uma divergência aqui é `IndexError` em produção, no caminho de leitura do FeatureServer).
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.erros import ErroAPI
from app.versionamento import consulta, leitura

COLUNAS = ["fid", "nome", "area", "geom", "globalid", "versao", "tenant_id"]
SCHEMA, TABELA = "d_demo", "c_0123456789abcdef"
MOMENTO = dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.timezone.utc)
VERSAO = "11111111-2222-3333-4444-555555555555"


def test_nomes_invalidos_sao_recusados():
    for schema in ("demo", "d_Demo", 'd_demo"; DROP TABLE x; --', "", None):
        with pytest.raises(ErroAPI):
            leitura.nomes_ok(schema, TABELA)
    for tabela in ("c_XYZ", "c_0123", "tabela", 'c_0123456789abcdef"', None):
        with pytest.raises(ErroAPI):
            leitura.nomes_ok(SCHEMA, tabela)
    assert leitura.nomes_ok(SCHEMA, TABELA) == (SCHEMA, TABELA)


def test_tabela_de_ramo_cabe_no_limite_de_nome_do_postgres():
    nome = leitura.tabela_ramo(TABELA)
    assert nome == "c_0123456789abcdef__ramo"
    assert len(nome) < 63


def test_relacao_do_padrao_no_momento_tem_as_duas_pernas_e_os_parametros_certos():
    sql, params = leitura.relacao_padrao_no_momento(None, SCHEMA, TABELA, 4674, MOMENTO, COLUNAS)
    assert sql.count("UNION ALL") == 1
    assert f'"{SCHEMA}"."{TABELA}"' in sql
    assert "plat.feicao_historico" in sql
    assert "h.operacao <> 'inserir'" in sql
    assert sql.count("%s") == len(params)
    # o momento é parâmetro, nunca texto colado
    assert MOMENTO in params and str(MOMENTO) not in sql


def test_relacao_do_ramo_tem_as_tres_pernas_e_exclui_o_que_o_ramo_tocou():
    sql, params = leitura.relacao_do_ramo(None, SCHEMA, TABELA, 4674, VERSAO, MOMENTO, COLUNAS)
    assert sql.count("UNION ALL") == 2
    assert f'"{SCHEMA}"."{leitura.tabela_ramo(TABELA)}"' in sql
    assert "b.momento_fim IS NULL AND NOT b.apagada" in sql
    assert sql.count("NOT IN (SELECT globalid FROM toque)") == 2
    assert sql.count("%s") == len(params)
    assert params.count(VERSAO) == 2  # a CTE de toque e a perna do ramo


def test_projecao_tem_a_mesma_ordem_nas_tres_pernas():
    """`UNION ALL` casa coluna por POSIÇÃO: se as pernas divergirem, `nome` de uma vira `area` de outra
    sem erro nenhum do banco. A prova é a ordem literal em cada perna."""
    sql, _ = leitura.relacao_do_ramo(None, SCHEMA, TABELA, 4674, VERSAO, MOMENTO, COLUNAS)
    pernas = sql.split("UNION ALL")
    assert len(pernas) == 3
    ordem_esperada = [c for c in COLUNAS]
    for perna in pernas:
        achadas = [c for c in ordem_esperada if f'"{c}"' in perna or (c == "geom" and "geom_antes" in perna)]
        assert achadas == ordem_esperada, perna


def test_historic_moment_aceita_epoch_em_milissegundos_e_iso():
    assert consulta.momento_de("1757332800000") == dt.datetime.fromtimestamp(
        1757332800, tz=dt.timezone.utc
    )
    assert consulta.momento_de("2026-09-08T12:00:00Z") == MOMENTO
    assert consulta.momento_de("2026-09-08T12:00:00").tzinfo is not None
    with pytest.raises(ErroAPI) as e:
        consulta.momento_de("ontem")
    assert e.value.erro == "historicmoment_invalido"
