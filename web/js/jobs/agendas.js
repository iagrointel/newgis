/* plat · tarefas — agendas (ADR 0003 seções 7 e 9) sobre os componentes da base: <plat-tabela> para a lista e
   <plat-formulario> para criar/editar (nome, tipo do registro, parâmetros JSON conferidos no navegador contra os
   campos obrigatórios do parametros_schema, cron de 5 campos, fuso IANA, validade). Ações pausar/retomar/rodar
   agora/apagar. Erros 422 do servidor aparecem campo a campo (detalhe do pydantic ou dicionário por campo). */
import { confirmar } from '../base/componentes.js';
import { h } from '../base/dom.js';
import * as api from './api.js';
import { cronTemCincoCampos, data, dataHora, fusoValido } from './formato.js';
import { marcaEstado } from './lista.js';
import { aviso, porId } from './util.js';

const s = { tipos: [], usuario: null, itens: [], editando: null, aoNovoJob: null, form: null, tabela: null };
const CAMPOS = ['nome', 'tipo', 'parametros', 'cron', 'fuso', 'expira_em'];

const tipoPorNome = (nome) => s.tipos.find((t) => t.nome === nome) || null;

/* ---------- erros por campo ---------- */

export function errosPorCampo(detalhe) {
  const m = {};
  const junta = (campo, msg) => { m[campo] = m[campo] ? `${m[campo]}; ${msg}` : msg; };
  if (Array.isArray(detalhe)) {
    for (const d of detalhe) {
      const loc = Array.isArray(d.loc) ? d.loc.filter((x) => typeof x === 'string' && x !== 'body') : [];
      junta(CAMPOS.includes(loc[0]) ? loc[0] : '_', d.msg || JSON.stringify(d));
    }
  } else if (detalhe && typeof detalhe === 'object') {
    for (const [k, v] of Object.entries(detalhe)) junta(CAMPOS.includes(k) ? k : '_', typeof v === 'string' ? v : JSON.stringify(v));
  } else if (typeof detalhe === 'string') {
    m._ = detalhe;
  }
  return m;
}

function mostrarErros(erros) {
  s.form.limparErros();
  for (const [campo, msg] of Object.entries(erros)) {
    if (campo === '_') s.form.mensagem(msg, 'erro');
    else s.form.erro(campo, msg);
  }
}

/* ---------- formulário ---------- */

function validar(v) {
  const erros = {};
  let parametros = {};
  const texto = (v.parametros || '').trim();
  if (texto) {
    try {
      parametros = JSON.parse(texto);
      if (!parametros || typeof parametros !== 'object' || Array.isArray(parametros)) erros.parametros = 'os parâmetros são um objeto JSON';
    } catch {
      erros.parametros = 'JSON inválido';
    }
  }
  const t = tipoPorNome(v.tipo);
  const obrigatorios = (t && t.parametros_schema && Array.isArray(t.parametros_schema.required)) ? t.parametros_schema.required : [];
  const faltam = obrigatorios.filter((k) => !(k in parametros));
  if (!erros.parametros && faltam.length) erros.parametros = `campos obrigatórios ausentes: ${faltam.join(', ')}`;
  if (!cronTemCincoCampos(v.cron)) erros.cron = 'a expressão cron tem 5 campos (minuto hora dia mês dia-da-semana)';
  const fuso = v.fuso || 'America/Sao_Paulo';
  if (!fusoValido(fuso)) erros.fuso = 'fuso desconhecido (nome IANA, ex.: America/Sao_Paulo)';
  const dados = { nome: v.nome, tipo: v.tipo, parametros, cron: v.cron, fuso };
  if (v.expira_em) {
    const d = new Date(v.expira_em);
    if (Number.isNaN(d.getTime())) erros.expira_em = 'data inválida (ISO 8601, ex.: 2026-12-31T23:59)';
    else dados.expira_em = d.toISOString();
  }
  return { dados, erros };
}

function ajudaParametros() {
  const t = tipoPorNome(s.form.campo('tipo').value);
  const n = s.form.querySelector('[data-campo="parametros"] .ajuda');
  if (!n) return;
  if (!t) {
    n.textContent = 'objeto JSON com os parâmetros do tipo';
    return;
  }
  const props = (t.parametros_schema && t.parametros_schema.properties) || {};
  const obrig = new Set((t.parametros_schema && t.parametros_schema.required) || []);
  const lista = Object.entries(props).map(([k, v]) => `${k}${obrig.has(k) ? ' (obrigatório)' : ''}${v && v.type ? `: ${v.type}` : ''}`);
  n.textContent = `${t.descricao || t.nome}${lista.length ? ` · parâmetros: ${lista.join(', ')}` : ' · sem parâmetros'}`;
}

function abrirFormulario(agenda = null) {
  s.editando = agenda ? agenda.id : null;
  porId('agenda-form-titulo').textContent = agenda ? `editar agenda: ${agenda.nome}` : 'nova agenda';
  s.form.limparErros();
  s.form.definir({
    nome: agenda ? agenda.nome : '',
    tipo: agenda ? agenda.tipo : '',
    parametros: agenda ? JSON.stringify(agenda.parametros || {}, null, 2) : '{}',
    cron: agenda ? agenda.cron : '',
    fuso: agenda ? agenda.fuso : 'America/Sao_Paulo',
    expira_em: agenda && agenda.expira_em ? agenda.expira_em : '',
  });
  ajudaParametros();
  porId('agenda-form-caixa').hidden = false;
  s.form.focarPrimeiro();
}

function fecharFormulario() {
  porId('agenda-form-caixa').hidden = true;
  s.editando = null;
}

async function salvar(valores) {
  const { dados, erros } = validar(valores);
  if (Object.keys(erros).length) {
    mostrarErros(erros);
    return;
  }
  s.form.ocupado = true;
  try {
    if (s.editando) await api.agendas.atualizar(s.editando, dados);
    else await api.agendas.criar(dados);
    s.form.ocupado = false;
    fecharFormulario();
    aviso('agendas-aviso', '');
    await carregar();
  } catch (e) {
    s.form.ocupado = false;
    const m = e.status === 422 ? errosPorCampo(e.detalhe) : {};
    if (e.status === 409) m.nome = e.message || 'já existe uma agenda com este nome';
    if (e.status === 413) m._ = e.message || 'cota de agendas do inquilino atingida';
    if (e.status === 403) m._ = e.message || 'sem permissão para criar agendas';
    if (!Object.keys(m).length) m._ = `não foi possível salvar (${e.status || 'rede'}): ${e.message}`;
    mostrarErros(m);
  }
}

/* ---------- lista ---------- */

async function acao(id, agenda) {
  const fn = { rodar: api.agendas.rodarAgora, pausar: api.agendas.pausar, retomar: api.agendas.retomar, apagar: api.agendas.apagar }[id];
  if (id === 'editar') {
    abrirFormulario(agenda);
    return;
  }
  if (id === 'apagar' && !(await confirmar('Apagar agenda', `Apagar a agenda "${agenda.nome}"?`, { ok: 'apagar', perigo: true }))) return;
  if (!fn) return;
  try {
    const r = await fn(agenda.id);
    aviso('agendas-aviso', '');
    await carregar();
    if (id === 'rodar' && r && r.id && s.aoNovoJob) s.aoNovoJob(r);
  } catch (e) {
    aviso('agendas-aviso', `não foi possível executar (${e.status || 'rede'}): ${e.message}`);
  }
}

const COLUNAS = [
  { chave: 'nome', titulo: 'nome', classe: 'c-nome' },
  { chave: 'tipo', titulo: 'tipo', classe: 'c-tipo mono' },
  { chave: 'cron', titulo: 'cron', classe: 'c-cron mono' },
  { chave: 'fuso', titulo: 'fuso', classe: 'c-fuso' },
  {
    chave: 'proxima_em', titulo: 'próxima', classe: 'c-proxima',
    formatar: (v, a) => (a.ativa
      ? h('time', { datetime: v || '', title: dataHora(v) }, data(v))
      : h('span', { class: 'marcador atencao' }, 'pausada')),
  },
  {
    chave: 'ultimo_estado', titulo: 'última', classe: 'c-ultima',
    formatar: (v, a) => (v
      ? h('span', {}, marcaEstado(v), ' ', h('time', { datetime: a.ultima_em || '', title: dataHora(a.ultima_em) }, data(a.ultima_em)),
        a.falhas_seguidas > 0 ? h('span', { class: 'msg falha' }, ` · ${a.falhas_seguidas} falhas seguidas`) : null)
      : '—'),
  },
];

const acoesDe = (a) => [
  { id: 'rodar', rotulo: 'rodar agora', classe: 'acao-rodar' },
  a.ativa ? { id: 'pausar', rotulo: 'pausar', classe: 'acao-pausar' } : { id: 'retomar', rotulo: 'retomar', classe: 'acao-retomar' },
  { id: 'editar', rotulo: 'editar', classe: 'texto acao-editar' },
  { id: 'apagar', rotulo: 'apagar', classe: 'perigo acao-apagar' },
];

export async function carregar() {
  try {
    const r = await api.agendas.listar({ limite: 200 });
    s.itens = Array.isArray(r.itens) ? r.itens : [];
    s.tabela.linhas = s.itens;
    porId('agendas-total').textContent = `${s.itens.length} ${s.itens.length === 1 ? 'agenda' : 'agendas'}`;
    aviso('agendas-aviso', '');
  } catch (e) {
    if (e.status === 403) {
      porId('agendas').hidden = true;
      return;
    }
    aviso('agendas-aviso', `não foi possível carregar as agendas (${e.status || 'rede'}): ${e.message}`);
  }
}

export async function iniciar({ usuario = null, tipos = [], aoNovoJob = null } = {}) {
  s.usuario = usuario;
  s.tipos = tipos;
  s.aoNovoJob = aoNovoJob;
  const sec = porId('agendas');
  const perfil = usuario && usuario.perfil;
  if (perfil && !['admin', 'editor'].includes(perfil)) {
    sec.hidden = true;
    return;
  }
  sec.hidden = false;

  s.tabela = porId('agendas-tabela');
  s.tabela.vazio = 'nenhuma agenda';
  s.tabela.colunas = COLUNAS;
  s.tabela.acoes = acoesDe;
  s.tabela.addEventListener('acao', (ev) => acao(ev.detail.id, ev.detail.linha));

  s.form = porId('agenda-form');
  s.form.campos = [
    { nome: 'nome', rotulo: 'nome', tipo: 'texto', obrigatorio: true, atributos: { maxlength: '128', autocomplete: 'off' } },
    { nome: 'tipo', rotulo: 'tipo', tipo: 'select', obrigatorio: true,
      opcoes: [{ valor: '', rotulo: '— escolha —' }, ...tipos.map((t) => ({ valor: t.nome, rotulo: t.nome }))] },
    { nome: 'parametros', rotulo: 'parâmetros (JSON)', tipo: 'area', padrao: '{}', linhas: 3, ajuda: 'objeto JSON com os parâmetros do tipo' },
    { nome: 'cron', rotulo: 'cron', tipo: 'texto', obrigatorio: true, padrao: '',
      ajuda: '5 campos: minuto hora dia mês dia-da-semana (ex.: 30 3 * * *); intervalo mínimo de 15 min', atributos: { autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'fuso', rotulo: 'fuso', tipo: 'texto', padrao: 'America/Sao_Paulo', ajuda: 'nome IANA', atributos: { autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'expira_em', rotulo: 'expira em', tipo: 'texto', padrao: '', ajuda: 'opcional; ISO 8601 (ex.: 2026-12-31T23:59)', atributos: { autocomplete: 'off' } },
  ];
  s.form.botoes = [
    { id: 'salvar', rotulo: 'salvar', tipo: 'submit' },
    { id: 'cancelar', rotulo: 'cancelar', tipo: 'button' },
  ];
  s.form.addEventListener('enviar', (ev) => salvar(ev.detail.valores));
  s.form.addEventListener('botao', (ev) => { if (ev.detail.id === 'cancelar') fecharFormulario(); });
  s.form.campo('tipo').addEventListener('change', ajudaParametros);
  porId('agenda-nova').addEventListener('click', () => abrirFormulario());
  await carregar();
}
