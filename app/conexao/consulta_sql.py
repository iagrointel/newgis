"""Consulta SQL do cliente sobre o banco externo dele (item L6-02-j-bancos-externos; "query layer" do Esri /
"SQL view" do GeoServer, decisão B8 do L3L6_CONCEITO: "SELECT com lista branca, LIMIT obrigatório, sem DDL/DML").

Fechada por construção, em quatro camadas — nenhuma delas sozinha bastaria:
  1. FORMA: um único comando, começa por SELECT, sem `;`, sem comentário (`--`, `/*`), sem `$$`, sem
     função de sistema/tempo/arquivo/rede (pg_sleep, pg_read_file, lo_import, dblink, copy...), sem
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
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file", "lo_import", "lo_export",
    "dblink", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "current_setting", "set_config",
    "pg_advisory", "txid_", "pg_notify", "query_to_xml", "xmlparse", "pg_exec",
)


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
