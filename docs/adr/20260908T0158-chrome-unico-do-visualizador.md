# ADR — chrome único do visualizador de mapa (UX-04)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto
Cinco ramos entregaram painéis do mapa (camadas/legenda, tabela, desenho/anotações, popup, exportação), cada um com
o seu bloco na mesma coluna lateral e o seu CSS. Juntos, a coluna passava de 3 telas de altura e cada painel novo
trazia estilo próprio — o oposto do que o alfa exige.

## Decisão
1. Um só chrome: barra no topo · trilho à esquerda com um botão por painel (rótulo + tecla) · gaveta com UM
   `<plat-painel>` visível por vez · mapa em tela cheia · tabela de atributos ancorada ao rodapé do mapa. O painel
   aberto fica em `localStorage plat_mapa_painel`; em tela larga a primeira visita abre "Camadas".
2. Um painel novo entra com duas linhas de HTML (`<plat-painel id="painel-x" data-titulo="chave">` na gaveta e um
   botão no trilho) e nenhuma regra de CSS própria: o chrome do painel é o do sistema de design (refutação do item).
3. Atalhos só com o foco fora de campo de texto; Esc fecha na ordem navegação → tabela → painel; `?` lista tudo num
   diálogo. Tela cheia pela API do documento no `main` inteiro. Impressão pelo navegador esconde o chrome e fixa a
   área do mapa (`@media print`); PNG/PDF continuam no painel Impressão.
4. Celular (≤ 800 px): trilho no rodapé, gaveta como painel inferior limitado a `--painel-inferior-altura` (390 px),
   tabela e popup acoplado com o mesmo teto.
5. O aviso da barra flutua sobre o mapa (absoluto): nada no fluxo pode mudar a altura do canvas.
6. Junção de ramos que tocam o mesmo arquivo: três vias sobre a base comum, nunca união de texto — a união deixou
   funções duplicadas em Python e JS e um `<select>` vazio na tabela de atributos, todos consertados aqui.
7. e2e de trilha com tiles: o Martin de produção descobre funções só na subida, então a trilha sobe o seu Martin
   (`martin --config deploy/martin.yaml --listen-addresses 127.0.0.1:87NN` com o DSN de leitura da trilha) e a API
   recebe `PLAT_MARTIN_URL`. O papel de leitura da trilha nasce sem LOGIN em `trilha_ambiente.sh` (achado).

## Consequências
- Os e2e dos painéis abrem o painel que usam (`window.plat.mapa.abrirPainel(nome, {foco:false})`).
- `painel.js` (lista de camadas antiga do ramo de exportação) deixou de ser usado pela tela; a árvore (`camadas.js`)
  é a única lista de camadas.
