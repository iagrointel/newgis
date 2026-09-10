"""Portão do SQL livre do usuário sobre os Parquet do inquilino (item L2-15-b-consultas-duckdb-em-escala).

O SQL do usuário NUNCA nomeia arquivo: ele enxerga só as VIEWS que o motor injeta, uma por item de catálogo
tipo `parquet` que o chamador pode ler. Este módulo é a primeira das duas barreiras (a segunda é o próprio
motor do DuckDB, configurado em `duckdb_cli.py` com `enable_external_access=false` +
`allowed_directories` + `lock_configuration=true`; ver ADR do item):

1. **Só uma instrução, e só SELECT.** Quem decide isso é o próprio analisador do DuckDB, não uma expressão
   regular: `json_serialize_sql` devolve `{"error": true, "error_message": "Only SELECT statements can be
   serialized to json!"}` para INSERT, UPDATE, DELETE, COPY, CREATE, ATTACH, INSTALL, LOAD, PRAGMA, SET,
   EXPORT e CALL (MEDIDO em 08/09/2026 nesta instalação, DuckDB 1.5.5). Ou seja, a recusa dessas formas é
   consequência de o SQL nem chegar a ter árvore, e não de uma lista de palavras que alguém precisa manter.
2. **Função de tabela por lista branca.** Toda função que aparece na posição de tabela (`TABLE_FUNCTION` na
   árvore) tem de estar em `TABELAS_PERMITIDAS`. É por aqui que `read_parquet`, `read_csv`, `glob`,
   `parquet_scan`, `postgres_scan`, `iceberg_scan`, `ST_Read` e companhia caem — inclusive as que ainda não
   existem, porque a lista branca não precisa prever nome novo.
3. **Lista negra explícita de funções**, escalares inclusive, para o caso de alguma chegar por outro caminho
   que não a posição de tabela (por exemplo dentro de um `WHERE`). É redundante de propósito: nomeia, em um
   lugar só e por escrito, exatamente as famílias que o portão do item exige recusar.
4. **Relação por lista branca.** Todo `BASE_TABLE` tem de ser uma das views injetadas, sem qualificação de
   schema nem de catálogo — `SELECT * FROM outro_inquilino.v` e `SELECT * FROM system.x` param aqui.

O que este módulo NÃO promete: não é um verificador de custo nem de semântica. Consulta cara, cartesiana ou
absurda passa por aqui e é o teto de tempo/memória/linhas do `duckdb_cli` que a corta.
"""

from __future__ import annotations

import json

# Funções de TABELA aceitas. Nenhuma delas abre arquivo, rede ou catálogo externo: `range`/`generate_series`
# geram números, `unnest` abre uma lista que já está na linha, `values` é literal.
TABELAS_PERMITIDAS = frozenset({"range", "generate_series", "unnest", "values"})

# Lista negra por escrito (redundante com a lista branca acima; ver docstring, item 3). Nomes em minúscula.
NEGRA_ARQUIVO = frozenset({
    "read_parquet", "parquet_scan", "read_csv", "read_csv_auto", "csv_scan", "sniff_csv", "read_json",
    "read_json_auto", "read_json_objects", "read_ndjson", "read_ndjson_auto", "read_ndjson_objects",
    "read_text", "read_blob", "glob", "parquet_metadata", "parquet_schema", "parquet_file_metadata",
    "parquet_kv_metadata", "parquet_bloom_probe", "st_read", "st_read_meta", "st_readosm", "st_drivers",
})
NEGRA_REDE_E_CATALOGO = frozenset({
    "postgres_scan", "postgres_scan_pushdown", "postgres_query", "sqlite_scan", "sqlite_query", "mysql_scan",
    "mysql_query", "iceberg_scan", "iceberg_metadata", "iceberg_snapshots", "delta_scan", "duckdb_extensions",
    "load_extension", "install_extension", "read_gsheet", "shapefile_meta",
})
NEGRA = NEGRA_ARQUIVO | NEGRA_REDE_E_CATALOGO

MENSAGEM_SO_SELECT = (
    "só é aceita UMA instrução SELECT; COPY, CREATE, INSERT, ATTACH, INSTALL, LOAD, PRAGMA, SET e EXPORT "
    "são recusados"
)


class ErroSqlInseguro(ValueError):
    """SQL recusado pelo portão. `motivo` é um código estável; `mensagem` é o que o usuário lê."""

    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo = motivo
        self.mensagem = mensagem


class Analise:
    """Resultado da leitura da árvore: o que a consulta usa, já conferido."""

    def __init__(self, sql: str, relacoes: set[str], funcoes: set[str], tabelas: set[str]):
        self.sql = sql
        self.relacoes = relacoes
        self.funcoes = funcoes
        self.funcoes_de_tabela = tabelas

    def como_dicionario(self) -> dict:
        return {"relacoes": sorted(self.relacoes), "funcoes": sorted(self.funcoes),
                "funcoes_de_tabela": sorted(self.funcoes_de_tabela)}


def _arvore(sql: str) -> list:
    """Árvore das instruções, pelo analisador do próprio DuckDB. Levanta ErroSqlInseguro para o que não for
    SELECT (ver docstring do módulo, item 1)."""
    import duckdb  # importação tardia: quem só valida parâmetro de rota não paga o carregamento do motor

    con = duckdb.connect()
    try:
        cru = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
    except Exception as e:  # noqa: BLE001 — erro de sintaxe também chega aqui e é do usuário
        raise ErroSqlInseguro("sql_invalido", f"SQL não pôde ser lido: {str(e).splitlines()[0][:200]}") from e
    finally:
        con.close()
    dado = json.loads(cru)
    if dado.get("error"):
        mensagem = str(dado.get("error_message") or "")
        if "Only SELECT" in mensagem:
            raise ErroSqlInseguro("nao_e_select", MENSAGEM_SO_SELECT)
        raise ErroSqlInseguro("sql_invalido", f"SQL não pôde ser lido: {mensagem[:200]}")
    return dado.get("statements") or []


def _andar(no, relacoes: set[str], funcoes: set[str], tabelas: set[str], qualificadas: set[str]) -> None:
    if isinstance(no, dict):
        tipo = no.get("type")
        if tipo == "BASE_TABLE":
            nome = (no.get("table_name") or "").lower()
            if no.get("schema_name") or no.get("catalog_name"):
                qualificadas.add(".".join(x for x in (no.get("catalog_name"), no.get("schema_name"), nome) if x))
            relacoes.add(nome)
        elif tipo == "TABLE_FUNCTION":
            f = no.get("function") or {}
            nome = (f.get("function_name") or "").lower()
            tabelas.add(nome)
            if f.get("catalog") or f.get("schema"):
                qualificadas.add(".".join(x for x in (f.get("catalog"), f.get("schema"), nome) if x))
        if "function_name" in no and isinstance(no.get("function_name"), str):
            funcoes.add(no["function_name"].lower())
        for valor in no.values():
            _andar(valor, relacoes, funcoes, tabelas, qualificadas)
    elif isinstance(no, list):
        for valor in no:
            _andar(valor, relacoes, funcoes, tabelas, qualificadas)


def analisar(sql: str, relacoes_permitidas, *, tamanho_max: int) -> Analise:
    """Lê a árvore do SQL e recusa tudo o que a docstring do módulo lista. Devolve a Analise em caso de aceite.

    `relacoes_permitidas` são os nomes das views injetadas pelo motor (uma por item Parquet do inquilino);
    nomes de CTE declarados na própria consulta são aceitos além delas."""
    if not isinstance(sql, str) or not sql.strip():
        raise ErroSqlInseguro("sql_vazio", "consulta vazia")
    if len(sql) > tamanho_max:
        raise ErroSqlInseguro("sql_longo", f"a consulta passa de {tamanho_max} caracteres")
    if "\x00" in sql:
        raise ErroSqlInseguro("sql_invalido", "a consulta tem byte nulo")
    instrucoes = _arvore(sql)
    if len(instrucoes) != 1:
        raise ErroSqlInseguro("varias_instrucoes",
                              f"esperava UMA instrução, a consulta tem {len(instrucoes)}")
    relacoes: set[str] = set()
    funcoes: set[str] = set()
    tabelas: set[str] = set()
    qualificadas: set[str] = set()
    ctes: set[str] = set()
    _coletar_ctes(instrucoes[0], ctes)
    _andar(instrucoes[0], relacoes, funcoes, tabelas, qualificadas)
    if qualificadas:
        raise ErroSqlInseguro("relacao_qualificada",
                              "nome qualificado por schema ou catálogo não é aceito: "
                              + ", ".join(sorted(qualificadas)))
    proibidas = sorted((funcoes | tabelas) & NEGRA)
    if proibidas:
        raise ErroSqlInseguro("funcao_proibida",
                              "função proibida na consulta: " + ", ".join(proibidas)
                              + " — os arquivos do inquilino já estão publicados como views")
    fora = sorted(tabelas - TABELAS_PERMITIDAS)
    if fora:
        raise ErroSqlInseguro("funcao_de_tabela_proibida",
                              "só estas funções podem estar na posição de tabela: "
                              + ", ".join(sorted(TABELAS_PERMITIDAS)) + "; a consulta usa " + ", ".join(fora))
    permitidas = {str(r).lower() for r in relacoes_permitidas} | ctes
    desconhecidas = sorted(relacoes - permitidas)
    if desconhecidas:
        raise ErroSqlInseguro("relacao_desconhecida",
                              "relação fora do inquilino ou inexistente: " + ", ".join(desconhecidas)
                              + "; disponíveis: " + (", ".join(sorted(permitidas)) or "nenhuma"))
    return Analise(sql, relacoes, funcoes, tabelas)


def _coletar_ctes(no, ctes: set[str]) -> None:
    if isinstance(no, dict):
        mapa = no.get("cte_map")
        if isinstance(mapa, dict):
            for entrada in mapa.get("map") or []:
                chave = entrada.get("key")
                if isinstance(chave, str):
                    ctes.add(chave.lower())
        for valor in no.values():
            _coletar_ctes(valor, ctes)
    elif isinstance(no, list):
        for valor in no:
            _coletar_ctes(valor, ctes)


# ---------------------------------------------------------------- análise do PLANO (segunda leitura)
# Operadores físicos aceitos no plano da consulta já preparada. A lista existe porque a árvore de sintaxe não
# vê o que o otimizador põe no lugar de uma view: aqui se confere que a única forma de leitura que sobrou é a
# do Parquet que nós mesmos injetamos. Nome novo (READ_CSV, HTTPFS, POSTGRES_SCAN, ARROW_SCAN…) reprova.
OPERADORES_DE_LEITURA_PERMITIDOS = frozenset({
    "READ_PARQUET", "PARQUET_SCAN", "COLUMN_DATA_SCAN", "DUMMY_SCAN", "EMPTY_RESULT", "RANGE", "UNNEST",
})
_SUFIXOS_DE_LEITURA = ("_SCAN", "SCAN", "READ_", "GET")


def conferir_plano(plano_json: str) -> list[str]:
    """Devolve os operadores de leitura vistos no plano; levanta ErroSqlInseguro se algum estiver fora da
    lista. Recebe o texto do `EXPLAIN (FORMAT json)`."""
    vistos: list[str] = []

    def anda(no):
        if isinstance(no, dict):
            nome = str(no.get("name") or "").upper()
            funcao = str((no.get("extra_info") or {}).get("Function") or "").upper()
            for candidato in (nome, funcao):
                if candidato and (candidato.endswith(_SUFIXOS_DE_LEITURA) or candidato.startswith("READ_")):
                    vistos.append(candidato)
            for valor in no.values():
                anda(valor)
        elif isinstance(no, list):
            for valor in no:
                anda(valor)

    anda(json.loads(plano_json))
    fora = sorted({v for v in vistos if v not in OPERADORES_DE_LEITURA_PERMITIDOS})
    if fora:
        raise ErroSqlInseguro("plano_com_leitura_estranha",
                              "o plano da consulta lê por um caminho que não é o Parquet do inquilino: "
                              + ", ".join(fora))
    return sorted(set(vistos))
