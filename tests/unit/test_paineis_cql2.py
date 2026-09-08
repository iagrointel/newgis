"""`app.paineis.cql2` (item L2-06-a-modelo-painel-fontes): tradução CQL2-JSON -> texto de `where_ast`,
depois compilação de verdade por `where_ast.compilar_where` — o ponto de auditoria de injeção é o mesmo
dos outros consumidores dessa gramática (nunca um SQL novo, ver docstring do módulo)."""

import pytest

from app.consulta.where_ast import compilar_where
from app.erros import ErroAPI
from app.paineis.cql2 import cql2_para_texto

COLUNAS = {"categoria": '"categoria"', "valor": '"valor"', "id": '"id"'}


def _sql(filtro):
    texto = cql2_para_texto(filtro)
    return compilar_where(texto, COLUNAS)


def test_none_e_vazio_nao_geram_filtro():
    assert cql2_para_texto(None) is None
    assert cql2_para_texto({}) is None


def test_comparacao_simples_texto_e_numero():
    c = _sql({"op": "=", "args": [{"property": "categoria"}, "agua"]})
    assert c.sql == '"categoria" = %s' and c.params == ["agua"]
    c = _sql({"op": ">=", "args": [{"property": "valor"}, 10]})
    assert c.sql == '"valor" >= %s' and c.params == [10]


def test_and_or_aninhado():
    filtro = {
        "op": "and",
        "args": [
            {"op": "=", "args": [{"property": "categoria"}, "agua"]},
            {"op": ">", "args": [{"property": "valor"}, 5]},
        ],
    }
    c = _sql(filtro)
    assert c.params == ["agua", 5]
    assert "AND" in c.sql


def test_in_e_isnull_e_like():
    c = _sql({"op": "in", "args": [{"property": "categoria"}, ["agua", "energia"]]})
    assert c.params == ["agua", "energia"]
    c = _sql({"op": "isNull", "args": [{"property": "valor"}]})
    assert c.params == []
    c = _sql({"op": "like", "args": [{"property": "categoria"}, "%agu%"]})
    assert c.params == ["%agu%"]


def test_literal_com_aspa_simples_escapa_sem_quebrar_sql():
    c = _sql({"op": "=", "args": [{"property": "categoria"}, "o'brien"]})
    assert c.params == ["o'brien"]  # o parâmetro chega intacto (nunca concatenado em texto)


def test_operador_desconhecido_e_erro_422():
    with pytest.raises(ErroAPI) as exc:
        cql2_para_texto({"op": "drop_table", "args": [{"property": "categoria"}, "x"]})
    assert exc.value.status_code == 422 and exc.value.erro == "filtro_cql2_invalido"


def test_property_ausente_e_erro():
    with pytest.raises(ErroAPI):
        cql2_para_texto({"op": "=", "args": ["categoria", "agua"]})


def test_literal_booleano_e_recusado():
    with pytest.raises(ErroAPI):
        cql2_para_texto({"op": "=", "args": [{"property": "categoria"}, True]})


def test_campo_fora_da_lista_branca_falha_na_compilacao_nao_na_traducao():
    """CQL2 não sabe quais campos existem (isso é responsabilidade de `where_ast.compilar_where` com a
    lista branca do chamador) — a tradução aceita qualquer nome de propriedade sintaticamente válido."""
    from app.consulta.where_ast import ErroWhere

    texto = cql2_para_texto({"op": "=", "args": [{"property": "coluna_que_nao_existe"}, "x"]})
    with pytest.raises(ErroWhere):
        compilar_where(texto, COLUNAS)
