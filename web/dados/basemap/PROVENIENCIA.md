# Proveniência — `guarulhos.pmtiles` (item L2-01-a-basemap-local-pmtiles)

Mapa-base local de demonstração: um recorte pequeno de OSM, servido do próprio nginx do appliance,
sem serviço de tiles dinâmico e sem chave de terceiro. Sem nome de cliente, sem PII (regra P7).

## Fonte

- Origem: OpenStreetMap, extrato regional `sudeste-latest.osm.pbf` já presente na casa em
  um recorte OSM já baixado por outra frente da casa (baixado por outra frente, sem novo download — disco a
  98 %). OSM © colaboradores do OpenStreetMap, licença **ODbL 1.0**
  (https://www.openstreetmap.org/copyright).
- Recorte: bbox `-46.62, -23.53, -46.42, -23.38` (Guarulhos-SP, área de teste; ≈ 21 × 17 km),
  extraído com `ogr2ogr` (driver OSM do GDAL 3.8.4, leitura em streaming, sem carregar o `.pbf`
  inteiro em memória — a alternativa `osmium extract` foi tentada primeiro e matada pelo OOM killer
  desta máquina, RAM disponível ~3 GB no momento).
- Camadas extraídas (uma chamada `ogr2ogr` por camada, `-spat`/`-clipsrc` no bbox acima):
  - `estradas` ← layer `lines` (50.593 feições; residencial/service/footway/secundária/etc.)
  - `edificacoes` ← layer `multipolygons`, `-where "building IS NOT NULL"`
  - `cobertura` ← layer `multipolygons`, `-where "natural IS NOT NULL OR landuse IS NOT NULL OR leisure IS NOT NULL"`
  - `lugares` ← layer `points`, `-where "place IS NOT NULL"` (212 feições; bairro/cidade)
- Ladrilhamento: `tippecanoe v2.80.0` (`~/tools/tippecanoe`), `-zg --drop-densest-as-needed
  --extend-zooms-if-still-dropping`, zoom 0-14 (decidido pelo próprio tippecanoe pelo tamanho do
  dado disponível), **`-L nome:arquivo.geojson` para cada camada, sem nenhum `-l`** (ver "achado"
  abaixo). Comando completo gravado no metadado interno do arquivo (`generator_options`,
  conferível com `pmtiles-show guarulhos.pmtiles`).

## Achado (corrigido antes de publicar): `-l` funde todas as camadas em uma só

A primeira rodada usou `-l estradas -L estradas:… -l edificacoes -L edificacoes:… …` (um `-l` antes
de cada `-L`, supondo que fixasse o nome de cada camada). O manual do tippecanoe é explícito ao
contrário: **"`-l` name: … If there are multiple input files specified, the files are all merged
into the single named layer, even if they try to specify individual names with `-L`."** Com quatro
`-l` repetidos, o tippecanoe fundiu as quatro camadas numa única camada de saída chamada `lugares`
(o último `-l` da linha) — confirmado decodificando um tile real (`tippecanoe-decode`): a camada
`lugares` continha LineString (estradas) e Polygon (edificações) junto dos 2 pontos de lugar. O
estilo (`web/js/mapa/estilo.js`) desenha `lugares` como camada `circle`; o `CircleBucket` do
MapLibre gera um círculo em CADA VÉRTICE da geometria, não só em pontos — o resultado visual era um
mapa inteiro coberto de pontos âmbar (uma bolinha por vértice de rua e de prédio), não um mapa
legível. **Passou despercebido pelo primeiro e2e** (a prova "mais de 50 cores distintas" também
aprova esse artefato — não distingue "mapa certo" de "bug visualmente denso"; só a conferência
visual da captura pegou). Corrigido: só `-L nome:arquivo` por camada, nenhum `-l`; decodificação do
mesmo tile depois confere 4 camadas com geometria certa (`edificacoes`→Polygon,
`estradas`→LineString, `cobertura`→Polygon, `lugares`→Point). Lição: **decodificar um tile de
verdade (`pmtiles` python + `tippecanoe-decode`) e olhar a captura antes de publicar**, não confiar
só na contagem de cores.

## Resultado medido

- Arquivo: 19.181.534 bytes (18,3 MiB) — bem abaixo do teto de 50 MB do item.
- sha256: `86aa490c784022c28de3671a1208f62f0ba91ad3cb8f63b909b8f3e71f01a475`
- zoom 0-14, 140 tiles, formato MVT, compressão gzip interna (padrão PMTiles); tile `13/3035/4646`
  decodificado como prova: 24.010 feições `edificacoes`, 5.343 `estradas`, 636 `cobertura`, 2
  `lugares`, geometria de cada uma batendo com o esperado.
- Extraído em 06/09/2026. Reprodutível: `ogr2ogr` + `tippecanoe` com os parâmetros acima (só `-L`,
  sem `-l`) sobre o mesmo `.pbf` (o `.pbf` de origem tem timestamp de dado até 2026-08-27; um
  recorte novo mais recente exige re-baixar o extrato regional, decisão de disco do dono — D27 do
  `L2_CONCEITO.md`).

## Limite deste item

Isto é o mapa-base MÍNIMO (estradas, edificações, cobertura do solo, lugares) para uma única área
de teste, não a base cartográfica nacional (essa é o D27 do dono — "mapa base (volume × disco
98 %)" — travado por disco, não por esta fatia). Rótulos de texto (nome de rua/bairro na tela)
ficam para `L2-02-e-simbolos-sprites-glifos` (exige servidor de glifos MapLibre); a camada
`lugares` está no tileset mas o estilo de `/mapa` hoje não desenha texto, só existência do dado.
