"""Motor de consulta grande sobre Parquet, num PROCESSO PRÓPRIO (item L2-15-b-consultas-duckdb-em-escala).

    python -m app.consulta_grande.duckdb_cli executar <plano.json>

Escreve UMA linha JSON em stdout e sai com 0; em erro, escreve a mensagem em stderr e sai com 1 (código 3
quando o motivo foi o teto de tempo, para a tarefa distinguir "cancelada por tempo" de "falhou").

**Por que processo próprio, de novo.** Pelo mesmo motivo medido no L0-04-h e repetido no L2-15-a: o filho que
roda um job é um FORK do worker e o DuckDB aborta (SIGABRT) depois de um fork. Aqui há um segundo motivo, mais
forte: é este processo, e só ele, que carrega o teto de memória do DuckDB. Se ele estourar, morre um processo
descartável — não o worker.

**O cofre.** A ordem dos ajustes importa e foi medida em 08/09/2026 nesta instalação (DuckDB 1.5.5):

1. `LOAD spatial` e a criação das VIEWS acontecem ANTES de fechar o cofre (com o acesso externo ainda ligado);
2. `SET allowed_directories=[...]` só pode ser mudado com o acesso externo LIGADO ("Cannot change
   allowed_directories when enable_external_access is disabled") e depois de a base subir ("Cannot change/set
   allowed_directories before the database is started") — ou seja, nem no `connect(config=...)` nem depois de
   desligar: tem de ser aqui, no meio;
3. `SET enable_external_access=false` fecha o sistema de arquivos e a rede, MENOS os diretórios da lista;
4. `SET lock_configuration=true` congela tudo: `SET enable_external_access=true` a partir daí devolve
   "Cannot change configuration option ... the configuration has been locked", e `SET allowed_directories`
   também. Não há caminho de volta dentro da sessão.

Com o cofre fechado, MEDIDO: `read_parquet` de caminho fora da lista, `read_csv('/etc/passwd')`,
`read_parquet('https://…')`, `ATTACH`, `INSTALL`, `LOAD` e `glob` devolvem PermissionException. O SQL do
usuário ainda passa antes pelo portão de `app.consulta_grande.seguranca`, que recusa essas formas na árvore
de sintaxe — as duas barreiras são independentes de propósito.

**Teto de tempo.** O DuckDB não tem `statement_timeout`. O corte é um `threading.Timer` que chama
`con.interrupt()`; o motor devolve `InterruptException` (MEDIDO: interrupção em 1,0 s de uma agregação sobre
`range(1e11)`), que vira a mensagem "a consulta passou do teto de N segundos e foi cancelada".

**Saída.** O resultado sai em DOIS arquivos no diretório de trabalho: um Parquet (para reabrir sem conversão)
e um CSV com a geometria em WKT (para a tarefa carregar no Postgres com `COPY ... FROM STDIN`, sem GDAL e sem
DuckDB no processo forkado). O teto de linhas é aplicado com `LIMIT teto + 1`: se voltar `teto + 1` linha, a
consulta é recusada em vez de entregar um resultado truncado em silêncio.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

from app.consulta_grande import seguranca

CODIGO_TEMPO = 3
# tipo do DuckDB -> tipo do Postgres na camada de destino. O que não estiver aqui vira `text` (o CSV já traz o
# valor como texto e o Postgres o aceita); GEOMETRY é tratado à parte, porque sai como WKT.
TIPOS_PG = {
    "BOOLEAN": "boolean", "TINYINT": "smallint", "SMALLINT": "smallint", "INTEGER": "integer",
    "BIGINT": "bigint", "HUGEINT": "numeric", "UTINYINT": "smallint", "USMALLINT": "integer",
    "UINTEGER": "bigint", "UBIGINT": "numeric", "FLOAT": "real", "DOUBLE": "double precision",
    "DECIMAL": "numeric", "VARCHAR": "text", "DATE": "date", "TIME": "time",
    "TIMESTAMP": "timestamp", "TIMESTAMP WITH TIME ZONE": "timestamptz", "UUID": "uuid",
}


class ErroTempo(RuntimeError):
    """A consulta passou do teto de tempo e foi interrompida."""


def _literal(valor: str) -> str:
    """Literal SQL de um texto que NÓS geramos (caminho de arquivo, nome de view). Aspa simples duplicada."""
    return "'" + str(valor).replace("'", "''") + "'"


def _identificador(nome: str) -> str:
    if not nome.replace("_", "").isalnum() or not nome[:1].isalpha():
        raise ValueError(f"nome de relação inválido: {nome!r}")
    return '"' + nome + '"'


def _conexao(plano: dict):
    import duckdb

    con = duckdb.connect()
    con.execute("LOAD spatial")
    con.execute(f"SET memory_limit='{max(192, int(plano['memoria_mb']))}MB'")
    con.execute(f"SET threads={max(1, int(plano['threads']))}")
    con.execute("SET preserve_insertion_order=false")
    for nome, caminhos in (plano.get("views") or {}).items():
        lista = "[" + ", ".join(_literal(c) for c in caminhos) + "]"
        con.execute(f"CREATE VIEW {_identificador(nome)} AS SELECT * FROM read_parquet({lista}, "
                    "union_by_name=true, hive_partitioning=true)")
    diretorios = "[" + ", ".join(_literal(d) for d in plano["diretorios"]) + "]"
    con.execute(f"SET allowed_directories={diretorios}")
    con.execute("SET autoinstall_known_extensions=false")
    con.execute("SET autoload_known_extensions=false")
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")  # daqui em diante nada do que está acima pode ser desfeito
    return con


def _colunas(con, sql_envolvido: str) -> list[dict]:
    desc = con.execute(f"SELECT * FROM ({sql_envolvido}) LIMIT 0").description
    return [{"nome": c[0], "tipo": str(c[1]).upper()} for c in desc]


def _tipo_pg(tipo_duckdb: str) -> str:
    """Tipo do Postgres para um tipo do DuckDB. O nome pode vir parametrizado (`DECIMAL(38,1)`,
    `VARCHAR(20)`, `TIMESTAMP WITH TIME ZONE`), então a busca é pelo nome exato e, falhando, pelo prefixo
    até o primeiro parêntese. O que não casa vira `text` — o CSV já traz o valor como texto."""
    nome = tipo_duckdb.upper().strip()
    if nome in TIPOS_PG:
        return TIPOS_PG[nome]
    return TIPOS_PG.get(nome.split("(")[0].strip(), "text")


def _e_geometria(tipo_duckdb: str) -> bool:
    """O DuckDB spatial declara a coluna como `GEOMETRY` ou `GEOMETRY('OGC:CRS84')` (o sistema de referência
    entra no nome do tipo quando o Parquet traz o metadado GeoParquet); as duas formas são geometria."""
    return tipo_duckdb.upper().startswith("GEOMETRY")


def _com_geometria_em_wkt(colunas: list[dict], sql: str) -> str:
    partes = []
    for c in colunas:
        alvo = _identificador(c["nome"]) if c["nome"].replace("_", "").isalnum() and c["nome"][:1].isalpha() \
            else '"' + c["nome"].replace('"', '""') + '"'
        partes.append(f"ST_AsText({alvo}) AS {alvo}" if _e_geometria(c["tipo"]) else alvo)
    return f"SELECT {', '.join(partes)} FROM ({sql})"


def executar(plano: dict) -> dict:
    tempo_s = int(plano["tempo_s"])
    linhas_max = int(plano["linhas_max"])
    con = _conexao(plano)
    relogio = None
    inicio = time.monotonic()
    try:
        analise = seguranca.analisar(plano["sql"], list((plano.get("views") or {}).keys()),
                                     tamanho_max=int(plano["sql_max"]))
        envolvido = f"SELECT * FROM ({analise.sql}) LIMIT {linhas_max + 1}"
        colunas = _colunas(con, envolvido)
        plano_json = con.execute(f"EXPLAIN (FORMAT json) {envolvido}").fetchone()[1]
        operadores = seguranca.conferir_plano(plano_json)

        relogio = threading.Timer(tempo_s, con.interrupt)
        relogio.daemon = True
        relogio.start()
        saida_parquet = plano["saida_parquet"]
        saida_csv = plano["saida_csv"]
        try:
            con.execute(f"CREATE TABLE _resultado AS {envolvido}")
        except Exception as e:  # noqa: BLE001 — a interrupção chega como exceção do motor
            if "INTERRUPT" in str(e).upper() or type(e).__name__ == "InterruptException":
                raise ErroTempo(f"a consulta passou do teto de {tempo_s} segundos e foi cancelada") from e
            raise
        relogio.cancel()
        linhas = int(con.execute("SELECT count(*) FROM _resultado").fetchone()[0])
        if linhas > linhas_max:
            raise RuntimeError(f"a consulta devolveu mais de {linhas_max} linhas; refine o filtro ou agregue "
                               "(o teto de linhas de saída é declarado em app/limites.py)")
        con.execute(f"COPY _resultado TO {_literal(saida_parquet)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        con.execute(f"COPY ({_com_geometria_em_wkt(colunas, 'SELECT * FROM _resultado')}) TO "
                    f"{_literal(saida_csv)} (FORMAT CSV, HEADER true, DELIMITER ',')")
        campos = [{"nome": c["nome"], "tipo_duckdb": c["tipo"],
                   "tipo": "geometry" if _e_geometria(c["tipo"]) else _tipo_pg(c["tipo"])}
                  for c in colunas]
        return {
            "linhas": linhas, "campos": campos, "ms": int((time.monotonic() - inicio) * 1000),
            "saida_parquet": saida_parquet, "saida_csv": saida_csv,
            "bytes_parquet": os.path.getsize(saida_parquet),
            "analise": analise.como_dicionario(), "operadores_do_plano": operadores,
            "memoria_mb": int(plano["memoria_mb"]), "threads": int(plano["threads"]),
            "tempo_s": tempo_s, "linhas_max": linhas_max,
        }
    finally:
        if relogio is not None:
            relogio.cancel()
        con.close()


def principal(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "executar":
        sys.stderr.write(f"uso: {argv[0]} executar <plano.json>\n")
        return 2
    with open(argv[2], encoding="utf-8") as f:
        plano = json.load(f)
    sys.stdout.write(json.dumps(executar(plano), default=str) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(principal(sys.argv))
    except ErroTempo as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(CODIGO_TEMPO)
    except seguranca.ErroSqlInseguro as e:
        sys.stderr.write(f"{e.motivo}: {e.mensagem}\n")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — a mensagem é o que o usuário lê no job
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        sys.exit(1)
