# Editor de arrasto compartilhado pelos construtores (item L5-08-editor-arrasto)

Data: 07/09/2026. Estado: aceito. Par: `laco/decomposicao/L5_CONCEITO.md` D1, D2, D12, D14, D15, D20.

## Contexto

Doze itens da linha L5 (app, painel, fluxo, formulário, narrativa, site, app instantâneo, popup, simbologia,
relatório, camada, captura) editam documentos diferentes com os MESMOS gestos: pôr na tela, mover, aninhar,
redimensionar, escolher e editar propriedade. Se cada construtor escrever o seu, são doze implementações de
acessibilidade, doze regras de ciclo e doze formatos de largura.

## Decisão

1. **Cinco módulos próprios em `web/js/editor/`**, sem framework e sem biblioteca de arrasto (D1 opção a):
   `documento.js` (modelo puro: inserir, mover, redimensionar, propriedade, remover, forma canônica),
   `arrasto.js` (HTML5 Drag and Drop para paleta→tela e tela→tela; Pointer Events com `setPointerCapture`
   para a alça de largura), `esquema.js` (validação de propriedade contra o subconjunto de JSON Schema que o
   painel usa, e recusa explícita de esquema que use palavra fora do subconjunto), `paleta.js` (catálogo de
   tipos em DADO) e `editor.js` (as quatro regiões e os comandos). Medido: 43.771 bytes de código próprio,
   0 byte de biblioteca de arrasto.
2. **O editor não conhece tipo nenhum.** Tudo o que ele sabe de um tipo vem da paleta: rótulo, se aceita
   filhos, largura padrão e JSON Schema das propriedades. Quando o L5-06 publicar o manifesto de widget,
   `criarEditor({paleta})` recebe a paleta montada do manifesto e nenhum arquivo deste item muda.
3. **Largura em COLUNAS da grade de 12, nunca em pixel.** O arrasto da alça mede a largura de uma coluna na
   hora (`(largura útil + vão) / 12`) e converte o deslocamento antes de gravar. O documento não tem nenhuma
   medida em px — o e2e confere procurando a cadeia "px" no JSON gravado.
4. **Uma operação, três caminhos, um só código.** Arrasto, teclado e menu chamam as mesmas quatro funções
   (`adicionar`, `mover`, `largura`, `remover`). É o que faz a equivalência do portão ser estrutural e não
   coincidência: não existe caminho de mouse que passe por outro código.
5. **Lista plana com `pai`, não árvore aninhada** (motivo em `documento.js`): o esquema `app-v2`/`painel-v2`
   do servidor já valida `corpo.nos` como lista com ULID e recusa id repetido e ligação órfã; árvore aninhada
   exigiria migração de esquema e quebraria o JSON Patch do desfazer (L5-09).
6. **Comparação por forma canônica.** Dois documentos montados por caminhos diferentes têm ULIDs diferentes,
   por construção (D2: id gerado na criação). A prova de equivalência troca cada ULID por `n1..nN` na ordem
   de profundidade e compara todo o resto. Está escrito duas vezes de propósito — em `documento.js` para o
   editor e no teste, em Python, para que um defeito na função não passe despercebido nos dois lados.

## Consequências

- L5-09 (desfazer) tem o modelo pronto: toda operação devolve documento novo, com id estável.
- L5-12 (acessibilidade e i18n dos construtores) recebe o caminho de teclado já existente e leva os textos
  literais desta tela para o dicionário — a tela `/construtor` está hoje em português literal.
- L5-06 substitui `paleta.js` por manifesto sem tocar no editor; L5-01-a, L5-02-a, L5-03-a, L5-04-a, L5-20,
  L5-26, L5-27, L5-29, L5-31, L5-34 herdam as primitivas.
- O que este item NÃO entrega: desfazer/refazer (L5-09), edição concorrente (L5-13), vista móvel própria
  (L5-15), zona de soltura "antes/depois" por metade do alvo (soltar sobre um nó entra sempre ANTES dele) e
  arrasto de reordenação dentro da própria árvore (a árvore reordena por teclado e por menu, não por gesto).

## Nota de ambiente de teste (não vale para produção)

O e2e da trilha roda com um nginx próprio em 127.0.0.1:8178 que reescreve o cabeçalho `Origin` para o valor
de `PLAT_URL_PUBLICA` da trilha. Sem isso, toda escrita sob cookie feita PELO NAVEGADOR cai no 403
`origem_invalida` de `app/auth/sessao.py::checar_escrita_sob_cookie` — em produção os dois coincidem porque
o nginx serve a própria URL pública. É a primeira tela do produto que grava por `fetch` sob cookie a partir
do navegador; os e2e anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`.
