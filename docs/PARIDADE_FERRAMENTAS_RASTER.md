# Paridade das ferramentas raster (item L2-05-e-raster-basico)

Referências da Esri, lidas em 08/09/2026:
`pro.arcgis.com/en/pro-app/latest/tool-reference/spatial-analyst/an-overview-of-the-spatial-analyst-toolbox.htm`,
`.../zonal-statistics.htm`, `.../raster-calculator.htm`, `.../slope.htm`, `.../viewshed-2.htm`, e a
"Raster analysis" do Map Viewer (`doc.arcgis.com/en/arcgis-online/analyze/perform-analysis-mv.htm`).
Sem ArcGIS Pro nem ArcGIS Online reais nesta máquina (decisão D20 em aberto): a coluna "Pro real" fica
pendente em tudo o que dependeria de rodar a ferramenta da Esri lado a lado.

Como se lê a tabela: "feito" é o que existe, tem teste e tem medida; "parcial" é o que existe com uma
limitação nomeada; "fora" é o que NÃO está nesta fase, com o motivo.

## O que está feito

| ferramenta da Esri | nossa ferramenta | diferença declarada | testado por |
|---|---|---|---|
| Zonal Statistics as Table | `estatisticas_zonais` | contagem, soma, média, mínimo, máximo, desvio, mediana, majoritário e percentual por classe, por polígono. Peso do pixel pela FRAÇÃO coberta (amostragem 5x5 por pixel); com `fracao=false` vale o critério clássico do centro do pixel, que reproduz o `rasterstats` | `tests/unit/test_raster_zonal.py`, `tests/unit/test_raster_medidas.py`, `tests/api/ferramentas/test_raster.py` |
| Raster Calculator | `calculadora_raster` | expressão com bandas de um ou mais rasters alinhados, avaliada pelo `numexpr` — o mesmo avaliador que roda dentro do TiTiler. Gramática fechada (banda, número, aritmética, parênteses e um punhado de funções); reamostragem entre grades diferentes é DECLARADA pelo usuário, nunca escolhida sozinha | `tests/unit/test_raster_calculo.py` (NDVI de cena Sentinel-2 real igual ao TiTiler a menos de 1e-6) |
| Reclassify | `reclassificar_raster` | tabela `min-max:classe`, intervalo fechado no início e aberto no fim, como a da Esri; `*` para faixa aberta e `nodata` como classe | `test_reclassificar_respeita_faixa_fechada_no_inicio`, `test_terreno_reclassificar_e_distancia_encadeados` |
| Extract by Mask / Clip Raster | `recortar_raster` | recorte e máscara por polígonos de uma camada (`gdalwarp -cutline`); camada que não toca o raster é erro nomeado, não produto vazio | `test_recortar_reprojetar_e_mosaico`, `test_polinomio_de_recorte_fora_da_extensao_e_erro_nomeado` |
| Project Raster / Resample | `reprojetar_raster` | reamostragem declarada entre vizinho, bilinear, cúbica, spline cúbica, lanczos, média, moda, mínimo e máximo | `test_recortar_reprojetar_e_mosaico` |
| Mosaic To New Raster | `mosaico_raster` | vários rasters do inquilino num só; contagem de bandas tem de bater | `test_recortar_reprojetar_e_mosaico` |
| Slope, Aspect, Hillshade, Roughness, TPI | `terreno_raster` | `gdaldem` nos cinco modos; declividade em grau ou por cento, fator z declarado. Em CRS geográfico a ferramenta RECUSA declividade e sombreamento sem `escala` declarada | `test_declividade_igual_ao_gdaldem_direto` (igual byte a byte ao `gdaldem` direto), `test_declividade_em_crs_geografico_e_recusada_com_o_motivo` |
| Contour | `curvas_de_nivel` | `gdal_contour` com intervalo e cota de base; saída como camada vetorial hospedada | `test_amostrar_curvas_e_vetorizar` |
| Raster to Polygon | `vetorizar_raster` | `gdal_polygonize`; teto de feições por execução | `test_amostrar_curvas_e_vetorizar` |
| Feature to Raster / Polygon to Raster | `rasterizar_camada` | `gdal_rasterize` por campo ou por valor fixo, resolução declarada | `test_rasterizar_camada_e_visibilidade` |
| Extract Values to Points / Sample | `amostrar_raster` | valor de cada banda na posição de cada ponto; ponto fora da extensão e pixel nodata devolvem nulo, nunca zero | `test_amostrar_curvas_e_vetorizar`, `test_amostrar_em_pontos_dentro_e_fora` |
| Viewshed | `visibilidade` | `gdal_viewshed` a partir de um ponto, com altura do observador, altura do alvo e raio | `test_visibilidade_igual_ao_gdal_viewshed_direto` (igual byte a byte), `test_rasterizar_camada_e_visibilidade` |
| Euclidean Distance | `distancia_euclidiana` | `gdal_proximity`, em unidade de mapa ou de pixel, com lista de valores-alvo e distância máxima | `test_terreno_reclassificar_e_distancia_encadeados` |

Comum às treze, e é onde ganhamos da referência: toda saída nasce como item do catálogo com o bloco de
proveniência (ferramenta, versão, parâmetros, entradas com uuid, versão e sha256, autor, data) e com a
relação `derivado_de` visível na ficha; todo raster de saída é COG validado pelo `rio-cogeo`, com
compressão e pirâmide declaradas no próprio item; e a leitura é sempre por janela sobre o COG onde ele
está, medida em 777 MB de pico de memória num raster de 9,77 GB de pixels
(`tests/medidas/L2-05-e-raster-basico.json`).

## O que está FORA desta fase, e por quê

| capacidade da Esri | motivo |
|---|---|
| Hidrologia inteira (Flow Direction, Flow Accumulation, Basin, Watershed, Stream Link, Fill) | decisão do item: `pysheds` e `whitebox` não estão instalados e não se escreve motor de hidrologia próprio. É item futuro, com dependência a decidir |
| Distância de custo (Cost Distance, Cost Path, Corridor) e Distance Accumulation | não implementado nesta fase; o `gdal_proximity` só faz distância euclidiana |
| Estatística focal (Focal Statistics, Filter, Block Statistics) e Zonal Fill | não implementado nesta fase |
| Interpolação (IDW, Kriging, Spline, Natural Neighbor) | pertence ao item irmão L2-05-d (grades, densidade, padrões e interpolação) |
| Densidade (Kernel Density, Point Density, Line Density) | idem, item L2-05-d |
| Solar Radiation, Surface Parameters (curvatura), Contour com suavização | não implementado nesta fase |
| Viewshed 2 com observadores múltiplos, refração e curvatura da Terra | `gdal_viewshed` faz um observador por execução; a curvatura e a refração não são expostas |
| Múltiplos rasters escolhidos na TELA para calculadora e mosaico | o formulário escolhe um raster por parâmetro e o envio o embrulha em lista; escolher vários numa execução é pela API. Limitação de tela, não de motor |
| Zonal statistics com `exactextract` (fração exata de pixel) | o `exactextract` não está instalado; a fração é aproximada por amostragem 5x5, com o erro medido e gravado |
| Raster functions, cadeias de função e Raster Analysis do Image Server (processamento distribuído, "Analysis on the fly") | fora: aqui a análise materializa um COG novo, não uma cadeia avaliada no desenho. Nada nesta fase finge ser função encadeada |
| Multidimensional (netCDF, séries temporais) e Deep Learning tools | fora desta fase |

## Nota sobre os dados usados nas medidas

O portão do item pede as estatísticas zonais de 5.570 municípios sobre o MapBiomas coleção 10 e a
declividade do GLO-30. O que existe nesta máquina, e é o que foi medido, está declarado no arquivo de
medidas: o recorte de uso do solo do MapBiomas coleção 10 do acervo cobre uma ÁREA DE ESTUDO e não o
país, então as 5.570 zonas são uma grade regular sobre a extensão dele — o número de zonas é o da
cláusula, a geometria não é a dos municípios; e do GLO-30 restou só o índice (o arquivo `.vrt`), sem os
ladrilhos, então a declividade foi conferida contra um modelo de elevação real de 1 segundo de arco do
acervo, reprojetado para UTM. As duas trocas estão escritas aqui e no arquivo de medidas, e nenhuma delas
muda o que a cláusula compara.
