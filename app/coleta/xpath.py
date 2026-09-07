"""Tradutor do XPath de XLSForm (relevant, constraint, calculation, choice_filter) para a linguagem de expressão
própria (L2-10-c, `app/expressao/avaliador_py.py`). Item L2-07-b.

Regra do C6 (L2_CONCEITO.md): a paridade é por FUNÇÃO, com três estados — `feito` (traduz sem perda), `parcial`
(traduz um subconjunto, registrado em aviso) e `fora` (não traduz; a regra inteira é descartada e o aviso guarda o
trecho original). Nada é traduzido em silêncio: `traduzir()` devolve o texto na linguagem própria E a lista de
avisos; quem chama decide o que fazer com uma expressão que ficou `fora`.

Convenções do contexto que os dois motores (Python e JavaScript) montam para avaliar uma regra:
  `$<campo>`            valor atual do campo (data e data-hora como milissegundos UTC, como manda o EXPRESSAO.md);
  `$_valor`             o `.` do XPath: valor do próprio campo cuja regra está sendo avaliada;
  `$<repeticao>`        lista de linhas (dicionários) de uma repetição;
  `$<repeticao>__<c>`   lista dos valores da coluna `c` da repetição (o caminho `${rep}/c` do XPath);
  `$_lista_<nome>`      dicionário `name -> linha` de uma lista de escolhas (para `pulldata`);
  `$_linha`             a linha da lista sendo filtrada por `choice_filter` (dicionário com as colunas extras).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FEITO, PARCIAL, FORA = "feito", "parcial", "fora"
MS_DIA = 86_400_000


class ErroXPath(Exception):
    def __init__(self, mensagem: str, posicao: int = 0):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.posicao = posicao


@dataclass
class Aviso:
    funcao: str
    estado: str
    trecho: str
    motivo: str

    def json(self) -> dict:
        return {"funcao": self.funcao, "estado": self.estado, "trecho": self.trecho, "motivo": self.motivo}


@dataclass
class Traducao:
    texto: str | None  # None quando alguma parte ficou `fora`
    avisos: list[Aviso] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        return self.texto is not None


# ----------------------------------------------------------------------------------------------- tokenizador
_RE_TOKEN = re.compile(
    r"""
    (?P<espaco>\s+)
  | (?P<var>\$\{\s*(?P<var_nome>[A-Za-z_][\w.-]*)\s*\})
  | (?P<numero>\d+(?:\.\d+)?|\.\d+)
  | (?P<texto>'(?:[^']*)'|"(?:[^"]*)")
  | (?P<nome>[A-Za-z_][\w-]*(?::[A-Za-z_][\w-]*)?)
  | (?P<op>!=|<=|>=|[-+*=<>(),/.])
    """,
    re.VERBOSE,
)


def _tokens(texto: str) -> list[tuple[str, str, int]]:
    saida = []
    pos = 0
    while pos < len(texto):
        m = _RE_TOKEN.match(texto, pos)
        if not m:
            raise ErroXPath(f"caractere inesperado em {pos}: {texto[pos]!r}", pos)
        pos = m.end()
        tipo = m.lastgroup
        if tipo == "espaco":
            continue
        if tipo == "var":
            saida.append(("var", m.group("var_nome"), m.start()))
        elif tipo == "var_nome":  # pragma: no cover - grupo interno nunca é o último
            continue
        else:
            saida.append((tipo, m.group(tipo), m.start()))
    return saida


# ----------------------------------------------------------------------------------------------- funções
def _texto_proprio(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _texto_ou_vazio(x: str) -> str:
    return x if x.startswith("'") else f"Texto(SeNulo({x}, ''))"


def _f_selected(a):
    return f"Contem(Split(Texto(SeNulo({a[0]}, '')), ' '), {a[1]})"


def _f_count_selected(a):
    return f"Se(Texto(SeNulo({a[0]}, '')) == '', 0, Contagem(Split(Texto({a[0]}), ' ')))"


def _f_substr(a):
    if len(a) == 2:
        return f"Mid({a[0]}, {a[1]})"
    return f"Mid({a[0]}, {a[1]}, ({a[2]}) - ({a[1]}))"


def _f_boolean_from_string(a):
    return f"(Texto({a[0]}) == 'true' || Texto({a[0]}) == '1')"


def _f_today(a):
    return f"Floor(AgoraUTC() / {MS_DIA}) * {MS_DIA}"


def _f_pulldata(a):
    # pulldata('lista', 'coluna', 'coluna_chave', valor): só a busca pela coluna `name` é direta (dicionário
    # `$_lista_<nome>` indexado por name). Outra coluna-chave fica `parcial` (tratado em _chamar).
    lista = a[0].strip("'")
    return f"Obter(Obter($_lista_{lista}, Texto({a[3]})), {a[1]})"


# nome XLSForm -> (estado, aridade mínima, aridade máxima|None, tradutor, nota)
TABELA_XLSFORM: dict[str, tuple[str, int, int | None, object, str]] = {
    "if": (FEITO, 3, 3, lambda a: f"Se({a[0]}, {a[1]}, {a[2]})", "Se"),
    "selected": (FEITO, 2, 2, _f_selected, "Contem(Split(...)) sobre a lista separada por espaço"),
    "selected-at": (FEITO, 2, 2, lambda a: f"Obter(Split(Texto({a[0]}), ' '), {a[1]})", "Obter(Split(...))"),
    "count-selected": (FEITO, 1, 1, _f_count_selected, "Contagem(Split(...)); vazio = 0"),
    "count": (FEITO, 1, 1, lambda a: f"Contagem({a[0]})", "Contagem sobre a lista da repetição"),
    "sum": (FEITO, 1, 1, lambda a: f"Soma({a[0]})", "Soma sobre ${rep}/coluna"),
    "max": (PARCIAL, 1, None, lambda a: f"Maximo({', '.join(a)})", "Maximo de escalares; max(${rep}/c) fica fora"),
    "min": (PARCIAL, 1, None, lambda a: f"Minimo({', '.join(a)})", "Minimo de escalares; min(${rep}/c) fica fora"),
    "today": (FEITO, 0, 0, _f_today, "AgoraUTC truncado ao dia (ms UTC)"),
    "now": (FEITO, 0, 0, lambda a: "AgoraUTC()", "AgoraUTC"),
    "string-length": (FEITO, 1, 1, lambda a: f"Contagem(Texto({a[0]}))", "Contagem de texto"),
    "round": (FEITO, 1, 2, lambda a: f"Arredondar({', '.join(a)})", "Arredondar"),
    "int": (FEITO, 1, 1, lambda a: f"Floor({a[0]})", "Floor"),
    "number": (FEITO, 1, 1, lambda a: f"Numero({a[0]})", "Numero"),
    "string": (FEITO, 1, 1, lambda a: f"Texto({a[0]})", "Texto"),
    "concat": (FEITO, 1, None, lambda a: f"Concatenar({', '.join(_texto_ou_vazio(x) for x in a)})",
               "Concatenar com Texto; nulo vira vazio"),
    "coalesce": (FEITO, 2, 2, lambda a: f"SeNulo({a[0]}, {a[1]})", "SeNulo"),
    "substr": (FEITO, 2, 3, _f_substr, "Mid (fim exclusivo vira comprimento)"),
    "contains": (FEITO, 2, 2, lambda a: f"Find({a[1]}, {a[0]}) >= 0", "Find >= 0"),
    "starts-with": (FEITO, 2, 2, lambda a: f"Left(Texto({a[0]}), Contagem(Texto({a[1]}))) == Texto({a[1]})", "Left"),
    "ends-with": (FEITO, 2, 2, lambda a: f"Right(Texto({a[0]}), Contagem(Texto({a[1]}))) == Texto({a[1]})", "Right"),
    "upper-case": (FEITO, 1, 1, lambda a: f"Maiuscula({a[0]})", "Maiuscula"),
    "lower-case": (FEITO, 1, 1, lambda a: f"Minuscula({a[0]})", "Minuscula"),
    "normalize-space": (FEITO, 1, 1, lambda a: f"Trim({a[0]})", "Trim (só as pontas)"),
    "abs": (FEITO, 1, 1, lambda a: f"Absoluto({a[0]})", "Absoluto"),
    "pow": (FEITO, 2, 2, lambda a: f"Potencia({a[0]}, {a[1]})", "Potencia"),
    "boolean-from-string": (FEITO, 1, 1, _f_boolean_from_string, "== 'true' ou '1'"),
    "not": (FEITO, 1, 1, lambda a: f"!({a[0]})", "operador !"),
    "true": (FEITO, 0, 0, lambda a: "verdadeiro", "verdadeiro"),
    "false": (FEITO, 0, 0, lambda a: "falso", "falso"),
    "pulldata": (PARCIAL, 4, 4, _f_pulldata, "só busca pela coluna name da lista embutida"),
    "regex": (FORA, 2, 2, None, "sem regex na linguagem própria (o Arcade também não tem; ReDoS no servidor)"),
    "date": (FORA, 1, 1, None, "conversão de texto em data não é determinística entre os dois motores"),
    "format-date": (FORA, 2, 2, None, "use TextoData no documento do L5-03"),
    "format-date-time": (FORA, 2, 2, None, "use TextoData no documento do L5-03"),
    "decimal-date-time": (FORA, 1, 1, None, "sem tipo data na linguagem"),
    "uuid": (FORA, 0, 1, None, "não determinístico; o servidor gera o globalid"),
    "random": (FORA, 0, 0, None, "não determinístico"),
    "position": (FORA, 0, 1, None, "índice da repetição não é exposto"),
    "indexed-repeat": (FORA, 3, None, None, "acesso indexado a repetição não é exposto"),
    "once": (FORA, 1, 1, None, "semântica de preenchimento único fica com o motor de formulário"),
    "jr:choice-name": (FORA, 2, 2, None, "rótulo de escolha depende do idioma"),
    "version": (FORA, 0, 0, None, "versão do formulário vem do metadado"),
}

_OPERADORES_BIN = {
    "or": ("||", 1), "and": ("&&", 2),
    "=": ("==", 3), "!=": ("!=", 3),
    "<": ("<", 4), "<=": ("<=", 4), ">": (">", 4), ">=": (">=", 4),
    "+": ("+", 5), "-": ("-", 5),
    "*": ("*", 6), "div": ("/", 6), "mod": ("%", 6),
}


class _Analisador:
    def __init__(self, texto: str):
        self.texto = texto
        self.tokens = _tokens(texto)
        self.i = 0
        self.avisos: list[Aviso] = []
        self.fora = False

    # utilidades
    def _olhar(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None, len(self.texto))

    def _comer(self, tipo=None, valor=None):
        t = self._olhar()
        if t[0] is None or (tipo and t[0] != tipo) or (valor is not None and t[1] != valor):
            raise ErroXPath(f"esperava {valor or tipo!r} em {t[2]}", t[2])
        self.i += 1
        return t

    # gramática (precedência crescente)
    def expressao(self, nivel: int = 1) -> str:
        if nivel > 6:
            return self.unario()
        esquerda = self.expressao(nivel + 1)
        while True:
            t = self._olhar()
            chave = t[1] if t[0] in ("op", "nome") else None
            op = _OPERADORES_BIN.get(chave) if chave is not None else None
            if not op or op[1] != nivel:
                return esquerda
            self.i += 1
            direita = self.expressao(nivel + 1)
            esquerda = f"{esquerda} {op[0]} {direita}"

    def unario(self) -> str:
        t = self._olhar()
        if t[0] == "op" and t[1] == "-":
            self.i += 1
            return f"-{self.unario()}"
        return self.primario()

    def primario(self) -> str:
        tipo, valor, pos = self._olhar()
        if tipo is None:
            raise ErroXPath("expressão terminou cedo demais", pos)
        self.i += 1
        if tipo == "numero":
            return valor
        if tipo == "texto":
            return _texto_proprio(valor[1:-1])
        if tipo == "var":
            return self._caminho("$" + valor.replace("-", "_").replace(".", "_"))
        if tipo == "op" and valor == ".":
            return "$_valor"
        if tipo == "op" and valor == "(":
            interno = self.expressao()
            self._comer("op", ")")
            return f"({interno})"
        if tipo == "nome":
            if valor in ("true", "false", "not") or self._olhar()[1] == "(":
                return self._chamar(valor, pos)
            # nome solto = coluna da linha de escolha (choice_filter: `estado=${estado}`)
            return f"Obter($_linha, {_texto_proprio(valor)})"
        raise ErroXPath(f"símbolo inesperado {valor!r} em {pos}", pos)

    def _caminho(self, base: str) -> str:
        # ${rep}/coluna -> $rep__coluna (lista de valores da coluna da repetição)
        t = self._olhar()
        if t[0] == "op" and t[1] == "/":
            proximo = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else (None, None, 0)
            if proximo[0] == "nome":
                self.i += 2
                return f"{base}__{proximo[1].replace('-', '_')}"
        return base

    def _chamar(self, nome: str, pos: int) -> str:
        args: list[str] = []
        self._comer("op", "(")
        if self._olhar()[1] != ")":
            args.append(self.expressao())
            while self._olhar()[1] == ",":
                self.i += 1
                args.append(self.expressao())
        fim = self._comer("op", ")")
        trecho = self.texto[pos: fim[2] + 1]
        entrada = TABELA_XLSFORM.get(nome)
        if entrada is None:
            self.avisos.append(Aviso(nome, FORA, trecho, "função XLSForm sem equivalente na tabela"))
            self.fora = True
            return "nulo"
        estado, minimo, maximo, tradutor, nota = entrada
        if len(args) < minimo or (maximo is not None and len(args) > maximo):
            raise ErroXPath(f"{nome}: aridade {len(args)} fora de {minimo}-{maximo}", pos)
        if estado == FORA:
            self.avisos.append(Aviso(nome, FORA, trecho, nota))
            self.fora = True
            return "nulo"
        if estado == PARCIAL:
            if nome in ("max", "min"):
                if len(args) == 1:  # max(${rep}/coluna): a linguagem não tem máximo de lista
                    self.avisos.append(Aviso(nome, FORA, trecho, "máximo/mínimo de coluna de repetição"))
                    self.fora = True
                    return "nulo"
                return tradutor(args)
            if nome == "pulldata" and args[2].strip("'") != "name":
                self.avisos.append(Aviso(nome, FORA, trecho, "pulldata só pela coluna name"))
                self.fora = True
                return "nulo"
            self.avisos.append(Aviso(nome, PARCIAL, trecho, nota))
        return tradutor(args)


def traduzir(texto: str) -> Traducao:
    """Texto XPath do XLSForm -> Traducao(texto na linguagem própria | None, avisos). Erro de sintaxe do XPath
    é ErroXPath (a linha do XLSForm está errada; quem importa transforma em 422 com a posição)."""
    texto = (texto or "").strip()
    if not texto:
        return Traducao("")
    a = _Analisador(texto)
    saida = a.expressao()
    if a.i < len(a.tokens):
        t = a.tokens[a.i]
        raise ErroXPath(f"sobrou {t[1]!r} em {t[2]}", t[2])
    return Traducao(None if a.fora else saida, a.avisos)


def tabela_equivalencia() -> list[dict]:
    """Tabela publicada em GET /api/formularios/{id}/equivalencia (paridade por função, C6)."""
    return [
        {"funcao": nome, "estado": estado, "equivalente": nota}
        for nome, (estado, _mi, _ma, _tr, nota) in TABELA_XLSFORM.items()
    ] + [
        {"funcao": op, "estado": FEITO, "equivalente": f"operador {alvo}"}
        for op, (alvo, _n) in _OPERADORES_BIN.items()
    ]
