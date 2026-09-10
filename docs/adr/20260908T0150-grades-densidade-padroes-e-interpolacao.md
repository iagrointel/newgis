# Grades, densidade, padrões espaciais e interpolação (item L2-05-d)

Data: setembro de 2026. Estado: aceita. Contexto: item `L2-05-d-grades-densidade-padroes-interpolacao`,
sobre o registro de ferramentas do L2-05-a, as vetoriais do L2-05-b e as de relação do L2-05-c.

## Decisão 1 — a estatística fica em módulo próprio, em numpy, e não em biblioteca de análise espacial

`app/ferramentas/estatistica_espacial.py` implementa Getis-Ord Gi*, I de Moran global, índice R de Clark &
Evans, centro médio / distância padrão / elipse de desvio padrão, densidade de kernel e IDW. São fórmulas
fechadas e curtas; `esda`/`libpysal` entrariam como dependência nova de produção para reproduzir o que cabe
em uma tela. As duas bibliotecas ficam **só no teste**, no papel de segunda implementação: o teste do item
confere Gi* e Moran contra elas com diferença medida de 8,9e-16 e 3e-16, e confere o resto contra fórmula
escrita de novo no próprio teste.

Ponto que custou tempo e fica registrado: `esda` e `libpysal` padronizam os pesos POR LINHA por padrão
(`transform="R"`). Gi* e I de Moran foram publicados com pesos binários. Comparar sem passar `transform="B"`
dá números diferentes e a diferença não é erro de implementação — é outra estatística.

## Decisão 2 — desenho de grade é PostGIS; o que nasce em numpy entra por `escrever_linhas`

Quadrado e hexágono saem de `ST_SquareGrid`/`ST_HexagonGrid` no UTM local (o mesmo caminho que
`agregar_pontos` do L2-05-c já usava), porque é lá que a célula tem metro de verdade. O que nasce em numpy
(células de densidade, de IDW, elipse, isolinhas) é inserido pela função `grade.escrever_linhas`, par de
`vetor.escrever`: cria a tabela com colunas declaradas, insere em lote com a geometria em WKB no SRID
métrico e reprojeta a coluna inteira em UM comando. A alternativa — converter ponto a ponto pelo banco —
faria uma ida ao banco por vértice.

## Decisão 3 — `tamanho` da célula é a distância entre lados opostos, não a aresta

`ST_HexagonGrid` recebe a ARESTA. O parâmetro da ferramenta é a distância entre lados paralelos, que é como
grade hexagonal é pedida na prática ("grade de 250 m"). A conversão é `aresta = tamanho / raiz(3)` e a área
da célula inteira é `3*raiz(3)/2 * aresta²` = 54.126,5877 m² para 250 m. O teste confere a área mediana
contra essa fórmula fechada, com diferença relativa abaixo de 1e-9.

## Decisão 4 — a saída de densidade e de IDW é CAMADA DE CÉLULAS enquanto o L1-01 não estiver em master

O portão do item pede que a saída raster entre pelo caminho de ingestão de raster do L1-01 (COG no bucket +
item do catálogo). Esse caminho **não existe no ramo em que este item foi construído** (`app/raster/` não
está em master; o ramo do L1-01 está PARCIAL). Duas saídas ruins seriam: (a) inventar aqui um segundo
mecanismo de publicação de raster, que o item proíbe; (b) registrar uma ferramenta cuja saída não pode ser
publicada, que é exatamente o vazio que a regra da casa proíbe.

O que foi feito: a superfície sai como camada de células quadradas com o valor no centro — que é também o
que o "Calculate Density" do Map Viewer da Esri devolve — e a MESMA conta em array
(`estatistica_espacial.densidade_kernel` e `.idw`) fica pronta e testada para virar GeoTIFF COG quando o
L1-01 chegar. Quando chegar, o COG entra por lá, e não por um caminho novo criado neste item.

## Decisão 5 — isolinha pelo gerador do GDAL, superfície pelo scipy

`gdal.ContourGenerateEx` gera as isolinhas sobre a superfície em memória. A superfície vem do IDW próprio ou
da triangulação de Delaunay do scipy (`LinearNDInterpolator`), que é a mesma triangulação Qhull que o
`gdal_grid -a linear` usa; escolher o scipy evita escrever a camada de pontos num arquivo temporário só para
o GDAL relê-lo.

Armadilha registrada: `Band.WriteArray` do GDAL passa por `osgeo.gdal_array`, compilado nesta máquina contra
numpy 1.x, e **não importa sob numpy 2.x** ("_ARRAY_API not found"). O caminho que funciona é
`Band.WriteRaster` com o buffer em bytes.

## Decisão 6 — numpy, scipy, h3 e GDAL passam a ser dependência de produção de fato

Como já acontece com o shapely (ver o cabeçalho de `requirements.txt`), estes pacotes vêm do sistema, não
deste arquivo, e **não foram instalados por este item** — já estavam na máquina. Fica anotado em
`requirements.txt` para a mesma decisão do dono que o shapely aguarda.

## Correções de passagem no executor do L2-05-a

Camada de saída com UMA feição pontual quebrava a publicação em dois lugares: a extensão era lida do anel do
GeoJSON de `ST_Extent` (que devolve um ponto, não um polígono) e o retângulo degenerado era recusado pelo
CHECK `item_extent_check` (`ST_MakeEnvelope` com os quatro cantos iguais é polígono inválido). Agora os
cantos vêm em número e o retângulo degenerado é aberto em 1e-9 grau (cerca de 0,1 mm).
