/* plat · catálogo — a lista de itens nas três vistas (tabela | lista | grade) sobre o mesmo JSON de GET /api/itens
   (ADR 0004 seção 15.1). Pagina por cursor ("carregar mais": os itens já vistos não repetem nem pulam), seleção em
   massa até 100, favoritar por linha, abrir por clique/Enter, teclado j/k/x. A tabela é própria (não <plat-tabela>)
   porque acrescenta linhas sem perder a seleção e ordena pelo cabeçalho; as classes de estilo são as da base. */
import { h, limpar, marcador } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { mensagemDe } from '../base/api.js';
import * as api from './api.js';
import { ctx, parametrosLista, rotuloTipo, tipoDe, selecionado, alternarSelecao, limparSelecao, marcaFavoritos, marcarFavoritoLocal, aplicarFavoritosLocais } from './contexto.js';
import { elipse, quando, rotuloAcesso, nomeDono, LIMITES } from './formato.js';
import { icone, iconeDoTipo } from './icones.js';

let seq = 0;
let aoAbrir = () => {};
let foco = -1;
const COLUNAS = [['titulo', 'catalogo.col_titulo'], ['tipo', 'catalogo.col_tipo'], ['dono', 'catalogo.col_dono'], ['modificado_em', 'catalogo.col_modificado'], ['acesso', 'catalogo.col_acesso']];
const ORDENAVEIS = new Set(['titulo', 'tipo', 'dono', 'modificado_em', 'criado_em', 'tamanho_bytes', 'pontuacao']);

const el = (id) => document.getElementById(id);

export function iniciar({ abrir }) {
  aoAbrir = abrir;
  el('carregar-mais').textContent = t('catalogo.carregar_mais');
  el('carregar-mais').addEventListener('click', () => carregar({ mais: true }));
  ctx.assinar(() => render(), ['itens', 'vista', 'selecionados', 'carregando']);
}

/* recarrega do zero (reiniciar) ou pede a página seguinte pelo cursor (mais) */
export async function carregar({ mais = false } = {}) {
  const aviso = el('lista-aviso');
  const meu = ++seq;
  const marcaAntes = marcaFavoritos();   // estado dos favoritos ANTES do pedido (achado G2-9)
  const p = parametrosLista();
  if (mais) { if (!ctx.ler('cursor')) return; p.cursor = ctx.ler('cursor'); } else limparSelecao();
  ctx.definir({ carregando: true });
  let r;
  try {
    r = await api.listar(p);
  } catch (e) {
    if (meu !== seq) return;
    ctx.definir({ carregando: false });
    if (e.status === 401) return;
    aviso.erro(`${t('erro.carregar')}: ${e.message}`);
    if (!mais) ctx.definir({ itens: [], total: 0, cursor: null, aproximado: false });
    return;
  }
  if (meu !== seq) return; // resposta atrasada: a lista nunca volta no tempo
  aviso.limpar();
  const novos = aplicarFavoritosLocais(Array.isArray(r.itens) ? r.itens : [], marcaAntes);
  const itens = mais ? [...ctx.ler('itens'), ...novos] : novos;
  ctx.definir({ itens, total: r.total ?? itens.length, cursor: r.proximo_cursor || null, aproximado: !!r.aproximado, carregando: false });
  const ap = el('aproximado');
  ap.hidden = !r.aproximado;
  ap.textContent = r.aproximado ? t('catalogo.aproximado', { q: ctx.ler('q') }) : '';
  if (!mais) foco = -1;
}

export function recarregar() { return carregar({ mais: false }); }

/* ---------- peças comuns às vistas ---------- */
function miniatura(item, classe = '') {
  const tipo = tipoDe(item.tipo);
  if (item.miniatura) {
    const img = h('img', { class: `mini ${classe}`.trim(), src: item.miniatura, alt: '', loading: 'lazy', width: 60, height: 40 });
    // 204 (sem miniatura) ou falha de rede: troca pelo ícone do tipo sem erro de console
    img.addEventListener('error', () => img.replaceWith(iconeCaixa(tipo, classe)), { once: true });
    return img;
  }
  return iconeCaixa(tipo, classe);
}
function iconeCaixa(tipo, classe) { return h('span', { class: `mini-icone ${classe}`.trim(), title: tipo ? tipo.rotulo : '' }, iconeDoTipo(tipo, { tamanho: 22 })); }

function selos(item) {
  const s = [];
  if (item.status === 'autoritativo') s.push(marcador(t('catalogo.status_autoritativo'), 'ok'));
  if (item.status === 'obsoleto') s.push(marcador(t('catalogo.status_obsoleto'), 'atencao'));
  if (item.protegido) s.push(h('span', { class: 'marcador', title: t('catalogo.protegido') }, icone('cadeado', { tamanho: 11 })));
  return s.length ? h('span', { class: 'selos' }, ...s) : null;
}

function botaoFavorito(item) {
  const b = h('button', { type: 'button', class: 'favorito', 'aria-pressed': String(!!item.favorito), 'aria-label': item.favorito ? t('catalogo.desfavoritar') : t('catalogo.favoritar'), title: item.favorito ? t('catalogo.desfavoritar') : t('catalogo.favoritar') }, icone('estrela', { tamanho: 16 }));
  b.addEventListener('click', async (e) => {
    e.stopPropagation();
    b.disabled = true;
    const querer = !item.favorito;
    // a intenção é registrada ANTES da chamada: se um GET /api/itens pedido antes do clique chegar no meio, a
    // lista repintada não volta ao estado velho (achado G2-9). Em erro, a marca é desfeita.
    marcarFavoritoLocal(item.id, querer);
    b.setAttribute('aria-pressed', String(querer));
    b.setAttribute('aria-label', querer ? t('catalogo.desfavoritar') : t('catalogo.favoritar'));
    try {
      if (querer) await api.favoritar(item.id); else await api.desfavoritar(item.id);
      item.favorito = querer;
      if (ctx.ler('aba') === 'favoritos' && !querer) ctx.definir({ itens: ctx.ler('itens').filter((x) => x.id !== item.id), total: Math.max(0, ctx.ler('total') - 1) });
    } catch (err) {
      marcarFavoritoLocal(item.id, !querer);
      b.setAttribute('aria-pressed', String(!querer));
      b.setAttribute('aria-label', !querer ? t('catalogo.desfavoritar') : t('catalogo.favoritar'));
      el('lista-aviso').erro(err.message);
    } finally { b.disabled = false; }
  });
  return b;
}

function caixaSelecao(item) {
  const cx = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_linha') });
  cx.checked = selecionado(item.id);
  cx.addEventListener('click', (e) => e.stopPropagation());
  cx.addEventListener('change', () => {
    if (!alternarSelecao(item.id, cx.checked)) { cx.checked = false; el('lista-aviso').mostrar(t('catalogo.selecao_limite', { max: LIMITES.lote }), 'atencao'); }
  });
  return cx;
}

function tituloLink(item) {
  const a = h('a', { class: 'titulo-item', href: `/conteudo/${item.id}`, title: item.titulo }, elipse(item.titulo, 200));
  a.addEventListener('click', (e) => { e.preventDefault(); aoAbrir(item.id); });
  return a;
}

function ligarAbrir(no, item) {
  no.tabIndex = 0;
  no.dataset.id = item.id;
  no.addEventListener('click', (e) => { if (e.target.closest('button, input, a')) return; aoAbrir(item.id); });
  no.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); aoAbrir(item.id); }
    if (e.key === 'x' || e.key === ' ') { if (e.target !== no) return; e.preventDefault(); alternarSelecao(item.id); }
  });
}

/* ---------- render ---------- */
function render() {
  const raiz = el('lista');
  raiz.setAttribute('aria-busy', String(!!ctx.ler('carregando')));
  const itens = ctx.ler('itens');
  const sel = new Set(ctx.ler('selecionados'));
  limpar(raiz);
  const vista = ctx.ler('vista');
  raiz.dataset.vista = vista;
  if (!itens.length) {
    raiz.append(h('p', { class: 'vazio' }, ctx.ler('carregando') ? t('catalogo.carregando') : (ctx.ler('q') || ctx.ler('pastaId') ? t('catalogo.vazio_filtro') : t('catalogo.vazio'))));
  } else if (vista === 'tabela') raiz.append(tabela(itens, sel));
  else if (vista === 'lista') raiz.append(vistaLista(itens, sel));
  else raiz.append(vistaGrade(itens, sel));
  const total = ctx.ler('total');
  el('contagem').textContent = itens.length ? t('catalogo.contagem', { n: itens.length, total }) : '';
  const mais = el('carregar-mais');
  mais.hidden = !ctx.ler('cursor');
  mais.disabled = !!ctx.ler('carregando');
}

function cabecalhoOrdenavel(campo, chave) {
  const th = h('th', { scope: 'col', class: `c-${campo}` });
  if (!ORDENAVEIS.has(campo)) { th.textContent = t(chave); return th; }
  const [atual, dir] = (ctx.ler('ordenar') || '').split(':');
  th.dataset.campo = campo;
  th.tabIndex = 0;
  th.setAttribute('aria-sort', atual === campo ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
  th.textContent = t(chave);
  const alternar = () => {
    const nova = atual === campo && dir !== 'asc' ? 'asc' : 'desc';
    ctx.definir({ ordenar: `${campo}:${nova}` });
    document.dispatchEvent(new CustomEvent('catalogo:ordenar'));
  };
  th.addEventListener('click', alternar);
  th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); alternar(); } });
  return th;
}

function tabela(itens, sel) {
  const tab = h('table', { class: 'tabela' }, h('caption', { class: 'sr-only' }, t('catalogo.lista_itens')));
  const todos = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_todos') });
  todos.checked = itens.length > 0 && itens.every((i) => sel.has(i.id));
  todos.addEventListener('change', () => {
    if (todos.checked) { const ids = itens.slice(0, LIMITES.lote).map((i) => i.id); ctx.definir({ selecionados: ids }); if (itens.length > LIMITES.lote) el('lista-aviso').mostrar(t('catalogo.selecao_limite', { max: LIMITES.lote }), 'atencao'); } else limparSelecao();
  });
  const tr = h('tr', {}, h('th', { scope: 'col' }, todos), h('th', { scope: 'col', class: 'c-fav' }, h('span', { class: 'sr-only' }, t('catalogo.favorito'))), h('th', { scope: 'col', class: 'c-mini' }, h('span', { class: 'sr-only' }, t('catalogo.miniatura'))));
  for (const [campo, chave] of COLUNAS) tr.append(cabecalhoOrdenavel(campo, chave));
  tab.append(h('thead', {}, tr));
  const tb = h('tbody');
  for (const item of itens) {
    const trl = h('tr', { 'aria-selected': String(sel.has(item.id)) },
      h('td', {}, caixaSelecao(item)),
      h('td', { class: 'c-fav' }, botaoFavorito(item)),
      h('td', { class: 'c-mini' }, miniatura(item)),
      h('td', { class: 'c-titulo' }, tituloLink(item), selos(item)),
      h('td', { class: 'c-tipo' }, rotuloTipo(item.tipo)),
      h('td', { class: 'c-dono' }, nomeDono(item.dono)),
      h('td', { class: 'c-quando' }, h('time', { datetime: item.modificado_em || '' }, quando(item.modificado_em))),
      h('td', { class: 'c-acesso' }, rotuloAcesso(item)));
    ligarAbrir(trl, item);
    tb.append(trl);
  }
  tab.append(tb);
  return h('div', { class: 'tabela-rolagem' }, tab);
}

function vistaLista(itens, sel) {
  const ul = h('div', { class: 'vista-lista', role: 'list' });
  for (const item of itens) {
    const li = h('div', { class: 'linha-item', role: 'listitem', 'aria-selected': String(sel.has(item.id)) },
      caixaSelecao(item), miniatura(item),
      h('div', { class: 'corpo' }, h('div', {}, tituloLink(item), selos(item)), h('div', { class: 'resumo' }, elipse(item.resumo, 160) || t('catalogo.sem_resumo')),
        h('div', { class: 'meta' }, h('span', {}, rotuloTipo(item.tipo)), h('span', {}, nomeDono(item.dono)), h('span', {}, quando(item.modificado_em)), h('span', {}, rotuloAcesso(item)),
          ...(item.tags || []).slice(0, 5).map((tg) => h('span', { class: 'chip' }, h('span', { class: 'nome' }, tg))))),
      h('div', { class: 'lado' }, botaoFavorito(item)));
    ligarAbrir(li, item);
    ul.append(li);
  }
  return ul;
}

function vistaGrade(itens, sel) {
  const g = h('div', { class: 'vista-grade', role: 'list' });
  for (const item of itens) {
    const c = h('div', { class: 'cartao-item', role: 'listitem', 'aria-selected': String(sel.has(item.id)) },
      miniatura(item, 'grande'),
      h('div', { class: 'canto' }, caixaSelecao(item), iconeDoTipo(tipoDe(item.tipo), { tamanho: 14 })),
      h('div', { class: 'canto-dir' }, botaoFavorito(item)),
      h('div', { class: 'corpo' }, h('div', {}, tituloLink(item), selos(item)),
        h('div', { class: 'meta' }, h('span', {}, rotuloTipo(item.tipo)), h('span', {}, nomeDono(item.dono)), h('span', {}, quando(item.modificado_em)))));
    ligarAbrir(c, item);
    g.append(c);
  }
  return g;
}

/* navegação por teclado (j/k) entre as linhas da vista corrente */
export function moverFoco(delta) {
  const nos = [...el('lista').querySelectorAll('[data-id]')];
  if (!nos.length) return;
  foco = Math.max(0, Math.min(nos.length - 1, foco + delta));
  nos[foco].focus();
}
