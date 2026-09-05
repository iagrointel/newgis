/* plat · catálogo — entrada da tela /conteudo (e /conteudo/<uuid>, /conteudo/lixeira). Módulos ES sem build; o cache
   é resolvido por no-store no nginx: NUNCA ?v= nos imports. Sessão por exigirSessao (ADR 0002); tipos de item de
   GET /api/tipos-item; abas Meu conteúdo · Favoritos · Meus grupos · Inquilino · Lixeira; busca com sintaxe por campo
   validada no cliente; vistas tabela/lista/grade; pastas, filtros, seleção em massa, painel do item; teclado:
   / foca a busca, j/k navegam, x seleciona, Enter abre, Esc limpa/fecha. body[data-pronto="1"] após a 1ª carga. */
import '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao, irParaLogin } from '../auth/sessao.js';
import * as api from './api.js';
import { ctx, lerVistaGuardada, guardarVista, limparSelecao } from './contexto.js';
import { analisar, EXEMPLOS, CAMPOS_TEXTO, CAMPOS_EXATOS, CAMPOS_DATA } from './busca_sintaxe.js';
import { icone } from './icones.js';
import * as lista from './lista.js';
import * as filtros from './filtros.js';
import * as pastas from './pastas.js';
import * as selecao from './selecao.js';
import * as lixeira from './lixeira.js';
import * as item from './item.js';
import { botaoNovo } from './novo.js';

const UUID_NA_URL = /^\/conteudo\/([0-9a-f-]{36})\/?$/i;
const ABAS = [['meus', 'catalogo.aba_meus'], ['favoritos', 'catalogo.aba_favoritos'], ['grupos', 'catalogo.aba_grupos'], ['inquilino', 'catalogo.aba_inquilino'], ['lixeira', 'catalogo.aba_lixeira']];
const ORDENS = [['', 'catalogo.ordem_padrao'], ['modificado_em:desc', 'catalogo.ordem_modificado'], ['criado_em:desc', 'catalogo.ordem_criado'], ['titulo:asc', 'catalogo.ordem_titulo'], ['tipo:asc', 'catalogo.ordem_tipo'], ['dono:asc', 'catalogo.ordem_dono'], ['tamanho_bytes:desc', 'catalogo.ordem_tamanho'], ['pontuacao:desc', 'catalogo.ordem_pontuacao']];
const el = (id) => document.getElementById(id);
let busca = null;
let saindo = false;

await carregarIdioma();
api.definirSemSessao(() => { saindo = true; irParaLogin(); });
const usuario = await exigirSessao();
if (usuario) {
  try { await iniciar(); } catch (e) { if (!(e && e.status === 401)) el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`); }
}
if (!saindo) pronto();

async function iniciar() {
  ctx.definir({ usuario });
  montarLayout({ usuario, ativo: '/conteudo' });
  const vista = lerVistaGuardada();
  if (['tabela', 'lista', 'grade'].includes(vista)) ctx.definir({ vista });
  // tipos primeiro: rótulos, ícones e esquemas dependem deles
  try { ctx.definir({ tipos: await api.tipos() }); } catch (e) { if (e.status === 401) return; el('aviso').mostrar(`${t('catalogo.tipos_indisponiveis')}: ${e.message}`, 'atencao'); }
  const botoes = [];
  if (tem('conteudo.criar')) botoes.push(botaoNovo({ criado: (novo) => { recarregarTudo(); item.abrir(novo.id); }, rotas: await api.rotasPublicadas() }));
  cabecalho(t('catalogo.titulo'), { contagem: 0, botoes });
  montarAbas();
  montarBusca();
  montarOrdenar();
  montarVistas();
  lista.iniciar({ abrir: (id) => item.abrir(id) });
  filtros.iniciar({ mudou: () => recarregarLista() });
  pastas.iniciar({ mudou: () => recarregarLista() });
  selecao.iniciar({ mudou: () => recarregarTudo() });
  lixeira.iniciar({ mudou: () => {} });
  item.iniciar({
    fechou: () => { ctx.definir({ itemAberto: null }); if (UUID_NA_URL.test(location.pathname)) history.pushState({}, '', '/conteudo'); },
    mudou: (it, info) => { if (info && (info.pasta || info.apagado)) recarregarTudo(); },
  });
  document.addEventListener('catalogo:ordenar', () => { el('ordenar').value = ctx.ler('ordenar'); recarregarLista(); });
  document.addEventListener('catalogo:restaurado', () => pastas.carregar());
  ctx.assinar(() => cabecalho(t('catalogo.titulo'), { contagem: ctx.ler('total') }), ['total']);
  teclado();
  // estado inicial pela URL
  if (location.pathname.replace(/\/$/, '') === '/conteudo/lixeira') ctx.definir({ aba: 'lixeira' });
  window.addEventListener('popstate', () => {
    const m = UUID_NA_URL.exec(location.pathname);
    if (m) item.abrir(m[1], { empurrarUrl: false }); else if (item.aberto()) item.fechar();
  });
  await Promise.all([pastas.carregar(), recarregarLista()]);
  const m = UUID_NA_URL.exec(location.pathname);
  if (m) await item.abrir(m[1], { empurrarUrl: false });
}

function recarregarTudo() { pastas.carregar(); return recarregarLista(); }

async function recarregarLista() {
  const aba = ctx.ler('aba');
  el('lixeira-area').hidden = aba !== 'lixeira';
  el('conteudo-grade').hidden = aba === 'lixeira';
  el('busca-linha').hidden = aba === 'lixeira';
  el('grupo-seletor').hidden = aba !== 'grupos';
  if (aba === 'lixeira') { limparSelecao(); await lixeira.carregar(); return; }
  if (aba === 'grupos' && !ctx.ler('grupoId')) { ctx.definir({ itens: [], total: 0, cursor: null }); return; }
  await Promise.all([lista.carregar(), filtros.carregar()]);
}

function montarAbas() {
  const area = el('abas');
  for (const [id, chave] of ABAS) {
    const b = h('button', { type: 'button', role: 'tab', id: `aba-${id}`, 'aria-selected': String(id === ctx.ler('aba')), 'aria-controls': id === 'lixeira' ? 'lixeira-area' : 'lista-area' }, t(chave));
    b.addEventListener('click', () => escolherAba(id));
    area.append(b);
  }
  ctx.assinar(() => { area.querySelectorAll('[role=tab]').forEach((x) => x.setAttribute('aria-selected', String(x.id === `aba-${ctx.ler('aba')}`))); }, ['aba']);
}

async function escolherAba(id) {
  if (ctx.ler('aba') === id) return;
  ctx.definir({ aba: id, cursor: null });
  limparSelecao();
  if (id === 'lixeira' && location.pathname !== '/conteudo/lixeira') history.pushState({}, '', '/conteudo/lixeira');
  else if (id !== 'lixeira' && location.pathname === '/conteudo/lixeira') history.pushState({}, '', '/conteudo');
  if (id === 'grupos') await montarGrupos();
  await recarregarLista();
}

async function montarGrupos() {
  const area = el('grupo-seletor');
  limpar(area);
  let grupos = [];
  try { grupos = (await api.meusGrupos()).itens || []; } catch (e) { if (e.status !== 401) el('aviso').erro(e.message); }
  const s = h('select', { id: 'grupo-id', 'aria-label': t('catalogo.grupo') }, h('option', { value: '' }, grupos.length ? t('catalogo.escolha_grupo') : t('grupos.vazio_meus')), ...grupos.map((g) => h('option', { value: g.id }, g.nome)));
  s.value = ctx.ler('grupoId') || '';
  s.addEventListener('change', () => { ctx.definir({ grupoId: s.value || null }); recarregarLista(); });
  area.append(h('label', {}, t('catalogo.grupo'), s));
  if (grupos.length === 1 && !ctx.ler('grupoId')) { s.value = grupos[0].id; ctx.definir({ grupoId: grupos[0].id }); }
}

function montarBusca() {
  const linha = el('busca-linha');
  busca = h('plat-busca', { id: 'busca', rotulo: t('catalogo.buscar'), atraso: '350' });
  linha.prepend(busca);
  const erro = el('busca-erro');
  busca.addEventListener('buscar', (e) => {
    const q = e.detail.q;
    const r = analisar(q);
    if (!r.ok) { erro.hidden = false; erro.textContent = r.erros.map((x) => x.mensagem).join('; '); return; }
    erro.hidden = true; erro.textContent = '';
    if (q === ctx.ler('q')) return;
    ctx.definir({ q, cursor: null });
    recarregarLista();
  });
  const bt = el('busca-ajuda-botao');
  bt.textContent = t('catalogo.busca_ajuda');
  const painelAjuda = el('busca-ajuda');
  bt.addEventListener('click', () => { painelAjuda.hidden = !painelAjuda.hidden; bt.setAttribute('aria-expanded', String(!painelAjuda.hidden)); if (!painelAjuda.hidden && !el('busca-ajuda-corpo').childElementCount) montarAjuda(); });
}

function montarAjuda() {
  const corpo = el('busca-ajuda-corpo');
  const tab = h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, t('catalogo.busca_forma')), h('th', {}, t('catalogo.busca_exemplo')), h('th', {}, t('catalogo.busca_faz')))));
  const tb = h('tbody');
  const linha = (forma, exemplo, faz) => tb.append(h('tr', {}, h('td', {}, forma), h('td', {}, h('code', {}, exemplo)), h('td', {}, faz)));
  linha(t('catalogo.busca_f_termos'), 'municipio rodovia', t('catalogo.busca_f_termos_faz'));
  linha(t('catalogo.busca_f_frase'), '"setor censitario"', t('catalogo.busca_f_frase_faz'));
  linha(t('catalogo.busca_f_operadores'), 'a OR b · NOT c · -c · (a OR b) c', t('catalogo.busca_f_operadores_faz'));
  linha(t('catalogo.busca_f_texto'), CAMPOS_TEXTO.map((c) => `${c}:`).join(' '), t('catalogo.busca_f_texto_faz'));
  linha(t('catalogo.busca_f_exato'), CAMPOS_EXATOS.map((c) => `${c}:`).join(' '), t('catalogo.busca_f_exato_faz'));
  linha(t('catalogo.busca_f_data'), CAMPOS_DATA.map((c) => `${c}:[a TO b]`).join(' '), t('catalogo.busca_f_data_faz'));
  tab.append(tb);
  const ex = h('ul', { class: 'sugestoes' });
  for (const [q, chave] of EXEMPLOS) {
    const b = h('button', { type: 'button', class: 'pequeno exemplo', title: t(chave) }, q);
    b.addEventListener('click', () => { busca.valor = q; busca.dispatchEvent(new CustomEvent('buscar', { detail: { q } })); busca.focar(); });
    ex.append(h('li', {}, b));
  }
  corpo.append(tab, h('h3', {}, t('catalogo.busca_exemplos')), ex);
}

function montarOrdenar() {
  const s = el('ordenar');
  for (const [v, chave] of ORDENS) s.append(h('option', { value: v }, t(chave)));
  s.value = ctx.ler('ordenar');
  s.addEventListener('change', () => { ctx.definir({ ordenar: s.value, cursor: null }); recarregarLista(); });
}

function montarVistas() {
  const area = el('vistas');
  area.setAttribute('aria-label', t('catalogo.vista'));
  for (const v of ['tabela', 'lista', 'grade']) {
    const b = h('button', { type: 'button', class: 'pequeno', id: `vista-${v}`, 'aria-pressed': String(ctx.ler('vista') === v), 'aria-label': t(`catalogo.vista_${v}`), title: t(`catalogo.vista_${v}`) }, icone(v, { tamanho: 16 }));
    b.addEventListener('click', () => { ctx.definir({ vista: v }); guardarVista(v); });
    area.append(b);
  }
  ctx.assinar(() => area.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.id === `vista-${ctx.ler('vista')}`))), ['vista']);
}

function teclado() {
  document.addEventListener('keydown', (e) => {
    const alvo = e.target;
    const emCampo = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'TEXTAREA' || alvo.tagName === 'SELECT' || alvo.isContentEditable);
    if (document.querySelector('dialog[open]')) return;
    if (e.key === '/' && !emCampo) { e.preventDefault(); busca.focar(); return; }
    if (emCampo) { if (e.key === 'Escape' && alvo === busca.querySelector('input')) { busca.valor = ''; busca.dispatchEvent(new CustomEvent('buscar', { detail: { q: '' } })); } return; }
    if (e.key === 'j') lista.moverFoco(1);
    else if (e.key === 'k') lista.moverFoco(-1);
    else if (e.key === 'Escape') limparSelecao();
  });
}
