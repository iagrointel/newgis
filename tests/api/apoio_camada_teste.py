"""Duas camadas vetoriais do inquilino, criadas do jeito que a plataforma as tem depois de uma importação:
uma tabela num schema de dado e um item `camada_vetorial` no catálogo apontando para ela. Apoio dos testes da
rede simples (item L4-18-rede-simples-trace-network) — a rede simples nasce de camadas do inquilino, então o
teste precisa de camadas de verdade, não de um atalho por dentro.

A bancada nasce no schema de dado da PRÓPRIA instalação (`PLAT_SCHEMA_TRABALHO` do ambiente da trilha; nas
árvores que já têm o isolamento por instalação esse é o schema com o prefixo da instalação). Antes ela nascia
no `d_demo`, compartilhado entre as trilhas: a primeira trilha a rodar virava dona das tabelas e todas as
outras recebiam `permission denied`. Cada trilha agora escreve no seu schema, e o `apagar_tabelas` do teardown
só apaga tabela com o prefixo do item dentro desse schema — o `d_demo` de outras trilhas nunca é tocado.
"""

import os
import re

import psycopg2
import psycopg2.extras

PREFIXO_TABELA = "zt_l418_"
SCHEMA_COMPARTILHADO = "d_demo"
SCHEMA_TRABALHO_PADRAO = "plat_trabalho"
NOME_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]*$")


def schema_dado() -> str:
    """O schema de dado desta instalação: `PLAT_SCHEMA_TRABALHO` (ambiente do processo ou `.env`), com o
    mesmo padrão que `tests/api/semear_catalogo.py` usa. Cada trilha tem o seu, então duas trilhas não
    disputam a dona da mesma tabela; o schema compartilhado nunca é devolvido."""
    from tests.conftest import valores_env

    schema = (valores_env().get("PLAT_SCHEMA_TRABALHO") or SCHEMA_TRABALHO_PADRAO).strip()
    assert NOME_SCHEMA.match(schema) and schema != SCHEMA_COMPARTILHADO, schema
    return schema


def apagar_tabelas(con, schema: str, tabelas: list[str]) -> None:
    """Teardown da bancada. Só apaga dentro do schema da própria instalação e só o que tem o prefixo do item."""
    assert schema != SCHEMA_COMPARTILHADO, "nunca apagar tabela no schema compartilhado"
    with con.cursor() as cur:
        for tabela in tabelas:
            assert tabela.startswith(PREFIXO_TABELA)
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}"')


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
