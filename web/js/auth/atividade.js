/* plat — tela /admin/atividade (item L0-07-e-relatorios): painel do admin com os 10 itens mais acessados, eventos
   por dia e por tipo e acessos por dia (GET /api/atividade, gráficos SVG simples desenhados aqui, sem biblioteca),
   mais os relatórios em CSV gerados como job (GET/POST /api/relatorios, download em /api/relatorios/{id}/csv) e os
   agendamentos diário/semanal/mensal com entrega por e-mail (GET/POST /api/relatorios/agendas; apagar por
   DELETE /api/agendas/{id}). Privilégio org.exportar (admin). Limites (12 meses, 10 mil linhas, 1 por tipo por
   hora) vêm de GET /api/relatorios/tipos e são mostrados, nunca escondidos. */
import { obter, enviar, apagar, mensagemDe, consulta } from '../base/api.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { filtro, seletor } from './comum.js';

const SVG = 'http://www.w3.org/2000/svg';
const JANELAS = [['7', '7 d'], ['30', '30 d'], ['92', '92 d'], ['366', '12 m']];
const PERIODICIDADES = ['diario', 'semanal', 'mensal'];
let dias = '30';
let tipos = [];
let limites = null;

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.exportar' });
if (usuario) await iniciar();
pronto();

function aviso() { return document.getElementById('aviso'); }

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/atividade' });
  cabecalho(t('atividade.titulo'));
  const sel = seletor('dias', JANELAS.map(([v, r]) => ({ valor: v, rotulo: r })), dias);
  sel.id = 'janela-dias';
  sel.addEventListener('change', () => { dias = sel.value; carregarPainel(); });
  document.getElementById('janela').append(filtro(t('atividade.janela'), sel).el);
  const r = await obter('/api/relatorios/tipos');
  if (r.status === 200) { tipos = r.json.tipos; limites = r.json.limites; }
  montarRelatorios();
  montarAgendas();
  await Promise.all([carregarPainel(), carregarRelatorios(), carregarAgendas()]);
}

/* ---------- painel ---------- */
async function carregarPainel() {
  const r = await obter(`/api/atividade${consulta({ dias })}`);
  if (r.status !== 200) { aviso().erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); return; }
  const p = r.json;
  const kpis = document.getElementById('kpis');
  limpar(kpis);
  for (const [chave, valor] of Object.entries(p.totais)) {
    kpis.append(h('div', { class: 'kpi', id: `kpi-${chave}` }, h('strong', {}, formatarNumero(valor)), h('span', {}, t(`atividade.kpi_${chave}`))));
  }
  barrasVerticais(document.getElementById('grafico-dias'), p.eventos_por_dia.map((x) => [x.dia.slice(5), x.n]));
  barrasVerticais(document.getElementById('grafico-acessos'), p.acessos_por_dia.map((x) => [x.dia.slice(5), x.n]));
  barrasHorizontais(document.getElementById('grafico-tipos'), p.eventos_por_tipo.map((x) => [x.tipo, x.n]));
  const tab = document.getElementById('tabela-top');
  tab.colunas = [
    { chave: 'titulo', titulo: t('atividade.col_titulo'), formatar: (v, l) => h('a', { href: `/conteudo/${l.id}` }, v) },
    { chave: 'tipo', titulo: t('atividade.col_tipo'), classe: 'mono' },
    { chave: 'dono', titulo: t('atividade.col_dono'), classe: 'mono' },
    { chave: 'acessos', titulo: t('atividade.col_acessos'), formatar: formatarNumero },
  ];
  tab.vazio = t('atividade.sem_acessos');
  tab.linhas = p.top_itens;
}

function svgEl(tag, atributos = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) el.setAttribute(k, String(v));
  return el;
}

function limparFigura(fig) {
  fig.querySelectorAll('svg, p').forEach((el) => el.remove());
}

function barrasVerticais(fig, pares) {
  limparFigura(fig);
  if (!pares.length) { fig.append(h('p', { class: 'fraco' }, t('atividade.sem_dado'))); return; }
  const L = 320; const A = 140; const margem = 24; const base = A - 20;
  const max = Math.max(1, ...pares.map(([, n]) => n));
  const svg = svgEl('svg', { viewBox: `0 0 ${L} ${A}`, role: 'img', 'aria-label': `${pares.length} ${t('atividade.pontos')}` });
  const largura = (L - margem) / pares.length;
  pares.forEach(([rotulo, n], i) => {
    const alt = Math.round((base - 10) * n / max);
    const x = margem + i * largura;
    const r = svgEl('rect', { class: 'barra', x: x + 1, y: base - alt, width: Math.max(1, largura - 2), height: alt });
    r.append(svgEl('title'));
    r.firstChild.textContent = `${rotulo}: ${n}`;
    svg.append(r);
    if (pares.length <= 16 || i % Math.ceil(pares.length / 8) === 0) {
      const tx = svgEl('text', { x: x + largura / 2, y: A - 6, 'text-anchor': 'middle' });
      tx.textContent = rotulo;
      svg.append(tx);
    }
  });
  const ty = svgEl('text', { x: 2, y: 12 });
  ty.textContent = formatarNumero(max);
  svg.append(ty);
  fig.append(svg);
}

function barrasHorizontais(fig, pares) {
  limparFigura(fig);
  if (!pares.length) { fig.append(h('p', { class: 'fraco' }, t('atividade.sem_dado'))); return; }
  const L = 320; const linha = 16; const A = pares.length * linha + 8; const esq = 150;
  const max = Math.max(1, ...pares.map(([, n]) => n));
  const svg = svgEl('svg', { viewBox: `0 0 ${L} ${A}`, role: 'img', 'aria-label': `${pares.length} ${t('atividade.tipos')}` });
  pares.forEach(([rotulo, n], i) => {
    const y = 4 + i * linha;
    const larg = Math.round((L - esq - 40) * n / max);
    const tx = svgEl('text', { class: 'rotulo-tipo', x: esq - 6, y: y + 11, 'text-anchor': 'end' });
    tx.textContent = rotulo;
    const r = svgEl('rect', { class: 'barra', x: esq, y: y + 2, width: Math.max(1, larg), height: linha - 5 });
    const tn = svgEl('text', { x: esq + larg + 4, y: y + 11 });
    tn.textContent = formatarNumero(n);
    svg.append(tx, r, tn);
  });
  fig.append(svg);
}

/* ---------- relatórios ---------- */
function opcoesTipo() { return tipos.map((x) => ({ valor: x.tipo, rotulo: t(`relatorios.tipo_${x.tipo}`) })); }

function montarRelatorios() {
  if (limites) {
    document.getElementById('relatorios-limites').textContent = t('relatorios.limites', { meses: Math.round(limites.janela_dias / 30.5), linhas: formatarNumero(limites.linhas_max), hora: limites.por_tipo_por_hora });
  }
  const area = document.getElementById('relatorios-pedir');
  const tipo = seletor('tipo', opcoesTipo(), tipos[0]?.tipo || 'membros');
  tipo.id = 'relatorio-tipo';
  const jan = seletor('janela', JANELAS.map(([v, r]) => ({ valor: v, rotulo: r })), '30');
  jan.id = 'relatorio-janela';
  const email = h('input', { type: 'checkbox', id: 'relatorio-email' });
  const bt = h('button', { type: 'button', class: 'primario', id: 'relatorio-gerar' }, t('relatorios.gerar'));
  bt.addEventListener('click', async () => {
    aviso().limpar();
    const ate = new Date();
    const desde = new Date(ate.getTime() - Number(jan.value) * 86400000);
    bt.disabled = true;
    const r = await enviar('/api/relatorios', { tipo: tipo.value, desde: desde.toISOString(), ate: ate.toISOString(), email: email.checked });
    bt.disabled = false;
    if (r.status !== 201) { aviso().erro(mensagemDe(r)); return; }
    aviso().ok(t('relatorios.pedido', { tipo: t(`relatorios.tipo_${tipo.value}`) }));
    await carregarRelatorios();
  });
  area.append(filtro(t('relatorios.tipo'), tipo).el, filtro(t('atividade.janela'), jan).el,
    h('label', { class: 'caixa' }, email, ' ', t('relatorios.por_email')), bt);
  const tab = document.getElementById('tabela-relatorios');
  tab.colunas = [
    { chave: 'criado_em', titulo: t('relatorios.col_quando'), formatar: (v) => formatarData(v) },
    { chave: 'parametros', titulo: t('relatorios.tipo'), formatar: (v) => t(`relatorios.tipo_${v?.tipo || ''}`) },
    { chave: 'estado', titulo: t('campo.estado'), formatar: (v) => marcador(t(`relatorios.estado_${v}`), v === 'concluido' ? 'ok' : (v === 'falhou' ? 'falha' : 'info')) },
    { chave: 'resultado', titulo: t('relatorios.col_linhas'), formatar: (v) => (v?.linhas === undefined ? '' : `${formatarNumero(v.linhas)}${v.truncado ? ' ' + t('relatorios.truncado') : ''}`) },
    { chave: 'id', titulo: t('relatorios.col_csv'), formatar: (v, l) => (l.estado === 'concluido' ? h('a', { href: `/api/relatorios/${v}/csv`, download: '' }, 'CSV') : (l.erro || l.mensagem || '')) },
  ];
  tab.vazio = t('relatorios.vazio');
  setInterval(() => { if (document.visibilityState === 'visible') carregarRelatorios(); }, 5000);
}

async function carregarRelatorios() {
  const r = await obter('/api/relatorios?limite=20');
  const tab = document.getElementById('tabela-relatorios');
  if (r.status !== 200) { tab.linhas = []; return; }
  tab.linhas = r.json.itens;
}

/* ---------- agendas ---------- */
function montarAgendas() {
  const area = document.getElementById('agendas-pedir');
  const tipo = seletor('tipo', opcoesTipo(), tipos[0]?.tipo || 'membros');
  tipo.id = 'agenda-tipo';
  const per = seletor('periodicidade', PERIODICIDADES.map((p) => ({ valor: p, rotulo: t(`relatorios.per_${p}`) })), 'semanal');
  per.id = 'agenda-periodicidade';
  const hora = h('input', { type: 'number', id: 'agenda-hora', min: 0, max: 23, value: 6, style: 'width:5rem' });
  const email = h('input', { type: 'checkbox', id: 'agenda-email', checked: true });
  const bt = h('button', { type: 'button', class: 'primario', id: 'agenda-criar' }, t('relatorios.agendar'));
  bt.addEventListener('click', async () => {
    aviso().limpar();
    bt.disabled = true;
    const r = await enviar('/api/relatorios/agendas', { tipo: tipo.value, periodicidade: per.value, hora: Number(hora.value) || 0, email: email.checked });
    bt.disabled = false;
    if (r.status !== 201) { aviso().erro(mensagemDe(r)); return; }
    aviso().ok(t('relatorios.agendado', { nome: r.json.nome }));
    await carregarAgendas();
  });
  area.append(filtro(t('relatorios.tipo'), tipo).el, filtro(t('relatorios.periodicidade'), per).el,
    filtro(t('relatorios.hora'), hora).el, h('label', { class: 'caixa' }, email, ' ', t('relatorios.por_email')), bt);
  const tab = document.getElementById('tabela-agendas');
  tab.colunas = [
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'cron', titulo: 'cron', classe: 'mono' },
    { chave: 'proxima_em', titulo: t('relatorios.col_proxima'), formatar: (v) => (v ? formatarData(v) : '—') },
    { chave: 'ultimo_estado', titulo: t('relatorios.col_ultimo'), formatar: (v) => (v ? t(`relatorios.estado_${v}`) : '—') },
    { chave: 'parametros', titulo: t('relatorios.por_email'), formatar: (v) => (v?.email ? t('geral.sim') : t('geral.nao')) },
  ];
  tab.acoes = () => [{ id: 'rodar', rotulo: t('relatorios.rodar_agora') }, { id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' }];
  tab.vazio = t('relatorios.agendas_vazio');
  tab.addEventListener('acao', async (e) => {
    const a = e.detail.linha;
    if (e.detail.id === 'rodar') {
      const r = await enviar(`/api/agendas/${a.id}/rodar-agora`);
      if (r.status === 201) { aviso().ok(t('relatorios.pedido', { tipo: a.nome })); await carregarRelatorios(); } else aviso().erro(mensagemDe(r));
      return;
    }
    if (!(await confirmar(t('acao.apagar'), t('relatorios.apagar_confirma', { nome: a.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/agendas/${a.id}`);
    if (r.status === 204) { await carregarAgendas(); aviso().ok(t('relatorios.agenda_apagada', { nome: a.nome })); } else aviso().erro(mensagemDe(r));
  });
}

async function carregarAgendas() {
  const r = await obter('/api/relatorios/agendas');
  const tab = document.getElementById('tabela-agendas');
  if (r.status !== 200) { tab.linhas = []; return; }
  tab.linhas = r.json.itens;
}
