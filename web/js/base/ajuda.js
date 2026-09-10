/* plat — ajuda por contexto (item L7-04-a-manual-capturas-geradas).
   Toda tela declara data-ajuda="<chave>" no body; a chave é uma seção do manual gerado
   (docs/manual/<tela>.md -> web/dados/manual.json). O botão Ajuda da barra lateral abre o painel
   com a seção da tela; a busca filtra por título, palavras-chave, resumo e corpo, no idioma ativo.
   HTML inserido passa por htmlSeguro (DOMPurify), a única porta da casa. */

import { h, htmlSeguro } from './dom.js';
import { t, carregar, idiomaAtual } from './i18n.js';

let secoes = [];
let aberto = false;
let carregando = null;

const IDIOMAS = [
  { valor: 'pt-BR', rotulo: 'Português' },
  { valor: 'en', rotulo: 'English' },
  { valor: 'es', rotulo: 'Español' },
];

/* minúsculas sem diacríticos: a busca não distingue "configuration" de "Configuração" */
export function normalizar(texto) {
  return String(texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function campoIdioma(secao, campo, idioma) {
  if (idioma === 'en') return secao[`${campo}_en`] ?? secao[campo];
  if (idioma === 'es') return secao[`${campo}_es`] ?? secao[campo];
  return secao[campo];
}

/* busca das seções: todos os termos têm de aparecer (E lógico); pontuação título > palavras > resumo > corpo.
   Exposta em window.platAjuda.buscar para os testes de ponta a ponta medirem o mesmo caminho da interface. */
export function buscar(consulta, idioma = idiomaAtual()) {
  const termos = normalizar(consulta).split(/\s+/).filter(Boolean);
  if (!termos.length) return secoes.map((s) => ({ secao: s, pontos: 0 }));
  const resultados = [];
  for (const s of secoes) {
    const titulo = normalizar(campoIdioma(s, 'titulo', idioma));
    const palavras = normalizar((campoIdioma(s, 'palavras', idioma) || []).join(' '));
    const resumo = normalizar(campoIdioma(s, 'resumo', idioma));
    const corpo = normalizar(s.corpo ? String(s.corpo).replace(/<[^>]+>/g, ' ') : '');
    let soma = 0;
    let falta = false;
    for (const termo of termos) {
      let pontos = 0;
      if (titulo.includes(termo)) pontos += 4;
      if (palavras.includes(termo)) pontos += 3;
      if (resumo.includes(termo)) pontos += 2;
      if (corpo.includes(termo)) pontos += 1;
      if (pontos === 0) { falta = true; break; }
      soma += pontos;
    }
    if (!falta) resultados.push({ secao: s, pontos: soma });
  }
  resultados.sort((a, b) => b.pontos - a.pontos || a.secao.titulo.localeCompare(b.secao.titulo));
  return resultados;
}

async function garantirSecoes() {
  if (secoes.length) return;
  if (carregando) return carregando;
  carregando = fetch('/static/dados/manual.json', { cache: 'no-store', credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : { secoes: [] }))
    .then((dados) => { secoes = dados.secoes || []; })
    .catch(() => { secoes = []; });
  return carregando;
}

function raiz() {
  return document.getElementById('painel-ajuda');
}

function trocarIdioma(valor) {
  try { localStorage.setItem('plat.idioma', valor); } catch { /* armazenamento bloqueado: segue com o atual */ }
  carregar(valor).then(() => {
    if (aberto) desenhar(document.body.dataset.ajuda || '', '');
  });
}

function desenhar(chaveAtual, consulta) {
  const painel = raiz();
  if (!painel) return;
  const idioma = idiomaAtual();
  painel.replaceChildren();
  const topo = h('div', { class: 'ajuda-topo' },
    h('strong', {}, t('ajuda.titulo')),
    h('select', { id: 'ajuda-idioma', 'aria-label': t('ajuda.idioma') },
      ...IDIOMAS.map((i) => h('option', { value: i.valor }, i.rotulo))),
    h('button', { type: 'button', class: 'pequeno', id: 'ajuda-fechar', 'aria-label': t('ajuda.fechar') }, '×'));
  topo.querySelector('select').value = idioma;
  topo.querySelector('select').addEventListener('change', (e) => trocarIdioma(e.target.value));
  topo.querySelector('button').addEventListener('click', fechar);
  const campo = h('input', {
    type: 'search', id: 'ajuda-busca',
    'aria-label': t('ajuda.busca'), value: consulta || '',
  });
  const lista = h('div', { class: 'ajuda-lista', id: 'ajuda-lista' });
  const conteudo = h('div', { class: 'ajuda-conteudo', id: 'ajuda-conteudo' });
  const link = h('a', { href: '/manual', target: '_blank', rel: 'noopener' }, t('ajuda.abrir_manual'));
  painel.append(topo, campo, lista, h('hr'), conteudo, h('p', { class: 'ajuda-manual' }, link));

  const mostrarConteudo = (secao) => {
    conteudo.replaceChildren(
      h('h3', {}, campoIdioma(secao, 'titulo', idioma)),
      h('p', { class: 'fraco' }, secao.caminho || ''),
      htmlSeguro(campoCorpo(secao, idioma)),
    );
  };

  const resultados = consulta ? buscar(consulta, idioma) : [];
  if (consulta && !resultados.length) {
    lista.append(h('p', { class: 'fraco' }, t('ajuda.sem_resultado')));
  } else {
    const base = consulta
      ? resultados
      : resultados.length ? resultados : secoes.map((s) => ({ secao: s, pontos: 0 }));
    const ordem = [...base].sort((a, b) => (b.secao.id === chaveAtual) - (a.secao.id === chaveAtual));
    for (const { secao } of ordem) {
      const b = h('button', { type: 'button', class: 'ajuda-item' },
        campoIdioma(secao, 'titulo', idioma), h('small', {}, campoIdioma(secao, 'resumo', idioma)));
      if (secao.id === chaveAtual) b.classList.add('atual');
      b.addEventListener('click', () => mostrarConteudo(secao));
      lista.append(b);
    }
  }
  const daTela = secoes.find((s) => s.id === chaveAtual);
  mostrarConteudo(daTela || (resultados.length ? resultados[0].secao : secoes[0]));
  campo.addEventListener('input', () => {
    desenhar(document.body.dataset.ajuda || '', campo.value);
    const deNovo = document.getElementById('ajuda-busca');
    deNovo.focus();
    deNovo.setSelectionRange(deNovo.value.length, deNovo.value.length);
  });
}

/* corpo em pt-BR sempre existe; en/es mostram o resumo traduzido e apontam o manual completo */
function campoCorpo(secao, idioma) {
  if (idioma === 'pt-BR' || !idioma) return secao.corpo || '';
  const resumo = campoIdioma(secao, 'resumo', idioma);
  return `<p>${String(resumo).replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p><p class="fraco">${t('ajuda.corpo_idioma')}</p>${secao.corpo || ''}`;
}

export function fechar() {
  aberto = false;
  const painel = raiz();
  if (painel) painel.hidden = true;
}

export async function abrir() {
  await garantirSecoes();
  const painel = raiz();
  if (!painel) return;
  aberto = true;
  painel.hidden = false;
  desenhar(document.body.dataset.ajuda || '', '');
  const campo = document.getElementById('ajuda-busca');
  if (campo) campo.focus();
}

/* botão da barra lateral + painel raiz; chamado por montarLayout (todas as telas com sessão) */
export function instalarAjuda(aside) {
  let painel = raiz();
  if (!painel) {
    painel = h('aside', { id: 'painel-ajuda', class: 'painel-ajuda', 'aria-label': t('ajuda.titulo') });
    painel.hidden = true;
    document.body.append(painel);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && aberto) fechar(); });
  }
  if (!aside || document.getElementById('botao-ajuda')) return;
  const botao = h('button', { type: 'button', class: 'pequeno', id: 'botao-ajuda' }, t('ajuda.titulo'));
  botao.addEventListener('click', () => (aberto ? fechar() : abrir()));
  aside.append(botao);
}

/* porta para os testes de ponta a ponta: a MESMA função que a interface usa */
window.platAjuda = { buscar, abrir, fechar, secoes: () => secoes };
