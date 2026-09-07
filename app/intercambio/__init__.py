"""Intercâmbio de formatos (item L6-02-o-importacao-exportacao-formatos): exportação de camada vetorial nos
formatos que o GDAL desta máquina escreve e que ainda não estavam no L0-04-h (geojsonseq, filegdb.zip, mbtiles,
pmtiles), escrow do inquilino inteiro em GeoPackage + manifesto JSON, importação em LOTE (N arquivos numa
chamada, sobre os conversores do L0-04) e a paridade "temos / não temos" de formatos.

⛔ A ENTRADA de formato NOVO (KML/KMZ, XLSX, FileGDB, DXF/DWG) NÃO está aqui e não está no L0-04: a importação
desta instalação lê 4 formatos (shapefile.zip, gpkg, geojson, csv), e ampliá-la é dos itens irmãos L0-04-e
(CAD) e L0-04-f (FileGDB). O lote deste item repete os conversores existentes; não inventa formato de entrada.
A lista viva sai de `GET /api/intercambio/formatos` (campos `importacao`, `exportacao`, `nao_temos`)."""
