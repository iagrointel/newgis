"""Apoio de teste (não é código de produto): avalia em Python só os operadores que
`app/expressao/compilador_maplibre.py` emite (get/literal/concat/to-string/upcase/downcase/case/
coalesce/abs/min/max/round/aritmética/comparação/all/any/!), para provar a IDENTIDADE do compilador
— "a mesma expressão, compilada para MapLibre e avaliada com as regras da Style Spec, dá o mesmo
texto que `avaliador_py.avaliar` dá pelo caminho do servidor" (cláusula do item L2-02-d-rotulos:
"expressão não compilável cai para coluna do servidor sem diferença visual ... texto idêntico em
100 feições"). NÃO é o motor do MapLibre (isso é testado à parte, com o MapLibre-GL real, em
tests/e2e/test_rotulos_render.py); é um intérprete de referência, escrito à mão, sem eval/exec, só
para o subconjunto que este item compila — a mesma disciplina de tests/e2e/apoio_estilo/
harness_estilo.html (arnês pequeno e explícito, não o produto)."""

from __future__ import annotations

from typing import Any


def _para_texto(v: Any) -> str:
    # ["to-string", v] pela Style Spec: nulo -> "", booleano -> "true"/"false", número como está.
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def avaliar(expr: Any, props: dict) -> Any:
    if not isinstance(expr, list):
        return expr
    op = expr[0]
    if op == "get":
        return props.get(expr[1])
    if op == "to-string":
        return _para_texto(avaliar(expr[1], props))
    if op == "concat":
        return "".join(_para_texto(avaliar(a, props)) for a in expr[1:])
    if op == "upcase":
        return _para_texto(avaliar(expr[1], props)).upper()
    if op == "downcase":
        return _para_texto(avaliar(expr[1], props)).lower()
    if op == "case":
        # ["case", cond1, val1, cond2, val2, ..., padrao]
        pares = expr[1:-1]
        for i in range(0, len(pares), 2):
            if avaliar(pares[i], props):
                return avaliar(pares[i + 1], props)
        return avaliar(expr[-1], props)
    if op == "coalesce":
        for a in expr[1:]:
            v = avaliar(a, props)
            if v is not None:
                return v
        return None
    if op == "abs":
        return abs(avaliar(expr[1], props))
    if op == "min":
        return min(avaliar(a, props) for a in expr[1:])
    if op == "max":
        return max(avaliar(a, props) for a in expr[1:])
    if op == "round":
        v = avaliar(expr[1], props)
        return float(int(v + 0.5)) if v >= 0 else float(-int(-v + 0.5))
    if op == "!":
        return not avaliar(expr[1], props)
    if op == "all":
        return all(avaliar(a, props) for a in expr[1:])
    if op == "any":
        return any(avaliar(a, props) for a in expr[1:])
    if op in ("+", "-", "*", "/"):
        a, b = avaliar(expr[1], props), avaliar(expr[2], props)
        return {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[op]
    if op in ("==", "!=", "<", "<=", ">", ">="):
        a, b = avaliar(expr[1], props), avaliar(expr[2], props)
        return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    raise ValueError(f"operador não suportado no arnês de teste: {op!r}")


def texto_final(expr: Any, props: dict) -> str:
    """Como o `text-field` chega ao rótulo: o resultado vira texto (nunca 'None'/'null' literal)."""
    v = avaliar(expr, props)
    return _para_texto(v)
