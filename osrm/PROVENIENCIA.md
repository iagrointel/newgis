# Proveniência — `guarulhos.osm.pbf` e o grafo OSRM de teste (item L2-11-c-rota-matriz-isocrona)

Recorte pequeno de OSM, isolado, só para o serviço de rota/matriz/isócrona de teste desta plataforma. Sem
nome de cliente, sem PII (regra P7). O serviço serve SÓ este recorte — nunca a base grande de outra frente.

## Fonte e recorte

- Origem: OpenStreetMap, mesmo extrato regional já presente na casa e já usado pelo item
  `L2-01-a-basemap-local-pmtiles` — `/home/dev/cbre/osm/area_estudo.osm.pbf` (135.113.946 bytes; bbox
  `-49,13/-24,27` a `-43,77/-21,80`; nós 17.564.362, vias 2.624.000; timestamp de dado até 2026-08-27).
  OSM © colaboradores do OpenStreetMap, licença **ODbL 1.0** (https://www.openstreetmap.org/copyright).
  Nenhum novo download (disco a 98/99 %, D28 do `L2_CONCEITO.md`).
- Bbox do recorte: `-46,62, -23,53, -46,42, -23,38` (Guarulhos-SP, **mesma área de teste do L2-01-a**;
  ≈ 21 × 17 km) — igual, de propósito, ao mapa-base já publicado, para o mesmo ponto clicado no mapa
  poder chamar rota/matriz/isócrona sem surpresa de cobertura.

## Por que não foi `osmium extract` (o caminho direto)

RAM disponível nesta máquina no momento da extração: **~2,5 GB, swap já praticamente cheio** (medido
`free -h` antes de cada tentativa). `osmium extract -b <bbox> --strategy=complete_ways` e depois
`--strategy=simple`, sob `ulimit -v` crescente (1,2 GB → 1,8 GB → 2,4 GB) para conter o processo num teto
próprio em vez de arriscar o OOM killer do sistema (o incidente do L2-01-a matou um backend do Postgres
por 14 min quando `osmium extract` rodou sem teto) — em **todas** as tentativas o processo dentro do teto
morreu com `Out of memory` (osmium precisa indexar os 17,5 milhões de nós do arquivo INTEIRO para montar o
recorte, não só a área pedida; o teto de 2,4 GB ainda deixou o arquivo pela metade: 3.335.564 nós e ZERO
vias gravadas, confirmado com `osmium check-refs`). Subir o teto mais não foi tentado: RAM do sistema
livre era só ~2,3-2,6 GB o tempo todo; um `ulimit` maior arriscaria o mesmo incidente do Postgres. Nenhum
processo do sistema foi afetado nas tentativas (o `ulimit -v` mata só o próprio processo).

## Caminho usado: `ogr2ogr` (mesmo padrão já medido seguro no L2-01-a) + síntese própria de `.osm`

1. `ogr2ogr -f GeoJSON estradas_raw.geojson area_estudo.osm.pbf lines -spat -46.62 -23.53 -46.42 -23.38
   -where "highway IS NOT NULL" --config OGR_INTERLEAVED_READING YES -select osm_id,highway,name,other_tags`
   — RSS medido 310 MB, 3,24 s, 42.720 vias com tag `highway`. `other_tags` carrega oneway/maxspeed/
   access/junction/bridge/tunnel/ref/surface/lanes como hstore textual (o schema padrão do driver OSM do
   GDAL não expõe essas colunas fora de `lines`, só `other_tags`).
2. `gerar_osm_xml.py` (neste diretório): lê o GeoJSON, deduplica nó por coordenada exata (mesma origem,
   sem preocupação de precisão de ponto flutuante — `round(lon,7)`/`round(lat,7)`), escreve um `.osm` XML
   válido (nó por coordenada única, via com `<nd ref>` por vértice, tags decodificadas do `other_tags`).
   RSS medido 255 MB, 1,22 s. Resultado: 210.065 nós únicos, 42.720 vias, 277.695 referências de nó, 0 nó
   de via faltando (`osmium check-refs`).
3. `osmium cat guarulhos.osm.xml -o guarulhos.osm.pbf` (conversão XML→PBF, sob `ulimit -v 1.000.000` por
   cautela; não precisou do teto — passagem única sobre um arquivo já pequeno).

**Limite explícito deste método**: só ruas com `highway=*` entram (é o que o roteamento de carro precisa);
prédios, uso do solo e lugares (as outras camadas do L2-01-a) NÃO estão neste grafo — não são rota.
Interseção em T no MEIO de uma via (não na ponta) é capturada porque a via que passa pelo cruzamento tem
um vértice ali com a MESMA coordenada da ponta da via que termina ali (dado de origem já assim); não foi
verificado every-caso, só a ausência de nó de via faltando (`check-refs`) e a rota/matriz medidas abaixo.

## Resultado

- `guarulhos.osm.pbf`: 1.669.892 bytes (1,6 MiB) — bem abaixo do teto de 50 MB do item.
- sha256: `aea5af38b5511ce3cbaae3218743c38295bb9948645e6b8ae676b8d623e0d7b2`
- 210.065 nós, 42.720 vias, 0 relações (restrições de manobra vêm de `type=restriction`, nenhuma no
  recorte — `osrm-extract` não relatou nenhuma).
- `osrm-extract -p car.lua` (imagem `osrm/osrm-backend`, mesma versão v5.26.0 já usada nos 4 contêineres
  da casa) → `osrm-partition` → `osrm-customize` (MLD): 117.140 nós no grafo por aresta, 227.801 arestas
  processadas, pico de RAM relatado pelo próprio OSRM 156 MB (extract) / 82 MB (partition) / 63 MB
  (customize) — todos rodados com `docker run --memory=1200m`/`800m` (teto duro do container; nenhum
  chegou perto do teto). Diretório final `osrm/`: **61 MB** (script + `.pbf` + `.osrm*`).
- Extraído/construído em 06/09/2026. Reprodutível: os três comandos acima, nesta ordem, sobre o mesmo
  `area_estudo.osm.pbf` (mesmo timestamp de dado citado acima).

## Serviço

Contêiner `plat-osrm-guarulhos` (imagem `osrm/osrm-backend`, `osrm-routed --algorithm mld
--max-table-size 625`), **127.0.0.1:5010**, só perfil carro (`car.lua`; não há grafo de pé/bicicleta neste
recorte — `ROTA_PERFIS = ("carro",)` em `app/limites.py`). Teto de memória do contêiner: 600 MB (medido em
uso: ~40 MB). Unidade systemd `plat-osrm-guarulhos.service` (`deploy/plat-osrm-guarulhos.service`) — decisão
de manter vivo (não por job): o serviço é um roteador HTTP leve (memória medida ~40 MB) que qualquer
pedido de `/api/rota`, `/api/matriz` ou `/api/isocrona` pode chamar a qualquer momento; o padrão da casa
para os outros 4 contêineres OSRM (`osrm-cbre`, `osrm-cbre-polos`, `osrm-edpes`, `buslog-osrm`) também é
"sempre ligado", não sob demanda — manter o mesmo padrão evita uma classe nova de latência de partida fria
(alguns segundos para carregar os arquivos `.osrm*` do disco) na primeira chamada de cada sessão.

## Portas e isolamento (não repetir o que já existe na casa)

Portas 5000-5003 já em uso por OUTRAS frentes (nenhuma tocada): `buslog-osrm` (5000, `rio_metro.osrm`),
`osrm-cbre` (5001, `area_estudo.osrm` — MESMO `.pbf` de origem que este item, mas grafo próprio, sem
relação de arquivo), `osrm-cbre-polos` (5002, `rmsp_camp_santos.osrm` — o que o pedido do dono citou como
"NÃO TOCAR"), `osrm-edpes` (5003, `es.osrm`). Este item usa **5010** (nova, dentro da faixa 8150-8159? não
— faixa de portas HTTP internas da plataforma é 8150-8159; OSRM fala o protocolo próprio do `osrm-routed`,
não HTTP da API, por isso segue a numeração 50xx já em uso pelas outras frentes de OSRM da casa, só
avançando para a próxima dezena livre).
