"""CQL2 (OGC 21-065r2) — Part 3 do OGC API Features (item L2-04-g). Duas sintaxes de entrada, uma
gramática só, um único gerador de SQL parametrizado: reusa a mesma garantia de segurança do
`where_ast.py` (nenhum texto do cliente concatenado em SQL, literal sempre vira parâmetro `%s`),
mas com o vocabulário CQL2, não o dialeto "standardized queries" da Esri: operadores de
comparação, lógicos (and/or/not), `in`/`like`/`between`/`isNull`, espaciais
(`s_intersects`/`s_within`/`s_dwithin`) e temporais (`t_after`/`t_before`/`t_during`).

Duas etapas, como o `where_ast`:
1. `analisar_texto(texto)` (CQL2-text) ou usar o dict já pronto (CQL2-JSON) — produz a mesma AST.
2. `compilar(no, colunas_sql, srid_nativo)` — só aqui entra a lista BRANCA de colunas (nome no
   filtro → expressão SQL de confiança do chamador) e o SRID nativo da tabela (as funções
   espaciais recebem GeoJSON/WKT em 4326 por convenção CQL2 e são transformadas para o SRID da
   camada antes de comparar com a coluna `geom`).

`compilar_cql2(bruto, linguagem, colunas_sql, srid_nativo) -> (sql, params)` é o que um endpoint
deve chamar; aceita `filter-lang` = `cql2-text` (padrão) ou `cql2-json`.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_TEXTO = 4000
MAX_TOKENS = 400
MAX_PROFUNDIDADE = 20

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$")

_ESPACIAIS = {"s_intersects": "ST_Intersects", "s_within": "ST_Within", "s_dwithin": "ST_DWithin"}
_TEMPORAIS = {"t_after", "t_before", "t_during"}
_COMPARACAO = {"=", "<>", "!=", "<", "<=", ">", ">="}
_COMPARACAO_SQL = {"=": "=", "<>": "<>", "!=": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


class ErroCql2(Exception):
    def __init__(self, codigo: str, mensagem: str, detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# --------------------------------------------------------------------------- AST comum (JSON e text convergem aqui)
@dataclass
class Propriedade:
    nome: str


@dataclass
class Literal:
    valor: Any


@dataclass
class IntervaloAberto:
    """`../2026-01-01` ou `2026-01-01/..` — instante indeterminado de um lado (T_BEFORE/T_DURING)."""

    inicio: Any
    fim: Any


@dataclass
class Comparacao:
    op: str  # um de _COMPARACAO, "like", "between", "in", "is_null", "is_not_null"
    operando: Propriedade
    valor: Any = None
    valor2: Any = None  # between/in (lista)


@dataclass
class Espacial:
    op: str  # s_intersects|s_within|s_dwithin
    operando: Propriedade
    geometria: dict  # GeoJSON geometry dict
    distancia: float | None = None


@dataclass
class Temporal:
    op: str  # t_after|t_before|t_during
    operando: Propriedade
    valor: Any  # datetime/date ou IntervaloAberto


@dataclass
class E:
    termos: list = field(default_factory=list)


@dataclass
class Ou:
    termos: list = field(default_factory=list)


@dataclass
class Nao:
    termo: Any = None


# --------------------------------------------------------------------------- CQL2-text: tokenizador + parser
_TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<parenesq>\()|(?P<parendir>\))|(?P<virgula>,)|
        (?P<op><=|>=|<>|!=|=|<|>)|
        (?P<string>'(?:[^']|'')*')|
        (?P<numero>-?\d+(?:\.\d+)?)|
        (?P<palavra>[A-Za-z_][A-Za-z0-9_]*)
    )""",
    re.VERBOSE,
)
_PALAVRAS_LOGICAS = {"and", "or", "not"}
_PALAVRAS_FUNC = set(_ESPACIAIS) | _TEMPORAIS | {"in", "like", "between", "is", "null", "casei", "true", "false"}


def _tokenizar(texto: str) -> list[str]:
    if len(texto) > MAX_TEXTO:
        raise ErroCql2("filtro_grande_demais", f"filtro CQL2 acima de {MAX_TEXTO} caracteres")
    pos = 0
    tokens: list[str] = []
    while pos < len(texto):
        m = _TOKEN_RE.match(texto, pos)
        if not m or m.end() == pos:
            resto = texto[pos:].strip()
            if not resto:
                break
            raise ErroCql2("filtro_sintaxe", f"token inválido em CQL2-text: {resto[:30]!r}")
        tokens.append(m.group().strip())
        pos = m.end()
        if len(tokens) > MAX_TOKENS:
            raise ErroCql2("filtro_grande_demais", f"filtro CQL2 com mais de {MAX_TOKENS} tokens")
    return [t for t in tokens if t]


class _AnalisadorTexto:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.i = 0
        self.profundidade = 0

    def _olhar(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _tomar(self) -> str:
        if self.i >= len(self.tokens):
            raise ErroCql2("filtro_sintaxe", "fim inesperado do filtro CQL2")
        t = self.tokens[self.i]
        self.i += 1
        return t

    def _esperar(self, palavra: str) -> None:
        t = self._tomar()
        if t.lower() != palavra:
            raise ErroCql2("filtro_sintaxe", f"esperava {palavra!r}, veio {t!r}")

    def analisar(self):
        no = self._expr()
        if self.i != len(self.tokens):
            raise ErroCql2("filtro_sintaxe", f"sobrou texto após o filtro: {self.tokens[self.i:]!r}")
        return no

    def _expr(self):
        termos = [self._termo_and()]
        while self._olhar() and self._olhar().lower() == "or":
            self._tomar()
            termos.append(self._termo_and())
        return termos[0] if len(termos) == 1 else Ou(termos)

    def _termo_and(self):
        termos = [self._termo_not()]
        while self._olhar() and self._olhar().lower() == "and":
            self._tomar()
            termos.append(self._termo_not())
        return termos[0] if len(termos) == 1 else E(termos)

    def _termo_not(self):
        if self._olhar() and self._olhar().lower() == "not":
            self._tomar()
            return Nao(self._termo_not())
        return self._primario()

    def _primario(self):
        if self._olhar() == "(":
            self.profundidade += 1
            if self.profundidade > MAX_PROFUNDIDADE:
                raise ErroCql2("filtro_profundo_demais", f"parênteses aninhados acima de {MAX_PROFUNDIDADE}")
            self._tomar()
            no = self._expr()
            if self._olhar() != ")":
                raise ErroCql2("filtro_sintaxe", "parêntese não fechado")
            self._tomar()
            self.profundidade -= 1
            return no
        return self._comparacao()

    def _campo(self) -> Propriedade:
        t = self._tomar()
        if not IDENT_RE.match(t):
            raise ErroCql2("filtro_sintaxe", f"nome de propriedade inválido: {t!r}")
        return Propriedade(t)

    def _valor(self):
        t = self._olhar()
        if t is None:
            raise ErroCql2("filtro_sintaxe", "valor ausente no filtro CQL2")
        if t.startswith("'"):
            self._tomar()
            return t[1:-1].replace("''", "'")
        if re.match(r"^-?\d", t):
            self._tomar()
            return float(t) if "." in t else int(t)
        if t.lower() in ("true", "false"):
            self._tomar()
            return t.lower() == "true"
        # DATE('...')/TIMESTAMP('...')/TIMESTAMP('../2026-01-01') funções literais de instante
        if t.lower() in ("date", "timestamp", "interval"):
            self._tomar()
            self._esperar("(")
            bruto = self._tomar()
            if not bruto.startswith("'"):
                raise ErroCql2("filtro_sintaxe", f"{t}() exige literal de texto entre parênteses")
            self._esperar(")")
            return _instante(bruto[1:-1].replace("''", "'"))
        raise ErroCql2("filtro_sintaxe", f"valor não reconhecido em CQL2-text: {t!r}")

    def _lista_valores(self) -> list:
        self._esperar("(")
        vs = [self._valor()]
        while self._olhar() == ",":
            self._tomar()
            vs.append(self._valor())
        if self._olhar() != ")":
            raise ErroCql2("filtro_sintaxe", "lista de valores sem fechar")
        self._tomar()
        return vs

    def _geometria_literal(self) -> dict:
        """CQL2-text não define um dialeto próprio de geometria fora do BNF de WKT; esta
        implementação aceita GeoJSON entre aspas simples (dialeto aceito pelo pygeofilter e mais
        simples de compor com o resto da API, que já fala GeoJSON em toda parte)."""
        t = self._tomar()
        if not t.startswith("'"):
            raise ErroCql2("filtro_sintaxe", "geometria em função espacial precisa vir entre aspas simples (GeoJSON)")
        bruto = t[1:-1].replace("''", "'")
        try:
            return json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErroCql2("filtro_geometria_invalida", "geometria da função espacial não é GeoJSON válido") from e

    def _comparacao(self):
        if self._olhar() and self._olhar().lower() in _ESPACIAIS:
            fname = self._tomar().lower()
            self._esperar("(")
            campo = self._campo()
            self._esperar(",")
            geom = self._geometria_literal()
            dist = None
            if fname == "s_dwithin":
                self._esperar(",")
                dv = self._valor()
                if not isinstance(dv, (int, float)):
                    raise ErroCql2("filtro_sintaxe", "S_DWITHIN exige distância numérica (metros)")
                dist = float(dv)
            self._esperar(")")
            return Espacial(fname, campo, geom, dist)
        if self._olhar() and self._olhar().lower() in _TEMPORAIS:
            fname = self._tomar().lower()
            self._esperar("(")
            campo = self._campo()
            self._esperar(",")
            v = self._valor()
            self._esperar(")")
            return Temporal(fname, campo, v)
        campo = self._campo()
        t = self._olhar()
        if t is None:
            raise ErroCql2("filtro_sintaxe", "comparação incompleta")
        tl = t.lower()
        if tl == "is":
            self._tomar()
            neg = False
            if self._olhar() and self._olhar().lower() == "not":
                self._tomar()
                neg = True
            self._esperar("null")
            return Comparacao("is_not_null" if neg else "is_null", campo)
        if tl == "not" and self.i + 1 < len(self.tokens) and self.tokens[self.i + 1].lower() in ("in", "like",
            "between"):
            self._tomar()
            no = self._comparacao_pos(campo)
            return Nao(no)
        return self._comparacao_pos(campo)

    def _comparacao_pos(self, campo: Propriedade):
        t = self._olhar()
        tl = (t or "").lower()
        if tl == "in":
            self._tomar()
            return Comparacao("in", campo, self._lista_valores())
        if tl == "like":
            self._tomar()
            return Comparacao("like", campo, self._valor())
        if tl == "between":
            self._tomar()
            v1 = self._valor()
            self._esperar("and")
            v2 = self._valor()
            return Comparacao("between", campo, v1, v2)
        if t in _COMPARACAO:
            op = self._tomar()
            return Comparacao(op, campo, self._valor())
        raise ErroCql2("filtro_sintaxe", f"operador não reconhecido após propriedade: {t!r}")


def _instante(texto: str):
    """Converte um literal de data/hora CQL2, aceitando `../X` e `X/..` (instante indeterminado —
    portão exige que `T_BEFORE`/`T_DURING` aceitem aberto de um lado)."""
    if "/" in texto:
        a, b = texto.split("/", 1)
        return IntervaloAberto(None if a in ("..", "") else _instante(a), None if b in ("..", "") else _instante(b))
    if _DATE_RE.match(texto):
        return datetime.date.fromisoformat(texto)
    if _TIMESTAMP_RE.match(texto):
        t = texto.rstrip("Z").replace(" ", "T")
        try:
            return datetime.datetime.fromisoformat(t)
        except ValueError as e:
            raise ErroCql2("filtro_data_invalida", f"instante inválido: {texto!r}") from e
    raise ErroCql2("filtro_data_invalida", f"instante não reconhecido (use ISO 8601): {texto!r}")


def analisar_texto(texto: str):
    tokens = _tokenizar(texto)
    return _AnalisadorTexto(tokens).analisar()


# --------------------------------------------------------------------------- CQL2-JSON: dict -> AST comum
def _json_valor(v):
    if isinstance(v, dict):
        if "property" in v:
            return Propriedade(v["property"])
        if "date" in v:
            return datetime.date.fromisoformat(v["date"])
        if "timestamp" in v:
            return _instante(v["timestamp"])
        if "interval" in v and isinstance(v["interval"], list) and len(v["interval"]) == 2:
            a, b = v["interval"]
            return IntervaloAberto(
                None if a in ("..", None) else _json_valor(a), None if b in ("..", None) else _json_valor(b)
            )
        if v.get("type"):  # GeoJSON geometry
            return v
        raise ErroCql2("filtro_sintaxe", f"objeto CQL2-JSON não reconhecido: {v!r}")
    return v


def analisar_json(no: dict, profundidade: int = 0):
    if profundidade > MAX_PROFUNDIDADE:
        raise ErroCql2("filtro_profundo_demais", f"CQL2-JSON aninhado acima de {MAX_PROFUNDIDADE}")
    if not isinstance(no, dict) or "op" not in no:
        raise ErroCql2("filtro_sintaxe", "CQL2-JSON precisa de {'op':..., 'args':[...]} em cada nó")
    op = str(no["op"]).lower()
    args = no.get("args")
    if not isinstance(args, list):
        raise ErroCql2("filtro_sintaxe", "CQL2-JSON: 'args' precisa ser lista")
    if op == "and":
        return E([analisar_json(a, profundidade + 1) for a in args])
    if op == "or":
        return Ou([analisar_json(a, profundidade + 1) for a in args])
    if op == "not":
        if len(args) != 1:
            raise ErroCql2("filtro_sintaxe", "'not' exige exatamente 1 argumento")
        return Nao(analisar_json(args[0], profundidade + 1))
    if op in _ESPACIAIS:
        if len(args) not in (2, 3):
            raise ErroCql2("filtro_sintaxe", f"{op} exige 2 ou 3 argumentos")
        campo = _json_valor(args[0])
        geom = _json_valor(args[1])
        if not isinstance(campo, Propriedade) or not isinstance(geom, dict):
            raise ErroCql2("filtro_sintaxe", f"{op}: argumentos precisam ser (propriedade, geometria[, distância])")
        dist = float(args[2]) if len(args) == 3 else None
        return Espacial(op, campo, geom, dist)
    if op in _TEMPORAIS:
        if len(args) != 2:
            raise ErroCql2("filtro_sintaxe", f"{op} exige 2 argumentos")
        campo = _json_valor(args[0])
        if not isinstance(campo, Propriedade):
            raise ErroCql2("filtro_sintaxe", f"{op}: primeiro argumento precisa ser propriedade")
        return Temporal(op, campo, _json_valor(args[1]))
    if op == "isnull":
        campo = _json_valor(args[0])
        return Comparacao("is_null", campo)
    if op == "between":
        campo = _json_valor(args[0])
        lo = _json_valor(args[1])
        hi = _json_valor(args[2])
        return Comparacao("between", campo, lo, hi)
    if op == "in":
        campo = _json_valor(args[0])
        lista = args[1] if isinstance(args[1], list) else args[1:]
        return Comparacao("in", campo, [_json_valor(x) for x in lista])
    if op == "like":
        campo = _json_valor(args[0])
        return Comparacao("like", campo, _json_valor(args[1]))
    if op in _COMPARACAO:
        if len(args) != 2:
            raise ErroCql2("filtro_sintaxe", f"{op} exige 2 argumentos")
        a, b = _json_valor(args[0]), _json_valor(args[1])
        if isinstance(a, Propriedade):
            return Comparacao(op, a, b)
        if isinstance(b, Propriedade):
            return Comparacao(_inverter_op(op), b, a)
        raise ErroCql2("filtro_sintaxe", f"{op} precisa de ao menos um lado ser propriedade")
    raise ErroCql2("filtro_operador_desconhecido", f"operador CQL2-JSON não suportado: {op!r}")


def _inverter_op(op: str) -> str:
    return {"<": ">", "<=": ">=", ">": "<", ">=": "<="}.get(op, op)


# --------------------------------------------------------------------------- compilação -> SQL parametrizado
def _coluna_sql(campo: Propriedade, colunas_sql: dict) -> str:
    if campo.nome not in colunas_sql:
        raise ErroCql2("filtro_campo_desconhecido", f"propriedade inexistente nesta coleção: {campo.nome!r}",
                        {"campo": campo.nome})
    return colunas_sql[campo.nome]


def compilar(no, colunas_sql: dict, srid_nativo: int, coluna_geom_sql: str = "geom") -> tuple[str, list]:
    if isinstance(no, E):
        partes, params = [], []
        for t in no.termos:
            s, p = compilar(t, colunas_sql, srid_nativo, coluna_geom_sql)
            partes.append(f"({s})")
            params += p
        return " AND ".join(partes), params
    if isinstance(no, Ou):
        partes, params = [], []
        for t in no.termos:
            s, p = compilar(t, colunas_sql, srid_nativo, coluna_geom_sql)
            partes.append(f"({s})")
            params += p
        return " OR ".join(partes), params
    if isinstance(no, Nao):
        s, p = compilar(no.termo, colunas_sql, srid_nativo, coluna_geom_sql)
        return f"NOT ({s})", p
    if isinstance(no, Comparacao):
        return _compilar_comparacao(no, colunas_sql)
    if isinstance(no, Espacial):
        return _compilar_espacial(no, colunas_sql, srid_nativo, coluna_geom_sql)
    if isinstance(no, Temporal):
        return _compilar_temporal(no, colunas_sql)
    raise ErroCql2("filtro_sintaxe", f"nó de AST não reconhecido: {no!r}")


def _compilar_comparacao(no: Comparacao, colunas_sql: dict) -> tuple[str, list]:
    col = _coluna_sql(no.operando, colunas_sql)
    if no.op == "is_null":
        return f"{col} IS NULL", []
    if no.op == "is_not_null":
        return f"{col} IS NOT NULL", []
    if no.op == "in":
        if not isinstance(no.valor, list) or not no.valor:
            raise ErroCql2("filtro_sintaxe", "IN exige lista não vazia")
        return f"{col} = ANY(%s)", [list(no.valor)]
    if no.op == "like":
        return f"{col}::text LIKE %s", [str(no.valor)]
    if no.op == "between":
        return f"{col} BETWEEN %s AND %s", [no.valor, no.valor2]
    if no.op in _COMPARACAO:
        return f"{col} {_COMPARACAO_SQL[no.op]} %s", [no.valor]
    raise ErroCql2("filtro_sintaxe", f"operador de comparação não reconhecido: {no.op!r}")


def _compilar_espacial(no: Espacial, colunas_sql: dict, srid_nativo: int, coluna_geom_sql: str) -> tuple[str, list]:
    func = _ESPACIAIS[no.op]
    try:
        geojson_txt = json.dumps(no.geometria)
    except (TypeError, ValueError) as e:
        raise ErroCql2("filtro_geometria_invalida", "geometria da função espacial não é serializável") from e
    expr_geom = f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), {srid_nativo})"
    if no.op == "s_dwithin":
        if no.distancia is None or no.distancia < 0:
            raise ErroCql2("filtro_sintaxe", "S_DWITHIN exige distância >= 0 (metros)")
        # `::geography` presume SRID 4326 (WGS84) — a coluna nativa pode estar noutro SRID (ex. 4674),
        # então transforma ANTES de fundir os dois lados em geography, senão o Postgres recusa com
        # "mixed SRID geometries" (achado desta trilha: o teste de S_DWITHIN estourava exatamente aqui).
        return (
            f"ST_DWithin(ST_Transform({coluna_geom_sql}, 4326)::geography, "
            f"ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)::geography, %s)",
            [geojson_txt, no.distancia],
        )
    return f"{func}({coluna_geom_sql}, {expr_geom})", [geojson_txt]


def _compilar_temporal(no: Temporal, colunas_sql: dict) -> tuple[str, list]:
    col = _coluna_sql(no.operando, colunas_sql)
    v = no.valor
    if no.op == "t_after":
        if isinstance(v, IntervaloAberto):
            raise ErroCql2("filtro_sintaxe", "T_AFTER exige um instante só, não um intervalo")
        return f"{col} > %s", [v]
    if no.op == "t_before":
        if isinstance(v, IntervaloAberto):
            # T_BEFORE(campo, ../X) == campo < X; T_BEFORE(campo, X/..) não tem limite superior definido
            if v.fim is not None:
                return f"{col} < %s", [v.fim]
            raise ErroCql2("filtro_sintaxe", "T_BEFORE com intervalo sem limite superior não é comparável")
        return f"{col} < %s", [v]
    if no.op == "t_during":
        if not isinstance(v, IntervaloAberto):
            raise ErroCql2("filtro_sintaxe", "T_DURING exige um intervalo (a/b, com a ou b podendo ser '..')")
        partes, params = [], []
        if v.inicio is not None:
            partes.append(f"{col} >= %s")
            params.append(v.inicio)
        if v.fim is not None:
            partes.append(f"{col} <= %s")
            params.append(v.fim)
        if not partes:
            return "TRUE", []
        return " AND ".join(partes), params
    raise ErroCql2("filtro_sintaxe", f"operador temporal não reconhecido: {no.op!r}")


def compilar_cql2(
    bruto: str | dict, linguagem: str, colunas_sql: dict, srid_nativo: int, coluna_geom_sql: str = "geom"
) -> tuple[str, list]:
    """Ponto único de entrada: `linguagem` = 'cql2-text' (padrão) ou 'cql2-json'. Devolve
    `(sql, params)` pronto para entrar numa cláusula `WHERE` parametrizada — nunca texto do
    cliente concatenado."""
    lang = (linguagem or "cql2-text").lower()
    if lang == "cql2-json":
        no = analisar_json(bruto if isinstance(bruto, dict) else json.loads(bruto))
    elif lang == "cql2-text":
        no = analisar_texto(bruto if isinstance(bruto, str) else json.dumps(bruto))
    else:
        raise ErroCql2("filtro_lang_invalido", f"filter-lang não suportado: {linguagem!r} (use cql2-text/cql2-json)")
    return compilar(no, colunas_sql, srid_nativo, coluna_geom_sql)
