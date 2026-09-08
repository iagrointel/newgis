/* plat · tarefas — agendas (ADR 0003 seções 7 e 9) sobre os componentes da base: <plat-tabela> para a lista e
   <plat-formulario> para criar/editar (nome, tipo do registro, parâmetros JSON conferidos no navegador contra os
   campos obrigatórios do parametros_schema, cron de 5 campos, fuso IANA, validade). Ações pausar/retomar/rodar
   agora/apagar. Erros 422 do servidor aparecem campo a campo (detalhe do pydantic ou dicionário por campo). */
import { confirmar } from '../base/componentes.js';
import { h } from '../base/dom.js';
import { aoTraduzir, t } from '../base/i18n.js';
import * as api from './api.js';
import { cronTemCincoCampos, data, dataHora, fusoValido } from './formato.js';
import { marcaEstado } from './lista.js';
import { aviso, podeExecutar, porId } from './util.js';

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
      if (!parametros || typeof parametros !== 'object' || Array.isArray(parametros)) erros.parametros = t('tarefas.ag_erro_parametros_objeto');
    } catch {
      erros.parametros = t('tarefas.ag_erro_json');
    }
  }
  const tp = tipoPorNome(v.tipo);
  const obrigatorios = (tp && tp.parametros_schema && Array.isArray(tp.parametros_schema.required)) ? tp.parametros_schema.required : [];
  const faltam = obrigatorios.filter((k) => !(k in parametros));
  if (!erros.parametros && faltam.length) erros.parametros = t('tarefas.ag_erro_obrigatorios', { lista: faltam.join(', ') });
  if (!cronTemCincoCampos(v.cron)) erros.cron = t('tarefas.ag_erro_cron');
  const fuso = v.fuso || 'America/Sao_Paulo';
  if (!fusoValido(fuso)) erros.fuso = t('tarefas.ag_erro_fuso');
  const dados = { nome: v.nome, tipo: v.tipo, parametros, cron: v.cron, fuso };
  if (v.expira_em) {
    const d = new Date(v.expira_em);
    if (Number.isNaN(d.getTime())) erros.expira_em = t('tarefas.ag_erro_data');
    else dados.expira_em = d.toISOString();
  }
  return { dados, erros };
}

function ajudaParametros() {
  const tp = tipoPorNome(s.form.campo('tipo').value);
  const n = s.form.querySelector('[data-campo="parametros"] .ajuda');
  if (!n) return;
  if (!tp) {
    n.textContent = t('tarefas.ag_parametros_ajuda');
    return;
  }
  const props = (tp.parametros_schema && tp.parametros_schema.properties) || {};
  const obrig = new Set((tp.parametros_schema && tp.parametros_schema.required) || []);
  const lista = Object.entries(props).map(([k, v]) => `${k}${obrig.has(k) ? ` (${t('tarefas.ag_obrigatorio')})` : ''}${v && v.type ? `: ${v.type}` : ''}`);
  n.textContent = `${tp.descricao || tp.nome}${lista.length ? ` · ${t('tarefas.ag_parametros')}: ${lista.join(', ')}` : ` · ${t('tarefas.ag_sem_parametros')}`}`;
}

function abrirFormulario(agenda = null) {
  s.editando = agenda ? agenda.id : null;
  porId('agenda-form-titulo').textContent = agenda ? t('tarefas.ag_editar', { nome: agenda.nome }) : t('tarefas.ag_nova');
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
    if (e.status === 409) m.nome = e.message || t('tarefas.ag_erro_nome');
    if (e.status === 413) m._ = e.message || t('tarefas.ag_erro_cota');
    if (e.status === 403) m._ = e.message || t('tarefas.ag_erro_permissao');
    if (!Object.keys(m).length) m._ = t('tarefas.ag_erro_salvar', { status: e.status || t('tarefas.rede'), erro: e.message });
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
  if (id === 'apagar' && !(await confirmar(t('tarefas.ag_apagar_titulo'), t('tarefas.ag_apagar_texto', { nome: agenda.nome }), { ok: t('tarefas.ag_apagar'), perigo: true }))) return;
  if (!fn) return;
  try {
    const r = await fn(agenda.id);
    aviso('agendas-aviso', '');
    await carregar();
    if (id === 'rodar' && r && r.id && s.aoNovoJob) s.aoNovoJob(r);
  } catch (e) {
    aviso('agendas-aviso', t('tarefas.ag_erro_executar', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

const colunas = () => [
  { chave: 'nome', titulo: t('tarefas.ag_col_nome'), classe: 'c-nome' },
  { chave: 'tipo', titulo: t('tarefas.ag_col_tipo'), classe: 'c-tipo mono' },
  { chave: 'cron', titulo: t('tarefas.ag_col_cron'), classe: 'c-cron mono' },
  { chave: 'fuso', titulo: t('tarefas.ag_col_fuso'), classe: 'c-fuso' },
  {
    chave: 'proxima_em', titulo: t('tarefas.ag_col_proxima'), classe: 'c-proxima',
    formatar: (v, a) => (a.ativa
      ? h('time', { datetime: v || '', title: dataHora(v) }, data(v))
      : h('span', { class: 'marcador atencao' }, t('tarefas.ag_pausada'))),
  },
  {
    chave: 'ultimo_estado', titulo: t('tarefas.ag_col_ultima'), classe: 'c-ultima',
    formatar: (v, a) => (v
      ? h('span', {}, marcaEstado(v), ' ', h('time', { datetime: a.ultima_em || '', title: dataHora(a.ultima_em) }, data(a.ultima_em)),
        a.falhas_seguidas > 0 ? h('span', { class: 'msg falha' }, ` · ${t('tarefas.ag_falhas_seguidas', { n: a.falhas_seguidas })}`) : null)
      : '—'),
  },
];

const acoesDe = (a) => [
  { id: 'rodar', rotulo: t('tarefas.ag_rodar'), classe: 'acao-rodar' },
  a.ativa ? { id: 'pausar', rotulo: t('tarefas.ag_pausar'), classe: 'acao-pausar' } : { id: 'retomar', rotulo: t('tarefas.ag_retomar'), classe: 'acao-retomar' },
  { id: 'editar', rotulo: t('tarefas.ag_editar_acao'), classe: 'texto acao-editar' },
  { id: 'apagar', rotulo: t('tarefas.ag_apagar'), classe: 'perigo acao-apagar' },
];

export async function carregar() {
  try {
    const r = await api.agendas.listar({ limite: 200 });
    s.itens = Array.isArray(r.itens) ? r.itens : [];
    s.tabela.linhas = s.itens;
    porId('agendas-total').textContent = s.itens.length === 1 ? t('tarefas.ag_total_uma') : t('tarefas.ag_total', { n: s.itens.length });
    aviso('agendas-aviso', '');
    const estado = document.getElementById('agendas-estado');
    if (estado) estado.limpar();
    s.tabela.hidden = false;
  } catch (e) {
    if (e.status === 403) {
      porId('agendas').hidden = true;
      return;
    }
    const estado = document.getElementById('agendas-estado');
    if (estado) { s.tabela.hidden = true; estado.erro({ status: e.status, json: { mensagem: e.message, req_id: e.reqId } }); }
    else aviso('agendas-aviso', t('tarefas.ag_erro_carregar', { status: e.status || t('tarefas.rede'), erro: e.message }));
  }
}

export async function iniciar({ usuario = null, tipos = [], aoNovoJob = null } = {}) {
  s.usuario = usuario;
  s.tipos = tipos;
  s.aoNovoJob = aoNovoJob;
  const sec = porId('agendas');
  // agenda é execução (POST/PUT/DELETE exigem jobs.executar): quem só tem jobs.ver não vê a seção. Critério por
  // PRIVILÉGIO e não por perfil (T2): antes o perfil `campo`, que executa, também ficava sem a seção.
  if (!podeExecutar()) {
    sec.hidden = true;
    return;
  }
  sec.hidden = false;

  s.tabela = porId('agendas-tabela');
  const montarTabela = () => {
    s.tabela.vazio = t('tarefas.ag_vazio');
    s.tabela.setAttribute('legenda', t('tarefas.ag_tabela_rotulo'));
    s.tabela.querySelector('table')?.setAttribute('aria-label', t('tarefas.ag_tabela_rotulo'));
    s.tabela.colunas = colunas();
  };
  montarTabela();
  s.tabela.acoes = acoesDe;
  s.tabela.addEventListener('acao', (ev) => acao(ev.detail.id, ev.detail.linha));

  s.form = porId('agenda-form');
  const montarForm = () => {
    const valores = s.form.campos.length ? s.form.valores() : null;
    s.form.campos = [
      { nome: 'nome', rotulo: t('tarefas.ag_campo_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '128', autocomplete: 'off' } },
      { nome: 'tipo', rotulo: t('tarefas.ag_campo_tipo'), tipo: 'select', obrigatorio: true,
        opcoes: [{ valor: '', rotulo: t('tarefas.ag_escolha') }, ...tipos.map((tp) => ({ valor: tp.nome, rotulo: tp.nome }))] },
      { nome: 'parametros', rotulo: t('tarefas.ag_campo_parametros'), tipo: 'area', padrao: '{}', linhas: 3, ajuda: t('tarefas.ag_parametros_ajuda') },
      { nome: 'cron', rotulo: t('tarefas.ag_campo_cron'), tipo: 'texto', obrigatorio: true, padrao: '',
        ajuda: t('tarefas.ag_cron_ajuda'), atributos: { autocomplete: 'off', spellcheck: 'false' } },
      { nome: 'fuso', rotulo: t('tarefas.ag_campo_fuso'), tipo: 'texto', padrao: 'America/Sao_Paulo', ajuda: t('tarefas.ag_fuso_ajuda'), atributos: { autocomplete: 'off', spellcheck: 'false' } },
      { nome: 'expira_em', rotulo: t('tarefas.ag_campo_expira'), tipo: 'texto', padrao: '', ajuda: t('tarefas.ag_expira_ajuda'), atributos: { autocomplete: 'off' } },
    ];
    s.form.botoes = [
      { id: 'salvar', rotulo: t('tarefas.ag_salvar'), tipo: 'submit' },
      { id: 'cancelar', rotulo: t('tarefas.ag_cancelar'), tipo: 'button' },
    ];
    if (valores) s.form.definir(valores);
    s.form.campo('tipo').addEventListener('change', ajudaParametros);
  };
  montarForm();
  s.form.addEventListener('enviar', (ev) => salvar(ev.detail.valores));
  s.form.addEventListener('botao', (ev) => { if (ev.detail.id === 'cancelar') fecharFormulario(); });
  porId('agenda-nova').addEventListener('click', () => abrirFormulario());
  aoTraduzir(() => { montarTabela(); s.tabela.linhas = s.itens; montarForm(); });
  await carregar();
}
