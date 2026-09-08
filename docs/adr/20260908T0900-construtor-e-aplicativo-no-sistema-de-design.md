# ADR — construtor e aplicativo publicado no sistema de design (UX-07)

Data: setembro de 2026. Estado: aceito. Trilha de interface.

## Contexto
O construtor (`/construtor`, L5-08 + L5-01-a) e o executor (`/executar`) existiam como telas finas sobre o editor de
arrasto e o executor de páginas; o motor de widgets (L5-06, `wt/cx506`) e os doze widgets de página e menu
(L5-01-d, `wt/cx501d`) estavam na fila de junção com versões antigas dos arquivos do visualizador. Faltavam: um
caminho para chegar ao construtor sem colar `?item=<id>` na URL, publicar a versão editada, estados explícitos,
textos do chrome pelo dicionário e a prova de ponta a ponta "monta por arrasto, publica e abre".

## Decisão
1. **Junção dos ramos de widgets por três vias.** `wt/cx506` carregava cópias antigas dos arquivos do visualizador
   (`app/mapa/*`, `web/js/mapa/*`, `servir_local.py`); os nossos (já refeitos em UX-04) prevalecem e só os três
   trechos próprios do motor entram no mapa (`<plat-w-mapa>`, o ouvinte de `plat-mapa-enquadrar`, o `emitir` de
   `mapa.extensao_alterada`). `wt/cx501d` junta limpo em cima.
2. **Elementos dos widgets são `plat-w-<nome>`.** `plat-tabela`, `plat-tema` e `plat-idioma` já são componentes
   do sistema de design (tabela declarativa, seletor de tema, seletor de idioma) e `definir()` do motor silenciava a
   colisão (`customElements.get` existente = pula), o que entregava um componente errado ao documento. O prefixo
   separa os dois vocabulários; `registro.js`, os módulos, `widgets.css` e os e2e seguem o mesmo nome.
3. **`/construtor` sem `?item=` é a escolha do item**: lista de `app` e `painel` (busca, ordem por modificação),
   "Novo aplicativo" que cria o item com o documento vazio e abre o editor; com item, a barra tem Salvar, Publicar
   (`POST /api/itens/{id}/versoes/{n}/publicar`, com confirmação, só depois de gravar), Executar (só `app`: um painel
   não tem página para o executor) e "escolher outro". O conflito de versão (409) vira aviso com "recarregar". Estados
   por `<plat-estado>`: carregando, inexistente, tipo que não é aplicativo, erro.
4. **Textos do chrome do editor pelo dicionário** (`construtor.*`, três idiomas); os rótulos e títulos da PALETA
   continuam dados do documento (rótulo do nó, título do esquema) — levá-los ao dicionário é o item
   L5-12-acessibilidade-i18n-construtores, que cobre os construtores todos de uma vez.
5. **Paleta e painel lateral presos ao topo com rolagem própria.** Não é só conforto: com a paleta na rolagem da
   página, o arrasto pegava o item errado depois de o documento crescer (o ponto do `dragstart` era calculado antes
   da rolagem que o próprio arrasto provocava) — medido e reproduzido pelo e2e.
6. **Árvore da estrutura conforme ARIA**: a linha (`div`) é o `treeitem` filho direto do `tree`; o botão dentro
   dela é o rótulo focável. Antes o `treeitem` era o botão dentro de um `div` sem papel, o que o axe marca como
   crítico (`aria-required-children`).
7. **Nó-widget no executor leva `data-no`** além do `data-no-id` do motor: os e2e de layout medem por `data-no`
   e um widget não pode virar um endereço diferente só porque passou a ser desenhado pelo motor.
8. **`/executar` tem estados** (sem item, carregando, inexistente, tipo errado, erro) e continua sem chrome interno:
   o aplicativo é dono do viewport.

## Consequências
- `widgets.css` só com tokens (a guarda de tokens vale para ele); `--cor` da legenda com valor local.
- Renomear os elementos muda a marcação de documentos que os citem por tag — nenhum documento cita (o documento
  guarda `tipo`, o registro resolve o elemento), então não há migração.
- O `<plat-w-mapa>` do visualizador é o recipiente do MapLibre e o widget ao mesmo tempo; `emitir` só existe quando
  o módulo do widget carregou (por isso `recipiente.emitir?.`).

## Alternativas recusadas
- Pré-visualização embutida no construtor: o executor roteia por `history.pushState(?pagina=)` na URL da própria
  página; embutir mudaria a URL do construtor. "Executar" abre em outra aba, com a URL do aplicativo.
- Manter `plat-tabela` etc. e trocar o `definir()` para lançar erro na colisão: só trocaria um silêncio por uma
  quebra; o problema é o nome.
