/* plat — tela /plataforma (item L0-07-f-console-plataforma; ADR 0002 seção 10): console do superadmin, fora de
   qualquer inquilino. GET/POST /api/plataforma/inquilinos, GET /inquilinos/{id}, PUT /inquilinos/{id}/cotas,
   POST /inquilinos/{id}/suspender (com mensagem para os membros) e /reativar, POST
   /inquilinos/{id}/admins/{uid}/2fa/desativar, DELETE /inquilinos/{id}, GET /fila, GET /eventos.
   Só quem GET /api/eu diz superadmin=true chega aqui (a API responde 404 a todo o resto); nunca "entrar como"
   membro — cada ação do operador sai com evento na trilha da plataforma, mostrada no fim da tela. */
import { obter, enviar, alterar, apagar, mensagemDe, consulta } from '../base/api.js';
import { h, limpar, botaoCopiar, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao, semPermissao } from './sessao.js';

const MB = 1024 * 1024;
const LIMITE_EVENTOS = 25;
const eventosFiltro = { tipo: '', limite: LIMITE_EVENTOS, deslocamento: 0 };
let inquilinos = [];

await carregar();
const usuario = await exigirSessao();
if (usuario && !usuario.superadmin) semPermissao('superadmin');
else if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/plataforma' });
  const novo = h('button', { type: 'button', class: 'primario', id: 'novo' }, t('plataforma.novo'));
  novo.addEventListener('click', () => abrirNovo());
  document.getElementById('ferramentas').append(novo);
  cabecalho(t('plataforma.titulo'));
  montarTabela();
  montarEventos();
  await Promise.all([carregarInquilinos(), carregarFila(), carregarEventos()]);
}

function aviso() { return document.getElementById('aviso'); }
function mb(bytes) { return formatarNumero(Math.round((bytes || 0) / MB)); }
function dataOuTraco(v) { return v ? formatarData(v) : '—'; }

function estadoDe(i) {
  if (i.ativo) return marcador(t('plataforma.ativo'), 'ok');
  const m = i.suspensao?.mensagem;
  const el = marcador(t('plataforma.suspenso'), 'falha');
  if (m) el.title = m;
  return el;
}

// ---------------------------------------------------------------- inquilinos
function montarTabela() {
  const tab = document.getElementById('tabela');
  tab.colunas = [
    { chave: 'slug', titulo: t('plataforma.slug'), classe: 'mono' },
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'ativo', titulo: t('campo.estado'), formatar: (_, i) => estadoDe(i) },
    { chave: 'usuarios', titulo: t('plataforma.col_usuarios'), formatar: (_, i) => `${formatarNumero(i.usuarios_ativos)} / ${formatarNumero(i.cota_usuarios)}` },
    { chave: 'bytes_usados', titulo: t('plataforma.col_armazenamento'), formatar: (_, i) => `${mb(i.bytes_usados)} / ${mb(i.cota_bytes)}` },
    { chave: 'itens', titulo: t('plataforma.col_itens'), formatar: (_, i) => `${formatarNumero(i.itens)} / ${formatarNumero(i.cota_itens)}` },
    { chave: 'jobs_pendentes', titulo: t('plataforma.col_jobs'), formatar: (_, i) => `${formatarNumero(i.jobs_pendentes)} / ${formatarNumero(i.jobs_rodando)}` },
    { chave: 'ultimo_acesso', titulo: t('usuario.ultimo_acesso'), formatar: dataOuTraco },
  ];
  tab.acoes = (i) => {
    const a = [{ id: 'cotas', rotulo: t('plataforma.cotas') }, { id: '2fa', rotulo: t('plataforma.admins_2fa') }];
    if (i.slug !== 'plataforma') {
      a.push(i.ativo ? { id: 'suspender', rotulo: t('plataforma.suspender'), classe: 'perigo' } : { id: 'reativar', rotulo: t('plataforma.reativar') });
      a.push({ id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' });
    }
    return a;
  };
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
}

async function carregarInquilinos() {
  const r = await obter('/api/plataforma/inquilinos');
  if (r.status !== 200) { aviso().erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); return; }
  inquilinos = r.json;
  document.getElementById('tabela').linhas = inquilinos;
  cabecalho(t('plataforma.titulo'), { contagem: inquilinos.length });
}

async function recarregar() {
  await Promise.all([carregarInquilinos(), carregarFila(), carregarEventos()]);
}

async function acao(id, i) {
  aviso().limpar();
  if (id === 'cotas') return abrirCotas(i);
  if (id === '2fa') return abrirAdmins(i);
  if (id === 'suspender') return abrirSuspender(i);
  if (id === 'reativar') {
    const r = await enviar(`/api/plataforma/inquilinos/${i.id}/reativar`);
    if (r.status === 204) { await recarregar(); aviso().ok(t('plataforma.reativado', { slug: i.slug })); } else aviso().erro(mensagemDe(r));
    return;
  }
  if (id === 'apagar') {
    if (!(await confirmar(t('acao.apagar'), t('plataforma.apagar_confirma', { slug: i.slug }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/plataforma/inquilinos/${i.id}`);
    if (r.status === 204) { await recarregar(); aviso().ok(t('plataforma.apagado', { slug: i.slug })); } else aviso().erro(mensagemDe(r));
  }
}

function camposCotas(c = {}) {
  return [
    { nome: 'cota_mb', rotulo: t('org.cota_armazenamento_mb'), tipo: 'numero', padrao: c.cota_bytes ? Math.round(c.cota_bytes / MB) : 20480, atributos: { min: 100, step: 1 } },
    { nome: 'cota_usuarios', rotulo: t('org.cota_usuarios'), tipo: 'numero', padrao: c.cota_usuarios ?? 2000, atributos: { min: 1, step: 1 } },
    { nome: 'cota_itens', rotulo: t('plataforma.cota_itens'), tipo: 'numero', padrao: c.cota_itens ?? 100000, atributos: { min: 1, step: 1 } },
    { nome: 'cota_jobs_dia', rotulo: t('plataforma.cota_jobs_dia'), tipo: 'numero', padrao: c.cota_jobs_dia ?? 1000, atributos: { min: 1, step: 1 } },
    { nome: 'cota_jobs_simultaneos', rotulo: t('plataforma.cota_jobs_simultaneos'), tipo: 'numero', padrao: c.cota_jobs_simultaneos ?? 2, atributos: { min: 1, step: 1 } },
    { nome: 'cota_agendas', rotulo: t('plataforma.cota_agendas'), tipo: 'numero', padrao: c.cota_agendas ?? 50, atributos: { min: 1, step: 1 } },
  ];
}

function cotasDe(v) {
  const c = {};
  if (v.cota_mb !== null && v.cota_mb !== undefined) c.cota_bytes = Math.round(v.cota_mb * MB);
  for (const k of ['cota_usuarios', 'cota_itens', 'cota_jobs_dia', 'cota_jobs_simultaneos', 'cota_agendas']) {
    if (v[k] !== null && v[k] !== undefined) c[k] = v[k];
  }
  return c;
}

function abrirNovo() {
  const painel = document.getElementById('painel');
  const f = h('plat-formulario', { autocompletar: 'off' });
  f.campos = [
    { nome: 'slug', rotulo: t('plataforma.slug'), tipo: 'texto', obrigatorio: true, ajuda: t('plataforma.slug_ajuda'), atributos: { maxlength: 39, pattern: '^[a-z0-9][a-z0-9-]{1,38}$', autocapitalize: 'none', spellcheck: 'false' } },
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: 200 } },
    { nome: 'admin_login', rotulo: t('plataforma.admin_login'), tipo: 'texto', obrigatorio: true, padrao: 'admin', atributos: { maxlength: 128, autocapitalize: 'none', spellcheck: 'false' } },
    { nome: 'admin_nome', rotulo: t('plataforma.admin_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: 200 } },
    ...camposCotas(),
  ];
  f.botoes = [{ id: 'criar', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    const corpo = { slug: (v.slug || '').trim().toLowerCase(), nome: v.nome, admin_login: v.admin_login, admin_nome: v.admin_nome, cotas: cotasDe(v) };
    f.ocupado = true;
    const r = await enviar('/api/plataforma/inquilinos', corpo);
    f.ocupado = false;
    if (r.status === 201) {
      painel.fechar('ok');
      await recarregar();
      mostrarSenhaTemporaria(r.json.slug, r.json.admin.login, r.json.senha_temporaria);
      return;
    }
    const campoPorErro = { slug_existente: 'slug', slug_reservado: 'slug' };
    const campo = campoPorErro[r.json?.erro] || (r.json?.detalhe?.campo === 'slug' ? 'slug' : null);
    if (campo) f.erro(campo, mensagemDe(r)); else f.mensagem(mensagemDe(r), 'erro');
  });
  painel.abrir({ titulo: t('plataforma.novo'), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

function mostrarSenhaTemporaria(slug, login, senha) {
  const painel = document.getElementById('painel');
  const cod = h('code', { class: 'codigo grande', id: 'senha-temporaria' }, senha);
  painel.abrir({
    titulo: t('usuarios.senha_temporaria'),
    corpo: h('div', {}, h('p', {}, t('plataforma.senha_temporaria_texto', { slug, login })), cod,
      h('div', { class: 'botoes espaco' }, botaoCopiar(senha, cod, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })),
      h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('usuarios.senha_uma_vez'))),
    botoes: [{ id: 'ok', rotulo: t('acao.fechar'), classe: 'primario' }],
  });
}

async function abrirCotas(i) {
  const painel = document.getElementById('painel');
  const r = await obter(`/api/plataforma/inquilinos/${i.id}`);
  if (r.status !== 200) { aviso().erro(mensagemDe(r)); return; }
  const d = r.json;
  const f = h('plat-formulario', { autocompletar: 'off' });
  f.campos = [
    { nome: 'uso', rotulo: t('plataforma.uso'), tipo: 'info', padrao: t('plataforma.uso_texto', { usuarios: formatarNumero(d.uso.usuarios_ativos), mb: mb(d.uso.bytes_usados), itens: formatarNumero(d.uso.itens), jobs: formatarNumero(d.uso.jobs_hoje), agendas: formatarNumero(d.uso.agendas) }) },
    ...camposCotas(d.cotas),
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const rr = await alterar(`/api/plataforma/inquilinos/${i.id}/cotas`, cotasDe(e.detail.valores));
    f.ocupado = false;
    if (rr.status === 200) { painel.fechar('ok'); await recarregar(); aviso().ok(t('plataforma.cotas_salvas', { slug: i.slug })); return; }
    f.mensagem(mensagemDe(rr), 'erro');
  });
  painel.abrir({ titulo: t('plataforma.cotas_de', { slug: i.slug }), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

function abrirSuspender(i) {
  const painel = document.getElementById('painel');
  const f = h('plat-formulario', { autocompletar: 'off' });
  f.campos = [
    { nome: 'mensagem', rotulo: t('plataforma.mensagem'), tipo: 'area', ajuda: t('plataforma.mensagem_ajuda'), atributos: { maxlength: 300, rows: 3 } },
  ];
  f.botoes = [{ id: 'suspender', rotulo: t('plataforma.suspender'), tipo: 'submit', classe: 'perigo' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const r = await enviar(`/api/plataforma/inquilinos/${i.id}/suspender`, { mensagem: (e.detail.valores.mensagem || '').trim() || null });
    f.ocupado = false;
    if (r.status === 204) { painel.fechar('ok'); await recarregar(); aviso().ok(t('plataforma.suspendido', { slug: i.slug })); return; }
    f.mensagem(mensagemDe(r), 'erro');
  });
  painel.abrir({ titulo: t('plataforma.suspender_de', { slug: i.slug }), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

async function abrirAdmins(i) {
  const painel = document.getElementById('painel');
  const r = await obter(`/api/plataforma/inquilinos/${i.id}`);
  if (r.status !== 200) { aviso().erro(mensagemDe(r)); return; }
  const tab = h('plat-tabela', { id: 'admins-tabela', legenda: t('plataforma.admins_2fa') });
  tab.colunas = [
    { chave: 'login', titulo: t('campo.login'), classe: 'mono' },
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'totp_ativo', titulo: t('usuario.2fa'), formatar: (v) => (v ? t('geral.sim') : t('geral.nao')) },
    { chave: 'ultimo_login', titulo: t('usuario.ultimo_acesso'), formatar: dataOuTraco },
  ];
  tab.acoes = (a) => (a.totp_ativo && i.slug !== 'plataforma' ? [{ id: '2fa', rotulo: t('usuarios.desligar_2fa'), classe: 'perigo' }] : []);
  tab.linhas = r.json.admins;
  tab.addEventListener('acao', async (e) => {
    const a = e.detail.linha;
    if (!(await confirmar(t('usuarios.desligar_2fa'), t('plataforma.desligar_2fa_confirma', { login: a.login, slug: i.slug }), { perigo: true }))) return;
    const rr = await enviar(`/api/plataforma/inquilinos/${i.id}/admins/${a.id}/2fa/desativar`);
    if (rr.status !== 204) { aviso().erro(mensagemDe(rr)); return; }
    painel.fechar('ok');
    await recarregar();
    aviso().ok(t('usuarios.2fa_desligado', { login: a.login }));
  });
  painel.abrir({
    titulo: t('plataforma.admins_de', { slug: i.slug }),
    corpo: h('div', {}, h('p', { class: 'fraco' }, t('plataforma.admins_ajuda')), tab),
    botoes: [{ id: 'fechar', rotulo: t('acao.fechar') }],
  });
}

// ---------------------------------------------------------------- fila
async function carregarFila() {
  const r = await obter('/api/plataforma/fila');
  const total = document.getElementById('fila-total');
  const tab = document.getElementById('fila-tabela');
  const workers = document.getElementById('fila-workers');
  limpar(total); limpar(workers);
  if (r.status !== 200) { total.append(h('span', { class: 'fraco' }, mensagemDe(r))); return; }
  const f = r.json;
  for (const k of ['pendente', 'rodando', 'concluido_24h', 'falhou_24h', 'cancelado_24h']) {
    total.append(h('span', { class: 'marcador', id: `fila-${k}` }, `${t(`plataforma.fila_${k}`)}: ${formatarNumero(f.total[k] || 0)}`));
  }
  if (f.mais_antigo_pendente_em) total.append(h('span', { class: 'fraco' }, t('plataforma.fila_mais_antigo', { quando: formatarData(f.mais_antigo_pendente_em) })));
  tab.colunas = [
    { chave: 'slug', titulo: t('plataforma.slug'), classe: 'mono' },
    { chave: 'pendente', titulo: t('plataforma.fila_pendente'), formatar: formatarNumero },
    { chave: 'rodando', titulo: t('plataforma.fila_rodando'), formatar: formatarNumero },
    { chave: 'concluido_24h', titulo: t('plataforma.fila_concluido_24h'), formatar: formatarNumero },
    { chave: 'falhou_24h', titulo: t('plataforma.fila_falhou_24h'), formatar: formatarNumero },
  ];
  tab.chave = 'slug';
  tab.vazio = t('plataforma.fila_vazia');
  tab.linhas = f.por_inquilino;
  if (!f.workers.length) { workers.append(h('p', { class: 'fraco' }, t('plataforma.sem_workers'))); return; }
  const ul = h('ul', { id: 'workers' });
  for (const w of f.workers) {
    ul.append(h('li', {}, marcador(w.vivo ? t('plataforma.worker_vivo') : t('plataforma.worker_parado'), w.vivo ? 'ok' : 'falha'), ' ',
      h('span', { class: 'mono' }, w.nome), ' ', h('span', { class: 'fraco' }, t('plataforma.worker_detalhe', { processos: w.processos, rodando: w.rodando, quando: formatarData(w.heartbeat_em) }))));
  }
  workers.append(ul);
}

// ---------------------------------------------------------------- eventos
function montarEventos() {
  const filtros = document.getElementById('eventos-filtros');
  const busca = h('plat-busca', { rotulo: t('plataforma.eventos_tipo') });
  busca.addEventListener('buscar', (e) => { eventosFiltro.tipo = (e.detail.q || '').trim(); eventosFiltro.deslocamento = 0; carregarEventos(); });
  filtros.append(busca);
  const tab = document.getElementById('eventos-tabela');
  tab.colunas = [
    { chave: 'em', titulo: t('plataforma.ev_quando'), formatar: (v) => formatarData(v) },
    { chave: 'tipo', titulo: t('plataforma.ev_tipo'), classe: 'mono' },
    { chave: 'ator', titulo: t('log.ator'), formatar: (v) => (v ? v.login : '—') },
    { chave: 'alvo_id', titulo: t('log.alvo'), formatar: (v, l) => (l.alvo_tipo ? `${l.alvo_tipo} ${v ?? ''}` : '—') },
    { chave: 'propriedades', titulo: t('log.propriedades'), classe: 'mono', formatar: (v) => (v && Object.keys(v).length ? JSON.stringify(v) : '') },
  ];
  tab.vazio = t('plataforma.eventos_vazio');
  document.getElementById('eventos-paginacao').addEventListener('mudar', (e) => { eventosFiltro.deslocamento = e.detail.deslocamento; carregarEventos(); });
}

async function carregarEventos() {
  const r = await obter(`/api/plataforma/eventos${consulta(eventosFiltro)}`);
  const tab = document.getElementById('eventos-tabela');
  if (r.status !== 200) { tab.linhas = []; aviso().erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); return; }
  tab.linhas = r.json.itens;
  document.getElementById('eventos-paginacao').atualizar({ total: r.json.total, limite: LIMITE_EVENTOS, deslocamento: eventosFiltro.deslocamento });
}
