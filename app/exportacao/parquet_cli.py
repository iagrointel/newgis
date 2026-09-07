"""Conversão para GeoParquet num PROCESSO PRÓPRIO (item L0-04-h-exportar).

    python -m app.exportacao.parquet_cli converter <origem.gpkg> <destino.parquet> <memoria_mb>
    python -m app.exportacao.parquet_cli contar    <arquivo.parquet>

Escreve uma linha JSON em stdout (`{"linhas": 100000}`) e sai com 0; em erro, escreve a mensagem em stderr e
sai com 1.

**Por que um processo separado, e não `import duckdb` dentro da tarefa.** O filho que roda um job é um FORK do
worker (`app/jobs/filho.py`), e o DuckDB não é seguro depois de um fork: MEDIDO em 06/09/2026 nesta máquina,
o mesmo `COPY (SELECT * FROM ST_Read(…)) TO …` que roda em 0,17 s num processo normal mata o processo
FORKADO com `terminate called without an active exception` (SIGABRT, sinal 6) — com `threads=1` e com
`threads=2`, antes de escrever qualquer byte. Como o job já roda o `ogr2ogr` como neto (`ctx.subprocesso`),
o GeoParquet segue o mesmo caminho: `exec` de um processo limpo, que herda o `RLIMIT_DATA` do job e morre
junto com ele no cancelamento.

Os três ajustes de memória são obrigatórios: `memory_limit` em um terço do teto do job,
`preserve_insertion_order=false` (deixa o motor descarregar em lotes) e `ROW_GROUP_SIZE` (limita o buffer do
escritor de Parquet). Sem eles, um esbarro no `RLIMIT_DATA` vira `std::bad_alloc` sem tratamento — o DuckDB
aborta o processo em vez de devolver erro.

A extensão `spatial` é carregada do cache local do usuário que roda o worker (`~/.duckdb/extensions`); sem
rede e sem esse cache, `LOAD spatial` falha e a mensagem sai daqui, explicando o que falta.
"""

from __future__ import annotations

import json
import sys


def _conexao(memoria_mb: int):
    import duckdb

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{max(192, int(memoria_mb) // 3)}MB'")
    con.execute("SET threads=2")
    con.execute("SET preserve_insertion_order=false")
    con.execute("LOAD spatial")
    return con


def _literal(caminho: str) -> str:
    """Caminho como literal SQL. Parâmetro (`?`) NÃO serve: MEDIDO em 06/09/2026, num
    `COPY (SELECT * FROM ST_Read(?)) TO ? (…)` o DuckDB casa os dois `?` na ordem errada e tenta ABRIR o
    arquivo de saída como GDAL dataset ("Could not open GDAL dataset at: …parquet"). O caminho é sempre
    gerado por nós (diretório de trabalho do job); a aspa simples é duplicada."""
    return "'" + str(caminho).replace("'", "''") + "'"


def converter(origem: str, destino: str, memoria_mb: int) -> int:
    con = _conexao(memoria_mb)
    try:
        con.execute(
            f"COPY (SELECT * FROM ST_Read({_literal(origem)})) TO {_literal(destino)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50000)"
        )
        return int(con.execute(f"SELECT count(*) FROM read_parquet({_literal(destino)})").fetchone()[0])
    finally:
        con.close()


def contar(arquivo: str) -> int:
    con = _conexao(512)
    try:
        return int(con.execute(f"SELECT count(*) FROM read_parquet({_literal(arquivo)})").fetchone()[0])
    finally:
        con.close()


def principal(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "converter":
        linhas = converter(argv[2], argv[3], int(argv[4]) if len(argv) > 4 else 1024)
    elif len(argv) >= 3 and argv[1] == "contar":
        linhas = contar(argv[2])
    else:
        sys.stderr.write(f"uso: {argv[0]} converter <origem> <destino> <memoria_mb> | contar <arquivo>\n")
        return 2
    sys.stdout.write(json.dumps({"linhas": linhas}) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(principal(sys.argv))
    except Exception as e:  # noqa: BLE001 — a mensagem é o que o job mostra ao usuário
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        sys.exit(1)
