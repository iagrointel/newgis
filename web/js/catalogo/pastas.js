/* plat · catálogo — árvore de pastas do inquilino (ADR 0004 seção 8.1: ≤ 5 níveis, visível a todos, contagem de
   itens visíveis vinda do servidor). Selecionar um nó filtra a lista por pasta_id; raiz = sem pasta. Criar, renomear
   e apagar (409 pasta_nao_vazia com a mensagem da API). */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { confirmar, pedir } from '../base/componentes.js';
import * as api from './api.js';
import { ctx } from './contexto.js';
import { icone } from './icones.js';
import { LIMITES } from './formato.js';

let arvore = [];        // nós aninhados [{id, nome, pai_id, profundidade, itens_visiveis, filhas: []}]
let porId = new Map();
let abertas = new Set();
let aoMudar = () => {};
const el = (id) => document.getElementById(id);

export function iniciar({ mudou }) {
  aoMudar = mudou;
  ctx.assinar(() => render(), ['pastaId']);
}

/* aceita a resposta aninhada (filhas) ou plana (pai_id) de GET /api/pastas/arvore */
function normalizar(lista) {
  const nos = Array.isArray(lista) ? lista : (lista && Array.isArray(lista.itens) ? lista.itens : []);
  const planos = [];
  const achatar = (n, prof) => { planos.push({ ...n, profundidade: n.profundidade ?? prof }); for (const f of n.filhas || []) achatar(f, (n.profundidade ?? prof) + 1); };
  for (const n of nos) achatar(n, 0);
  porId = new Map(planos.map((n) => [n.id, { ...n, filhas: [] }]));
  const raizes = [];
  for (const n of porId.values()) {
    const pai = n.pai_id ? porId.get(n.pai_id) : null;
    if (pai) pai.filhas.push(n); else raizes.push(n);
  }
  const ordenar = (l) => { l.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')); l.forEach((n) => ordenar(n.filhas)); };
  ordenar(raizes);
  return raizes;
}

export async function carregar() {
  try {
    arvore = normalizar(await api.pastasArvore());
  } catch (e) {
    if (e.status === 401) return;
    arvore = [];
    el('pastas').replaceChildren(h('p', { class: 'vazio-coluna' }, `${t('erro.carregar')}: ${e.message}`));
    return;
  }
  render();
}

export function pasta(id) { return porId.get(id) || null; }
export function todas() { return [...porId.values()]; }
export function caminhoDe(id) {
  const partes = [];
  let n = porId.get(id);
  while (n) { partes.unshift(n.nome); n = n.pai_id ? porId.get(n.pai_id) : null; }
  return partes;
}

/* <select> com a árvore indentada, para mover e criar */
export function seletorPasta(atual, { nome = 'pasta_id' } = {}) {
  const s = h('select', { name: nome, 'aria-label': t('catalogo.pasta') }, h('option', { value: '' }, t('catalogo.raiz')));
  const andar = (l) => { for (const n of l) { s.append(h('option', { value: n.id }, `${'  '.repeat(n.profundidade || 0)}${n.nome}`)); andar(n.filhas); } };
  andar(arvore);
  s.value = atual || '';
  return s;
}

function no(n) {
  const selecionada = ctx.ler('pastaId') === n.id;
  const temFilhas = n.filhas.length > 0;
  const aberta = abertas.has(n.id) || (n.ancestrais || []).length === 0 && n.profundidade === 0 && !temFilhas;
  const b = h('button', { type: 'button', class: 'no', 'aria-current': String(selecionada), 'aria-expanded': temFilhas ? String(aberta) : undefined },
    h('span', { class: 'alternar' }, temFilhas ? icone(aberta ? 'chevron_baixo' : 'chevron_dir', { tamanho: 12 }) : null),
    icone(aberta && temFilhas ? 'pasta_aberta' : 'pasta', { tamanho: 14 }),
    h('span', { class: 'nome', title: n.nome }, n.nome),
    n.itens_visiveis === undefined || n.itens_visiveis === null ? null : h('span', { class: 'n' }, String(n.itens_visiveis)));
  b.addEventListener('click', () => {
    if (temFilhas && selecionada) { if (abertas.has(n.id)) abertas.delete(n.id); else abertas.add(n.id); render(); return; }
    if (temFilhas) abertas.add(n.id);
    ctx.definir({ pastaId: n.id });
    aoMudar();
  });
  const li = h('li', {}, b);
  if (temFilhas && aberta) li.append(h('ul', {}, ...n.filhas.map(no)));
  return li;
}

function render() {
  const raiz = el('pastas');
  limpar(raiz);
  const raizBotao = h('button', { type: 'button', class: 'no', 'aria-current': String(!ctx.ler('pastaId')) }, h('span', { class: 'alternar' }, ''), icone('pasta_aberta', { tamanho: 14 }), h('span', { class: 'nome' }, t('catalogo.raiz')));
  raizBotao.addEventListener('click', () => { ctx.definir({ pastaId: null }); aoMudar(); });
  const ul = h('ul', {}, h('li', {}, raizBotao), ...arvore.map(no));
  raiz.append(h('nav', { class: 'arvore', 'aria-label': t('catalogo.pastas') }, ul));
  if (tem('conteudo.criar')) {
    const acoes = h('div', { class: 'acoes-pasta' });
    const nova = h('button', { type: 'button', class: 'pequeno', id: 'pasta-nova' }, t('catalogo.pasta_nova'));
    nova.addEventListener('click', () => criar(ctx.ler('pastaId')));
    acoes.append(nova);
    const atual = ctx.ler('pastaId') ? porId.get(ctx.ler('pastaId')) : null;
    if (atual) {
      const ren = h('button', { type: 'button', class: 'pequeno', id: 'pasta-renomear' }, t('catalogo.pasta_renomear'));
      ren.addEventListener('click', () => renomear(atual));
      const apg = h('button', { type: 'button', class: 'pequeno perigo', id: 'pasta-apagar' }, t('catalogo.pasta_apagar'));
      apg.addEventListener('click', () => apagar(atual));
      acoes.append(ren, apg);
    }
    raiz.append(acoes);
  }
}

function formNome(padrao) {
  const f = h('plat-formulario');
  f.campos = [{ nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: padrao || '', atributos: { maxlength: LIMITES.pastaNome }, ajuda: t('catalogo.pasta_nome_ajuda', { max: LIMITES.pastaNome }) }];
  f.botoes = [{ id: 'ok', rotulo: t('acao.salvar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  return f;
}

export async function criar(paiId) {
  const pai = paiId ? porId.get(paiId) : null;
  if (pai && (pai.profundidade || 0) >= LIMITES.pastaProfundidade - 1) { el('aviso').mostrar(t('catalogo.pasta_profunda', { max: LIMITES.pastaProfundidade }), 'atencao'); return; }
  const v = await pedir(pai ? t('catalogo.pasta_nova_em', { pasta: pai.nome }) : t('catalogo.pasta_nova'), formNome(''));
  if (!v) return;
  try {
    const p = await api.pastaCriar(v.nome.trim(), paiId || null);
    await carregar();
    if (paiId) abertas.add(paiId);
    ctx.definir({ pastaId: p.id });
    aoMudar();
    el('aviso').ok(t('catalogo.pasta_criada', { nome: p.nome }));
  } catch (e) { el('aviso').erro(e.message); }
}

async function renomear(n) {
  const v = await pedir(t('catalogo.pasta_renomear'), formNome(n.nome));
  if (!v || v.nome.trim() === n.nome) return;
  try { await api.pastaEditar(n.id, { nome: v.nome.trim() }); await carregar(); el('aviso').ok(t('catalogo.pasta_salva')); } catch (e) { el('aviso').erro(e.message); }
}

async function apagar(n) {
  if (!(await confirmar(t('catalogo.pasta_apagar'), t('catalogo.pasta_apagar_confirma', { nome: n.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
  try {
    await api.pastaApagar(n.id);
    ctx.definir({ pastaId: n.pai_id || null });
    await carregar();
    aoMudar();
    el('aviso').ok(t('catalogo.pasta_apagada', { nome: n.nome }));
  } catch (e) {
    const d = e.detalhe || {};
    el('aviso').erro(e.codigo === 'pasta_nao_vazia' ? t('catalogo.pasta_nao_vazia', { itens: d.itens ?? '?', pastas: d.pastas ?? '?' }) : e.message);
  }
}
