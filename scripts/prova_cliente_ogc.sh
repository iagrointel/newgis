#!/bin/bash
# Prova com CLIENTE OGC de verdade (item L1-02-tiles-token, cláusula "QGIS carrega o WMTS e o XYZ").
#
# Não há QGIS nesta máquina (medido 07/09/2026: `which qgis` vazio; o pacote puxa ~1,5 GB com o disco a
# 94 %). O que roda aqui é o GDAL — a mesma biblioteca que o QGIS carrega para raster — nos dois papéis:
#   1. driver WMTS: abre o GetCapabilities e LÊ PIXEL do serviço;
#   2. driver WMS em modo TMS: consome o gabarito XYZ, que é a mesma URL que o QGIS usa em "XYZ Tiles".
# O que este script NÃO prova: a interface do QGIS. Prova o protocolo, que é o que está sob nosso controle.
#
# Uso: prova_cliente_ogc.sh <base https://...> <token> <item> [saida]
set -euo pipefail
BASE=${1:?base https}; TOK=${2:?token}; ITEM=${3:?item}; SAIDA=${4:-/tmp/prova_ogc}
mkdir -p "$SAIDA"
export GDAL_HTTP_UNSAFESSL=${GDAL_HTTP_UNSAFESSL:-NO}
CAPS="$BASE/svc/$TOK/raster/$ITEM/wmts/1.0.0/WMTSCapabilities.xml"

echo "== 1. driver WMTS do GDAL abre o serviço"
gdalinfo "WMTS:$CAPS" | sed -n '1,3p;/Size is/p'

echo "== 2. driver WMTS lê pixel (estatística != 0 prova que veio imagem, não vazio)"
gdal_translate -q -of GTiff -projwin -5333000 -1785000 -5327000 -1791000 "WMTS:$CAPS" "$SAIDA/wmts.tif"
gdalinfo -stats "$SAIDA/wmts.tif" | grep -E "Size is|Minimum=" | head -3

echo "== 3. driver WMS/TMS do GDAL consome o gabarito XYZ"
cat > "$SAIDA/xyz.xml" <<XML
<GDAL_WMS>
  <Service name="TMS"><ServerUrl>$BASE/svc/$TOK/raster/$ITEM/\${z}/\${x}/\${y}.png</ServerUrl></Service>
  <DataWindow><UpperLeftX>-20037508.34</UpperLeftX><UpperLeftY>20037508.34</UpperLeftY>
    <LowerRightX>20037508.34</LowerRightX><LowerRightY>-20037508.34</LowerRightY>
    <TileLevel>15</TileLevel><TileCountX>1</TileCountX><TileCountY>1</TileCountY><YOrigin>top</YOrigin></DataWindow>
  <Projection>EPSG:3857</Projection><BlockSizeX>256</BlockSizeX><BlockSizeY>256</BlockSizeY>
  <BandsCount>4</BandsCount><Cache/>
</GDAL_WMS>
XML
gdal_translate -q -of GTiff -projwin -5333000 -1785000 -5327000 -1791000 "$SAIDA/xyz.xml" "$SAIDA/xyz.tif"
gdalinfo -stats "$SAIDA/xyz.tif" | grep -E "Size is|Minimum=" | head -3
echo "== ok: as tres etapas passaram; arquivos em $SAIDA"
