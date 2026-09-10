"""Fixtures do item L2-15-b-consultas-duckdb-em-escala.

Reusa a infraestrutura do irmão L2-15-a (`tests/api/geoparquet/conftest.py`): inquilino próprio com slug sem
hífen, worker de teste e semeadura de camada. O que este item acrescenta é o passo do meio — publicar a camada
como item de catálogo tipo `parquet` pelo job `geoparquet.gerar` — porque é ESSE item que as ferramentas
grandes consomem.

Cada fonte existe nas DUAS formas ao mesmo tempo: a camada no Postgres e o Parquet no bucket, com o mesmo
conteúdo. É essa duplicidade que permite rodar a MESMA ferramenta nos dois motores e comparar as contagens,
que é a refutação exigida pelo item.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from tests.api.exportacao.conftest import InquilinoDeExportacao, WorkerDeTeste, _contexto, conexao
from tests.api.geoparquet.conftest import gerar

PONTOS = 40_000       # pontos da fonte de teste; cabe no disco apertado e ainda exercita a agregação
POLIGONOS = 40        # polígonos que cobrem a área dos pontos
NAVIOS = 50           # identificadores distintos, para o deslocamento e as duplicatas terem grupos


@pytest.fixture(scope="session")
def worker_cg(env):
    w = WorkerDeTeste(env, f"teste-consulta-grande-{os.getpid()}")
    yield w
    w.parar()


@pytest.fixture(scope="session")
def inquilino_cg(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="session")
def inquilino_vizinho(sessao_plat):
    """Segundo inquilino: é dele o item Parquet que o primeiro NÃO pode ler."""
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


def semear_pontos(env, inq, quantidade: int = PONTOS, titulo: str = "zt consulta grande pontos") -> dict:
    """`d_<slug>.c_<hex>` com navio (identificador), instante, carga (número) e ponto em 4326."""
    return _semear(
        env, inq, titulo, "Point",
        colunas="navio bigint, instante timestamp, carga double precision, geom geometry(Point, 4326)",
        insercao=(
            "INSERT INTO {alvo} (navio, instante, carga, geom) "
            "SELECT (i %% {navios}), timestamp '2024-01-01' + ((i %% 900) || ' hours')::interval, "
            "       (i %% 37) * 0.5, "
            "       ST_SetSRID(ST_MakePoint(-50.0 + (i %% 97) * 0.05, -20.0 + ((i / 97) %% 53) * 0.05), 4326) "
            "FROM generate_series(1, %s) i"
        ).format(alvo="{alvo}", navios=NAVIOS),
        parametros=(quantidade,),
        campos=[{"nome": "navio", "tipo": "bigint"}, {"nome": "instante", "tipo": "timestamp"},
                {"nome": "carga", "tipo": "double precision"}],
        feicoes=quantidade,
    )


def semear_poligonos(env, inq, quantidade: int = POLIGONOS,
                     titulo: str = "zt consulta grande areas") -> dict:
    """Faixas verticais que cobrem a área dos pontos, sem sobreposição de interior."""
    return _semear(
        env, inq, titulo, "Polygon",
        colunas="codigo text, geom geometry(Polygon, 4326)",
        insercao=(
            "INSERT INTO {alvo} (codigo, geom) "
            "SELECT 'area-' || lpad(i::text, 3, '0'), "
            # o deslocamento de 0,025 grau existe para que nenhuma divisa caia EXATAMENTE sobre a coordenada
            # de um ponto (que é múltipla de 0,05): ponto sobre a divisa pertenceria aos dois polígonos e a
            # junção devolveria mais linhas que pontos, misturando o caso de borda com a contagem
            "       ST_SetSRID(ST_MakeEnvelope(-50.025 + (i - 1) * 0.12, -20.5, -50.025 + i * 0.12, -16.5), "
            "                  4326) "
            "FROM generate_series(1, %s) i"
        ),
        parametros=(quantidade,),
        campos=[{"nome": "codigo", "tipo": "text"}],
        feicoes=quantidade,
    )


def _semear(env, inq, titulo: str, geometria: str, colunas: str, insercao: str, parametros: tuple,
            campos: list, feicoes: int) -> dict:
    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    schema = f"d_{inq.slug}"
    alvo = f'"{schema}"."{tabela}"'
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inq.slug,))
            cur.execute(f"CREATE TABLE {alvo} (fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, {colunas})")
            cur.execute(insercao.format(alvo=alvo), parametros)
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4326, geometria, inq.admin_id))
            cur.execute(f"ANALYZE {alvo}")
            dados = {"schema": schema, "tabela": tabela, "geometria": geometria, "srid": 4326,
                     "fonte": "hospedada", "campos": campos}
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "criado_por, modificado_por) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s::jsonb, "
                "pg_total_relation_size(%s::regclass), %s, %s)",
                (item_id, inq.id, titulo, inq.admin_id, json.dumps(dados), f'"{schema}"."{tabela}"',
                 inq.admin_id, inq.admin_id),
            )
        con.commit()
    finally:
        con.close()
    return {"item_id": item_id, "schema": schema, "tabela": tabela, "feicoes": feicoes, "dados": dados}


def publicar_parquet(cliente, camada: dict, timeout: float = 600) -> str:
    """Roda o job do L2-15-a e devolve o id do item de catálogo tipo `parquet`."""
    job = gerar(cliente, {"item_id": camada["item_id"], "modo": "exportar"}, timeout=timeout)
    assert job["estado"] == "pronta", job
    assert job["catalogo_item_id"], job
    return str(job["catalogo_item_id"])


@pytest.fixture(scope="session")
def fonte_pontos(env, inquilino_cg, worker_cg):
    camada = semear_pontos(env, inquilino_cg)
    camada["parquet_id"] = publicar_parquet(inquilino_cg.admin, camada)
    return camada


@pytest.fixture(scope="session")
def fonte_poligonos(env, inquilino_cg, worker_cg):
    camada = semear_poligonos(env, inquilino_cg)
    camada["parquet_id"] = publicar_parquet(inquilino_cg.admin, camada)
    return camada


@pytest.fixture(scope="session")
def fonte_do_vizinho(env, inquilino_vizinho, worker_cg):
    camada = semear_pontos(env, inquilino_vizinho, quantidade=500, titulo="zt vizinho pontos")
    camada["parquet_id"] = publicar_parquet(inquilino_vizinho.admin, camada)
    return camada


def contar_no_banco(env, inq, schema: str, tabela: str) -> int:
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
            return int(cur.fetchone()["n"])
    finally:
        con.close()
