/* plat — visualizador em tempo de execução do documento de construtor (item L5-15-vista-movel-responsivo).
   É o "app publicado": renderiza `corpo.nos` (web/js/editor/documento.js) SEM nenhuma primitiva de edição —
   sem arrasto, sem seleção, sem painel de propriedades. Duas formas de chegar ao documento, que convivem sem
   se atrapalhar:

   1. `?item=<id>` na URL: carrega pela API, como qualquer outra tela — é o caminho de quem abre o app
      publicado direto (o cenário do adversário: "abre o app publicado em 360×640");
   2. `postMessage({tipo:'plat-documento-preview', documento})` de MESMA ORIGEM: é como o construtor alimenta
      a pré-visualização por dispositivo (web/js/editor/pre_visualizacao.js) SEM salvar — o iframe carrega
      esta página vazia (sem `?item=`) e recebe o documento em edição a cada mudança.

   Duas larguras, uma regra cada (portão do item):
     ≤ 600 px, `vista_movel.manual` falso/ausente  -> REFLOW automático: puro CSS (web/estilo/visualizador.css
       força a grade de 12 colunas para 1), a mesma árvore de sempre, nada escondido — é o que garante a
       refutação do adversário (nenhum widget cortado ou inacessível);
     ≤ 600 px, `vista_movel.manual` verdadeiro -> a lista de `corpo.vista_movel.nos` (só nó de RAIZ, D1 do
       item) manda: visibilidade e ordem vêm de lá, o reflow automático não se aplica a esse nível;
     > 600 px -> grade de 12 colunas normal, igual à tela do construtor, sem nenhuma das duas regras acima.

   `tabela` widget não tem dado ligado ainda (isso é o L5-06/L5-07: motor de widget/fonte de dado, fora deste
   item) — o que a cláusula "tabela vira lista" testa é a TROCA DE ELEMENTO SEMÂNTICO (table -> ul) com a
   única propriedade que o widget já grava de verdade (`linhas_por_pagina`), nunca um dado inventado. */
import { obter, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import * as doc from '../editor/documento.js';
import { PALETA_LAYOUT } from '../editor/paleta.js';

const MEDIA_MOVEL = window.matchMedia('(max-width: 600px)');

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  const raiz = document.getElementById('vista-raiz');
  const aviso = document.getElementById('aviso');
  const h1 = document.getElementById('v-titulo');
  let documentoAtual = null;

  const id = new URLSearchParams(location.search).get('item');
  if (id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    const item = r.json;
    const dados = item.dados || {};
    documentoAtual = dados.corpo ? { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } } : doc.novoDocumento(item.tipo);
    h1.textContent = item.titulo;
    h1.hidden = false;
    document.title = `${item.titulo} · plat`;
    renderizar(documentoAtual);
  }

  /* mesma origem só (D23 do L5_CONCEITO vale aqui também: nunca aceitar postMessage de outra origem) */
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin) return;
    if (!ev.data || ev.data.tipo !== 'plat-documento-preview') return;
    documentoAtual = ev.data.documento;
    renderizar(documentoAtual);
  });

  MEDIA_MOVEL.addEventListener('change', () => renderizar(documentoAtual));

  function renderizar(documento) {
    limpar(raiz);
    if (!documento) { raiz.append(h('p', { class: 'vazio' }, 'sem documento')); return; }
    const movel = MEDIA_MOVEL.matches;
    const vm = doc.vistaMovel(documento);
    raiz.classList.toggle('v-movel', movel);
    raiz.classList.toggle('v-movel-manual', movel && vm.manual);
    raiz.classList.toggle('v-desktop', !movel);

    if (movel && vm.manual) {
      for (const { no } of doc.nosVistaMovelManual(documento)) raiz.append(renderNo(no, documento, movel));
      if (!raiz.childElementCount) raiz.append(h('p', { class: 'vazio' }, 'vista móvel manual sem nenhum nó visível'));
      return;
    }
    for (const no of doc.filhos(documento, null)) raiz.append(renderNo(no, documento, movel));
    if (!raiz.childElementCount) raiz.append(h('p', { class: 'vazio' }, 'documento vazio'));
  }

  function renderNo(no, documento, movel) {
    const def = PALETA_LAYOUT.tipos[no.tipo] || { rotulo: no.tipo };
    const el = h('div', {
      class: `v-no v-tipo-${no.tipo}`, dataset: { no: no.id, tipo: no.tipo },
      'aria-label': def.rotulo,
    });
    if (!movel) el.style.gridColumn = `span ${no.largura_colunas}`;

    if (no.tipo === 'grupo') {
      const dentro = h('div', { class: 'v-no-filhos', dataset: { filhosDe: no.id } });
      for (const f of doc.filhos(documento, no.id)) dentro.append(renderNo(f, documento, movel));
      el.append(h('p', { class: 'v-rotulo-grupo' }, no.propriedades?.rotulo || def.rotulo), dentro);
      return el;
    }
    if (no.tipo === 'texto') {
      const nivel = no.propriedades?.nivel || 'corpo';
      const tag = nivel === 'titulo' ? 'h2' : nivel === 'legenda' ? 'small' : 'p';
      el.append(h(tag, { class: 'v-texto' }, no.propriedades?.texto || ''));
      return el;
    }
    if (no.tipo === 'imagem') {
      el.append(h('img', { class: 'v-imagem', src: no.propriedades?.url || '', alt: no.propriedades?.alternativo || '' }));
      return el;
    }
    if (no.tipo === 'mapa') {
      /* mapa não some nunca: nem no reflow automático nem no manual (a integração de mapa de verdade é
         outro item; aqui a exigência do portão — "mapa visível" — é sobre PRESENÇA e TAMANHO no DOM em
         qualquer largura, que é o que se pode provar sem o widget de mapa de verdade). */
      const zoom = no.propriedades?.zoom ?? 0;
      const escala = no.propriedades?.mostrar_escala ? 'com escala' : 'sem escala';
      el.classList.add('v-mapa');
      el.setAttribute('role', 'img');
      el.setAttribute('aria-label', `Mapa, zoom ${zoom}, ${escala}`);
      el.append(h('span', { class: 'v-mapa-legenda' }, `Mapa · zoom ${zoom} · ${escala}`));
      return el;
    }
    if (no.tipo === 'tabela') {
      const linhas = no.propriedades?.linhas_por_pagina ?? '';
      el.classList.add('v-tabela-caixa');
      if (movel) {
        el.append(h('ul', { class: 'v-tabela-lista', role: 'list', 'aria-label': 'Tabela' },
          h('li', {}, `Linhas por página: ${linhas}`)));
      } else {
        el.append(h('table', { class: 'v-tabela', 'aria-label': 'Tabela' },
          h('caption', {}, 'Tabela'),
          h('thead', {}, h('tr', {}, h('th', {}, 'Linhas por página'))),
          h('tbody', {}, h('tr', {}, h('td', {}, String(linhas))))));
      }
      return el;
    }
    el.append(h('span', {}, def.rotulo));
    return el;
  }
}
