"""CQL2-JSON (OGC 21-065r2, "Common Query Language 2") — subconjunto restrito usado pelo construtor de
filtro do mapa (item L2-01-h) e pela `vista_de_camada` (ADR 0004 seção 3, tabela de tipos, campo
`filtro`, comentário "L2 C7"). O item L5-07 (barramento de mensagens do builder) ainda está `pendente`
no laço — este módulo é o primeiro tradutor CQL2-JSON → SQL da casa, e o VOCABULÁRIO JSON aceito aqui
é o que aquele item deve reaproveitar quando for construído (mesmo formato, nunca um segundo).

Vocabulário aceito — tudo fora disto é `operador_nao_permitido`, nunca ignorado nem tolerado:

  lógico:      {"op": "and"|"or", "args": [nó, nó, ...]}   — aninhamento máximo `MAX_PROFUNDIDADE` (2)
  comparação:  {"op": "="|"<>"|"<"|"<="|">"|">=", "args": [{"property": campo}, literal]}
  texto:       {"op": "like", "args": [{"property": campo}, "padrão com % e _"]}
  lista:       {"op": "in", "args": [{"property": campo}, [v1, v2, ...]]}
  nulo:        {"op": "isNull", "args": [{"property": campo}]}
  espacial:    {"op": "s_intersects", "args": [{"property": campo_geometria}, geometria GeoJSON]}
               {"op": "s_dwithin", "args": [{"property": campo_geometria}, geometria GeoJSON, metros]}
               (`s_dwithin` é uma EXTENSÃO declarada: o núcleo do CQL2 não tem função de distância;
               ver ADR do item)
  temporal relativo: função nomeada `now_menos_dias`, SÓ dentro de um argumento de comparação —
               {"op": ">=", "args": [{"property": campo_data}, {"function": {"name": "now_menos_dias",
               "args": [30]}}]} — equivale a "últimos 30 dias". Nenhuma outra função é aceita
               (`FUNCOES_PERMITIDAS` é a lista branca inteira; `now_menos_dias` sozinha).
  literal:     número, string, booleano, null, lista (só dentro de `in`)
  referência:  {"property": "<campo>"}

Duas etapas, como em `where_ast.py` (mesma disciplina, mesmo módulo de erro `ErroWhere`):

1. `_validar_estrutura(no)` — só vocabulário e forma: função/operador fora da lista branca, aninhamento
   acima do limite ou mais de `MAX_CLAUSULAS` comparações levantam ANTES de olhar qualquer coluna.
2. `compilar_cql2(no, colunas)` — só então a lista branca de COLUNAS do chamador entra em jogo: campo
   fora dela é `campo_nao_permitido`; valor de tipo incompatível com o tipo declarado da coluna é
   `tipo_invalido`. Todo literal vira parâmetro `%s`; nunca é escrito no texto do SQL.

`colunas` é um dict `nome_no_filtro -> {"sql": expressão SQL de confiança do chamador, "tipo": tipo
PostgreSQL declarado ("text", "integer", "bigint", "double precision", "real", "boolean", "date",
"timestamp with time zone", "timestamp without time zone", "geometry" — o mesmo vocabulário de
`app.ingestao.tipos_campo`), "srid": int (só para "geometry")}`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.consulta.where_ast import ConsultaSQL, ErroWhere  # reaproveita infraestrutura de erro/retorno

MAX_PROFUNDIDADE = 2  # AND/OR aninhado até 2 níveis (portão do item)
MAX_CLAUSULAS = 100  # cláusulas de comparação/espacial; refutação ataca com 200 e espera 422
MAX_IN = 500  # tamanho de uma lista de "in"

OPS_LOGICOS = {"and", "or"}
OPS_COMPARACAO = {"=", "<>", "<", "<=", ">", ">="}
OPS_ESPACIAIS = {"s_intersects", "s_dwithin"}
OPS_FOLHA = OPS_COMPARACAO | {"like", "in", "isNull"} | OPS_ESPACIAIS
FUNCOES_PERMITIDAS = {"now_menos_dias"}

TIPOS_NUMERICOS = {"integer", "bigint", "smallint", "double precision", "real", "numeric"}
TIPOS_TEMPORAIS = {"date", "timestamp", "timestamp with time zone", "timestamp without time zone"}
TIPOS_BOOLEANOS = {"boolean"}
TIPOS_GEOMETRICOS = {"geometry"}

GEOJSON_TIPOS = {
    "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection",
}


# =================================================================== 1. validação de estrutura/vocabulário
def _validar_estrutura(no: Any, profundidade: int, contador: dict) -> None:
    if not isinstance(no, dict):
        raise ErroWhere("sintaxe_invalida", "cada nó CQL2 é um objeto {\"op\": ..., \"args\": [...]}")
    op = no.get("op")
    if not isinstance(op, str) or not op:
        raise ErroWhere("sintaxe_invalida", "nó sem 'op' (string)")
    if op in OPS_LOGICOS:
        if profundidade > MAX_PROFUNDIDADE:
            raise ErroWhere(
                "expressao_complexa", f"aninhamento AND/OR acima de {MAX_PROFUNDIDADE} níveis", {"op": op}
            )
        args = no.get("args")
        if not isinstance(args, list) or len(args) < 2:
            raise ErroWhere("sintaxe_invalida", f"'{op}' exige 'args' como lista com 2 ou mais elementos")
        for a in args:
            _validar_estrutura(a, profundidade + 1, contador)
        return
    if op in OPS_FOLHA:
        contador["n"] += 1
        if contador["n"] > MAX_CLAUSULAS:
            raise ErroWhere("expressao_complexa", f"mais de {MAX_CLAUSULAS} cláusulas de comparação")
        args = no.get("args")
        if not isinstance(args, list):
            raise ErroWhere("sintaxe_invalida", f"'{op}' exige 'args' como lista")
        for a in args:
            _validar_valor_ou_propriedade(a)
        return
    raise ErroWhere("operador_nao_permitido", f"operador não permitido: {op!r}", {"op": op})


def _validar_valor_ou_propriedade(v: Any) -> None:
    """Varre um argumento à procura de `function` não whitelisted — o único lugar onde texto livre
    do cliente poderia nomear algo executável. Listas (para `in`) são varridas item a item."""
    if isinstance(v, list):
        if len(v) > MAX_IN:
            raise ErroWhere("expressao_complexa", f"lista de 'in' com mais de {MAX_IN} valores")
        for item in v:
            _validar_valor_ou_propriedade(item)
        return
    if not isinstance(v, dict):
        return  # número, string, bool, None: literal, nada a validar aqui
    if "property" in v:
        if not isinstance(v["property"], str) or not v["property"]:
            raise ErroWhere("sintaxe_invalida", "'property' precisa ser uma string não vazia")
        return
    if "function" in v:
        fn = v.get("function")
        nome = fn.get("name") if isinstance(fn, dict) else None
        if nome not in FUNCOES_PERMITIDAS:
            raise ErroWhere("operador_nao_permitido", f"função não permitida: {nome!r}", {"funcao": nome})
        return
    # qualquer outro objeto (geometria GeoJSON de s_intersects/s_dwithin, válida ou não) é deixado para
    # `compilar_cql2`, que sabe qual operador está pedindo geometria e devolve `tipo_invalido` — aqui
    # só barramos o único vetor de execução (`function` fora da lista branca), nunca a forma do literal.


# =================================================================== 2. compilação em SQL parametrizado
def _normalizar_colunas(colunas: dict) -> dict:
    norm = {}
    for nome, info in colunas.items():
        if isinstance(info, str):
            norm[nome] = {"sql": info, "tipo": "text"}
        else:
            norm[nome] = dict(info)
    return norm


def _tipo_de(info: dict) -> str:
    return (info.get("tipo") or "text").lower()


def _checar_tipo_literal(info: dict, valor: Any) -> None:
    if isinstance(valor, dict):
        return  # function — já validada em _validar_valor_ou_propriedade
    if valor is None:
        return
    tipo = _tipo_de(info)
    if tipo in TIPOS_NUMERICOS:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroWhere("tipo_invalido", f"valor não numérico para campo numérico: {valor!r}", {"valor": valor})
    elif tipo in TIPOS_TEMPORAIS:
        if not isinstance(valor, str) or _parse_temporal(valor) is None:
            raise ErroWhere("tipo_invalido", f"data/hora inválida (ISO 8601): {valor!r}", {"valor": valor})
    elif tipo in TIPOS_BOOLEANOS:
        if not isinstance(valor, bool):
            raise ErroWhere("tipo_invalido", f"valor não booleano para campo booleano: {valor!r}", {"valor": valor})
    else:
        if not isinstance(valor, str):
            raise ErroWhere("tipo_invalido", f"valor não texto para campo de texto: {valor!r}", {"valor": valor})


def _parse_temporal(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _validar_geojson(g: Any) -> dict:
    if not isinstance(g, dict) or g.get("type") not in GEOJSON_TIPOS:
        raise ErroWhere("tipo_invalido", "geometria GeoJSON inválida (campo 'type' ausente ou desconhecido)")
    if g.get("type") != "GeometryCollection" and "coordinates" not in g:
        raise ErroWhere("tipo_invalido", "geometria GeoJSON sem 'coordinates'")
    return g


def compilar_cql2(no: dict, colunas: dict) -> ConsultaSQL:
    """`no` já é o objeto Python (json.loads do corpo do pedido). `colunas` é a lista branca do
    CHAMADOR — nunca descoberta a partir do pedido. Levanta `ErroWhere` (a rota converte em 422)."""
    contador = {"n": 0}
    _validar_estrutura(no, 1, contador)
    colunas_ok = _normalizar_colunas(colunas)
    params: list = []

    def propriedade(node: Any) -> tuple[str, dict]:
        if not (isinstance(node, dict) and "property" in node):
            raise ErroWhere("sintaxe_invalida", "esperava {'property': campo}", {"obtido": node})
        campo = node["property"]
        info = colunas_ok.get(campo)
        if info is None:
            raise ErroWhere("campo_nao_permitido", f"campo não está na lista branca: {campo}", {"campo": campo})
        return campo, info

    def marcador_de(info: dict, valor: Any) -> str:
        if isinstance(valor, dict) and "function" in valor:
            fn = valor["function"]
            nome = fn.get("name")
            fargs = fn.get("args") or []
            if nome == "now_menos_dias":
                if len(fargs) != 1 or isinstance(fargs[0], bool) or not isinstance(fargs[0], (int, float)):
                    raise ErroWhere("tipo_invalido", "now_menos_dias espera 1 argumento numérico (dias)")
                params.append(int(fargs[0]))
                return "(now() - make_interval(days => %s))"
            raise ErroWhere(  # pragma: no cover
                "operador_nao_permitido", f"função não permitida: {nome!r}", {"funcao": nome})
        _checar_tipo_literal(info, valor)
        params.append(valor)
        return "%s"

    def visitar(nodo: dict) -> str:
        op = nodo["op"]
        if op in OPS_LOGICOS:
            partes = [visitar(a) for a in nodo["args"]]
            juntor = " AND " if op == "and" else " OR "
            return "(" + juntor.join(partes) + ")"
        args = nodo.get("args") or []
        if op == "isNull":
            if len(args) != 1:
                raise ErroWhere("sintaxe_invalida", "isNull espera 1 argumento")
            _campo, info = propriedade(args[0])
            return f"{info['sql']} IS NULL"
        if op == "in":
            if len(args) != 2 or not isinstance(args[1], list) or not args[1]:
                raise ErroWhere("sintaxe_invalida", "in espera [{'property': campo}, lista não vazia]")
            _campo, info = propriedade(args[0])
            marcadores = ", ".join(marcador_de(info, v) for v in args[1])
            return f"{info['sql']} IN ({marcadores})"
        if op == "like":
            if len(args) != 2:
                raise ErroWhere("sintaxe_invalida", "like espera 2 argumentos")
            _campo, info = propriedade(args[0])
            if _tipo_de(info) not in ("text",) and _tipo_de(info) not in TIPOS_NUMERICOS:
                pass  # like em qualquer coluna: comparação é feita por texto (cast na expressão SQL)
            if not isinstance(args[1], str):
                raise ErroWhere("tipo_invalido", "padrão do 'like' precisa ser texto", {"valor": args[1]})
            params.append(args[1])
            return f"{info['sql']}::text ILIKE %s"
        if op in OPS_COMPARACAO:
            if len(args) != 2:
                raise ErroWhere("sintaxe_invalida", f"'{op}' espera 2 argumentos")
            _campo, info = propriedade(args[0])
            marcador = marcador_de(info, args[1])
            sql_op = "!=" if op == "<>" else op
            return f"{info['sql']} {sql_op} {marcador}"
        if op in OPS_ESPACIAIS:
            if _campo_espacial_invalido(args):
                raise ErroWhere("sintaxe_invalida", f"'{op}' espera [{{'property': campo_geometria}}, geometria, ...]")
            _campo, info = propriedade(args[0])
            if _tipo_de(info) not in TIPOS_GEOMETRICOS:
                raise ErroWhere("tipo_invalido", f"'{op}' só em campo de geometria: {_campo}", {"campo": _campo})
            geom = _validar_geojson(args[1])
            srid_coluna = int(info.get("srid") or 4326)
            params.append(json.dumps(geom))
            expr_geom = f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), {srid_coluna})"
            if op == "s_intersects":
                if len(args) != 2:
                    raise ErroWhere("sintaxe_invalida", "s_intersects espera 2 argumentos")
                return f"ST_Intersects({info['sql']}, {expr_geom})"
            # s_dwithin: distância medida em metros sobre geography (esférica), não em unidade do SRID
            if len(args) != 3 or isinstance(args[2], bool) or not isinstance(args[2], (int, float)):
                raise ErroWhere("sintaxe_invalida", "s_dwithin espera [propriedade, geometria, distância em metros]")
            params.append(float(args[2]))
            return f"ST_DWithin({info['sql']}::geography, ({expr_geom})::geography, %s)"
        raise ErroWhere("operador_nao_permitido", f"operador não permitido: {op!r}", {"op": op})  # pragma: no cover

    sql = visitar(no)
    return ConsultaSQL(sql, params)


def _campo_espacial_invalido(args: list) -> bool:
    return not args or not (isinstance(args[0], dict) and "property" in args[0])


def compilar(no: dict, colunas: dict) -> ConsultaSQL:
    """Alias curto, mesmo nome de `where_ast.compilar` — comodidade para quem importa os dois módulos."""
    return compilar_cql2(no, colunas)


def contar_clausulas(no: dict) -> int:
    """Só para teste/diagnóstico: valida e devolve quantas cláusulas de comparação o filtro tem."""
    contador = {"n": 0}
    _validar_estrutura(no, 1, contador)
    return contador["n"]
