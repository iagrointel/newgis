"""Catálogo dos formatos de saída da exportação (item L0-04-h-exportar; ADR 0018).

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


FORMATOS: dict[str, Formato] = {f.nome: f for f in (
    Formato("gpkg", "GPKG", ".gpkg", "application/geopackage+sqlite3", "GeoPackage"),
    Formato("geojson", "GeoJSON", ".geojson", "application/geo+json", "GeoJSON",
            lco=("RFC7946=YES",),
            observacao="RFC 7946: coordenada sempre em EPSG:4326 (o driver reprojeta; é o que a especificação "
                       "exige). Para outro CRS, use GeoPackage ou FlatGeobuf."),
    Formato("shapefile", "ESRI Shapefile", ".zip", "application/zip", "Shapefile (zip)",
            em_diretorio=True, zipar=True, codificacoes=("UTF-8", "ISO-8859-1"),
            observacao="nome de campo truncado em 10 caracteres e tipos limitados são do FORMATO, não da "
                       "plataforma; o relatório da exportação lista o que o driver avisou."),
    Formato("csv", "CSV", ".csv", "text/csv", "CSV", guarda_geometria=False,
            codificacoes=("UTF-8", "ISO-8859-1"), opcoes_csv=True,
            observacao="a geometria vira colunas X/Y (nomes escolhidos pelo usuário) ou uma coluna WKT."),
    Formato("xlsx", "XLSX", ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel (XLSX)",
            guarda_geometria=False,
            observacao="planilha só de atributos (o formato não tem geometria); teto de 1.048.576 linhas do "
                       "próprio Excel."),
    Formato("kml", "KML", ".kml", "application/vnd.google-earth.kml+xml", "KML"),
    Formato("kmz", "KML", ".kmz", "application/vnd.google-earth.kmz", "KMZ", zipar=True,
            observacao="zip do KML gerado (nome interno doc.kml)."),
    Formato("fgb", "FlatGeobuf", ".fgb", "application/octet-stream", "FlatGeobuf"),
    Formato("gml", "GML", ".gml", "application/gml+xml", "GML"),
    Formato("dxf", "DXF", ".dxf", "image/vnd.dxf", "DXF", guarda_atributos=False,
            observacao="o DXF guarda só geometria: o driver recusa criar campo de atributo (medido em "
                       "06/09/2026 — 'DXF layer does not support arbitrary field creation'). Quem precisa de "
                       "atributo exporta outro formato."),
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
        })
    return saida


__all__ = ["FORMATOS", "NOMES", "Formato", "descrever", "obter"]
