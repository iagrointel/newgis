# Dados de demonstração instalados com o appliance

Este arquivo lista todo dado de terceiro que o instalador ou a galeria de mapas base (item
L2-01-e-mapas-base) instala por padrão, com licença, atribuição obrigatória e proveniência —
exigido pelo portão de pronto do item. Nenhuma fonte aqui é dado de cliente.

## Mapas base (galeria, `plat.item` tipo `mapa_base`)

| # | fonte | tipo de instalação | atribuição (`item.creditos`) | licença (`item.termos_de_uso`) | proveniência |
|---|---|---|---|---|---|
| 1 | OpenStreetMap (recorte de Guarulhos-SP) | PMTiles vetorial local, servido por Range HTTP pelo próprio nginx (`web/dados/basemap/guarulhos.pmtiles`) | © colaboradores do OpenStreetMap | ODbL 1.0 (Open Database License) — https://opendatacommons.org/licenses/odbl/1-0/ | `web/dados/basemap/PROVENIENCIA.md` (item L2-01-a-basemap-local-pmtiles); extraído com `ogr2ogr` + `tippecanoe` de um extrato OSM datado |
| 2 | OpenStreetMap (padrão, "Standard" tile layer) | raster, por proxy próprio com cache em disco e `User-Agent` identificado (`GET /api/mapas-base/osm/{z}/{x}/{y}.png`, nunca o navegador direto — política de uso do OSM) | © colaboradores do OpenStreetMap | dado ODbL 1.0; estilo cartográfico "Standard" sob CC BY-SA 2.0 — ver https://www.openstreetmap.org/copyright | política de uso: https://operations.osmfoundation.org/policies/tiles/ (uso pesado sem cache é proibido; daí o proxy) |
| 3 | Sentinel-2 (mosaico da casa) | raster, servido direto pelo navegador a partir de um TiTiler (`PLAT_TITILER_URL`, item L1-02), COG único (cena 23KLQ) | Contém dados Copernicus Sentinel modificados, processados pela casa via TiTiler | reuso livre conforme a Política de Dados e Informação do Programa Copernicus (Regulamento (UE) nº 1159/2013) | cena baixada e convertida a COG (`s2-23klq-20260818_visual*.tif`, banda visual RGB) no balde de objetos da própria casa; instalada só quando `PLAT_TITILER_URL` está configurado — sem isso a fonte 3 não entra na galeria |
| 4 | (nenhuma) | fundo de cor sólida, sem fonte externa | — | — | sem dado de terceiro; sempre disponível |

## Regra de instalação

`app/mapas_base/semear.py` só cria os itens 1, 2 e 4 sempre; o item 3 (satélite) só entra quando o
inquilino técnico tem `PLAT_TITILER_URL` configurado (produção não tem por padrão — ver `.env`).
`POST /api/mapas-base/instalar` é idempotente: chamar de novo não duplica nem sobrescreve um item
que o admin já editou (título/ordem/padrão mudados manualmente).

## Por que nenhuma licença aqui é "livre para qualquer uso"

ODbL exige atribuição e "share-alike" de bases de dados derivadas; CC BY-SA da cartografia OSM
exige atribuição e mesma licença de trabalhos derivados; a Política de Dados do Copernicus é aberta
mas cita a UE/ESA como titular dos dados originais. A atribuição visível no canto do mapa (DOM) e a
listagem acima cobrem a exigência de atribuição das três licenças; nenhuma delas autoriza remover a
atribuição, mesmo em relatório impresso.
