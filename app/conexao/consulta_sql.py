"""Consulta SQL do cliente sobre o banco externo dele (item L6-02-j-bancos-externos; "query layer" do Esri /
"SQL view" do GeoServer, decisão B8 do L3L6_CONCEITO: "SELECT com lista branca, LIMIT obrigatório, sem DDL/DML").

Fechada por construção, em quatro camadas — nenhuma delas sozinha bastaria:
  1. FORMA: um único comando, começa por SELECT, sem `;`, sem comentário (`--`, `/*`), sem `$$`, sem
     função de sistema/tempo/arquivo/rede (pg_sleep, pg_read_file, lo_import, dblink, a família pg_ls_*,
     copy...) e, mais forte, NENHUMA função fora da lista branca `FUNCOES_PERMITIDAS` (+ prefixo `st_` do
     PostGIS) — inclusive na lista de projeção, que antes não era conferida por lista nenhuma; sem
     palavra de escrita (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/GRANT/REVOKE/CALL/DO/SET/LOCK/
     VACUUM/REINDEX/CLUSTER/REFRESH, FOR UPDATE/SHARE) — em qualquer posição, inclusive dentro de subconsulta ou CTE.
  2. LISTA BRANCA: toda tabela citada depois de FROM/JOIN tem de estar entre as tabelas do schema remoto
     que a conexão lista (`pgfdw.listar_tabelas`); nome com schema só se for o schema da conexão.
  3. LIMIT obrigatório e explícito, <= `CONEXAO_PG_CONSULTA_LINHAS_MAX`; sem LIMIT a consulta é recusada
     ANTES de tocar o banco (refutação: "consulta sem LIMIT em tabela de 100 mi de linhas").
  4. EXECUÇÃO: conexão `readonly=True` com `statement_timeout` (o mesmo `pgfdw.conectar`), cursor com
     `fetchmany` até o LIMIT, tempo medido e devolvido.
O que passa por aqui é texto do cliente sobre o banco DELE (nunca o nosso): a lista branca e o read-only são
o que impede que a conexão registrada vire um canal para o resto do banco do cliente."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import psycopg2

from app import limites
from app.conexao import pgfdw

_RE_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\s*(?:OFFSET\s+\d+\s*)?$", re.I)
_RE_IDENT = re.compile(r'(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))(?:\s*\.\s*(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*)))?')
_RE_FROM = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)(?:\s*\.\s*(?:\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*))?)", re.I
)
PALAVRAS_PROIBIDAS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "call", "do",
    "set", "lock", "share", "vacuum", "reindex", "cluster", "refresh", "copy", "execute", "prepare", "deallocate",
    "listen", "notify", "load", "security", "into",
)
FUNCOES_PROIBIDAS = (
    # `pg_ls_` cobre a FAMÍLIA inteira de listagem de diretório do servidor (pg_ls_dir, pg_ls_logdir,
    # pg_ls_waldir, pg_ls_tmpdir, pg_ls_archive_statusdir e as que vierem): era o buraco que o adversário
    # T9 da linha L6 mostrou no item L6-02-j.
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_", "pg_ls_dir", "pg_stat_file", "lo_import",
    "lo_export", "dblink", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "current_setting",
    "set_config", "pg_advisory", "txid_", "pg_notify", "query_to_xml", "xmlparse", "pg_exec",
)

# Camada 1b — LISTA BRANCA DE FUNÇÃO. O denylist acima só barra o que já se sabe perigoso; num Postgres do
# cliente com extensão instalada (pgsql-http, uma UDF da casa dele, dblink com outro nome) qualquer função
# na lista de PROJEÇÃO passava, porque a lista branca do módulo só olhava tabela depois de FROM/JOIN. Aqui a
# regra vira a mesma das tabelas: só passa o que está declarado. Tudo que é PostGIS (`st_`) entra por
# prefixo; o resto é esta lista de funções de leitura pura do SQL.
FUNCOES_PERMITIDAS = frozenset({
    # agregação e janela
    "count", "sum", "avg", "min", "max", "array_agg", "string_agg", "json_agg", "jsonb_agg", "bool_and",
    "bool_or", "every", "stddev", "stddev_pop", "stddev_samp", "variance", "var_pop", "var_samp",
    "percentile_cont", "percentile_disc", "mode", "corr", "row_number", "rank", "dense_rank", "ntile",
    "lag", "lead", "first_value", "last_value", "nth_value", "cume_dist", "percent_rank",
    # texto
    "lower", "upper", "initcap", "length", "char_length", "character_length", "octet_length", "substr",
    "substring", "trim", "btrim", "ltrim", "rtrim", "replace", "split_part", "concat", "concat_ws",
    "lpad", "rpad", "position", "strpos", "regexp_replace", "regexp_match", "regexp_matches",
    "regexp_split_to_array", "format", "md5", "sha256", "encode", "decode", "translate", "repeat",
    "starts_with", "reverse", "quote_literal", "quote_ident", "chr", "ascii", "to_ascii", "unaccent",
    "similarity", "levenshtein", "soundex", "metaphone",
    # número
    "abs", "ceil", "ceiling", "floor", "round", "trunc", "mod", "div", "power", "sqrt", "cbrt", "exp",
    "ln", "log", "log10", "sign", "greatest", "least", "width_bucket", "random", "degrees", "radians",
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "pi", "numeric", "int4", "int8", "float8",
    # data e hora (cálculo sobre valor; relógio de sessão não muda nada que possa vazar)
    "date_trunc", "date_part", "extract", "age", "to_char", "to_date", "to_timestamp", "to_number",
    "make_date", "make_time", "make_timestamp", "make_interval", "justify_days", "justify_hours", "date",
    # conversão, nulos, JSON e array
    "cast", "coalesce", "nullif", "to_json", "to_jsonb", "json_build_object", "jsonb_build_object",
    "json_build_array", "jsonb_build_array", "row_to_json", "json_agg", "json_extract_path",
    "json_extract_path_text", "jsonb_extract_path", "jsonb_extract_path_text", "jsonb_array_elements",
    "json_array_elements", "jsonb_array_length", "json_array_length", "jsonb_object_keys", "array_length",
    "array_position", "array_remove", "array_append", "array_cat", "array_to_string", "string_to_array",
    "unnest", "cardinality", "generate_series", "bool", "text", "varchar",
    # tipos geográficos que não começam por st_
    "geometry", "geography", "box2d", "box3d", "postgis_version",
})
PREFIXOS_FUNCAO_PERMITIDOS = ("st_",)
# palavras da própria linguagem que aparecem antes de '(' e não são chamada de função
_NAO_E_FUNCAO = frozenset({
    "select", "from", "where", "and", "or", "not", "in", "exists", "as", "on", "join", "inner", "left",
    "right", "full", "outer", "cross", "lateral", "union", "intersect", "except", "by", "group", "order",
    "having", "limit", "offset", "when", "then", "else", "case", "end", "all", "any", "some", "distinct",
    "values", "with", "is", "between", "like", "ilike", "similar", "over", "partition", "filter", "within",
    "using", "returning", "asc", "desc", "true", "false", "null", "array", "row", "interval", "recursive",
    "nulls", "first", "last", "tablesample", "ordinality", "unbounded", "preceding", "following", "current",
})


class ConsultaRecusada(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass
class ConsultaValidada:
    sql: str
    limite: int
    tabelas: list[str] = field(default_factory=list)


def _sem_strings(sql: str) -> str:
    """apaga o conteúdo das strings 'assim' (com '' dentro) para que as palavras dentro delas não contem."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validar(sql: str, tabelas_permitidas: set[str], schema_remoto: str) -> ConsultaValidada:
    texto = (sql or "").strip()
    if not texto:
        raise ConsultaRecusada("consulta_vazia", "consulta vazia")
    if len(texto) > limites.CONEXAO_PG_CONSULTA_TEXTO_MAX:
        raise ConsultaRecusada(
            "consulta_longa", f"consulta acima de {limites.CONEXAO_PG_CONSULTA_TEXTO_MAX} caracteres"
        )
    if ";" in texto or "--" in texto or "/*" in texto or "$$" in texto or "\x00" in texto:
        raise ConsultaRecusada("consulta_recusada", "um comando só: sem ';', comentário ou bloco $$")
    limpo = _sem_strings(texto)
    if not re.match(r"^\s*(WITH\b|SELECT\b)", limpo, re.I):
        raise ConsultaRecusada("consulta_recusada", "só SELECT (ou WITH ... SELECT) é aceito")
    palavras = {p.lower() for p in re.findall(r"[A-Za-z_]+", limpo)}
    proibidas = sorted(palavras & set(PALAVRAS_PROIBIDAS))
    if proibidas:
        raise ConsultaRecusada(
            "consulta_recusada", f"palavra não permitida em consulta de leitura: {', '.join(proibidas)}"
        )
    baixo = limpo.lower()
    funcoes = [f for f in FUNCOES_PROIBIDAS if f in baixo]
    if funcoes:
        raise ConsultaRecusada("consulta_recusada", f"função de sistema não permitida: {', '.join(funcoes)}")
    chamadas = {c.lower() for c in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", limpo)}
    fora_da_lista = sorted(
        c for c in chamadas
        if c not in _NAO_E_FUNCAO
        and c not in FUNCOES_PERMITIDAS
        and not c.startswith(PREFIXOS_FUNCAO_PERMITIDOS)
    )
    if fora_da_lista:
        raise ConsultaRecusada(
            "consulta_recusada",
            "função fora da lista branca de leitura: " + ", ".join(fora_da_lista),
        )
    m = _RE_LIMIT.search(limpo)
    if not m:
        raise ConsultaRecusada(
            "limit_obrigatorio", "a consulta precisa terminar com LIMIT <n> (e opcionalmente OFFSET)"
        )
    limite = int(m.group(1))
    if limite < 1 or limite > limites.CONEXAO_PG_CONSULTA_LINHAS_MAX:
        raise ConsultaRecusada(
            "limit_acima_do_teto", f"LIMIT precisa estar entre 1 e {limites.CONEXAO_PG_CONSULTA_LINHAS_MAX}"
        )
    tabelas: list[str] = []
    ctes = {c.lower() for c in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", limpo, re.I)}
    for ref in _RE_FROM.findall(limpo):
        mi = _RE_IDENT.match(ref.strip())
        if not mi:
            raise ConsultaRecusada("consulta_recusada", f"referência de tabela ilegível: {ref!r}")
        a, b, c, d = mi.groups()
        esquema, tabela = ((a or b), (c or d)) if (c or d) else (None, (a or b))
        if esquema and esquema.lower() != schema_remoto.lower():
            raise ConsultaRecusada("tabela_fora_da_lista", f"schema {esquema!r} não é o da conexão ({schema_remoto})")
        if tabela.lower() in ctes:
            continue
        if tabela not in tabelas_permitidas:
            raise ConsultaRecusada("tabela_fora_da_lista", f"tabela {tabela!r} não está entre as tabelas da conexão")
        tabelas.append(tabela)
    if not tabelas:
        raise ConsultaRecusada("consulta_recusada", "a consulta precisa ler ao menos uma tabela da conexão (FROM ...)")
    return ConsultaValidada(sql=texto, limite=limite, tabelas=tabelas)


def executar(alvo: pgfdw.AlvoPg, senha: str, consulta: ConsultaValidada) -> dict:
    """roda no banco do cliente, só leitura, com o statement_timeout de `pgfdw.conectar`; devolve colunas,
    linhas (no máximo `consulta.limite`) e o tempo. Nunca deixa a exceção crua do driver subir."""
    conn = pgfdw.conectar(alvo, senha)
    inicio = time.perf_counter()
    try:
        with conn.cursor() as cur:
            # autocommit (pgfdw.conectar): SET de sessão, e a conexão é fechada logo abaixo — SET LOCAL seria ignorado
            cur.execute(f"SET search_path TO {psycopg2.extensions.quote_ident(alvo.schema_remoto, cur)}, public")
            cur.execute(consulta.sql)
            colunas = [d.name for d in cur.description or []]
            linhas = cur.fetchmany(consulta.limite)
    except psycopg2.errors.QueryCanceled as e:
        raise ConsultaRecusada("tempo_esgotado", "a consulta passou do tempo máximo no banco do cliente") from e
    except psycopg2.Error as e:
        msg = (e.diag.message_primary or str(e)).splitlines()[0][:200] if getattr(e, "diag", None) else str(e)[:200]
        raise ConsultaRecusada("consulta_invalida", f"o banco do cliente recusou a consulta: {msg}") from e
    finally:
        conn.close()
    return {
        "colunas": colunas,
        "linhas": [[_json_ok(v) for v in r.values()] for r in linhas],
        "n": len(linhas),
        "limite": consulta.limite,
        "tabelas": consulta.tabelas,
        "tempo_ms": int((time.perf_counter() - inicio) * 1000),
    }


def _json_ok(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (bytes, memoryview)):
        return bytes(v).hex()
    return str(v)
