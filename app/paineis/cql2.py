"""Subconjunto seguro de CQL2-JSON (item L2-06-a-modelo-painel-fontes) para o filtro FIXO de uma vista
de painel (`corpo.fontes[].filtro`, forma `{"op": ..., "args": [...]}` do padrão OGC CQL2 — JSON, não
texto). O L2-01-h amplia a gramática (mais operadores, geometria); este módulo cobre só o que o
esquema do painel aceita hoje: comparação simples, `and`/`or`, `in`, `isNull`, `like`.

Em vez de gerar SQL de novo (uma segunda superfície de injeção para auditar), este módulo TRADUZ o
CQL2-JSON para o texto da gramática já auditada de `app.consulta.where_ast` (a mesma que
`POST /api/camadas/{id}/estatisticas`, item L2-06-e, usa para `corpo.filtro`) e devolve esse texto —
quem quiser o SQL final chama `where_ast.compilar_where(texto, colunas)` como já faz hoje. Literal
nunca é concatenado cru: string ganha aspa simples dobrada (mesma regra do tokenizador do where_ast,
`''` dentro da string é uma aspa literal), número vira repr Python (sem aspas), boolean/None não são
aceitos como literal (CQL2 não define comparação com null fora de `isNull`)."""

from __future__ import annotations

from app.erros import ErroAPI

_OPERADORES_BINARIOS = {"=": "=", "<>": "!=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
_ACEITOS = {"and", "or", "in", "isnull", "like"} | set(_OPERADORES_BINARIOS)

MAX_PROFUNDIDADE = 20


def _erro(msg: str) -> ErroAPI:
    return ErroAPI(422, "filtro_cql2_invalido", msg)


def _literal(valor) -> str:
    if isinstance(valor, bool):
        raise _erro("CQL2: literal booleano não é aceito (use isNull ou uma comparação por campo)")
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, str):
        return "'" + valor.replace("'", "''") + "'"
    raise _erro(f"CQL2: tipo de literal não suportado: {type(valor).__name__}")


def _propriedade(no) -> str:
    if not isinstance(no, dict) or "property" not in no or not isinstance(no["property"], str):
        raise _erro("CQL2: esperava {'property': <campo>} nesta posição")
    campo = no["property"]
    if not campo or not (campo[0].isalpha() or campo[0] == "_"):
        raise _erro(f"CQL2: nome de campo inválido: {campo!r}")
    return campo


def _traduzir(no, profundidade: int = 0) -> str:
    if profundidade > MAX_PROFUNDIDADE:
        raise _erro("CQL2: filtro aninhado demais")
    no = _normalizar(no)
    if not isinstance(no, dict):
        raise _erro("CQL2: cada nó do filtro precisa ser um objeto {'op':..., 'args':[...]}")
    op = no.get("op")
    args = no.get("args")
    if op not in _ACEITOS or not isinstance(args, list):
        raise _erro(f"CQL2: operador não suportado ou 'args' ausente: {op!r}")

    if op in ("and", "or"):
        if len(args) < 2:
            raise _erro(f"CQL2: '{op}' exige ao menos dois operandos")
        partes = [f"({_traduzir(a, profundidade + 1)})" for a in args]
        return f" {op.upper()} ".join(partes)

    if op in _OPERADORES_BINARIOS:
        if len(args) != 2:
            raise _erro(f"CQL2: '{op}' exige exatamente dois operandos")
        campo = _propriedade(args[0])
        return f"{campo} {_OPERADORES_BINARIOS[op]} {_literal(args[1])}"

    if op == "like":
        if len(args) != 2 or not isinstance(args[1], str):
            raise _erro("CQL2: 'like' exige campo e um literal texto")
        campo = _propriedade(args[0])
        return f"{campo} LIKE {_literal(args[1])}"

    if op == "isnull":
        if len(args) != 1:
            raise _erro("CQL2: 'isNull' exige um único operando")
        campo = _propriedade(args[0])
        return f"{campo} IS NULL"

    if op == "in":
        if len(args) != 2 or not isinstance(args[1], list) or not args[1]:
            raise _erro("CQL2: 'in' exige campo e uma lista não vazia de literais")
        campo = _propriedade(args[0])
        valores = ", ".join(_literal(v) for v in args[1])
        return f"{campo} IN ({valores})"

    raise _erro(f"CQL2: operador não implementado: {op!r}")  # pragma: no cover — _ACEITOS já filtrou


def cql2_para_texto(filtro: dict | None) -> str | None:
    """`None`/`{}` → nenhum filtro. Caso contrário, devolve o texto na gramática de `where_ast`,
    pronto para `where_ast.compilar_where(texto, colunas)`. Levanta `ErroAPI(422, ...)`."""
    if not filtro:
        return None
    return _traduzir(filtro)


def _normalizar(no):
    if isinstance(no, dict) and isinstance(no.get("op"), str):
        return {**no, "op": no["op"].lower()}
    return no
