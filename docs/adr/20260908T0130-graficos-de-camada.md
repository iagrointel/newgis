# ADR 20260908T0130 — gráficos por camada agregados no servidor

Item L2-01-i-graficos-de-camada. Cinco tipos de gráfico no visualizador de mapa (barras por categoria, pizza,
linha por faixa de data, histograma de N faixas, dispersão com regressão), reagindo a filtro, extensão e seleção,
com clique que seleciona no mapa, guardados por camada, SVG próprio com tabela oculta e exportação PNG/CSV.

## Decisões

1. **Uma rota de gráfico ao lado da rota de agregação do L2-06-e, não em vez dela.** `POST /api/camadas/{id}/grafico`
   (`app/estatistica/rotas_graficos.py`) reutiliza do L2-06-e a leitura do item, as colunas, o filtro SQL-92 com
   extensão (extraído para `compilar_filtro`, partilhado pelas duas rotas), o cache por (item, versão, corpo) e,
   para a linha por data, o próprio `agregacao.construir_sql` com `faixa_data` (corte de mês no fuso). Barras e
   pizza têm SQL próprio porque o contrato do motor ("mais de 10.000 grupos = 422") é o certo para uma tabela e o
   errado para um gráfico: 5.000 categorias viram as N maiores mais UM grupo `outros` calculado por janelas na
   mesma consulta, e o resto nunca sai do banco. Histograma e dispersão não existiam no motor.
2. **Histograma exatamente como `numpy.histogram`.** Bordas = `linspace(lo, hi, N+1)` calculado em float8 dentro
   do Postgres com a mesma aritmética (`lo + i*passo`, última borda = máximo; valor igual ao máximo cai na última
   faixa; um valor só → `[lo-0,5, hi+0,5]`) e atribuição por `width_bucket(x, bordas[])`, a mesma busca binária
   nas bordas — o teste compara contagens E bordas, inclusive inteiros caindo nas bordas.
3. **Regressão no servidor sobre todas as linhas; amostra só para desenhar.** `regr_slope/regr_intercept/regr_r2`
   (mínimos quadrados, o mesmo problema do `numpy.polyfit(x, y, 1)`; conferido a 1e-6) e uma amostra de pontos por
   `TABLESAMPLE SYSTEM` dimensionada por `reltuples`, limitada por `limites.GRAFICO_AMOSTRA_*` e declarada na resposta.
4. **A política de RLS impedia varredura paralela.** `plat.tenant_atual()` era PARALLEL UNSAFE (padrão) e o
   planejador confere a segurança paralela antes de inlinar a função SQL: toda consulta de camada sob RLS corria em
   um só processo. Medido na bancada de 1 mi de pontos: histograma 551 ms sem paralelismo, 113 ms com 4
   trabalhadores. A migração `20260908T0100_funcoes_contexto_parallel_safe.sql` declara `tenant_atual()` e
   `usuario_atual()` PARALLEL SAFE (só leem um GUC de sessão, herdado pelos trabalhadores). Depois dela, os cinco
   pedidos do portão ficam entre 72 e 168 ms p95 (`tests/medidas/L2-01-i-graficos-de-camada.json`).
5. **Datas saem como texto.** A faixa de um gráfico é um rótulo; o `datetime` do Python não representa ano 1 a.C.
   (onde `0001-01-01 UTC` cai ao ser truncado em America/Sao_Paulo) nem `infinity`. Um conversor de tipo por cursor
   entrega `date/timestamp/timestamptz` como o Postgres os escreve — refutação "datas fora de faixa".
6. **SVG próprio, puro e limitado por construção.** `web/js/mapa/grafico_svg.js` recebe a resposta agregada e
   devolve uma árvore `{tag, atrs, filhos}`: o painel a converte com `createElementNS` (nenhum HTML em string, texto
   hostil vira texto) e o teste no node a serializa para conferir conteúdo e tamanho. Tetos de desenho (100 barras,
   50 fatias, 400 pontos de linha, 1.500 pontos de dispersão num único `<path>`) mantêm o SVG ≤ 40 kB nos piores
   casos que a rota pode devolver; a tabela oculta (`.sr-only`) e o CSV guardam a série inteira.
7. **Clique seleciona no mapa por dois caminhos equivalentes.** O elemento clicado vira um filtro SQL-92
   (`campo = 'v'`, `IS NULL`, `campo >= de AND campo < ate`, última faixa fechada) enviado ao servidor com
   `tipo: contagem` — a contagem mostrada é a contagem da barra — e uma expressão MapLibre com o mesmo significado
   numa camada de destaque clonada do estilo da camada. Sem o front-end do L2-01-h, a seleção vive no painel e é
   anunciada por `plat:selecao-camada`; o painel ouve `plat:filtro-camada` para reagir ao construtor de filtro quando
   ele entrar.
8. **Guardado por camada em localStorage**, como a ordem das camadas e os favoritos. Gravar no documento do item
   de mapa espera o esquema do L2-01-a (na fila); declarado como parcial em PARIDADE.md.

## Fora deste item
Construtor de filtro visual e seleção espacial (L2-01-h); gráficos nos painéis (L2-06-b, que usa esta primitiva);
séries múltiplas e eixos duplos; exportação vetorial (SVG/PDF) além do PNG.
