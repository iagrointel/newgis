"""Catálogo dos formatos de saída da exportação (itens L0-04-h-exportar e L2-01-l-exportacao-do-mapa; ADR 0018).

Cada linha diz o que o motor precisa saber para gerar o arquivo: driver do GDAL, extensão, tipo de conteúdo,
se o driver escreve num DIRETÓRIO (shapefile) e se aceita geometria/atributo. Nada aqui é opinião: os drivers
e o comportamento de cada um foram MEDIDOS nesta máquina em 06/09/2026 com GDAL 3.8.4 sobre uma camada de
100 mil pontos (`tests/medidas/L0-04-h-exportar.json` guarda o tempo por formato da rodada de teste).

Duas escolhas que custaram medição e não devem ser desfeitas sem repetir a medida:

1. **KML pelo driver `KML`, não `LIBKML`.** Com LIBKML, 50 mil pontos consumiram 3,5 minutos de CPU e 255 MB
   de RSS sem terminar (o driver monta o documento inteiro em memória antes de gravar); com o driver `KML` o
   mesmo recorte saiu em 0,34 s e 56 MB. O KMZ é o zip do KML feito aqui (`zipfile`, que lê do disco em
   blocos), não `-f LIBKML saida.kmz`.
2. **GeoParquet pelo DuckDB, não pelo GDAL.** O GDAL 3.8.4 desta máquina foi compilado SEM o driver Parquet
   (`ogrinfo --formats | grep -i parquet` não devolve nada), então não há como pedir `-f Parquet`. O caminho
   é: ogr2ogr escreve um GPKG intermediário e o DuckDB (extensão `spatial`, já instalada em
   ~/.duckdb/extensions) copia para Parquet — o arquivo sai com o metadado `geo` da especificação GeoParquet
   1.0.0 (conferido com `parquet_kv_metadata`). Consequência honesta: o GeoParquet é o único formato que o
   `ogrinfo` desta máquina NÃO reabre; o teste do portão o reabre com o DuckDB.

**CRS de saída (campo `crs_saida`), medido nesta máquina em 07/09/2026 exportando as MESMAS 500 feições
para cada driver com `-t_srs EPSG:31983` e relendo com `ogrinfo`:**

* `livre` — o arquivo carrega o CRS que se pediu e o `ogrinfo` o devolve com o código EPSG:
  GeoPackage, shapefile, FlatGeobuf, GML, File Geodatabase.
* `4326` — o formato PRENDE o CRS por especificação (GeoJSON RFC 7946, GeoJSON Sequence, KML/KMZ). Pedir
  outro CRS é 422 na entrada, nunca um arquivo com coordenada projetada sob o rótulo WGS 84: medido que o
  driver GeoJSONSeq escreve a coordenada transformada e MESMO ASSIM declara EPSG:4326, que é exatamente o
  arquivo mentiroso que a recusa evita.
* `3857` — pirâmide de tiles (MVT, PMTiles): o CRS é o do esquema de tile, não uma escolha.
* `nenhum` — o formato não guarda CRS (CSV, XLSX, DXF). A reprojeção continua valendo para os números
  gravados, mas o arquivo não diz em que CRS eles estão; o relatório da exportação diz.

Codificação: só o shapefile e o CSV aceitam ISO-8859-1 (o primeiro pela opção de criação `ENCODING` do driver,
o segundo na reescrita em `csv_saida.py`). Os demais são UTF-8 por definição do próprio formato (GeoJSON, GML, KML,
XLSX, GPKG, FlatGeobuf, Parquet) — pedir outra coisa é 422, nunca um arquivo mal codificado em silêncio.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Formato:
    nome: str
    driver: str                      # driver do GDAL ("" quando o arquivo não é escrito pelo ogr2ogr)
    extensao: str                    # extensão do arquivo entregue ao usuário
    content_type: str
    rotulo: str
    em_diretorio: bool = False       # o driver escreve vários arquivos num diretório (shapefile)
    zipar: bool = False              # o que sai é um zip do que o driver escreveu
    guarda_atributos: bool = True
    guarda_geometria: bool = True
    codificacoes: tuple[str, ...] = ("UTF-8",)
    lco: tuple[str, ...] = ()        # opções de criação de camada fixas
    dsco: tuple[str, ...] = ()       # opções de criação de fonte fixas
    observacao: str = ""
    reabre_com_ogrinfo: bool = True
    opcoes_csv: bool = False
    crs_saida: str = "livre"         # "livre" | "4326" | "3857" | "nenhum" (ver bloco CRS no topo)
    caminho_interno: str = ""        # nome da pasta/arquivo DENTRO do zip (formatos que zipam um diretório)
    linhas_max: int = 0              # teto de linhas do PRÓPRIO formato (0 = sem teto); XLSX = 1.048.576
    tilado: bool = False             # o arquivo é um conjunto de tiles: a contagem de feições não é a do banco
    nome_camada_alfanumerico: bool = False   # o driver recusa nome de camada com hífen/ponto (File Geodatabase)


FORMATOS: dict[str, Formato] = {f.nome: f for f in (
    Formato("gpkg", "GPKG", ".gpkg", "application/geopackage+sqlite3", "GeoPackage"),
    Formato("geojson", "GeoJSON", ".geojson", "application/geo+json", "GeoJSON",
            lco=("RFC7946=YES",), crs_saida="4326",
            observacao="RFC 7946: coordenada sempre em EPSG:4326 (o driver reprojeta; é o que a especificação "
                       "exige). Para outro CRS, use GeoPackage ou FlatGeobuf."),
    Formato("shapefile", "ESRI Shapefile", ".zip", "application/zip", "Shapefile (zip)",
            em_diretorio=True, zipar=True, codificacoes=("UTF-8", "ISO-8859-1"),
            observacao="nome de campo truncado em 10 caracteres e tipos limitados são do FORMATO, não da "
                       "plataforma; o relatório da exportação lista o que o driver avisou."),
    Formato("csv", "CSV", ".csv", "text/csv", "CSV", guarda_geometria=False,
            codificacoes=("UTF-8", "ISO-8859-1"), opcoes_csv=True, crs_saida="nenhum",
            observacao="a geometria vira colunas X/Y (nomes escolhidos pelo usuário) ou uma coluna WKT."),
    Formato("xlsx", "XLSX", ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel (XLSX)",
            guarda_geometria=False, crs_saida="nenhum", linhas_max=1_048_576,
            observacao="planilha só de atributos (o formato não tem geometria); teto de 1.048.576 linhas do "
                       "próprio Excel."),
    Formato("kml", "KML", ".kml", "application/vnd.google-earth.kml+xml", "KML", crs_saida="4326"),
    Formato("kmz", "KML", ".kmz", "application/vnd.google-earth.kmz", "KMZ", zipar=True, crs_saida="4326",
            observacao="zip do KML gerado (nome interno doc.kml)."),
    Formato("fgb", "FlatGeobuf", ".fgb", "application/octet-stream", "FlatGeobuf"),
    Formato("gml", "GML", ".gml", "application/gml+xml", "GML"),
    Formato("dxf", "DXF", ".dxf", "image/vnd.dxf", "DXF", guarda_atributos=False, crs_saida="nenhum",
            observacao="o DXF guarda só geometria: o driver recusa criar campo de atributo (medido em "
                       "06/09/2026 — 'DXF layer does not support arbitrary field creation'). Quem precisa de "
                       "atributo exporta outro formato."),
    Formato("geojsonseq", "GeoJSONSeq", ".geojsonl", "application/geo+json-seq", "GeoJSON Sequence",
            crs_saida="4326",
            observacao="uma feição por linha (streaming). O driver declara sempre EPSG:4326, por isso a "
                       "exportação REPROJETA para 4326 em vez de gravar coordenada de outro CRS sob um "
                       "rótulo errado."),
    Formato("filegdb", "OpenFileGDB", ".zip", "application/zip", "File Geodatabase (zip)",
            em_diretorio=True, zipar=True, caminho_interno="dados.gdb", nome_camada_alfanumerico=True,
            observacao="a .gdb é uma PASTA; o que se entrega é o zip dela, com a pasta dentro "
                       "(reabre em /vsizip/<arquivo>.zip/dados.gdb). Escrita pelo OpenFileGDB do próprio "
                       "GDAL, sem o SDK proprietário da Esri."),
    Formato("mvt", "MVT", ".zip", "application/zip", "Mapbox Vector Tiles (zip)",
            em_diretorio=True, zipar=True, caminho_interno="tiles", crs_saida="3857", tilado=True,
            guarda_geometria=True,
            observacao="pirâmide de tiles z/x/y + metadata.json, zipada. A geometria é RECORTADA por tile e "
                       "generalizada por zoom: a contagem de feições do arquivo NÃO é a do banco e não deve "
                       "ser usada como conferência."),
    Formato("pmtiles", "PMTiles", ".pmtiles", "application/vnd.pmtiles", "PMTiles",
            crs_saida="3857", tilado=True,
            observacao="a mesma pirâmide do MVT num arquivo único com índice (PMTiles v3), servível por "
                       "range request. Vale a mesma ressalva: a contagem é por tile, não do banco."),
    Formato("pacote", "", ".zip", "application/zip", "Pacote de mapa",
            zipar=True, reabre_com_ogrinfo=False,
            observacao="o MAPA inteiro: documento, estilos (MapLibre e SLD 1.0) e os dados das camadas "
                       "citadas num GeoPackage só, para levar a outra instalação. A origem é um item do "
                       "tipo `mapa`, não uma camada."),
    Formato("geoparquet", "GPKG", ".parquet", "application/vnd.apache.parquet", "GeoParquet",
            reabre_com_ogrinfo=False,
            observacao="gerado pelo DuckDB a partir de um GPKG intermediário (o GDAL desta instalação não tem "
                       "driver Parquet); metadado `geo` GeoParquet 1.0.0."),
)}

NOMES = tuple(FORMATOS)


def obter(nome: str) -> Formato | None:
    return FORMATOS.get((nome or "").strip().lower())


def descrever() -> list[dict]:
    """Linha de `GET /api/exportacoes/formatos` (o que a tela do botão Exportar desenha)."""
    saida = []
    for f in FORMATOS.values():
        saida.append({
            "nome": f.nome, "rotulo": f.rotulo, "extensao": f.extensao, "content_type": f.content_type,
            "guarda_geometria": f.guarda_geometria, "guarda_atributos": f.guarda_atributos,
            "codificacoes": list(f.codificacoes), "opcoes_csv": f.opcoes_csv, "observacao": f.observacao,
            "crs_saida": f.crs_saida, "linhas_max": f.linhas_max, "tilado": f.tilado,
        })
    return saida


__all__ = ["FORMATOS", "NOMES", "Formato", "descrever", "obter"]
