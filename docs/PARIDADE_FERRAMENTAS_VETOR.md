# Paridade das ferramentas vetoriais com o ArcGIS Online Map Viewer (item L2-05-b)

O que este documento faz: colocar lado a lado a ferramenta desta plataforma e a ferramenta equivalente das
categorias **Manage data** e **Use proximity** do Map Viewer, dizendo o que é igual, o que é diferente e o
que ainda não existe aqui. Fontes: a referência de ferramentas do ArcGIS Pro e a página de análise do Map
Viewer listadas no item, consultadas em setembro de 2026, e a referência do PostGIS 3.6.

## Use proximity

| Map Viewer | aqui | diferença |
|---|---|---|
| Create buffers | `buffer` | a distância é geodésica por padrão (o Map Viewer também oferece distância planar); aceita distância por campo e anel (distância interna), como o Buffer do Pro; `dissolver` equivale a "Overlap: dissolve". O desvio de área contra o círculo geodésico de referência é 5,0e-5, medido. |
| Find nearest / Plan routes / Create drive-time areas | — | dependem de rede e de matriz origem-destino; não saem de uma expressão SQL e não estão neste item. |

## Manage data

| Map Viewer | aqui | diferença |
|---|---|---|
| Clip layer | `recorte` | conserva os campos da entrada; recorta contra a união da camada de recorte, que precisa ser poligonal. |
| Overlay layers — Intersect | `intersecao` | uma feição por par que se sobrepõe, campos das duas camadas com prefixo `a_`/`b_` (o Map Viewer resolve a colisão de nome renomeando também). |
| Overlay layers — Union | `uniao` | acrescenta o campo `origem` (`ambas`, `a`, `b`) em vez de deixar o usuário deduzir pela presença de nulos. Só polígonos, como lá. |
| Overlay layers — Erase | `diferenca` | igual; apaga contra a união da camada a apagar. |
| — | `diferenca_simetrica` | não existe como botão no Map Viewer (é composição de dois Erase); aqui é uma ferramenta só. |
| Dissolve boundaries | `dissolver` | agrupa por campos e aceita estatísticas `soma`, `media`, `minimo`, `maximo`, `desvio` e `contagem`; `multipartes=false` separa as partes, o que no Pro é o "Create multipart features" invertido. |
| Merge layers | `mesclar` | empilha N camadas (o Map Viewer mescla duas por vez); campo com o mesmo nome vira uma coluna e o que falta fica nulo; grava a camada de origem num campo. |
| Generate tessellation / Create bins | — | grade regular ainda não existe aqui. |
| Extract data | — | é exportação, não análise; mora na linha de exportação do catálogo. |

## Ferramentas de dado que no ArcGIS ficam no Pro (não no Map Viewer) e existem aqui

`explodir` (Multipart To Singlepart), `centroide` (Feature To Point, com a opção "inside" = ponto interior),
`casco` (Minimum Bounding Geometry, convexo; o côncavo não tem equivalente direto), `simplificar`
(Simplify Line/Polygon, com preservação de topologia), `suavizar` (Smooth Line/Polygon — aqui é Chaikin, o
Pro usa PAEK ou Bezier: a curva não é a mesma), `reprojetar` (Project), `calcular_geometria` (Calculate
Geometry Attributes), `pontos_aleatorios` (Create Random Points, aqui sempre dentro de polígono),
`linhas_para_pontos` (Feature Vertices To Points e Generate Points Along Lines num só, pelo parâmetro `modo`),
`poligonos_para_linhas` (Polygon To Line, sem a detecção de borda compartilhada), `densificar` (Densify, com
o comprimento máximo de segmento medido no elipsoide).

## O que é deliberadamente diferente

1. **Medida geodésica como padrão.** No ArcGIS a unidade de saída depende da projeção da camada e do ambiente
   de geoprocessamento. Aqui área, perímetro e comprimento saem sempre do elipsoide WGS 84 e sempre em metros.
2. **Sem geometria de saída "não simples".** Toda operação booleana passa por `ST_MakeValid` +
   `ST_ReducePrecision`, e a contagem de inválidas da entrada fica escrita na procedência da camada de saída.
3. **Limite declarado.** Cada manifesto publica `feicoes_max` (2 milhões por entrada) e a execução tem teto de
   30 minutos. O Map Viewer usa crédito; aqui o que existe é limite de tamanho, visível na API antes de rodar.
4. **`poligonos_para_linhas` não desduplica borda compartilhada** (o Polygon To Line do Pro, com
   `Identify_and_store_polygon_neighboring_information`, devolve uma linha só por fronteira comum e os
   identificadores dos dois vizinhos). Aqui cada polígono devolve a sua borda inteira.
