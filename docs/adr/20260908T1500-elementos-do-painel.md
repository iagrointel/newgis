# ADR 20260908T1500 — elementos básicos do painel

Item L2-06-b-elementos-basicos. Doze tipos de elemento no documento de painel do L2-06-a (indicador, gráfico
serial, pizza, tabela, lista, mapa, detalhes, texto rico, legenda, cabeçalho, além do texto e do gráfico simples
que já existiam), todos alimentados pelo motor de agregação do L2-06-e.

## Decisões

1. **Nenhum número é calculado no navegador.** Contagem, soma, média, subtotal, total geral, agrupamento por data
   e paginação vêm do servidor. `app/paineis/dados.py` é a única ponte: cada pedido de elemento vira um corpo
   canônico do motor (`agregacao.montar_pedido` + `construir_sql`). Consequência prática que o teste guarda: o
   TOTAL de uma tabela agrupada é uma agregação sem `grupos`, nunca a soma das linhas da página — em grupos
   desbalanceados (10 contra 2.990 linhas) a média das médias erra e a soma das contagens de uma página truncada
   também. A tela só formata.
2. **Um pedido por FONTE, não por elemento.** Continua valendo o agrupamento do L2-06-a: os elementos que leem a
   mesma vista viajam numa requisição só, com o mesmo filtro de execução. O que este item acrescenta é o descarte
   de resposta ATRASADA: cada fonte tem um número de ordem e a resposta que chega depois de um filtro novo é
   jogada fora. Sem isso, quem digita no filtro global vê o painel voltar ao resultado anterior quando a resposta
   lenta (a lista de 10.000, por exemplo) chega depois da rápida — a tela mentiria sobre o filtro que está na barra.
3. **A extensão do mapa é um filtro como outro qualquer.** O elemento de mapa publica a caixa dos pontos que
   desenhou e a ação "filtrar pela extensão" a põe em `filtro_execucao.__extensao` (quatro números em EPSG:4326).
   O servidor traduz para `geom && ST_MakeEnvelope(...)` na coluna de geometria da camada — que NUNCA é campo da
   fonte: a lista branca de campos continua valendo, o painel jamais expõe a geometria crua, e o mapa recebe só o
   centroide (`ST_X/ST_Y(ST_Centroid(ST_Transform(geom, 4326)))`). Extensão malformada ou fora do mundo é 422
   nomeado (`extensao_invalida`, `extensao_fora_do_mundo`), nunca um filtro silenciosamente ignorado.
4. **Estado "sem dado" explícito em todo elemento, e zero nunca é inventado.** Filtro que não casa dá contagem 0 e
   soma/média NULO — o elemento mostra a mensagem, não um "0" que pareceria medição. O texto rico ligado a campos
   não desenha o modelo com os `{campos}` vazios ("maior valor: em"): sem feição, mostra "sem dado".
5. **Todo elemento gráfico publica a tabela equivalente do mesmo dado**, num `<details>`, ligada por
   `aria-describedby` — quem usa leitor de tela lê os números, não "gráfico". É também por onde o e2e confere que
   o que está desenhado é o que o servidor mandou.
6. **A ordem dos parâmetros do SQL segue a ordem dos `%s`, não a ordem em que o código os descobre.** Achado deste
   item, corrigido em `app/estatistica/agregacao.py`: com faixa de data (dois `%s` de fuso no SELECT e dois no
   GROUP BY) MAIS um filtro de execução, a lista montada com o `where` na frente ligava o valor do filtro ao
   `AT TIME ZONE` e o Postgres recusava com `must appear in the GROUP BY clause`. Isto é, gráfico por mês com
   qualquer filtro global caía em 500. Agora os parâmetros são montados em três partes (SELECT, WHERE, GROUP BY) e
   concatenados na ordem do texto do SQL, com regressão no nível da API.
7. **Markdown mínimo construído em DOM.** O texto rico aceita negrito, itálico, código, lista e título e monta nós
   com `document.createElement`; nunca `innerHTML`, porque o texto carrega valor de campo do inquilino.

## Consequências

- O painel avançado (L5-17) herda o contrato: gauge, conteúdo incorporado, seletores como elemento da grade,
  legenda derivada da simbologia e o mapa completo do L2-01 dentro do painel. A paridade linha a linha contra a
  lista dos Dashboards está em `docs/PARIDADE.md`, seção "Elementos do painel".
- Medido nesta trilha (`tests/medidas/L2-06-b-elementos-basicos.json`): 14 elementos desenhados com captura por
  elemento; lista de 10.000 feições a 66,8 ms por página (p95, portão ≤ 300 ms); extensão do mapa recortando
  10.000 para 999 feições, conta exata pela grade regular da camada de teste.
