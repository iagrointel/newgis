# Paridade das ferramentas de grade, densidade e padrão com o ArcGIS (item L2-05-d)

O que este documento faz: pôr lado a lado as oito ferramentas deste item e as equivalentes do ArcGIS Pro
(caixa Spatial Statistics e Spatial Analyst) e do Map Viewer do ArcGIS Online, dizendo o que é igual, o que é
diferente e o que não existe aqui. Fontes consultadas em setembro de 2026: visão geral da caixa Spatial
Analyst do ArcGIS Pro, a página "Perform analysis" do ArcGIS Online, a referência do PostGIS 3.6 e a página
do driver COG do GDAL.

| ArcGIS | aqui | diferença |
|---|---|---|
| Generate Tessellation | `tesselacao` | quadrado, hexágono e **H3 (níveis 5 a 10)**. O tamanho é a distância entre lados opostos, em metros, desenhada no UTM WGS 84 do centro da área e trazida de volta ao SRID da camada. O ArcGIS também tem triângulo, losango e transversal; aqui não. `recortar` corta as células pela área (o Pro chama de "clip"). |
| Kernel Density (Spatial Analyst) / Calculate Density (Map Viewer) | `densidade_kernel` | pontos e linhas, com raio e função declarados (quártica de Silverman, gaussiana truncada, triangular, uniforme). A saída é camada de células, como no Map Viewer, não raster — ver a decisão 4 do ADR do item. A linha é amostrada a cada meia célula e cada amostra pesa o comprimento que representa: a integral do campo devolve o comprimento total. A gaussiana é truncada no raio e perde 1 - exp(-4,5) = 1,1 % da massa; está escrito no método da procedência e medido no teste. |
| Hot Spot Analysis (Getis-Ord Gi*) | `hot_spot` | vizinhança por **distância fixa** com pesos binários (o Pro oferece oito conceitos de vizinhança). Devolve `z`, `p` bilateral, número de vizinhos e `faixa` no vocabulário do Gi_Bin (+-3 = 99 %, +-2 = 95 %, +-1 = 90 %). **Não** faz correção de comparações múltiplas (FDR), que no Pro é opcional. Valor constante devolve z nulo em vez de zero, porque Gi* é indefinido nesse caso. |
| Mean Center / Standard Distance / Directional Distribution | `centro_medio` | uma ferramenta com o parâmetro `forma`: `centro` (ponto), `circulo_distancia_padrao` e `elipse`. Aceita campo de peso e 0,5 a 3 desvios. O campo de agrupamento (`Case Field`) do Pro não existe: a saída aqui é uma feição por execução. |
| Average Nearest Neighbor | `vizinho_mais_proximo_medio` | índice R de Clark & Evans com z e p. A área de referência é uma camada informada ou, sem ela, o casco convexo dos pontos — a mesma escolha que o Pro oferece. A saída é uma feição com a área de referência e os números (o Pro só devolve relatório). |
| Spatial Autocorrelation (Global Moran's I) | `moran_global` | pesos binários por distância fixa, sem o próprio ponto, significância sob normalidade. Sem permutação (o Pro também usa a aproximação analítica por padrão). |
| IDW (Spatial Analyst / Geostatistical Analyst) | `interpolacao_idw` | potência e número de vizinhos declarados; célula cujo centro cai sobre uma amostra recebe o valor da amostra. Sem barreira, sem setor de busca, sem anisotropia. |
| Contour / Contour List | `contorno` | superfície por IDW ou por triangulação de Delaunay (equivalente ao `gdal_grid -a linear`) e isolinhas pelo gerador do GDAL. Intervalo fixo; lista de níveis avulsos ainda não. |

## O que vale para todas

1. **Toda conta métrica acontece em UTM WGS 84 do centro da camada** (32600+fuso ao norte, 32700+fuso ao sul),
   nunca em graus. A saída volta ao SRID da camada de entrada.
2. **O método fica na procedência do item de saída** (`dados.procedencia.metodo`): função, raio, célula,
   número de amostras e, na densidade, a integral medida contra o peso total. Quem abre a ficha da camada lê
   como o número saiu.
3. **Limites declarados no manifesto** (`app/limites.py`): 200 mil feições nas estatísticas que carregam
   coordenadas em memória, 250 mil células por grade, 64 vizinhos no IDW, 200 mil isolinhas. Passar do limite
   é erro nomeado com o campo, não estouro de memória.
