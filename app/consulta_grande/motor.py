"""Motor das consultas grandes (item L2-15-b-consultas-duckdb-em-escala): resolve os Parquet do inquilino,
chama o processo do DuckDB e carrega o resultado como camada no Postgres.

Três serviços, nesta ordem:

1. `resolver_parquet` — de um item de catálogo tipo `parquet` (publicado pelo L2-15-a) para a lista de
   arquivos, o esquema e o sha256 de cada parte. Passa pela MESMA porta de leitura das outras rotas
   (`plat.pode_ler` + RLS): item de outro inquilino não é lido, e a resposta é a mesma de item inexistente.
2. `preparar_dados` — traz cada arquivo do bucket para um diretório de trabalho do job e CONFERE o sha256
   contra o que o catálogo declara. Um arquivo do bucket que não bate com o catálogo interrompe a consulta:
   é a única forma de o resultado poder carregar "sha256 dos arquivos" na proveniência e a frase significar
   alguma coisa. O diretório é só deste job, e é o ÚNICO caminho que o motor do DuckDB pode abrir.
3. `carregar_no_destino` — cria a tabela de saída no schema de dado do inquilino a partir dos campos que o
   processo do DuckDB declarou e carrega o CSV com `COPY ... FROM STDIN`, recurso nativo do Postgres. A
   geometria vem em WKT e vira `geometry(<tipo>, <srid>)` com `ST_GeomFromText`. Sem GDAL e sem DuckDB neste
   processo (que é um fork do worker; ver a docstring do `duckdb_cli`).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from app import limites, objetos
from app.exportacao import motor as motor_exportacao

TIPO_ITEM_PARQUET = "parquet"
RAIZ = motor_exportacao.RAIZ


class ErroConsulta(Exception):
    """Falha que o usuário pode corrigir. `motivo` é um código estável; `tempo` marca o estouro do teto."""

    def __init__(self, mensagem: str, motivo: str = "consulta_invalida", tempo: bool = False):
        super().__init__(mensagem)
        self.motivo = motivo
        self.tempo = tempo


# ---------------------------------------------------------------- 1. resolver
def resolver_parquet(cur, item_id: str, nome_parametro: str = "fonte") -> dict:
    """{item_id, titulo, versao, arquivos, linhas, bytes, esquema, crs, sha256}. Item que não existe, que foi
    apagado, que é de outro inquilino ou que não é do tipo `parquet` dá o MESMO erro: nunca confirma existência."""
    cur.execute("SELECT id, titulo, tipo, dados, versao_atual FROM plat.item "
                "WHERE id = %s::uuid AND apagado_em IS NULL AND plat.pode_ler(id)", (str(item_id),))
    r = cur.fetchone()
    if r is None or r["tipo"] != TIPO_ITEM_PARQUET:
        raise ErroConsulta(f"{nome_parametro}: fonte Parquet inexistente ou sem leitura", "fonte_inexistente")
    d = r["dados"] or {}
    arquivos = list(d.get("arquivos") or [])
    if not arquivos:
        raise ErroConsulta(f"{nome_parametro}: a fonte não tem nenhum arquivo publicado", "fonte_vazia")
    if len(arquivos) > limites.CONSULTA_GRANDE_ARQUIVOS_MAX:
        raise ErroConsulta(f"{nome_parametro}: a fonte tem {len(arquivos)} partes; o teto é "
                           f"{limites.CONSULTA_GRANDE_ARQUIVOS_MAX}", "fonte_grande_demais")
    partes = "".join(sorted(a["sha256"] for a in arquivos))
    return {
        "item_id": str(r["id"]), "titulo": r["titulo"], "versao": int(r["versao_atual"]), "arquivos": arquivos,
        "linhas": int(d.get("linhas_total") or 0), "bytes": int(d.get("bytes_total") or 0),
        "esquema": list(d.get("esquema") or []), "crs": int(d.get("crs") or 4326),
        "sha256": hashlib.sha256(partes.encode("utf-8")).hexdigest(),
    }


# ---------------------------------------------------------------- 2. trazer os arquivos
def preparar_dados(fonte: dict, dir_dados: Path) -> list[str]:
    """Baixa cada parte do bucket para `dir_dados` e confere o sha256 contra o catálogo. Devolve os caminhos."""
    dir_dados.mkdir(parents=True, exist_ok=True)
    motor_exportacao.exigir_disco(dir_dados, max(int(fonte["bytes"]) * 2, 8 * 1024 * 1024))
    caminhos = []
    for i, a in enumerate(fonte["arquivos"]):
        destino = dir_dados / f"parte_{i:05d}.parquet"
        h = hashlib.sha256()
        with open(destino, "wb") as f:
            for bloco in objetos.ler_stream(a["chave"], limites.EXPORTACAO_BLOCO_LEITURA_BYTES):
                h.update(bloco)
                f.write(bloco)
        if h.hexdigest() != a["sha256"]:
            raise ErroConsulta(
                f"a parte {a['chave'].rsplit('/', 1)[-1]} do bucket não bate com o sha256 do catálogo; "
                "a consulta foi interrompida", "sha256_divergente")
        caminhos.append(str(destino))
    return caminhos


# ---------------------------------------------------------------- 3. rodar o processo do DuckDB
def executar_sql(ctx, *, sql: str, views: dict[str, list[str]], dir_trabalho: Path,
                 memoria_mb: int | None = None, threads: int | None = None, tempo_s: int | None = None,
                 linhas_max: int | None = None) -> dict:
    """Roda o `duckdb_cli` como NETO do job (`ctx.subprocesso`) e devolve o manifesto do resultado."""
    dir_trabalho.mkdir(parents=True, exist_ok=True)
    diretorios = sorted({str(Path(c).parent) for cs in views.values() for c in cs} | {str(dir_trabalho)})
    plano = {
        "sql": sql, "views": views, "diretorios": diretorios,
        "memoria_mb": int(memoria_mb or limites.CONSULTA_GRANDE_MEMORIA_MB),
        "threads": int(threads or limites.CONSULTA_GRANDE_THREADS),
        "tempo_s": int(tempo_s or limites.CONSULTA_GRANDE_TEMPO_S),
        "linhas_max": int(linhas_max or limites.CONSULTA_GRANDE_LINHAS_SAIDA_MAX),
        "sql_max": limites.CONSULTA_GRANDE_SQL_MAX,
        "saida_parquet": str(dir_trabalho / "resultado.parquet"),
        "saida_csv": str(dir_trabalho / "resultado.csv"),
    }
    caminho_plano = dir_trabalho / "plano.json"
    caminho_plano.write_text(json.dumps(plano), encoding="utf-8")
    argv = [sys.executable, "-m", "app.consulta_grande.duckdb_cli", "executar", str(caminho_plano)]
    resultado = ctx.subprocesso(argv, cwd=str(RAIZ))
    if resultado.returncode != 0:
        detalhe = [ln for ln in (resultado.stderr or "").splitlines() if ln.strip()]
        mensagem = (detalhe[-1] if detalhe else "sem detalhe")[:400]
        from app.consulta_grande.duckdb_cli import CODIGO_TEMPO

        raise ErroConsulta(mensagem, "tempo_esgotado" if resultado.returncode == CODIGO_TEMPO else "sql_recusado",
                           tempo=resultado.returncode == CODIGO_TEMPO)
    for linha in reversed((resultado.stdout or "").splitlines()):
        if linha.strip().startswith("{"):
            return json.loads(linha)
    raise ErroConsulta("o motor de consulta não devolveu o manifesto", "sem_manifesto")


def subprocesso_simples(argv: list[str], cwd: str | None = None):
    """`ctx.subprocesso` de um contexto que não tem um (execução em processo): mesmo contrato mínimo."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False,  # noqa: S603
                          env={**os.environ, "PYTHONPATH": str(RAIZ)})


# ---------------------------------------------------------------- 4. carregar o resultado como camada
GEOMETRIAS_PG = {"POINT": "Point", "MULTIPOINT": "MultiPoint", "LINESTRING": "LineString",
                 "MULTILINESTRING": "MultiLineString", "POLYGON": "Polygon", "MULTIPOLYGON": "MultiPolygon",
                 "GEOMETRYCOLLECTION": "GeometryCollection"}


def _tipo_geometria(cur, tabela_temporaria: str, coluna: str) -> str:
    cur.execute(f'SELECT DISTINCT upper(ST_GeometryType(ST_GeomFromText("{coluna}"))) AS t '
                f'FROM {tabela_temporaria} WHERE "{coluna}" IS NOT NULL AND "{coluna}" <> \'\' LIMIT 8')
    tipos = {(r["t"] or "").replace("ST_", "") for r in cur.fetchall()}
    if not tipos:
        return "Geometry"
    if len(tipos) == 1:
        return GEOMETRIAS_PG.get(tipos.pop(), "Geometry")
    return "Geometry"


def carregar_no_destino(cur, destino: dict, manifesto: dict, caminho_csv: str, srid: int) -> dict:
    """Cria `destino.schema.destino.tabela` com os campos do manifesto e carrega o CSV. Devolve o dicionário
    que o executor de ferramentas espera: {geometria, srid, campos, metodo}."""
    alvo = f'"{destino["schema"]}"."{destino["tabela"]}"'
    campos = manifesto["campos"]
    if not campos:
        raise ErroConsulta("a consulta não devolveu nenhuma coluna", "sem_colunas")
    coluna_geom = next((c["nome"] for c in campos if c["tipo"] == "geometry"), None)
    colunas_sql = ", ".join(
        f'"{c["nome"]}" ' + ("text" if c["tipo"] == "geometry" else c["tipo"]) for c in campos)
    temporaria = f'"{destino["schema"]}"."{destino["tabela"]}_bruto"'
    cur.execute(f"CREATE TABLE {temporaria} ({colunas_sql})")
    lista = ", ".join(f'"{c["nome"]}"' for c in campos)
    with open(caminho_csv, encoding="utf-8") as f:
        cur.copy_expert(f"COPY {temporaria} ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    if coluna_geom:
        geometria = _tipo_geometria(cur, temporaria, coluna_geom)
        outras = [c for c in campos if c["nome"] != coluna_geom]
        selecao = ", ".join([f'"{c["nome"]}"' for c in outras]
                            + [f'ST_SetSRID(ST_GeomFromText("{coluna_geom}"), {int(srid)}) AS geom'])
        cur.execute(f"CREATE TABLE {alvo} AS SELECT {selecao} FROM {temporaria}")
        cur.execute(f'ALTER TABLE {alvo} ALTER COLUMN geom TYPE geometry({geometria}, {int(srid)}) USING geom')
        campos_saida = [{"nome": c["nome"], "tipo": c["tipo"], "alias": c["nome"]} for c in outras]
    else:
        geometria = "Geometry"
        cur.execute(f"CREATE TABLE {alvo} AS SELECT * FROM {temporaria}")
        cur.execute(f"ALTER TABLE {alvo} ADD COLUMN geom geometry(Geometry, {int(srid)})")
        campos_saida = [{"nome": c["nome"], "tipo": c["tipo"], "alias": c["nome"]} for c in campos]
    cur.execute(f"DROP TABLE {temporaria}")
    cur.execute(f"ALTER TABLE {alvo} ADD COLUMN fid bigserial PRIMARY KEY")
    return {"geometria": geometria, "srid": int(srid), "campos": campos_saida}


def proveniencia(sql: str, fontes: list[dict], manifesto: dict) -> dict:
    """Bloco que vai para `dados.procedencia.consulta_grande` do item de resultado: o SQL que rodou, o sha256
    de cada arquivo lido e o que o motor mediu. É o que torna a camada reprodutível."""
    return {
        "motor": "duckdb", "sql": sql,
        "fontes": [{"item_id": f["item_id"], "versao": f["versao"], "sha256": f["sha256"],
                    "arquivos": [{"chave": a["chave"], "sha256": a["sha256"], "linhas": a.get("linhas")}
                                 for a in f["arquivos"]]} for f in fontes],
        "linhas": manifesto["linhas"], "duracao_ms": manifesto["ms"],
        "memoria_mb": manifesto["memoria_mb"], "threads": manifesto["threads"],
        "teto_tempo_s": manifesto["tempo_s"], "teto_linhas": manifesto["linhas_max"],
        "operadores_do_plano": manifesto.get("operadores_do_plano") or [],
        "funcoes": (manifesto.get("analise") or {}).get("funcoes") or [],
    }
