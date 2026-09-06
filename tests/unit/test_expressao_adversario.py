"""Ataque adversarial ao item L2-10-c-linguagem-expressao (turno 3, 06/09/2026).

Escrito por um agente que NÃO construiu a linguagem, contra o commit cb92de9, seguindo o roteiro
de `laco/handoffs/T3/L2-10-c-ADVERSARIO.md`. Duas classes de teste convivem aqui de propósito:

1. Testes normais — o ataque FALHOU, o produto se defendeu. Ficam como regressão: se um dia o
   guarda-corpo afrouxar, estes quebram.
2. Testes marcados `xfail(strict=True)` — o ataque PASSOU. A asserção escreve o comportamento
   CORRETO (o que o contrato promete), e ela falha hoje. `strict=True` faz o teste virar erro no
   dia em que o defeito for corrigido, obrigando quem corrigir a apagar a marca. Nenhum defeito
   fica registrado como "comportamento esperado".

O lado JavaScript é chamado pelo MESMO executor dos testes de equivalência
(`tests/expressoes/executar_js.mjs --stdin`), um processo Node para todos os casos do módulo.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
EXECUTOR_JS = RAIZ / "tests" / "expressoes" / "executar_js.mjs"
DOC = RAIZ / "docs" / "EXPRESSAO.md"

sys.path.insert(0, str(RAIZ))
from app.expressao.avaliador_py import (  # noqa: E402
    MAX_PASSOS_PADRAO,
    ErroExpressao,
    analisar,
    ast_de_json,
    avaliar,
    avaliar_texto,
)

# ---------------------------------------------------------------- utilidades de comparação


def _canonicalizar(valor):
    if isinstance(valor, bool) or valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, (int, float)):
        return int(valor) if isinstance(valor, float) and valor.is_integer() else valor
    if isinstance(valor, list):
        return [_canonicalizar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _canonicalizar(v) for k, v in valor.items()}
    raise AssertionError(f"tipo fora do contrato do avaliador: {type(valor)}")


def _serializar(resultado, erro):
    if erro is not None:
        return "ERRO:" + erro
    return json.dumps(_canonicalizar(resultado), ensure_ascii=True, sort_keys=True)


def _python(entrada, contexto):
    try:
        return _serializar(avaliar_texto(entrada, contexto), None)
    except ErroExpressao as e:
        return _serializar(None, e.codigo)
    except Exception as e:  # exceção CRUA: o contrato promete erro nomeado, isto é achado
        return _serializar(None, f"EXCECAO_NAO_TRATADA:{type(e).__name__}")


# Cada caso é (apelido, entrada, contexto). Os 46 casos abaixo são NOVOS: nenhum deles está em
# tests/expressoes/vetores.json (o teste `test_casos_do_adversario_sao_novos` prova isso).
CASOS_NOVOS: list[tuple[str, str, dict]] = [
    # --- operador resto com sinal (o documento não fixa convenção de sinal para '%')
    ("resto -7 por 3", "$a % $b", {"a": -7, "b": 3}),
    ("resto 7 por -3", "$a % $b", {"a": 7, "b": -3}),
    ("resto -1 por 2", "$a % $b", {"a": -1, "b": 2}),
    ("resto 5 por -2", "$a % $b", {"a": 5, "b": -2}),
    ("resto -0,5 por 2", "$a % $b", {"a": -0.5, "b": 2}),
    ("resto literal negativo", "(0-7) % 3", {}),
    ("resto dentro de Texto", "Texto((0-10) % 3)", {}),
    ("resto decide ramo do Se", "Se($a % $b > 0,'p','n')", {"a": -7, "b": 3}),
    # --- texto fora do plano básico multilíngue (par substituto / meia-substituta)
    ("Find de meia-substituta baixa", "Find($a,$b)", {"a": "\udf0d", "b": "\U0001f30d"}),
    ("Find de meia-substituta alta", "Find($a,$b)", {"a": "\ud83c", "b": "\U0001f30d"}),
    ("Split por meia-substituta", "Split($t,$s)", {"t": "a\U0001f30db", "s": "\udf0d"}),
    ("Replace de meia-substituta", "Replace($t,$s,'X')", {"t": "a\U0001f30db", "s": "\udf0d"}),
    ("Contagem de par montado de duas metades", "Contagem(Concatenar($a,$b))", {"a": "\ud83c", "b": "\udf0d"}),
    ("Left de par montado de duas metades", "Left(Concatenar($a,$b),1)", {"a": "\ud83c", "b": "\udf0d"}),
    ("menor que entre emoji e caractere BMP", "$a < $b", {"a": "\U0001f30d", "b": "�"}),
    ("menor ou igual entre emoji e BMP", "$a <= $b", {"a": "\U0001f30d", "b": "�"}),
    ("maior ou igual entre emoji e BMP", "$a >= $b", {"a": "\U0001f30d", "b": "�"}),
    ("menor que entre plano 1 e BMP alto", "$a < $b", {"a": "\U00010000", "b": "＀"}),
    # --- os que o produto DEFENDE (mesmos temas, sem divergência)
    ("Contagem de emoji", "Contagem($t)", {"t": "a\U0001f30d"}),
    ("Left sobre emoji", "Left($t,2)", {"t": "a\U0001f30db"}),
    ("Mid sobre emoji", "Mid($t,1,1)", {"t": "a\U0001f30db"}),
    ("Right sobre emoji", "Right($t,1)", {"t": "a\U0001f30d"}),
    ("Find depois do emoji", "Find('b',$t)", {"t": "a\U0001f30db"}),
    ("Split vazio sobre emoji", "Split($t,'')", {"t": "a\U0001f30d"}),
    ("acento composto contra precomposto", "$a == $b", {"a": "á", "b": "á"}),
    ("Contagem de acento composto", "Contagem($t)", {"t": "á"}),
    ("Maiuscula de acento composto", "Maiuscula($t)", {"t": "á"}),
    ("Maiuscula de eszett", "Maiuscula($t)", {"t": "ß"}),
    ("Minuscula de I com ponto", "Minuscula($t)", {"t": "İ"}),
    ("Maiuscula de deseret", "Maiuscula($t)", {"t": "\U00010428"}),
    # --- número muito grande, zero negativo
    ("zero negativo em Texto", "Texto(-$z)", {"z": 0}),
    ("zero negativo em TextoNumero", "TextoNumero(0-0.0001,2)", {}),
    ("Texto de 1e308", "Texto($x)", {"x": 1e308}),
    ("Texto acima de 2^53", "Texto($x)", {"x": 9007199254740994}),
    ("Texto de 1e21", "Texto($x)", {"x": 1e21}),
    ("soma que estoura o double", "$x+$x", {"x": 1.7e308}),
    ("produto que estoura o double", "$x*$x", {"x": 1e200}),
    ("Arredondar com fator infinito", "Arredondar($x,15)", {"x": 1e308}),
    # --- conversão de texto para número
    ("Numero com algarismo arábico-índico", "Numero($t)", {"t": "٤٢"}),
    ("Numero com algarismo devanágari", "Numero($t)", {"t": "१२"}),
    ("Numero com algarismo de largura inteira", "Numero($t)", {"t": "１２"}),
    ("Numero com algarismo matemático", "Numero($t)", {"t": "\U0001d7d9\U0001d7da"}),
    # --- data: ano bissexto, antes de 1970, milissegundo fracionário
    ("Ano de milissegundo fracionário negativo", "Ano(0-0.5)", {}),
    ("Mes de milissegundo fracionário negativo", "Mes(0-0.5)", {}),
    ("Dia de milissegundo fracionário negativo", "Dia(0-0.5)", {}),
    ("Ano de -0,4 milissegundo", "Ano(0-0.4)", {}),
    ("TextoData de milissegundo fracionário negativo", "TextoData(0-0.5,'data_hora_segundos')", {}),
    ("Dia de 29 de fevereiro de 2024", "Dia($d)", {"d": 1709164800000}),
    ("TextoData no ano 1", "TextoData($d,'extenso')", {"d": -62135596800000}),
    ("TextoData em 1900 (não bissexto)", "TextoData($d)", {"d": -2203891200000}),
    ("TextoData em 1600 (bissexto secular)", "TextoData($d)", {"d": -11676096000000}),
    ("TextoData um milissegundo antes da época", "TextoData(0-1,'data_hora_segundos')", {}),
    ("Weekday antes da época", "Weekday(0-1)", {}),
    ("DiferencaDias com fração negativa", "DiferencaDias(0-0.5,0)", {}),
]

# Divergências MEDIDAS neste ataque (apelido → (resultado Python, resultado JavaScript)).
DIVERGENCIAS_MEDIDAS = {
    "resto -7 por 3": ("2", "-1"),
    "resto 7 por -3": ("-2", "1"),
    "resto -1 por 2": ("1", "-1"),
    "resto 5 por -2": ("-1", "1"),
    "resto -0,5 por 2": ("1.5", "-0.5"),
    "resto literal negativo": ("2", "-1"),
    "resto dentro de Texto": ('"2"', '"-1"'),
    "resto decide ramo do Se": ('"p"', '"n"'),
    "Find de meia-substituta baixa": ("-1", "1"),
    "Find de meia-substituta alta": ("-1", "0"),
    "Split por meia-substituta": ('["a\\ud83c\\udf0db"]', '["a\\ud83c", "b"]'),
    "Replace de meia-substituta": ('"a\\ud83c\\udf0db"', '"a\\ud83cXb"'),
    "Contagem de par montado de duas metades": ("2", "1"),
    "Left de par montado de duas metades": ('"\\ud83c"', '"\\ud83c\\udf0d"'),
    "menor que entre emoji e caractere BMP": ("false", "true"),
    "menor ou igual entre emoji e BMP": ("false", "true"),
    "maior ou igual entre emoji e BMP": ("true", "false"),
    "menor que entre plano 1 e BMP alto": ("false", "true"),
    "Numero com algarismo arábico-índico": ("42", "null"),
    "Numero com algarismo devanágari": ("12", "null"),
    "Numero com algarismo de largura inteira": ("12", "null"),
    "Numero com algarismo matemático": ("12", "null"),
    "Ano de milissegundo fracionário negativo": ("1969", "1970"),
    "Mes de milissegundo fracionário negativo": ("12", "1"),
    "Dia de milissegundo fracionário negativo": ("31", "1"),
    "Ano de -0,4 milissegundo": ("1969", "1970"),
}


@pytest.fixture(scope="module")
def resultados_js() -> dict[str, str]:
    entrada = [{"entrada": e, "contexto": c} for _apelido, e, c in CASOS_NOVOS]
    r = subprocess.run(
        ["node", str(EXECUTOR_JS), "--stdin"],
        input=json.dumps(entrada),
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(RAIZ),
        check=True,
    )
    saida = json.loads(r.stdout)
    assert len(saida) == len(CASOS_NOVOS)
    return {
        apelido: _serializar(item["resultado"], item["erro"])
        for (apelido, _e, _c), item in zip(CASOS_NOVOS, saida, strict=True)
    }


def test_casos_do_adversario_sao_novos():
    """Nenhum dos casos deste arquivo repete um vetor de tests/expressoes/vetores.json — o ataque
    tem de sair de onde o construtor já mediu."""
    vetores = json.loads((RAIZ / "tests" / "expressoes" / "vetores.json").read_text(encoding="utf-8"))
    conhecidos = {(v["entrada"], json.dumps(v.get("contexto") or {}, sort_keys=True)) for v in vetores}
    novos = {(e, json.dumps(c, sort_keys=True)) for _a, e, c in CASOS_NOVOS}
    assert len(CASOS_NOVOS) >= 40, "o roteiro pede ao menos 40 casos novos"
    assert not (novos & conhecidos)


@pytest.mark.parametrize(
    "apelido,entrada,contexto",
    [c for c in CASOS_NOVOS if c[0] not in DIVERGENCIAS_MEDIDAS],
    ids=[c[0] for c in CASOS_NOVOS if c[0] not in DIVERGENCIAS_MEDIDAS],
)
def test_ataque_2_casos_em_que_python_e_javascript_concordam(apelido, entrada, contexto, resultados_js):
    """Ataque 2, parte que FALHOU: nestes o produto se defendeu (emoji em Left/Mid/Right/Split,
    acento composto, caixa alta de eszett/deseret, número acima de 2^53, estouro do double)."""
    assert _python(entrada, contexto) == resultados_js[apelido]


@pytest.mark.parametrize(
    "apelido,entrada,contexto",
    [c for c in CASOS_NOVOS if c[0] in DIVERGENCIAS_MEDIDAS],
    ids=[c[0] for c in CASOS_NOVOS if c[0] in DIVERGENCIAS_MEDIDAS],
)
@pytest.mark.xfail(strict=True, reason="ACHADO 1: Python e JavaScript divergem fora dos 309 vetores")
def test_ataque_2_python_e_javascript_tem_de_concordar(apelido, entrada, contexto, resultados_js):
    """Ataque 2 que PASSOU. O contrato (docs/EXPRESSAO.md §6) diz que os dois avaliadores dão o
    MESMO resultado para o mesmo texto e o mesmo contexto. Estes 26 casos provam que não dão.
    Causas medidas: (a) '%' — Python usa resto de módulo com sinal do divisor, JavaScript usa
    resto truncado com sinal do dividendo; (b) texto — Python indexa e compara PONTO DE CÓDIGO,
    JavaScript indexa e compara UNIDADE UTF-16 em `<`, `indexOf`, `split` e `replace`;
    (c) `Numero` — o `\\d` do Python casa dígito Unicode de qualquer escrita, o do JavaScript não;
    (d) `Ano`/`Mes`/`Dia` com milissegundo fracionário negativo — `datetime.timedelta` arredonda
    para o microssegundo mais próximo (vai para 1969) e `new Date` trunca para zero (fica em 1970).
    Quando estiver corrigido, apagar a marca xfail."""
    esperado_py, esperado_js = DIVERGENCIAS_MEDIDAS[apelido]
    obtido_py, obtido_js = _python(entrada, contexto), resultados_js[apelido]
    assert (obtido_py, obtido_js) == (esperado_py, esperado_js), "a divergência medida mudou de forma"
    assert obtido_py == obtido_js


@pytest.mark.xfail(strict=True, reason="ACHADO 2: TextoNumero levanta decimal.InvalidOperation crua")
@pytest.mark.parametrize(
    "valor,casas",
    [(1e13, 15), (1e14, 14), (1e20, 8), (1e20, 15), (1e15, 14)],
    ids=["1e13/15", "1e14/14", "1e20/8", "1e20/15", "1e15/14"],
)
def test_ataque_2_texto_numero_devolve_erro_nomeado_e_nao_excecao_crua(valor, casas):
    """`_texto_numero_pt` usa `decimal.Decimal(n).quantize(...)` com o contexto PADRÃO do módulo
    `decimal` (28 dígitos significativos). Quando dígitos inteiros + casas passa de 28, o
    `quantize` levanta `decimal.InvalidOperation`, que NÃO é `ErroExpressao` nem está na lista
    que `avaliar` captura (`OverflowError, ValueError, ZeroDivisionError`) — a exceção sobe crua
    para quem chamou. O guarda `abs(n) >= 1e21` não pega: 1e20 com 8 casas já estoura. O lado
    JavaScript, com `toFixed`, devolve o texto normalmente — logo é também divergência."""
    entrada, contexto = f"TextoNumero($x,{casas})", {"x": valor}
    resultado = _python(entrada, contexto)
    assert not resultado.startswith("ERRO:EXCECAO_NAO_TRATADA"), resultado


# ---------------------------------------------------------------- ataque 1: custo por passo


def _cadeia_plana(unidade: str, grupos: int = 3, por_grupo: int = 64) -> str:
    """`Minimo` é variádico (64 argumentos) e chato de aprofundar: 3 grupos de 64 dão 192 chamadas
    da unidade com profundidade 3 e ~1.550 tokens — o máximo que os limites do parser deixam passar
    (encadear com '+' não serve: a árvore fica à esquerda e bate em profundidade_excedida aos 60)."""
    return "Minimo(%s)" % ",".join("Minimo(%s)" % ",".join([unidade] * por_grupo) for _ in range(grupos))


ATAQUES_DE_CUSTO = [
    ("192 Maiuscula de 20.000 acentuados", _cadeia_plana("Contagem(Maiuscula($t))"), {"t": "á" * 20000}),
    ("192 Find de agulha de 10.000 em 20.000", _cadeia_plana("Find($a,$b)"), {"a": "a" * 9999 + "b", "b": "a" * 20000}),
    ("192 Contagem de texto de 20.000", _cadeia_plana("Contagem($t)"), {"t": "a" * 20000}),
    ("192 Contagem de 10.000 emoji", _cadeia_plana("Contagem($t)"), {"t": "\U0001f30d" * 10000}),
    ("192 Juntar de lista de 1.024", _cadeia_plana("Contagem(Juntar($l,''))"), {"l": ["a"] * 1024}),
    ("192 Split vazio de 1.024", _cadeia_plana("Contagem(Split($t,''))"), {"t": "a" * 1024}),
    ("192 Reverter de lista de 1.024", _cadeia_plana("Contagem(Reverter($l))"), {"l": list(range(1024))}),
    ("192 Soma de lista de 1.024", _cadeia_plana("Soma($l)"), {"l": [1] * 1024}),
    ("192 Numero de 20.000 dígitos", _cadeia_plana("SeNulo(Numero($t),0)"), {"t": "1" * 20000}),
    ("192 Texto de 1e308", _cadeia_plana("Contagem(Texto($x))"), {"x": 1e308}),
]


@pytest.mark.parametrize("apelido,entrada,contexto", ATAQUES_DE_CUSTO, ids=[a[0] for a in ATAQUES_DE_CUSTO])
def test_ataque_1_nenhuma_expressao_legal_passa_de_500_ms_no_servidor(apelido, entrada, contexto):
    """Ataque 1, que FALHOU. Procurei função cujo trabalho cresça mais rápido que a contagem de
    passos (`Replace`, `Split('')`, `Juntar`, `Find`, `Maiuscula`, `Numero`, concatenação em
    cadeia) e montei a expressão de maior trabalho que os limites do parser aceitam. Nenhuma passa
    de 500 ms: o teto de trabalho de UMA operação é o teto do VALOR (20.000 pontos de código,
    1.024 elementos), e nenhuma operação sobre esse teto custa mais que ~0,06 ms nesta máquina."""
    no = analisar(entrada)
    inicio = time.perf_counter()
    try:
        avaliar(no, contexto)
    except ErroExpressao:
        pass
    decorrido_ms = (time.perf_counter() - inicio) * 1000.0
    assert decorrido_ms < 500.0, f"{apelido} levou {decorrido_ms:.2f} ms"


def test_ataque_1_no_javascript_o_estouro_do_relogio_de_50_ms_fica_abaixo_de_5_ms(tmp_path):
    """A mesma bateria no avaliador do cliente, com o orçamento apertado de 50 ms. O que importa
    não é o tempo total (o relógio corta), é o ESTOURO: quanto o avaliador passa do limite depois
    da última conferência. Se houvesse uma operação cara que não cobra passo, o estouro seria da
    ordem do custo dela. Medido: menos de 1 ms."""
    arquivo = tmp_path / "ataques.json"
    arquivo.write_text(json.dumps([{"entrada": e, "contexto": c} for _a, e, c in ATAQUES_DE_CUSTO]), encoding="utf-8")
    programa = (
        "import {readFileSync} from 'node:fs';\n"
        "import {analisar,avaliar,ErroExpressao} from '%s';\n"
        "const casos=JSON.parse(readFileSync(process.argv[process.argv.length-1],'utf8'));let pior=0;\n"
        "for(const c of casos){const no=analisar(c.entrada);\n"
        "  try{avaliar(no,c.contexto,{limiteMs:50});}catch(e){}\n"
        "  const t=performance.now();\n"
        "  try{avaliar(no,c.contexto,{limiteMs:50});}catch(e){if(!(e instanceof ErroExpressao))throw e;}\n"
        "  pior=Math.max(pior,performance.now()-t-50);}\n"
        "process.stdout.write(String(pior));\n" % (RAIZ / "web" / "js" / "expressao" / "avaliador.js")
    )
    r = subprocess.run(
        ["node", "--input-type=module", "-e", programa, "--", str(arquivo)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(RAIZ),
        check=True,
    )
    estouro_ms = float(r.stdout)
    assert estouro_ms < 5.0, f"estouro do relógio de 50 ms no JavaScript: {estouro_ms:.2f} ms"


# ---------------------------------------------------------------- ataque 3: AST fabricada à mão

_L = {"tipo": "literal", "tipo_valor": "numero", "valor": 1}


def _ast_profunda(n: int) -> dict:
    d = dict(_L)
    for _ in range(n):
        d = {"tipo": "unario", "operador": "-", "operando": d}
    return d


def _ast_ciclica() -> dict:
    d: dict = {"tipo": "unario", "operador": "-", "operando": None}
    d["operando"] = d
    return d


AST_FABRICADAS = [
    ("tipo de nó desconhecido", {"tipo": "lambda", "corpo": 1}),
    ("nó sem campo tipo", {"nome": "x"}),
    ("literal com tipo_valor incoerente", {"tipo": "literal", "tipo_valor": "numero", "valor": "texto"}),
    ("literal com tipo_valor fora do contrato", {"tipo": "literal", "tipo_valor": "lista", "valor": [1, 2]}),
    ("literal de texto com valor lista", {"tipo": "literal", "tipo_valor": "texto", "valor": ["a"]}),
    ("literal booleano declarado número", {"tipo": "literal", "tipo_valor": "numero", "valor": True}),
    ("campo com nome fora do identificador", {"tipo": "campo", "nome": "a.b"}),
    ("campo com nome não textual", {"tipo": "campo", "nome": 5}),
    ("unário com operador inventado", {"tipo": "unario", "operador": "~", "operando": _L}),
    ("binário com operador inventado", {"tipo": "binario", "operador": "**", "esquerda": _L, "direita": _L}),
    ("chamada com nome não identificador", {"tipo": "chamada", "nome": "a b", "argumentos": []}),
    ("chamada com argumentos que não são lista", {"tipo": "chamada", "nome": "Texto", "argumentos": {"0": _L}}),
    ("chamada com 65 argumentos", {"tipo": "chamada", "nome": "Minimo", "argumentos": [_L] * 65}),
    ("profundidade 200", _ast_profunda(200)),
    ("ciclo no operando", _ast_ciclica()),
    (
        "grafo compartilhado de 64 x 64 nós",
        {
            "tipo": "chamada",
            "nome": "Minimo",
            "argumentos": [{"tipo": "chamada", "nome": "Minimo", "argumentos": [_L] * 64}] * 64,
        },
    ),
]

AST_QUE_SO_FALHAM_NA_AVALIACAO = [
    ("campo proibido", {"tipo": "campo", "nome": "__proto__"}, "campo_nao_permitido"),
    ("campo fora do contexto", {"tipo": "campo", "nome": "qualquer"}, "campo_nao_permitido"),
    ("Se com 1 argumento", {"tipo": "chamada", "nome": "Se", "argumentos": [_L]}, "aridade_invalida"),
    ("Left com 5 argumentos", {"tipo": "chamada", "nome": "Left", "argumentos": [_L] * 5}, "aridade_invalida"),
    ("função inexistente", {"tipo": "chamada", "nome": "Exec", "argumentos": []}, "funcao_desconhecida"),
    (
        "literal infinito",
        {"tipo": "literal", "tipo_valor": "numero", "valor": float("inf")},
        "numero_invalido",
    ),
]


@pytest.mark.parametrize("apelido,dados", AST_FABRICADAS, ids=[a[0] for a in AST_FABRICADAS])
def test_ataque_3_ast_fabricada_e_recusada_na_importacao_com_erro_nomeado(apelido, dados):
    """Ataque 3, que FALHOU. Nenhuma destas chega a avaliar: `ast_de_json` recusa na importação
    com `ErroExpressao`, nunca com exceção crua nem com recursão que estoura a pilha."""
    with pytest.raises(ErroExpressao) as excecao:
        ast_de_json(dados)
    assert excecao.value.codigo in {"no_desconhecido", "expressao_grande", "profundidade_excedida"}


@pytest.mark.parametrize(
    "apelido,dados,codigo", AST_QUE_SO_FALHAM_NA_AVALIACAO, ids=[a[0] for a in AST_QUE_SO_FALHAM_NA_AVALIACAO]
)
def test_ataque_3_ast_bem_formada_mas_fora_do_contrato_falha_na_avaliacao(apelido, dados, codigo):
    """Estas passam pela importação (a forma do nó é válida) e param na avaliação, também com erro
    nomeado. Aridade de função e existência da função são conferidas em tempo de avaliação, não na
    importação — o que importa é que nenhuma avalia."""
    no = ast_de_json(dados)
    with pytest.raises(ErroExpressao) as excecao:
        avaliar(no, {})
    assert excecao.value.codigo == codigo


def test_ataque_3_campo_extra_no_no_e_ignorado_nos_dois_lados():
    """Único ponto do ataque 3 em que o contrato é TOLERANTE: campo desconhecido dentro de um nó
    (inclusive uma chave literal `__proto__` vinda de JSON) é ignorado, não recusado. Não muda
    comportamento nem polui protótipo — mas está registrado, porque uma AST assinada com campo
    extra não é rejeitada."""
    dados = json.loads('{"tipo":"literal","tipo_valor":"numero","valor":7,"extra":"x","__proto__":{"p":1}}')
    assert avaliar(ast_de_json(dados), {}) == 7


# ---------------------------------------------------------------- ataque 4: contexto hostil no JS


def _node_modulo(corpo: str) -> str:
    caminho = RAIZ / "web" / "js" / "expressao" / "avaliador.js"
    r = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"import {{analisar,avaliar,avaliarTexto,astDeJson,ErroExpressao}} from '{caminho}';\n{corpo}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(RAIZ),
        check=True,
    )
    return json.loads(r.stdout)


def test_ataque_4_javascript_nao_le_prototipo_nem_executa_getter():
    """Ataque 4, que FALHOU no que importa: protótipo poluído não vira campo, getter no contexto
    e getter dentro de dicionário/lista NUNCA são executados (`proprio()` exige descritor de dado),
    `toJSON`/`valueOf` não são chamados, `__proto__`/`constructor`/`prototype` como nome de campo
    dão `campo_nao_permitido` e nada do ataque polui `Object.prototype`."""
    saida = _node_modulo(
        """
const r={};
function tenta(nome,ctx,expr){ try{ r[nome]=['ok',avaliarTexto(expr,ctx)]; }
  catch(e){ r[nome]=[(e instanceof ErroExpressao)?'erro':'excecao_crua', e.codigo||e.message]; } }
Object.prototype.injetado='VAZOU';
tenta('campo_so_no_prototipo',{},'$injetado');
tenta('obter_chave_so_no_prototipo',{d:{a:1}},"Obter($d,'injetado')");
delete Object.prototype.injetado;
let lidoContexto=0; const ctxGetter={};
Object.defineProperty(ctxGetter,'x',{get(){lidoContexto++;return 42;},enumerable:true,configurable:true});
tenta('contexto_com_getter',ctxGetter,'$x');
let lidoDentro=0; const dicGetter={};
Object.defineProperty(dicGetter,'k',{get(){lidoDentro++;return 1;},enumerable:true,configurable:true});
tenta('dicionario_com_getter',{d:dicGetter},"Obter($d,'k')");
const lista=[1,2];
let lidoIndice=0;
Object.defineProperty(lista,'0',{get(){lidoIndice++;return 9;},enumerable:true,configurable:true});
tenta('lista_com_getter_no_indice',{l:lista},'Primeiro($l)');
let chamouToJson=0;
tenta('to_json_no_dicionario',{d:{toJSON(){chamouToJson++;return 'x';},a:1}},'Contagem($d)');
let chamouValueOf=0;
tenta('value_of_no_dicionario',{d:{valueOf(){chamouValueOf++;return 1;}}},'Contagem($d)');
tenta('chave_proto_vinda_de_json',{d:JSON.parse('{"__proto__":{"x":1},"a":2}')},"Obter($d,'__proto__')");
tenta('campo_constructor',{constructor:'dado'},'$constructor');
tenta('campo_prototype',{prototype:'dado'},'$prototype');
tenta('contexto_sem_prototipo',Object.assign(Object.create(null),{a:5}),'$a');
let getterDeAst=0; const astComGetter={tipo:'literal',tipo_valor:'numero'};
Object.defineProperty(astComGetter,'valor',{get(){getterDeAst++;return 7;},enumerable:true,configurable:true});
try{ r.ast_com_getter=['ok',avaliar(astDeJson(astComGetter),{})]; }
catch(e){ r.ast_com_getter=[(e instanceof ErroExpressao)?'erro':'excecao_crua',e.codigo||e.message]; }
r.contadores={lidoContexto,lidoDentro,lidoIndice,chamouToJson,chamouValueOf,getterDeAst};
r.prototipo_poluido=Object.prototype.injetado===undefined && Object.prototype.p===undefined;
process.stdout.write(JSON.stringify(r));
"""
    )
    assert saida["contadores"] == {
        "lidoContexto": 0,
        "lidoDentro": 0,
        "lidoIndice": 0,
        "chamouToJson": 0,
        "chamouValueOf": 0,
        "getterDeAst": 0,
    }
    assert saida["prototipo_poluido"] is True
    assert saida["campo_so_no_prototipo"] == ["erro", "campo_nao_permitido"]
    assert saida["obter_chave_so_no_prototipo"] == ["ok", None]
    assert saida["contexto_com_getter"] == ["erro", "tipo_invalido"]
    assert saida["dicionario_com_getter"] == ["erro", "tipo_invalido"]
    assert saida["lista_com_getter_no_indice"] == ["erro", "tipo_invalido"]
    assert saida["to_json_no_dicionario"] == ["erro", "tipo_invalido"]
    assert saida["value_of_no_dicionario"] == ["erro", "tipo_invalido"]
    assert saida["chave_proto_vinda_de_json"] == ["erro", "campo_nao_permitido"]
    assert saida["campo_constructor"] == ["erro", "campo_nao_permitido"]
    assert saida["campo_prototype"] == ["erro", "campo_nao_permitido"]
    assert saida["contexto_sem_prototipo"] == ["ok", 5]
    assert saida["ast_com_getter"] == ["erro", "no_desconhecido"]


@pytest.mark.xfail(strict=True, reason="ACHADO 4: contexto Proxy no JS resolve qualquer campo e roda armadilha")
def test_ataque_4_contexto_exotico_deveria_ser_recusado_como_no_python():
    """Ataque 4 que PASSOU em parte. `avaliar` do Python confere `type(contexto) is not dict` e
    recusa qualquer objeto exótico. O JavaScript não confere nada no contexto de TOPO: um `Proxy`
    sobre objeto simples atravessa (o protótipo do alvo é `Object.prototype`), suas armadilhas
    `has`/`getOwnPropertyDescriptor` executam código de quem montou o contexto, e `$qualquerCampo`
    resolve. A lista branca de campos, no JavaScript, vale só até o objeto passado ser simples.
    O mesmo vale para uma AST entregue como `Proxy`. Correção: aplicar ao contexto de topo o mesmo
    teste de protótipo que `valorSeguro` já aplica a dicionário aninhado."""
    saida = _node_modulo(
        """
const r={};
let armadilhas=0;
const px=new Proxy({},{has(){armadilhas++;return true;},
  getOwnPropertyDescriptor(){armadilhas++;return {value:'QUALQUER',enumerable:true,configurable:true};},
  ownKeys(){armadilhas++;return ['a'];}});
try{ r.proxy=['ok',avaliarTexto('$campoQueNaoExiste',px)]; }
catch(e){ r.proxy=[(e instanceof ErroExpressao)?'erro':'excecao_crua',e.codigo||e.message]; }
let trapAst=0;
const astPx=new Proxy({tipo:'literal',tipo_valor:'numero',valor:7},{get(t,k){trapAst++;return t[k];}});
try{ r.ast_proxy=['ok',avaliar(astDeJson(astPx),{})]; }
catch(e){ r.ast_proxy=[(e instanceof ErroExpressao)?'erro':'excecao_crua',e.codigo||e.message]; }
r.armadilhas=armadilhas; r.trap_ast=trapAst;
process.stdout.write(JSON.stringify(r));
"""
    )
    assert saida["armadilhas"] == 0 and saida["trap_ast"] == 0
    assert saida["proxy"][0] == "erro"


def test_ataque_4_python_recusa_contexto_que_nao_e_dicionario():
    """Contraprova: o lado Python fecha essa porta."""

    class ContextoQueResponde(dict):
        def __missing__(self, chave):  # pragma: no cover — nunca chamado, o tipo é recusado antes
            return "VAZOU"

    with pytest.raises(ErroExpressao) as excecao:
        avaliar(analisar("$qualquer"), ContextoQueResponde())
    assert excecao.value.codigo == "tipo_invalido"


# ---------------------------------------------------------------- ataque 5: valor intermediário

ATAQUES_DE_MEMORIA = [
    ("Concatenar 64 textos de 20.000", "Contagem(Concatenar(%s))" % ",".join(["$t"] * 64), {"t": "a" * 20000}),
    ("Lista de 64 listas de 1.024", "Contagem(Lista(%s))" % ",".join(["$l"] * 64), {"l": list(range(1024))}),
    ("Replace que multiplica por 20", "Contagem(Replace($t,'a','%s'))" % ("b" * 20), {"t": "a" * 19999}),
    ("Split vazio de texto de 20.000", "Contagem(Split($t,''))", {"t": "a" * 20000}),
    ("Unicos de 1.024 listas", "Contagem(Unicos($l))", {"l": [[1, 2, 3, i] for i in range(1024)]}),
    (
        "árvore de 192 Concatenar dobrados",
        _cadeia_plana("Contagem(Concatenar($t,$t))"),
        {"t": "a" * 20000},
    ),
]


@pytest.mark.parametrize("apelido,entrada,contexto", ATAQUES_DE_MEMORIA, ids=[a[0] for a in ATAQUES_DE_MEMORIA])
def test_ataque_5_valor_intermediario_nao_passa_de_4_mib(apelido, entrada, contexto):
    """Ataque 5, que FALHOU. Todo resultado de nó passa por `_valor_seguro` antes de subir na
    árvore, então o valor intermediário máximo é o de UMA operação sobre valores já limitados:
    64 argumentos × 20.000 pontos de código. Pico medido nesta bateria: ~2,1 MiB, sempre seguido
    de `valor_grande`."""
    import tracemalloc

    no = analisar(entrada)
    tracemalloc.start()
    try:
        avaliar(no, contexto)
    except ErroExpressao:
        pass
    _atual, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert pico < 4 * 1024 * 1024, f"{apelido}: pico de {pico / 1024 / 1024:.2f} MiB"


# ---------------------------------------------------------------- ataque 6: honestidade da paridade

# Linha da tabela da seção 10 de docs/EXPRESSAO.md → (o que a documentação oficial do Arcade diz,
# lida em developers.arcgis.com/arcade/function-reference/ em 06/09/2026, e o que a nossa faz).
LINHAS_FEITO_QUE_NAO_SAO_FEITO = {
    "Month": (
        "Arcade: 'Values range from 0-11 where January is 0 and December is 11' "
        "(date_functions). Nosso `Mes(0)` devolve 1. A própria observação da linha diz '1-12'.",
    ),
    "Now": (
        "Arcade: 'Creates a Date value representing the current date and time in the time zone of "
        "the profile's execution context' — hora LOCAL. `AgoraUTC` é UTC; o equivalente de UTC é "
        "`Timestamp`, que já tem linha própria.",
    ),
    "Abs": ("Arcade: 'If the input is null, then it returns 0'. Nosso `Absoluto(nulo)` levanta `tipo_invalido`.",),
    "Reverse": (
        "Arcade: 'Reverses the contents of the array in place'. O nosso devolve cópia — a própria "
        "observação da linha diz isso e mesmo assim marca feito.",
    ),
    "Back": (
        "Arcade: 'If the input array is empty, then the expression evaluation will fail'. "
        "`Ultimo(Lista())` devolve nulo.",
    ),
    "Front": (
        "Arcade: mesma regra do Back — falha em lista vazia. `Primeiro(Lista())` devolve nulo "
        "(isso equivale ao `First` do Arcade, que tem linha própria, não ao `Front`).",
    ),
}


def _linhas_da_secao_10() -> list[tuple[str, str, str]]:
    texto = DOC.read_text(encoding="utf-8")
    secao = texto.split("## 10. Paridade")[1].split("## 11.")[0]
    linhas = []
    for linha in secao.splitlines():
        campos = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(campos) >= 3 and campos[2] in {"feito", "parcial", "fora"}:
            linhas.append((campos[0], campos[1], campos[2]))
    return linhas


def test_ataque_6_a_tabela_de_paridade_existe_e_tem_as_linhas_conferidas():
    linhas = _linhas_da_secao_10()
    assert len(linhas) >= 130, f"seção 10 com {len(linhas)} linhas de função"
    nomes = {nome for nome, _nosso, _estado in linhas}
    assert set(LINHAS_FEITO_QUE_NAO_SAO_FEITO) <= nomes


@pytest.mark.parametrize("arcade", sorted(LINHAS_FEITO_QUE_NAO_SAO_FEITO), ids=sorted(LINHAS_FEITO_QUE_NAO_SAO_FEITO))
@pytest.mark.xfail(strict=True, reason="ACHADO 3: linha marcada 'feito' que não é 'feito'")
def test_ataque_6_nenhuma_destas_linhas_pode_estar_marcada_feito(arcade):
    """Ataque 6, que PASSOU. Conferi 17 das linhas `feito` contra a documentação oficial do Arcade
    (developers.arcgis.com/arcade/function-reference/, lida em 06/09/2026); 6 delas não são `feito`.
    Cada uma vale como promessa em documento de paridade — é o defeito mais grave desta entrega.
    Quando a linha for corrigida para `parcial`/`fora`, este teste passa e a marca xfail sai."""
    estados = {estado for nome, _nosso, estado in _linhas_da_secao_10() if nome == arcade}
    assert "feito" not in estados, LINHAS_FEITO_QUE_NAO_SAO_FEITO[arcade][0]


def test_ataque_6_o_mesmo_nome_do_arcade_carrega_estados_contraditorios():
    """Achado menor da mesma varredura: `DefaultValue` aparece em três categorias com três estados
    (`parcial` para `SeNulo`, `parcial` para `Obter(lista, i, padrão)` e `feito` para
    `Obter(dic, chave, padrão)`), sendo uma função só no Arcade — `DefaultValue(value, defaultValue)`,
    substituição de nulo/vazio, nunca busca por chave. Registro do fato, sem corrigir."""
    estados = sorted({estado for nome, _nosso, estado in _linhas_da_secao_10() if nome == "DefaultValue"})
    assert estados == ["feito", "parcial"], estados


# ---------------------------------------------------------------- ataque 7: conferência dos números


def test_ataque_7_contagem_independente_de_funcoes_e_vetores():
    """Contado dos arquivos, não do handoff: 43 funções na tabela do Python, as MESMAS 43 no
    JavaScript (lidas pelo `--nomes-funcoes` do executor) e 309 vetores."""
    from app.expressao.avaliador_py import TABELA_FUNCOES

    vetores = json.loads((RAIZ / "tests" / "expressoes" / "vetores.json").read_text(encoding="utf-8"))
    r = subprocess.run(
        ["node", str(EXECUTOR_JS), "--nomes-funcoes"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(RAIZ),
        check=True,
    )
    nomes_js = set(json.loads(r.stdout))
    assert len(TABELA_FUNCOES) == 43
    assert nomes_js == set(TABELA_FUNCOES)
    assert len(vetores) == 309
    assert MAX_PASSOS_PADRAO == 100_000


def test_ataque_7_o_documento_declara_o_mesmo_numero_de_funcoes_que_o_codigo():
    from app.expressao.avaliador_py import TABELA_FUNCOES

    titulo = re.search(r"^## 5\. Catálogo de funções \((\d+)\)", DOC.read_text(encoding="utf-8"), re.M)
    assert titulo is not None
    assert int(titulo.group(1)) == len(TABELA_FUNCOES)
