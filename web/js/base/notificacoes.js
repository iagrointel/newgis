/* plat — sino de notificações na barra lateral (item L0-03-k). Uma consulta só para o número
   (GET /api/notificacoes/contagem, índice parcial no banco) e a lista sob demanda, ao abrir o painel.
   Sem sessão ou com a API fora do ar o sino simplesmente não aparece: nenhuma tela quebra por causa dele. */
import { h, limpar } from './dom.js';
import { t } from './i18n.js';
import { chamar } from './api.js';

const RECARGA_MS = 60000;
let temporizador = null;

async function pedir(metodo, url, corpo) {
  const r = await chamar(metodo, url, corpo);
  return r.status >= 200 && r.status < 300 ? r.json : null;
}

function linha(n, aoMarcar) {
  const quando = n.criado_em ? n.criado_em.replace('T', ' ').replace('Z', '') : '';
  const corpo = h('div', { class: 'notificacao-texto' },
    h('strong', {}, n.titulo || ''),
    n.corpo ? h('span', {}, n.corpo) : null,
    h('small', {}, quando));
  const item = h('li', { class: n.lida_em ? 'lida' : 'nao-lida', 'data-id': n.id },
    n.url ? h('a', { href: n.url }, corpo) : corpo);
  if (!n.lida_em) {
    const bt = h('button', { type: 'button', class: 'pequeno', 'aria-label': t('notificacao.marcar_lida') }, '✓');
    bt.addEventListener('click', async () => { await aoMarcar([n.id]); });
    item.append(bt);
  }
  return item;
}

export function montarSino(aside) {
  const contador = h('span', { class: 'sino-contagem', id: 'sino-contagem', hidden: true }, '0');
  const botao = h('button', { type: 'button', class: 'sino', id: 'sino', 'aria-expanded': 'false',
    'aria-controls': 'sino-painel', 'aria-label': t('notificacao.sino') }, h('span', { 'aria-hidden': 'true' }, '🔔'), contador);
  const lista = h('ul', { class: 'notificacoes' });
  const marcarTodas = h('button', { type: 'button', class: 'pequeno', id: 'sino-todas' }, t('notificacao.marcar_todas'));
  const painel = h('div', { class: 'sino-painel', id: 'sino-painel', hidden: true },
    h('div', { class: 'sino-topo' }, h('strong', {}, t('notificacao.titulo')), marcarTodas), lista);

  async function atualizarContagem() {
    const j = await pedir('GET', '/api/notificacoes/contagem');
    if (!j) return;
    const n = Number(j.nao_lidas) || 0;
    contador.textContent = String(n);
    contador.hidden = n === 0;
    botao.setAttribute('data-nao-lidas', String(n));
  }

  async function marcar(ids) {
    await pedir('POST', '/api/notificacoes/lidas', ids ? { ids } : { todas: true });
    await Promise.all([atualizarContagem(), carregarLista()]);
  }

  async function carregarLista() {
    const j = await pedir('GET', '/api/notificacoes?limite=20');
    limpar(lista);
    const itens = (j && j.itens) || [];
    if (!itens.length) { lista.append(h('li', { class: 'vazia' }, t('notificacao.vazio'))); return; }
    for (const n of itens) lista.append(linha(n, marcar));
  }

  botao.addEventListener('click', async () => {
    const abrir = painel.hidden;
    painel.hidden = !abrir;
    botao.setAttribute('aria-expanded', String(abrir));
    if (abrir) await carregarLista();
  });
  marcarTodas.addEventListener('click', () => marcar(null));
  document.addEventListener('click', (e) => {
    if (painel.hidden || botao.contains(e.target) || painel.contains(e.target)) return;
    painel.hidden = true;
    botao.setAttribute('aria-expanded', 'false');
  });

  aside.append(h('div', { class: 'sino-area' }, botao, painel));
  atualizarContagem();
  if (temporizador) clearInterval(temporizador);
  temporizador = setInterval(atualizarContagem, RECARGA_MS);
  return { atualizarContagem };
}
