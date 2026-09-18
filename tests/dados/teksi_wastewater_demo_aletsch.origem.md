# Origem do `teksi_wastewater_demo_aletsch.gpkg`

GeoPackage com os dados de exemplo OFICIAIS do projeto TEKSI wastewater
(https://teksi.github.io/wastewater/), usado pelo item L4-05-e-gas-e-esgoto para provar a
importação do esquema TEKSI contra dado real do projeto, e não contra um arquivo fabricado em casa.

O projeto TEKSI não publica um `.gpkg` de amostra: o dado de exemplo oficial é o "demo dataset"
da comuna de Aletsch (Valais, Suíça), publicado como dump PostgreSQL no release `2026.1.0` de
https://github.com/teksi/wastewater. Este arquivo é as duas views de trabalho do modelo
(`vw_tww_wastewater_structure`, `vw_tww_reach`) exportadas para GeoPackage, sem filtro e sem
edição de dado.

## Cadeia de origem

1. Download de `datamodel-dumps.zip` do release 2026.1.0:
   https://github.com/teksi/wastewater/releases/download/2026.1.0/datamodel-dumps.zip
   sha256 do zip: `a4da2fab4740ad9bda2aa6bb794cad067c9d169f1272cc0b4446fc456714961e`
2. De dentro, `datamodel/artifacts/tww-2026.1.0-db-dump-with-demo.sql`
   sha256: `e12cbd0d4209c7219fbcbe617c094f0be55085e6f5c0bbc49505423a3bb89a29`
3. Restauração íntegra (sem tocar no arquivo) num banco vazio descartável com PostGIS.
4. Exportação das duas views com ogr2ogr, reprojetando de EPSG:2056 (LV95, o SRID do modelo)
   para EPSG:4326 e achatando Z (`-dim 2`), que é o que a rede da plataforma guarda:

       ogr2ogr -f GPKG teksi_wastewater_demo_aletsch.gpkg "PG:dbname=<banco descartavel>" \
         -sql "SELECT * FROM tww_app.vw_tww_wastewater_structure" \
         -nln vw_tww_wastewater_structure -t_srs EPSG:4326 -dim 2
       ogr2ogr -f GPKG -update teksi_wastewater_demo_aletsch.gpkg "PG:dbname=<banco descartavel>" \
         -sql "SELECT * FROM tww_app.vw_tww_reach" \
         -nln vw_tww_reach -t_srs EPSG:4326 -dim 2

5. Banco descartável apagado. sha256 do gpkg resultante:
   `f3138640ae8fac5dea5be8ee8eb8cd6fe2eeb6aa08fd324ef38a2f26fb737093`

## O que o dado real trouxe que o sintético não trazia (e o importador aprendeu)

- 5 estruturas cadastradas SEM geometria (o modelo TEKSI admite) — contadas como ignoradas
  com aviso `estrutura_sem_geometria`, em vez de derrubar o lote;
- a espécie `infiltration_installation`, sem grupo correspondente no pacote — aviso
  `especie_sem_correspondencia`, o caminho honesto já existente;
- a progressão do trecho tipada como CompoundCurve (o tipo do datamodel), com 1 arco de
  verdade (CircularString) — segmentos retos achatados em linha; o arco fica de fora com
  aviso `trecho_com_arco` (endireitar arco em silêncio falsificaria a geometria);
- 20 dos 102 trechos sem cota nas duas pontas — dado real tem lacuna, e a conferência de
  escoamento já sabe acusar `cota_ausente`.

Conteúdo: 77 estruturas (71 lidas) e 102 trechos (101 lidos), cotas em metros (região
alpina, ~1300-2000 m), geometria na área de Aletsch (lon 7.97-8.12, lat 46.40-46.55).
