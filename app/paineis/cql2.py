"""Subconjunto seguro de CQL2-JSON (item L2-06-a-modelo-painel-fontes) para o filtro FIXO de uma vista
de painel (`corpo.fontes[].filtro`, forma `{"op": ..., "args": [...]}` do padrão OGC CQL2 — JSON, não
texto). O L2-01-h amplia a gramática (mais operadores, geometria); este módulo cobre só o que o
esquema do painel aceita hoje: comparação simples, `and`/`or`, `in`, `isNull`, `like` — e, para o
filtro dinâmico por pedido do L2-06-c (`separar_espacial`), o nó `s_intersects` na única forma que
o barramento do L5-07 produz (caixa alinhada aos eixos), que não entra no texto: vira parâmetro.

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


# -----------------------------------------------------------------------------------------------
# Item L2-06-c: o filtro dinâmico de UMA ação (seletor, seleção em barra/lista, extensão do mapa)
# chega por PEDIDO (`pedidos[<elemento>].filtro`), além do filtro fixo da fonte. Gramática é a mesma;
# o único nó novo é `s_intersects` (a relação espacial do barramento do L5-07), que só é aceito na
# forma que o barramento produz: polígono-retaângulo alinhado aos eixos → vira caixa [o,s,l,n] e o
# chamador transforma em `ST_MakeEnvelope(%s,%s,%s,%s,4326)` com parâmetro (nunca texto solto).
CAMADA_MAX_ENVELOPES = 8  # caixas espaciais num mesmo filtro de pedido (basta: cada ação produz 1)


def propriedades(filtro, saida: set[str] | None = None) -> set[str]:
    """Todo nome de campo citado no filtro (para validar contra a lista branca da fonte ANTES de
    traduzir, devolvendo `campo_fora_da_fonte` em vez de um erro de gramática genérico)."""
    saida = saida if saida is not None else set()
    if isinstance(filtro, dict):
        if isinstance(filtro.get("property"), str):
            saida.add(filtro["property"])
        for v in filtro.values():
            if isinstance(v, (dict, list)):
                propriedades(v, saida)
    elif isinstance(filtro, list):
        for v in filtro:
            propriedades(v, saida)
    return saida


def _caixa_de_poligono(geom) -> list[float]:
    """Polygon CQL2 → caixa [oeste, sul, leste, norte], só quando o anel é um retângulo alinhado
    (a forma que o barramento do L5-07 produz em `#traduzir` para a relação `espacial`). Qualquer
    outra geometria é RECUSADA: interseção exata de polígono no servidor é trabalho do L2-01-h,
    não do filtro de execução do painel."""
    if not isinstance(geom, dict) or geom.get("type") != "Polygon":
        raise _erro("CQL2: s_intersects do painel aceita só Polygon alinhado aos eixos")
    anel = geom.get("coordinates")
    if not isinstance(anel, list) or len(anel) != 1 or not isinstance(anel[0], list) or len(anel[0]) != 5:
        raise _erro("CQL2: s_intersects do painel exige um único anel fechado de 5 pontos (retângulo)")
    pontos = anel[0]
    try:
        xs = [float(p[0]) for p in pontos]
        ys = [float(p[1]) for p in pontos]
    except (TypeError, ValueError, IndexError) as e:
        raise _erro("CQL2: s_intersects com coordenada inválida") from e
    if pontos[0] != pontos[4]:
        raise _erro("CQL2: anel de s_intersects não fecha (primeiro e último ponto diferem)")
    if len({*xs}) > 2 or len({*ys}) > 2:
        raise _erro("CQL2: s_intersects do painel só aceita retângulo alinhado aos eixos (caixa)")
    return [min(xs), min(ys), max(xs), max(ys)]


def separar_espacial(filtro, coluna_geometria: str = "geom", profundidade: int = 0):
    """Divide o filtro CQL2 de um pedido em (resto, caixas): os nós `s_intersects` saem da árvore e
    viram caixas [o,s,l,n] para o chamador montar a condição espacial com parâmetro; o que sobra
    (podendo ser `None`) segue pelo tradutor de texto de sempre. `s_intersects` dentro de `or` é
    recusado — (A ou caixa) não separa em (A) E (caixa); o editor manda o autor usar dois pedidos."""
    if profundidade > MAX_PROFUNDIDADE:
        raise _erro("CQL2: filtro aninhado demais")
    if not isinstance(filtro, dict):
        return filtro, []
    no = _normalizar(filtro)
    op = no.get("op")
    if op == "s_intersects":
        args = no.get("args")
        if not isinstance(args, list) or len(args) != 2:
            raise _erro("CQL2: 's_intersects' exige campo e geometria")
        campo = _propriedade(args[0])
        if campo not in ("geometria", coluna_geometria):
            raise _erro(f"CQL2: s_intersects só vale na coluna de geometria da fonte ({campo!r})")
        return None, [_caixa_de_poligono(args[1])]
    if op in ("and", "or"):
        args = no.get("args")
        if not isinstance(args, list) or len(args) < 2:
            raise _erro(f"CQL2: '{op}' exige ao menos dois operandos")
        restos = []
        caixas: list[list[float]] = []
        for a in args:
            r, c = separar_espacial(a, coluna_geometria, profundidade + 1)
            if c and op == "or":
                raise _erro("CQL2: s_intersects dentro de 'or' não é aceito no filtro de pedido do painel")
            if r is not None:
                restos.append(r)
            caixas += c
        resto = {"op": op, "args": restos} if len(restos) > 1 else (restos[0] if restos else None)
        return resto, caixas[:CAMADA_MAX_ENVELOPES + 1]
    return no, []


def _normalizar(no):
    if isinstance(no, dict) and isinstance(no.get("op"), str):
        return {**no, "op": no["op"].lower()}
    return no
