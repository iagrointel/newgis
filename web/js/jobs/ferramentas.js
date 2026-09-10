/* plat · ferramentas — tela /ferramentas (item UX-09): o catálogo de ferramentas é o REGISTRO DE TIPOS DE TAREFA que
   o backend já publica (GET /api/jobs/tipos, ADR 0003 seção 9): nome, descrição, custo (memória, tempo, pesado,
   executor), perfil mínimo e o ESQUEMA DE PARÂMETROS (JSON Schema gerado do modelo pydantic do tipo). Daí nasce o
   formulário — campo por propriedade, com tipo, limites, enum, obrigatório e ajuda — sem uma linha de formulário
   escrita à mão por ferramenta. Executar = POST /api/jobs {tipo, parametros}; o progresso vem ao vivo pelo mesmo
   canal da tela Tarefas (SSE com reserva por polling, web/js/jobs/eventos.js); o resultado com `item_id` vira o
   caminho para o catálogo (e dali para o mapa). Erro 422 do servidor volta campo a campo (loc do pydantic);
   parâmetro fora do limite é recusado no navegador com o motivo no campo (refutação do item: nunca 422 cru).
   O que NÃO está aqui: as ferramentas GP no vocabulário Esri (item L2-05-a) — não existem no tronco; quando
   entrarem, o manifesto delas cabe no mesmo gerador de formulário. */
import { obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t, formatarNumero } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import * as api from './api.js';
import { assinar, cancelarAssinatura } from './eventos.js';
import { FINAIS, dataHora, estado as fmtEstado, hora } from './formato.js';

function el(id) { return document.getElementById(id); }
const s = { tipos: [], q: '', diagnostico: false, tipo: null, job: null, form: null, conversores: {}, validadores: {}, linhasLog: new Set() };

await carregarIdioma();
const usuario = await exigirSessao({ privilegio: 'jobs.executar' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/ferramentas' });
  cabecalho(t('ferramentas.titulo'));
  const busca = el('catalogo-busca');
  busca.querySelector('label').textContent = t('ferramentas.buscar');
  busca.querySelector('input').setAttribute('aria-label', t('ferramentas.buscar'));
  busca.addEventListener('buscar', (ev) => { s.q = ev.detail.q; desenharCatalogo(); });
  el('catalogo-diagnostico').addEventListener('change', (ev) => { s.diagnostico = ev.target.checked; desenharCatalogo(); });
  el('catalogo-estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'tentar') carregarTipos();
    if (ev.detail.id === 'limpar') { s.q = ''; busca.valor = ''; s.diagnostico = true; el('catalogo-diagnostico').checked = true; desenharCatalogo(); }
  });
  el('ferramenta-fechar').addEventListener('click', fecharFerramenta);
  el('ferramenta-form').addEventListener('enviar', (ev) => executar(ev.detail.valores));
  el('execucao-cancelar').addEventListener('click', cancelarJob);
  await carregarTipos();
  const pedido = new URLSearchParams(location.search).get('tipo');
  if (pedido) abrirFerramenta(pedido);
}

/* ---------------------------------------------------------------- catálogo */
async function carregarTipos() {
  const estado = el('catalogo-estado');
  estado.carregando(t('ferramentas.carregando'));
  el('catalogo-lista').hidden = true;
  try {
    const r = await api.tipos();
    s.tipos = (Array.isArray(r) ? r : (r.itens || [])).filter((tp) => !tp.somente_sistema);
  } catch (e) {
    estado.erro({ status: e.status, json: { mensagem: e.message, req_id: e.reqId } });
    return;
  }
  desenharCatalogo();
}

// declarações de função (içadas): o módulo executa `await iniciar()` no topo, antes de qualquer `const` abaixo
function ehDiagnostico(tp) { return tp.nome.startsWith('prova.') || tp.nome.startsWith('jobs.'); }
function grupoDe(tp) { return tp.nome.split('.')[0]; }
function podeRodar(tp) { return !tp.perfil_minimo || tem('jobs.executar'); }

function visiveis() {
  const q = s.q.toLocaleLowerCase();
  return s.tipos.filter((tp) => (s.diagnostico || !ehDiagnostico(tp)) && (!q || `${tp.nome} ${tp.descricao || ''}`.toLocaleLowerCase().includes(q)));
}

function custoDe(tp) {
  const partes = [];
  if (tp.memoria_mb) partes.push(t('ferramentas.custo_memoria', { mb: formatarNumero(tp.memoria_mb) }));
  if (tp.timeout_s) partes.push(tp.timeout_s < 60 ? t('ferramentas.custo_tempo_s', { s: formatarNumero(tp.timeout_s) }) : t('ferramentas.custo_tempo', { min: formatarNumero(Math.round(tp.timeout_s / 60)) }));
  if (tp.pesado) partes.push(t('ferramentas.custo_pesado'));
  if (tp.executor && tp.executor !== 'local') partes.push(t('ferramentas.custo_executor', { executor: tp.executor }));
  if (tp.perfil_minimo) partes.push(t('ferramentas.perfil_minimo', { perfil: t(`perfil.${tp.perfil_minimo}`) }));
  return partes.join(' · ');
}

function desenharCatalogo() {
  const estado = el('catalogo-estado');
  const lista = el('catalogo-lista');
  limpar(lista);
  const itens = visiveis();
  el('catalogo-total').textContent = `(${itens.length}/${s.tipos.length})`;
  if (!s.tipos.length) { lista.hidden = true; estado.vazio(t('ferramentas.vazio')); return; }
  if (!itens.length) { lista.hidden = true; estado.vazio(t('ferramentas.vazio_filtro'), [{ id: 'limpar', rotulo: t('ferramentas.limpar_filtros') }]); return; }
  estado.limpar();
  lista.hidden = false;
  const grupos = new Map();
  for (const tp of itens) { if (!grupos.has(grupoDe(tp))) grupos.set(grupoDe(tp), []); grupos.get(grupoDe(tp)).push(tp); }
  for (const [grupo, tps] of grupos) {
    const sec = h('section', { class: 'ferramentas-grupo', 'aria-label': grupo });
    sec.append(h('h3', {}, t(`ferramentas.grupo_${grupo}`) === `ferramentas.grupo_${grupo}` ? grupo : t(`ferramentas.grupo_${grupo}`)));
    for (const tp of tps) {
      const bt = h('button', { type: 'button', class: 'primario pequeno', dataset: { abrir: tp.nome } }, t('ferramentas.abrir'));
      bt.addEventListener('click', () => abrirFerramenta(tp.nome));
      const n = Object.keys((tp.parametros_schema || {}).properties || {}).length;
      sec.append(h('article', { class: `ferramenta-cartao${s.tipo && s.tipo.nome === tp.nome ? ' selecionada' : ''}`, dataset: { tipo: tp.nome } },
        h('div', { class: 'ferramenta-topo' }, h('span', { class: 'mono' }, tp.nome), ehDiagnostico(tp) ? h('span', { class: 'marcador info' }, t('ferramentas.diagnostico')) : null),
        h('p', {}, tp.descricao || ''),
        h('p', { class: 'ajuda' }, `${custoDe(tp)}${n ? ` · ${t('ferramentas.n_parametros', { n })}` : ` · ${t('ferramentas.sem_parametros')}`}`),
        h('div', { class: 'botoes' }, bt)));
    }
    lista.append(sec);
  }
}

/* ---------------------------------------------------------------- formulário gerado do esquema */
function ehNulo(esq) { return Array.isArray(esq.anyOf) && esq.anyOf.some((x) => x.type === 'null'); }
function esquemaBase(esq) {
  if (Array.isArray(esq.anyOf)) return { ...esq, ...(esq.anyOf.find((x) => x.type !== 'null') || {}) };
  return esq;
}

/* JSON Schema (pydantic) -> definição de campo do <plat-formulario>; devolve também o conversor de valor */
function campoDe(nome, esqBruto, obrigatorio) {
  const esq = esquemaBase(esqBruto);
  const rotulo = nome; // o nome do parâmetro é o que a API recebe; o título do pydantic é derivado dele
  const ajuda = [esq.description, limitesTexto(esq)].filter(Boolean).join(' · ');
  const base = { nome, rotulo, obrigatorio, ajuda };
  if (Array.isArray(esq.enum)) {
    return { def: { ...base, tipo: 'select', padrao: esq.default ?? esq.enum[0], opcoes: [...(obrigatorio ? [] : [{ valor: '', rotulo: '—' }]), ...esq.enum.map((v) => ({ valor: String(v), rotulo: String(v) }))] }, converter: (v) => (v === '' ? null : v) };
  }
  if (esq.type === 'boolean') return { def: { ...base, tipo: 'caixa', padrao: !!esq.default }, converter: (v) => !!v };
  if (esq.type === 'integer' || esq.type === 'number') {
    const atributos = { step: esq.type === 'integer' ? '1' : 'any' };
    if (esq.minimum !== undefined) atributos.min = String(esq.minimum);
    if (esq.maximum !== undefined) atributos.max = String(esq.maximum);
    return { def: { ...base, tipo: 'numero', padrao: esq.default ?? '', atributos }, converter: (v) => (v === null || v === '' ? null : Number(v)), validar: (v) => validarNumero(esq, v, obrigatorio) };
  }
  if (esq.type === 'array') {
    const item = esquemaBase(esq.items || {});
    return { def: { ...base, tipo: 'lista', padrao: Array.isArray(esq.default) ? esq.default.map(String) : [], linhas: 3, ajuda: `${ajuda ? `${ajuda} · ` : ''}${t('ferramentas.lista_ajuda')}` }, converter: (v) => (v.length ? v.map((x) => (item.type === 'integer' || item.type === 'number' ? Number(x) : x)) : null), validar: (v) => (esq.maxItems !== undefined && v.length > esq.maxItems ? t('ferramentas.lista_max', { n: esq.maxItems }) : null) };
  }
  if (esq.type === 'object' || esq.additionalProperties) {
    return { def: { ...base, tipo: 'area', padrao: esq.default ? JSON.stringify(esq.default, null, 1) : '', linhas: 3, ajuda: `${ajuda ? `${ajuda} · ` : ''}${t('ferramentas.json_ajuda')}` }, converter: (v) => (v.trim() ? JSON.parse(v) : null), validar: (v) => { if (!v.trim()) return null; try { const o = JSON.parse(v); return o && typeof o === 'object' && !Array.isArray(o) ? null : t('ferramentas.json_objeto'); } catch { return t('ferramentas.json_invalido'); } } };
  }
  const atributos = { autocomplete: 'off' };
  if (esq.maxLength) atributos.maxlength = String(esq.maxLength);
  if (esq.format === 'uuid') atributos.pattern = '^[0-9a-fA-F-]{36}$';
  if (esq.format === 'date-time') return { def: { ...base, tipo: 'texto', padrao: '', atributos, ajuda: `${ajuda ? `${ajuda} · ` : ''}${t('ferramentas.data_ajuda')}` }, converter: (v) => (v ? new Date(v).toISOString() : null), validar: (v) => (v && Number.isNaN(new Date(v).getTime()) ? t('ferramentas.data_invalida') : null) };
  return {
    def: { ...base, tipo: 'texto', padrao: esq.default ?? '', atributos, ajuda: esq.format === 'uuid' ? `${ajuda ? `${ajuda} · ` : ''}${t('ferramentas.uuid_ajuda')}` : ajuda },
    converter: (v) => (v === '' ? null : v),
    validar: (v) => {
      if (esq.format === 'uuid' && v && !/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(v)) return t('ferramentas.uuid_invalido');
      if (esq.minLength && v && v.length < esq.minLength) return t('ferramentas.texto_min', { n: esq.minLength });
      if (esq.pattern && v && !new RegExp(esq.pattern).test(v)) return t('ferramentas.texto_padrao', { padrao: esq.pattern });
      return null;
    },
  };
}

function limitesTexto(esq) {
  const p = [];
  if (esq.minimum !== undefined) p.push(`≥ ${esq.minimum}`);
  if (esq.maximum !== undefined) p.push(`≤ ${esq.maximum}`);
  if (esq.default !== undefined && esq.default !== null && typeof esq.default !== 'object') p.push(t('ferramentas.padrao', { valor: String(esq.default) }));
  return p.join(' · ');
}

function validarNumero(esq, v, obrigatorio) {
  if (v === null || v === '') return obrigatorio ? t('form.obrigatorio') : null;
  const n = Number(v);
  if (Number.isNaN(n)) return t('ferramentas.numero_invalido');
  if (esq.type === 'integer' && !Number.isInteger(n)) return t('ferramentas.inteiro');
  if (esq.minimum !== undefined && n < esq.minimum) return t('ferramentas.minimo', { n: esq.minimum });
  if (esq.maximum !== undefined && n > esq.maximum) return t('ferramentas.maximo', { n: esq.maximum });
  return null;
}

function abrirFerramenta(nome) {
  const tp = s.tipos.find((x) => x.nome === nome);
  const sec = el('ferramenta');
  const estado = el('ferramenta-estado');
  if (!tp) { sec.hidden = false; estado.mostrar({ tipo: 'vazio', titulo: t('ferramentas.inexistente_titulo'), texto: t('ferramentas.inexistente', { nome }) }); el('ferramenta-form').campos = []; return; }
  s.tipo = tp;
  history.replaceState({}, '', `/ferramentas?tipo=${encodeURIComponent(nome)}`);
  // ferramenta de diagnóstico aberta pela URL: liga o filtro para o cartão selecionado aparecer no catálogo
  if (ehDiagnostico(tp) && !s.diagnostico) { s.diagnostico = true; el('catalogo-diagnostico').checked = true; }
  desenharCatalogo();
  sec.hidden = false;
  document.body.dataset.detalhe = '1';
  el('ferramenta-nome').textContent = tp.nome;
  el('ferramenta-descricao').textContent = tp.descricao || '';
  el('ferramenta-custo').textContent = custoDe(tp);
  el('execucao').hidden = true;
  estado.limpar();
  const esquema = tp.parametros_schema || {};
  const obrig = new Set(esquema.required || []);
  const campos = []; const conversores = {}; const validadores = {};
  for (const [pn, pe] of Object.entries(esquema.properties || {})) {
    const c = campoDe(pn, pe, obrig.has(pn) && !ehNulo(pe));
    campos.push(c.def); conversores[pn] = c.converter; if (c.validar) validadores[pn] = c.validar;
  }
  const f = el('ferramenta-form');
  s.form = f;
  f.campos = campos;
  f.botoes = podeRodar(tp) ? [{ id: 'executar', rotulo: t('ferramentas.executar'), tipo: 'submit' }] : [];
  if (!campos.length) f.mensagem(t('ferramentas.sem_parametros_texto'), 'info');
  if (!podeRodar(tp)) estado.negado(t('ferramentas.negado', { perfil: t(`perfil.${tp.perfil_minimo}`) }));
  s.conversores = conversores;
  s.validadores = validadores;
  sec.scrollIntoView({ block: 'nearest' });
  f.focarPrimeiro();
}

function fecharFerramenta() {
  s.tipo = null;
  if (s.job && !FINAIS.has(s.job.estado)) cancelarAssinatura(s.job.id, ouvinte);
  el('ferramenta').hidden = true;
  delete document.body.dataset.detalhe;
  history.replaceState({}, '', '/ferramentas');
  desenharCatalogo();
}

/* ---------------------------------------------------------------- execução */
async function executar(valores) {
  const f = s.form; const tp = s.tipo; const { conversores, validadores } = s;
  f.limparErros();
  const parametros = {}; let erros = 0;
  for (const [nome, v] of Object.entries(valores)) {
    const motivo = validadores[nome] ? validadores[nome](v) : null;
    if (motivo) { f.erro(nome, motivo); erros += 1; continue; }
    try {
      const conv = conversores[nome] ? conversores[nome](v) : v;
      if (conv !== null && conv !== undefined) parametros[nome] = conv;
    } catch (e) { f.erro(nome, e.message); erros += 1; }
  }
  if (erros) { f.querySelector('[aria-invalid="true"]')?.focus(); return; }
  f.ocupado = true;
  let job;
  try {
    job = await api.criar(tp.nome, parametros);
  } catch (e) {
    f.ocupado = false;
    if (e.status === 422 && Array.isArray(e.detalhe)) {
      // detalhe do serviço de jobs: [{campo, mensagem}] (app/jobs/servico.py); o campo pode vir "a.b" em aninhados
      for (const d of e.detalhe) {
        const campo = String(d.campo || '').split('.')[0];
        const msg = d.mensagem || JSON.stringify(d);
        if (campo && f.campo(campo)) f.erro(campo, msg); else f.mensagem(campo ? `${campo}: ${msg}` : msg, 'erro');
      }
      f.querySelector('[aria-invalid="true"]')?.focus();
    } else if (e.status === 422 && e.detalhe && typeof e.detalhe === 'object') {
      for (const [campo, msg] of Object.entries(e.detalhe)) { if (f.campo(campo)) f.erro(campo, String(msg)); else f.mensagem(`${campo}: ${msg}`, 'erro'); }
    } else f.mensagem(e.status === 403 ? t('ferramentas.negado_executar') : t('ferramentas.erro_criar', { status: e.status || t('tarefas.rede'), erro: e.message }), 'erro');
    return;
  }
  f.ocupado = false;
  mostrarJob(job);
}

function mostrarJob(job) {
  if (s.job && s.job.id !== job.id && !FINAIS.has(s.job.estado)) cancelarAssinatura(s.job.id, ouvinte);
  s.job = job;
  s.linhasLog = new Set();
  limpar(el('execucao-log'));
  el('execucao').hidden = false;
  el('execucao-tarefa').href = `/tarefas/${encodeURIComponent(job.id)}`;
  pintarJob(job);
  if (!FINAIS.has(job.estado)) assinar(job.id, ouvinte);
  el('execucao').scrollIntoView({ block: 'nearest' });
}

function pintarJob(job) {
  const e = fmtEstado(job.estado);
  const marc = el('execucao-estado');
  marc.className = `estado-job ${e.classe}`;
  limpar(marc).append(h('span', { class: 'simbolo', 'aria-hidden': 'true' }, e.simbolo), ' ', e.rotulo);
  const pct = job.estado === 'concluido' ? 100 : Math.max(0, Math.min(100, Number(job.progresso) || 0));
  el('execucao-preenchido').style.width = `${pct}%`;
  el('execucao-valor').textContent = `${pct} %`;
  el('execucao-progresso').setAttribute('aria-valuenow', String(pct));
  el('execucao-mensagem').textContent = job.mensagem || (job.estado === 'pendente' ? t('tarefas.na_fila') : '');
  const erro = el('execucao-erro');
  erro.hidden = !job.erro; erro.textContent = job.erro ? t('tarefas.det_erro', { erro: job.erro }) : '';
  el('execucao-cancelar').hidden = FINAIS.has(job.estado);
  el('execucao-cancelar').disabled = !!job.cancelar_solicitado;
  const item = job.resultado && job.resultado.item_id;
  const link = el('execucao-item');
  link.hidden = !item;
  if (item) link.href = `/conteudo/${encodeURIComponent(item)}`;
}

function ouvinte(ev) {
  if (!s.job || ev.id !== s.job.id) return;
  if ((ev.tipo === 'estado' || ev.tipo === 'fim') && ev.dados) { s.job = ev.dados; pintarJob(ev.dados); }
  if (ev.tipo === 'log' && ev.dados && ev.dados.id != null && !s.linhasLog.has(ev.dados.id)) {
    s.linhasLog.add(ev.dados.id);
    const l = ev.dados;
    el('execucao-log').append(h('li', { class: `n-${l.nivel}` }, h('time', { datetime: l.em || '', title: dataHora(l.em) }, hora(l.em)), h('b', {}, l.nivel), h('span', {}, l.mensagem)));
  }
  if (ev.tipo === 'fim' && !ev.dados) api.obter(s.job.id).then((j) => { s.job = j; pintarJob(j); }).catch(() => {});
}

async function cancelarJob() {
  if (!s.job) return;
  if (!(await confirmar(t('tarefas.cancelar_titulo'), t('tarefas.cancelar_texto', { tipo: s.job.tipo }), { ok: t('tarefas.cancelar_ok'), perigo: true }))) return;
  try { s.job = await api.cancelar(s.job.id); pintarJob(s.job); } catch (e) { el('aviso').erro(t('tarefas.erro_cancelar', { status: e.status || t('tarefas.rede'), erro: e.message })); }
}
