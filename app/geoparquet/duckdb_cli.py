"""Conversão para GeoParquet PARTICIONADO num PROCESSO PRÓPRIO (item L2-15-a-geoparquet-bucket-catalogo).

    python -m app.geoparquet.duckdb_cli particionar <origem.gpkg> <destino_dir> <memoria_mb> \
        <colunas_particao|-> <linhas_grupo>
    python -m app.geoparquet.duckdb_cli contar       <arquivo_ou_glob.parquet>

Escreve uma linha JSON em stdout e sai com 0; em erro, escreve a mensagem em stderr e sai com 1. Mesmo padrão
de `app/exportacao/parquet_cli.py` (item L0-04-h) e PELO MESMO MOTIVO documentado lá: o DuckDB não é seguro
depois de um `fork()` (o filho do worker é um fork — `terminate called without an active exception`, SIGABRT,
medido em 06/09/2026), então a conversão roda num `exec` limpo, neto do job (`ctx.subprocesso`).

Por isso este módulo REUSA `_conexao`/`_literal` de `app.exportacao.parquet_cli` em vez de reimplementar os
mesmos três ajustes de memória (memory_limit em 1/3 do teto, preserve_insertion_order=false, ROW_GROUP_SIZE) —
são a mesma configuração testada, e duplicá-la seria a única diferença seria esquecer de repetir o ajuste na
próxima medição.

O que este módulo acrescenta sobre o parquet_cli original:

1. **Partição hive** (`PARTITION_BY`, opcional): quando `colunas_particao` não é `-`, o COPY escreve um
   DIRETÓRIO (`<col>=<valor>/data_0.parquet`, layout padrão do DuckDB) em vez de um arquivo único. Sem
   partição, escreve um arquivo único `<destino_dir>/dados.parquet` (a assinatura da função sempre recebe um
   diretório de destino, para que o chamador não precise ramificar).
2. **Selo de versão 1.1.0**: o DuckDB 1.5.5 desta máquina escreve o metadado `geo` da especificação
   GeoParquet na versão **1.0.0** (MEDIDO em 07/09/2026: `COPY ... TO ... (FORMAT PARQUET)` sobre uma tabela
   com coluna GEOMETRY grava `{"version":"1.0.0",...}` no key-value `geo` do rodapé Parquet — não há opção do
   DuckDB para pedir 1.1). O conteúdo que o DuckDB escreve (`encoding: WKB`, `geometry_types`, `bbox`) é um
   SUBCONJUNTO válido do que a 1.1 aceita (o schema oficial só torna obrigatórios `version`, `primary_column`,
   `columns[].encoding`, `columns[].geometry_types` — `covering`, `epoch`, `orientation` são opcionais); a
   troca do rótulo de versão não muda o SIGNIFICADO do metadado, só declara a versão que ele já satisfaz.
   `"1.0.0"` e `"1.1.0"` têm o MESMO NÚMERO DE BYTES, então a troca é um find-and-replace binário dentro do
   arquivo (sem tocar em offset nenhum do rodapé Thrift) — nunca uma reescrita completa via pyarrow, que
   exigiria ler a tabela inteira de volta para a memória por arquivo.
3. **bbox e contagem lidos do ARQUIVO GERADO**, não do banco (mesmo princípio do L0-04-h): depois de escrever,
   cada `.parquet` é reaberto e agregado (`min/max` de `ST_XMin/YMin/XMax/YMax`, ou `NULL` quando a tabela não
   tem coluna `geom` — item sem geometria é um cenário do próprio portão do item).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

from app.exportacao.parquet_cli import _conexao, _literal  # reuso deliberado (ver docstring acima)

VERSAO_ANTIGA = b'"version":"1.0.0"'
VERSAO_NOVA = b'"version":"1.1.0"'
assert len(VERSAO_ANTIGA) == len(VERSAO_NOVA)  # a troca só é segura em-arquivo por terem o mesmo tamanho
_COLUNA_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _selar_1_1_0(caminho: str) -> None:
    """Troca `"version":"1.0.0"` por `"version":"1.1.0"` nos bytes do arquivo, em-lugar. Só mexe quando o
    padrão aparece EXATAMENTE uma vez (metadado `geo` do DuckDB); tabela sem geometria não tem esse metadado
    e a função não faz nada."""
    with open(caminho, "rb") as f:
        dados = f.read()
    n = dados.count(VERSAO_ANTIGA)
    if n == 0:
        return
    if n > 1:
        raise RuntimeError(f"{caminho}: padrão de versão GeoParquet apareceu {n} vezes, esperava 1")
    with open(caminho, "wb") as f:
        f.write(dados.replace(VERSAO_ANTIGA, VERSAO_NOVA, 1))


def _sha256_bytes(caminho: str) -> tuple[str, int]:
    h = hashlib.sha256()
    tamanho = 0
    with open(caminho, "rb") as f:
        while True:
            bloco = f.read(1024 * 1024)
            if not bloco:
                break
            h.update(bloco)
            tamanho += len(bloco)
    return h.hexdigest(), tamanho


def _particao_do_caminho(relativo: str) -> dict:
    """`{"uf": "SP"}` a partir de `uf=SP/data_0.parquet` (layout hive do DuckDB); `{}` sem partição."""
    partes = {}
    for segmento in relativo.replace(os.sep, "/").split("/")[:-1]:
        if "=" in segmento:
            chave, _, valor = segmento.partition("=")
            partes[chave] = valor
    return partes


def _tem_coluna_geom(con, caminho: str) -> bool:
    desc = con.execute(f"SELECT * FROM read_parquet({_literal(caminho)}) LIMIT 0").description
    return any(c[0] == "geom" for c in desc)


def _esquema(con, caminho: str) -> list[dict]:
    desc = con.execute(f"SELECT * FROM read_parquet({_literal(caminho)}) LIMIT 0").description
    return [{"nome": c[0], "tipo": str(c[1])} for c in desc]


def particionar(origem: str, destino_dir: str, memoria_mb: int, colunas_particao: str, linhas_grupo: int) -> dict:
    colunas = [c for c in (colunas_particao or "-").split(",") if c and c != "-"]
    for c in colunas:
        if not _COLUNA_OK.match(c):
            raise ValueError(f"nome de coluna de partição inválido: {c!r}")
    os.makedirs(destino_dir, exist_ok=True)
    con = _conexao(memoria_mb)
    try:
        opcoes = f"FORMAT PARQUET, OVERWRITE_OR_IGNORE true, COMPRESSION ZSTD, ROW_GROUP_SIZE {int(linhas_grupo)}"
        if colunas:
            particao_sql = ", ".join(f'"{c}"' for c in colunas)
            destino_sql = _literal(destino_dir)
            opcoes = f"PARTITION_BY ({particao_sql}), {opcoes}"
        else:
            destino_sql = _literal(os.path.join(destino_dir, "dados.parquet"))
        con.execute(f"COPY (SELECT * FROM ST_Read({_literal(origem)})) TO {destino_sql} ({opcoes})")

        arquivos = []
        linhas_total = 0
        esquema: list[dict] | None = None
        for raiz, _dirs, nomes in os.walk(destino_dir):
            for nome in sorted(nomes):
                if not nome.endswith(".parquet"):
                    continue
                caminho = os.path.join(raiz, nome)
                _selar_1_1_0(caminho)
                sha, tamanho = _sha256_bytes(caminho)
                linhas = int(con.execute(f"SELECT count(*) FROM read_parquet({_literal(caminho)})").fetchone()[0])
                bbox = None
                if _tem_coluna_geom(con, caminho):
                    r = con.execute(
                        "SELECT min(ST_XMin(geom)), min(ST_YMin(geom)), max(ST_XMax(geom)), max(ST_YMax(geom)) "
                        f"FROM read_parquet({_literal(caminho)}) WHERE geom IS NOT NULL"
                    ).fetchone()
                    if r and r[0] is not None:
                        bbox = [float(x) for x in r]
                if esquema is None:
                    esquema = _esquema(con, caminho)
                relativo = os.path.relpath(caminho, destino_dir)
                arquivos.append({
                    "caminho": relativo, "sha256": sha, "bytes": tamanho, "linhas": linhas, "bbox": bbox,
                    "particao": _particao_do_caminho(relativo),
                })
                linhas_total += linhas
        return {"arquivos": arquivos, "linhas_total": linhas_total, "esquema": esquema or []}
    finally:
        con.close()


def contar(padrao: str) -> int:
    con = _conexao(512)
    try:
        return int(con.execute(f"SELECT count(*) FROM read_parquet({_literal(padrao)})").fetchone()[0])
    finally:
        con.close()


def principal(argv: list[str]) -> int:
    if len(argv) >= 6 and argv[1] == "particionar":
        saida = particionar(argv[2], argv[3], int(argv[4]), argv[5], int(argv[6]) if len(argv) > 6 else 50_000)
    elif len(argv) >= 3 and argv[1] == "contar":
        saida = {"linhas": contar(argv[2])}
    else:
        sys.stderr.write(f"uso: {argv[0]} particionar <origem> <destino_dir> <memoria_mb> <colunas|-> "
                         "<linhas_grupo> | contar <padrao>\n")
        return 2
    sys.stdout.write(json.dumps(saida) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(principal(sys.argv))
    except Exception as e:  # noqa: BLE001 — a mensagem é o que o job mostra ao usuário
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        sys.exit(1)
