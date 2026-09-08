# ADR — ferramentas de rede como ferramentas do registro, sobre o serviço de rota já existente

Item `L2-05-f-rede-isocrona-rota-ferramentas`. Estado: aceita.

## Contexto

A casa já tem duas peças prontas: o registro de ferramentas do L2-05-a (`@ferramenta`, execução como job ou em
processo, resultado como item com proveniência e `derivado_de`, superfície GPServer) e o serviço de rota do
L2-11-c (`/api/rota`, `/api/matriz`, `/api/isocrona` sobre o OSRM isolado `plat-osrm-guarulhos`). Faltava a
ponte: pedir uma isócrona e receber uma CAMADA do catálogo, não um JSON de resposta.

## Decisão

1. As seis ferramentas de rede (`area_de_servico`, `rota_paradas`, `matriz_od`, `mais_proximas`,
   `conectar_a_rede`, `localizar_alocar`) são ferramentas comuns do registro. Não têm rota de API própria, não
   têm tabela própria e não têm tela própria: entram no catálogo `/api/ferramentas`, no formulário de `/analise`
   e no GPServer pelo mesmo caminho do `buffer`.
2. Nenhuma delas fala com o OSRM. Quem fala é `app/rede/osrm.py` e `app/rede/isocrona.py` — as mesmas funções
   que atendem `/api/isocrona`. Por isso a isócrona de um ponto sai idêntica à do serviço: é a mesma função, e o
   teste do portão compara os dois polígonos.
3. A versão do grafo (arquivo, data e sha256 do recorte OSM) passa a ter uma fonte única,
   `app.rede.osrm.PROVENIENCIA`, e entra no `metodo` de toda camada derivada — o resultado diz sobre que grafo
   foi calculado.
4. Ausência de rota é NULL, nunca 0: par sem rota na matriz, ponto fora do alcance da rede e isócrona de ponto
   sem via saem nulos, com o motivo no log da execução.
5. `localizar_alocar` resolve só cobertura máxima e por heurística gulosa, dito no `metodo` da camada e na
   descrição da ferramenta. Não se anuncia ótimo o que não é.

## Consequências

- Três defeitos do que já existia apareceram ao exercitar o portão e foram corrigidos aqui:
  a isócrona de 30 min estourava o tamanho da URL (a grade passa do `--max-table-size` do OSRM) — agora a
  linha da matriz é partida em blocos por `osrm.matriz_grande`; o `ST_Extent` de uma camada de saída com uma
  feição só degenera em ponto e quebrava a publicação do item; e o CHECK de `plat.item` recusa caixa degenerada,
  então nesse caso o item fica sem extent em vez de ganhar uma caixa inventada.
- O teto de matriz do PEDIDO (1.000×1.000 declarado) é maior que o teto de uma CHAMADA ao OSRM (625): a
  diferença é resolvida por blocos, não relaxando o `--max-table-size` do contêiner.
- A grade da isócrona ainda passa de `PLAT_ROTA_ISOCRONA_MAX_PONTOS` quando a resolução bate no piso de 2.000 m
  (comportamento do L2-11-c, não alterado aqui); com blocos isso deixou de ser erro, mas continua a valer que
  30 min sobre um recorte pequeno satura na borda do grafo.
