# ADR 20260908T0712 — MapServer e GeometryServer compatíveis com Esri

Item `L2-04-f-mapserver-identify-legend-geometryserver`. Estado: aceito.

## Contexto

O FeatureServer dos itens irmãos (L2-04-b/c/d) atende quem consome FEIÇÃO. Falta o outro contrato do
protocolo Esri, o que os clientes antigos usam: a JS API 3.x e o "map image layer" do ArcGIS Pro pedem
um serviço que devolva UMA IMAGEM já desenhada e responda `identify`, `find` e `legend`; e a JS API
pede um GeometryServer para projetar e medir sem biblioteca local.

## Decisões

**1. O MapServer é um MAPA do catálogo, não uma camada.** O identificador de camada do serviço é a
posição no documento de mapa (item L2-01-a), e a camada 0 desenha por cima, como no ArcGIS Server.
A alternativa — um MapServer por camada — daria um serviço de uma camada só, que é justamente o que o
FeatureServer já é; e o documento de mapa já traz ordem, visibilidade, estilo e extensão. Camada do
documento que a RLS não deixa ler não entra na lista: o serviço tem menos camadas, nunca um erro.

**2. O desenho é do Pillow, no servidor, sem navegador e sem dependência nova.** `app/catalogo/
miniatura.py` já desenhava feição vetorial com `PIL.ImageDraw` desde o item do catálogo. `export`
reusa esse desenho, trocando o azul fixo da miniatura pelo símbolo do estilo. O motor de renderização
com navegador sem cabeça (item L2-12-a) fica de fora por decisão, não por esquecimento: ele mora em
outro ramo, ainda não juntado, e importar um navegador para desenhar polígono é caro por pixel e
frágil por dependência. Medido: 5.003 polígonos em 1024×768 saem em 0,075 s quentes.

**3. O símbolo do desenho e a amostra da legenda saem do MESMO `drawingInfo`.** É a estrutura que o
FeatureServer já publica (`app/consulta/renderizador.py`, conversor de estilo MapLibre). Assim não
existe caminho no código em que a legenda diga uma cor e o mapa desenhe outra — e a cláusula "legend
devolve uma imagem por classe do estilo" é a lista de classes daquele mesmo renderer, incluindo o
símbolo padrão. Renderer `simple` tem UMA classe; a legenda de uma camada sem estilo não é vazia.

**4. `layerDefs` passa pelo analisador `where_ast`, o mesmo da operação `query`.** Lista branca de
colunas lida de `information_schema`, valores sempre por parâmetro. Expressão fora da gramática é 400
e não chega ao banco. Foi a resposta escolhida para a refutação do item (SQL injetado em `layerDefs`).

**5. Os tetos do serviço são declarados em `app/limites.py`, não escondidos no código.**
`MAPSERVER_LADO_MAX = 4096` é o mesmo `maxImageWidth`/`maxImageHeight` que o ArcGIS Server traz de
fábrica, e aparece no descritor do serviço para o cliente ler. Um pedido de 8.000×8.000 (a refutação
declarada) volta 400 antes de alocar imagem.

**6. `time` é recusado com o motivo escrito, não ignorado.** Nenhuma camada desta implementação
declara `timeInfo` (o descritor já diz `timeInfo: null`); aceitar o parâmetro e não filtrar seria
devolver ao cliente um mapa errado sem aviso. `export` com `time` responde 422 dizendo por quê.

**7. O GeometryServer não calcula nada em Python: cada operação é uma chamada ao PostGIS.**
`project` é `ST_Transform` — a mesma transformação da consulta espacial, então a coordenada que o
cliente recebe não pode divergir da que uma consulta devolveria (medido: diferença 0,0 m em 100
pontos). `buffer` geodésico é `ST_Buffer` sobre `geography`, porque `ST_Buffer` planar sobre grau dá
um círculo achatado longe do equador. `simplify` da Esri é conserto de topologia, não generalização:
é `ST_MakeValid`, e generalizar por tolerância aqui devolveria ao cliente menos vértices do que ele
mandou (essa outra operação é a do desenho, com o pixel como tolerância).

## Consequências

- Um cliente Esri antigo passa a enxergar o catálogo por dois contratos: FeatureServer por camada e
  MapServer por mapa. O diretório por token (L2-04-b) lista os dois, com o `type` certo em cada.
- A imagem sai da mesma máquina que responde a consulta; um mapa muito denso paga no servidor. Os
  tetos (`MAPSERVER_FEICOES_POR_CAMADA`, `MAPSERVER_CAMADAS_MAX`) existem para que isso seja um
  número declarado, não uma surpresa.
- O `Cache-Control: no-store` da imagem é deliberado: o desenho depende do token do caminho, e
  nenhuma camada intermediária deve guardar a imagem de um inquilino.

## O que NÃO foi provado

QGIS e ArcGIS Pro não existem nesta máquina (sem ambiente gráfico). A cláusula do portão que pede
"QGIS adiciona o MapServer como ArcGIS REST Server e desenha (medido, captura)" está registrada na
matriz de conformidade como `nao_medido`, com esse motivo — nunca como aprovada. A comparação da
imagem com a captura do visualizador também não foi feita por esse mesmo motivo; no lugar dela, o
teste compara o pixel desenhado com a cor que o `drawingInfo` declara para a classe, que é a
propriedade que a comparação com o visualizador queria checar.

`generateKml` sai como KML simples (uma pasta por camada), sem KMZ e sem `<Style>` por classe.
