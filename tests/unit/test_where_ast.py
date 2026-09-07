"""Parser de `where` restrito (item L2-04-b, ADR pendente do L2-04-servicos-esri-ogc; ver
L2_CONCEITO.md seção C7). Nunca eval/exec, nunca string do cliente concatenada em SQL: todo valor
literal vira parâmetro `%s`; todo nome de campo passa pela lista branca do chamador antes de virar
texto de coluna. Casos de ataque (SQLi clássico, tautologia, empilhamento de instrução, comentário,
campo fora da lista branca) têm de ser recusados OU neutralizados como literal, nunca executados
como SQL; consulta legítima com 3 condições e parênteses tem de gerar o SQL esperado, comparado."""

import re

import pytest

from app.consulta import where_ast as w

COLUNAS = {"nome": "i.nome", "idade": "i.idade", "uf": "i.uf", "status": "i.status", "endereco": "i.endereco"}


def compilar(texto, colunas=COLUNAS):
    return w.compilar_where(texto, colunas)


# --------------------------------------------------------------------- 1. consultas legítimas
def test_comparacao_simples_igualdade():
    c = compilar("nome = 'Ana Silva'")
    assert c.sql == "i.nome = %s"
    assert c.params == ["Ana Silva"]


@pytest.mark.parametrize(
    "op,esperado",
    [("!=", "!="), ("<>", "!="), ("<", "<"), ("<=", "<="), (">", ">"), (">=", ">=")],
)
def test_todos_os_operadores_de_comparacao(op, esperado):
    c = compilar(f"idade {op} 30")
    assert c.sql == f"i.idade {esperado} %s"
    assert c.params == [30]


def test_numero_negativo_e_decimal():
    c = compilar("idade >= -3.5")
    assert c.sql == "i.idade >= %s"
    assert c.params == [-3.5]


def test_like():
    c = compilar("nome like '%Silva%'")
    assert c.sql == "i.nome LIKE %s"
    assert c.params == ["%Silva%"]


def test_in_com_strings():
    c = compilar("uf in ('SP', 'RJ', 'MG')")
    assert c.sql == "i.uf IN (%s, %s, %s)"
    assert c.params == ["SP", "RJ", "MG"]


def test_in_com_numeros():
    c = compilar("idade in (18, 21, 65)")
    assert c.sql == "i.idade IN (%s, %s, %s)"
    assert c.params == [18, 21, 65]


def test_is_null():
    c = compilar("endereco is null")
    assert c.sql == "i.endereco IS NULL"
    assert c.params == []


def test_is_not_null():
    c = compilar("endereco is not null")
    assert c.sql == "i.endereco IS NOT NULL"
    assert c.params == []


def test_palavras_chave_sao_case_insensitive():
    c = compilar("idade Is Not Null")
    assert c.sql == "i.idade IS NOT NULL"
    c2 = compilar("nome LIKE 'x' aNd idade > 1")
    assert c2.sql == "(i.nome LIKE %s AND i.idade > %s)"


def test_consulta_legitima_complexa_3_condicoes_and_or_parenteses():
    """A consulta-espelho do portão: 3 condições, AND/OR misturados, parênteses — compara com o
    SQL e os parâmetros esperados, na ordem em que aparecem no texto (contrato de `compilar`)."""
    texto = "(idade >= 18 AND idade <= 65) OR (uf = 'SP' AND status != 'inativo')"
    c = compilar(texto)
    assert c.sql == "((i.idade >= %s AND i.idade <= %s) OR (i.uf = %s AND i.status != %s))"
    assert c.params == [18, 65, "SP", "inativo"]


def test_precedencia_and_antes_de_or_sem_parenteses():
    # a AND b OR c AND d == (a AND b) OR (c AND d)
    c = compilar("idade = 1 AND uf = 'SP' OR idade = 2 AND uf = 'RJ'")
    assert c.sql == "((i.idade = %s AND i.uf = %s) OR (i.idade = %s AND i.uf = %s))"
    assert c.params == [1, "SP", 2, "RJ"]


def test_aspa_simples_escapada_dentro_de_string_literal():
    c = compilar("nome = 'O''Brien'")
    assert c.sql == "i.nome = %s"
    assert c.params == ["O'Brien"]


def test_coluna_mapeada_para_outra_expressao_sql_pelo_chamador():
    """A lista branca pode apontar para expressão diferente do nome no filtro (alias, cast, outra
    tabela) — o SQL final usa SÓ o que o chamador declarou, nunca o texto que o usuário digitou."""
    c = compilar("cidade = 'Recife'", colunas={"cidade": "c.nome_cidade::text"})
    assert c.sql == "c.nome_cidade::text = %s"
    assert c.params == ["Recife"]


def test_lista_branca_por_conjunto_de_nomes_vira_identificador_entre_aspas():
    c = compilar("idade = 1", colunas={"idade"})
    assert c.sql == '"idade" = %s'


# --------------------------------------------------------------------- 2. ataques recusados ou neutralizados
def test_injecao_classica_string_fechada_vira_parametro_nunca_executada():
    """O clássico `'; DROP TABLE--` só entra como VALOR de uma comparação legítima; vira parâmetro
    ligado, nunca texto de SQL — a tabela não aparece em lugar nenhum do `sql` produzido."""
    c = compilar("nome = '''; DROP TABLE camada; --'")
    assert c.sql == "i.nome = %s"
    assert c.params == ["'; DROP TABLE camada; --"]
    assert "DROP" not in c.sql
    assert "camada" not in c.sql


def test_injecao_com_ponto_e_virgula_fora_de_string_e_recusada():
    with pytest.raises(w.ErroWhere) as e:
        compilar("idade = 1; DROP TABLE camada")
    assert e.value.codigo in ("sintaxe_invalida", "caractere_invalido")


def test_injecao_com_comentario_sql_e_recusada():
    with pytest.raises(w.ErroWhere) as e:
        compilar("nome = 'a' -- ' OR '1'='1'")
    assert e.value.codigo == "caractere_invalido"


def test_tautologia_classica_1_igual_1_e_recusada():
    """`1=1 OR ...`: a gramática exige que o lado esquerdo de uma comparação seja um identificador
    de campo — um literal numérico nunca é aceito nessa posição, então a tautologia nem chega a
    ser avaliada como sintaxe válida."""
    with pytest.raises(w.ErroWhere) as e:
        compilar("1 = 1 OR nome = 'x'")
    assert e.value.codigo == "sintaxe_invalida"


def test_tautologia_com_string_do_lado_esquerdo_e_recusada():
    with pytest.raises(w.ErroWhere) as e:
        compilar("'1' = '1'")
    assert e.value.codigo == "sintaxe_invalida"


def test_campo_fora_da_lista_branca_e_recusado_na_compilacao():
    """Sintaticamente válido; recusado na hora de compilar contra a lista branca do chamador."""
    no = w.analisar("segredo_do_banco = 'x'")
    with pytest.raises(w.ErroWhere) as e:
        w.compilar(no, COLUNAS)
    assert e.value.codigo == "campo_nao_permitido"
    assert e.value.detalhe["campo"] == "segredo_do_banco"


def test_injecao_dentro_de_lista_in_vira_parametro():
    c = compilar("uf in ('SP', '''); DROP TABLE camada; --')")
    assert c.sql == "i.uf IN (%s, %s)"
    assert c.params == ["SP", "'); DROP TABLE camada; --"]
    assert "DROP" not in c.sql


def test_in_vazio_e_recusado():
    with pytest.raises(w.ErroWhere):
        compilar("uf in ()")


def test_string_sem_fechamento_e_recusada():
    with pytest.raises(w.ErroWhere) as e:
        compilar("nome = 'sem fechar")
    assert e.value.codigo == "sintaxe_invalida"


def test_caractere_nao_reconhecido_e_recusado():
    for texto in ["nome ~ 'x'", "idade = 1 # comentario", "nome = /* */ 'x'"]:
        with pytest.raises(w.ErroWhere) as e:
            compilar(texto)
        assert e.value.codigo == "caractere_invalido"


def test_texto_apos_expressao_completa_e_recusado():
    with pytest.raises(w.ErroWhere) as e:
        compilar("idade = 1 lixo")
    assert e.value.codigo == "sintaxe_invalida"


def test_parenteses_nao_fechados_sao_recusados():
    with pytest.raises(w.ErroWhere):
        compilar("(idade = 1")


def test_parenteses_excedentes_sao_recusados():
    with pytest.raises(w.ErroWhere):
        compilar("idade = 1)")


def test_expressao_vazia_e_recusada():
    with pytest.raises(w.ErroWhere) as e:
        compilar("")
    assert e.value.codigo == "expressao_vazia"


def test_aninhamento_acima_do_limite_e_recusado():
    texto = "(" * (w.MAX_PROFUNDIDADE + 1) + "idade = 1" + ")" * (w.MAX_PROFUNDIDADE + 1)
    with pytest.raises(w.ErroWhere) as e:
        compilar(texto)
    assert e.value.codigo == "expressao_complexa"


def test_aninhamento_no_limite_e_aceito():
    texto = "(" * w.MAX_PROFUNDIDADE + "idade = 1" + ")" * w.MAX_PROFUNDIDADE
    c = compilar(texto)
    assert c.params == [1]


def test_texto_acima_do_tamanho_maximo_e_recusado():
    with pytest.raises(w.ErroWhere) as e:
        compilar("nome = '" + "a" * w.MAX_TEXTO + "'")
    assert e.value.codigo == "expressao_complexa"


def test_nome_de_coluna_invalido_no_conjunto_e_recusado():
    with pytest.raises(w.ErroWhere) as e:
        compilar("idade = 1", colunas={"idade; DROP TABLE camada"})
    assert e.value.codigo == "coluna_invalida"


# --------------------------------------------------------------------- 3. garantias estáticas do módulo
def test_modulo_nao_usa_eval_nem_exec_nem_interpolacao_de_texto_em_sql():
    fonte = open(w.__file__, encoding="utf-8").read()
    assert not re.search(r"\beval\s*\(", fonte)
    assert not re.search(r"\bexec\s*\(", fonte)
    # nenhuma formatação de string (`%`, `.format`, f-string) recebe `valor`/`valores`/`texto` do
    # usuário para montar SQL — só `col` (sempre saído da lista branca) entra em f-string
    assert ".format(" not in fonte


def test_ast_e_tipada_antes_de_compilar():
    no = w.analisar("idade = 1 AND uf = 'SP'")
    assert isinstance(no, w.E)
    assert isinstance(no.esquerda, w.Comparacao)
    assert no.esquerda.campo == "idade"
    assert no.esquerda.operador == "="
    assert no.esquerda.valor == 1


# --------------------------------------------------------------------- 4. item L2-04-c: BETWEEN, NOT,
# literais de data/hora e as duas funções de texto do dialeto Esri ("standardized queries")
def test_between_numerico():
    c = compilar("idade between 18 and 65")
    assert c.sql == "i.idade BETWEEN %s AND %s"
    assert c.params == [18, 65]


def test_between_seguido_de_and_externo():
    c = compilar("idade between 18 and 65 and uf = 'SP'")
    assert c.sql == "(i.idade BETWEEN %s AND %s AND i.uf = %s)"
    assert c.params == [18, 65, "SP"]


def test_not_prefixo_em_comparacao():
    c = compilar("not idade = 1")
    assert c.sql == "NOT (i.idade = %s)"
    assert c.params == [1]


def test_not_prefixo_em_parenteses():
    c = compilar("not (idade = 1 and uf = 'SP')")
    assert c.sql == "NOT ((i.idade = %s AND i.uf = %s))"
    assert c.params == [1, "SP"]


def test_not_liga_mais_forte_que_and():
    # not a and b == (not a) and b
    no = w.analisar("not idade = 1 and uf = 'SP'")
    assert isinstance(no, w.E)
    assert isinstance(no.esquerda, w.Nao)


def test_date_literal_vira_parametro_date_python():
    import datetime

    c2 = w.compilar_where("idade > DATE '2020-01-01'", {"idade": "i.idade"})
    assert c2.sql == "i.idade > %s"
    assert c2.params == [datetime.date(2020, 1, 1)]


def test_timestamp_literal_vira_parametro_datetime_python():
    import datetime

    c = w.compilar_where("idade > TIMESTAMP '2020-01-01 10:30:00'", {"idade": "i.idade"})
    assert c.sql == "i.idade > %s"
    assert c.params == [datetime.datetime(2020, 1, 1, 10, 30, 0)]


def test_date_literal_formato_invalido_e_recusado():
    with pytest.raises(w.ErroWhere) as e:
        w.compilar_where("idade > DATE '01/01/2020'", {"idade": "i.idade"})
    assert e.value.codigo == "data_invalida"


def test_current_date_vira_literal_sql_fixo_nunca_parametro():
    c = w.compilar_where("idade < CURRENT_DATE", {"idade": "i.idade"})
    assert c.sql == "i.idade < CURRENT_DATE"
    assert c.params == []


def test_current_timestamp_vira_literal_sql_fixo():
    c = w.compilar_where("idade < CURRENT_TIMESTAMP", {"idade": "i.idade"})
    assert c.sql == "i.idade < CURRENT_TIMESTAMP"
    assert c.params == []


def test_upper_envolve_so_o_campo_da_lista_branca():
    c = compilar("upper(nome) = 'ANA'")
    assert c.sql == "UPPER(i.nome) = %s"
    assert c.params == ["ANA"]


def test_lower_envolve_so_o_campo_da_lista_branca():
    c = compilar("lower(uf) = 'sp'")
    assert c.sql == "LOWER(i.uf) = %s"


def test_upper_com_campo_fora_da_lista_branca_e_recusado():
    with pytest.raises(w.ErroWhere) as e:
        compilar("upper(segredo) = 'X'")
    assert e.value.codigo == "campo_nao_permitido"


def test_upper_de_expressao_arbitraria_e_recusado_na_sintaxe():
    # UPPER só aceita um identificador de campo — nunca uma sub-expressão, string ou número
    with pytest.raises(w.ErroWhere):
        compilar("upper('literal') = 'X'")
    with pytest.raises(w.ErroWhere):
        compilar("upper(1) = 'X'")


# --------------------------------------------------------------------- 5. ataques novos (L2-04-c)
def test_between_com_subselect_e_recusado():
    with pytest.raises(w.ErroWhere):
        compilar("idade between (select 1) and 65")


def test_funcao_nao_prevista_e_recusada():
    for texto in ["lower(idade); DROP TABLE camada", "extract(year from idade) = 1",
                  "cast(idade as text) = '1'", "pg_sleep(idade) = 1"]:
        with pytest.raises(w.ErroWhere):
            compilar(texto)


def test_date_com_injecao_no_literal_e_recusada_pelo_formato():
    with pytest.raises(w.ErroWhere) as e:
        w.compilar_where("idade > DATE '2020-01-01''; DROP TABLE camada; --'", {"idade": "i.idade"})
    assert e.value.codigo in ("data_invalida", "sintaxe_invalida")


def test_not_seguido_de_texto_invalido_e_recusado():
    with pytest.raises(w.ErroWhere):
        compilar("not")
    with pytest.raises(w.ErroWhere):
        compilar("not not")
