/* plat · tarefas — painel de detalhe de um job (ADR 0003 seção 10): abre por clique ou por /tarefas/<id>;
   assina o SSE do job (com reserva por polling); anexa linhas de log conforme chegam; filtro por nível; baixar
   log (GET /api/jobs/{id}/log?limite=2000 em texto); blocos de parâmetros, resultado (link para o item quando
   resultado.item_id existe) e proveniência; cancelar e repetir. */
import { confirmar } from '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { formatarJSON } from '../core.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';
import { assinar, cancelarAssinatura } from './eventos.js';
import {
  FINAIS, NIVEIS, dataHora, duracao, duracaoJob, estado as fmtEstado, hora, linhasLog, numero,
} from './formato.js';
import { aviso, baixar, podeExecutar, porId } from './util.js';

const s = {
  id: null,
  job: null,
  linhas: [],
  ids: new Set(),
  totalLog: 0,
  nivelMin: 'INFO',
  modo: null,
  aoAbrir: null,
  aoFechar: null,
  aoNovoJob: null,
  timerRelogio: null,
};

const sec = () => porId('detalhe');
const nivelVisivel = (nivel) => NIVEIS.indexOf(nivel) >= NIVEIS.indexOf(s.nivelMin);

/* ---------- render ---------- */

function proveniencia(p) {
  if (!p || typeof p !== 'object') return '—';
  const partes = [];
  const restante = { ...p };
  const pegar = (chave, rotulo) => {
    if (restante[chave] === undefined) return;
    partes.push(`${rotulo}: ${typeof restante[chave] === 'object' ? JSON.stringify(restante[chave]) : restante[chave]}`);
    delete restante[chave];
  };
  pegar('git_sha', 'git');
  pegar('versao', t('tarefas.prov_versao'));
  pegar('tipo_versao', t('tarefas.prov_versao_tipo'));
  pegar('gdal', 'gdal');
  pegar('repetido_de', t('tarefas.prov_repetido_de'));
  if (Array.isArray(restante.entradas)) {
    for (const e of restante.entradas) {
      partes.push(`${t('tarefas.prov_entrada')}: ${e.nome || e.caminho || '?'}${e.sha256 ? ` sha256 ${String(e.sha256).slice(0, 12)}…` : ''}`
        + `${e.bytes != null ? ` ${numero(e.bytes)} bytes` : ''}`);
    }
    delete restante.entradas;
  }
  if (Object.keys(restante).length) partes.push(formatarJSON(restante));
  return partes.join('\n');
}

function renderizarCabecalho() {
  const job = s.job;
  if (!job) return;
  const e = fmtEstado(job.estado);
  porId('detalhe-tipo').textContent = job.tipo || '—';
  const marc = porId('detalhe-estado');
  marc.className = `estado-job ${e.classe}`;
  limpar(marc).append(h('span', { class: 'simbolo', 'aria-hidden': 'true' }, e.simbolo), ' ', e.rotulo);
  const partes = [`${job.progresso ?? 0} %`, t('tarefas.tentativa', { n: job.tentativa ?? 0, max: job.max_tentativas ?? '—' })];
  if (job.reinicios) partes.push(job.reinicios === 1 ? t('tarefas.reinicio_um') : t('tarefas.reinicios', { n: job.reinicios }));
  partes.push(`worker ${job.worker || '—'}`, t('tarefas.det_criado', { quando: dataHora(job.criado_em) }));
  if (job.iniciado_em) partes.push(t('tarefas.det_iniciado', { quando: hora(job.iniciado_em) }));
  partes.push(duracao(duracaoJob(job)));
  porId('detalhe-resumo').textContent = partes.join(' · ');
  porId('detalhe-mensagem').textContent = job.mensagem || '';
  const erro = porId('detalhe-erro');
  erro.textContent = job.erro ? t('tarefas.det_erro', { erro: job.erro }) : '';
  erro.hidden = !job.erro;
  porId('detalhe-id').textContent = job.id;

  const final = FINAIS.has(job.estado);
  const btnCancelar = porId('detalhe-cancelar');
  btnCancelar.hidden = final || !podeExecutar();
  btnCancelar.disabled = Boolean(job.cancelar_solicitado);
  btnCancelar.textContent = job.cancelar_solicitado ? t('tarefas.cancelando') : t('tarefas.cancelar');
  porId('detalhe-repetir').hidden = !final || !podeExecutar();
  porId('detalhe-baixar-log').disabled = !(job.linhas_log > 0 || s.linhas.length > 0);

  porId('detalhe-parametros').textContent = job.parametros ? formatarJSON(job.parametros) : '—';
  porId('detalhe-resultado').textContent = job.resultado ? formatarJSON(job.resultado) : (final ? '—' : t('tarefas.sem_resultado'));
  const link = porId('detalhe-item');
  const itemId = job.resultado && job.resultado.item_id;
  link.hidden = !itemId;
  if (itemId) link.href = `/conteudo/${encodeURIComponent(itemId)}`;
  porId('detalhe-proveniencia').textContent = proveniencia(job.proveniencia);
  porId('log-contagem').textContent = linhasLog(Math.max(Number(job.linhas_log) || 0, s.linhas.length));
}

function itemLog(l) {
  return h('li', { class: `n-${l.nivel}`, hidden: !nivelVisivel(l.nivel), dataset: { id: String(l.id) } },
    h('time', { datetime: l.em || '', title: dataHora(l.em) }, hora(l.em)),
    h('b', {}, l.nivel),
    h('span', {}, l.mensagem));
}

const pertoDoFim = (n) => n.scrollHeight - n.scrollTop - n.clientHeight < 40;

function renderizarLog() {
  const ol = limpar(porId('log-linhas'));
  for (const l of s.linhas) ol.append(itemLog(l));
  porId('log-nota').textContent = s.totalLog > s.linhas.length && s.job && FINAIS.has(s.job.estado)
    ? t('tarefas.log_nota', { n: numero(s.linhas.length), total: numero(s.totalLog) })
    : '';
  ol.scrollTop = ol.scrollHeight;
}

function acrescentarLinhas(linhas, aoVivo = false) {
  const ol = porId('log-linhas');
  const rolar = !aoVivo || pertoDoFim(ol);
  let novas = 0;
  for (const l of linhas || []) {
    if (!l || l.id == null || s.ids.has(l.id)) continue;
    s.ids.add(l.id);
    s.linhas.push(l);
    novas += 1;
    if (aoVivo) ol.append(itemLog(l));
  }
  if (!aoVivo) renderizarLog();
  else if (rolar) ol.scrollTop = ol.scrollHeight;
  if (novas && s.job) porId('log-contagem').textContent = linhasLog(Math.max(Number(s.job.linhas_log) || 0, s.linhas.length));
  porId('detalhe-baixar-log').disabled = s.linhas.length === 0 && !(s.job && s.job.linhas_log > 0);
}

function mostrarModo(modo) {
  s.modo = modo;
  const n = porId('detalhe-modo');
  n.hidden = !modo;
  n.textContent = modo === 'sse' ? t('tarefas.modo_sse') : (modo ? t('tarefas.modo_polling_detalhe') : '');
  n.className = `marcador ${modo === 'sse' ? 'ok' : 'atencao'}`;
}

/* ---------- eventos do job ---------- */

function ouvinte(ev) {
  if (ev.id !== s.id) return;
  if (ev.tipo === 'estado' && ev.dados) {
    s.job = ev.dados;
    renderizarCabecalho();
  } else if (ev.tipo === 'log' && ev.dados) {
    acrescentarLinhas([ev.dados], true);
  } else if (ev.tipo === 'fim') {
    if (ev.dados) s.job = ev.dados;
    renderizarCabecalho();
    mostrarModo(null);
  } else if (ev.tipo === 'modo' && ev.dados) {
    mostrarModo(ev.dados.modo);
  } else if (ev.tipo === 'erro' && ev.dados) {
    aviso('detalhe-aviso', t('tarefas.atualizacao_interrompida', { status: ev.dados.status || t('tarefas.rede'), erro: ev.dados.message }), 'atencao');
  }
}

/* ---------- ações ---------- */

async function cancelar() {
  if (!s.job || !(await confirmar(t('tarefas.cancelar_titulo'), t('tarefas.cancelar_texto', { tipo: s.job.tipo }), { ok: t('tarefas.cancelar_ok'), perigo: true }))) return;
  const btn = porId('detalhe-cancelar');
  btn.disabled = true;
  btn.textContent = t('tarefas.cancelando');
  try {
    s.job = await api.cancelar(s.id);
    renderizarCabecalho();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = t('tarefas.cancelar');
    aviso('detalhe-aviso', t('tarefas.erro_cancelar', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

async function repetir() {
  if (!s.job) return;
  try {
    const novo = await api.repetir(s.id);
    if (s.aoNovoJob) s.aoNovoJob(novo);
    await abrir(novo.id);
  } catch (e) {
    aviso('detalhe-aviso', t('tarefas.erro_repetir', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

async function baixarLog() {
  if (!s.id) return;
  try {
    const r = await api.log(s.id, 0, 2000);
    const texto = (r.linhas || []).map((l) => `${dataHora(l.em)} ${String(l.nivel).padEnd(5)} ${l.mensagem}`).join('\n') + '\n';
    baixar(`tarefa-${s.id}.log`, texto);
  } catch (e) {
    aviso('detalhe-aviso', t('tarefas.erro_baixar_log', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

function mudarNivel() {
  s.nivelMin = porId('log-nivel').value;
  for (const li of document.querySelectorAll('#log-linhas li')) li.hidden = !nivelVisivel(li.className.replace('n-', ''));
}

/* ---------- abrir / fechar ---------- */

export async function abrir(id, { empurrarUrl = true } = {}) {
  if (!id) return;
  if (s.id && s.id !== id) cancelarAssinatura(s.id, ouvinte);
  s.id = id;
  s.job = null;
  s.linhas = [];
  s.ids = new Set();
  s.totalLog = 0;
  limpar(porId('log-linhas'));
  aviso('detalhe-aviso', '');
  mostrarModo(null);
  const estadoArea = document.getElementById('detalhe-estado-area');
  if (estadoArea) estadoArea.carregando(t('tarefas.carregando_tarefa'));
  sec().hidden = false;
  document.body.dataset.detalhe = '1';
  if (empurrarUrl && location.pathname !== `/tarefas/${id}`) history.pushState({ id }, '', `/tarefas/${id}`);
  if (s.aoAbrir) s.aoAbrir(id);
  try {
    const job = await api.obter(id);
    if (s.id !== id) return;
    s.job = job;
    renderizarCabecalho();
    // assina antes de ler o log: linha que chegar entre a leitura e a conexão é deduplicada pelo id
    if (!FINAIS.has(job.estado)) assinar(id, ouvinte);
    const r = await api.log(id, 0, 500);
    if (s.id !== id) return;
    s.totalLog = Number(r.total) || 0;
    acrescentarLinhas(r.linhas);
    if (estadoArea) estadoArea.limpar();
    sec().dataset.carregado = '1';
  } catch (e) {
    const estado = document.getElementById('detalhe-estado-area');
    if (estado) {
      if (e.status === 404) estado.mostrar({ tipo: 'vazio', titulo: t('tarefas.nao_encontrada_titulo'), texto: t('tarefas.nao_encontrada'), acoes: [{ id: 'fechar', rotulo: t('tarefas.fechar') }] });
      else estado.erro({ status: e.status, json: { mensagem: e.message, req_id: e.reqId } });
    } else {
      aviso('detalhe-aviso', e.status === 404 ? t('tarefas.nao_encontrada') : t('tarefas.erro_carregar_tarefa', { status: e.status || t('tarefas.rede'), erro: e.message }));
    }
    sec().dataset.carregado = '0';
  }
  sec().scrollIntoView({ block: 'nearest' });
}

export function fechar({ empurrarUrl = true } = {}) {
  if (s.id) cancelarAssinatura(s.id, ouvinte);
  s.id = null;
  s.job = null;
  sec().hidden = true;
  delete document.body.dataset.detalhe;
  delete sec().dataset.carregado;
  if (empurrarUrl && location.pathname !== '/tarefas') history.pushState({}, '', '/tarefas');
  if (s.aoFechar) s.aoFechar();
}

export const idAberto = () => s.id;

function relogio() {
  if (s.job && s.job.estado === 'rodando') renderizarCabecalho();
}

export function iniciar({ aoAbrir = null, aoFechar = null, aoNovoJob = null } = {}) {
  s.aoAbrir = aoAbrir;
  s.aoFechar = aoFechar;
  s.aoNovoJob = aoNovoJob;
  porId('detalhe-fechar').addEventListener('click', () => fechar());
  const estadoArea = document.getElementById('detalhe-estado-area');
  if (estadoArea) estadoArea.addEventListener('acao', (ev) => { if (ev.detail.id === 'fechar') fechar(); else if (ev.detail.id === 'tentar' && s.id) abrir(s.id, { empurrarUrl: false }); });
  porId('detalhe-cancelar').addEventListener('click', cancelar);
  porId('detalhe-repetir').addEventListener('click', repetir);
  porId('detalhe-baixar-log').addEventListener('click', baixarLog);
  const nivel = porId('log-nivel');
  nivel.value = s.nivelMin;
  nivel.addEventListener('change', mudarNivel);
  if (!s.timerRelogio) s.timerRelogio = setInterval(relogio, 1000);
}
