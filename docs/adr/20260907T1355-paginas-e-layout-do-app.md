# Páginas e layout do app (item L5-01-a-layout-paginas)

Data: 07/09/2026. Estado: aceito. Par: `laco/decomposicao/L5_CONCEITO.md`; ADR `20260907T0302-editor-de-arrasto-compartilhado.md` (L5-08, base desta entrega).

## Contexto

O item L5-08 entregou o editor de arrasto GENÉRICO (documento em lista plana, paleta em dado, editor sem
`if (tipo === ...)`). Faltava o que faz um documento `app` virar um APLICATIVO navegável: página de tela
cheia e página rolável, cabeçalho/rodapé, menu entre páginas, painel lateral recolhível, os widgets de
layout do Experience Builder (linha, coluna, grade, acordeão, painel fixo) e janela (modal/ancorada).

## Decisão

1. **Página é um NÓ, não um conceito à parte do servidor.** `pagina` é só mais um tipo na paleta
   (`web/js/editor/paleta_paginas.js`), com propriedades `titulo`, `caminho`, `tipo_pagina`
   (`tela_cheia`/`rolavel`), `ordem`, `oculta`, `inicial`. Convenção da linha (documentada, não imposta pelas
   primitivas genéricas e compartilhadas de `documento.js`): um nó `pagina` só faz sentido na RAIZ
   (`pai=null`); o resto mora dentro dela. Isso evitou qualquer migração de esquema — a coluna `esquema` de
   `tipo_item` já aceita `tipo` de nó como string livre (`028_documento_grafo.sql`).
2. **Um EXECUTOR separado do editor** (`web/js/executor/executor.js` + `paginas.js`), que lê o MESMO
   documento e a MESMA paleta que o editor usa para autoria. O editor (`editor.js`, compartilhado com os
   outros 11 construtores) desenha CAIXAS GENÉRICAS de arrasto; o executor desenha o SIGNIFICADO de cada
   tipo em produção — nav de verdade, painel que recolhe, `<dialog>` que abre e fecha. Nenhum dos dois
   conhece o outro; os dois só conhecem `documento.js` (`filhos`, `emProfundidade`) e a paleta.
3. **Roteamento por querystring, não por segmento de URL**: `/executar?item=<id>&pagina=<caminho>`, mesma
   convenção de `/construtor?item=<id>` (L5-08). Trocar de página chama `history.pushState` (sem recarregar);
   abrir a URL direto ou dar F5 lê só a querystring, sem estado de sessão. Decisão de escopo: um roteador por
   segmento de caminho (`/executar/<id>/<pagina>`) exigiria uma rota curinga nova em `app/paginas.py`
   (hoje cada rota é uma entrada fixa no dicionário `PAGINAS`) — mais mudança num arquivo que a árvore
   principal também mexe, para o mesmo resultado observável.
4. **Janela modal usa `<dialog>` nativo** — Esc-para-fechar e backdrop vêm de graça do navegador (portão do
   item exige "fecha por Esc"; não escrevemos um `keydown` para isso, o próprio `<dialog>.showModal()` já
   captura). Janela "ancorada" (o outro modo que a Esri chama "Window" ancorada perto do que a abriu) não usa
   `<dialog>` (que sempre centraliza) — é um `<div>` posicionado com Esc por `keydown` manual e fechamento ao
   clicar fora.
5. **Grade por CSS Grid `repeat(N, minmax(0,1fr))`, linha/coluna por Flexbox com `flex: <colunas> 1 0` e
   `min-width:0`/`min-height:0` em cada item flexível, sem exceção.** A proporção entre dois filhos da grade é uma razão
   de frações — invariante à largura do contêiner por definição do próprio CSS Grid, não por cálculo nosso;
   é isso que a cláusula "grade responsiva mantém proporção" mede (medido: razão 2,016 a 1200 px e 2,033 a
   600 px, portanted `tests/medidas/L5-01-a-layout-paginas.json`). O `min-width:0`/`min-height:0` é a linha
   que existe especificamente por causa da refutação do adversário: sem ela, Flexbox por padrão nunca encolhe
   um item abaixo do tamanho do seu conteúdo, e 6 níveis de linha/coluna aninhados estouram a largura da tela
   (bug clássico de Flexbox, não hipotético — reproduzido e corrigido nesta entrega).
6. **`app` ganha a paleta nova; os outros tipos de construtor continuam com a paleta de layout comum do
   L5-08.** `web/js/editor/tela.js` (a tela fina do L5-08) escolhe a paleta pelo `tipo` do item — a ÚNICA
   mudança feita num arquivo que outro item também toca, e é de uma linha (`paletaDoTipo`).

## Consequências

- O editor continua sem saber o que é uma página; um construtor futuro (painel, formulário) pode reusar
  `pagina`/`menu`/`janela` da mesma paleta sem tocar em `editor.js` nem `documento.js`.
- Falta (fora do portão deste item, registrado para não fingir que não falta): o editor NÃO tem uma vista
  "por página" — todas as páginas aparecem na mesma tela do construtor, uma abaixo da outra. Fica para
  L5-15 (vista móvel) ou um item de UX do construtor.
- A convenção "página só na raiz" não é imposta pelas primitivas compartilhadas — um documento poderia
  tecnicamente aninhar uma página dentro de outra. Impor isso em `documento.js` afetaria os outros 11
  construtores; a prova de que a montagem certa funciona está no e2e do portão, não numa trava de código.
