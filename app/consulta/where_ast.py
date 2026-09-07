"""Parser próprio de um subconjunto restrito de `where` (o que a Esri chama de standardized queries)
e futuro alvo do CQL2-JSON canônico (L2_CONCEITO.md seção C7: "um único gerador de SQL parametrizado
é o ponto de auditoria de injeção"). Este módulo é essa peça, isolada e reutilizável por qualquer
serviço (FeatureServer, OGC API Features, painel) que precise transformar filtro digitado por
cliente em predicado SQL seguro — nasceu no item L2-04-b (sem tabela de mapa, sem integração de
rota) e o item L2-04-c (operação `query` do FeatureServer) acrescenta BETWEEN, NOT, os literais de
data/hora e as duas funções de texto do dialeto Esri ("standardized queries"), mantendo as mesmas
duas etapas e a mesma garantia: nenhum caminho monta SQL por concatenação de texto do cliente.

Gramática (EBNF), operadores fixos — nada além disto é aceito:

    expr        := and_termo (OR and_termo)*
    and_termo   := nao_termo (AND nao_termo)*
    nao_termo   := [NOT] primario
    primario    := "(" expr ")" | comparacao
    comparacao  := operando ( is_nulo | in_lista | between | op_valor )
    operando    := CAMPO | UPPER "(" CAMPO ")" | LOWER "(" CAMPO ")"
    is_nulo     := IS [NOT] NULL
    in_lista    := IN "(" valor ("," valor)* ")"
    between     := BETWEEN valor AND valor
    op_valor    := ( "=" | "!=" | "<>" | "<" | "<=" | ">" | ">=" | LIKE ) valor
    valor       := NUMERO | STRING | data_lit | CURRENT_DATE | CURRENT_TIMESTAMP
    data_lit    := DATE STRING | TIMESTAMP STRING
    CAMPO       := identificador ASCII (letra/"_" seguido de letras/dígitos/"_")

`DATE 'YYYY-MM-DD'` e `TIMESTAMP 'YYYY-MM-DD HH:MM:SS'` (ISO 8601, sem fuso — dialeto Esri) viram
objeto `datetime.date`/`datetime.datetime` Python, que o psycopg2 adapta como parâmetro tipado —
nunca como texto colado no SQL. `CURRENT_DATE`/`CURRENT_TIMESTAMP` são palavras-chave fixas do
analisador (não texto do usuário) e por isso podem virar SQL literal com segurança. `UPPER(campo)`/
`LOWER(campo)` só envolvem um CAMPO da lista branca — nunca uma expressão arbitrária.

Duas etapas, nunca uma só:

1. `analisar(texto)` — só sintaxe. Produz uma AST tipada (`Comparacao`/`E`/`Ou`). Não sabe nada sobre
   colunas de banco; um texto sintaticamente válido com campo inexistente passa por aqui.
2. `compilar(no, colunas)` — só semântica de segurança. `colunas` é a lista BRANCA passada pelo
   CHAMADOR (nunca descoberta em tempo de execução, nunca "todas as colunas da tabela"): um `dict`
   nome-no-filtro → expressão SQL de confiança do desenvolvedor (ex.: `{"cidade": "c.nome_cidade"}`,
   podendo apontar para outra tabela/alias/cast), ou um `set`/`list` de nomes que viram identificador
   entre aspas duplas depois de validados pelo mesmo regex de identificador. Todo valor literal do
   usuário vira parâmetro `%s`; NUNCA é escrito no texto do SQL. Sem `eval`/`exec`, sem `%`/`.format`
   aplicado a texto do usuário, sem string do cliente concatenada em SQL.

`compilar_where(texto, colunas)` faz as duas etapas de uma vez — é o que um endpoint deve chamar.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Union

# ---------------------------------------------------------------- limites (negação-de-serviço)
MAX_TEXTO = 4000  # caracteres do filtro bruto
MAX_TOKENS = 400  # tokens após tokenizar (largura: número de termos)
MAX_PROFUNDIDADE = 20  # aninhamento de parênteses

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PALAVRAS_CHAVE = {
    "and", "or", "not", "in", "like", "is", "null", "between",
    "date", "timestamp", "current_date", "current_timestamp", "upper", "lower",
}
_OPERADORES = ["<=", ">=", "!=", "<>", "=", "<", ">"]  # ordem importa: prefixos de 2 chars primeiro
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")


class _CurrentKeyword:
    """Marcador de valor: `CURRENT_DATE`/`CURRENT_TIMESTAMP` não são texto do usuário — são
    palavras-chave reconhecidas pelo tokenizador — por isso podem virar SQL literal fixo em vez de
    parâmetro, sem violar a regra de nunca concatenar texto do cliente."""

    def __init__(self, sql: str):
        self.sql = sql

    def __eq__(self, outro):
        return isinstance(outro, _CurrentKeyword) and self.sql == outro.sql

    def __repr__(self):
        return f"_CurrentKeyword({self.sql!r})"


CURRENT_DATE = _CurrentKeyword("CURRENT_DATE")
CURRENT_TIMESTAMP = _CurrentKeyword("CURRENT_TIMESTAMP")


class ErroWhere(Exception):
    """`codigo` curto (a rota converte em 400/422 do contrato de erro da API), `mensagem` em
    português, `detalhe` opcional (posição, campo, token obtido) — nunca expõe o SQL final."""

    def __init__(self, codigo: str, mensagem: str, detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# =================================================================== 1. tokenizador
@dataclass
class Token:
    tipo: str  # ident | numero | string | ( | ) | , | op | AND | OR | NOT | IN | LIKE | IS | NULL
    valor: Any = None


def _tokenizar(texto: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            tokens.append(Token("("))
            i += 1
            continue
        if c == ")":
            tokens.append(Token(")"))
            i += 1
            continue
        if c == ",":
            tokens.append(Token(","))
            i += 1
            continue
        if c == "'":
            # string entre aspas simples; '' dentro da string é uma aspa literal (padrão SQL)
            j = i + 1
            partes: list[str] = []
            fechou = False
            while j < n:
                k = texto.find("'", j)
                if k < 0:
                    break
                partes.append(texto[j:k])
                if k + 1 < n and texto[k + 1] == "'":
                    partes.append("'")
                    j = k + 2
                    continue
                j = k + 1
                fechou = True
                break
            if not fechou:
                raise ErroWhere("sintaxe_invalida", "string sem aspa de fechamento", {"posicao": i})
            tokens.append(Token("string", "".join(partes)))
            i = j
            continue
        op_casado = next((op for op in _OPERADORES if texto.startswith(op, i)), None)
        if op_casado:
            tokens.append(Token("op", "!=" if op_casado == "<>" else op_casado))
            i += len(op_casado)
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and texto[i + 1].isdigit()):
            j = i + 1 if c == "-" else i
            while j < n and texto[j].isdigit():
                j += 1
            eh_float = False
            if j < n and texto[j] == "." and j + 1 < n and texto[j + 1].isdigit():
                eh_float = True
                j += 1
                while j < n and texto[j].isdigit():
                    j += 1
            bruto = texto[i:j]
            tokens.append(Token("numero", float(bruto) if eh_float else int(bruto)))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (texto[j].isalnum() or texto[j] == "_"):
                j += 1
            palavra = texto[i:j]
            baixa = palavra.lower()
            if baixa in _PALAVRAS_CHAVE:
                tokens.append(Token(baixa.upper()))
            else:
                tokens.append(Token("ident", palavra))
            i = j
            continue
        # qualquer outro caractere (`;`, `-` solto, `--`, `/*`, `~`, `#`, etc.) é recusado, nunca
        # ignorado silenciosamente — é o que fecha a porta de comentário/empilhamento de instrução
        raise ErroWhere("caractere_invalido", f"caractere não reconhecido: {c!r}", {"posicao": i, "caractere": c})
    return tokens


# =================================================================== 2. AST tipada
@dataclass
class Comparacao:
    campo: str
    operador: str  # "=" "!=" "<" "<=" ">" ">=" "LIKE" "IN" "BETWEEN" "IS NULL" "IS NOT NULL"
    valor: Any = None
    valores: list | None = None  # para IN (lista) e BETWEEN ([inicio, fim])
    funcao: str | None = None  # None | "UPPER" | "LOWER" — envolve o CAMPO (dialeto Esri), não o valor


@dataclass
class E:
    esquerda: "No"
    direita: "No"


@dataclass
class Ou:
    esquerda: "No"
    direita: "No"


@dataclass
class Nao:
    """`NOT <primario>` — negação prefixa de uma comparação ou de uma expressão entre parênteses."""

    no: "No"


No = Union[Comparacao, E, Ou, Nao]


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.i = 0

    def _olha(self) -> Token | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _espera(self, tipo: str) -> Token:
        tok = self._olha()
        if tok is None or tok.tipo != tipo:
            raise ErroWhere(
                "sintaxe_invalida",
                f"esperava '{tipo}'" + (f", obtive '{tok.tipo}'" if tok else ", a expressão terminou antes"),
                {"posicao": self.i, "esperado": tipo, "obtido": tok.tipo if tok else None},
            )
        self.i += 1
        return tok

    def analisar_tudo(self) -> No:
        no = self.expr(0)
        sobra = self._olha()
        if sobra is not None:
            raise ErroWhere(
                "sintaxe_invalida", "texto após o fim da expressão", {"posicao": self.i, "obtido": sobra.tipo}
            )
        return no

    def expr(self, profundidade: int) -> No:
        esquerda = self.e_termo(profundidade)
        while (tok := self._olha()) is not None and tok.tipo == "OR":
            self.i += 1
            direita = self.e_termo(profundidade)
            esquerda = Ou(esquerda, direita)
        return esquerda

    def e_termo(self, profundidade: int) -> No:
        esquerda = self.nao_termo(profundidade)
        while (tok := self._olha()) is not None and tok.tipo == "AND":
            self.i += 1
            direita = self.nao_termo(profundidade)
            esquerda = E(esquerda, direita)
        return esquerda

    def nao_termo(self, profundidade: int) -> No:
        tok = self._olha()
        if tok is not None and tok.tipo == "NOT":
            self.i += 1
            return Nao(self.primario(profundidade))
        return self.primario(profundidade)

    def primario(self, profundidade: int) -> No:
        tok = self._olha()
        if tok is None:
            raise ErroWhere("sintaxe_invalida", "expressão incompleta", {"posicao": self.i})
        if tok.tipo == "(":
            if profundidade + 1 > MAX_PROFUNDIDADE:
                raise ErroWhere(
                    "expressao_complexa", f"aninhamento de parênteses acima de {MAX_PROFUNDIDADE}", {"posicao": self.i}
                )
            self.i += 1
            no = self.expr(profundidade + 1)
            self._espera(")")
            return no
        return self.comparacao()

    def _operando(self) -> tuple[str, str | None]:
        """CAMPO | UPPER "(" CAMPO ")" | LOWER "(" CAMPO ")" — devolve (campo, funcao)."""
        tok = self._olha()
        if tok is not None and tok.tipo in ("UPPER", "LOWER"):
            funcao = tok.tipo
            self.i += 1
            self._espera("(")
            campo_tok = self._espera("ident")
            self._espera(")")
            return campo_tok.valor, funcao
        campo_tok = self._espera("ident")
        return campo_tok.valor, None

    def comparacao(self) -> Comparacao:
        campo, funcao = self._operando()
        tok = self._olha()
        if tok is None:
            raise ErroWhere("sintaxe_invalida", f"operador esperado após '{campo}'", {"campo": campo})
        if tok.tipo == "IS":
            self.i += 1
            negado = False
            prox = self._olha()
            if prox is not None and prox.tipo == "NOT":
                negado = True
                self.i += 1
            self._espera("NULL")
            return Comparacao(campo, "IS NOT NULL" if negado else "IS NULL", funcao=funcao)
        if tok.tipo == "IN":
            self.i += 1
            self._espera("(")
            valores = [self.valor()]
            while (t2 := self._olha()) is not None and t2.tipo == ",":
                self.i += 1
                valores.append(self.valor())
            self._espera(")")
            return Comparacao(campo, "IN", valores=valores, funcao=funcao)
        if tok.tipo == "BETWEEN":
            self.i += 1
            inicio = self.valor()
            self._espera("AND")
            fim = self.valor()
            return Comparacao(campo, "BETWEEN", valores=[inicio, fim], funcao=funcao)
        if tok.tipo == "LIKE":
            self.i += 1
            return Comparacao(campo, "LIKE", valor=self.valor(), funcao=funcao)
        if tok.tipo == "op":
            self.i += 1
            return Comparacao(campo, tok.valor, valor=self.valor(), funcao=funcao)
        raise ErroWhere(
            "sintaxe_invalida",
            f"operador desconhecido após '{campo}': '{tok.tipo}'",
            {"campo": campo, "obtido": tok.tipo},
        )

    def valor(self):
        tok = self._olha()
        if tok is None:
            raise ErroWhere("sintaxe_invalida", "valor esperado", {"posicao": self.i})
        if tok.tipo in ("numero", "string"):
            self.i += 1
            return tok.valor
        if tok.tipo == "CURRENT_DATE":
            self.i += 1
            return CURRENT_DATE
        if tok.tipo == "CURRENT_TIMESTAMP":
            self.i += 1
            return CURRENT_TIMESTAMP
        if tok.tipo in ("DATE", "TIMESTAMP"):
            literal_tipo = tok.tipo
            self.i += 1
            texto_tok = self._espera("string")
            return self._literal_data(literal_tipo, texto_tok.valor)
        raise ErroWhere(
            "sintaxe_invalida",
            "valor esperado (número, 'string', DATE/TIMESTAMP 'iso' ou CURRENT_DATE/CURRENT_TIMESTAMP)",
            {"posicao": self.i, "obtido": tok.tipo},
        )

    def _literal_data(self, literal_tipo: str, texto: str):
        """DATE/TIMESTAMP seguido de STRING vira `date`/`datetime` Python — nunca texto solto no
        SQL; formato fixo ISO 8601 (dialeto Esri), qualquer outro formato é sintaxe inválida."""
        if literal_tipo == "DATE":
            if not _DATE_RE.match(texto):
                raise ErroWhere("data_invalida", f"DATE espera 'YYYY-MM-DD', obtive {texto!r}", {"valor": texto})
            try:
                return datetime.strptime(texto, "%Y-%m-%d").date()
            except ValueError as e:
                raise ErroWhere("data_invalida", f"data inválida: {texto!r}", {"valor": texto}) from e
        if not _TIMESTAMP_RE.match(texto):
            raise ErroWhere(
                "data_invalida", f"TIMESTAMP espera 'YYYY-MM-DD HH:MM[:SS]', obtive {texto!r}", {"valor": texto}
            )
        normalizado = texto.replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(normalizado, fmt)
            except ValueError:
                continue
        raise ErroWhere("data_invalida", f"timestamp inválido: {texto!r}", {"valor": texto})


def analisar(texto: str) -> No:
    """texto → AST tipada. Levanta `ErroWhere` em qualquer sintaxe fora da gramática — inclusive
    ponto-e-vírgula, comentário SQL (`--`, `/*`), aspa não fechada e campo escrito como número."""
    texto = (texto or "").strip()
    if not texto:
        raise ErroWhere("expressao_vazia", "expressão de filtro vazia")
    if len(texto) > MAX_TEXTO:
        raise ErroWhere("expressao_complexa", f"filtro maior que {MAX_TEXTO} caracteres")
    tokens = _tokenizar(texto)
    if len(tokens) > MAX_TOKENS:
        raise ErroWhere("expressao_complexa", f"filtro com mais de {MAX_TOKENS} tokens")
    return _Parser(tokens).analisar_tudo()


# =================================================================== 3. compilação em SQL parametrizado
@dataclass
class ConsultaSQL:
    sql: str
    params: list = field(default_factory=list)


def _normalizar_colunas(colunas) -> dict[str, str]:
    """`colunas` é a lista branca do CHAMADOR: um dict nome→expressão SQL de confiança, ou um
    set/list de nomes (viram identificador entre aspas duplas, só depois de validados por regex —
    nunca aceitos como texto livre)."""
    if isinstance(colunas, dict):
        return colunas
    mapa: dict[str, str] = {}
    for nome in colunas:
        if not IDENT_RE.match(nome):
            raise ErroWhere("coluna_invalida", f"nome de coluna fora do padrão de identificador: {nome!r}")
        mapa[nome] = f'"{nome}"'
    return mapa


def compilar(no: No, colunas) -> ConsultaSQL:
    """AST → `ConsultaSQL(sql, params)`. `campo` que não estiver em `colunas` (a lista branca do
    chamador) é recusado aqui, nunca antes — a sintaxe pode ser válida com um campo inexistente."""
    colunas_ok = _normalizar_colunas(colunas)
    params: list = []

    def _valor_sql(v) -> str:
        """`CURRENT_DATE`/`CURRENT_TIMESTAMP` (palavra-chave do analisador) viram literal SQL fixo;
        qualquer outro valor (número, string, `date`/`datetime` de DATE/TIMESTAMP) é parâmetro."""
        if isinstance(v, _CurrentKeyword):
            return v.sql
        params.append(v)
        return "%s"

    def visitar(nodo: No) -> str:
        if isinstance(nodo, Ou):
            return f"({visitar(nodo.esquerda)} OR {visitar(nodo.direita)})"
        if isinstance(nodo, E):
            return f"({visitar(nodo.esquerda)} AND {visitar(nodo.direita)})"
        if isinstance(nodo, Nao):
            return f"NOT ({visitar(nodo.no)})"
        if isinstance(nodo, Comparacao):
            if nodo.campo not in colunas_ok:
                raise ErroWhere(
                    "campo_nao_permitido", f"campo não está na lista branca: {nodo.campo}", {"campo": nodo.campo}
                )
            col = colunas_ok[nodo.campo]
            if nodo.funcao in ("UPPER", "LOWER"):
                col = f"{nodo.funcao}({col})"
            if nodo.operador in ("IS NULL", "IS NOT NULL"):
                return f"{col} {nodo.operador}"
            if nodo.operador == "IN":
                marcadores = ", ".join(_valor_sql(v) for v in nodo.valores)
                return f"{col} IN ({marcadores})"
            if nodo.operador == "BETWEEN":
                ini_sql = _valor_sql(nodo.valores[0])
                fim_sql = _valor_sql(nodo.valores[1])
                return f"{col} BETWEEN {ini_sql} AND {fim_sql}"
            val_sql = _valor_sql(nodo.valor)
            return f"{col} {nodo.operador} {val_sql}"
        raise ErroWhere("no_desconhecido", "nó de AST fora dos tipos esperados")  # pragma: no cover

    sql = visitar(no)
    return ConsultaSQL(sql, params)


def compilar_where(texto: str, colunas) -> ConsultaSQL:
    """Atalho de um passo só: `analisar(texto)` + `compilar(..., colunas)` — é o que um endpoint
    deve chamar; nunca montar `WHERE` por conta própria em outro lugar do serviço."""
    return compilar(analisar(texto), colunas)
