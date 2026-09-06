/* plat — tela /admin/auditoria (item L7-20): trilha de auditoria de negócio do inquilino.
   Filtros (período, usuário, ação, origem), tabela paginada de 50, exportação CSV e JSON pela mesma
   consulta que alimenta a tabela, e o cartão de retenção para quem tem org.configurar.
   A tela nunca oferece apagar linha: a trilha é append-only e a única saída é o expurgo de retenção. */
import { obter, alterar, mensagemDe, consulta } from '../base/api.js';
import { h, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { filtro, seletor } from './comum.js';

const LIMITE = 50;
const PERIODOS = [['1', '24 h'], ['7', '7 d'], ['30', '30 d'], ['92', '92 d']];
const ORIGENS = ['evento', 'cobertura', 'aplicacao'];
const f = { periodo: '7', ator_id: '', acao: '', origem: '', deslocamento: 0 };
let usuarios = [];
let config = null;
let seq = 0;

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
  montarLayout({ usuario, ativo: '/admin/auditoria' });
  cabecalho(t('auditoria.titulo'));
  const cargas = [];
  if (tem('membros.ver')) {
    cargas.push(obter(`/api/usuarios${consulta({ limite: 1000, ativo: '' })}`)
      .then((r) => { usuarios = r.status === 200 ? (r.json.itens || []) : []; }));
  }
  if (tem('org.configurar')) {
    cargas.push(obter('/api/auditoria/config').then((r) => { config = r.status === 200 ? r.json : null; }));
  }
  await Promise.all(cargas);
  montarRetencao();
  montarFiltros();
  montarTabela();
  await carregarTrilha();
}

function montarRetencao() {
  const secao = document.getElementById('retencao');
  if (!config) return;
  secao.hidden = false;
  const campo = document.getElementById('retencao-dias');
  campo.min = String(config.minimo_dias);
  campo.max = String(config.maximo_dias);
  campo.value = String(config.retencao_dias);
  document.getElementById('retencao-ajuda').textContent =
    t('auditoria.retencao_ajuda', { min: config.minimo_dias, max: config.maximo_dias, padrao: config.padrao_dias });
  document.getElementById('retencao-gravar').addEventListener('click', gravarRetencao);
  atualizarRodape();
}

async function gravarRetencao() {
  const aviso = document.getElementById('aviso');
  const dias = Number(document.getElementById('retencao-dias').value);
  const r = await alterar('/api/auditoria/config', { retencao_dias: dias });
  if (r.status !== 200) { aviso.erro(`${t('erro.gravar')}: ${mensagemDe(r)}`); return; }
  config = r.json;
  document.getElementById('retencao-dias').value = String(config.retencao_dias);
  aviso.ok(t('auditoria.retencao_gravada', { dias: config.retencao_dias }));
  atualizarRodape();
  await carregarTrilha();
}

function atualizarRodape() {
  const rodape = document.getElementById('rodape');
  if (!config) { rodape.textContent = t('auditoria.rodape_sem_config'); return; }
  rodape.textContent = t('auditoria.rodape', { dias: config.retencao_dias, job: config.job_expurgo || '—' });
}

function montarFiltros() {
  const area = document.getElementById('filtros');
  const periodo = seletor('periodo', PERIODOS.map(([v, r]) => ({ valor: v, rotulo: r })), '7');
  const ator = seletor('ator_id', [{ valor: '', rotulo: t('geral.todos') },
    ...usuarios.map((u) => ({ valor: String(u.id), rotulo: u.login }))], '');
  const acao = h('input', { type: 'text', name: 'acao', autocomplete: 'off', spellcheck: 'false' });
  const origem = seletor('origem', [{ valor: '', rotulo: t('geral.todos') },
    ...ORIGENS.map((o) => ({ valor: o, rotulo: t(`auditoria.origem_${o}`) }))], '');
  const bt = h('button', { type: 'button', class: 'primario', id: 'filtrar' }, t('log.filtrar'));
  const csv = h('a', { class: 'botao', id: 'exportar-csv', download: 'auditoria.csv' }, t('auditoria.exportar_csv'));
  const json = h('a', { class: 'botao', id: 'exportar-json', download: 'auditoria.json' }, t('auditoria.exportar_json'));
  const aplicar = () => {
    f.periodo = periodo.value; f.ator_id = ator.value; f.acao = acao.value.trim(); f.origem = origem.value;
    f.deslocamento = 0;
    carregarTrilha();
  };
  bt.addEventListener('click', aplicar);
  acao.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); aplicar(); } });
  area.append(filtro(t('log.periodo'), periodo).el);
  if (usuarios.length) area.append(filtro(t('campo.usuario'), ator).el);
  area.append(filtro(t('auditoria.acao'), acao).el, filtro(t('auditoria.origem'), origem).el, bt, csv, json);
  document.getElementById('paginacao').addEventListener('mudar', (e) => {
    f.deslocamento = e.detail.deslocamento; carregarTrilha();
  });
}

function parametros(formato) {
  const j = janela(f.periodo);
  return consulta({ ator_id: f.ator_id, acao: f.acao, origem: f.origem, desde: j.desde, ate: j.ate,
    limite: formato ? '' : LIMITE, deslocamento: formato ? '' : f.deslocamento, formato });
}

function diferenca(linha) {
  const partes = [];
  if (linha.antes) partes.push(h('div', {}, h('span', { class: 'fraco' }, t('auditoria.antes')), ' ',
    h('code', {}, JSON.stringify(linha.antes))));
  if (linha.depois) partes.push(h('div', {}, h('span', { class: 'fraco' }, t('auditoria.depois')), ' ',
    h('code', {}, JSON.stringify(linha.depois))));
  if (!partes.length) return '';
  return h('details', {}, h('summary', {}, t('log.ver_json')), h('pre', { class: 'json-dobravel' },
    JSON.stringify({ antes: linha.antes, depois: linha.depois }, null, 1)));
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  tab.colunas = [
    { chave: 'em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'ator_login', titulo: t('campo.usuario'), classe: 'mono',
      formatar: (v, l) => v || (l.ator_id ? `#${l.ator_id}` : t('auditoria.sem_ator')) },
    { chave: 'acao', titulo: t('auditoria.acao'), classe: 'mono' },
    { chave: 'recurso_tipo', titulo: t('auditoria.recurso'), classe: 'mono',
      formatar: (v, l) => [v, l.recurso_id].filter(Boolean).join(':') },
    { chave: 'depois', titulo: t('auditoria.mudanca'), formatar: (v, l) => diferenca(l) },
    { chave: 'origem', titulo: t('auditoria.origem'),
      formatar: (v) => marcador(t(`auditoria.origem_${v}`), v === 'evento' ? 'ok' : '') },
    { chave: 'ip', titulo: t('sessao.ip'), classe: 'mono' },
    { chave: 'req_id', titulo: t('auditoria.req_id'), classe: 'mono' },
  ];
  tab.vazio = t('auditoria.vazio');
}

async function carregarTrilha() {
  const aviso = document.getElementById('aviso');
  const tab = document.getElementById('tabela');
  document.getElementById('exportar-csv').href = `/api/auditoria${parametros('csv')}`;
  document.getElementById('exportar-json').href = `/api/auditoria${parametros('json_export')}`;
  const meu = ++seq;
  const r = await obter(`/api/auditoria${parametros('')}`);
  if (meu !== seq) return; // resposta atrasada de um pedido anterior: descarta
  if (r.status !== 200) { aviso.erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); tab.linhas = []; return; }
  tab.linhas = r.json.itens || [];
  const total = r.json.total ?? tab.linhas.length;
  document.getElementById('paginacao').atualizar({ total, limite: LIMITE, deslocamento: f.deslocamento });
  cabecalho(t('auditoria.titulo'), { contagem: formatarNumero(total) });
}
