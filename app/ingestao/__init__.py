"""Ingestão vetorial (item L0-04-ingest-vetor; ADR 0005). Núcleo desta passagem: upload reaproveitado do L0-11
(POST /api/arquivos), inspeção (`ingestao.inspecionar`), confirmação do usuário e carga (`ingestao.carregar`) para
shapefile (zip), GeoPackage, GeoJSON e CSV (lat/lon). O que ficou de fora está no handoff do item
(laco/handoffs/T3/L0-04-ingest-vetor.md): KML/KMZ, GPX, XLSX, DXF/DWG, FileGDB/FlatGeobuf/GML, atualizar dados,
exportação, vista de camada e fonte registrada — todos previstos pelo ADR 0005 e adiados para itens L0-04-* futuros.
"""
