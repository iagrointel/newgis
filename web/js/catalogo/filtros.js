/* plat · catálogo — filtros laterais (facetas de GET /api/itens/facetas, ADR 0004 seção 7.5): tipo, dono, tags,
   status, acesso, categoria, datas, origem e bbox. Combinam com a busca; as contagens vêm do servidor sobre o mesmo
   WHERE. Só pede as facetas quando a gaveta está aberta. Chips dos filtros ativos com remoção individual. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';
import { ctx, parametrosLista, rotuloTipo, definirFiltro, alternarFiltro, limparFiltros, filtrosAtivos } from './contexto.js';
import { rotuloStatus } from './formato.js';

let seq = 0;
let aoMudar = () => {};
let facetas = {};
let mostrarTudo = new Set();
const el = (id) => document.getElementById(id);

export function iniciar({ mudou }) {
  aoMudar = mudou;
  ctx.assinar(() => render(), ['filtros', 'tipos']);
  el('coluna-filtros').addEventListener('toggle', () => { if (el('coluna-filtros').open) carregar(); });
}

/* chamada por quem recarrega a lista: refaz as contagens quando a gaveta está aberta */
export async function carregar() {
  if (!el('coluna-filtros').open) return;
  const meu = ++seq;
  const p = parametrosLista();
  delete p.limite;
  try {
    const r = await api.facetas(p);
    if (meu !== seq) return;
    facetas = r || {};
  } catch (e) {
    if (meu !== seq || e.status === 401) return;
    facetas = {};
  }
  render();
}

function rotuloDe(chave, v) {
  if (chave === 'tipo') return rotuloTipo(v.valor);
  if (chave === 'status') return rotuloStatus(v.valor);
  if (chave === 'acesso') return t(`catalogo.acesso_${v.valor}`);
  if (chave === 'familia') return t(`catalogo.familia_${v.valor}`) === `catalogo.familia_${v.valor}` ? v.valor : t(`catalogo.familia_${v.valor}`);
  return v.rotulo || v.caminho || v.login || v.nome || String(v.valor);
}

function faceta(chave, titulo, valores, { limite = 8 } = {}) {
  const f = ctx.ler('filtros');
  const marcados = new Set((f[chave] || []).map(String));
  const lista = Array.isArray(valores) ? valores.slice() : [];
  // valores marcados que não vieram nas contagens continuam visíveis (senão não dá para desmarcar)
  for (const m of marcados) if (!lista.some((v) => String(v.valor) === m)) lista.push({ valor: m, n: null });
  if (!lista.length) return null;
  const sec = h('section', { class: 'faceta', 'aria-label': titulo }, h('h3', {}, titulo));
  const tudo = mostrarTudo.has(chave);
  const visiveis = tudo ? lista : lista.slice(0, limite);
  for (const v of visiveis) {
    const cx = h('input', { type: 'checkbox', value: String(v.valor) });
    cx.checked = marcados.has(String(v.valor));
    cx.addEventListener('change', () => { alternarFiltro(chave, chave === 'dono_id' ? Number(v.valor) || v.valor : v.valor); aoMudar(); });
    sec.append(h('label', {}, cx, h('span', { class: 'rotulo', title: rotuloDe(chave, v) }, rotuloDe(chave, v)), v.n === null || v.n === undefined ? null : h('span', { class: 'n' }, String(v.n))));
  }
  if (lista.length > limite) {
    const b = h('button', { type: 'button', class: 'texto pequeno mais' }, tudo ? t('catalogo.menos') : t('catalogo.mais_n', { n: lista.length - limite }));
    b.addEventListener('click', () => { if (tudo) mostrarTudo.delete(chave); else mostrarTudo.add(chave); render(); });
    sec.append(b);
  }
  return sec;
}

function campoData(chave, rotulo) {
  const f = ctx.ler('filtros');
  const de = h('input', { type: 'date', 'aria-label': `${rotulo} ${t('catalogo.de')}`, value: f[`${chave}_de`] || '' });
  const ate = h('input', { type: 'date', 'aria-label': `${rotulo} ${t('catalogo.ate')}`, value: f[`${chave}_ate`] || '' });
  de.addEventListener('change', () => { definirFiltro(`${chave}_de`, de.value); aoMudar(); });
  ate.addEventListener('change', () => { definirFiltro(`${chave}_ate`, ate.value); aoMudar(); });
  return h('section', { class: 'faceta', 'aria-label': rotulo }, h('h3', {}, rotulo), h('div', { class: 'datas' }, h('label', {}, h('span', { class: 'rotulo' }, t('catalogo.de')), de), h('label', {}, h('span', { class: 'rotulo' }, t('catalogo.ate')), ate)));
}

function chipsAtivos() {
  const f = ctx.ler('filtros');
  const area = h('div', { class: 'filtros-ativos' });
  const chip = (texto, remover) => {
    const b = h('button', { type: 'button', class: 'texto pequeno', 'aria-label': t('catalogo.remover_filtro', { filtro: texto }) }, '×');
    b.addEventListener('click', () => { remover(); aoMudar(); });
    return h('span', { class: 'chip' }, h('span', { class: 'nome' }, texto), b);
  };
  for (const k of ['tipo', 'familia', 'status', 'acesso', 'tags', 'categoria', 'dono_id']) {
    for (const v of f[k] || []) {
      const conjunto = facetas[k === 'dono_id' ? 'dono' : k] || [];
      const achado = conjunto.find((x) => String(x.valor) === String(v));
      const texto = achado ? rotuloDe(k, achado) : (k === 'tipo' ? rotuloTipo(v) : k === 'status' ? rotuloStatus(v) : k === 'acesso' ? t(`catalogo.acesso_${v}`) : String(v));
      area.append(chip(texto, () => alternarFiltro(k, v)));
    }
  }
  for (const k of ['origem', 'criado_de', 'criado_ate', 'modificado_de', 'modificado_ate', 'bbox']) if (f[k]) area.append(chip(`${t(`catalogo.f_${k}`)}: ${f[k]}`, () => definirFiltro(k, '')));
  return area.childElementCount ? area : null;
}

function render() {
  const raiz = el('filtros');
  limpar(raiz);
  const ativos = filtrosAtivos();
  if (ativos) {
    const b = h('button', { type: 'button', class: 'pequeno', id: 'filtros-limpar' }, t('catalogo.limpar_filtros', { n: ativos }));
    b.addEventListener('click', () => { limparFiltros(); aoMudar(); });
    raiz.append(b, chipsAtivos());
  }
  const f = ctx.ler('filtros');
  const partes = [
    faceta('tipo', t('catalogo.col_tipo'), facetas.tipo || (ctx.ler('tipos') || []).map((x) => ({ valor: x.nome, n: null }))),
    faceta('dono_id', t('catalogo.col_dono'), facetas.dono),
    faceta('tags', t('catalogo.tags'), facetas.tags, { limite: 10 }),
    faceta('categoria', t('catalogo.categorias'), facetas.categoria),
    faceta('status', t('catalogo.status'), facetas.status || [{ valor: 'autoritativo', n: null }, { valor: 'obsoleto', n: null }]),
    ctx.ler('aba') === 'inquilino' ? null : faceta('acesso', t('catalogo.col_acesso'), facetas.acesso || ['privado', 'inquilino', 'publico'].map((v) => ({ valor: v, n: null }))),
    campoData('modificado', t('catalogo.col_modificado')),
    campoData('criado', t('catalogo.f_criado')),
  ];
  for (const p of partes) if (p) raiz.append(p);
  // origem
  const origem = h('select', { 'aria-label': t('catalogo.origem') }, h('option', { value: '' }, t('geral.todos')), h('option', { value: 'hospedado' }, t('catalogo.origem_hospedado')), h('option', { value: 'referenciado' }, t('catalogo.origem_referenciado')));
  origem.value = f.origem || '';
  origem.addEventListener('change', () => { definirFiltro('origem', origem.value); aoMudar(); });
  raiz.append(h('section', { class: 'faceta', 'aria-label': t('catalogo.origem') }, h('h3', {}, t('catalogo.origem')), origem));
  // bbox
  const bbox = h('input', { type: 'text', title: 'xmin, ymin, xmax, ymax', 'aria-label': t('catalogo.f_bbox'), value: f.bbox || '' });
  bbox.addEventListener('change', () => {
    const v = bbox.value.trim().split(/[,\s]+/).filter(Boolean);
    if (v.length && v.length !== 4) { bbox.setAttribute('aria-invalid', 'true'); return; }
    bbox.removeAttribute('aria-invalid');
    definirFiltro('bbox', v.join(',')); aoMudar();
  });
  raiz.append(h('section', { class: 'faceta', 'aria-label': t('catalogo.f_bbox') }, h('h3', {}, t('catalogo.f_bbox')), bbox, h('span', { class: 'ajuda' }, t('catalogo.f_bbox_ajuda'))));
}
