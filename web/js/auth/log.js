/* plat — tela /admin/log (ADR 0002 seção 15.6): filtros (período, usuário, token, rota, status), tabela paginada de 50,
   exportar CSV (link para /api/log?formato=csv&..., o navegador baixa), aba Eventos (GET /api/eventos). */
import { obter, mensagemDe, consulta } from '../base/api.js';
import { h, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { filtro, seletor } from './comum.js';

const LIMITE = 50;
const PERIODOS = [['1', '24 h'], ['7', '7 d'], ['30', '30 d'], ['92', '92 d']];
const f = { periodo: '7', usuario_id: '', token_id: '', rota: '', status: '', deslocamento: 0 };
const fe = { periodo: '7', tipo: '', ator_id: '', deslocamento: 0 };
let usuarios = [];
let tokens = [];

let seqLog = 0;

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.log_ver' });
if (usuario) await iniciar();
pronto();
function janela(periodo) {
  const ate = new Date();
  const desde = new Date(ate.getTime() - Number(periodo) * 86400000);
  return { desde: desde.toISOString(), ate: ate.toISOString() };
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/log' });
  cabecalho(t('log.titulo'));
  const cargas = [];
  if (tem('membros.ver')) cargas.push(obter(`/api/usuarios${consulta({ limite: 1000, ativo: '' })}`).then((r) => { usuarios = r.status === 200 ? (r.json.itens || []) : []; }));
  cargas.push(obter(`/api/tokens${consulta({ todos: tem('tokens.gerir_todos') ? '1' : '' })}`).then((r) => { tokens = r.status === 200 ? (Array.isArray(r.json) ? r.json : (r.json.itens || [])) : []; }));
  await Promise.all(cargas);
  montarAbas();
  montarFiltros();
  montarTabela();
  montarEventos();
  await carregarLog();
}

function montarAbas() {
  const area = document.getElementById('abas');
  const defs = [['acessos', t('log.aba_acessos'), 'painel-acessos'], ['eventos', t('log.aba_eventos'), 'painel-eventos']];
  for (const [id, rot, painel] of defs) {
    const b = h('button', { type: 'button', role: 'tab', id: `aba-${id}`, 'aria-selected': String(id === 'acessos'), 'aria-controls': painel }, rot);
    b.addEventListener('click', async () => {
      area.querySelectorAll('[role=tab]').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      document.getElementById('painel-acessos').hidden = id !== 'acessos';
      document.getElementById('painel-eventos').hidden = id !== 'eventos';
      if (id === 'eventos') await carregarEventos();
    });
    area.append(b);
  }
}

function montarFiltros() {
  const area = document.getElementById('filtros');
  const periodo = seletor('periodo', PERIODOS.map(([v, r]) => ({ valor: v, rotulo: r })), '7');
  const usu = seletor('usuario_id', [{ valor: '', rotulo: t('geral.todos') }, ...usuarios.map((u) => ({ valor: String(u.id), rotulo: u.login }))], '');
  const tok = seletor('token_id', [{ valor: '', rotulo: t('geral.todos') }, ...tokens.map((k) => ({ valor: String(k.id), rotulo: `${k.nome} (${k.prefixo})` }))], '');
  const rota = h('input', { type: 'text', name: 'rota', autocomplete: 'off', spellcheck: 'false' });
  const status = seletor('status', [{ valor: '', rotulo: t('geral.todos') }, ...['2xx', '3xx', '4xx', '5xx', '200', '201', '204', '400', '401', '403', '404', '409', '422', '423', '429', '500'].map((s) => ({ valor: s, rotulo: s }))], '');
  const btFiltrar = h('button', { type: 'button', class: 'primario', id: 'filtrar' }, t('log.filtrar'));
  const csv = h('a', { class: 'botao', id: 'exportar-csv', download: 'log_acesso.csv' }, t('log.exportar_csv'));
  const aplicar = () => {
    f.periodo = periodo.value; f.usuario_id = usu.value; f.token_id = tok.value; f.rota = rota.value.trim(); f.status = status.value; f.deslocamento = 0;
    carregarLog();
  };
  btFiltrar.addEventListener('click', aplicar);
  rota.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); aplicar(); } });
  area.append(filtro(t('log.periodo'), periodo).el);
  if (usuarios.length) area.append(filtro(t('campo.usuario'), usu).el);
  area.append(filtro(t('log.token'), tok).el, filtro(t('log.rota_comeca'), rota).el, filtro(t('log.status'), status).el, btFiltrar, csv);
  document.getElementById('paginacao').addEventListener('mudar', (e) => { f.deslocamento = e.detail.deslocamento; carregarLog(); });
}

function parametrosLog(formato) {
  const j = janela(f.periodo);
  return consulta({ usuario_id: f.usuario_id, token_id: f.token_id, rota: f.rota, status: f.status, desde: j.desde, ate: j.ate, limite: LIMITE, deslocamento: f.deslocamento, formato });
}

function statusMarcador(s) {
  const n = Number(s);
  return marcador(String(s), n >= 500 ? 'falha' : (n >= 400 ? 'atencao' : (n >= 200 && n < 300 ? 'ok' : '')));
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  const porId = Object.fromEntries(usuarios.map((u) => [u.id, u.login]));
  const tokPorId = Object.fromEntries(tokens.map((k) => [k.id, k.prefixo]));
  tab.colunas = [
    { chave: 'em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'usuario_id', titulo: t('campo.usuario'), formatar: (v, l) => l.usuario_login || l.login || (v ? (porId[v] || `#${v}`) : ''), classe: 'mono' },
    { chave: 'token_id', titulo: t('log.token'), formatar: (v, l) => l.token_prefixo || (v ? (tokPorId[v] || `#${v}`) : ''), classe: 'mono' },
    { chave: 'ip', titulo: t('sessao.ip'), classe: 'mono' },
    { chave: 'metodo', titulo: t('log.metodo'), classe: 'mono' },
    { chave: 'rota', titulo: t('log.rota'), classe: 'mono', formatar: (v) => (v || '').slice(0, 90) },
    { chave: 'status', titulo: t('log.status'), formatar: statusMarcador },
    { chave: 'bytes', titulo: t('log.bytes'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'tempo_ms', titulo: t('log.tempo_ms'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'resultado', titulo: t('log.resultado'), formatar: (v) => v || '' },
  ];
  tab.vazio = t('log.vazio');
}

async function carregarLog() {
  const aviso = document.getElementById('aviso');
  const tab = document.getElementById('tabela');
  document.getElementById('exportar-csv').href = `/api/log${parametrosLog('csv')}`;
  const seq = ++seqLog;
  const r = await obter(`/api/log${parametrosLog('')}`);
  if (seq !== seqLog) return; // resposta atrasada de um pedido anterior: descarta
  if (r.status !== 200) { aviso.erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); tab.linhas = []; return; }
  aviso.limpar();
  tab.linhas = r.json.itens || [];
  const total = r.json.total ?? tab.linhas.length;
  document.getElementById('paginacao').atualizar({ total, limite: LIMITE, deslocamento: f.deslocamento });
  cabecalho(t('log.titulo'), { contagem: formatarNumero(total) });
}

function montarEventos() {
  const area = document.getElementById('filtros-eventos');
  const periodo = seletor('periodo', PERIODOS.map(([v, r]) => ({ valor: v, rotulo: r })), '7');
  const tipo = h('input', { type: 'text', name: 'tipo', autocomplete: 'off', spellcheck: 'false' });
  const ator = seletor('ator_id', [{ valor: '', rotulo: t('geral.todos') }, ...usuarios.map((u) => ({ valor: String(u.id), rotulo: u.login }))], '');
  const bt = h('button', { type: 'button', class: 'primario', id: 'filtrar-eventos' }, t('log.filtrar'));
  const aplicar = () => { fe.periodo = periodo.value; fe.tipo = tipo.value.trim(); fe.ator_id = ator.value; fe.deslocamento = 0; carregarEventos(); };
  bt.addEventListener('click', aplicar);
  tipo.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); aplicar(); } });
  area.append(filtro(t('log.periodo'), periodo).el, filtro(t('log.tipo_evento'), tipo).el);
  if (usuarios.length) area.append(filtro(t('log.ator'), ator).el);
  area.append(bt);
  const tab = document.getElementById('tabela-eventos');
  tab.colunas = [
    { chave: 'em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'tipo', titulo: t('log.tipo_evento'), classe: 'mono' },
    { chave: 'ator', titulo: t('log.ator'), formatar: (a) => a?.login || '' , classe: 'mono' },
    { chave: 'alvo_tipo', titulo: t('log.alvo'), formatar: (v, l) => [v, l.alvo_id].filter(Boolean).join(':'), classe: 'mono' },
    { chave: 'propriedades', titulo: t('log.propriedades'), formatar: (p) => (p && Object.keys(p).length ? h('details', {}, h('summary', {}, t('log.ver_json')), h('pre', { class: 'json-dobravel' }, JSON.stringify(p, null, 1))) : '') },
    { chave: 'ip', titulo: t('sessao.ip'), classe: 'mono' },
  ];
  tab.vazio = t('log.vazio');
  document.getElementById('paginacao-eventos').addEventListener('mudar', (e) => { fe.deslocamento = e.detail.deslocamento; carregarEventos(); });
}

async function carregarEventos() {
  const aviso = document.getElementById('aviso');
  const tab = document.getElementById('tabela-eventos');
  const j = janela(fe.periodo);
  const r = await obter(`/api/eventos${consulta({ tipo: fe.tipo, ator_id: fe.ator_id, desde: j.desde, ate: j.ate, limite: LIMITE, deslocamento: fe.deslocamento })}`);
  if (r.status !== 200) { aviso.erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); tab.linhas = []; return; }
  aviso.limpar();
  tab.linhas = r.json.itens || [];
  document.getElementById('paginacao-eventos').atualizar({ total: r.json.total ?? tab.linhas.length, limite: LIMITE, deslocamento: fe.deslocamento });
}

