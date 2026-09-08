"""Motor do GeoParquet particionado (item L2-15-a-geoparquet-bucket-catalogo).

Reusa DE PROPÓSITO o motor do L0-04-h-exportar (`app.exportacao.motor`, ADR 0018) para tudo que já foi
medido e testado lá: a conexão `PG:...` já com `-c plat.tenant_id=N` (a RLS do PostgreSQL vale DENTRO do
ogr2ogr, não o inverso), a guarda de disco antes de escrever byte, o cronômetro e a limpeza do diretório de
trabalho. Este módulo só acrescenta o que o L0-04-h não precisa: um SELECT com colunas de PARTIÇÃO derivadas
(ano/mês) e a chamada ao `app.geoparquet.duckdb_cli` (que particiona, em vez de escrever um arquivo só).

A consulta NUNCA usa `SELECT *`: mesmo que a origem seja uma `vista_de_camada` com `campos_ocultos`, quem
chama este módulo resolve a lista de campos ANTES (mesma função que decide o que a vista mostra) e passa só
essa lista — é o que impede uma coluna escondida pela vista de aparecer no arquivo (refutação do item).
"""

from __future__ import annotations

from app.consulta import where_ast
from app.exportacao import motor as motor_exportacao
from app.exportacao.formatos import obter as formato_de

# reuso direto (ver docstring): nada disto precisa de outra versão para o GeoParquet
RAIZ = motor_exportacao.RAIZ
conninfo_pg = motor_exportacao.conninfo_pg
colunas_permitidas = motor_exportacao.colunas_permitidas
conferir_where = motor_exportacao.conferir_where
exigir_disco = motor_exportacao.exigir_disco
espaco_livre = motor_exportacao.espaco_livre
cronometrar = motor_exportacao.cronometrar
limpar = motor_exportacao.limpar
tamanho = motor_exportacao.tamanho
GPKG = formato_de("gpkg")


class ErroGeoparquet(Exception):
    """Falha que o usuário pode corrigir (partição/filtro/disco); a tarefa a converte em FalhaDefinitiva."""


def montar_select(
    cur, *, schema: str, tabela: str, campos: list[str], coluna_geom: str | None, where: str | None,
    srid_tabela: int, colunas_brancas: dict[str, str], particionar_por: dict | None,
) -> tuple[str, str | None]:
    """`(sql_completo, colunas_particao_csv)`. `colunas_particao_csv` é `None` sem partição, ou os nomes das
    colunas (já presentes no SELECT) que o `duckdb_cli.particionar` deve usar em `PARTITION_BY`."""
    selecionadas = [f'"{c}"' for c in campos]
    if coluna_geom:
        selecionadas.append(f'"{coluna_geom}"')
    condicoes: list[str] = []
    params: list = []
    if where:
        consulta = where_ast.compilar_where(where, colunas_brancas)
        condicoes.append(f"({consulta.sql})")
        params.extend(consulta.params)
    colunas_particao: str | None = None
    if particionar_por:
        coluna = particionar_por["coluna"]
        if coluna not in colunas_brancas:
            raise ErroGeoparquet(f"coluna de partição fora da lista branca do item: {coluna!r}")
        if particionar_por.get("grao") == "ano_mes":
            selecionadas.append(f"to_char({colunas_brancas[coluna]}, 'YYYY') AS _geoparquet_ano")
            selecionadas.append(f"to_char({colunas_brancas[coluna]}, 'MM') AS _geoparquet_mes")
            colunas_particao = "_geoparquet_ano,_geoparquet_mes"
        else:
            if coluna not in campos:
                selecionadas.append(f'{colunas_brancas[coluna]} AS "{coluna}"')
            colunas_particao = coluna
    sql = f'SELECT {", ".join(selecionadas)} FROM "{schema}"."{tabela}"'
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    return cur.mogrify(sql, params).decode("utf-8"), colunas_particao


def argumentos_ogr2ogr_gpkg(*, destino, conninfo: str, sql: str, nome_camada: str) -> list[str]:
    """GPKG intermediário (mesmo papel que tem no L0-04-h para o formato geoparquet de arquivo único): o
    `ogr2ogr` já resolve tipo/CRS/geometria mista; o DuckDB só faz a conversão e a partição."""
    return motor_exportacao.argumentos_ogr2ogr(
        GPKG, destino=destino, conninfo=conninfo, sql=sql, nome_camada=nome_camada, srid_saida=None,
        codificacao="UTF-8",
    )
