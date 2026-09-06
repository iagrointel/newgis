"""Núcleo da linguagem de expressão própria (item L2-10-c-linguagem-expressao, equivalente ao Arcade
da Esri para os perfis popup/rótulo/cálculo/restrição/validação/indicador — a integração com esses
perfis é de itens futuros; aqui só o analisador, a AST e o avaliador). Gramática publicada em
`docs/EXPRESSAO.md` — este módulo TEM de ser a implementação exata daquele documento; a tabela de
funções (`TABELA_FUNCOES`) é a fonte única que o teste `test_expressao_doc_sincronizada.py` confere
contra o texto do documento.

Mesmo padrão de segurança do `app/consulta/where_ast.py`: duas etapas nunca uma só.

1. `analisar(texto)` — só sintaxe. Tokeniza e monta uma AST tipada (dataclasses). Não sabe nada
   sobre o `contexto` de avaliação.
2. `avaliar(no, contexto, ...)` — só semântica. `contexto` é o dicionário BRANCO de campos
   disponíveis passado pelo CHAMADOR (nunca descoberto em tempo de execução, nunca `getattr` em
   objeto do chamador, nunca `vars()`/`__dict__`): `$campo` que não estiver em `contexto` é erro de
   permissão (`campo_nao_permitido`), nunca `None` silencioso. Sem `eval`/`exec`/`compile`, sem
   `importlib`, sem acesso a atributo de objeto Python arbitrário — só busca em dicionário.

Limites (negação de serviço, refutação do item-pai): texto bruto, tokens, profundidade de
aninhamento (parser) e passos de avaliação (evaluator) — todos com erro nomeado, nunca uma
recursão que estoura a pilha do Python ou um laço que nunca devolve.

Tipos desta passagem: número (int/float), texto (str), booleano (bool), nulo (None). "Data" é
CONVENÇÃO sobre número: milissegundos desde a época Unix (1970-01-01T00:00:00Z), sempre UTC — a
mesma representação em Python e em JavaScript (`web/js/expressao/avaliador.js`), para os dois
avaliadores concordarem byte a byte sem depender de biblioteca de fuso horário nenhuma das duas
línguas. Lista, dicionário e geometria (pedidos na hipótese cheia do item) ficam FORA desta
passagem — não há função que os produza ou consuma aqui.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Union

# ---------------------------------------------------------------- limites (negação-de-serviço)
MAX_TEXTO = 20_000  # caracteres do texto bruto da expressão (bem acima de qualquer uso real;
# bem abaixo de "string gigante" — um literal de 10 MB nunca chega ao tokenizador)
MAX_TOKENS = 2_000  # tokens após tokenizar
MAX_PROFUNDIDADE = 60  # aninhamento de parênteses/unários/chamadas que o PARSER aceita — acima
# disso a recursão descendente estouraria a pilha do Python antes de qualquer erro "educado";
# por isso o limite é conferido a cada descida, não depois
MAX_ARGUMENTOS = 64  # argumentos por chamada de função (Concatenar/Minimo/Maximo variádicas)
MAX_PASSOS_PADRAO = 100_000  # nós avaliados (10^5, valor do portão do item-pai)
LIMITE_MS_SERVIDOR = 500  # orçamento de tempo do avaliador no servidor (o cliente usa 50 ms — é
# quem chama que passa `limite_ms`; o valor aqui é só o default do lado servidor)

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PALAVRAS_CHAVE = {"verdadeiro", "falso", "nulo"}
_OPERADORES = ["<=", ">=", "==", "!=", "&&", "||", "<", ">", "+", "-", "*", "/", "%", "^", "!"]  # ordem
# importa: prefixos de 2 caracteres antes dos de 1


class ErroExpressao(Exception):
    """`codigo` curto e estável (o que uma rota converte em 400/422), `mensagem` em português,
    `detalhe` opcional (posição/linha/coluna, nome do campo ou função, contagem) — nunca expõe
    estado interno do avaliador nem o `contexto` do chamador."""

    def __init__(self, codigo: str, mensagem: str, detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# =================================================================== 1. tokenizador
@dataclass
class Token:
    tipo: str  # numero | string | campo | ident | ( | ) | , | op | verdadeiro | falso | nulo
    valor: Any = None
    posicao: int = 0
    linha: int = 1
    coluna: int = 1


def _linha_coluna(texto: str, posicao: int) -> tuple[int, int]:
    """1-based, como qualquer editor de texto — é o que o erro de sintaxe devolve (portão do item)."""
    ate = texto[:posicao]
    linha = ate.count("\n") + 1
    coluna = posicao - (ate.rfind("\n")) if "\n" in ate else posicao + 1
    return linha, coluna


def _tokenizar(texto: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            tokens.append(Token("(", posicao=i))
            i += 1
            continue
        if c == ")":
            tokens.append(Token(")", posicao=i))
            i += 1
            continue
        if c == ",":
            tokens.append(Token(",", posicao=i))
            i += 1
            continue
        if c == "'":
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
                linha, coluna = _linha_coluna(texto, i)
                raise ErroExpressao(
                    "sintaxe_invalida", "texto sem aspa de fechamento", {"linha": linha, "coluna": coluna}
                )
            tokens.append(Token("string", "".join(partes), posicao=i))
            i = j
            continue
        if c == "$":
            j = i + 1
            if j >= n or not (texto[j].isalpha() or texto[j] == "_"):
                linha, coluna = _linha_coluna(texto, i)
                raise ErroExpressao(
                    "sintaxe_invalida", "'$' precisa ser seguido de nome de campo", {"linha": linha, "coluna": coluna}
                )
            k = j
            while k < n and (texto[k].isalnum() or texto[k] == "_"):
                k += 1
            tokens.append(Token("campo", texto[j:k], posicao=i))
            i = k
            continue
        op_casado = next((op for op in _OPERADORES if texto.startswith(op, i)), None)
        if op_casado:
            tokens.append(Token("op", op_casado, posicao=i))
            i += len(op_casado)
            continue
        if c.isdigit() or (c == "." and i + 1 < n and texto[i + 1].isdigit()):
            j = i
            while j < n and texto[j].isdigit():
                j += 1
            if j < n and texto[j] == "." and j + 1 < n and texto[j + 1].isdigit():
                j += 1
                while j < n and texto[j].isdigit():
                    j += 1
            bruto = texto[i:j]
            # todo número é float (double), como no JavaScript; a saída de `avaliar` canonicaliza inteiros
            tokens.append(Token("numero", _finito(float(bruto)), posicao=i))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (texto[j].isalnum() or texto[j] == "_"):
                j += 1
            palavra = texto[i:j]
            baixa = palavra.lower()
            if baixa in _PALAVRAS_CHAVE:
                tokens.append(Token(baixa, posicao=i))
            else:
                tokens.append(Token("ident", palavra, posicao=i))
            i = j
            continue
        linha, coluna = _linha_coluna(texto, i)
        raise ErroExpressao(
            "caractere_invalido", f"caractere não reconhecido: {c!r}", {"linha": linha, "coluna": coluna}
        )
    return tokens


# =================================================================== 2. AST tipada
@dataclass
class Literal:
    tipo_valor: str  # numero | texto | booleano | nulo
    valor: Any = None


@dataclass
class Campo:
    nome: str


@dataclass
class Unario:
    operador: str  # "-" | "!"
    operando: "No"


@dataclass
class Binario:
    operador: str  # "+" "-" "*" "/" "%" "^" "==" "!=" "<" "<=" ">" ">=" "&&" "||"
    esquerda: "No"
    direita: "No"


@dataclass
class Chamada:
    nome: str
    argumentos: list = field(default_factory=list)


No = Union[Literal, Campo, Unario, Binario, Chamada]

_PRECEDENCIA_LOGICA_OU = {"||"}
_PRECEDENCIA_LOGICA_E = {"&&"}
_PRECEDENCIA_IGUALDADE = {"==", "!="}
_PRECEDENCIA_COMPARACAO = {"<", "<=", ">", ">="}
_PRECEDENCIA_ADITIVA = {"+", "-"}
_PRECEDENCIA_MULTIPLICATIVA = {"*", "/", "%"}
_PRECEDENCIA_POTENCIA = {"^"}
_OPERADORES_UNARIOS = {"-", "!"}


class _Parser:
    def __init__(self, tokens: list[Token], texto: str):
        self.t = tokens
        self.i = 0
        self.texto = texto

    def _olha(self) -> Token | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _erro_posicao(self, posicao: int) -> dict:
        linha, coluna = _linha_coluna(self.texto, posicao)
        return {"linha": linha, "coluna": coluna}

    def _espera(self, tipo: str) -> Token:
        tok = self._olha()
        posicao = tok.posicao if tok else len(self.texto)
        if tok is None or tok.tipo != tipo:
            raise ErroExpressao(
                "sintaxe_invalida",
                f"esperava '{tipo}'" + (f", obtive '{tok.tipo}'" if tok else ", a expressão terminou antes"),
                {**self._erro_posicao(posicao), "esperado": tipo, "obtido": tok.tipo if tok else None},
            )
        self.i += 1
        return tok

    def _profundidade_ok(self, profundidade: int, posicao: int) -> None:
        if profundidade > MAX_PROFUNDIDADE:
            raise ErroExpressao(
                "profundidade_excedida",
                f"aninhamento acima de {MAX_PROFUNDIDADE}",
                {**self._erro_posicao(posicao), "limite": MAX_PROFUNDIDADE},
            )

    def analisar_tudo(self) -> No:
        no = self.ou(0)
        sobra = self._olha()
        if sobra is not None:
            raise ErroExpressao("sintaxe_invalida", "texto após o fim da expressão", self._erro_posicao(sobra.posicao))
        return no

    # precedência (do menor para o maior): || && == != < <= > >= + - * / % ^ unário chamada/primário
    def ou(self, p: int) -> No:
        self._profundidade_ok(p, self.t[self.i].posicao if self.i < len(self.t) else len(self.texto))
        esquerda = self.e(p + 1)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_LOGICA_OU:
            self.i += 1
            direita = self.e(p + 1)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def e(self, p: int) -> No:
        esquerda = self.igualdade(p)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_LOGICA_E:
            self.i += 1
            direita = self.igualdade(p)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def igualdade(self, p: int) -> No:
        esquerda = self.comparacao(p)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_IGUALDADE:
            self.i += 1
            direita = self.comparacao(p)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def comparacao(self, p: int) -> No:
        esquerda = self.aditiva(p)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_COMPARACAO:
            self.i += 1
            direita = self.aditiva(p)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def aditiva(self, p: int) -> No:
        esquerda = self.multiplicativa(p)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_ADITIVA:
            self.i += 1
            direita = self.multiplicativa(p)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def multiplicativa(self, p: int) -> No:
        esquerda = self.potencia(p)
        while (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_MULTIPLICATIVA:
            self.i += 1
            direita = self.potencia(p)
            esquerda = Binario(tok.valor, esquerda, direita)
        return esquerda

    def potencia(self, p: int) -> No:
        esquerda = self.unario(p)
        if (tok := self._olha()) is not None and tok.tipo == "op" and tok.valor in _PRECEDENCIA_POTENCIA:
            self.i += 1
            self._profundidade_ok(p + 1, tok.posicao)
            direita = self.potencia(p + 1)  # associatividade à direita
            return Binario("^", esquerda, direita)
        return esquerda

    def unario(self, p: int) -> No:
        tok = self._olha()
        if tok is not None and tok.tipo == "op" and tok.valor in _OPERADORES_UNARIOS:
            self._profundidade_ok(p + 1, tok.posicao)
            self.i += 1
            operando = self.unario(p + 1)
            return Unario(tok.valor, operando)
        return self.primario(p)

    def primario(self, p: int) -> No:
        tok = self._olha()
        if tok is None:
            raise ErroExpressao("sintaxe_invalida", "expressão incompleta", self._erro_posicao(len(self.texto)))
        if tok.tipo == "numero":
            self.i += 1
            return Literal("numero", tok.valor)
        if tok.tipo == "string":
            self.i += 1
            return Literal("texto", tok.valor)
        if tok.tipo == "verdadeiro":
            self.i += 1
            return Literal("booleano", True)
        if tok.tipo == "falso":
            self.i += 1
            return Literal("booleano", False)
        if tok.tipo == "nulo":
            self.i += 1
            return Literal("nulo", None)
        if tok.tipo == "campo":
            self.i += 1
            return Campo(tok.valor)
        if tok.tipo == "(":
            self._profundidade_ok(p + 1, tok.posicao)
            self.i += 1
            no = self.ou(p + 1)
            self._espera(")")
            return no
        if tok.tipo == "ident":
            nome = tok.valor
            self.i += 1
            self._espera("(")
            self._profundidade_ok(p + 1, tok.posicao)
            argumentos: list[No] = []
            if (prox := self._olha()) is not None and prox.tipo != ")":
                argumentos.append(self.ou(p + 1))
                while (t2 := self._olha()) is not None and t2.tipo == ",":
                    self.i += 1
                    if len(argumentos) >= MAX_ARGUMENTOS:
                        raise ErroExpressao(
                            "expressao_grande",
                            f"mais de {MAX_ARGUMENTOS} argumentos em '{nome}'",
                            {**self._erro_posicao(t2.posicao), "funcao": nome},
                        )
                    argumentos.append(self.ou(p + 1))
            self._espera(")")
            return Chamada(nome, argumentos)
        raise ErroExpressao("sintaxe_invalida", f"token inesperado: '{tok.tipo}'", self._erro_posicao(tok.posicao))


def _profundidade_da_arvore(no: No) -> int:
    """Profundidade REAL da AST, medida com pilha explícita (nunca recursão Python) — porque uma
    cadeia longa do MESMO operador na mesma precedência ("1+1+1+...+1") é montada por um `while` do
    parser (não recursa a cada termo, então o contador de profundidade do parser nunca dispara) mas
    ainda produz uma árvore tão funda quanto o número de termos: sem esta conferência, o AVALIADOR
    (que É recursivo em `v()`) estouraria a pilha do Python nessa cadeia — o mesmo bug de classe que
    a refutação do item-pai pede para fechar. Custo O(nós), pilha própria limitada por MAX_TOKENS."""
    pilha: list[tuple[No, int]] = [(no, 1)]
    maior = 0
    while pilha:
        atual, profundidade = pilha.pop()
        if profundidade > maior:
            maior = profundidade
        if profundidade > MAX_PROFUNDIDADE * 4:  # corta cedo — não precisa visitar o resto para saber que já estourou
            return profundidade
        if isinstance(atual, Unario):
            pilha.append((atual.operando, profundidade + 1))
        elif isinstance(atual, Binario):
            pilha.append((atual.esquerda, profundidade + 1))
            pilha.append((atual.direita, profundidade + 1))
        elif isinstance(atual, Chamada):
            for a in atual.argumentos:
                pilha.append((a, profundidade + 1))
    return maior


def analisar(texto: str) -> No:
    """texto → AST tipada. Levanta `ErroExpressao` (com linha/coluna quando aplicável, portão do
    item) em qualquer sintaxe fora da gramática de `docs/EXPRESSAO.md` — inclusive texto vazio,
    texto/tokens acima do limite e aninhamento acima do limite. Duas defesas de profundidade, não
    uma: o PARSER conta a descida a cada parêntese/unário/chamada (nunca deixa a própria pilha do
    Python estourar enquanto analisa) e, depois de montada, a árvore inteira é medida de novo com
    pilha explícita (`_profundidade_da_arvore`) — cobre a cadeia longa do mesmo operador, que o
    parser constrói em `while`, não em recursão."""
    texto = texto if texto is not None else ""
    if not texto.strip():
        raise ErroExpressao("expressao_vazia", "expressão vazia")
    if len(texto) > MAX_TEXTO:
        raise ErroExpressao("expressao_grande", f"expressão maior que {MAX_TEXTO} caracteres", {"limite": MAX_TEXTO})
    tokens = _tokenizar(texto)
    if len(tokens) > MAX_TOKENS:
        raise ErroExpressao("expressao_grande", f"expressão com mais de {MAX_TOKENS} tokens", {"limite": MAX_TOKENS})
    no = _Parser(tokens, texto).analisar_tudo()
    profundidade = _profundidade_da_arvore(no)
    if profundidade > MAX_PROFUNDIDADE:
        raise ErroExpressao(
            "profundidade_excedida",
            f"árvore da expressão acima de {MAX_PROFUNDIDADE} níveis ({profundidade})",
            {"limite": MAX_PROFUNDIDADE, "medido": profundidade},
        )
    return no


def ebnf() -> str:
    """A gramática publicada em `docs/EXPRESSAO.md` seção 1 é ESTE texto, gerado das mesmas tabelas
    que o parser usa (`_PRECEDENCIA_*`, `_PALAVRAS_CHAVE`) — `test_expressao_doc_sincronizada.py`
    compara byte a byte; e `_OPERADORES` (tokenizador) tem de ser exatamente o conjunto de
    operadores que aparece aqui, senão o tokenizador aceitaria um token que a gramática não tem."""

    def alt(ops: set[str]) -> str:
        ordenados = sorted(ops, key=lambda o: _OPERADORES.index(o))
        dentro = " | ".join(f'"{o}"' for o in ordenados)
        return f'"{ordenados[0]}"' if len(ordenados) == 1 else f"( {dentro} )"

    palavras = " | ".join(f'"{p}"' for p in sorted(_PALAVRAS_CHAVE, key=len, reverse=True))
    return "\n".join(
        [
            "expressao     = ou ;",
            f'ou            = "e" , {{ {alt(_PRECEDENCIA_LOGICA_OU)} , "e" }} ;',
            f"e             = igualdade , {{ {alt(_PRECEDENCIA_LOGICA_E)} , igualdade }} ;",
            f"igualdade     = comparacao , {{ {alt(_PRECEDENCIA_IGUALDADE)} , comparacao }} ;",
            f"comparacao    = aditiva , {{ {alt(_PRECEDENCIA_COMPARACAO)} , aditiva }} ;",
            f"aditiva       = multiplicativa , {{ {alt(_PRECEDENCIA_ADITIVA)} , multiplicativa }} ;",
            f"multiplicativa= potencia , {{ {alt(_PRECEDENCIA_MULTIPLICATIVA)} , potencia }} ;",
            f"potencia      = unario , [ {alt(_PRECEDENCIA_POTENCIA)} , potencia ] ;"
            + "              (* associa à direita *)",
            f"unario        = {alt(_OPERADORES_UNARIOS)} , unario | primario ;",
            f"primario      = numero | string | {palavras}",
            "              | campo",
            '              | identificador , "(" , [ expressao , { "," , expressao } ] , ")"',
            '              | "(" , expressao , ")" ;',
            "",
            'campo          = "$" , identificador ;',
            'identificador  = ( letra | "_" ) , { letra | digito | "_" } ;',
            'numero         = digitos , [ "." , digitos ] | "." , digitos ;',
            'string         = "\'" , { qualquer_caractere_exceto_aspa_simples | "\'\'" } , "\'" ;',
        ]
    )


# =================================================================== 3. AST ↔ JSON (exportável)
def ast_para_json(no: No) -> dict:
    """AST → `dict` serializável (`json.dumps`). É o que se grava no documento junto com o texto
    (C6 do L2_CONCEITO.md) — reimportado por `ast_de_json`, tem de avaliar exatamente igual."""
    if isinstance(no, Literal):
        return {"tipo": "literal", "tipo_valor": no.tipo_valor, "valor": no.valor}
    if isinstance(no, Campo):
        return {"tipo": "campo", "nome": no.nome}
    if isinstance(no, Unario):
        return {"tipo": "unario", "operador": no.operador, "operando": ast_para_json(no.operando)}
    if isinstance(no, Binario):
        return {
            "tipo": "binario",
            "operador": no.operador,
            "esquerda": ast_para_json(no.esquerda),
            "direita": ast_para_json(no.direita),
        }
    if isinstance(no, Chamada):
        return {"tipo": "chamada", "nome": no.nome, "argumentos": [ast_para_json(a) for a in no.argumentos]}
    raise ErroExpressao("no_desconhecido", "nó de AST fora dos tipos esperados")  # pragma: no cover


def _validar_ast(no):
    stack = [(no, 1)]
    count = 0
    while stack:
        n, depth = stack.pop()
        count += 1
        if depth > MAX_PROFUNDIDADE:
            _falha("profundidade_excedida")
        if count > MAX_TOKENS:
            _falha("expressao_grande")
        if type(n) is Literal:
            valid = {
                "nulo": n.valor is None,
                "booleano": type(n.valor) is bool,
                "texto": type(n.valor) is str,
                "numero": _eh_numero(n.valor),
            }
            if type(n.tipo_valor) is not str or not valid.get(n.tipo_valor, False):
                _falha("no_desconhecido")
        elif type(n) is Campo:
            if type(n.nome) is not str or not IDENT_RE.fullmatch(n.nome):
                _falha("no_desconhecido")
        elif type(n) is Unario:
            if n.operador not in _OPERADORES_UNARIOS:
                _falha("no_desconhecido")
            stack.append((n.operando, depth + 1))
        elif type(n) is Binario:
            if n.operador not in _OPERADORES:
                _falha("no_desconhecido")
            stack.extend([(n.esquerda, depth + 1), (n.direita, depth + 1)])
        elif type(n) is Chamada:
            if type(n.nome) is not str or not IDENT_RE.fullmatch(n.nome) or type(n.argumentos) is not list:
                _falha("no_desconhecido")
            if len(n.argumentos) > MAX_ARGUMENTOS:
                _falha("expressao_grande")
            stack.extend((a, depth + 1) for a in n.argumentos)
        else:
            _falha("no_desconhecido")


def ast_de_json(d: dict, _profundidade: int = 1) -> No:
    count = 0

    def build(d, p):
        nonlocal count
        count += 1
        if p > MAX_PROFUNDIDADE:
            _falha("profundidade_excedida")
        if count > MAX_TOKENS:
            _falha("expressao_grande")
        if type(d) is not dict:
            _falha("no_desconhecido")
        t = d.get("tipo")
        required = {
            "literal": {"tipo_valor", "valor"},
            "campo": {"nome"},
            "unario": {"operador", "operando"},
            "binario": {"operador", "esquerda", "direita"},
            "chamada": {"nome", "argumentos"},
        }
        if type(t) is not str or t not in required or not required[t].issubset(d):
            _falha("no_desconhecido")
        if t == "literal":
            return Literal(d["tipo_valor"], d["valor"])
        if t == "campo":
            return Campo(d["nome"])
        if t == "unario":
            return Unario(d["operador"], build(d["operando"], p + 1))
        if t == "binario":
            return Binario(d["operador"], build(d["esquerda"], p + 1), build(d["direita"], p + 1))
        a = d["argumentos"]
        if type(a) is not list:
            _falha("no_desconhecido")
        if len(a) > MAX_ARGUMENTOS:
            _falha("expressao_grande")
        return Chamada(d["nome"], [build(x, p + 1) for x in a])

    result = build(d, _profundidade)
    _validar_ast(result)
    return result


# =================================================================== 4. avaliador
_EPOCA_MS_POR_DIA = 86_400_000


def _eh_numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _tipo_nome(v: Any) -> str:
    if v is None:
        return "nulo"
    if isinstance(v, bool):
        return "booleano"
    if _eh_numero(v):
        return "numero"
    if isinstance(v, str):
        return "texto"
    return type(v).__name__  # pragma: no cover — nenhum outro tipo nasce deste avaliador


def _formatar_numero(n: float) -> str:
    """Algoritmo ÚNICO (documentado em EXPRESSAO.md), replicado byte a byte em avaliador.js: inteiro
    sem parte fracionária vira texto sem ponto; caso contrário, até 6 casas decimais sem zero à
    direita. Nunca usa `str()`/`repr()` puro nem `toFixed` isolado — os dois divergem entre as
    línguas para o mesmo número (1.0 vira "1.0" em Python e "1" em JavaScript)."""
    if float(n).is_integer():
        return str(int(n))  # exato também acima de 1e21 (o JS usa BigInt no mesmo caso)
    s = _decimal_fixo(n, 6)
    return s.rstrip("0").rstrip(".")


def _decimal_fixo(n: float, casas: int) -> str:
    """`n` com exatamente `casas` decimais, arredondado sobre o VALOR BINÁRIO EXATO com empate para
    longe de zero — é a regra do `toFixed` do JavaScript. `f"{n:.6f}"` do Python arredonda empate
    para o par e diverge do JS em `0.0078125` (`'0.007812'` × `'0.007813'`): por isso `Decimal`,
    que carrega o binário exato, com `ROUND_HALF_UP`."""
    from decimal import ROUND_HALF_UP, Decimal

    return format(Decimal(n).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP), "f")


def _arredondar(x: float, casas: int) -> float:
    """Meio-para-longe-de-zero (não é o banker's rounding do `round()` do Python nem o arredonda-
    para-cima do `Math.round` do JavaScript para negativos): a MESMA fórmula nas duas línguas."""
    if abs(casas) > 15:
        _falha("numero_invalido")
    fator = 10.0**casas
    if x >= 0:
        return math.floor(x * fator + 0.5) / fator
    return math.ceil(x * fator - 0.5) / fator


class _Contador:
    __slots__ = ("passos", "limite_passos", "inicio", "limite_ms")

    def __init__(self, limite_passos: int, limite_ms: float):
        self.passos = 0
        self.limite_passos = limite_passos
        self.inicio = time.perf_counter()
        self.limite_ms = limite_ms

    def passo(self) -> None:
        self.passos += 1
        if self.passos > self.limite_passos:
            raise ErroExpressao(
                "limite_passos", f"avaliação acima de {self.limite_passos} passos", {"limite": self.limite_passos}
            )
        # relógio conferido a CADA passo (operações de coleção fazem um passo custar mais do que um nó;
        # amostrar a cada N passos deixaria um único `Unicos` de 1.024 elementos passar do orçamento)
        decorrido_ms = (time.perf_counter() - self.inicio) * 1000.0
        if decorrido_ms > self.limite_ms:
            raise ErroExpressao(
                "tempo_excedido", f"avaliação acima de {self.limite_ms:.0f} ms", {"limite_ms": self.limite_ms}
            )


# nome → (min_args, max_args ou None=variádico, descrição de 1 linha, exemplo)
TABELA_FUNCOES: dict[str, tuple[int, int | None, str, str]] = {
    # texto
    "Maiuscula": (1, 1, "converte texto para maiúsculas", "Maiuscula('sítio') → 'SÍTIO'"),
    "Minuscula": (1, 1, "converte texto para minúsculas", "Minuscula('SÍTIO') → 'sítio'"),
    "Concatenar": (1, None, "junta 2+ textos (nulo vira texto vazio)", "Concatenar('a','b','c') → 'abc'"),
    "Texto": (1, 1, "converte número/booleano/nulo para texto", "Texto(3.5) → '3.5'"),
    # número
    "Arredondar": (1, 2, "arredonda para N casas (padrão 0), meio-para-longe-de-zero", "Arredondar(2.345, 2) → 2.35"),
    "Absoluto": (1, 1, "valor absoluto", "Absoluto(-4) → 4"),
    "Minimo": (1, None, "menor valor entre 1+ números", "Minimo(4, 1, 9) → 1"),
    "Maximo": (1, None, "maior valor entre 1+ números", "Maximo(4, 1, 9) → 9"),
    "Numero": (1, 1, "converte texto/booleano para número (nulo se não for número válido)", "Numero('42') → 42"),
    "Potencia": (2, 2, "base elevada ao expoente", "Potencia(2, 10) → 1024"),
    # data (convenção: milissegundos desde a época Unix UTC)
    "AgoraUTC": (0, 0, "instante atual, milissegundos UTC desde a época Unix", "AgoraUTC() → 1798000000000"),
    "Ano": (1, 1, "ano civil UTC de uma data", "Ano(1798761600000) → 2026"),
    "Mes": (1, 1, "mês civil UTC de uma data (1-12)", "Mes(1798761600000) → 12"),
    "Dia": (1, 1, "dia do mês civil UTC de uma data (1-31)", "Dia(1798761600000) → 31"),
    "DiferencaDias": (2, 2, "dias corridos completos entre duas datas (data2 − data1)", "DiferencaDias(a, b) → 30"),
    # nulo
    "SeNulo": (2, 2, "se o 1º argumento é nulo, avalia e devolve o 2º (curto-circuito)", "SeNulo($x, 0) → 0"),
    "EhNulo": (1, 1, "verdadeiro se o argumento é nulo", "EhNulo($x) → falso"),
    # condicional
    "Se": (3, 3, "condição booleana decide qual ramo é avaliado (curto-circuito)", "Se($a > 0, 'pos', 'neg')"),
}

# Bounded JSON values and collection functions share the evaluator's operation budget.
MAX_COLECAO = 1024
MAX_VALOR_NOS = 4096
MAX_VALOR_TEXTO = 20000
MAX_VALOR_PROFUNDIDADE = 20
_PROIBIDOS = {"__proto__", "prototype", "constructor"}
_EXT_FUNCOES: dict[str, tuple[int, int | None, str, str]] = {
    # texto (índices e contagens em pontos de código Unicode, base zero)
    "Trim": (1, 1, "remove espaços ASCII das pontas", "Trim(' a ') → 'a'"),
    "Left": (2, 2, "primeiros N pontos de código", "Left('a🌍b', 2) → 'a🌍'"),
    "Right": (2, 2, "últimos N pontos de código (0 devolve vazio)", "Right('abc', 1) → 'c'"),
    "Mid": (2, 3, "trecho a partir de um índice; sem quantidade vai até o fim", "Mid('abcd', 1, 2) → 'bc'"),
    "Find": (2, 3, "índice da 1ª ocorrência a partir de um início; −1 se ausente", "Find('b', 'abc') → 1"),
    "Split": (2, 2, "divide por separador literal (vazio divide em pontos de código)", "Split('a,b', ',')"),
    "Replace": (3, 3, "troca todas as ocorrências literais", "Replace('aba', 'a', 'x') → 'xbx'"),
    # número
    "Floor": (1, 1, "maior inteiro ≤ número", "Floor(-1.5) → -2"),
    "Ceil": (1, 1, "menor inteiro ≥ número", "Ceil(-1.5) → -1"),
    "Sqrt": (1, 1, "raiz quadrada (negativo é numero_invalido)", "Sqrt(9) → 3"),
    # data
    "Weekday": (1, 1, "dia da semana UTC, domingo 0 … sábado 6", "Weekday(0) → 4"),
    # escolha
    "Decode": (4, None, "pares caso/resultado e padrão; só o resultado escolhido é avaliado", "Decode(1, 1, 'a', 'z')"),
    # coleções
    "Lista": (0, None, "lista nova com os argumentos (preserva nulos)", "Lista(1, nulo)"),
    "Contagem": (1, 1, "tamanho de lista, texto (pontos de código) ou dicionário", "Contagem(Lista(1, 2)) → 2"),
    "Primeiro": (1, 1, "primeiro elemento (nulo se vazia)", "Primeiro(Lista(4, 5)) → 4"),
    "Ultimo": (1, 1, "último elemento (nulo se vazia)", "Ultimo(Lista(4, 5)) → 5"),
    "Obter": (
        2,
        3,
        "lista por índice ou dicionário por chave própria; ausente → padrão/nulo",
        "Obter(Lista(4), 0) → 4",
    ),
    "Contem": (2, 2, "presença por igualdade estrutural estrita", "Contem(Lista(1), verdadeiro) → falso"),
    "Soma": (1, 1, "soma de números (vazia → 0; membro nulo → nulo)", "Soma(Lista(1, 2)) → 3"),
    "Media": (1, 1, "média de números (vazia ou membro nulo → nulo)", "Media(Lista(1, 2)) → 1.5"),
    "Reverter": (1, 1, "cópia em ordem inversa", "Reverter(Lista(1, 2))"),
    "Unicos": (1, 1, "sem repetições, preservando a 1ª ocorrência", "Unicos(Lista(1, 1))"),
    "Juntar": (1, 2, "texto dos escalares com separador (nulo vira vazio)", "Juntar(Lista(1, 2), '/') → '1/2'"),
    # formatação pt-BR (sempre UTC; algoritmo único, seção 6 de EXPRESSAO.md)
    "TextoNumero": (
        1,
        2,
        "número em pt-BR: milhar '.', decimal ',', N casas (padrão 2)",
        "TextoNumero(1234.5) → '1.234,50'",
    ),
    "TextoData": (
        1,
        2,
        "data UTC em pt-BR: 'data' (padrão), 'data_hora', 'data_hora_segundos', 'extenso'",
        "TextoData(0) → '01/01/1970'",
    ),
}
_EXT_ARIDADES = {nome: (minimo, maximo) for nome, (minimo, maximo, _d, _e) in _EXT_FUNCOES.items()}
TABELA_FUNCOES.update(_EXT_FUNCOES)
_MESES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
_FORMATOS_DATA = ("data", "data_hora", "data_hora_segundos", "extenso")


def _falha(codigo="tipo_invalido"):
    raise ErroExpressao(codigo, "valor ou operação fora do contrato")


def _finito(n):
    try:
        if not math.isfinite(n):
            _falha("numero_invalido")
    except (OverflowError, TypeError):
        _falha("numero_invalido")
    return n


def _potencia(a, b):
    if abs(b) > 1024:
        _falha("numero_invalido")
    try:
        return _finito(math.pow(a, b))
    except (OverflowError, ValueError):
        _falha("numero_invalido")


def _valor_seguro(valor, contador):
    nos = texto = 0

    def copiar(v, p):
        nonlocal nos, texto
        contador.passo()
        nos += 1
        if nos > MAX_VALOR_NOS or p > MAX_VALOR_PROFUNDIDADE:
            _falha("valor_grande")
        if v is None or type(v) is bool:
            return v
        if type(v) in (int, float):
            return _finito(float(v))
        if type(v) is str:
            texto += len(v)
            if texto > MAX_VALOR_TEXTO:
                _falha("valor_grande")
            return v
        if type(v) not in (list, dict):
            _falha()
        if len(v) > MAX_COLECAO:
            _falha("valor_grande")
        if type(v) is list:
            return [copiar(a, p + 1) for a in v]
        out = {}
        for k, a in v.items():
            if type(k) is not str:
                _falha()
            copiar(k, p + 1)
            out[k] = copiar(a, p + 1)
        return out

    return copiar(valor, 0)


def _igual_json(a, b, contador):
    contador.passo()
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    if _eh_numero(a) and _eh_numero(b):
        return a == b
    if type(a) is not type(b):
        return False
    if type(a) is list:
        return len(a) == len(b) and all(_igual_json(x, y, contador) for x, y in zip(a, b, strict=True))
    if type(a) is dict:
        return a.keys() == b.keys() and all(_igual_json(a[k], b[k], contador) for k in a)
    return a == b


def _indice(a):
    if not _eh_numero(a) or a < 0 or a != math.floor(a):
        _falha()
    return int(a)


def _ext_funcao(nome, a, contador):
    minimo, maximo = _EXT_ARIDADES[nome]
    if len(a) < minimo or (maximo is not None and len(a) > maximo):
        _falha("aridade_invalida")
    if nome == "Lista":
        return a
    if nome == "Obter":
        c, k = a[:2]
        default = a[2] if len(a) == 3 else None
        if c is None:
            return default
        if type(c) is list:
            k = _indice(k)
            return c[k] if k < len(c) else default
        if type(c) is not dict or type(k) is not str:
            _falha()
        if k in _PROIBIDOS:
            _falha("campo_nao_permitido")
        return c.get(k, default)
    if nome == "Contem":
        if a[0] is None:
            return None
        if type(a[0]) is not list:
            _falha()
        return any(_igual_json(x, a[1], contador) for x in a[0])
    if any(x is None for x in a):
        return None
    if nome in ("Trim", "Left", "Right", "Mid", "Find", "Split", "Replace"):
        if type(a[0]) is not str:
            _falha()
        t = a[0]
        if nome == "Trim":
            return t.strip(" \t\r\n\f\v")
        if nome == "Left":
            return t[: _indice(a[1])]
        if nome == "Right":
            n = _indice(a[1])
            return t[-n:] if n else ""
        if nome == "Mid":
            n = _indice(a[1])
            return t[n : n + _indice(a[2])] if len(a) == 3 else t[n:]
        if type(a[1]) is not str:
            _falha()
        if nome == "Find":
            return a[1].find(t, _indice(a[2]) if len(a) == 3 else 0)
        if nome == "Split":
            r = t.split(a[1]) if a[1] else list(t)
            if len(r) > MAX_COLECAO:
                _falha("valor_grande")
            return r
        if type(a[2]) is not str:
            _falha()
        if not a[1]:
            return t
        if len(t) + t.count(a[1]) * (len(a[2]) - len(a[1])) > MAX_VALOR_TEXTO:
            _falha("valor_grande")
        return t.replace(a[1], a[2])
    if nome == "TextoNumero":
        return _texto_numero_pt(_exigir_numero(a[0], nome), _indice(a[1]) if len(a) == 2 else 2)
    if nome == "TextoData":
        formato = a[1] if len(a) == 2 else "data"
        if type(formato) is not str or formato not in _FORMATOS_DATA:
            _falha()
        return _texto_data_pt(_exigir_numero(a[0], nome), formato)
    if nome in ("Floor", "Ceil", "Sqrt", "Weekday"):
        n = _exigir_numero(a[0], nome)
        if nome == "Floor":
            return math.floor(n)
        if nome == "Ceil":
            return math.ceil(n)
        if nome == "Sqrt":
            if n < 0:
                _falha("numero_invalido")
            return math.sqrt(n)
        _ano_mes_dia_utc(n)
        return (math.floor(n / _EPOCA_MS_POR_DIA) + 4) % 7
    c = a[0]
    if nome == "Contagem":
        if type(c) not in (list, dict, str):
            _falha()
        return len(c)
    if type(c) is not list:
        _falha()
    if nome == "Primeiro":
        return c[0] if c else None
    if nome == "Ultimo":
        return c[-1] if c else None
    if nome == "Reverter":
        return c[::-1]
    if nome in ("Soma", "Media"):
        if any(x is None for x in c):
            return None
        soma = 0.0
        for x in c:
            contador.passo()
            soma = _finito(soma + _exigir_numero(x, nome))
        return soma if nome == "Soma" else soma / len(c) if c else None
    if nome == "Unicos":
        out = []
        for x in c:
            if not any(_igual_json(x, y, contador) for y in out):
                out.append(x)
        return out
    if nome == "Juntar":
        sep = a[1] if len(a) == 2 else ""
        if type(sep) is not str:
            _falha()
        partes = [_chamar_funcao("Texto", [x], {}) for x in c]
        if sum(map(len, partes)) + len(sep) * max(0, len(c) - 1) > MAX_VALOR_TEXTO:
            _falha("valor_grande")
        return sep.join(partes)
    _falha("funcao_desconhecida")


def _texto_numero_pt(n: float, casas: int) -> str:
    """pt-BR: separador de milhar '.', decimal ',', exatamente `casas` decimais (0–15), arredondado
    sobre o valor binário exato com empate para longe de zero (= `toFixed`); zero nunca leva sinal."""
    if casas > 15 or abs(n) >= 1e21:
        _falha("numero_invalido")
    fixo = _decimal_fixo(abs(n), casas)
    inteiro, _, fracao = fixo.partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    texto = ".".join(grupos) + ("," + fracao if casas else "")
    negativo = n < 0 and any(c not in "0.," for c in texto)
    return ("-" if negativo else "") + texto


def _texto_data_pt(ms: float, formato: str) -> str:
    import datetime

    _ano_mes_dia_utc(ms)  # mesma faixa (anos 1–9999) e mesmo erro nomeado que Ano/Mes/Dia/Weekday
    dt = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(milliseconds=math.floor(ms))
    if formato == "extenso":
        return f"{dt.day} de {_MESES_PT[dt.month - 1]} de {dt.year:04d}"
    texto = f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"
    if formato == "data_hora":
        return f"{texto} {dt.hour:02d}:{dt.minute:02d}"
    if formato == "data_hora_segundos":
        return f"{texto} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    return texto


def _canonico(v):
    """Valor de SAÍDA na forma que o JSON dos dois lados produz: número inteiro (até 2^53, exato em
    double) vira `int`, `-0.0` vira `0` — `JSON.stringify(7)` é `7`, e `json.dumps(7.0)` seria `7.0`.
    Só na saída de `avaliar`; por dentro a aritmética é toda em `float`, como o double do JS."""
    if type(v) is float:
        if v.is_integer() and abs(v) < 9007199254740992.0:
            return int(v)
        return v
    if type(v) is list:
        return [_canonico(x) for x in v]
    if type(v) is dict:
        return {k: _canonico(x) for k, x in v.items()}
    return v


_FUNCOES_PREGUICOSAS = {"Se", "SeNulo"}  # não avaliam todos os argumentos de antemão


def _dias_desde_epoca(ms: int) -> int:
    return ms // _EPOCA_MS_POR_DIA if ms >= 0 else -((-ms + _EPOCA_MS_POR_DIA - 1) // _EPOCA_MS_POR_DIA)


def _ano_mes_dia_utc(ms: float) -> tuple[int, int, int]:
    import datetime

    if ms < -62135596800000 or ms >= 253402300800000:
        _falha("numero_invalido")
    dt = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(milliseconds=ms)
    return dt.year, dt.month, dt.day


def _exigir_numero(v: Any, onde: str) -> float:
    if not _eh_numero(v):
        raise ErroExpressao("tipo_invalido", f"{onde} espera número, recebeu {_tipo_nome(v)}", {"onde": onde})
    return _finito(v)


def _chamar_funcao(nome: str, args: list[Any], onde_erro: dict) -> Any:
    if nome not in TABELA_FUNCOES:
        raise ErroExpressao("funcao_desconhecida", f"função desconhecida: {nome}", {**onde_erro, "nome": nome})
    minimo, maximo, _desc, _exemplo = TABELA_FUNCOES[nome]
    if len(args) < minimo or (maximo is not None and len(args) > maximo):
        raise ErroExpressao(
            "aridade_invalida",
            f"{nome} espera "
            + (f"{minimo}" if maximo == minimo else f"{minimo}-{maximo}" if maximo is not None else f"≥{minimo}")
            + f" argumento(s), recebeu {len(args)}",
            {**onde_erro, "nome": nome, "recebido": len(args)},
        )

    if nome == "Maiuscula":
        if not isinstance(args[0], str):
            raise ErroExpressao("tipo_invalido", "Maiuscula espera texto", onde_erro)
        return args[0].upper()
    if nome == "Minuscula":
        if not isinstance(args[0], str):
            raise ErroExpressao("tipo_invalido", "Minuscula espera texto", onde_erro)
        return args[0].lower()
    if nome == "Concatenar":
        partes = []
        for a in args:
            if a is None:
                partes.append("")
            elif isinstance(a, bool):
                partes.append("verdadeiro" if a else "falso")
            elif isinstance(a, str):
                partes.append(a)
            elif _eh_numero(a):
                partes.append(_formatar_numero(a))
            else:  # pragma: no cover
                raise ErroExpressao("tipo_invalido", "Concatenar recebeu tipo não suportado", onde_erro)
        return "".join(partes)
    if nome == "Texto":
        v = args[0]
        if v is None:
            return ""
        if isinstance(v, bool):
            return "verdadeiro" if v else "falso"
        if isinstance(v, str):
            return v
        return _formatar_numero(_exigir_numero(v, "Texto"))
    if nome == "Arredondar":
        casas = 0
        if len(args) == 2:
            casas_v = _exigir_numero(args[1], "Arredondar (casas)")
            casas = int(casas_v)
        valor = _exigir_numero(args[0], "Arredondar")
        r = _arredondar(float(valor), casas)
        return int(r) if r == int(r) else r
    if nome == "Absoluto":
        return abs(_exigir_numero(args[0], "Absoluto"))
    if nome == "Minimo":
        return min(_exigir_numero(a, "Minimo") for a in args)
    if nome == "Maximo":
        return max(_exigir_numero(a, "Maximo") for a in args)
    if nome == "Numero":
        v = args[0]
        if _eh_numero(v):
            return v
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, str):
            texto = v.strip()
            if re.fullmatch(r"-?\d+", texto):
                return _finito(float(texto))
            if re.fullmatch(r"-?\d+\.\d+", texto):
                return float(texto)
            return None
        return None
    if nome == "Potencia":
        base = _exigir_numero(args[0], "Potencia")
        expoente = _exigir_numero(args[1], "Potencia")
        return _potencia(base, expoente)
    if nome == "AgoraUTC":
        return int(time.time() * 1000)
    if nome in ("Ano", "Mes", "Dia"):
        ms = _exigir_numero(args[0], nome)
        ano, mes, dia = _ano_mes_dia_utc(float(ms))
        return {"Ano": ano, "Mes": mes, "Dia": dia}[nome]
    if nome == "DiferencaDias":
        a = _exigir_numero(args[0], "DiferencaDias")
        b = _exigir_numero(args[1], "DiferencaDias")
        return _dias_desde_epoca(int(b)) - _dias_desde_epoca(int(a))
    if nome == "EhNulo":
        return args[0] is None
    raise ErroExpressao(  # pragma: no cover
        "funcao_desconhecida", f"função desconhecida: {nome}", {**onde_erro, "nome": nome}
    )


def avaliar(
    no: No,
    contexto: dict[str, Any] | None = None,
    *,
    limite_passos: int = MAX_PASSOS_PADRAO,
    limite_ms: float = LIMITE_MS_SERVIDOR,
) -> Any:
    """AST → valor. `contexto` é a lista BRANCA de campos disponíveis (nunca `getattr` de objeto do
    chamador, nunca `globals()`/`vars()`): `$campo` fora de `contexto` é `campo_nao_permitido`. Todo
    nó consome pelo menos 1 passo do orçamento (`limite_passos`) e o relógio de parede é conferido
    periodicamente contra `limite_ms` — os dois cortam laço/recursão profunda com erro nomeado,
    nunca com estouro de pilha ou travamento (refutação do item-pai)."""
    contexto = {} if contexto is None else contexto
    if type(contexto) is not dict:
        _falha()
    contador = _Contador(limite_passos, limite_ms)

    _validar_ast(no)

    def v(nodo: No) -> Any:
        try:
            return _valor_seguro(executar(nodo), contador)
        except (OverflowError, ValueError, ZeroDivisionError):
            _falha("numero_invalido")

    def executar(nodo: No) -> Any:
        contador.passo()
        if isinstance(nodo, Literal):
            return nodo.valor
        if isinstance(nodo, Campo):
            if nodo.nome in _PROIBIDOS or nodo.nome not in contexto:
                raise ErroExpressao("campo_nao_permitido", f"campo não permitido: {nodo.nome}", {"campo": nodo.nome})
            return contexto[nodo.nome]
        if isinstance(nodo, Unario):
            operando = v(nodo.operando)
            if nodo.operador == "-":
                if operando is None:
                    return None
                return -_exigir_numero(operando, "operador unário -")
            if nodo.operador == "!":
                if operando is None:
                    return None
                if not isinstance(operando, bool):
                    raise ErroExpressao("tipo_invalido", "operador '!' espera booleano", {})
                return not operando
            raise ErroExpressao(  # pragma: no cover
                "operador_desconhecido", f"operador unário desconhecido: {nodo.operador}"
            )
        if isinstance(nodo, Binario):
            return _binario(nodo, v)
        if isinstance(nodo, Chamada):
            if nodo.nome == "Se":
                if len(nodo.argumentos) != 3:
                    raise ErroExpressao("aridade_invalida", "Se espera 3 argumentos", {"nome": "Se"})
                cond = v(nodo.argumentos[0])
                if not isinstance(cond, bool):
                    raise ErroExpressao(
                        "tipo_invalido", f"Se espera condição booleana, recebeu {_tipo_nome(cond)}", {"nome": "Se"}
                    )
                return v(nodo.argumentos[1]) if cond else v(nodo.argumentos[2])
            if nodo.nome == "SeNulo":
                if len(nodo.argumentos) != 2:
                    raise ErroExpressao("aridade_invalida", "SeNulo espera 2 argumentos", {"nome": "SeNulo"})
                primeiro = v(nodo.argumentos[0])
                return v(nodo.argumentos[1]) if primeiro is None else primeiro
            if nodo.nome == "Decode":
                if len(nodo.argumentos) < 4 or len(nodo.argumentos) % 2:
                    _falha("aridade_invalida")
                valor = v(nodo.argumentos[0])
                for i in range(1, len(nodo.argumentos) - 1, 2):
                    if _igual_json(valor, v(nodo.argumentos[i]), contador):
                        return v(nodo.argumentos[i + 1])
                return v(nodo.argumentos[-1])
            args = [v(a) for a in nodo.argumentos]
            if nodo.nome in _EXT_ARIDADES:
                return _ext_funcao(nodo.nome, args, contador)
            return _chamar_funcao(nodo.nome, args, {"nome": nodo.nome})
        raise ErroExpressao("no_desconhecido", "nó de AST fora dos tipos esperados")  # pragma: no cover

    def _binario(nodo: Binario, v) -> Any:
        op = nodo.operador
        if op == "&&":
            esquerda = v(nodo.esquerda)
            _exigir_booleano_ou_nulo(esquerda, "&&")
            if esquerda is False:
                return False  # curto-circuito SQL: falso decide, nunca avalia o direito
            direita = v(nodo.direita)
            _exigir_booleano_ou_nulo(direita, "&&")
            if direita is False:
                return False
            if esquerda is None or direita is None:
                return None
            return True
        if op == "||":
            esquerda = v(nodo.esquerda)
            _exigir_booleano_ou_nulo(esquerda, "||")
            if esquerda is True:
                return True
            direita = v(nodo.direita)
            _exigir_booleano_ou_nulo(direita, "||")
            if direita is True:
                return True
            if esquerda is None or direita is None:
                return None
            return False
        esquerda = v(nodo.esquerda)
        direita = v(nodo.direita)
        if op == "==":
            return _igual(esquerda, direita)
        if op == "!=":
            r = _igual(esquerda, direita)
            return None if r is None else (not r)
        if op in ("<", "<=", ">", ">="):
            if esquerda is None or direita is None:
                return None
            if _eh_numero(esquerda) and _eh_numero(direita):
                a, b = esquerda, direita
            elif isinstance(esquerda, str) and isinstance(direita, str):
                a, b = esquerda, direita
            else:
                raise ErroExpressao(
                    "tipo_invalido",
                    f"'{op}' espera dois números ou dois textos, recebeu {_tipo_nome(esquerda)}/{_tipo_nome(direita)}",
                    {"operador": op},
                )
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        # aritmética: propaga nulo
        if esquerda is None or direita is None:
            return None
        a = _exigir_numero(esquerda, f"operador '{op}'")
        b = _exigir_numero(direita, f"operador '{op}'")
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise ErroExpressao("divisao_por_zero", "divisão por zero", {})
            return a / b
        if op == "%":
            if b == 0:
                raise ErroExpressao("divisao_por_zero", "resto da divisão por zero", {})
            return a % b
        if op == "^":
            return _potencia(a, b)
        raise ErroExpressao("operador_desconhecido", f"operador desconhecido: {op}")  # pragma: no cover

    def _exigir_booleano_ou_nulo(valor: Any, op: str) -> None:
        if valor is not None and not isinstance(valor, bool):
            raise ErroExpressao(
                "tipo_invalido", f"'{op}' espera booleano ou nulo, recebeu {_tipo_nome(valor)}", {"operador": op}
            )

    def _igual(a: Any, b: Any) -> bool | None:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b
        if _eh_numero(a) and _eh_numero(b):
            return a == b
        if isinstance(a, str) and isinstance(b, str):
            return a == b
        return False

    return _canonico(v(no))


def avaliar_texto(
    texto: str,
    contexto: dict[str, Any] | None = None,
    *,
    limite_passos: int = MAX_PASSOS_PADRAO,
    limite_ms: float = LIMITE_MS_SERVIDOR,
) -> Any:
    """Atalho de um passo só: `analisar(texto)` + `avaliar(...)`."""
    return avaliar(analisar(texto), contexto, limite_passos=limite_passos, limite_ms=limite_ms)
