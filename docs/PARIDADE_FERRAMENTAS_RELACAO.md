# Paridade das ferramentas de relação com o "Summarize data" do Map Viewer (item L2-05-c)

O que este documento faz: colocar lado a lado as ferramentas de relação entre camadas desta plataforma e as
ferramentas equivalentes das categorias **Summarize data** e **Analyze patterns** do ArcGIS Online Map Viewer
(e as do ArcGIS Pro quando o botão só existe lá), dizendo o que é igual, o que é diferente e o que ainda não
existe aqui. Fontes: a referência de ferramentas do ArcGIS Pro (Spatial Join, Summarize Within, Near) e as
páginas Summarize Nearby do ArcGIS Online e do Portal 11.4 listadas no item, consultadas em setembro de 2026,
e a referência do PostGIS 3.6.

## Summarize data

| Map Viewer | aqui | diferença |
|---|---|---|
| Summarize within | `resumir_dentro` | contagem, `soma`/`media`/`minimo`/`maximo`/`contagem`/`primeiro`/`concatenar` e a medida geodésica da parte contida (`area_m2` para polígono, `comprimento_m` para linha). O `campo_grupo` do Map Viewer gera uma TABELA relacionada; aqui gera uma feição por par polígono × valor do grupo, porque a saída da plataforma é sempre uma camada. |
| Summarize nearby | `resumir_perto` | só a distância em linha reta, com a área de proximidade desenhada como buffer geodésico e devolvida como geometria da saída (o Map Viewer também devolve a área). Os modos por tempo ou distância de rota dependem do motor de roteamento (item L2-11) e **não existem aqui**: não há parâmetro que os aceite, para o formulário não prometer o que não roda. |
| Aggregate points | `agregar_pontos` | com `camada_poligonos`, agrega nos polígonos dados e atribui cada ponto a um só polígono. Sem ela, desenha a grade: `quadrada` (ST_SquareGrid) ou `hexagonal` (ST_HexagonGrid), com o lado em metros de verdade — a grade é desenhada no UTM WGS 84 do centro da camada e trazida de volta ao SRID dela, em vez de traçada em graus (que dá célula achatada conforme a latitude). O "Generate tessellation" do Pro é este mesmo desenho sem os pontos. |
| Join features | `juncao_espacial` e `juncao_atributo` | o Map Viewer junta por atributo e por espaço na mesma ferramenta; aqui são duas, porque a validação de parâmetro fica muito mais clara separada. `juncao_espacial` faz um-para-um (com regra de mesclagem por campo) e um-para-muitos, nas relações `intersecta`, `contem`, `dentro`, `a_distancia` e `mais_proximo`. `juncao_atributo` faz `inner` e `left` por igualdade de chave e **exige que as duas chaves tenham o mesmo tipo** (o Map Viewer aceita a conversão implícita e erra em silêncio quando o texto tem espaço à direita). |
| Summarize center and dispersion / Summarize attributes (só tabela) | — | a primeira é estatística direcional, a segunda devolve tabela sem geometria; nenhuma das duas cabe numa camada de saída e ficam fora deste item. |

## Analyze patterns e Use proximity

| Map Viewer / Pro | aqui | diferença |
|---|---|---|
| Near (Pro, Analysis) | `vizinho_mais_proximo` | acrescenta `vizinho_fid` e `distancia_m` (geodésica, elipsoide WGS 84) e, se pedido, campos do vizinho com prefixo `vizinho_`. O `NEAR_ANGLE` do Pro não é calculado. |
| Generate near table (Pro) | `tabela_distancias` | uma feição por par com `origem_fid`, `destino_fid` e `distancia_m`; a geometria é o segmento entre os pontos mais próximos das duas feições, para o resultado poder ser desenhado. `vizinhos_por_origem` é o `CLOSEST_COUNT`. |
| Enrich layer | `enriquecer_por_area` | o Enrich do ArcGIS traz variáveis do catálogo demográfico da Esri; aqui a variável vem de uma camada de polígonos do próprio acervo e é repartida por proporção de área geodésica, com o resultado no campo `origem_<campo>`. A conservação da soma só vale onde os polígonos de destino cobrem os de origem — está escrito no método da procedência. |
| Count points in polygon (comum em script de usuário) | `contar_dentro` | é o `resumir_dentro` sem estatística; existe separado porque é o pedido mais frequente e o formulário fica com dois campos. |

## Três diferenças de comportamento que valem para todas

1. **Contagem dupla.** Se a camada de polígonos tem feições sobrepostas, a mesma feição resumida entra em cada
   polígono que a contém — é o que o Summarize Within faz. Aqui isso é contado e escrito no método da
   procedência do item de saída ("N feições contadas em mais de um polígono"), e `atribuicao='exclusivo'`
   atribui cada feição a um só polígono (o de menor `fid`). O Map Viewer não oferece essa opção nem avisa.
2. **Feição exatamente na fronteira.** O predicado é `ST_Intersects`, então um ponto sobre a divisa conta nos
   dois polígonos vizinhos. É o mesmo resultado do `intersects` do geopandas, contra o qual a suíte confere.
3. **Ordem de execução.** O par candidato sai de `ST_Subdivide` sobre a camada de polígonos (partes de até
   `SUBDIVIDIR_VERTICES` vértices), com `DISTINCT` para desfazer a repetição da subdivisão; a relação pedida e
   toda medida são conferidas contra a geometria ORIGINAL. Polígono com muitos vértices deixa de ser uma caixa
   envolvente inútil para o índice sem que o número mude.
