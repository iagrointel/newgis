# Desfazer/refazer, autosave de rascunho e diferença entre versões (item L5-09-desfazer-refazer-rascunho)

Data: 07/09/2026. Estado: aceito. Par: `laco/decomposicao/L5_CONCEITO.md` D2, D12; ADR
`20260907T0302-editor-de-arrasto-compartilhado.md` (L5-08, seção "Consequências").

## Contexto

O editor de arrasto (L5-08) já devolve um documento NOVO a cada mutação (`web/js/editor/documento.js`), com id
de nó estável (ULID gerado na criação, D2). Faltava: (1) desfazer/refazer por sessão de edição; (2) sobreviver
a uma queda de rede no meio da edição; (3) mostrar o que mudou entre duas versões gravadas; (4) nunca perder
uma edição silenciosamente quando duas sessões escrevem o mesmo item.

## Decisão

1. **Três módulos novos em `web/js/editor/`**, todos puros ou injetáveis (testáveis fora do navegador):
   `desfazer.js` (pilha de JSON Patch RFC 6902 com direto+inverso por passo), `rascunho.js` (autosave de
   servidor + cópia local) e `diferenca.js` (comparação de duas versões por ID de nó). `tela.js` (a página
   `/construtor`) os conecta; nenhum dos três conhece DOM ou fetch além do que recebe por parâmetro.

2. **Desfazer/refazer é JSON Patch com inverso GRAVADO, não pilha de cópias inteiras.** Cada passo guarda
   `{antes, depois, direto, inverso, grupo}`; desfazer aplica `inverso` ao documento atual, refazer aplica
   `direto`. `diferencaJson`/`aplicarPatch` são uma reimplementação em JS de `app/catalogo/diff.py`, DE
   PROPÓSITO sem compartilhar código com o Python (mesmo motivo do L5-08 para a forma canônica): um defeito
   num lado não passa despercebido só porque o outro concorda consigo mesmo.

3. **"Arrastar = 1 passo" já vem de graça do L5-08**, não precisou de detecção especial: `editor.js` só chama
   `aoMudar` UMA vez por gesto completo (a pré-visualização do arrasto da alça de largura mexe em CSS, nunca
   no documento — `ligarRedimensionar`/`aoPrever`). O parâmetro `grupo` de `historico.registrar` existe para
   o dia em que um controle passar a emitir vários `aoMudar` pelo MESMO gesto (ex.: gravar a cada tecla em vez
   de no `change`): chamadas consecutivas com o mesmo `grupo` substituem o topo da pilha em vez de empilhar —
   testado com um grupo sintético de 5 redimensionamentos virando 1 passo de histórico.

4. **Autosave é o MESMO PATCH do botão Salvar, só com `?rotulo=rascunho`.** Rota nova em
   `app/catalogo/rotas_itens.py::editar_parcial`: query param aceito SÓ com o valor `"rascunho"` (regex
   `^rascunho$`), repassado a `editar_item(..., rotulo=...)` — a função já existia (usada por
   `restaurar_versao` com `rotulo="restauracao"`); só faltava um jeito do CLIENTE pedir esse rótulo
   específico. `versao_publicada` não é tocado por nenhum PATCH — só `.../versoes/{n}/publicar` muda isso
   (rota do L5-05) — logo o autosave nunca publica sozinho, por construção, não por checagem extra.

5. **Cópia local em `localStorage` é gravada a CADA mudança**, não só no ciclo do autosave de servidor
   (`rascunho.js::registrarLocal`), com `pendente: true`. Só é apagada quando o SERVIDOR confirma o MESMO
   documento (`confirmarServidor`). Uma queda de rede no meio de duas mudanças não perde a segunda: o
   navegador já tinha gravado antes de tentar a rede.

6. **Diferença entre versões é por ID de nó, não RFC 6902 posicional.** `diferenca.js::compararDocumentos`
   NÃO reusa `diferencaJson`/`app/catalogo/diff.py`: aquele é posicional (inserir um nó no meio da lista
   desloca o índice de tudo que vem depois, virando uma cascata de "replace" que aponta para o nó errado na
   tela). Como o ULID de um nó é estável entre versões (D2), comparar por id classifica cada nó em
   adicionado/removido/alterado corretamente mesmo com reordenação no meio.

7. **Conflito de edição concorrente já existia no L5-05** (`versao_atual` no corpo do PATCH, 409
   `versao_conflito` quando diverge do banco) — este item só ACRESCENTA a reação da TELA: ao receber 409,
   busca a versão do servidor, mostra a diferença contra a base local, e exige um clique explícito
   ("gravar mesmo assim" ou "descartar a minha") antes de qualquer escrita nova. Nunca sobrescreve sozinho.

## Consequências

- **Limitação aceita e registrada**: a rota de compartilhamento (`app/catalogo/rotas_compartilhamento.py`,
  herdada, fora do escopo deste item) serve o `dados` CORRENTE do item no link público, não uma vista presa a
  `versao_publicada` — não existe ainda um "renderizador do publicado" separado do editor. O que este item
  garante é mais estreito e já é o que o portão pede: o autosave não AVANÇA o ponteiro de publicação nem
  altera o CONTEÚDO da versão que esse ponteiro aponta (provado comparando `GET .../versoes/{versao_publicada}`
  antes e depois — imutável por construção do L5-05). Renderizar o publicado de verdade (sem o rascunho
  vazando pro link público) é trabalho de um item de runtime de app, ainda não escrito.
- `tests/unit/test_desfazer_refazer.py` roda por Node (`tests/unit/apoio_editor_desfazer.mjs`), mesmo padrão
  de `tests/expressoes/executar_js.mjs`: sem framework de teste em JS no repositório, quem afirma é o Python,
  de fora, rodando o módulo de verdade.
- Nota de ambiente de trilha (não vale para produção, mesma observação do L5-08): o e2e desta trilha rodou
  atrás de um nginx próprio em `127.0.0.1:8269` com `include mime.types` (sem isso o Chromium recusa os
  módulos JS por MIME `text/plain`) e `proxy_set_header Origin ""` (sem isso toda escrita sob cookie cai em
  403 `origem_invalida`, porque a origem do navegador nunca bate com a `PLAT_URL_PUBLICA` fictícia da trilha).
