"""HARD-03 — adversário L2, o parser de `where`/CQL (item L2-04-b, app/consulta/where_ast.py). É o único gerador
de SQL a partir de filtro do cliente (FeatureServer, OGC API, painel dependem dele), então é o ponto de auditoria
de injeção. Ataques: valor com aspas/ponto-e-vírgula/comentário nunca vira texto de SQL (sempre `%s`); nome de
coluna fora da lista branca é recusado; identificador com caractere de SQL nunca vira coluna; negação de serviço
(texto/tokens/profundidade) é cortada. Só roda em trilha (conftest do pacote). Módulo puro: sem banco, rápido."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.consulta import where_ast as w  # noqa: E402

COLUNAS = {"cidade": "c.nome_cidade", "uf": '"uf"', "pop": '"populacao"'}

INJECOES = [
    "cidade = 'x'; DROP TABLE plat.item;--",
    "cidade = 'x' OR '1'='1'",
    "cidade = 'x'/**/UNION/**/SELECT/**/senha_hash/**/FROM/**/plat.usuario--",
    "cidade = '\\'; DELETE FROM plat.usuario WHERE ''='",
    "cidade = 'a' OR pg_sleep(10) > 0",
    "cidade = 'a'||(SELECT senha_hash FROM plat.usuario LIMIT 1)",
]


@pytest.mark.parametrize("filtro", INJECOES)
def test_l2_04b_valor_com_veneno_vai_para_parametro_nunca_para_o_sql(filtro):
    """O valor perigoso, quando o filtro é sintaticamente aceito, sai como parâmetro; o texto do SQL só tem `%s`,
    o nome de coluna de confiança e os operadores da gramática — nunca o conteúdo do valor."""
    try:
        consulta = w.compilar_where(filtro, COLUNAS)
    except w.ErroWhere:
        return  # recusado na sintaxe também é uma defesa válida — nada chega ao SQL
    sql = consulta.sql
    # nada do valor do usuário no texto do SQL
    for agulha in ("DROP", "DELETE", "UNION", "SELECT", "pg_sleep", "senha_hash", "--", ";", "'"):
        assert agulha not in sql, (filtro, agulha, sql)
    # o valor perigoso está nos parâmetros, fora do texto
    assert consulta.params, (filtro, sql)
    # o SQL só usa marcadores e a expressão de coluna de confiança
    assert "%s" in sql or "IS N" in sql, sql


def test_l2_04b_coluna_fora_da_lista_branca_e_recusada():
    for campo in ("senha_hash", "usuario.senha", "pop; DROP", "(SELECT 1)"):
        try:
            w.compilar_where(f"{campo} = 1", COLUNAS)
        except w.ErroWhere:
            pass  # recusado (fora da lista branca ou nem tokeniza como identificador): o que importa e nao passar
        else:
            pytest.fail(f"campo fora da lista branca aceito: {campo!r}")


def test_l2_04b_lista_branca_por_conjunto_valida_identificador():
    # nome legítimo vira identificador entre aspas; nome com caractere de SQL é recusado na normalização
    ok = w.compilar_where("cidade = 'sp'", {"cidade"})
    assert ok.sql == '"cidade" = %s' and ok.params == ["sp"]
    for nome_ruim in ('cidade"; DROP--', "a b", "1col", "col;", 'c")'):
        with pytest.raises(w.ErroWhere):
            w.compilar_where("x = 1", {nome_ruim})


def test_l2_04b_identificador_de_campo_no_filtro_nunca_carrega_sql():
    """O campo do lado esquerdo é um identificador ASCII pela gramática; um 'campo' com aspas/espaço/; não
    tokeniza como ident, então nem chega à checagem de lista branca — é erro de sintaxe."""
    for texto in ('col"onha = 1', "col;drop = 1", "col' = 1", "col-- = 1"):
        with pytest.raises(w.ErroWhere):
            w.analisar(texto)


def test_l2_04b_negacao_de_servico_cortada():
    assert w.MAX_TEXTO <= 100_000 and w.MAX_TOKENS <= 10_000 and w.MAX_PROFUNDIDADE <= 200
    with pytest.raises(w.ErroWhere):
        w.analisar("cidade = 'a' " + "OR cidade = 'a' " * w.MAX_TOKENS)
    with pytest.raises(w.ErroWhere):
        w.analisar("(" * (w.MAX_PROFUNDIDADE + 5) + "cidade = 1" + ")" * (w.MAX_PROFUNDIDADE + 5))
    with pytest.raises(w.ErroWhere):
        w.analisar("cidade = '" + "a" * (w.MAX_TEXTO + 10) + "'")


def test_l2_04b_in_e_like_tambem_parametrizam():
    consulta = w.compilar_where("uf IN ('SP','RJ','; DROP--') AND cidade LIKE '%s;--'", COLUNAS)
    assert consulta.sql.count("%s") == 4, consulta.sql
    assert "DROP" not in consulta.sql and ";" not in consulta.sql
    assert "; DROP--" in consulta.params and "%s;--" in consulta.params
