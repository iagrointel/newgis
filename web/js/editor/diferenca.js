/* plat — diferença visual entre duas versões do documento (item L5-09-desfazer-refazer-rascunho).

   Compara os nós por ID (ULID estável entre versões: o L5-08 nunca troca o id de um nó existente, só cria
   id novo por `inserir` — ver web/js/editor/documento.js), NUNCA pela posição na lista. É por isso que este
   módulo não reusa `app/catalogo/diff.py`/`desfazer.js::diferencaJson`: aquele é RFC 6902 posicional (o
   índice de um `add`/`remove` desloca tudo que vem depois na mesma lista), ótimo para desfazer/refazer sobre
   o MESMO documento passo a passo, péssimo para "quais nós mudaram entre v3 e v7" — inserir um nó no meio
   viraria uma cascata de "replace" em todos os nós seguintes, e a árvore mostrada ao usuário apontaria nó
   errado. Com id estável, um nó novo é `adicionado` e o resto nem aparece. */

import { emProfundidade, filhos } from './documento.js';

function propriedadesIguais(a, b) {
  return JSON.stringify(a || {}) === JSON.stringify(b || {});
}

/* devolve a lista de nós com estado 'adicionado' | 'removido' | 'alterado', na ordem de profundidade do
   documento em que cada um aparece (o removido usa a ordem do documento ANTES). `campos` lista o que mudou
   num nó 'alterado' (tipo, pai, largura_colunas, propriedades). */
export function compararDocumentos(antes, depois) {
  const nosAntes = new Map(emProfundidade(antes).map(({ no, nivel }) => [no.id, { no, nivel }]));
  const nosDepois = new Map(emProfundidade(depois).map(({ no, nivel }) => [no.id, { no, nivel }]));
  const saida = [];

  for (const [id, { no, nivel }] of nosDepois) {
    if (!nosAntes.has(id)) { saida.push({ id, estado: 'adicionado', nivel, no }); continue; }
    const anterior = nosAntes.get(id).no;
    const campos = [];
    if (anterior.tipo !== no.tipo) campos.push('tipo');
    if ((anterior.pai ?? null) !== (no.pai ?? null)) campos.push('pai');
    if (anterior.largura_colunas !== no.largura_colunas) campos.push('largura_colunas');
    if (!propriedadesIguais(anterior.propriedades, no.propriedades)) campos.push('propriedades');
    if (campos.length) saida.push({ id, estado: 'alterado', nivel, no, antes: anterior, campos });
  }
  for (const [id, { no, nivel }] of nosAntes) {
    if (!nosDepois.has(id)) saida.push({ id, estado: 'removido', nivel, no });
  }
  return saida;
}

export function resumo(comparacao) {
  const n = (estado) => comparacao.filter((c) => c.estado === estado).length;
  return { adicionados: n('adicionado'), removidos: n('removido'), alterados: n('alterado') };
}

/* monta a árvore (DOM) da diferença: usa `paleta` só para o rótulo do tipo — igual ao editor, nunca sabe o
   que o tipo FAZ. `h`/`filhos` recebidos por parâmetro para não amarrar este módulo a um DOM específico
   (o teste de unidade em Node roda sem `document`). */
export function montarArvoreDiferenca(h, comparacao, paleta) {
  const raiz = h('ul', { class: 'diferenca-arvore', role: 'list' });
  const rotuloDe = (no) => paleta?.tipos?.[no.tipo]?.rotulo || no.tipo;
  for (const item of comparacao) {
    const rotulo = rotuloDe(item.no);
    let texto = `${rotulo}`;
    if (item.estado === 'alterado') texto += ` — mudou: ${item.campos.join(', ')}`;
    const li = h(
      'li',
      { class: `diferenca-${item.estado}`, dataset: { diferenca: item.id, estado: item.estado } },
      h('span', { class: 'diferenca-rotulo' }, texto),
    );
    li.style.paddingLeft = `${item.nivel * 16 + 8}px`;
    raiz.append(li);
  }
  return raiz;
}

export { filhos };
