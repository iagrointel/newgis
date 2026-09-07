/* plat · catálogo — aba Metadado do painel do item (item L0-09-b-editor-iso-mgb): editor do Perfil MGB 2.0 da
   INDE em duas subabas ('essencial' e 'completo'), botão Validar (lista de campos que faltam, sem gravar) e
   Salvar (grava; nunca bloqueia por campo essencial faltando, só por estrutura inválida — 422 do servidor).
   Título/resumo/palavras-chave/créditos ficam sincronizados com a Visão geral (mesma coluna do item, ver
   app/catalogo/metadado_mgb.py); o resto (contato, licença, extensão declarada, sistema de referência,
   manutenção, formato de distribuição) é a parte própria do metadado. Linhagem é só leitura (computada). */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import * as api from './api.js';

function campoTexto(id, rotulo, valor, { tipo = 'text', ajuda } = {}) {
  const entrada = h('input', { type: tipo, id, value: valor ?? '' });
  return h('div', { class: 'campo-linha' }, h('label', { class: 'rotulo', for: id }, rotulo), h('div', { class: 'valor' }, entrada, ajuda ? h('span', { class: 'ajuda' }, ajuda) : null));
}

function campoSelect(id, rotulo, valor, opcoes) {
  const sel = h('select', { id }, h('option', { value: '' }, '—'), ...opcoes.map((o) => h('option', { value: o, selected: o === valor }, o)));
  return { el: h('div', { class: 'campo-linha' }, h('label', { class: 'rotulo', for: id }, rotulo), h('div', { class: 'valor' }, sel)), sel };
}

const PAPEIS = ['resourceProvider', 'custodian', 'owner', 'user', 'distributor', 'originator', 'pointOfContact', 'principalInvestigator', 'processor', 'publisher', 'author'];
const FREQUENCIAS = ['continual', 'daily', 'weekly', 'fortnightly', 'monthly', 'quarterly', 'biannually', 'annually', 'asNeeded', 'irregular', 'notPlanned', 'unknown'];

function lerFormulario(raiz) {
  const v = (id) => raiz.querySelector(`#${id}`)?.value?.trim() || undefined;
  const metadado = {};
  const contato = {};
  if (v('mgb-contato-org')) contato.organizacao = v('mgb-contato-org');
  if (v('mgb-contato-ind')) contato.individuo = v('mgb-contato-ind');
  if (v('mgb-contato-email')) contato.email = v('mgb-contato-email');
  if (v('mgb-contato-papel')) contato.papel = v('mgb-contato-papel');
  if (Object.keys(contato).length) metadado.contato = contato;
  const restricoes = {};
  if (v('mgb-licenca')) restricoes.licenca = v('mgb-licenca');
  restricoes.uso_condicionado = !!raiz.querySelector('#mgb-uso-condicionado')?.checked;
  metadado.restricoes = restricoes;
  const extensao = {};
  const temporal = {};
  if (v('mgb-temporal-inicio')) temporal.inicio = v('mgb-temporal-inicio');
  if (v('mgb-temporal-fim')) temporal.fim = v('mgb-temporal-fim');
  if (Object.keys(temporal).length) extensao.temporal = temporal;
  const xmin = v('mgb-esp-xmin'), ymin = v('mgb-esp-ymin'), xmax = v('mgb-esp-xmax'), ymax = v('mgb-esp-ymax');
  if (xmin && ymin && xmax && ymax) extensao.espacial = { xmin: Number(xmin), ymin: Number(ymin), xmax: Number(xmax), ymax: Number(ymax) };
  if (Object.keys(extensao).length) metadado.extensao = extensao;
  const sr = {};
  if (v('mgb-sr-codigo')) sr.codigo = v('mgb-sr-codigo');
  if (v('mgb-sr-codespace')) sr.codespace = v('mgb-sr-codespace');
  if (Object.keys(sr).length) metadado.sistema_referencia = sr;
  const man = {};
  if (v('mgb-manutencao-freq')) man.frequencia = v('mgb-manutencao-freq');
  if (v('mgb-manutencao-prox')) man.proxima_atualizacao = v('mgb-manutencao-prox');
  if (Object.keys(man).length) metadado.manutencao = man;
  if (v('mgb-dist-formato')) metadado.distribuicao = { formato: v('mgb-dist-formato') };
  const item = {};
  if (v('mgb-item-resumo') !== undefined) item.resumo = v('mgb-item-resumo') || null;
  if (v('mgb-item-tags') !== undefined) item.tags = (v('mgb-item-tags') || '').split(',').map((s) => s.trim()).filter(Boolean);
  return { item, metadado };
}

function listaFaltantes(faltantes) {
  if (!faltantes.length) return h('p', { class: 'ok' }, t('catalogo.metadado_completo_ok'));
  return h('div', { class: 'faltantes' }, h('p', {}, t('catalogo.metadado_faltam', { n: faltantes.length })), h('ul', {}, ...faltantes.map((f) => h('li', {}, f.rotulo || f.campo))));
}

/* montar() é síncrono (mesmo padrão de item_versoes.js/item_relacoes.js): devolve a raiz na hora, com um
   marcador de carregamento, e a preenche quando a leitura assíncrona chega — a aba nunca fica pendurada num
   Promise dentro do dispatch de render() do painel do item. */
export function montar(item, { aoMudou } = {}) {
  const raiz = h('div', { class: 'metadado-mgb' });
  const carregando = h('p', { class: 'fraco' }, t('catalogo.carregando'));
  raiz.append(carregando);
  api.metadadoObter(item.id).then(
    (leitura) => { limpar(raiz); raiz.append(preencher(item, leitura, aoMudou)); },
    (e) => { limpar(raiz); raiz.append(h('p', { class: 'erro' }, e.message)); },
  );
  return raiz;
}

function preencher(item, leitura, aoMudou) {
  const raiz = h('div', { class: 'metadado-mgb-corpo' });
  const aviso = h('plat-aviso', { id: 'mgb-aviso' });
  const corpoFaltantes = h('div', { id: 'mgb-faltantes' });
  raiz.append(aviso, corpoFaltantes);
  const c = leitura.campos;

  raiz.append(h('p', { class: 'fraco' }, `${t('catalogo.metadado_estilo')}: ${leitura.perfil}`));

  // ---- essencial: título/resumo/palavras-chave (sincronizados) + contato/licença/sistema de referência
  const form = h('form', { id: 'mgb-form' });
  form.append(
    h('h3', {}, t('catalogo.metadado_subaba_essencial')),
    campoTexto('mgb-item-resumo', t('catalogo.resumo'), c.identificacao.resumo),
    campoTexto('mgb-item-tags', t('catalogo.tags'), (c.identificacao.palavras_chave || []).join(', '), { ajuda: t('catalogo.tags_ajuda_editor', { max: 50 }) }),
    campoTexto('mgb-contato-org', t('catalogo.metadado_organizacao'), c.contato.organizacao),
    campoTexto('mgb-contato-email', t('catalogo.metadado_email'), c.contato.email, { tipo: 'email' }),
    campoTexto('mgb-licenca', t('catalogo.metadado_licenca'), c.restricoes.licenca),
    h('div', { class: 'campo-linha' }, h('span', { class: 'rotulo' }, t('catalogo.metadado_espacial'))),
    h('div', { class: 'linha-4' },
      campoTexto('mgb-esp-xmin', 'xmin', c.extensao.espacial?.xmin),
      campoTexto('mgb-esp-ymin', 'ymin', c.extensao.espacial?.ymin),
      campoTexto('mgb-esp-xmax', 'xmax', c.extensao.espacial?.xmax),
      campoTexto('mgb-esp-ymax', 'ymax', c.extensao.espacial?.ymax)),
    campoTexto('mgb-sr-codigo', t('catalogo.metadado_sistema_codigo'), c.sistema_referencia.codigo || '4326'),
    campoTexto('mgb-sr-codespace', t('catalogo.metadado_sistema_codespace'), c.sistema_referencia.codespace || 'EPSG'),
  );

  // ---- completo: o resto do perfil
  const completo = h('div', { id: 'mgb-completo' });
  completo.append(h('h3', {}, t('catalogo.metadado_subaba_completo')));
  completo.append(campoTexto('mgb-contato-ind', t('catalogo.metadado_individuo'), c.contato.individuo));
  const papel = campoSelect('mgb-contato-papel', t('catalogo.metadado_papel'), c.contato.papel, PAPEIS);
  completo.append(papel.el);
  const usoCond = h('input', { type: 'checkbox', id: 'mgb-uso-condicionado' });
  usoCond.checked = !!c.restricoes.uso_condicionado;
  completo.append(h('div', { class: 'campo-linha' }, h('label', { class: 'rotulo', for: 'mgb-uso-condicionado' }, t('catalogo.metadado_uso_condicionado')), usoCond));
  completo.append(campoTexto('mgb-temporal-inicio', t('catalogo.metadado_temporal_inicio'), c.extensao.temporal?.inicio, { tipo: 'date' }));
  completo.append(campoTexto('mgb-temporal-fim', t('catalogo.metadado_temporal_fim'), c.extensao.temporal?.fim, { tipo: 'date' }));
  const freq = campoSelect('mgb-manutencao-freq', t('catalogo.metadado_frequencia'), c.manutencao.frequencia, FREQUENCIAS);
  completo.append(freq.el);
  completo.append(campoTexto('mgb-manutencao-prox', t('catalogo.metadado_proxima_atualizacao'), c.manutencao.proxima_atualizacao, { tipo: 'date' }));
  completo.append(campoTexto('mgb-dist-formato', t('catalogo.metadado_formato_distribuicao'), c.distribuicao.formato));
  form.append(completo);

  // ---- linhagem: só leitura
  const linhagem = c.qualidade_linhagem || {};
  const blocoLinhagem = h('div', { class: 'linhagem' }, h('h3', {}, t('catalogo.metadado_linhagem')));
  if (linhagem.declaracao || (linhagem.processos || []).length) {
    if (linhagem.declaracao) blocoLinhagem.append(h('p', {}, linhagem.declaracao));
    if ((linhagem.processos || []).length) blocoLinhagem.append(h('ul', {}, ...linhagem.processos.map((p) => h('li', {}, `${p.em} · ${p.descricao}`))));
  } else {
    blocoLinhagem.append(h('p', { class: 'fraco' }, t('catalogo.metadado_sem_linhagem')));
  }
  form.append(blocoLinhagem);

  corpoFaltantes.append(listaFaltantes(leitura.faltantes_essencial || []));
  if ((leitura.avisos || []).length) {
    const av = h('plat-aviso', { 'data-tipo': 'atencao' });
    av.textContent = `${t('catalogo.metadado_avisos')}: ${leitura.avisos.map((a) => a.aviso).join('; ')}`;
    corpoFaltantes.append(av);
  }

  const botoes = h('div', { class: 'botoes' });
  const validarBt = h('button', { type: 'button', class: 'pequeno', id: 'mgb-validar' }, t('catalogo.metadado_validar'));
  const salvarBt = h('button', { type: 'button', class: 'primario', id: 'mgb-salvar', disabled: !item.pode_editar }, t('catalogo.metadado_salvar'));
  validarBt.addEventListener('click', async () => {
    const { item: itemParcial, metadado } = lerFormulario(form);
    try {
      const r = await api.metadadoValidar(item.id, { item: itemParcial, metadado });
      limpar(corpoFaltantes);
      corpoFaltantes.append(listaFaltantes(r.faltantes_essencial || []));
    } catch (e) {
      aviso.erro(e.message);
    }
  });
  salvarBt.addEventListener('click', async () => {
    const { item: itemParcial, metadado } = lerFormulario(form);
    salvarBt.disabled = true;
    try {
      const r = await api.metadadoSalvar(item.id, { item: itemParcial, metadado });
      aviso.ok(t('catalogo.metadado_salvo'));
      if (typeof aoMudou === 'function') aoMudou(r.item);
      limpar(corpoFaltantes);
      corpoFaltantes.append(listaFaltantes([]));
      if ((r.avisos || []).length) {
        const av = h('plat-aviso', { 'data-tipo': 'atencao' });
        av.textContent = `${t('catalogo.metadado_avisos')}: ${r.avisos.map((a) => a.aviso).join('; ')}`;
        corpoFaltantes.append(av);
      }
    } catch (e) {
      aviso.erro(e.message);
    } finally {
      salvarBt.disabled = !item.pode_editar;
    }
  });
  botoes.append(validarBt, salvarBt);
  form.append(botoes);
  raiz.append(form);
  return raiz;
}
