/* plat · tarefas — progresso em tempo real (ADR 0003 seção 5): EventSource em /api/jobs/{id}/eventos com
   reserva por polling. Uma assinatura por job, vários ouvintes (lista e detalhe partilham a mesma conexão).
   Depois de 2 erros seguidos do EventSource (ou conexão recusada de vez: 404/429) cai para polling de 3 s em
   obter(id) + log(id, apos); a próxima abertura tenta o SSE de novo. Limite de 10 assinaturas por página:
   acima disso assinar() devolve false e a lista faz polling da própria lista.
   Eventos entregues ao ouvinte: {tipo: 'estado'|'log'|'fim'|'modo'|'erro', id, dados}. */
import { log as lerLog, obter } from './api.js';
import { FINAIS } from './formato.js';

export const LIMITE = 10;
export const INTERVALO_POLLING_MS = 3000;
const assinaturas = new Map();

function json(texto) {
  try {
    return JSON.parse(texto);
  } catch {
    return null;
  }
}

function emitir(a, evento) {
  for (const o of [...a.ouvintes]) {
    try {
      o(evento);
    } catch (e) {
      console.warn('ouvinte de eventos falhou', e);
    }
  }
}

function tratar(a, tipo, dados) {
  if (!assinaturas.has(a.id)) return;
  if (tipo === 'log' && dados && dados.id != null) a.apos = Math.max(a.apos, Number(dados.id) || 0);
  emitir(a, { tipo, id: a.id, dados });
  if (tipo === 'fim') encerrar(a);
}

function abrirSse(a) {
  a.modo = 'sse';
  const es = new EventSource(`/api/jobs/${encodeURIComponent(a.id)}/eventos`);
  a.es = es;
  es.addEventListener('open', () => {
    a.erros = 0;
    emitir(a, { tipo: 'modo', id: a.id, dados: { modo: 'sse' } });
  });
  es.addEventListener('estado', (e) => tratar(a, 'estado', json(e.data)));
  es.addEventListener('log', (e) => tratar(a, 'log', json(e.data)));
  es.addEventListener('fim', (e) => {
    const job = json(e.data);
    if (job) tratar(a, 'estado', job);
    tratar(a, 'fim', job);
  });
  es.addEventListener('error', () => {
    a.erros += 1;
    // CLOSED = o navegador desistiu (resposta não-200 ou tipo errado); não haverá reconexão automática
    if (a.erros >= 2 || es.readyState === EventSource.CLOSED) {
      es.close();
      a.es = null;
      abrirPolling(a);
    }
  });
}

function abrirPolling(a) {
  if (a.modo === 'polling') return;
  a.modo = 'polling';
  emitir(a, { tipo: 'modo', id: a.id, dados: { modo: 'polling' } });
  const passo = async () => {
    if (a.consultando || !assinaturas.has(a.id)) return;
    a.consultando = true;
    try {
      const job = await obter(a.id);
      const r = await lerLog(a.id, a.apos, 500);
      tratar(a, 'estado', job);
      for (const linha of (r && r.linhas) || []) tratar(a, 'log', linha);
      if (FINAIS.has(job.estado)) tratar(a, 'fim', job);
    } catch (e) {
      emitir(a, { tipo: 'erro', id: a.id, dados: e });
      if (e && e.status === 404) encerrar(a);
    } finally {
      a.consultando = false;
    }
  };
  a.timer = setInterval(passo, INTERVALO_POLLING_MS);
  passo();
}

function encerrar(a) {
  if (a.es) a.es.close();
  if (a.timer) clearInterval(a.timer);
  a.es = null;
  a.timer = null;
  assinaturas.delete(a.id);
}

/* devolve true se o job está assinado (nova ou existente); false quando o limite foi atingido */
export function assinar(id, ouvinte) {
  let a = assinaturas.get(id);
  if (a) {
    a.ouvintes.add(ouvinte);
    return true;
  }
  if (assinaturas.size >= LIMITE) return false;
  a = { id, ouvintes: new Set([ouvinte]), es: null, timer: null, erros: 0, apos: 0, modo: 'sse', consultando: false };
  assinaturas.set(id, a);
  abrirSse(a);
  return true;
}

/* remove um ouvinte; sem ouvinte fecha a assinatura inteira */
export function cancelarAssinatura(id, ouvinte) {
  const a = assinaturas.get(id);
  if (!a) return;
  if (ouvinte) {
    a.ouvintes.delete(ouvinte);
    if (a.ouvintes.size > 0) return;
  }
  encerrar(a);
}

export function cancelarTodas() {
  for (const a of [...assinaturas.values()]) encerrar(a);
}

export const assinado = (id) => assinaturas.has(id);
export const modo = (id) => (assinaturas.get(id) || {}).modo || null;
export const total = () => assinaturas.size;
