/* plat · catálogo — ações em massa sobre a seleção (POST /api/itens/lote, ADR 0004 seção 13.3): mover, compartilhar,
   tags, apagar, proteger/desproteger, status, transferir dono. Até 100; o resultado {feitos, recusados} aparece
   com o motivo por item. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { confirmar, pedir } from '../base/componentes.js';
import { textoErro } from '../auth/comum.js';
import * as api from './api.js';
import { ctx, limparSelecao } from './contexto.js';
import { seletorPasta } from './pastas.js';
import { tagsDeTexto } from './formato.js';
import { abrirTransferencia } from './item_transferir.js';

let aoMudar = () => {};
const el = (id) => document.getElementById(id);

export function iniciar({ mudou }) {
  aoMudar = mudou;
  ctx.assinar(() => render(), ['selecionados', 'aba']);
}

function render() {
  const area = el('lote');
  limpar(area);
  const ids = ctx.ler('selecionados');
  if (!ids.length) { area.hidden = true; return; }
  area.hidden = false;
  area.append(h('span', { id: 'lote-contagem' }, t('catalogo.selecionados', { n: ids.length })));
  const limparBt = h('button', { type: 'button', class: 'texto pequeno' }, t('catalogo.limpar_selecao'));
  limparBt.addEventListener('click', () => limparSelecao());
  area.append(limparBt);
  const bt = (id, rotulo, fn, classe = 'pequeno') => { const b = h('button', { type: 'button', class: classe, id: `lote-${id}` }, rotulo); b.addEventListener('click', () => fn(ids)); area.append(b); };
  if (ctx.ler('aba') === 'lixeira') {
    bt('restaurar', t('catalogo.restaurar'), restaurar, 'pequeno primario');
    bt('expurgar', t('catalogo.apagar_agora'), expurgar, 'pequeno perigo');
  } else {
    bt('mover', t('catalogo.mover'), mover);
    bt('compartilhar', t('catalogo.compartilhar'), compartilhar);
    bt('tags', t('catalogo.tags'), tags);
    if (tem('conteudo.editar_tudo') || tem('conteudo.criar')) { bt('proteger', t('catalogo.proteger'), (i) => simples(i, 'proteger')); bt('desproteger', t('catalogo.desproteger'), (i) => simples(i, 'desproteger')); bt('status', t('catalogo.status'), status); }
    if (tem('conteudo.transferir') || tem('conteudo.criar')) bt('transferir', t('catalogo.transferir_dono'), (i) => abrirTransferencia(i, { aoTerminar: () => { limparSelecao(); aoMudar(); } }));
    bt('apagar', t('acao.apagar'), apagar, 'pequeno perigo');
  }
  area.append(h('span', { class: 'resultado-lote', id: 'resultado-lote', 'aria-live': 'polite' }));
}

async function executar(corpo) {
  const aviso = el('aviso');
  let r;
  try { r = await api.lote(corpo); } catch (e) { aviso.erro(e.message); return null; }
  const rec = r.recusados || [];
  const feitos = r.feitos ?? r.apagados ?? 0;
  aoMudar();
  const partes = [t('catalogo.lote_feitos', { n: feitos })];
  if (rec.length) partes.push(t('catalogo.lote_recusados', { n: rec.length, motivos: rec.map((x) => `${String(x.id).slice(0, 8)}: ${textoErro(x.erro)}`).join('; ') }));
  aviso.mostrar(partes.join(' · '), rec.length ? 'atencao' : 'ok');
  if (!rec.length) limparSelecao();
  return r;
}

async function mover(ids) {
  const f = h('plat-formulario');
  const sel = seletorPasta(ctx.ler('pastaId'));
  f.campos = [{ nome: 'pasta_id', rotulo: t('catalogo.pasta'), tipo: 'select', opcoes: [...sel.options].map((o) => ({ valor: o.value, rotulo: o.textContent })), padrao: ctx.ler('pastaId') || '' }];
  f.botoes = [{ id: 'ok', rotulo: t('catalogo.mover'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.mover_n', { n: ids.length }), f);
  if (!v) return;
  await executar({ ids, acao: 'mover', pasta_id: v.pasta_id || null });
}

async function compartilhar(ids) {
  const f = h('plat-formulario');
  const opcoes = [{ valor: 'privado', rotulo: t('catalogo.acesso_privado') }];
  if (tem('compartilhar.inquilino')) opcoes.push({ valor: 'inquilino', rotulo: t('catalogo.acesso_inquilino') });
  if (tem('compartilhar.publico')) opcoes.push({ valor: 'publico', rotulo: t('catalogo.acesso_publico') });
  f.campos = [{ nome: 'acesso', rotulo: t('catalogo.nivel_acesso'), tipo: 'select', opcoes, padrao: 'privado', ajuda: t('catalogo.compartilhar_lote_ajuda') }];
  f.botoes = [{ id: 'ok', rotulo: t('catalogo.aplicar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.compartilhar_n', { n: ids.length }), f);
  if (!v) return;
  await executar({ ids, acao: 'compartilhar', acesso: v.acesso });
}

async function tags(ids) {
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'acrescentar', rotulo: t('catalogo.tags_acrescentar'), tipo: 'texto', ajuda: t('catalogo.tags_ajuda') },
    { nome: 'de', rotulo: t('catalogo.tag_renomear_de'), tipo: 'texto' },
    { nome: 'para', rotulo: t('catalogo.tag_renomear_para'), tipo: 'texto' },
  ];
  f.botoes = [{ id: 'ok', rotulo: t('catalogo.aplicar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.tags_n', { n: ids.length }), f);
  if (!v) return;
  const corpo = { ids, acao: 'tags' };
  const acr = tagsDeTexto(v.acrescentar);
  if (acr.length) corpo.tags = acr;
  if (v.de && v.para) { corpo.de = v.de.trim(); corpo.para = v.para.trim(); }
  if (!corpo.tags && !corpo.de) { el('aviso').mostrar(t('catalogo.tags_nada'), 'atencao'); return; }
  await executar(corpo);
}

async function status(ids) {
  const f = h('plat-formulario');
  const opcoes = [{ valor: '', rotulo: t('catalogo.status_nenhum') }, { valor: 'obsoleto', rotulo: t('catalogo.status_obsoleto') }];
  if (tem('conteudo.editar_tudo')) opcoes.push({ valor: 'autoritativo', rotulo: t('catalogo.status_autoritativo') });
  f.campos = [{ nome: 'status', rotulo: t('catalogo.status'), tipo: 'select', opcoes, padrao: '' }];
  f.botoes = [{ id: 'ok', rotulo: t('catalogo.aplicar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.status_n', { n: ids.length }), f);
  if (!v) return;
  await executar({ ids, acao: 'status', status: v.status || 'nenhum' });
}

async function simples(ids, acao) { await executar({ ids, acao }); }

async function apagar(ids) {
  if (!(await confirmar(t('acao.apagar'), t('catalogo.apagar_n_confirma', { n: ids.length }), { perigo: true, ok: t('acao.apagar') }))) return;
  await executar({ ids, acao: 'apagar' });
}

async function restaurar(ids) { await executar({ ids, acao: 'restaurar' }); }

async function expurgar(ids) {
  if (!(await confirmar(t('catalogo.apagar_agora'), t('catalogo.expurgar_n_confirma', { n: ids.length }), { perigo: true, ok: t('catalogo.apagar_agora') }))) return;
  try { await api.lixeiraEsvaziar(ids); limparSelecao(); aoMudar(); el('aviso').ok(t('catalogo.expurgo_enfileirado', { n: ids.length })); } catch (e) { el('aviso').erro(e.message); }
}
