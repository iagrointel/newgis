# Widgets de dado do app sobre camada no servidor (item L5-01-c-widgets-dado)

Data: 08/09/2026. Estado: aceito. Par: ADR `20260908T1050-fontes-vistas-mensagens` (L5-07, base), `laco/decomposicao/L5_CONCEITO.md`
D21 (gráficos) e D22 (tabela); L2-04-c (`query` do FeatureServer) e L2-04-g (CQL2 no OGC API Features).

## Decisões

1. **Uma API assíncrona na Vista, dois motores por baixo.** `pagina()`, `total()`, `agregar()`, `histograma()`,
   `distintos()`, `idsDoFiltro()`, `exportar()` em `web/js/app/vistas.js`. Fonte embutida/arquivo/URL resolve em
   memória (`agregacao.js`); fonte de camada resolve no FeatureServer (`consulta.js`, classe `FonteServidor`). Os
   widgets (tabela, gráfico, filtro, lista, consulta, seleção, informação) só conhecem a Vista.
2. **A fonte de camada nunca vem inteira.** `Fonte.carregar()` de um item `camada_vetorial` descreve a camada
   (`/rest/services/{item}/FeatureServer/0`), carrega uma janela de 2 mil feições com geometria (mapa) e passa a
   modo `servidor`; `feicoes` vira o cache do que já foi visto (páginas, seleção) e `registros()`/`selecionados()`
   do L5-07 continuam a valer sobre o cache — o barramento não mudou.
3. **Filtro CQL2-JSON → `where` do FeatureServer no navegador** (`cql2ParaWhere`): =, <>, <, <=, >, >=, like, in,
   between, isNull, and/or/not; `__id` vira o campo de id do servidor; literal sempre `'...'` com aspas dobradas ou
   número; nome de campo só identificador simples. Predicado espacial vira o parâmetro `geometry` e só é aceito no
   nível de AND. O servidor revalida tudo (lista branca de colunas do L2-04-b). Rejeitado: pedir ao servidor que
   aceite CQL2 no `query` (dobraria a superfície de análise) ou acrescentar `sortby` ao OGC Features (fora do Part 1).
4. **Agregação no servidor, nunca no navegador sobre a camada** (D21): barra/linha/pizza = `outStatistics` +
   `groupByFieldsForStatistics`; histograma = min/max + N contagens (`returnCountOnly`) em paralelo; valores únicos
   = `returnDistinctValues` (ordenados no navegador: o servidor não ordena nesse modo); dispersão = amostra de até
   5 mil registros. Chart.js 4.5.1 vendido (`web/vendor`, `VERSOES.txt`), carregado por `import()` só na tela com
   gráfico; sem ele o gráfico de barras cai no SVG próprio do L5-07.
5. **Tabela própria com paginação no servidor** (D22): `resultOffset`/`resultRecordCount`/`orderByFields`; 50
   linhas por página por padrão; sem virtualização (o portão mede p95 < 300 ms por página com 100 mil e ficou em
   ~113 ms nesta máquina). Tabulator só se um item futuro medir o contrário.
6. **Filtros dinâmicos por origem** na Vista: cada origem (widget ou vista) tem o seu, combinados por AND; a mesma
   origem substitui o próprio; seleção vazia levada por mensagem tira o filtro daquela origem (regra dos
   Dashboards). Isto muda o L5-07 só no sentido de somar filtros em vez de trocar.
7. **Exportação no navegador, dado do servidor:** CSV (RFC 4180, BOM UTF-8) e GeoJSON montados no navegador a partir
   de páginas de 5 mil do filtro ativo, teto de 200 mil feições. Nada de rota nova de exportação.
8. **Dado temporário só em fonte de memória** (`adicionar-dado`): entra por `fonte.adicionar()` (evento
   `dado_adicionado`), não é gravado e some ao recarregar; fonte de camada recusa — dado novo em camada é edição.
9. **Fora deste item:** edição no app (L5-03), busca (L5-01 busca / L2-11), Near Me, análise (L3), popup por construtor
   (L5-26), Feature Report (L5-29), Business Analyst.

## Consequências

- `registro.js` publica tabela 2.0.0, gráfico 2.0.0, filtro 2.0.0 e os novos `lista`, `consulta`, `selecao`,
  `info-feicao`, `adicionar-dado` (nome de manifesto não aceita `_`); a paleta do construtor ganha os sete.
- `PlatWidget.renderizar(mudanca)` recebe a causa da repintura; os widgets de dado não refazem a página do servidor
  quando só a seleção mudou.
- Teste de paridade obrigatório: todo `where` que o navegador gera passa por `where_ast.compilar_where` no teste de
  unidade; quem mexer na tradução tem de manter isso verde.
