# Terreno: codificador terrain-RGB/Terrarium/normal-map e amostragem de perfil sobre o COG

Item `L2-09-a-terreno-terrain-rgb-relevo`.

## Decisão

1. Três codecs (`app/relevo/codec.py`), todos em numpy puro, sem GDAL na etapa de codificação:
   `terrain_rgb` (Mapbox, passo 0,1 m) para o `setTerrain` do MapLibre; `terrarium` (Mapzen) e
   `normal_map` (Mapzen "normal") porque o Martin 1.15 **não** deriva hillshade/contorno do
   terrain-RGB — o `convert_to_hillshade` lê normal map, o `convert_to_contour` lê Terrarium (achado
   registrado em `app/relevo/__init__.py`, contra a hipótese original do item). O job produz as três
   camadas na mesma leitura da fonte.
2. `app/relevo/malha.py` faz UMA reprojeção por zoom, direto da fonte (GLO-30 ou outro MDT), nunca
   reamostrando um tile de zoom vizinho já codificado — regra da casa.
3. `app/relevo/perfil.py` amostra SEMPRE o COG de origem (`rasterio.sample`), nunca o tile: um perfil
   de 10 km cruzaria dezenas de tiles em vários zooms, e a quantização do codec (0,1 m) não afetaria o
   resultado, mas a reprojeção Web Mercator mudaria a posição das amostras.

## GLO-30 de teste: 2 blocos por `/vsicurl`, sem cópia local

Disco a 95% nos dois volumes (`/` e `/mnt/pgdata`). `laco/var/dem_lorena/lorena_glo30.vrt`
(`gdalbuildvrt` sobre `/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/.../S23_00_W046_00...tif`
e `.../S23_00_W045_00...tif`) é só texto (8 KB) — o raster nunca toca o disco, GDAL lê por streaming
HTTP range request. Cobre Lorena-SP e a serra da Mantiqueira. O VRT `brasil_glo30.vrt` já existente em
`/mnt/pgdata/dem_glo30/` aponta para arquivos locais que nunca foram baixados (pasta `tiles/` vazia) —
não serve para nada hoje; não mexido.

## 20 pontos "conhecidos" do portão de pronto: RN do IBGE via WFS

`bdg.ibge.gov.br` não resolve nesta máquina (DNS). `geoservicos.ibge.gov.br/geoserver/CGED`
(camada `V_INDE_RN_2`, WFS 2.0, filtro `cql_filter` em `LATITUDE`/`LONGITUDE` — o `BBOX()` do CQL
devolveu 400/ExceptionReport nesta instância do GeoServer, não investigado a fundo) devolveu 1.356
estações RN na região; 20 dentro dos 2 blocos do VRT viraram `tests/dados/rn_ibge_lorena.json`.

**O que a cláusula 1 do portão realmente testa**: fidelidade do pipeline codec+tile (tile decodificado
== COG lido direto no mesmo pixel), usando coordenadas reais e espalhadas pelo relevo como amostra —
não a acurácia absoluta do GLO-30 contra a rede geodésica oficial. Isso ficou claro comparando
`alt_ibge_m` (altitude oficial, datum Imbituba) com uma leitura ingênua do GLO-30 no ponto bruto: a
diferença passa de 50 m em vários pontos (serra da Mantiqueira, terreno íngreme + datum vertical
diferente — Imbituba x EGM2008 — não é o mesmo problema). Por isso o teste usa `Resampling.nearest`
e compara contra o **mesmo pixel exato** do COG, não contra a altitude oficial da estação; comparar
contra `alt_ibge_m` exigiria compensar o datum vertical, fora do escopo deste item.

## O que ficou de fora (registrado, não escondido)

Martin 1.15 com `convert_to_hillshade`/`convert_to_contour` sobre as camadas geradas, MapLibre
`setTerrain` com exagero configurável, controle de inclinação/rotação, endpoint de altitude/perfil
(`app/relevo/perfil.py` existe como biblioteca; não há rota HTTP — `L1-01-ingest-raster`, de onde viria
o `raster_item` do catálogo para resolver "qual COG" por inquilino/item, está só PARCIAL nesta árvore),
medição de fps por Playwright, e a varredura do adversário em serra real z10-z14 não foram construídos
nesta rodada. Ver `tests/medidas/L2-09-a-terreno-terrain-rgb-relevo.json` e o handoff.
