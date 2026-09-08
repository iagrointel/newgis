#!/bin/bash
cd <scratchpad>/adr0005; L=carga.log; : > $L
DSN='postgresql://plat_app:<senha>@127.0.0.1:5432/iagro_sat'
carga(){ # nome arquivo [extras]
  n=$1; f=$2; shift 2
  /usr/bin/time -f "TEMPO %e s RSS %M kB" -o t.txt ogr2ogr -f PostgreSQL "PG:$DSN" "$f" -nln adr0005_tmp.$n -nlt PROMOTE_TO_MULTI -lco GEOMETRY_NAME=geom -lco FID=fid -lco SPATIAL_INDEX=NONE -lco PRECISION=NO --config PG_USE_COPY YES "$@" > o.txt 2>&1; rc=$?
  echo "== $n rc=$rc $(cat t.txt) | $(grep -v '^$' o.txt | head -3 | tr '\n' ' ' | cut -c1-260)" >> $L
}
carga gpkg_municipios dados.gpkg municipios
carga gpkg_ferrovias dados.gpkg ferrovias
carga gpkg_heliportos dados.gpkg heliportos
carga shp_utf8 /vsizip/municipios_shp.zip
carga shp_semprj /vsizip/municipios_semprj.zip
carga shp_semprj_asrs /vsizip/municipios_semprj.zip -a_srs EPSG:4674
carga shp_latin1 /vsizip/municipios_latin1_semcpg.zip -oo ENCODING=ISO-8859-1
carga kml_municipios pastas.kml municipios
carga gml municipios.gml
carga fgb ferrovias.fgb
carga geojsonl heliportos.geojsonl
carga xlsx_heliportos heliportos.xlsx heliportos -oo AUTODETECT_TYPE=YES
carga geojson_31984 municipios_31984.geojson
carga geojson_misto misto.geojson
carga geojson_gravata gravata.geojson
carga csv_pv heliportos_pv.csv -oo AUTODETECT_TYPE=YES -oo X_POSSIBLE_NAMES=long -oo Y_POSSIBLE_NAMES=lat -a_srs EPSG:4674
carga csv_wkt municipios_wkt.csv -oo AUTODETECT_TYPE=YES -oo GEOM_POSSIBLE_NAMES=WKT -a_srs EPSG:4326
carga txt_sem_geom tabela_sem_geom.txt -oo AUTODETECT_TYPE=YES
carga dxf_blocos blocos.dxf -a_srs EPSG:31984
carga dxf_linhas ferrovias.dxf -a_srs EPSG:31984
carga tab /vsizip/municipios_tab.zip
carga gpx heliportos.gpx waypoints
carga csv_aspas csv_aspas.csv -oo AUTODETECT_TYPE=YES -oo X_POSSIBLE_NAMES=lon -oo Y_POSSIBLE_NAMES=lat
carga csv_dup csv_dup.csv -oo AUTODETECT_TYPE=YES
cat $L
