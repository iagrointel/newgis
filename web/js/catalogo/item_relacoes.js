/* plat · catálogo — aba Relações (ADR 0004 seção 5): "usado por" (profundidade 2) e "criado a partir de", cada
   entrada abre o item; entradas ocultas (sem acesso) aparecem como tal. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';
import { rotuloTipo } from './contexto.js';
import { elipse } from './formato.js';

function rotuloRelacao(tipo) { const k = `catalogo.rel_${tipo}`; const s = t(k); return s === k ? (tipo || '') : s; }

function lista(entradas, { abrir }) {
  const ul = h('ul', { class: 'lista-relacoes' });
  if (!entradas.length) { ul.append(h('li', { class: 'oculto' }, t('catalogo.sem_relacoes'))); return ul; }
  for (const e of entradas) {
    if (e.oculto) { ul.append(h('li', { class: 'oculto' }, t('catalogo.item_oculto'))); continue; }
    const it = e.item || e;
    const a = h('a', { href: `/conteudo/${it.id}`, class: 'titulo-item' }, elipse(it.titulo, 80));
    a.addEventListener('click', (ev) => { ev.preventDefault(); abrir(it.id); });
    ul.append(h('li', {}, a, h('span', { class: 'fraco' }, rotuloTipo(it.tipo)), e.tipo_relacao ? h('span', { class: 'marcador info' }, rotuloRelacao(e.tipo_relacao)) : null, e.profundidade ? h('span', { class: 'prof' }, t('catalogo.profundidade', { n: e.profundidade })) : null));
  }
  return ul;
}

export function montar(item, { abrir }) {
  const raiz = h('div', { class: 'relacoes' });
  const usado = h('div', {}, h('p', { class: 'fraco' }, t('catalogo.carregando')));
  const origem = h('div', {}, h('p', { class: 'fraco' }, t('catalogo.carregando')));
  raiz.append(h('h3', {}, t('catalogo.usado_por'), ' ', h('span', { class: 'contagem' }, `(${item.usado_por ?? 0})`)), usado,
    h('h3', {}, t('catalogo.criado_a_partir_de'), ' ', h('span', { class: 'contagem' }, `(${item.criado_a_partir_de ?? 0})`)), origem);
  api.usadoPor(item.id, 2).then((r) => { limpar(usado); usado.append(lista(Array.isArray(r) ? r : (r.itens || []), { abrir })); }).catch((e) => { limpar(usado); usado.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, e.message)); });
  api.criadoAPartirDe(item.id).then((r) => { limpar(origem); origem.append(lista(Array.isArray(r) ? r : (r.itens || []), { abrir })); }).catch((e) => { limpar(origem); origem.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, e.message)); });
  return raiz;
}
