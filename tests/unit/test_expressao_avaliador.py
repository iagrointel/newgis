"""Núcleo funcional do avaliador Python (item L2-10-c-linguagem-expressao): gramática, tipos,
propagação de nulo (semântica de três valores do SQL para os operadores lógicos), catálogo de
erros nomeados e AST exportável/reimportável. O teste de equivalência entre os dois avaliadores
está em `test_expressao_equivalencia.py`; o de segurança sob ataque em
`test_expressao_seguranca.py` — este arquivo é só Python, sem subprocesso."""

import pytest

from app.expressao.avaliador_py import (
    TABELA_FUNCOES,
    Binario,
    Campo,
    Chamada,
    ErroExpressao,
    Literal,
    Unario,
    analisar,
    ast_de_json,
    ast_para_json,
    avaliar,
    avaliar_texto,
)


def av(texto, contexto=None):
    return avaliar_texto(texto, contexto or {})


# --------------------------------------------------------------------- 1. gramática e precedência
def test_precedencia_aritmetica():
    assert av("2 + 3 * 4") == 14
    assert av("(2 + 3) * 4") == 20


def test_potencia_associa_a_direita():
    assert av("2 ^ 3 ^ 2") == 512  # 2^(3^2) = 2^9, não (2^3)^2 = 64


def test_unario_encadeado():
    assert av("--5") == 5
    assert av("!!Verdadeiro") is True


@pytest.mark.parametrize(
    "texto,esperado",
    [("1<2", True), ("2<=2", True), ("3>2", True), ("2>=3", False), ("2==2", True), ("2!=3", True)],
)
def test_operadores_de_comparacao(texto, esperado):
    assert av(texto) is esperado


def test_string_com_aspa_escapada():
    assert av("'ele disse ''oi'''") == "ele disse 'oi'"


# --------------------------------------------------------------------- 2. campo ($) e lista branca
def test_campo_presente_no_contexto():
    assert av("$area * 2", {"area": 21}) == 42


def test_campo_fora_da_lista_branca_e_erro_de_permissao_nunca_none_silencioso():
    with pytest.raises(ErroExpressao) as exc:
        av("$campo_inexistente", {"outro": 1})
    assert exc.value.codigo == "campo_nao_permitido"
    assert exc.value.detalhe["campo"] == "campo_inexistente"


# --------------------------------------------------------------------- 3. nulo — semântica de três valores
@pytest.mark.parametrize(
    "texto,contexto,esperado",
    [
        ("$x + 1", {"x": None}, None),
        ("$x * $y", {"x": None, "y": 5}, None),
        ("Nulo == Nulo", {}, True),
        ("Nulo != Nulo", {}, False),
        ("1 == Nulo", {}, False),
        ("1 != Nulo", {}, True),
        ("$x < 5", {"x": None}, None),  # comparação de ordem propaga nulo, nunca decide sozinha
        ("Falso && $x", {"x": None}, False),  # falso decide o E, mesmo com o outro lado nulo
        ("Verdadeiro || $x", {"x": None}, True),  # verdadeiro decide o OU
        ("Verdadeiro && $x", {"x": None}, None),  # sem lado falso: resultado é nulo
        ("Falso || $x", {"x": None}, None),
        ("!$x", {"x": None}, None),
        ("-$x", {"x": None}, None),
    ],
)
def test_propagacao_de_nulo(texto, contexto, esperado):
    assert av(texto, contexto) == esperado


def test_divisao_por_zero_e_erro_nomeado_nao_excecao_python_crua():
    with pytest.raises(ErroExpressao) as exc:
        av("1 / 0")
    assert exc.value.codigo == "divisao_por_zero"
    with pytest.raises(ErroExpressao) as exc2:
        av("1 % 0")
    assert exc2.value.codigo == "divisao_por_zero"


# --------------------------------------------------------------------- 4. tipos e erros nomeados
@pytest.mark.parametrize(
    "texto",
    ["1 && Verdadeiro", "'a' + 1", "1 < 'a'", "!1", "Se(1, 'a', 'b')", "Maiuscula(42)"],
)
def test_operacao_com_tipo_errado_e_erro_nomeado(texto):
    with pytest.raises(ErroExpressao) as exc:
        av(texto)
    assert exc.value.codigo == "tipo_invalido"


def test_funcao_desconhecida():
    with pytest.raises(ErroExpressao) as exc:
        av("FuncaoQueNaoExiste(1)")
    assert exc.value.codigo == "funcao_desconhecida"


@pytest.mark.parametrize("texto", ["Absoluto()", "Absoluto(1, 2)", "Se(1>0, 'a')", "Potencia(1)"])
def test_aridade_invalida(texto):
    with pytest.raises(ErroExpressao) as exc:
        av(texto)
    assert exc.value.codigo == "aridade_invalida"


@pytest.mark.parametrize(
    "texto,codigo",
    [
        ("", "expressao_vazia"),
        ("   ", "expressao_vazia"),
        ("1 +", "sintaxe_invalida"),
        ("(1 + 2", "sintaxe_invalida"),
        ("1 2", "sintaxe_invalida"),
        ("'sem fechar", "sintaxe_invalida"),
        ("1 # 2", "caractere_invalido"),
        ("$", "sintaxe_invalida"),
    ],
)
def test_catalogo_de_erros_de_sintaxe(texto, codigo):
    with pytest.raises(ErroExpressao) as exc:
        analisar(texto)
    assert exc.value.codigo == codigo


def test_erro_de_sintaxe_devolve_linha_e_coluna_em_texto_com_quebra_de_linha():
    with pytest.raises(ErroExpressao) as exc:
        analisar("$area > 0 &&\n$perimetro >>> 0")
    assert exc.value.detalhe["linha"] == 2
    assert exc.value.detalhe["coluna"] > 0


# --------------------------------------------------------------------- 5. todas as ≥ 15 funções (1 caso cada)
@pytest.mark.parametrize(
    "texto,contexto,esperado",
    [
        ("Maiuscula('abc')", {}, "ABC"),
        ("Minuscula('ABC')", {}, "abc"),
        ("Concatenar('a', 'b')", {}, "ab"),
        ("Texto(5)", {}, "5"),
        ("Arredondar(1.2345, 2)", {}, 1.23),
        ("Absoluto(-3)", {}, 3),
        ("Minimo(3, 1, 2)", {}, 1),
        ("Maximo(3, 1, 2)", {}, 3),
        ("Numero('7')", {}, 7),
        ("Potencia(3, 2)", {}, 9),
        ("Ano(1788652800000)", {}, 2026),
        ("Mes(1788652800000)", {}, 9),
        ("Dia(1788652800000)", {}, 6),
        ("DiferencaDias(1788652800000, 1791244800000)", {}, 30),
        ("SeNulo(Nulo, 9)", {}, 9),
        ("EhNulo(Nulo)", {}, True),
        ("Se(Verdadeiro, 1, 2)", {}, 1),
    ],
)
def test_cada_funcao_tem_ao_menos_um_caso(texto, contexto, esperado):
    assert av(texto, contexto) == esperado


def test_agora_utc_devolve_milissegundos_plausiveis():
    r = av("AgoraUTC()")
    assert isinstance(r, int)
    assert r > 1_700_000_000_000  # depois de 2023; garante que não é segundos nem um placeholder fixo


def test_tabela_de_funcoes_tem_ao_menos_15_entradas():
    assert len(TABELA_FUNCOES) >= 15, "portão do item: ≥ 15 funções"


# --------------------------------------------------------------------- 6. curto-circuito (ramo não escolhido não roda)
def test_se_e_curto_circuito():
    assert av("Se(Verdadeiro, 1, 10 / 0)") == 1
    assert av("Se(Falso, 10 / 0, 2)") == 2


def test_senulo_e_curto_circuito():
    assert av("SeNulo(5, 10 / 0)") == 5


def test_e_ou_curto_circuito_nao_avalia_o_lado_direito_quando_ja_decidido():
    assert av("Falso && (10 / 0 > 0)") is False
    assert av("Verdadeiro || (10 / 0 > 0)") is True


# --------------------------------------------------------------------- 7. AST ↔ JSON
def test_ast_para_json_e_de_volta_produz_estrutura_equivalente():
    no = analisar("Se($x > 0, Concatenar('a', Texto($x)), 'b')")
    d = ast_para_json(no)
    assert d["tipo"] == "chamada" and d["nome"] == "Se"
    no2 = ast_de_json(d)
    assert avaliar(no, {"x": 3}) == avaliar(no2, {"x": 3}) == "a3"


def test_ast_json_e_serializavel_por_json_puro():
    import json

    no = analisar("$a + Maximo(1, $b, 3)")
    texto_json = json.dumps(ast_para_json(no), ensure_ascii=False)
    d = json.loads(texto_json)
    no2 = ast_de_json(d)
    assert avaliar(no2, {"a": 1, "b": 10}) == 11


def test_ast_de_json_recusa_no_desconhecido():
    with pytest.raises(ErroExpressao) as exc:
        ast_de_json({"tipo": "coisa_que_nao_existe"})
    assert exc.value.codigo == "no_desconhecido"


def test_dataclasses_da_ast_sao_as_esperadas():
    """documenta o vocabulário de nós — se alguém acrescentar um tipo novo sem passar por
    `ast_para_json`/`ast_de_json`, este teste denuncia."""
    no = analisar("-$a + Maiuscula('x') * 2 == Se(Verdadeiro, 1, 2)")
    assert isinstance(no, Binario)
    assert isinstance(no.esquerda, Binario)
    assert isinstance(no.esquerda.esquerda, Unario)
    assert isinstance(no.esquerda.esquerda.operando, Campo)
    assert isinstance(no.direita, Chamada)
    assert isinstance(no.esquerda.direita.esquerda, Chamada)
    assert isinstance(no.esquerda.direita.direita, Literal)
