#!/bin/bash
# Deriva os arquivos de teste (dado aberto, ≤ 5 MB) a partir dos 3 GeoJSON exportados do iagro_sat
set -u; cd "$(dirname "$0")"; L=gerar.log; : > $L
t(){ echo "== $*" | tee -a $L; }
r(){ "$@" >> $L 2>&1; echo "rc=$?" >> $L; }
t gpkg 3 camadas; r ogr2ogr -f GPKG dados.gpkg municipios.geojson -nln municipios -nlt PROMOTE_TO_MULTI; r ogr2ogr -f GPKG -update dados.gpkg ferrovias_4674.geojson -nln ferrovias; r ogr2ogr -f GPKG -update dados.gpkg heliportos_4674.geojson -nln heliportos
t shapefile utf8 + zip; mkdir -p shp; r ogr2ogr -f "ESRI Shapefile" shp/municipios.shp municipios.geojson -lco ENCODING=UTF-8 -nlt PROMOTE_TO_MULTI; (cd shp && zip -q ../municipios_shp.zip municipios.*)
t shapefile sem prj; mkdir -p shp_semprj; cp shp/municipios.shp shp/municipios.shx shp/municipios.dbf shp/municipios.cpg shp_semprj/; (cd shp_semprj && zip -q ../municipios_semprj.zip municipios.*)
t shapefile latin1 sem cpg; mkdir -p shp_l1; r ogr2ogr -f "ESRI Shapefile" shp_l1/municipios_l1.shp municipios.geojson -lco ENCODING=ISO-8859-1 -nlt PROMOTE_TO_MULTI; rm -f shp_l1/municipios_l1.cpg; (cd shp_l1 && zip -q ../municipios_latin1_semcpg.zip municipios_l1.*)
t shapefile zip com 2 shapefiles; mkdir -p shp2; r ogr2ogr -f "ESRI Shapefile" shp2/heliportos.shp heliportos_4674.geojson -lco ENCODING=UTF-8; cp shp/municipios.* shp2/; (cd shp2 && zip -q ../dois_shapefiles.zip *)
t kml pastas + kmz; r ogr2ogr -f LIBKML pastas.kml dados.gpkg; r ogr2ogr -f LIBKML pastas.kmz dados.gpkg
t gml 3.2; r ogr2ogr -f GML municipios.gml municipios.geojson -dsco FORMAT=GML3.2 -nlt PROMOTE_TO_MULTI
t fgb; r ogr2ogr -f FlatGeobuf ferrovias.fgb ferrovias_4674.geojson
t geojsonseq; r ogr2ogr -f GeoJSONSeq heliportos.geojsonl heliportos_4674.geojson
t xlsx 2 planilhas; r ogr2ogr -f XLSX heliportos.xlsx heliportos_4674.geojson -sql "SELECT nome, tipo, cidade, uf, latitude_dec AS latitude, longitude_dec AS longitude, elevacao, efetivacao FROM heliportos" -nln heliportos; r ogr2ogr -f XLSX -update heliportos.xlsx municipios.geojson -sql "SELECT \"Código IBGE\", \"Município\", \"Área km²\" FROM municipios" -nln municipios
t gpx; r ogr2ogr -f GPX heliportos.gpx heliportos_4674.geojson -nlt POINT -explodecollections -nln waypoints -sql "SELECT nome AS name, tipo AS desc, elevacao AS ele FROM heliportos" -dsco GPX_USE_EXTENSIONS=NO
t dxf linhas; r ogr2ogr -f DXF ferrovias.dxf ferrovias_4674.geojson -t_srs EPSG:31984 -sql "SELECT linha AS Layer FROM ferrovias"
t crs legado 31984; r ogr2ogr -f GeoJSON municipios_31984.geojson municipios.geojson -t_srs EPSG:31984 -lco RFC7946=NO
t mapinfo tab; r ogr2ogr -f "MapInfo File" municipios.tab municipios.geojson -nlt PROMOTE_TO_MULTI; zip -q municipios_tab.zip municipios.tab municipios.dat municipios.id municipios.map
t csv por python; python3 - <<'EOF'
import json, csv, io
h = json.load(open('heliportos_4674.geojson'))
# a) ponto e virgula + virgula decimal + BOM + lat/long por nome, com 'Elevação' 1.234,5
with open('heliportos_pv.csv','w',encoding='utf-8-sig',newline='') as f:
    w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    w.writerow(['Nome','Tipo','Cidade','UF','lat','long','Elevação (m)','Data'])
    for ft in h['features']:
        p = ft['properties']; x,y = ft['geometry']['coordinates'][0]
        elev = p['elevacao'] if p['elevacao'] is not None else 1234.5
        w.writerow([p['nome'],p['tipo'],p['cidade'],p['uf'],f"{y:.6f}".replace('.',','),f"{x:.6f}".replace('.',','),f"{elev:,.1f}".replace(',','X').replace('.',',').replace('X','.'),(p.get('efetivacao') or '2020-01-15').replace('-','/')])
# b) WKT, virgula, sem coordenada nomeada
m = json.load(open('municipios.geojson'))
with open('municipios_wkt.csv','w',encoding='utf-8',newline='') as f:
    w = csv.writer(f); w.writerow(['codigo','nome','WKT'])
    from json import dumps
    for ft in m['features'][:20]:
        g = ft['geometry']; rings = g['coordinates'] if g['type']=='Polygon' else g['coordinates'][0]
        wkt = 'POLYGON(' + ','.join('(' + ','.join(f'{x} {y}' for x,y in r) + ')' for r in rings) + ')'
        w.writerow([ft['properties']['Código IBGE'], ft['properties']['Município'], wkt])
# c) tabela sem geometria (latin-1, tabulacao)
with open('tabela_sem_geom.txt','w',encoding='latin-1',newline='') as f:
    w = csv.writer(f, delimiter='\t'); w.writerow(['Código','Município','População estimada'])
    for ft in m['features']: w.writerow([ft['properties']['Código IBGE'], ft['properties']['Município'], 12345])
# d) 300 colunas e 0 linhas
open('csv_300col_0lin.csv','w').write(','.join(f'c{i}' for i in range(300))+'\n')
# e) aspas desbalanceadas
open('csv_aspas.csv','w').write('nome,lat,lon\n"Heliponto A,-10.9,-37.1\n"B",-10.8,-37.0\n')
# f) nome de campo duplicado e com espaco/acento
open('csv_dup.csv','w').write('Município,Município,Área km²,lat,lon\nA,B,1.5,-10.9,-37.1\n')
# geojson auto-intersectado (gravata) + valido
bow = {"type":"FeatureCollection","features":[
 {"type":"Feature","properties":{"nome":"gravata"},"geometry":{"type":"Polygon","coordinates":[[[-37.1,-10.9],[-37.0,-10.8],[-37.1,-10.8],[-37.0,-10.9],[-37.1,-10.9]]]}},
 {"type":"Feature","properties":{"nome":"ok"},"geometry":{"type":"Polygon","coordinates":[[[-37.3,-10.9],[-37.2,-10.9],[-37.2,-10.8],[-37.3,-10.8],[-37.3,-10.9]]]}},
 {"type":"Feature","properties":{"nome":"anel_nao_fechado_e_duplicado"},"geometry":{"type":"Polygon","coordinates":[[[-37.5,-10.9],[-37.4,-10.9],[-37.4,-10.9],[-37.4,-10.8],[-37.5,-10.8]]]}}]}
json.dump(bow, open('gravata.geojson','w'))
# geojson misto ponto+poligono
mix = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"a":1},"geometry":{"type":"Point","coordinates":[-37.1,-10.9]}},{"type":"Feature","properties":{"a":2},"geometry":{"type":"Polygon","coordinates":[[[-37.3,-10.9],[-37.2,-10.9],[-37.2,-10.8],[-37.3,-10.9]]]}}]}
json.dump(mix, open('misto.geojson','w'))
# dxf com blocos, texto, polilinha, linha, unidades em metros (INSUNITS 6), sem CRS
dxf = ['0','SECTION','2','HEADER','9','$ACADVER','1','AC1015','9','$INSUNITS','70','6','0','ENDSEC',
 '0','SECTION','2','TABLES','0','TABLE','2','LAYER','70','3',
 '0','LAYER','2','LOTES','70','0','62','7','6','CONTINUOUS','0','LAYER','2','VEGETACAO','70','0','62','3','6','CONTINUOUS','0','LAYER','2','TEXTOS','70','0','62','1','6','CONTINUOUS','0','ENDTAB','0','ENDSEC',
 '0','SECTION','2','BLOCKS','0','BLOCK','8','0','2','ARVORE','70','0','10','0','20','0','30','0','3','ARVORE',
 '0','CIRCLE','8','0','10','0','20','0','30','0','40','2.5','0','LINE','8','0','10','0','20','0','30','0','11','0','21','4','31','0','0','ENDBLK','8','0','0','ENDSEC',
 '0','SECTION','2','ENTITIES']
for i,(x,y) in enumerate([(700010,8790010),(700030,8790015),(700050,8790020)]):
    dxf += ['0','INSERT','8','VEGETACAO','2','ARVORE','10',str(x),'20',str(y),'30','0','41','1','42','1','43','1','50',str(15*i)]
dxf += ['0','LWPOLYLINE','8','LOTES','90','4','70','1','10','700000','20','8790000','10','700020','20','8790000','10','700020','20','8790012','10','700000','20','8790012']
dxf += ['0','LINE','8','LOTES','10','700000','20','8790012','30','0','11','700060','21','8790012','31','0']
dxf += ['0','TEXT','8','TEXTOS','10','700005','20','8790005','30','0','40','2','1','LOTE 01']
dxf += ['0','ENDSEC','0','EOF']
open('blocos.dxf','w').write('\n'.join(dxf)+'\n')
# dxf binario (assinatura) e dxf em polegada
open('binario.dxf','wb').write(b'AutoCAD Binary DXF\r\n\x1a\x00' + b'\x00'*64)
open('polegada.dxf','w').write('\n'.join(dxf).replace("'70','6'","'70','1'").replace('$INSUNITS\n70\n6','$INSUNITS\n70\n1')+'\n')
print('csv/geojson/dxf gerados')
EOF
t nome de camada com controle; r ogr2ogr -f GPKG controle.gpkg municipios.geojson -nln "$(printf 'mun\001icipios')"
t tamanhos; ls -la | awk '{s+=$5} END{print "total bytes", s}' | tee -a $L; du -sh . | tee -a $L
