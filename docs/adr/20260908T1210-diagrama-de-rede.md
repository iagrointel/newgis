# 20260908T1210 — o diagrama de rede é um grafo derivado, com coordenada própria e estado de consistência

Item `L4-04-d-diagrama-esquematico`. Situação: aceito.

## Contexto

Quem opera uma rede de distribuição não lê o mapa dela. O mapa mostra onde as coisas estão; o esquema mostra
como elas se ligam, e é o esquema que responde "se eu abrir esta chave, o que fica sem energia". A fonte
declarada no item (ArcGIS Pro 3.4, *network diagrams*) resolve isso com três peças: um MODELO (template) que
diz como simplificar, REGRAS de construção que executam a simplificação, e LAYOUTS que dão posição ao
resultado.

## Decisões

1. **O diagrama é derivado três vezes e não é fonte de nada.** A topologia (`plat.rede_topo_*`) já é índice
   derivado das feições; o recorte escolhe que parte dela entra; as regras simplificam; o layout posiciona.
   Nada do que o diagrama guarda pode ser lido como dado da rede.

2. **As coordenadas do diagrama são adimensionais, não graus.** `x`,`y` vivem no espaço do diagrama. Guardar
   o esquema em graus faria parecer que o desenho tem geografia, e a primeira pessoa a somar aquilo a uma
   camada de mapa acharia que a rede se mudou de lugar. A tela usa MapLibre com uma transformação LINEAR
   declarada para desenhar o espaço cartesiano, e o quadro do esquema não tem escala nem coordenada.

3. **A âncora de volta ao mapa é a CHAVE do nó, nunca a geometria.** `terminal:<feicao>:<n>`,
   `conexao:<no>` ou `conteiner:<feicao>`. Sem chave estrangeira para `rede_topo_no`, porque
   `topologia.habilitar()` apaga e refaz o índice inteiro e uma FK levaria o diagrama junto na primeira
   reconstrução — o mesmo raciocínio que o controlador de subrede já seguia (ADR 20260907T2031).

4. **Regra reduz, layout posiciona — e nenhum dos dois pode perder ligação.** A redução de junção de
   passagem nunca remove um nó cujos dois vizinhos são o MESMO nó: isso apagaria a aresta de um laço, e uma
   rede em anel deixaria de parecer anel. O layout é conferido no código: se o número de nós ou de arestas
   mudar durante o posicionamento, o programa levanta erro em vez de entregar um desenho a menos.

5. **Separação mínima por varredura em grade, não por comparação de todos contra todos.** A cláusula do
   portão pede zero par de nós a menos de 1 unidade. Com célula do tamanho da separação mínima, basta olhar
   as 8 células vizinhas, e o custo fica proporcional ao número de nós. O empurrão é em espiral quadrada, na
   ordem das chaves: o mesmo grafo dá sempre o mesmo desenho.

6. **Consistência é marcada na hora da edição, não calculada depois.** Editar a rede marca o diagrama como
   `inconsistente` no mesmo instante em que marca a subrede suja, porque `habilitar` apaga as áreas sujas: se
   o estado fosse calculado a partir das áreas abertas, reconstruir a topologia limparia em silêncio um
   desenho obsoleto. O diagrama não se refaz sozinho — quem manda refazer é quem lê.

7. **`colapsar_conteiner` é tradução, não equivalência.** O modelo desta plataforma não tem contêiner com
   conteúdo; o que existe de "caixa" é o dispositivo multi-terminal, e é ele que a regra colapsa. Está
   escrito assim em `docs/PARIDADE.md`, como divergência deliberada.

## Consequências

- Seis layouts, três regras: menos que a fonte, e a diferença está nomeada linha a linha na paridade. Regra
  ou layout desconhecido é recusado, nunca ignorado.
- A força dirigida compara todos os nós contra todos a cada rodada; acima de 200 nós o desenho cai na grade,
  com o aviso na resposta. Prometer força dirigida num alimentador inteiro seria prometer um pedido que não
  volta.
- Não há edição manual do desenho (mover nó e guardar a posição). Fazer isso exige decidir o que acontece
  com a posição guardada quando o diagrama é regerado, e este item não toma essa decisão.
- O quadro do mapa desenha só os nós. A linha exigiria a geometria do trecho, e traçar uma reta entre dois
  nós seria inventar traçado.
