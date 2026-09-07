"""Catálogo dos formatos de SAÍDA do intercâmbio (item L6-02-o-importacao-exportacao-formatos), cada um MEDIDO
no GDAL 3.8.4 desta máquina em 06/09/2026 (`ogrinfo --formats` + escrita/leitura de prova em /tmp):

- shapefile.zip: DBF trunca nome de campo em 10 caracteres ("campo_muito_longo_mesmo" vira "campo_muit",
  Warning 6 do GDAL, silencioso sem o nosso aviso) e NÃO tem tipo data-hora: DateTime vira texto ISO 8601
  (medido: "2026-09-06T14:30:00Z" num campo String). Texto tem largura máxima de 254.
- kml/kmz (LIBKML): sempre EPSG:4326; campo DateTime vira elemento <TimeStamp> (o campo some da tabela de
  atributos na releitura — medido); na releitura aparecem colunas próprias do KML (Name, description,
  timestamp, altitudeMode...). Atributos comuns voltam por ExtendedData.
- xlsx: o driver XLSX não escreve geometria (medido: GEOMETRY=AS_WKT ignorado, a coluna nem aparece) —
  por isso a exportação acrescenta a coluna `geometria_wkt` (ST_AsText) ela mesma.
- mbtiles/pmtiles: geometria quantizada na grade do tile (4096 por tile no zoom de geração) e feição que
  cruza borda de tile pode ser duplicada recortada; é formato de PUBLICAÇÃO, não de intercâmbio fiel —
  o aviso é inerente e vai em toda exportação.
- filegdb.zip: diretório .gdb escrito pelo driver OpenFileGDB (o MESMO driver que o QGIS usa para abrir
  FileGDB — não há QGIS nesta máquina; a prova de "abre" é estrutural + releitura pelo driver).
- DXF não está na lista de SAÍDA: o formato não tem tabela de atributos, logo falha a cláusula do portão
  "geometria e atributos preservados" (a ENTRADA de DXF é do item irmão L0-04-e-formatos-cad).
- MSSQLSpatial: o driver existe no GDAL da máquina, mas não há servidor SQL Server para provar ida e
  volta — fica de fora do que se oferece (paridade honesta em docs/PARIDADE_FORMATOS.md).
- Parquet e OCI: drivers AUSENTES do GDAL 3.8.4 desta máquina (medido) — não temos.

A lista NÃO é marketing: cada formato oferecido tem teste de ida e volta em
tests/api/intercambio/test_exportacao.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import limites


@dataclass(frozen=True)
class FormatoSaida:
    nome: str                 # chave declarada na API (ex.: "shapefile.zip")
    rotulo: str
    driver: str               # driver GDAL de escrita
    extensao: str             # extensão do pacote final (depois do zip, quando empacota)
    content_type: str
    empacotar: str | None     # None | "zip_shapefile" | "zip_gdb" — como o arquivo final é montado
    crs_fixo: int | None      # CRS imposto pelo formato (4326); None = o usuário escolhe (padrão: o da camada)
    geometria: str            # "nativa" | "wkt" | "tile"
    opcoes_camada: tuple[str, ...] = ()
    opcoes_dataset: tuple[str, ...] = ()
    avisos_inerentes: tuple[str, ...] = ()


_AVISO_TILE = (
    "geometria quantizada na grade do tile (4096 passos por tile); feição que cruza borda de tile pode "
    "voltar duplicada e recortada — formato de publicação, não de intercâmbio fiel"
)

FORMATOS_SAIDA: dict[str, FormatoSaida] = {
    "gpkg": FormatoSaida(
        "gpkg", "GeoPackage", "GPKG", "gpkg", "application/geopackage+sqlite3", None, None, "nativa",
        opcoes_camada=("SPATIAL_INDEX=YES",),
    ),
    "shapefile.zip": FormatoSaida(
        "shapefile.zip", "Shapefile (zip)", "ESRI Shapefile", "zip", "application/zip", "zip_shapefile",
        None, "nativa",
        avisos_inerentes=(
            "nomes de campo com mais de 10 caracteres são truncados pelo formato DBF (o aviso por campo "
            "vem no relatório da exportação)",
            "campos data-hora viram texto ISO 8601 (DBF não tem tipo data-hora); campos data são preservados",
            f"texto com mais de {limites.INTERCAMBIO_DBF_LARGURA_MAX} caracteres é truncado pelo formato DBF",
        ),
    ),
    "geojson": FormatoSaida(
        "geojson", "GeoJSON (RFC 7946)", "GeoJSON", "geojson", "application/geo+json", None, 4326, "nativa",
        opcoes_camada=("RFC7946=YES", "WRITE_BBOX=YES"),
        avisos_inerentes=("reprojetado para EPSG:4326 (exigência da RFC 7946)",),
    ),
    "geojsonseq": FormatoSaida(
        "geojsonseq", "GeoJSON Sequence (uma feição por linha)", "GeoJSONSeq", "geojsonl",
        "application/geo+json-seq", None, 4326, "nativa",
        opcoes_camada=("RS=YES",),
        avisos_inerentes=("reprojetado para EPSG:4326 (exigência da RFC 7946)",),
    ),
    "csv": FormatoSaida(
        "csv", "CSV (geometria em WKT, separador ';')", "CSV", "csv", "text/csv", None, None, "wkt",
        opcoes_camada=("GEOMETRY=AS_WKT", "SEPARATOR=SEMICOLON", "WRITE_BOM=YES"),
        avisos_inerentes=("a geometria vai na coluna WKT (CSV não tem geometria própria)",),
    ),
    "xlsx": FormatoSaida(
        "xlsx", "Planilha XLSX (geometria em coluna WKT)", "XLSX", "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", None, None, "wkt",
        avisos_inerentes=(
            "o driver XLSX do GDAL não grava geometria (medido em 06/09/2026): a exportação acrescenta a "
            "coluna geometria_wkt",
        ),
    ),
    "kml": FormatoSaida(
        "kml", "KML", "LIBKML", "kml", "application/vnd.google-earth.kml+xml", None, 4326, "nativa",
        avisos_inerentes=(
            "reprojetado para EPSG:4326 (exigência do KML)",
            "campo data-hora vira elemento TimeStamp do KML (medido em 06/09/2026: o campo sai da tabela "
            "de atributos na releitura)",
        ),
    ),
    "kmz": FormatoSaida(
        "kmz", "KMZ (KML zipado)", "LIBKML", "kmz", "application/vnd.google-earth.kmz", None, 4326, "nativa",
        avisos_inerentes=(
            "reprojetado para EPSG:4326 (exigência do KML)",
            "campo data-hora vira elemento TimeStamp do KML (medido em 06/09/2026: o campo sai da tabela "
            "de atributos na releitura)",
        ),
    ),
    "filegdb.zip": FormatoSaida(
        "filegdb.zip", "File Geodatabase (zip)", "OpenFileGDB", "zip", "application/zip", "zip_gdb",
        None, "nativa",
        avisos_inerentes=(
            "escrito pelo driver OpenFileGDB do GDAL — o mesmo driver que o QGIS usa para abrir FileGDB",
        ),
    ),
    "mbtiles": FormatoSaida(
        "mbtiles", "Tiles vetoriais MBTiles", "MVT", "mbtiles", "application/vnd.sqlite3", None, 3857,
        "tile",
        opcoes_dataset=(f"MAXZOOM={limites.INTERCAMBIO_MVT_ZOOM}",),
        avisos_inerentes=(_AVISO_TILE, "reprojetado para EPSG:3857 (grade web dos tiles)"),
    ),
    "pmtiles": FormatoSaida(
        "pmtiles", "Tiles vetoriais PMTiles", "PMTiles", "pmtiles", "application/octet-stream", None, 3857,
        "tile",
        opcoes_dataset=(f"MAXZOOM={limites.INTERCAMBIO_MVT_ZOOM}",),
        avisos_inerentes=(_AVISO_TILE, "reprojetado para EPSG:3857 (grade web dos tiles)"),
    ),
}

# Paridade com o que o GDAL desta máquina lê/escreve mas NÓS não oferecemos, com o motivo — a resposta
# "temos / não temos" da rota GET /api/intercambio/formatos (nunca um total de formatos).
NAO_TEMOS: tuple[dict, ...] = (
    {"formato": "DXF (saída no intercâmbio em lote)",
     "motivo": "o formato CAD não tem tabela de atributos, então a cláusula 'geometria E atributos "
     "preservados' deste item falharia. A exportação avulsa (POST /api/exportacoes, item L0-04-h) OFERECE "
     "DXF, declarando que os atributos não vão. Entrada de DXF/DWG: item irmão L0-04-e-formatos-cad."},
    {"formato": "GeoParquet (saída no intercâmbio em lote)",
     "motivo": "o driver Parquet está ausente do GDAL 3.8.4 desta máquina (medido em ogrinfo --formats, "
     "06/09/2026). A exportação avulsa (L0-04-h) gera GeoParquet por outro caminho (DuckDB), que não vale "
     "para o escrow multicamada nem para o lote."},
    {"formato": "MSSQLSpatial", "motivo": "o driver existe no GDAL 3.8.4 da máquina, mas não há servidor "
     "SQL Server para provar ida e volta; sem prova, não se oferece."},
    {"formato": "Oracle (OCI)", "motivo": "driver OCI ausente do GDAL 3.8.4 desta máquina (medido em "
     "ogrinfo --formats, 06/09/2026)."},
    {"formato": "entrada de KML/KMZ, XLSX, FileGDB, GeoJSONSeq, DXF/DWG",
     "motivo": "a IMPORTAÇÃO desta instalação lê 4 formatos (shapefile.zip, gpkg, geojson, csv — item "
     "L0-04); o lote deste item chama esses mesmos conversores N vezes, não acrescenta formato de entrada. "
     "Os formatos de entrada novos são dos itens irmãos L0-04-e (CAD) e L0-04-f (FileGDB). A lista viva de "
     "entrada é o campo `importacao` desta mesma resposta."},
)

# Formatos de ENTRADA novos deste item (a ingestão dos 4 originais é do L0-04); a paridade completa de
# entrada sai de app.ingestao.formatos.FORMATOS.
DRIVERS_ESPERADOS = {
    "gpkg": "GPKG", "shapefile.zip": "ESRI Shapefile", "geojson": "GeoJSON", "geojsonseq": "GeoJSONSeq",
    "csv": "CSV", "xlsx": "XLSX", "kml": "LIBKML", "kmz": "LIBKML", "filegdb.zip": "OpenFileGDB",
    "mbtiles": "MVT", "pmtiles": "PMTiles",
}


def formato_saida(nome: str) -> FormatoSaida:
    f = FORMATOS_SAIDA.get(nome)
    if f is None:
        raise KeyError(nome)
    return f
