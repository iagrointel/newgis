"""Compila um subconjunto da linguagem de expressão própria (item L2-10-c-linguagem-expressao,
`app/expressao/avaliador_py.py`) para uma expressão da MapLibre Style Spec v8 (item
L2-02-d-rotulos: "texto = campo ou expressão ... compilada para expressão MapLibre quando
possível ... e, quando não, pré-calculada como coluna de rótulo no tile").

Só a AST — nunca o texto — entra aqui: quem chama já rodou `avaliador_py.analisar(texto)`. Nada
de `eval`/`exec`/`compile`; a função é recursiva descendente sobre o mesmo tipo `No` do avaliador.

O QUE COMPILA (tem operador nativo de mesma semântica na Style Spec, https://maplibre.org/maplibre-
style-spec/expressions/): literais, `$campo` (`["get", campo]`), aritmética `+ - * /`, comparação
`== != < <= > >=`, lógica `&& ||` e `!`, `Se` (`case`), `SeNulo` (`coalesce`), `EhNulo`
(comparação com `null`), `Concatenar`/`Texto` (`concat`/`to-string` — nulo vira "" nos dois lados,
mesma convenção), `Maiuscula`/`Minuscula` (`upcase`/`downcase`), `Absoluto`/`Minimo`/`Maximo`
(`abs`/`min`/`max`), `Arredondar` sem casas ou com casas fixas (`round` combinado com `* / 10^n`).

O QUE NÃO COMPILA (levanta `NaoCompilavel`, motivo nomeado — cai para a coluna pré-calculada do
servidor): `%` e `^` (sem operador nativo equivalente), `TextoNumero`/`TextoData` (formatação
pt-BR de milhar/decimal e de data por extenso não tem tradução 1:1 na Style Spec), e qualquer
função de coleção/data/texto fora da lista acima (`Trim`, `Left`, `Right`, `Mid`, `Find`, `Split`,
`Replace`, `Numero`, `Potencia`, `AgoraUTC`, `Ano`, `Mes`, `Dia`, `DiferencaDias`, `Floor`, `Ceil`,
`Sqrt`, `Weekday`, `Decode`, `Lista`, `Contagem`, `Primeiro`, `Ultimo`, `Obter`, `Contem`, `Soma`,
`Media`, `Reverter`, `Unicos`, `Juntar`).
"""

from __future__ import annotations

from app.expressao.avaliador_py import Binario, Campo, Chamada, Literal, Unario

# Funções com equivalente nativo 1:1 na Style Spec (fora as tratadas por código próprio abaixo).
_FUNCOES_DIRETAS = {"Absoluto": "abs", "Minimo": "min", "Maximo": "max"}

# Funções conhecidas mas SEM equivalente — nomeadas aqui para a mensagem de erro citar o motivo
# certo (formatação pt-BR) em vez de "função desconhecida".
_SEM_EQUIVALENTE = {
    "TextoNumero": "formatação de número em pt-BR (separador de milhar/decimal) não tem operador nativo na Style Spec",
    "TextoData": "formatação de data em pt-BR não tem operador nativo na Style Spec",
}


class NaoCompilavel(Exception):
    """A expressão (ou uma parte dela) não tem tradução para a MapLibre Style Spec.

    `motivo` é a frase que vai para o handoff/log e para `plat_construtor.rotulos` (campo
    `motivo_servidor` de cada classe, gravado pelo compilador de estilo para o editor explicar por
    que aquela classe cai para a coluna pré-calculada)."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _num(no) -> float | int:
    if isinstance(no, Literal) and no.tipo_valor == "numero":
        return no.valor
    raise NaoCompilavel("esperava um número literal neste ponto (casas de Arredondar)")


def compilar(no) -> object:
    """AST → expressão MapLibre (lista/escalar/`None`). Levanta `NaoCompilavel` com motivo."""
    if isinstance(no, Literal):
        return None if no.tipo_valor == "nulo" else no.valor

    if isinstance(no, Campo):
        return ["get", no.nome]

    if isinstance(no, Unario):
        operando = compilar(no.operando)
        if no.operador == "-":
            return ["-", 0, operando]
        if no.operador == "!":
            return ["!", operando]
        raise NaoCompilavel(f"operador unário {no.operador!r} sem equivalente")

    if isinstance(no, Binario):
        op = no.operador
        if op in ("%", "^"):
            raise NaoCompilavel(f"operador {op!r} sem operador nativo na Style Spec")
        esquerda = compilar(no.esquerda)
        direita = compilar(no.direita)
        if op in ("+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">="):
            return [op, esquerda, direita]
        if op == "&&":
            return ["all", esquerda, direita]
        if op == "||":
            return ["any", esquerda, direita]
        raise NaoCompilavel(f"operador {op!r} sem equivalente")

    if isinstance(no, Chamada):
        nome = no.nome
        if nome in _SEM_EQUIVALENTE:
            raise NaoCompilavel(_SEM_EQUIVALENTE[nome])
        if nome in _FUNCOES_DIRETAS:
            return [_FUNCOES_DIRETAS[nome]] + [compilar(a) for a in no.argumentos]
        if nome == "Concatenar":
            # convenção do avaliador: nulo vira texto vazio (avaliador_py._chamar_funcao/Concatenar).
            # ["to-string", null] já devolve "" na Style Spec — mesma convenção, sem tratamento à parte.
            return ["concat"] + [["to-string", compilar(a)] for a in no.argumentos]
        if nome == "Texto":
            return ["to-string", compilar(no.argumentos[0])]
        if nome == "Maiuscula":
            return ["upcase", compilar(no.argumentos[0])]
        if nome == "Minuscula":
            return ["downcase", compilar(no.argumentos[0])]
        if nome == "Se":
            return ["case", compilar(no.argumentos[0]), compilar(no.argumentos[1]), compilar(no.argumentos[2])]
        if nome == "SeNulo":
            return ["coalesce", compilar(no.argumentos[0]), compilar(no.argumentos[1])]
        if nome == "EhNulo":
            return ["==", compilar(no.argumentos[0]), None]
        if nome == "Arredondar":
            valor = compilar(no.argumentos[0])
            casas = _num(no.argumentos[1]) if len(no.argumentos) > 1 else 0
            if casas == 0:
                return ["round", valor]
            fator = 10 ** int(casas)
            return ["/", ["round", ["*", valor, fator]], fator]
        raise NaoCompilavel(f"função {nome!r} sem compilação para MapLibre")

    raise NaoCompilavel("nó de AST desconhecido")
