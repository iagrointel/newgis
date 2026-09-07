# Acessibilidade e idioma da base dos construtores (item L5-12-acessibilidade-i18n-construtores)

## Contexto

O L5-08-editor-arrasto entregou a primitiva `criarEditor()` (`web/js/editor/{documento,arrasto,esquema,
paleta,editor,tela}.js`) que os doze construtores da linha L5 vão reusar, com o texto da tela em português
literal (registrado como dívida no próprio cabeçalho de `tela.js`). Este item paga essa dívida na BASE —
não em cada construtor individual, porque hoje só existe UMA instanciação concreta (`/construtor`, que abre
item de tipo `app` ou `painel`; o construtor de FORMULÁRIO do `L5-03-form-builder` está `pendente` no laço
e herda esta base quando for construído.

## Decisões

1. **A "árvore" de estrutura não é `role=tree`.** O componente não implementa o modelo de teclado que
   `role=tree`/`treeitem` promete a um leitor de tela (navegação por seta ENTRE itens, com um único tabstop);
   aqui cada linha é seu próprio tabstop (Tab avança), e Alt+Seta move o nó selecionado — um modelo diferente,
   válido, mas não o de árvore ARIA. Além do desalinhamento semântico, `role=tree` RECUSA botão/select como
   descendente em qualquer profundidade (axe-core `aria-required-children`, achado real rodando o item), e
   cada linha carrega o menu "mover para" e os botões de largura/remover — descendentes que uma árvore ARIA
   de verdade não permite. Trocado por `role=list`/`listitem`, que não tem essa restrição. `aria-level` migrou
   do botão (que não o suporta; `role=button` não está na lista de `aria-allowed-attr` para esse atributo)
   para o `<li role=listitem>` que o envolve (listitem SUPORTA `aria-level`), e o nível também entra por
   extenso no `aria-label` do botão (WAI-ARIA in HTML, mapeamento de `listitem`). `aria-selected` virou
   `aria-current="true"` (semântica correta para "item atual de uma lista", não de uma árvore).
2. **Ação (clique de um nó abre outro).** `documento.js` ganhou `ligar/desligar/ligacaoDe` sobre
   `corpo.ligacoes` (primitiva que já existia, vazia, desde o L5-08; o servidor já valida `origem`/`alvo`
   contra os ids do documento em `app/catalogo/documento.py::validar_grafo`). Um nó tem no máximo uma
   ligação de ação como origem. `editor.js` ganhou o quinto painel (Ações): select de alvo + "Ligar ação" +
   lista das ligações existentes, tudo com `t()`/aria-label.
3. **Publicar.** `tela.js` ganhou o botão Publicar sobre a rota que já existe
   (`POST /api/itens/{id}/versoes/{n}/publicar`, a mesma que `catalogo/item_versoes.js` usa) — publica a
   versão que o Salvar acabou de gravar. Não é uma rota nova.
4. **Idioma do construtor.** Catálogo único por idioma (`web/js/i18n/{pt-BR,en,es}.json`, decisão herdada do
   L0-02/L5-05: um dicionário global, não um por módulo), com **paridade total de chaves nos três arquivos**
   (testado estaticamente, cláusula do item) — mas a QUALIDADE de tradução exigida por este item cobre só o
   namespace `construtor.*` (a BASE dos construtores, escopo declarado na hipótese; o resto do dicionário,
   herdado de L0-02/L0-03/etc., é escopo do L7-10-a). O seletor de idioma vive DENTRO do `/construtor`
   (não é a preferência de conta do L7-10, que ainda não existe) e troca só o dicionário desta aba, na
   hora: `carregar(idioma)` busca o JSON nono, `document.documentElement.lang` é atualizado (WCAG 3.1.1 —
   adicionado a `web/js/base/i18n.js`, afeta toda tela que já usa `carregar()`, não só o construtor) e
   `editor.redesenharTudo()` reconstrói os rótulos que `t()` gera dinamicamente (os que passam por
   `data-i18n` já se resolvem sozinhos via `aplicar()`).
5. **Contraste do tema "instrumento" no claro.** `--i-acento: #a8641c` sobre `--i-acento-texto: #fff6ec`
   media 4,36:1 — abaixo do 4,5:1 exigido pela AA para texto normal (o rótulo dos botões `.primario` desta
   tela, e de toda tela que usa a classe `instrumento`). Achado pelo axe-core rodando `/construtor`, corrigido
   escurecendo o âmbar para `#a05f1b` (4,74:1) nos dois lugares onde o token se repete
   (`@media (prefers-color-scheme: light)` e `:root[data-theme="light"]`, `web/estilo/tokens.css`). O tom
   escuro (`:root` padrão e `[data-theme="dark"]`) já media 6,81:1 — não mexido.

## Consequências

- `docs/ACESSIBILIDADE.md` (documento tipo ACR) fica para o `L7-10-b-acessibilidade-wcag21aa`, que testa o
  produto INTEIRO; este item mede e prova só a base dos construtores (as duas cláusulas de axe/e2e do
  próprio portão).
- O ajuste de contraste em `tokens.css` é uma correção de fundo (não uma bandeira nova): toda tela
  `instrumento` em modo claro do sistema herda o tom mais escuro. Nenhuma tela foi testada além do
  construtor por este item — se outra tela depender do valor exato antigo (nenhuma encontrada), é
  achado a registrar, não deste item.
- `test_editor_arrasto.py` (L5-08, já ENTREGUE) teve UMA linha ajustada: a leitura de `aria-level` passou
  do `[data-arvore]` para `.closest('.arvore-linha')`, porque o atributo mudou de elemento por este item
  (razão 1 acima). O valor e o aninhamento verificados são os mesmos; a suíte continua 5/5.
