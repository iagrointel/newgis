/* plat · catálogo — painel do item (/conteudo/{id}, ADR 0004 seção 15.2) no <plat-dialogo modo="lateral">: cabeçalho
   (miniatura, título, tipo, dono, acesso, status, uuid/URL copiáveis, favorito, Abrir em, menu ⋯), pontuação 0-10 com
   o que falta, abas Visão geral (metadado editável em linha por PATCH) · Dados (formulário do JSON Schema, PUT) ·
   Configurações (extent, proteção, status, pasta, dono, miniatura) · Versões · Relações · Compartilhamento.
   A descrição chega saneada do servidor (descricao_html) e passa de novo pelo DOMPurify aqui (L5 D23). */
import { h, limpar, htmlSeguro, botaoCopiar, marcador } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import { confirmar, pedir } from '../base/componentes.js';
import * as api from './api.js';
import { ctx, tipoDe, rotuloTipo, atualizarItemNaLista, removerItemDaLista } from './contexto.js';
import { bytes, elipse, quando, dataHora, rotuloAcesso, rotuloStatus, rotuloOrigem, nomeDono, tagsDeTexto, textoExtent, extentDeTexto, validarMetadado, LIMITES } from './formato.js';
import { icone, iconeDoTipo } from './icones.js';
import { camposDoEsquema, dadosDosValores, aplicarErros, errosDoServidor, resumoDados } from './item_dados.js';
import { abrirCompartilhar } from './item_compartilhar.js';
import { abrirTransferencia } from './item_transferir.js';
import * as versoes from './item_versoes.js';
import * as relacoes from './item_relacoes.js';
import { seletorPasta, caminhoDe } from './pastas.js';

let item = null;
let aba = 'visao';
let aoFechar = () => {};
let aoMudou = () => {};
const el = (id) => document.getElementById(id);
const painel = () => el('painel');

export function iniciar({ fechou, mudou }) { aoFechar = fechou; aoMudou = mudou; }
export function aberto() { return !!item; }
export function idAberto() { return item ? item.id : null; }

export async function abrir(id, { empurrarUrl = true, abaInicial } = {}) {
  const d = painel();
  const corpo = h('div', { class: 'item-painel' }, h('p', { class: 'fraco' }, t('catalogo.carregando')));
  if (!d.aberto) {
    d.abrir({ titulo: t('catalogo.item'), corpo }).then(() => { const era = item; item = null; if (era) aoFechar(era); });
  } else { limpar(d.corpo); d.corpo.append(corpo); }
  if (empurrarUrl && location.pathname !== `/conteudo/${id}`) history.pushState({ item: id }, '', `/conteudo/${id}`);
  try {
    item = await api.obter(id);
  } catch (e) {
    limpar(corpo);
    corpo.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, e.status === 404 ? t('catalogo.item_inexistente') : e.message));
    ctx.definir({ itemAberto: id });
    return;
  }
  ctx.definir({ itemAberto: id });
  if (abaInicial) aba = abaInicial;
  render();
}

export function fechar() { if (painel().aberto) painel().fechar(null); }

function mudou(parcial) {
  item = { ...item, ...parcial };
  atualizarItemNaLista(item);
  aoMudou(item);
}

async function recarregar() { try { item = await api.obter(item.id); atualizarItemNaLista(item); render(); } catch (e) { avisoPainel().erro(e.message); } }

function avisoPainel() { return el('item-aviso') || h('plat-aviso'); }

/* ---------- cabeçalho ---------- */
function miniatura() {
  const tipo = tipoDe(item.tipo);
  if (item.miniatura) {
    const img = h('img', { class: 'mini', src: `${item.miniatura}${item.miniatura.includes('?') ? '&' : '?'}r=${encodeURIComponent(item.modificado_em || '')}`, alt: '', width: 150, height: 100 });
    img.addEventListener('error', () => img.replaceWith(h('span', { class: 'mini-icone' }, iconeDoTipo(tipo, { tamanho: 36 }))), { once: true });
    return img;
  }
  return h('span', { class: 'mini-icone' }, iconeDoTipo(tipo, { tamanho: 36 }));
}

function pontuacao() {
  const faltam = [];
  if (!item.resumo) faltam.push(t('catalogo.resumo'));
  if (!(item.descricao || '').length || (item.descricao || '').length < 100) faltam.push(t('catalogo.descricao_100'));
  if ((item.tags || []).length < 3) faltam.push(t('catalogo.tags_3'));
  if (!item.creditos) faltam.push(t('catalogo.creditos'));
  if (!item.termos_de_uso) faltam.push(t('catalogo.termos_de_uso'));
  if (!item.extent) faltam.push(t('catalogo.extent'));
  if (!item.miniatura) faltam.push(t('catalogo.miniatura'));
  if (!(item.categorias || []).length) faltam.push(t('catalogo.categorias'));
  const p = item.pontuacao ?? 0;
  const det = h('details', { class: 'pontuacao' }, h('summary', {}, t('catalogo.pontuacao', { n: p }), h('span', { class: 'barra' }, h('span', { style: `width:${p * 10}%` }))));
  det.append(faltam.length ? h('ul', {}, ...faltam.map((x) => h('li', {}, x))) : h('p', {}, t('catalogo.pontuacao_completa')));
  return det;
}

function menuMais() {
  const wrap = h('div', { class: 'menu-mais' });
  const b = h('button', { type: 'button', class: 'pequeno', id: 'item-mais', 'aria-haspopup': 'true', 'aria-expanded': 'false', 'aria-label': t('catalogo.mais_acoes') }, '⋯');
  const ul = h('ul', { role: 'menu', hidden: true });
  const fechar = () => { ul.hidden = true; b.setAttribute('aria-expanded', 'false'); };
  const op = (id, rotulo, fn, classe = '') => { const bt = h('button', { type: 'button', role: 'menuitem', class: classe, id: `item-${id}` }, rotulo); bt.addEventListener('click', () => { fechar(); fn(); }); ul.append(h('li', {}, bt)); };
  if (item.pode_editar) op('mover', t('catalogo.mover'), mover);
  if (item.pode_editar && (tem('conteudo.transferir') || tem('conteudo.criar'))) op('transferir', t('catalogo.transferir_dono'), () => abrirTransferencia([item.id], { aoTerminar: () => recarregar() }));
  if (item.pode_editar) op('proteger', item.protegido ? t('catalogo.desproteger') : t('catalogo.proteger'), () => remendar({ protegido: !item.protegido }));
  if (item.pode_editar) op('obsoleto', item.status === 'obsoleto' ? t('catalogo.tirar_obsoleto') : t('catalogo.marcar_obsoleto'), () => remendar({ status: item.status === 'obsoleto' ? 'nenhum' : 'obsoleto' }));
  if (tem('conteudo.editar_tudo')) op('autoritativo', item.status === 'autoritativo' ? t('catalogo.tirar_autoritativo') : t('catalogo.marcar_autoritativo'), () => remendar({ status: item.status === 'autoritativo' ? 'nenhum' : 'autoritativo' }));
  op('copiar_uuid', t('catalogo.copiar_uuid'), () => navigator.clipboard?.writeText(item.id).catch(() => {}));
  op('copiar_url', t('catalogo.copiar_url'), () => navigator.clipboard?.writeText(`${location.origin}/conteudo/${item.id}`).catch(() => {}));
  if (item.pode_apagar) op('apagar', t('acao.apagar'), apagar, 'perigo');
  b.addEventListener('click', () => { ul.hidden = !ul.hidden; b.setAttribute('aria-expanded', String(!ul.hidden)); if (!ul.hidden) ul.querySelector('button')?.focus(); });
  wrap.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); fechar(); b.focus(); } });
  wrap.addEventListener('focusout', (e) => { if (!wrap.contains(e.relatedTarget)) fechar(); });
  wrap.append(b, ul);
  return wrap;
}

function botaoFavorito() {
  const b = h('button', { type: 'button', class: 'favorito', id: 'item-favorito', 'aria-pressed': String(!!item.favorito), 'aria-label': item.favorito ? t('catalogo.desfavoritar') : t('catalogo.favoritar') }, icone('estrela', { tamanho: 18 }));
  b.addEventListener('click', async () => {
    try { if (item.favorito) await api.desfavoritar(item.id); else await api.favoritar(item.id); mudou({ favorito: !item.favorito }); render(); } catch (e) { avisoPainel().erro(e.message); }
  });
  return b;
}

function abrirEm() {
  const destinos = Array.isArray(item.abre_em) ? item.abre_em : [];
  if (!destinos.length) return null;
  const s = h('select', { id: 'item-abrir-em', 'aria-label': t('catalogo.abrir_em') }, h('option', { value: '' }, t('catalogo.abrir_em')), ...destinos.map((d) => h('option', { value: d }, t(`catalogo.abrir_${d}`) === `catalogo.abrir_${d}` ? d : t(`catalogo.abrir_${d}`))));
  s.addEventListener('change', () => { if (!s.value) return; avisoPainel().mostrar(t('catalogo.abrir_em_futuro', { destino: s.options[s.selectedIndex].textContent }), 'info'); s.value = ''; });
  return s;
}

function cabecalho() {
  const tipo = tipoDe(item.tipo);
  const selos = [];
  if (item.status) selos.push(marcador(rotuloStatus(item.status), item.status === 'autoritativo' ? 'ok' : 'atencao'));
  if (item.protegido) selos.push(marcador(t('catalogo.protegido'), ''));
  if (item.apagado_em) selos.push(marcador(t('catalogo.na_lixeira'), 'falha'));
  const url = `${location.origin}/conteudo/${item.id}`;
  return h('div', { class: 'item-cabecalho' }, miniatura(),
    h('div', {},
      h('h3', { id: 'item-titulo' }, item.titulo),
      h('div', { class: 'meta' }, h('span', {}, iconeDoTipo(tipo, { tamanho: 14 }), ' ', rotuloTipo(item.tipo)), h('span', {}, nomeDono(item.dono)), h('span', { title: dataHora(item.modificado_em) }, t('catalogo.modificado_ha', { quando: quando(item.modificado_em) })), h('span', {}, rotuloAcesso(item)), ...selos),
      h('div', { class: 'item-ids' }, h('span', {}, 'uuid ', h('code', { id: 'item-uuid' }, item.id)), botaoCopiar(item.id, null, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') }), h('span', {}, 'URL'), botaoCopiar(url, null, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })),
      h('div', { class: 'acoes' }, botaoFavorito(), item.pode_compartilhar ? botaoCompartilhar() : null, abrirEm(), menuMais()),
      pontuacao()));
}

function botaoCompartilhar() {
  const b = h('button', { type: 'button', class: 'pequeno', id: 'item-compartilhar' }, t('catalogo.compartilhar'));
  b.addEventListener('click', () => abrirCompartilhar(item, { aoMudar: (p) => { mudou(p); render(); } }));
  return b;
}

/* ---------- abas ---------- */
const ABAS = [['visao', 'catalogo.aba_visao'], ['dados', 'catalogo.aba_dados'], ['config', 'catalogo.aba_config'], ['versoes', 'catalogo.versoes'], ['relacoes', 'catalogo.aba_relacoes'], ['compartilhamento', 'catalogo.aba_compartilhamento']];

function render() {
  const d = painel();
  const corpo = h('div', { class: 'item-painel' });
  const aviso = h('plat-aviso', { id: 'item-aviso' });
  corpo.append(aviso, cabecalho());
  const abas = h('div', { class: 'abas', role: 'tablist', id: 'item-abas' });
  const paineis = h('div', { class: 'item-abas' });
  for (const [id, chave] of ABAS) {
    const b = h('button', { type: 'button', role: 'tab', id: `item-aba-${id}`, 'aria-selected': String(id === aba), 'aria-controls': `item-painel-${id}` }, t(chave));
    b.addEventListener('click', () => { aba = id; render(); });
    abas.append(b);
  }
  const conteudo = h('div', { role: 'tabpanel', id: `item-painel-${aba}`, 'aria-labelledby': `item-aba-${aba}` });
  conteudo.append({ visao: abaVisao, dados: abaDados, config: abaConfig, versoes: () => versoes.montar(item, { aoMudar: (novo) => { mudou(novo); } }), relacoes: () => relacoes.montar(item, { abrir: (id) => abrir(id) }), compartilhamento: abaCompartilhamento }[aba]());
  paineis.append(abas, conteudo);
  corpo.append(paineis);
  limpar(d.corpo);
  d.corpo.append(corpo);
  d.querySelector('h2').textContent = elipse(item.titulo, 60);
}

/* ---------- visão geral: campo a campo, editar em linha ---------- */
function linhaCampo(rotulo, valorNo, { chave, editar } = {}) {
  const valor = h('div', { class: `valor${valorNo ? '' : ' vazio'}` }, valorNo || t('catalogo.vazio_campo'));
  if (editar && item.pode_editar) {
    const b = h('button', { type: 'button', class: 'pequeno texto editar', 'data-campo': chave, 'aria-label': `${t('acao.editar')} ${rotulo}` }, t('acao.editar'));
    b.addEventListener('click', () => editar(valor));
    valor.append(b);
  }
  return h('div', { class: 'campo-linha', 'data-campo': chave }, h('div', { class: 'rotulo' }, rotulo), valor);
}

function editorTexto(chave, rotulo, { area = false, max, ajuda } = {}) {
  return async () => {
    const f = h('plat-formulario');
    f.campos = [{ nome: chave, rotulo, tipo: area ? 'area' : 'texto', padrao: item[chave] || '', atributos: { maxlength: max }, ajuda, linhas: area ? 8 : undefined, obrigatorio: chave === 'titulo' }];
    f.botoes = [{ id: 'ok', rotulo: t('acao.salvar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
    f.addEventListener('enviar', async (e) => {
      const v = e.detail.valores;
      const erros = validarMetadado({ [chave]: v[chave] });
      if (erros[chave]) { f.erro(chave, erros[chave]); return; }
      f.ocupado = true;
      try { const novo = await api.editar(item.id, { [chave]: v[chave] || null }); mudou(novo); el('painel-editar')?.fechar('ok'); render(); avisoPainel().ok(t('catalogo.salvo')); } catch (err) { f.ocupado = false; f.mensagem(err.message, 'erro'); }
    });
    abrirEditor(`${t('acao.editar')} · ${rotulo}`, f);
  };
}

function abrirEditor(titulo, f) {
  const d = el('painel-editar') || document.body.appendChild(h('plat-dialogo', { id: 'painel-editar' }));
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') d.fechar(null); });
  d.abrir({ titulo, corpo: f });
}

function editorTags() {
  return async () => {
    const f = h('div', { class: 'form' });
    const atual = [...(item.tags || [])];
    const chips = h('div', { class: 'chips', id: 'tags-chips' });
    const entrada = h('input', { type: 'text', id: 'tags-entrada', 'aria-label': t('catalogo.tags_nova'), maxlength: LIMITES.tag, autocomplete: 'off', list: 'tags-sugestoes' });
    const lista = h('datalist', { id: 'tags-sugestoes' });
    const desenhar = () => { limpar(chips); for (const tg of atual) { const rm = h('button', { type: 'button', class: 'texto', 'aria-label': t('catalogo.remover_tag', { tag: tg }) }, '×'); rm.addEventListener('click', () => { atual.splice(atual.indexOf(tg), 1); desenhar(); }); chips.append(h('span', { class: 'chip' }, h('span', { class: 'nome' }, tg), rm)); } };
    const acrescentar = () => { for (const tg of tagsDeTexto(entrada.value)) if (!atual.includes(tg) && atual.length < LIMITES.tags) atual.push(tg); entrada.value = ''; desenhar(); };
    entrada.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); acrescentar(); } });
    let timer = null;
    entrada.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(async () => { try { const r = await api.tagsSugerir(entrada.value.trim()); limpar(lista); for (const s of Array.isArray(r) ? r : []) lista.append(h('option', { value: s.tag })); } catch { /* sem sugestão */ } }, 250); });
    const add = h('button', { type: 'button', class: 'pequeno', id: 'tags-acrescentar' }, t('catalogo.acrescentar'));
    add.addEventListener('click', acrescentar);
    desenhar();
    const editor = h('div', { class: 'chips-editor' }, chips, h('div', { class: 'entrada' }, entrada, lista, add), h('span', { class: 'ajuda' }, t('catalogo.tags_ajuda_editor', { max: LIMITES.tags })));
    const salvar = h('button', { type: 'button', class: 'primario', id: 'tags-salvar' }, t('acao.salvar'));
    const aviso = h('plat-aviso');
    salvar.addEventListener('click', async () => {
      acrescentar();
      salvar.disabled = true;
      try { const novo = await api.editar(item.id, { tags: atual }); mudou(novo); el('painel-editar')?.fechar('ok'); render(); avisoPainel().ok(t('catalogo.salvo')); } catch (err) { salvar.disabled = false; aviso.erro(err.message); }
    });
    f.append(aviso, editor, h('div', { class: 'botoes' }, salvar));
    const d = el('painel-editar') || document.body.appendChild(h('plat-dialogo', { id: 'painel-editar' }));
    d.abrir({ titulo: t('catalogo.tags'), corpo: f, botoes: [{ id: 'cancelar', rotulo: t('acao.cancelar') }] });
  };
}

function descricaoHtml() {
  if (!item.descricao_html && !item.descricao) return null;
  const div = h('div', { class: 'descricao-html' });
  if (item.descricao_html) div.append(htmlSeguro(item.descricao_html));
  else div.append(h('pre', { class: 'diff' }, item.descricao));
  return div;
}

function abaVisao() {
  const raiz = h('div', { class: 'visao' });
  raiz.append(
    linhaCampo(t('catalogo.col_titulo'), h('span', {}, item.titulo), { chave: 'titulo', editar: editorTexto('titulo', t('catalogo.col_titulo'), { max: LIMITES.titulo }) }),
    linhaCampo(t('catalogo.resumo'), item.resumo ? h('span', {}, item.resumo) : null, { chave: 'resumo', editar: editorTexto('resumo', t('catalogo.resumo'), { area: true, max: LIMITES.resumo, ajuda: t('catalogo.resumo_ajuda', { max: LIMITES.resumo }) }) }),
    linhaCampo(t('catalogo.descricao'), descricaoHtml(), { chave: 'descricao', editar: editorTexto('descricao', t('catalogo.descricao'), { area: true, max: LIMITES.descricao, ajuda: t('catalogo.descricao_ajuda') }) }),
    linhaCampo(t('catalogo.tags'), (item.tags || []).length ? h('div', { class: 'chips' }, ...item.tags.map((tg) => h('span', { class: 'chip' }, h('span', { class: 'nome' }, tg)))) : null, { chave: 'tags', editar: editorTags() }),
    linhaCampo(t('catalogo.creditos'), item.creditos ? h('span', {}, item.creditos) : null, { chave: 'creditos', editar: editorTexto('creditos', t('catalogo.creditos'), { max: LIMITES.creditos }) }),
    linhaCampo(t('catalogo.termos_de_uso'), item.termos_de_uso ? h('span', {}, item.termos_de_uso) : null, { chave: 'termos_de_uso', editar: editorTexto('termos_de_uso', t('catalogo.termos_de_uso'), { area: true, max: LIMITES.termos }) }),
    linhaCampo(t('catalogo.categorias'), (item.categorias || []).length ? h('div', { class: 'chips' }, ...item.categorias.map((c) => h('span', { class: 'chip' }, h('span', { class: 'nome' }, c.caminho || c.nome || c.id)))) : null, { chave: 'categorias' }),
    linhaCampo(t('catalogo.pasta'), item.pasta ? h('span', {}, (item.pasta.caminho || caminhoDe(item.pasta.id) || [item.pasta.nome]).join(' / ')) : h('span', {}, t('catalogo.raiz')), { chave: 'pasta' }),
    linhaCampo(t('catalogo.origem'), h('span', {}, rotuloOrigem(item.origem), item.url ? h('span', {}, ' · ', h('a', { href: item.url, rel: 'noopener noreferrer', target: '_blank' }, elipse(item.url, 80))) : null), { chave: 'origem' }),
    linhaCampo(t('catalogo.tamanho'), h('span', {}, bytes(item.tamanho_bytes)), { chave: 'tamanho' }),
    linhaCampo(t('campo.criado_em'), h('span', {}, dataHora(item.criado_em), item.criado_por ? ` · ${item.criado_por.login || ''}` : ''), { chave: 'criado' }),
    linhaCampo(t('catalogo.col_modificado'), h('span', {}, dataHora(item.modificado_em), item.modificado_por ? ` · ${item.modificado_por.login || ''}` : '', ` · ${t('catalogo.versao')} ${item.versao_atual ?? 0}`), { chave: 'modificado' }),
    linhaCampo(t('catalogo.usado_por'), h('span', {}, String(item.usado_por ?? 0), ' · ', t('catalogo.criado_a_partir_de'), ' ', String(item.criado_a_partir_de ?? 0)), { chave: 'relacoes' }),
    linhaCampo(t('catalogo.proveniencia'), proveniencia(), { chave: 'proveniencia' }),
  );
  return raiz;
}

/* bloco de proveniência gravado pelo executor de ferramentas (L2-05-a) em dados.procedencia.ferramenta:
   ferramenta, versão, parâmetros, entradas (uuid + versão + sha256), data e autor. Sem o bloco, a linha fica vazia. */
function proveniencia() {
  const p = item.dados && item.dados.procedencia && item.dados.procedencia.ferramenta;
  if (!p || !p.ferramenta) return null;
  const entradas = (p.entradas || []).map((e) => h('li', {},
    h('a', { href: `/conteudo/${e.item_id}` }, e.item_id), ` · ${t('catalogo.versao')} ${e.versao} · sha256 `, h('code', {}, String(e.sha256 || '').slice(0, 16))));
  return h('div', { class: 'proveniencia' },
    h('div', {}, h('strong', {}, `${p.ferramenta} v${p.versao}`), ' · ', dataHora(p.executada_em), p.autor && p.autor.login ? ` · ${p.autor.login}` : '', p.job_id ? ` · job ${p.job_id}` : ''),
    h('div', {}, t('catalogo.proveniencia_parametros'), ' ', h('code', {}, JSON.stringify(p.parametros || {}))),
    entradas.length ? h('ul', { class: 'proveniencia-entradas' }, ...entradas) : null);
}

/* ---------- dados: formulário do JSON Schema ---------- */
function abaDados() {
  const tipo = tipoDe(item.tipo);
  const raiz = h('div', { class: 'dados' });
  if (!tipo || !tipo.esquema) { raiz.append(h('p', { class: 'fraco' }, t('catalogo.dados_sem_esquema')), resumoDados(item.dados)); return raiz; }
  raiz.append(h('p', { class: 'fraco' }, t('catalogo.dados_texto', { tipo: tipo.rotulo, versao: tipo.esquema_versao ?? 1 })));
  if (!item.pode_editar) { raiz.append(resumoDados(item.dados)); return raiz; }
  const f = h('plat-formulario', { class: 'dados-form', id: 'dados-form' });
  const campos = camposDoEsquema(tipo.esquema, item.dados || {});
  f.campos = campos;
  f.botoes = [{ id: 'ok', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const { dados, erros } = dadosDosValores(campos, e.detail.valores, tipo.esquema);
    if (Object.keys(erros).length) { aplicarErros(f, erros); return; }
    f.ocupado = true;
    try {
      const novo = await api.substituir(item.id, { dados, versao_atual: item.versao_atual });
      mudou(novo);
      f.ocupado = false;
      f.mensagem(t('catalogo.salvo'), 'ok');
    } catch (err) {
      f.ocupado = false;
      if (err.codigo === 'dados_invalidos') { aplicarErros(f, errosDoServidor(err.detalhe)); f.mensagem(err.message, 'erro'); } else if (err.codigo === 'versao_conflito') f.mensagem(t('catalogo.versao_conflito'), 'erro'); else f.mensagem(err.message, 'erro');
    }
  });
  raiz.append(f);
  return raiz;
}

/* ---------- configurações ---------- */
function abaConfig() {
  const raiz = h('div', { class: 'config' });
  const pode = !!item.pode_editar;
  // extent
  const extentTexto = h('input', { type: 'text', id: 'config-extent', value: Array.isArray(item.extent) ? item.extent.join(', ') : '', title: 'xmin, ymin, xmax, ymax', 'aria-label': t('catalogo.extent'), disabled: !pode });
  const extentSalvar = h('button', { type: 'button', class: 'pequeno', id: 'config-extent-salvar', disabled: !pode }, t('acao.salvar'));
  const extentLimpar = h('button', { type: 'button', class: 'pequeno', id: 'config-extent-limpar', disabled: !pode || !item.extent }, t('catalogo.extent_limpar'));
  extentSalvar.addEventListener('click', () => { const r = extentDeTexto(extentTexto.value); if (r.erro) { avisoPainel().erro(r.erro); return; } remendar({ extent: r.extent }); });
  extentLimpar.addEventListener('click', () => remendar({ extent: null }));
  raiz.append(linhaCampo(t('catalogo.extent'), h('div', { class: 'chips-editor' }, h('span', { class: 'fraco' }, textoExtent(item.extent), item.extent_origem ? ` · ${t(`catalogo.extent_origem_${item.extent_origem}`)}` : ''), h('div', { class: 'entrada' }, extentTexto, extentSalvar, extentLimpar)), { chave: 'extent' }));
  // proteção
  const prot = h('input', { type: 'checkbox', id: 'config-protegido', disabled: !pode });
  prot.checked = !!item.protegido;
  prot.addEventListener('change', () => remendar({ protegido: prot.checked }));
  raiz.append(linhaCampo(t('catalogo.protecao'), h('div', { class: 'caixa' }, prot, h('label', { for: 'config-protegido' }, t('catalogo.proteger_contra_exclusao')), item.status === 'autoritativo' ? h('span', { class: 'fraco' }, ` · ${t('catalogo.autoritativo_liga_protecao')}`) : null), { chave: 'protegido' }));
  // status
  const st = h('select', { id: 'config-status', disabled: !pode }, h('option', { value: '' }, t('catalogo.status_nenhum')), h('option', { value: 'obsoleto' }, t('catalogo.status_obsoleto')), h('option', { value: 'autoritativo', disabled: !tem('conteudo.editar_tudo') }, t('catalogo.status_autoritativo')));
  st.value = item.status || '';
  st.addEventListener('change', () => remendar({ status: st.value || 'nenhum' }));
  raiz.append(linhaCampo(t('catalogo.status'), h('div', {}, st, h('span', { class: 'ajuda' }, ' ', t('catalogo.status_ajuda'))), { chave: 'status' }));
  // pasta
  const moverBt = h('button', { type: 'button', class: 'pequeno', id: 'config-mover', disabled: !pode }, t('catalogo.mover'));
  moverBt.addEventListener('click', mover);
  raiz.append(linhaCampo(t('catalogo.pasta'), h('div', {}, h('span', {}, item.pasta ? (item.pasta.caminho || caminhoDe(item.pasta.id) || [item.pasta.nome]).join(' / ') : t('catalogo.raiz')), ' ', moverBt), { chave: 'pasta' }));
  // dono
  const transBt = h('button', { type: 'button', class: 'pequeno', id: 'config-transferir', disabled: !(pode && (tem('conteudo.transferir') || tem('conteudo.criar'))) }, t('catalogo.transferir_dono'));
  transBt.addEventListener('click', () => abrirTransferencia([item.id], { aoTerminar: () => recarregar() }));
  raiz.append(linhaCampo(t('catalogo.col_dono'), h('div', {}, h('span', {}, nomeDono(item.dono), item.dono?.login ? ` (${item.dono.login})` : ''), ' ', transBt), { chave: 'dono' }));
  // miniatura
  const arquivo = h('input', { type: 'file', id: 'config-miniatura', accept: 'image/png,image/jpeg,image/gif', disabled: !pode, 'aria-label': t('catalogo.miniatura_enviar') });
  const enviarBt = h('button', { type: 'button', class: 'pequeno', id: 'config-miniatura-enviar', disabled: true }, t('catalogo.miniatura_enviar'));
  arquivo.addEventListener('change', () => { enviarBt.disabled = !arquivo.files?.length; });
  enviarBt.addEventListener('click', async () => {
    const f = arquivo.files?.[0];
    if (!f) return;
    if (f.size > LIMITES.miniaturaBytes) { avisoPainel().erro(t('catalogo.miniatura_grande', { max: bytes(LIMITES.miniaturaBytes) })); return; }
    enviarBt.disabled = true;
    try { const r = await api.miniaturaEnviar(item.id, f); mudou({ miniatura: r.miniatura || api.miniaturaUrl(item.id), modificado_em: new Date().toISOString() }); render(); avisoPainel().ok(t('catalogo.miniatura_salva')); } catch (e) { enviarBt.disabled = false; avisoPainel().erro(e.message); }
  });
  const gerarBt = h('button', { type: 'button', class: 'pequeno', id: 'config-miniatura-gerar', disabled: !pode }, t('catalogo.miniatura_gerar'));
  gerarBt.addEventListener('click', async () => {
    gerarBt.disabled = true;
    try {
      const r = await api.miniaturaGerar(item.id);
      avisoPainel().mostrar(t('catalogo.miniatura_gerando', { job: r.job_id || '' }), 'info');
      const antes = item.miniatura ? String(item.miniatura) : '';
      const t0 = Date.now();
      const espera = async () => {
        if (Date.now() - t0 > 60000) { avisoPainel().mostrar(t('catalogo.miniatura_demora'), 'atencao'); return; }
        try { const novo = await api.obter(item.id); if (novo.miniatura && (novo.miniatura !== antes || novo.modificado_em !== item.modificado_em)) { mudou(novo); render(); avisoPainel().ok(t('catalogo.miniatura_salva')); return; } } catch { /* tenta de novo */ }
        setTimeout(espera, 2000);
      };
      setTimeout(espera, 2000);
    } catch (e) { gerarBt.disabled = false; avisoPainel().erro(e.codigo === 'tipo_sem_gerador' ? t('catalogo.tipo_sem_gerador') : e.message); }
  });
  const apagarMini = h('button', { type: 'button', class: 'pequeno perigo', id: 'config-miniatura-apagar', disabled: !pode || !item.miniatura }, t('catalogo.miniatura_apagar'));
  apagarMini.addEventListener('click', async () => { try { await api.miniaturaApagar(item.id); mudou({ miniatura: null }); render(); } catch (e) { avisoPainel().erro(e.message); } });
  raiz.append(linhaCampo(t('catalogo.miniatura'), h('div', { class: 'chips-editor' }, h('span', { class: 'fraco' }, t('catalogo.miniatura_ajuda')), h('div', { class: 'entrada' }, arquivo, enviarBt), h('div', { class: 'entrada' }, gerarBt, apagarMini)), { chave: 'miniatura' }));
  return raiz;
}

function abaCompartilhamento() {
  const raiz = h('div', { class: 'compartilhamento' });
  raiz.append(linhaCampo(t('catalogo.nivel_acesso'), h('span', {}, rotuloAcesso(item)), { chave: 'acesso' }), linhaCampo(t('catalogo.links'), h('span', {}, String(item.links_ativos ?? 0)), { chave: 'links' }));
  if (item.pode_compartilhar) { const b = botaoCompartilhar(); b.classList.add('primario'); raiz.append(h('div', { class: 'botoes' }, b)); } else raiz.append(h('p', { class: 'fraco' }, t('catalogo.sem_permissao_compartilhar')));
  return raiz;
}

/* ---------- ações ---------- */
async function remendar(parcial) {
  try { const novo = await api.editar(item.id, parcial); mudou(novo); render(); avisoPainel().ok(t('catalogo.salvo')); } catch (e) { render(); avisoPainel().erro(e.message); }
}

async function mover() {
  const f = h('plat-formulario');
  const sel = seletorPasta(item.pasta?.id || '');
  f.campos = [{ nome: 'pasta_id', rotulo: t('catalogo.pasta'), tipo: 'select', opcoes: [...sel.options].map((o) => ({ valor: o.value, rotulo: o.textContent })), padrao: item.pasta?.id || '' }];
  f.botoes = [{ id: 'ok', rotulo: t('catalogo.mover'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  const v = await pedir(t('catalogo.mover'), f);
  if (!v) return;
  try { const novo = await api.mover(item.id, v.pasta_id || null); mudou(novo); render(); avisoPainel().ok(t('catalogo.movido')); aoMudou(novo, { pasta: true }); } catch (e) { avisoPainel().erro(e.message); }
}

async function apagar() {
  let ordem = null;
  try { ordem = await api.ordemDeExclusao(item.id); } catch { ordem = null; }
  const dependentes = (ordem?.ordem || []).filter((x) => x.id !== item.id);
  const ocultos = ordem?.ocultos || 0;
  const corpo = h('div', {});
  if (item.protegido) { corpo.append(h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('catalogo.apagar_protegido'))); }
  corpo.append(h('p', {}, t('catalogo.apagar_confirma', { titulo: elipse(item.titulo, 60) })), h('p', { class: 'fraco' }, t('catalogo.apagar_obsoleto_dica')));
  if (dependentes.length || ocultos) {
    corpo.append(h('p', {}, t('catalogo.apagar_dependentes', { n: dependentes.length })), h('ul', { class: 'lista-relacoes' }, ...dependentes.map((x) => h('li', {}, elipse(x.titulo, 60), h('span', { class: 'fraco' }, rotuloTipo(x.tipo)), x.pode_editar === false ? marcador(t('catalogo.dependencia_sem_edicao'), 'falha') : null)), ocultos ? h('li', { class: 'oculto' }, t('catalogo.dependentes_ocultos', { n: ocultos })) : null));
  }
  const d = el('painel-editar') || document.body.appendChild(h('plat-dialogo', { id: 'painel-editar' }));
  const botoes = [{ id: 'cancelar', rotulo: t('acao.cancelar'), classe: dependentes.length ? 'primario' : '' }];
  if (dependentes.length) { if (!ocultos && dependentes.every((x) => x.pode_editar !== false)) botoes.push({ id: 'cascata', rotulo: t('catalogo.apagar_cascata', { n: dependentes.length }), classe: 'perigo' }); } else if (!item.protegido) botoes.push({ id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' });
  const r = await d.abrir({ titulo: t('acao.apagar'), corpo, botoes });
  if (r !== 'apagar' && r !== 'cascata') return;
  try {
    await api.apagar(item.id, r === 'cascata');
    const apagado = item;
    removerItemDaLista(apagado.id);
    for (const x of dependentes) removerItemDaLista(x.id);
    el('aviso').ok(t('catalogo.apagado', { titulo: elipse(apagado.titulo, 60) }));
    fechar();
    aoMudou(apagado, { apagado: true });
  } catch (e) {
    if (e.codigo === 'item_protegido') avisoPainel().erro(t('catalogo.apagar_protegido'));
    else if (e.codigo === 'possui_dependentes') avisoPainel().erro(t('catalogo.apagar_dependentes', { n: (e.detalhe?.ordem || []).length }));
    else avisoPainel().erro(e.message);
  }
}
