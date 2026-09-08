"""GeoPackage 1.2 escrito com a biblioteca padrão (item L4-02-f-resultados-e-exportacao).

Um GeoPackage é um banco SQLite com três tabelas de catálogo (`gpkg_spatial_ref_sys`, `gpkg_contents`,
`gpkg_geometry_columns`) e uma tabela de feições cuja coluna de geometria guarda o "GeoPackageBinary": um
cabeçalho curto (a marca `GP`, versão, sinalizadores, o código do sistema de referência) seguido do WKB da
geometria — que o próprio PostGIS devolve, em `ST_AsBinary`.

Por que não `ogr2ogr`: escrever o arquivo exigiria subprocesso e arquivo temporário dentro da requisição, e o
repositório só chama `ogr2ogr` de dentro de um job (`app/jobs/contexto_job.py`). Com `sqlite3` do Python o
arquivo nasce em memória e sai como bytes — sem processo filho, sem disco (a casa está com 98 % de disco) e
sem dependência nova. O formato é conferido no teste do item por `ogrinfo`, que é quem lê o arquivo de
verdade, e não por nós mesmos.

Escopo: uma tabela de feições, geometria genérica (`GEOMETRY`, porque um traçado devolve ponto e linha
juntos), colunas de atributo em texto ou número. Nada de índice espacial (`gpkg_rtree`), nada de extensão —
os dois são opcionais na especificação e o leitor não precisa deles."""

import sqlite3
import struct

APPLICATION_ID = 0x47504B47  # 'GPKG', o que o leitor procura nos bytes 68-71 do arquivo
USER_VERSION = 10200         # GeoPackage 1.2
SRID_PADRAO = 4326
_WGS84 = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
          'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')
_CATALOGO = """
CREATE TABLE gpkg_spatial_ref_sys (
  srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, organization TEXT NOT NULL,
  organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
CREATE TABLE gpkg_contents (
  table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
  description TEXT DEFAULT '', last_change DATETIME NOT NULL
    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
  CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_geometry_columns (
  table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
  srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
  CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
  CONSTRAINT uk_gc_table_name UNIQUE (table_name),
  CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
  CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));
"""


def envelope(wkb: bytes | memoryview | None, srid: int = SRID_PADRAO) -> bytes | None:
    """O WKB do PostGIS embrulhado no cabeçalho GeoPackageBinary (sem envelope: `flags` = 1, só a ordem de
    bytes little-endian). Geometria ausente vira NULL, que a especificação admite."""
    if wkb is None:
        return None
    return struct.pack("<ccBBi", b"G", b"P", 0, 1, srid) + bytes(wkb)


def _tipo_sqlite(valor) -> str:
    if isinstance(valor, bool):
        return "INTEGER"
    if isinstance(valor, int):
        return "INTEGER"
    if isinstance(valor, float):
        return "REAL"
    return "TEXT"


def escrever(tabela: str, colunas: list[str], linhas: list[dict], geometrias: list[bytes | None],
             srid: int = SRID_PADRAO, identificador: str | None = None) -> bytes:
    """Devolve os bytes de um GeoPackage com UMA tabela de feições. `linhas[i]` traz os atributos (só as
    chaves de `colunas`) e `geometrias[i]`, o WKB já embrulhado por `envelope`. `tabela` tem de ser um
    identificador simples — quem chama é código nosso, nunca texto de pedido."""
    if not tabela.replace("_", "").isalnum():
        raise ValueError(f"nome de tabela inválido para GeoPackage: {tabela!r}")
    if len(linhas) != len(geometrias):
        raise ValueError("uma geometria por linha (podendo ser None)")
    tipos = {}
    for coluna in colunas:
        achado = next((linha[coluna] for linha in linhas
                       if linha.get(coluna) is not None), None)
        tipos[coluna] = _tipo_sqlite(achado)

    con = sqlite3.connect(":memory:")
    try:
        con.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        con.execute(f"PRAGMA user_version = {USER_VERSION}")
        con.executescript(_CATALOGO)
        con.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
            [("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
             ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
             ("WGS 84 geodetic", 4326, "EPSG", 4326, _WGS84, None)],
        )
        colunas_sql = ", ".join(f'"{c}" {tipos[c]}' for c in colunas)
        con.execute(f'CREATE TABLE "{tabela}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, '
                    f'geom BLOB{", " + colunas_sql if colunas else ""})')
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?,?,?,?)",
                    (tabela, "features", identificador or tabela, srid))
        con.execute("INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
                    (tabela, "geom", "GEOMETRY", srid, 0, 0))
        marcas = ", ".join("?" * (len(colunas) + 1))
        nomes = ", ".join(['"geom"'] + [f'"{c}"' for c in colunas])
        con.executemany(
            f'INSERT INTO "{tabela}" ({nomes}) VALUES ({marcas})',
            [(geometrias[i], *[linhas[i].get(c) for c in colunas]) for i in range(len(linhas))],
        )
        con.commit()
        return con.serialize()
    finally:
        con.close()
