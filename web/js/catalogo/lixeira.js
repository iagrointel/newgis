/* plat · catálogo — aba Lixeira (ADR 0004 seção 9 e 15.3): GET /api/lixeira com título, tipo, apagado por, apagado
   em, expurga em (apagado + 30 d), Restaurar / Apagar agora por linha, filtro por tipo e período, "Esvaziar lixeira"
   com confirmação por texto. Usa <plat-tabela> e <plat-paginacao> da base. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { confirmar, pedir } from '../base/componentes.js';
import * as api from './api.js';
import { ctx, rotuloTipo } from './contexto.js';
import { dataHora, elipse, nomeDono, LIMITES } from './formato.js';

const LIMITE = LIMITES.pagina;
const f = { tipo: '', apagado_de: '', apagado_ate: '', deslocamento: 0 };
let seq = 0;
let total = 0;
let aoMudar = () => {};
const el = (id) => document.getElementById(id);

export function iniciar({ mudou }) {
  aoMudar = mudou;
  const tab = el('lixeira-tabela');
  tab.setAttribute('legenda', t('catalogo.aba_lixeira'));
  tab.colunas = [
    { chave: 'titulo', titulo: t('catalogo.col_titulo'), formatar: (v) => h('span', { title: v }, elipse(v, 120)) },
    { chave: 'tipo', titulo: t('catalogo.col_tipo'), formatar: (v) => rotuloTipo(v) },
    { chave: 'apagado_por', titulo: t('catalogo.apagado_por'), formatar: (v) => nomeDono(v) },
    { chave: 'apagado_em', titulo: t('catalogo.apagado_em'), formatar: (v) => dataHora(v) },
    { chave: 'expurga_em', titulo: t('catalogo.expurga_em'), classe: 'expurga', formatar: (v, l) => dataHora(v || (l.apagado_em ? new Date(new Date(l.apagado_em).getTime() + 30 * 86400000).toISOString() : null)) },
  ];
  tab.selecionavel = true;
  tab.limiteSelecao = LIMITES.lote;
  tab.acoes = () => [{ id: 'restaurar', rotulo: t('catalogo.restaurar'), classe: 'primario' }, { id: 'expurgar', rotulo: t('catalogo.apagar_agora'), classe: 'perigo' }];
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
  tab.addEventListener('selecao', (e) => ctx.definir({ selecionados: e.detail.ids }));
  el('lixeira-paginacao').addEventListener('mudar', (e) => { f.deslocamento = e.detail.deslocamento; carregar(); });
  montarFerramentas();
}

function montarFerramentas() {
  const barra = el('lixeira-ferramentas');
  limpar(barra);
  const tipo = h('select', { id: 'lixeira-tipo', 'aria-label': t('catalogo.col_tipo') }, h('option', { value: '' }, t('geral.todos')), ...(ctx.ler('tipos') || []).map((x) => h('option', { value: x.nome }, x.rotulo)));
  tipo.addEventListener('change', () => { f.tipo = tipo.value; f.deslocamento = 0; carregar(); });
  const de = h('input', { type: 'date', id: 'lixeira-de', 'aria-label': t('catalogo.de') });
  const ate = h('input', { type: 'date', id: 'lixeira-ate', 'aria-label': t('catalogo.ate') });
  de.addEventListener('change', () => { f.apagado_de = de.value; f.deslocamento = 0; carregar(); });
  ate.addEventListener('change', () => { f.apagado_ate = ate.value; f.deslocamento = 0; carregar(); });
  const esvaziar = h('button', { type: 'button', class: 'perigo pequeno', id: 'lixeira-esvaziar' }, t('catalogo.esvaziar_lixeira'));
  esvaziar.addEventListener('click', esvaziarTudo);
  barra.append(h('div', { class: 'filtros' }, h('label', {}, t('catalogo.col_tipo'), tipo), h('label', {}, t('catalogo.apagado_de'), de), h('label', {}, t('catalogo.apagado_ate'), ate)), h('div', { class: 'direita' }, h('span', { class: 'fraco' }, t('catalogo.lixeira_texto', { dias: 30 })), esvaziar));
}

export async function carregar() {
  const meu = ++seq;
  const tab = el('lixeira-tabela');
  const aviso = el('lixeira-aviso');
  try {
    const r = await api.lixeira({ limite: LIMITE, deslocamento: f.deslocamento, tipo: f.tipo, apagado_de: f.apagado_de, apagado_ate: f.apagado_ate });
    if (meu !== seq) return;
    aviso.limpar();
    tab.linhas = r.itens || [];
    tab.vazio = t('catalogo.lixeira_vazia');
    total = r.total ?? (r.itens || []).length;
    el('lixeira-paginacao').atualizar({ total, limite: LIMITE, deslocamento: f.deslocamento });
    el('lixeira-esvaziar').disabled = total === 0;
    aoMudar(total);
  } catch (e) {
    if (meu !== seq || e.status === 401) return;
    aviso.erro(`${t('erro.carregar')}: ${e.message}`);
    tab.linhas = [];
  }
}

async function acao(id, item) {
  const aviso = el('aviso');
  aviso.limpar();
  try {
    if (id === 'restaurar') {
      const it = await api.lixeiraRestaurar(item.id);
      await carregar();
      aviso.ok(t('catalogo.restaurado', { titulo: elipse(it.titulo || item.titulo, 60) }));
      document.dispatchEvent(new CustomEvent('catalogo:restaurado', { detail: { item: it } }));
    } else if (id === 'expurgar') {
      if (!(await confirmar(t('catalogo.apagar_agora'), t('catalogo.expurgar_confirma', { titulo: elipse(item.titulo, 60) }), { perigo: true, ok: t('catalogo.apagar_agora') }))) return;
      await api.lixeiraEsvaziar([item.id]);
      await carregar();
      aviso.ok(t('catalogo.expurgo_enfileirado', { n: 1 }));
    }
  } catch (e) { aviso.erro(e.message); }
}

async function esvaziarTudo() {
  const form = h('plat-formulario');
  form.campos = [{ nome: 'confirma', rotulo: t('catalogo.esvaziar_digite', { palavra: 'esvaziar' }), tipo: 'texto', obrigatorio: true, atributos: { autocomplete: 'off' } }];
  form.botoes = [{ id: 'ok', rotulo: t('catalogo.esvaziar_lixeira'), tipo: 'submit', classe: 'perigo' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.esvaziar_lixeira'), form);
  if (!v) return;
  if (v.confirma.trim().toLowerCase() !== 'esvaziar') { el('aviso').mostrar(t('catalogo.esvaziar_nao_confirmado'), 'atencao'); return; }
  try {
    await api.lixeiraEsvaziar();
    await carregar();
    el('aviso').ok(t('catalogo.expurgo_enfileirado', { n: total }));
  } catch (e) { el('aviso').erro(e.message); }
}
