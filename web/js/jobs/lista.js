/* plat · tarefas — lista de jobs do inquilino (ADR 0003 seção 10): filtros, ordenação por coluna, paginação de 50
   (<plat-paginacao> da base), progresso ao vivo por SSE nos jobs pendentes/rodando visíveis (polling da lista
   quando o limite de assinaturas estoura), resumo a cada 10 s (contador da barra lateral + releitura da 1ª página
   quando o número de ativos muda), cancelar/repetir por linha e CSV da página atual gerado no navegador.
   A tabela é própria (não <plat-tabela>) porque as linhas mudam uma a uma ao vivo e o cabeçalho ordena. */
import { confirmar } from '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { aoTraduzir, t } from '../base/i18n.js';
import * as api from './api.js';
import { INTERVALO_POLLING_MS, assinar, cancelarAssinatura } from './eventos.js';
import {
  FINAIS, csv, data, dataHora, duracao, duracaoJob, estado as fmtEstado, numero, quem, textoProgresso,
} from './formato.js';
import { aviso, baixar, opcoes, podeExecutar, porId } from './util.js';

export const LIMITE_PAGINA = 50;
export const INTERVALO_RESUMO_MS = 10000;
const PERIODOS = { '24h': 24 * 3600e3, '7d': 7 * 86400e3, '30d': 30 * 86400e3, tudo: null };
const ORDEM_PADRAO = { criado_em: 'desc', iniciado_em: 'desc', terminado_em: 'desc', estado: 'asc', tipo: 'asc' };

const s = {
  filtros: { estado: '', tipo: '', quem: 'eu', periodo: '7d' },
  deslocamento: 0,
  ordenar: 'criado_em:desc',
  itens: [],
  total: 0,
  usuario: null,
  aoAbrir: null,
  ativos: null,
  assinados: new Set(),
  timerPolling: null,
  timerResumo: null,
  timerRelogio: null,
  carregando: false,
  recarregarDepois: false,
  selecionado: null,
};

const admin = () => Boolean(s.usuario && s.usuario.perfil === 'admin');

function parametros() {
  const p = {
    limite: LIMITE_PAGINA, deslocamento: s.deslocamento, ordenar: s.ordenar,
    estado: s.filtros.estado, tipo: s.filtros.tipo,
  };
  if (admin() && s.filtros.quem === 'eu') p.usuario_id = s.usuario.id;
  const ms = PERIODOS[s.filtros.periodo];
  if (ms) p.de = new Date(Date.now() - ms).toISOString();
  return p;
}

function casaComFiltros(job) {
  if (s.filtros.estado && job.estado !== s.filtros.estado) return false;
  if (s.filtros.tipo && job.tipo !== s.filtros.tipo) return false;
  if (admin() && s.filtros.quem === 'eu' && job.usuario_id !== s.usuario.id) return false;
  const ms = PERIODOS[s.filtros.periodo];
  if (ms && job.criado_em && new Date(job.criado_em).getTime() < Date.now() - ms) return false;
  return true;
}

/* ---------- linha ---------- */

export function marcaEstado(nome) {
  const e = fmtEstado(nome);
  return h('span', { class: `estado-job ${e.classe}` }, h('span', { class: 'simbolo', 'aria-hidden': 'true' }, e.simbolo), ' ', e.rotulo);
}

function celulaProgresso(job) {
  const td = h('td', { class: 'c-progresso' });
  if (job.estado === 'rodando') {
    const pct = Math.max(0, Math.min(100, Number(job.progresso) || 0));
    td.append(
      h('div', { class: 'progresso', role: 'progressbar', 'aria-valuenow': String(pct), 'aria-valuemin': '0', 'aria-valuemax': '100' },
        h('div', { class: 'barra-progresso' }, h('div', { class: 'preenchido', style: `width:${pct}%` })),
        h('span', { class: 'valor' }, `${pct} %`)),
      h('span', { class: 'msg' }, (job.mensagem || '') + (job.cancelar_solicitado ? ` · ${t('tarefas.cancelando')}` : '')),
    );
    return td;
  }
  td.append(h('span', { class: job.estado === 'falhou' ? 'msg falha' : 'msg' }, textoProgresso(job)));
  if (job.estado === 'concluido' && job.resultado && job.resultado.item_id) {
    td.append(' ', h('a', { href: `/conteudo/${encodeURIComponent(job.resultado.item_id)}`, class: 'link-item' }, t('tarefas.ir_item')));
  }
  return td;
}

function botao(texto, classe, aoClicar, extra = {}) {
  return h('button', { type: 'button', class: `pequeno ${classe}`, onclick: (ev) => { ev.stopPropagation(); aoClicar(ev); }, ...extra }, texto);
}

async function cancelarJob(job, btn) {
  if (!(await confirmar(t('tarefas.cancelar_titulo'), t('tarefas.cancelar_texto', { tipo: job.tipo }), { ok: t('tarefas.cancelar_ok'), perigo: true }))) return;
  btn.disabled = true;
  btn.textContent = t('tarefas.cancelando');
  try {
    atualizarLinha(await api.cancelar(job.id));
    aviso('lista-aviso', '');
  } catch (e) {
    btn.disabled = false;
    btn.textContent = t('tarefas.cancelar');
    aviso('lista-aviso', t('tarefas.erro_cancelar', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

async function repetirJob(job) {
  try {
    const novo = await api.repetir(job.id);
    await carregar();
    if (s.aoAbrir) s.aoAbrir(novo.id);
  } catch (e) {
    aviso('lista-aviso', t('tarefas.erro_repetir', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

function celulaAcoes(job) {
  const caixa = h('div', { class: 'acoes-linha' });
  if (!podeExecutar()) {
    caixa.append(botao(t('tarefas.abrir'), 'texto acao-abrir', () => abrir(job.id)));
    return h('td', { class: 'c-acoes' }, caixa);
  }
  if (!FINAIS.has(job.estado)) {
    caixa.append(botao(job.cancelar_solicitado ? t('tarefas.cancelando') : t('tarefas.cancelar'), 'perigo acao-cancelar',
      (ev) => cancelarJob(job, ev.currentTarget), { disabled: Boolean(job.cancelar_solicitado) }));
  } else {
    caixa.append(botao(t('tarefas.repetir'), 'acao-repetir', () => repetirJob(job)));
  }
  caixa.append(botao(t('tarefas.abrir'), 'texto acao-abrir', () => abrir(job.id)));
  return h('td', { class: 'c-acoes' }, caixa);
}

function linha(job) {
  const tr = h('tr', { dataset: { id: job.id, estado: job.estado }, tabindex: '0', onclick: () => abrir(job.id) },
    h('td', { class: 'c-estado' }, marcaEstado(job.estado)),
    h('td', { class: 'c-tipo mono' }, job.tipo),
    h('td', { class: 'c-quem' }, quem(job)),
    h('td', { class: 'c-criado' }, h('time', { datetime: job.criado_em || '', title: dataHora(job.criado_em) }, data(job.criado_em))),
    h('td', { class: 'c-duracao num' }, duracao(duracaoJob(job))),
    celulaProgresso(job),
    celulaAcoes(job));
  tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(job.id); });
  if (s.selecionado === job.id) tr.setAttribute('aria-selected', 'true');
  return tr;
}

function abrir(id) {
  if (s.aoAbrir) s.aoAbrir(id);
}

/* substitui a linha existente ou insere no topo quando é job novo que cabe nos filtros (só na 1ª página) */
export function atualizarLinha(job) {
  if (!job || !job.id) return;
  const corpo = porId('lista-corpo');
  const tr = corpo.querySelector(`tr[data-id="${CSS.escape(job.id)}"]`);
  const i = s.itens.findIndex((j) => j.id === job.id);
  if (tr) {
    if (i >= 0) s.itens[i] = job;
    tr.replaceWith(linha(job));
  } else if (s.deslocamento === 0 && casaComFiltros(job)) {
    s.itens.unshift(job);
    s.total += 1;
    mostrarEstado(null);
    corpo.prepend(linha(job));
    renderizarPaginacao();
  }
  if (!FINAIS.has(job.estado)) assinaturas();
}

/* ---------- render ---------- */

function renderizarPaginacao() {
  porId('paginacao').atualizar({ total: s.total, limite: LIMITE_PAGINA, deslocamento: s.deslocamento });
  porId('lista-total').textContent = s.total === 1 ? t('tarefas.total_uma') : t('tarefas.total', { n: numero(s.total) });
}

/* estado explícito da lista (UX-05): null = tabela visível; 'vazio' | 'carregando' | erro (objeto) = <plat-estado> no lugar */
function mostrarEstado(tipo, extra) {
  const estado = document.getElementById('lista-estado');
  const caixa = document.getElementById('lista-caixa');
  if (!estado || !caixa) return;
  if (!tipo) { estado.limpar(); caixa.hidden = false; return; }
  caixa.hidden = true;
  if (tipo === 'carregando') estado.carregando(t('tarefas.carregando'));
  else if (tipo === 'vazio') {
    const filtrado = Boolean(s.filtros.estado || s.filtros.tipo || s.filtros.periodo !== 'tudo');
    estado.vazio(filtrado ? t('tarefas.vazio_filtros') : t('tarefas.vazio'), filtrado ? [{ id: 'limpar', rotulo: t('tarefas.limpar_filtros') }] : []);
  } else if (tipo === 'erro') estado.erro({ status: extra.status, json: { mensagem: extra.message, req_id: extra.reqId } });
}

function renderizar() {
  const corpo = limpar(porId('lista-corpo'));
  if (s.itens.length === 0) {
    mostrarEstado('vazio');
  } else {
    mostrarEstado(null);
    for (const job of s.itens) corpo.append(linha(job));
  }
  renderizarPaginacao();
  const [campo, dir] = s.ordenar.split(':');
  for (const th of document.querySelectorAll('#lista th[data-campo]')) {
    th.setAttribute('aria-sort', th.dataset.campo === campo ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
  }
  assinaturas();
}

/* ---------- carga, resumo e relógio ---------- */

export async function carregar() {
  if (s.carregando) {
    s.recarregarDepois = true;
    return;
  }
  s.carregando = true;
  porId('lista').setAttribute('aria-busy', 'true');
  if (!s.itens.length) mostrarEstado('carregando');
  try {
    const r = await api.listar(parametros());
    s.itens = Array.isArray(r.itens) ? r.itens : [];
    s.total = Number(r.total) || 0;
    renderizar();
    aviso('lista-aviso', '');
  } catch (e) {
    if (e.status !== 401) mostrarEstado('erro', e);
  } finally {
    porId('lista').setAttribute('aria-busy', 'false');
    s.carregando = false;
    if (s.recarregarDepois) {
      s.recarregarDepois = false;
      carregar();
    }
  }
}

export const recarregar = () => carregar();

function ouvinte(ev) {
  if ((ev.tipo === 'estado' || ev.tipo === 'fim') && ev.dados) atualizarLinha(ev.dados);
  if (ev.tipo === 'fim' || (ev.tipo === 'erro' && ev.dados && ev.dados.status === 404)) s.assinados.delete(ev.id);
}

function assinaturas() {
  const ativos = s.itens.filter((j) => !FINAIS.has(j.estado)).map((j) => j.id);
  for (const id of [...s.assinados]) {
    if (!ativos.includes(id)) {
      cancelarAssinatura(id, ouvinte);
      s.assinados.delete(id);
    }
  }
  let faltou = false;
  for (const id of ativos) {
    if (s.assinados.has(id)) continue;
    if (assinar(id, ouvinte)) s.assinados.add(id);
    else faltou = true;
  }
  if (faltou && !s.timerPolling) s.timerPolling = setInterval(carregar, INTERVALO_POLLING_MS);
  if (!faltou && s.timerPolling) {
    clearInterval(s.timerPolling);
    s.timerPolling = null;
  }
  porId('lista-modo').textContent = faltou
    ? t('tarefas.modo_polling', { n: s.assinados.size, s: INTERVALO_POLLING_MS / 1000 })
    : (s.assinados.size ? t('tarefas.modo_ao_vivo', { n: s.assinados.size }) : '');
}

export async function atualizarResumo() {
  try {
    const r = await api.resumo();
    const ativos = (Number(r.pendente) || 0) + (Number(r.rodando) || 0);
    const cont = document.getElementById('tarefas-ativas');
    if (cont) {
      cont.textContent = String(ativos);
      cont.hidden = ativos === 0;
    }
    porId('resumo-texto').textContent = t('tarefas.resumo', {
      pendente: numero(r.pendente), rodando: numero(r.rodando), concluido: numero(r.concluido_24h), falhou: numero(r.falhou_24h),
    });
    if (s.ativos !== null && s.ativos !== ativos && s.deslocamento === 0) carregar();
    s.ativos = ativos;
  } catch (e) {
    if (e.status !== 401) porId('resumo-texto').textContent = t('tarefas.resumo_indisponivel', { status: e.status || t('tarefas.rede') });
  }
}

function relogio() {
  const agora = Date.now();
  for (const tr of document.querySelectorAll('#lista-corpo tr[data-estado="rodando"]')) {
    const job = s.itens.find((j) => j.id === tr.dataset.id);
    const td = tr.querySelector('.c-duracao');
    if (job && td) td.textContent = duracao(duracaoJob(job, agora));
  }
}

/* ---------- filtros, ordenação, csv ---------- */

function lerFiltros() {
  s.filtros.estado = porId('f-estado').value;
  s.filtros.tipo = porId('f-tipo').value;
  s.filtros.periodo = porId('f-periodo').value;
  const quemSel = document.getElementById('f-quem');
  if (quemSel && !quemSel.closest('label').hidden) s.filtros.quem = quemSel.value;
  s.deslocamento = 0;
  carregar();
}

function ordenarPor(campo) {
  const [atual, dir] = s.ordenar.split(':');
  const nova = atual === campo ? (dir === 'asc' ? 'desc' : 'asc') : (ORDEM_PADRAO[campo] || 'asc');
  s.ordenar = `${campo}:${nova}`;
  s.deslocamento = 0;
  carregar();
}

function exportarCsv() {
  const cab = ['id', 'tipo', 'estado', 'quem', 'criado_em', 'iniciado_em', 'terminado_em', 'duracao_s', 'progresso', 'mensagem', 'erro'];
  const linhas = s.itens.map((j) => {
    const d = duracaoJob(j);
    return [j.id, j.tipo, j.estado, quem(j), j.criado_em, j.iniciado_em, j.terminado_em,
      d == null ? '' : Math.round(d * 10) / 10, j.progresso, j.mensagem, j.erro];
  });
  baixar('tarefas.csv', '﻿' + csv(cab, linhas), 'text/csv;charset=utf-8');
}

export function selecionar(id) {
  s.selecionado = id;
  for (const tr of document.querySelectorAll('#lista-corpo tr[data-id]')) {
    if (tr.dataset.id === id) tr.setAttribute('aria-selected', 'true');
    else tr.removeAttribute('aria-selected');
  }
}

export const filtros = () => ({ ...s.filtros });
export const itens = () => s.itens.slice();

export async function iniciar({ usuario = null, tipos = [], aoAbrir = null } = {}) {
  s.usuario = usuario;
  s.aoAbrir = aoAbrir;
  opcoes(porId('f-tipo'), tipos.map((t) => ({ valor: t.nome, texto: t.nome })));
  const quemSel = document.getElementById('f-quem');
  if (quemSel) {
    quemSel.closest('label').hidden = !admin();
    if (!admin()) s.filtros.quem = 'todos';
  }
  for (const id of ['f-estado', 'f-tipo', 'f-periodo', 'f-quem']) {
    const n = document.getElementById(id);
    if (n) n.addEventListener('change', lerFiltros);
  }
  const limparFiltros = () => {
    porId('f-estado').value = '';
    porId('f-tipo').value = '';
    porId('f-periodo').value = '7d';
    if (quemSel) quemSel.value = 'eu';
    lerFiltros();
  };
  porId('f-limpar').addEventListener('click', limparFiltros);
  const estadoLista = document.getElementById('lista-estado');
  if (estadoLista) estadoLista.addEventListener('acao', (ev) => { if (ev.detail.id === 'limpar') limparFiltros(); else if (ev.detail.id === 'tentar') carregar(); });
  // aoTraduzir roda já na inscrição: a primeira chamada é pulada (a carga inicial vem logo abaixo)
  let primeira = true;
  aoTraduzir(() => { if (primeira) { primeira = false; return; } renderizar(); atualizarResumo(); });
  for (const th of document.querySelectorAll('#lista th[data-campo]')) {
    th.addEventListener('click', () => ordenarPor(th.dataset.campo));
    th.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        ordenarPor(th.dataset.campo);
      }
    });
  }
  porId('paginacao').addEventListener('mudar', (ev) => {
    s.deslocamento = ev.detail.deslocamento;
    carregar();
  });
  porId('exportar-csv').addEventListener('click', exportarCsv);
  if (!s.timerResumo) s.timerResumo = setInterval(atualizarResumo, INTERVALO_RESUMO_MS);
  if (!s.timerRelogio) s.timerRelogio = setInterval(relogio, 1000);
  await Promise.all([carregar(), atualizarResumo()]);
}
