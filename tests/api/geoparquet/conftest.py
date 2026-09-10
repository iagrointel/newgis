"""Fixtures do GeoParquet particionado (item L2-15-a-geoparquet-bucket-catalogo).

Reusa DE PROPÓSITO a infraestrutura já construída para o L0-04-h-exportar (`tests/api/exportacao/conftest.py`,
que este ramo já mesclou): `InquilinoDeExportacao`, `WorkerDeTeste` e `conexao`/`_contexto` — a única coisa que
muda é a TABELA semeada, que aqui ganha `uf` (partição por valor) e `data_evento` (partição por ano/mês) além
das colunas que a exportação já usava."""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest

from tests.api.exportacao.conftest import (
    FEICOES,  # noqa: F401 — reexportado por conveniência de quem só quer o número
    InquilinoDeExportacao,
    WorkerDeTeste,
    _contexto,
    conexao,
)

UFS = ["SP", "RJ", "MG", "ES", "BA", "PE", "CE", "PA", "AM", "RS", "PR", "SC", "GO", "DF", "MT", "MS", "AL",
      "SE", "PB", "RN", "PI", "MA", "TO", "RO", "AC", "RR", "AP"]
assert len(UFS) == 27


@pytest.fixture(scope="session")
def worker_geoparquet(env):
    w = WorkerDeTeste(env, f"teste-geoparquet-{os.getpid()}")
    yield w
    w.parar()


@pytest.fixture(scope="session")
def inquilino_gp(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


def semear_camada_particionavel(env, inq, feicoes: int, titulo: str, ufs=None) -> dict:
    """`d_<slug>.c_<16 hex>` com `uf` (ciclando pelas 27 UFs, ou uma lista fixa) e `data_evento` (ano
    variando conforme `i`, para o grão ano_mes ter mais de um valor). Publica o item `camada_vetorial`."""
    ufs = ufs or UFS
    tabela = "c_" + uuid.uuid4().hex[:16]
    item_id = str(uuid.uuid4())
    schema = f"d_{inq.slug}"
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (inq.slug,))
            cur.execute(
                f'CREATE TABLE "{schema}"."{tabela}" ('
                " fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                " nome text, uf text, data_evento date, texto_grande text,"
                " geom geometry(Point, 4674))"
            )
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" (nome, uf, data_evento, texto_grande, geom) '
                "SELECT 'ponto ' || i, (%s::text[])[1 + (i %% %s)], "
                "       date '2024-01-01' + ((i %% 24) || ' months')::interval, "
                "       repeat('x', (i %% 5)), "
                "       ST_SetSRID(ST_MakePoint(-46.55 + (i %% 317) * 0.0009, -23.45 + (i / 317) * 0.0009), 4674) "
                "FROM generate_series(1, %s) i",
                (ufs, len(ufs), feicoes),
            )
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, 4674, "Point", inq.admin_id))
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            dados = {
                "schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4674, "fonte": "hospedada",
                "campos": [
                    {"nome": "fid", "tipo": "bigint"}, {"nome": "nome", "tipo": "text"},
                    {"nome": "uf", "tipo": "text"}, {"nome": "data_evento", "tipo": "date"},
                    {"nome": "texto_grande", "tipo": "text"},
                ],
            }
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


def esperar_job(cliente, job_id: str, timeout: float = 300) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = cliente.get(f"/api/geoparquet/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("pronta", "falhou", "cancelada"):
            return ultimo
        time.sleep(0.25)
    pytest.fail(f"job de geoparquet {job_id} não terminou em {timeout} s: {ultimo}")


def gerar(cliente, corpo: dict, timeout: float = 300) -> dict:
    r = cliente.post("/api/geoparquet", json=corpo)
    assert r.status_code == 202, r.text
    return esperar_job(cliente, r.json()["job_id"], timeout)


def linhas_no_banco(env, inq, schema: str, tabela: str) -> int:
    con = conexao(env)
    try:
        _contexto(con, inq.id, inq.admin_id)
        with con.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
            return int(cur.fetchone()["n"])
    finally:
        con.close()
