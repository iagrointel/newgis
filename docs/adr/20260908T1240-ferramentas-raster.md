# ADR 20260908T1240 — Ferramentas raster: onde o pixel é lido, onde o resultado é escrito

Item L2-05-e-raster-basico. Contexto: o registro de ferramentas (L2-05-a) já existia para vetor, e a
ingestão de imagem (L1-01) já punha COG no armazenamento de objetos com registro STAC. Faltava a análise
raster, e com ela três decisões que valem para toda a linha.

## Decisão 1 — a entrada é lida onde ela está, por caminho virtual do GDAL

Nenhuma ferramenta baixa o raster. O caminho de leitura nasce do catálogo do inquilino (item raster ->
item STAC -> asset de dado -> objeto) e vira `/vsis3/<balde>/<objeto>` com a credencial só-leitura do
balde, exatamente como o motor de ladrilho do L1-02 faz. Consequências aceitas:

* não há parâmetro de endereço em ferramenta nenhuma, logo não há requisição forjada a testar: o cliente
  escolhe um item, não uma URL;
* a leitura é por faixa de bytes, e as estatísticas zonais leem em faixas de 64 linhas dentro da janela
  de cada zona. Medido: 777 MB de pico de memória num raster de 9,77 GB de pixels;
* origens de baldes diferentes na mesma execução são recusadas, porque o GDAL guarda um par de chaves
  por processo e a alternativa seria ler com a credencial errada.

## Decisão 2 — o produto é feito pelo utilitário do GDAL, em subprocesso, e termina sempre em COG

Declividade, curvas de nível, visibilidade, distância, mosaico, reprojeção, rasterização e vetorização
são o `gdaldem`, o `gdal_contour`, o `gdal_viewshed`, o `gdal_proximity`, o `gdalwarp`, o
`gdal_rasterize` e o `gdal_polygonize` — não reimplementação. Motivos: o utilitário é o programa de
referência (o resultado é comparável byte a byte com o que o usuário rodaria à mão, e a suíte compara),
o neto herda o limite de memória e o cancelamento do trabalho, e a conta de manutenção é zero.

O que é conta de pixel e não tem utilitário — calculadora, reclassificação, estatísticas zonais e
amostragem — é escrito em Python bloco a bloco sobre o rasterio, com o `numexpr` (o mesmo avaliador do
TiTiler) na calculadora.

Todo produto raster passa por um `gdal_translate -of COG` final com compressão declarada, blocos de 512 e
pirâmide, validado pelo `rio-cogeo` antes de sair do diretório de trabalho. Custa uma passagem a mais e
compra: o item de resultado é imediatamente servível pelo motor de ladrilho, e a medida de disco do
adversário tem resposta escrita no próprio item.

## Decisão 3 — o resultado raster é item de catálogo com STAC, na coleção `analises`

O resultado vetorial já nascia como `camada_vetorial` com proveniência. O raster nasce como item `raster`
na coleção STAC `<inquilino>-analises`, separada da coleção de imagens ingeridas, com o mesmo bloco de
proveniência (ferramenta, versão, parâmetros, entradas com uuid, versão e sha256, autor, data) e uma
relação `derivado_de` por entrada. Para isso o esquema do tipo `raster`, que é fechado, ganhou a
propriedade `procedencia` (migração `20260908T1159_raster_procedencia.sql`).

## Duas armadilhas que custaram tempo, escritas para não voltarem

1. O `update_collection_extents` do pgstac dentro da MESMA transação do catálogo: quando ele falha, a
   transação inteira é abortada e o `commit` vira `rollback` em silêncio — o item de resultado sumia sem
   nenhum erro visível. Ele agora roda em transação própria, depois.
2. GeoJSON sem o membro `crs`: o GDAL assume EPSG:4326 e um recorte em coordenadas métricas morre com
   "Invalid latitude". A ponte entre camada e utilitário escreve o CRS no arquivo.

## Alternativas descartadas

* `exactextract` para a fração de pixel: não está instalado. A fração sai de uma amostragem de 5x5 por
  pixel, com o erro medido contra o `rasterstats` e gravado no arquivo de medidas — não se declara
  exatidão que não se tem.
* Hidrologia (direção de fluxo, bacia): `pysheds` e `whitebox` não estão instalados e não se escreve
  motor de hidrologia próprio nesta fase. Está na tabela do que ficou de fora.
