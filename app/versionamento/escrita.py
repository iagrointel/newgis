"""Escrita de linha de ramo (item L2-13-a): as primitivas que `edicao` e `servico` compartilham.

Invariante do ramo, uma frase: **para cada (ramo, feição) existe no máximo UMA linha com
`momento_fim` nulo** — a linha vigente. Toda alteração fecha a vigente (grava `momento_fim`) e insere
outra; apagar no ramo insere uma linha vigente com `apagada = true`, que é ao mesmo tempo a marca de
"esta feição saiu no ramo" e o registro de que o ramo TOCOU a feição (o que a tira da perna do padrão
na leitura, ver `leitura.relacao_do_ramo`).
"""

from __future__ import annotations

from typing import Any

import psycopg2

from app.erros import ErroAPI
from app.versionamento import leitura

MANTER = object()  # sentinela: "não mexe na geometria" (None quer dizer "geometria nula")

# colunas de sistema que a inserção de linha nova (feição que nasce no ramo) deixa o Postgres preencher
_DEIXAR_AO_BANCO = ("fid", "globalid", "criado_em", "criado_por", "tenant_id", "versao")


def linha_vigente(cur, schema: str, tabela: str, versao_id: str, globalid: str, tem_geom: bool) -> dict | None:
    ramo = leitura.tabela_ramo(tabela)
    extra = ", ST_AsGeoJSON(geom) AS __geom" if tem_geom else ""
    cur.execute(
        f'SELECT *{extra} FROM "{schema}"."{ramo}" '
        f"WHERE versao_id = %s::uuid AND globalid = %s::uuid AND momento_fim IS NULL",
        (versao_id, globalid),
    )
    return cur.fetchone()


def fechar(cur, schema: str, tabela: str, ramo_pk: int) -> None:
    ramo = leitura.tabela_ramo(tabela)
    cur.execute(f'UPDATE "{schema}"."{ramo}" SET momento_fim = now() WHERE ramo_pk = %s', (ramo_pk,))
    if cur.rowcount != 1:
        # a tabela de ramo tem RLS FORCE por inquilino: sem contexto, o UPDATE toca ZERO linhas em
        # silêncio. Conferir o número de linhas é a diferença entre "fechou" e "parecia ter fechado".
        raise ErroAPI(409, "linha_de_ramo_nao_fechada", "a linha vigente do ramo não pôde ser fechada")


def escrever(
    cur,
    schema: str,
    tabela: str,
    colunas: list[str],
    versao_id: str,
    srid: int,
    *,
    base: dict | None,
    atributos: dict[str, Any] | None = None,
    geom_geojson: Any = MANTER,
    geom_wkb: Any = MANTER,
    apagada: bool = False,
    usuario_id: int | None = None,
) -> dict:
    """Insere UMA linha vigente no ramo. `base` é o estado de partida (linha vigente do ramo ou linha
    do padrão no momento base); quando é None a feição nasce no ramo e o banco preenche fid/globalid.
    A geometria entra por GeoJSON (cópia de um estado já lido) ou por WKB (edição vinda do cliente,
    já validada por `app.edicao.servico._preparar_geometria`)."""
    ramo = leitura.tabela_ramo(tabela)
    atributos = atributos or {}
    colunas_sql: list[str] = []
    marcadores: list[str] = []
    valores: list[Any] = []

    def por(coluna: str, expr: str, *params: Any) -> None:
        colunas_sql.append(f'"{coluna}"')
        marcadores.append(expr)
        valores.extend(params)

    for c in colunas:
        if c == "geom":
            if geom_wkb is not MANTER:
                if geom_wkb is None:
                    por(c, "NULL")
                else:
                    por(c, "ST_SetSRID(ST_GeomFromWKB(%s), %s)", psycopg2.Binary(geom_wkb), srid)
            elif geom_geojson is not MANTER:
                if geom_geojson is None:
                    por(c, "NULL")
                else:
                    por(c, "ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)", geom_geojson, srid)
            elif base is not None and base.get("__geom") is not None:
                por(c, "ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)", base["__geom"], srid)
            continue
        if base is None and c in _DEIXAR_AO_BANCO and c not in atributos:
            continue
        if c in atributos:
            por(c, "%s", atributos[c])
        elif c == "versao":
            por(c, "%s", int(base.get("versao") or 0) + 1)
        elif c == "atualizado_em":
            por(c, "now()")
        elif c == "atualizado_por":
            por(c, "%s", usuario_id)
        elif base is not None:
            por(c, "%s", base.get(c))
    por("versao_id", "%s::uuid", versao_id)
    por("apagada", "%s", apagada)
    por("momento_inicio", "now()")
    sql = (
        f'INSERT INTO "{schema}"."{ramo}" ({", ".join(colunas_sql)}) '
        f'VALUES ({", ".join(marcadores)}) RETURNING ramo_pk, fid, globalid, versao'
    )
    cur.execute(sql, valores)
    return cur.fetchone()
