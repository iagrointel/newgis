/* plat · ferramentas — tela /ferramentas (item UX-09): DOIS registros viram um catálogo só.
   (1) REGISTRO DE TIPOS DE TAREFA (GET /api/jobs/tipos, ADR 0003 seção 9) — jobs administrativos/diagnóstico
   (importar, exportar, prova.*); executar = POST /api/jobs {tipo, parametros}.
   (2) REGISTRO DE FERRAMENTAS no vocabulário GP da Esri (GET /api/ferramentas, item L2-05-a) — cada ferramenta
   (`app.ferramentas.registro`, ex. buffer) com o mesmo formato de esquema (tp.parametros_schema); executar =
   POST /api/ferramentas/{nome}/executar (síncrono se o custo estimado ficar abaixo do teto, senão job
   `ferramentas.executar`) e TAMBÉM GPServer compatível — aba "ArcGIS (GPServer)" no painel (item UX-22): URL
   copiável dos descritores/execute/submitJob e um botão que roda a MESMA ferramenta por submitJob (mesmo
   caminho que o Pro/AGOL usariam), reaproveitando o painel de execução abaixo.
   Cada entrada do catálogo ganha `tp._origem` ('job' | 'gp') para o resto do arquivo saber a quem perguntar.
   Formulário: campo por propriedade do esquema, com tipo, limites, enum, obrigatório e ajuda — sem uma linha
   escrita à mão por ferramenta. O progresso de um job vem ao vivo pelo mesmo canal da tela Tarefas (SSE com
   reserva por polling, web/js/jobs/eventos.js); o resultado com `item_id` vira o caminho para o catálogo (e
   dali para o mapa). Erro 422 do servidor volta campo a campo (loc do pydantic ou `campo` do ErroParametro);
   parâmetro fora do limite é recusado no navegador com o motivo no campo (refutação do item: nunca 422 cru). */
import { chamar as chamarBase, enviar } from '../base/api.js';
import { h, limpar, botaoCopiar } from '../base/dom.js';
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
const s = { tipos: [], q: '', diagnostico: false, tipo: null, job: null, form: null, conversores: {}, validadores: {}, linhasLog: new Set(), destinoGp: null };
const gpToken = { promessa: null }; // token de serviço (escopo jobs:executar) cunhado uma vez por sessão da página

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
  el('gpserver-executar').addEventListener('click', () => {
    if (!s.tipo || s.tipo._origem !== 'gp') return;
    s.destinoGp = 'submitJob';
    s.form.querySelector('form')?.requestSubmit();
  });
  el('gpserver-execute').addEventListener('click', () => {
    if (!s.tipo || s.tipo._origem !== 'gp') return;
    s.destinoGp = 'execute';
    s.form.querySelector('form')?.requestSubmit();
  });
  await carregarTipos();
  const pedido = new URLSearchParams(location.search).get('tipo');
  if (pedido) abrirFerramenta(pedido);
}

/* ---------------------------------------------------------------- catálogo */
async function carregarTipos() {
  const estado = el('catalogo-estado');
  estado.carregando(t('ferramentas.carregando'));
  el('catalogo-lista').hidden = true;
  let tipos;
  let ferramentasGp;
  try {
    [tipos, ferramentasGp] = await Promise.all([api.tipos(), api.ferramentas()]);
  } catch (e) {
    estado.erro({ status: e.status, json: { mensagem: e.message, req_id: e.reqId } });
    return;
  }
  const dosJobs = (Array.isArray(tipos) ? tipos : (tipos.itens || []))
    .filter((tp) => !tp.somente_sistema)
    .map((tp) => ({ ...tp, _origem: 'job' }));
  const dosGp = (Array.isArray(ferramentasGp) ? ferramentasGp : (ferramentasGp.itens || []))
    .map((f) => ({ ...f, _origem: 'gp', parametros_schema: f.esquema }));
  s.tipos = [...dosJobs, ...dosGp];
  desenharCatalogo();
}

// declarações de função (içadas): o módulo executa `await iniciar()` no topo, antes de qualquer `const` abaixo
function ehDiagnostico(tp) { return tp._origem !== 'gp' && (tp.nome.startsWith('prova.') || tp.nome.startsWith('jobs.')); }
function grupoDe(tp) { return tp._origem === 'gp' ? `esri-${tp.categoria}` : tp.nome.split('.')[0]; }
function podeRodar(tp) { return tp._origem === 'gp' ? tem('analise.executar') : (!tp.perfil_minimo || tem('jobs.executar')); }

function visiveis() {
  const q = s.q.toLocaleLowerCase();
  return s.tipos.filter((tp) => (s.diagnostico || !ehDiagnostico(tp)) && (!q || `${tp.nome} ${tp.descricao || ''}`.toLocaleLowerCase().includes(q)));
}

function custoDe(tp) {
  if (tp._origem === 'gp') {
    return [t('ferramentas.gpserver_categoria', { categoria: t(`ferramentas.categoria_${tp.categoria}`) }),
            t('ferramentas.gpserver_versao', { versao: tp.versao })].join(' · ');
  }
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
        h('div', { class: 'ferramenta-topo' }, h('span', { class: 'mono' }, tp.nome),
          ehDiagnostico(tp) ? h('span', { class: 'marcador info' }, t('ferramentas.diagnostico')) : null,
          tp._origem === 'gp' ? h('span', { class: 'marcador info' }, t('ferramentas.gpserver_marcador')) : null),
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
  if (!podeRodar(tp)) {
    estado.negado(tp._origem === 'gp' ? t('ferramentas.gpserver_negado') : t('ferramentas.negado', { perfil: t(`perfil.${tp.perfil_minimo}`) }));
  }
  s.conversores = conversores;
  s.validadores = validadores;
  const gp = el('gpserver');
  gp.hidden = tp._origem !== 'gp';
  gp.open = false;
  el('gpserver-executar').disabled = !podeRodar(tp);
  el('gpserver-execute').disabled = !podeRodar(tp);
  if (tp._origem === 'gp') montarGpserver(tp);
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
function tratarErroExecucao(f, e) {
  if (e.status === 422 && Array.isArray(e.detalhe)) {
    // detalhe do serviço de jobs ou de registro.ErroParametro: [{campo, mensagem}]; o campo pode vir "a.b" em aninhados
    for (const d of e.detalhe) {
      const campo = String(d.campo || '').split('.')[0];
      const msg = d.mensagem || JSON.stringify(d);
      if (campo && f.campo(campo)) f.erro(campo, msg); else f.mensagem(campo ? `${campo}: ${msg}` : msg, 'erro');
    }
    f.querySelector('[aria-invalid="true"]')?.focus();
  } else if (e.status === 422 && e.detalhe && typeof e.detalhe === 'object') {
    for (const [campo, msg] of Object.entries(e.detalhe)) { if (f.campo(campo)) f.erro(campo, String(msg)); else f.mensagem(`${campo}: ${msg}`, 'erro'); }
  } else f.mensagem(e.status === 403 ? t('ferramentas.negado_executar') : t('ferramentas.erro_criar', { status: e.status || t('tarefas.rede'), erro: e.message }), 'erro');
}

/* valida e converte pelo mesmo esquema do formulário; devolve os parâmetros normalizados ou null (erro já
   marcado no campo). Usado pelo botão "executar" (API própria) e pelo botão do GPServer (mesmos parâmetros,
   destino diferente) — a validação nunca diverge entre os dois caminhos. */
function parametrosValidados(valores) {
  const f = s.form; const { conversores, validadores } = s;
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
  if (erros) { f.querySelector('[aria-invalid="true"]')?.focus(); return null; }
  return parametros;
}

async function executar(valores) {
  const f = s.form; const tp = s.tipo;
  const viaGp = s.destinoGp;
  s.destinoGp = null;
  const parametros = parametrosValidados(valores);
  if (parametros === null) return;
  f.ocupado = true;
  if (viaGp === 'submitJob') {
    try { await executarViaGpserverSubmitJob(tp, parametros); } finally { f.ocupado = false; }
    return;
  }
  if (viaGp === 'execute') {
    try { await executarViaGpserverExecute(tp, parametros); } finally { f.ocupado = false; }
    return;
  }
  if (tp._origem === 'gp') {
    let r;
    try {
      r = await api.ferramentaExecutar(tp.nome, { parametros });
    } catch (e) {
      f.ocupado = false;
      tratarErroExecucao(f, e);
      return;
    }
    f.ocupado = false;
    if (r.sincrono) mostrarResultadoSincrono(r); else mostrarJob(r.job);
    return;
  }
  let job;
  try {
    job = await api.criar(tp.nome, parametros);
  } catch (e) {
    f.ocupado = false;
    tratarErroExecucao(f, e);
    return;
  }
  f.ocupado = false;
  mostrarJob(job);
}

/* ferramenta do registro GP com custo abaixo do teto síncrono (item L2-05-a): a API própria já devolveu o
   item pronto (200, sem job) — mesmo painel de execução, sem assinatura SSE (não há o que esperar). */
function mostrarResultadoSincrono(r) {
  if (s.job && !FINAIS.has(s.job.estado)) cancelarAssinatura(s.job.id, ouvinte);
  s.job = null;
  s.linhasLog = new Set();
  limpar(el('execucao-log'));
  el('execucao').hidden = false;
  el('execucao-tarefa').hidden = true;
  const e = fmtEstado('concluido');
  const marc = el('execucao-estado');
  marc.className = `estado-job ${e.classe}`;
  limpar(marc).append(h('span', { class: 'simbolo', 'aria-hidden': 'true' }, e.simbolo), ' ', e.rotulo);
  el('execucao-preenchido').style.width = '100%';
  el('execucao-valor').textContent = '100 %';
  el('execucao-progresso').setAttribute('aria-valuenow', '100');
  el('execucao-mensagem').textContent = t('ferramentas.gpserver_sincrono', { feicoes: r.feicoes ?? 0 });
  const erro = el('execucao-erro');
  erro.hidden = true; erro.textContent = '';
  el('execucao-cancelar').hidden = true;
  const link = el('execucao-item');
  link.hidden = false;
  link.href = `/conteudo/${encodeURIComponent(r.item_id)}`;
  el('execucao').scrollIntoView({ block: 'nearest' });
}

function mostrarJob(job) {
  if (s.job && s.job.id !== job.id && !FINAIS.has(s.job.estado)) cancelarAssinatura(s.job.id, ouvinte);
  s.job = job;
  s.linhasLog = new Set();
  limpar(el('execucao-log'));
  el('execucao').hidden = false;
  el('execucao-tarefa').hidden = false;
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
  try {
    // job de uma ferramenta do registro GP: cancela pela mesma rota que o Pro/AGOL usariam (GPServer cancel),
    // não só pela interna — item UX-22, a rota de escrita precisa de um controle real, não só documentado.
    s.job = (s.tipo && s.tipo._origem === 'gp') ? await cancelarViaGpserver(s.tipo, s.job.id) : await api.cancelar(s.job.id);
    pintarJob(s.job);
  } catch (e) { el('aviso').erro(t('tarefas.erro_cancelar', { status: e.status || t('tarefas.rede'), erro: e.message })); }
}

/* ---------------------------------------------------------------- ArcGIS (GPServer) — item UX-22
   Aba do painel de cada ferramenta do registro GP (tp._origem === 'gp'): URL copiável dos descritores e das
   rotas de execução (mesmo padrão da aba Compartilhamento do catálogo, web/js/catalogo/item_compartilhar.js)
   e um botão que roda a MESMA ferramenta por `submitJob` — prova, com um controle de verdade, que a rota
   responde como o Pro/AGOL esperam; o resultado cai no mesmo painel de execução de baixo (submitJob devolve o
   id do job interno, então basta buscá-lo por `GET /api/jobs/{id}` e reusar mostrarJob). O token (escopo
   jobs:executar) é cunhado uma vez por carregamento de página — nunca a cada abertura da aba — para não
   repetir o problema medido em token_servico.js (12 tokens cunhados em 1h de reabrir painel). */
async function tokenGp() {
  if (!gpToken.promessa) {
    gpToken.promessa = (async () => {
      const r = await enviar('/api/tokens', { nome: 'gpserver-ferramentas', escopos: ['jobs:executar'] });
      if (r.status !== 201) throw new Error((r.json && r.json.mensagem) || t('ferramentas.gpserver_token_erro'));
      return r.json.token;
    })();
  }
  return gpToken.promessa;
}

function linhaUrl(rotulo, valor) {
  const entrada = h('input', { type: 'text', readonly: true, value: valor, 'aria-label': rotulo });
  const bt = botaoCopiar(valor, entrada, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') });
  return h('div', { class: 'gpserver-linha' }, h('span', { class: 'rotulo' }, rotulo), entrada, bt);
}

async function montarGpserver(tp) {
  const raiz = el('gpserver-urls');
  const estado = el('gpserver-estado');
  limpar(raiz);
  estado.hidden = true;
  const base = `${location.origin}/rest/services/${encodeURIComponent(tp.nome)}/GPServer`;
  raiz.append(
    linhaUrl(t('ferramentas.gpserver_servico'), `${base}?f=json`),
    linhaUrl(t('ferramentas.gpserver_tarefa'), `${base}/${encodeURIComponent(tp.nome)}?f=json`),
  );
  try {
    const tok = await tokenGp();
    if (s.tipo !== tp) return; // usuário já abriu outra ferramenta enquanto o token cunhava
    raiz.append(
      linhaUrl(t('ferramentas.gpserver_execute'), `${base}/${encodeURIComponent(tp.nome)}/execute?f=json&token=${encodeURIComponent(tok)}`),
      linhaUrl(t('ferramentas.gpserver_submitjob'), `${base}/${encodeURIComponent(tp.nome)}/submitJob?f=json&token=${encodeURIComponent(tok)}`),
    );
  } catch (e) {
    estado.hidden = false;
    estado.erro({ status: 0, json: { mensagem: e.message } });
  }
}

function erroGpserver(r) {
  return (r.json && r.json.error && r.json.error.message) || (r.json && r.json.mensagem) || t('tarefas.rede');
}

async function executarViaGpserverSubmitJob(tp, parametros) {
  // caminho relativo (same-origin, sessão por cookie): literal inline para o mapa de cobertura da interface
  // (docs/gerar_cobertura_ui.py) reconhecer a chamada — `${location.origin}` numa variável à parte não conta.
  const r = await chamarBase('POST', `/rest/services/${encodeURIComponent(tp.nome)}/GPServer/${encodeURIComponent(tp.nome)}/submitJob`, parametros);
  if (r.status >= 400 || r.status === 0) {
    s.form.mensagem(t('ferramentas.erro_criar', { status: r.status || t('tarefas.rede'), erro: erroGpserver(r) }), 'erro');
    return;
  }
  try {
    const job = await api.obter(r.json.jobId);
    mostrarJob(job);
  } catch (e) {
    s.form.mensagem(e.message, 'erro');
  }
}

async function executarViaGpserverExecute(tp, parametros) {
  const r = await chamarBase('POST', `/rest/services/${encodeURIComponent(tp.nome)}/GPServer/${encodeURIComponent(tp.nome)}/execute`, parametros);
  if (r.status >= 400 || r.status === 0) {
    // custo acima do teto síncrono (400 do backend, ADR do item): a mensagem do servidor já manda usar submitJob
    s.form.mensagem(t('ferramentas.erro_criar', { status: r.status || t('tarefas.rede'), erro: erroGpserver(r) }), 'erro');
    return;
  }
  const valor = (r.json.results && r.json.results[0] && r.json.results[0].value) || {};
  mostrarResultadoSincrono({ item_id: valor.itemId, feicoes: valor.featureCount });
}

async function cancelarViaGpserver(tp, jobId) {
  const r = await chamarBase('POST', `/rest/services/${encodeURIComponent(tp.nome)}/GPServer/${encodeURIComponent(tp.nome)}/jobs/${encodeURIComponent(jobId)}/cancel`);
  if (r.status >= 400 || r.status === 0) throw new Error(erroGpserver(r));
  return api.obter(jobId); // o job no formato interno (o GPServer devolve o formato Esri, o resto da tela lê o interno)
}
