"""Duas camadas vetoriais do inquilino, criadas do jeito que a plataforma as tem depois de uma importação:
uma tabela no schema de dado do inquilino (`d_<slug>`) e um item `camada_vetorial` no catálogo apontando para
ela. Apoio dos testes da rede simples (item L4-18-rede-simples-trace-network) — a rede simples nasce de
camadas do inquilino, então o teste precisa de camadas de verdade, não de um atalho por dentro.

⛔ O schema `d_demo` é COMPARTILHADO entre as trilhas desta sessão (só as trilhas que já têm a migração de
prefixo por trilha escrevem em `d_<trilha>_<slug>`). Por isso as tabelas daqui têm nome fixo com prefixo do
item (`zt_l418_*`), são recriadas por `CREATE TABLE IF NOT EXISTS` + `TRUNCATE`, e NADA que não tenha esse
prefixo é apagado."""

import os

import psycopg2
import psycopg2.extras

PREFIXO_TABELA = "zt_l418_"


def conexao():
    dsn = os.environ.get("PLAT_DSN")
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = True
    return con


def criar_tabela_linhas(con, schema: str, tabela: str, trechos: list[dict], campos: list[str]) -> None:
    """`trechos` = [{"coordenadas": [[lon,lat],...], "<campo>": valor, ...}]. A geometria entra como
    MultiLineString (é o que o ogr2ogr da ingestão grava com PROMOTE_TO_MULTI), para que a carga da rede
    simples tenha de explodir a multiparte de verdade."""
    assert tabela.startswith(PREFIXO_TABELA)
    colunas = ", ".join(f'"{c}" text' for c in campos)
    with con.cursor() as cur:
        cur.execute(f'CREATE TABLE IF NOT EXISTS "{schema}"."{tabela}" '
                    f'(fid bigserial PRIMARY KEY, {colunas}, geom geometry(MultiLineString, 4326))')
        cur.execute(f'TRUNCATE "{schema}"."{tabela}"')
        for t in trechos:
            wkt = "MULTILINESTRING((" + ", ".join(f"{lon} {lat}" for lon, lat in t["coordenadas"]) + "))"
            valores = [t.get(c) for c in campos]
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" ({", ".join(chr(34) + c + chr(34) for c in campos)}, geom) '
                f'VALUES ({", ".join(["%s"] * len(campos))}, ST_GeomFromText(%s, 4326))',
                (*valores, wkt),
            )


def criar_tabela_pontos(con, schema: str, tabela: str, pontos: list[dict], campos: list[str]) -> None:
    assert tabela.startswith(PREFIXO_TABELA)
    colunas = ", ".join(f'"{c}" text' for c in campos)
    with con.cursor() as cur:
        cur.execute(f'CREATE TABLE IF NOT EXISTS "{schema}"."{tabela}" '
                    f'(fid bigserial PRIMARY KEY, {colunas}, geom geometry(Point, 4326))')
        cur.execute(f'TRUNCATE "{schema}"."{tabela}"')
        for p in pontos:
            valores = [p.get(c) for c in campos]
            cur.execute(
                f'INSERT INTO "{schema}"."{tabela}" ({", ".join(chr(34) + c + chr(34) for c in campos)}, geom) '
                f'VALUES ({", ".join(["%s"] * len(campos))}, ST_SetSRID(ST_MakePoint(%s, %s), 4326))',
                (*valores, p["lon"], p["lat"]),
            )


def registrar_item(sessao, titulo: str, schema: str, tabela: str, geometria: str, campos: list[str]) -> str:
    """Item `camada_vetorial` no catálogo do inquilino apontando para a tabela. Devolve o id do item."""
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo,
        "dados": {"schema": schema, "tabela": tabela, "geometria": geometria, "srid": 4326,
                  "campos": [{"nome": c, "tipo": "text"} for c in campos], "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]
