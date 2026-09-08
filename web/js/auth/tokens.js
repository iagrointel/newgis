/* plat — tela /admin/tokens (ADR 0002 seção 15.5): lista (com "todos do inquilino" se tokens.gerir_todos), novo token
   (escopos em caixas; admin:inquilino só para perfil admin; validade; referer; IP/CIDR), token mostrado uma única vez,
   renovar (24 h de sobreposição), revogar, aba Acessos (GET /api/tokens/{id}/log). */
import { obter, enviar, apagar, mensagemDe, consulta } from '../base/api.js';
import { h, botaoCopiar, marcador } from '../base/dom.js';
import { carregar, t, formatarData, diasAte } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { estadoDeLista, eventoRegistrado } from './comum.js';

const ESCOPOS = ['catalogo:ler', 'camada:ler', 'camada:editar', 'tiles:ler', 'jobs:executar', 'admin:inquilino'];
let todos = false;

await carregar();
const usuario = await exigirSessao({ privilegio: 'tokens.gerar' });
if (usuario) await iniciar();
pronto();
function config() { return usuario.inquilino?.config_publica?.auth || {}; }
function padraoDias() { const c = config(); return Number(c.token_padrao_dias) > 0 ? Number(c.token_padrao_dias) : 90; }
function maxDias() { const c = config(); return Number(c.token_max_dias) > 0 ? Number(c.token_max_dias) : 365; }

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/tokens' });
  const botoes = [];
  if (tem('tokens.gerir_todos')) {
    const cx = h('input', { type: 'checkbox', id: 'todos' });
    cx.addEventListener('change', () => { todos = cx.checked; carregarLista(); });
    botoes.push(h('label', { class: 'caixa' }, cx, t('tokens.todos_inquilino')));
  }
  const bt = h('button', { type: 'button', class: 'primario', id: 'novo' }, t('tokens.novo'));
  bt.addEventListener('click', () => abrirNovo());
  botoes.push(bt);
  cabecalho(t('tokens.titulo'), { contagem: 0, botoes });
  montarTabela();
  document.getElementById('estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'tentar') carregarLista();
    if (ev.detail.id === 'novo') abrirNovo();
  });
  await carregarLista();
}

function estadoToken(tk) {
  if (tk.revogado_em) return marcador(t('token.revogado'), 'falha');
  const d = diasAte(tk.expira_em);
  if (d !== null && d <= 0) return marcador(t('token.expirado'), 'falha');
  if (d !== null && d <= 7) return marcador(t('token.expira_em_dias', { n: d }), 'atencao');
  return marcador(t('token.valido'), 'ok');
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  const colunas = [
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'prefixo', titulo: t('token.prefixo'), classe: 'mono' },
    { chave: 'escopos', titulo: t('token.escopos'), formatar: (v) => (v || []).join(', '), classe: 'mono' },
    { chave: 'expira_em', titulo: t('token.expira'), formatar: (v) => formatarData(v) },
    { chave: 'ultimo_uso', titulo: t('token.ultimo_uso'), formatar: (v) => (v ? formatarData(v) : '—') },
    { chave: 'ultimo_ip', titulo: t('sessao.ip'), classe: 'mono', formatar: (v) => v || '' },
    { chave: 'restricao', titulo: t('token.restricoes'), formatar: (r) => restricoesTexto(r) },
    { chave: 'id', titulo: t('campo.estado'), formatar: (_, tk) => estadoToken(tk) },
  ];
  if (tem('tokens.gerir_todos')) colunas.splice(1, 0, { chave: 'dono', titulo: t('token.dono'), formatar: (d) => d?.login || '' });
  tab.colunas = colunas;
  tab.acoes = (tk) => {
    const a = [{ id: 'acessos', rotulo: t('token.acessos') }];
    const meu = !tk.dono || tk.dono.id === usuario.id;
    if (!tk.revogado_em) {
      if (meu) a.push({ id: 'renovar', rotulo: t('token.renovar') });
      a.push({ id: 'revogar', rotulo: t('token.revogar'), classe: 'perigo' });
    }
    return a;
  };
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
}

function restricoesTexto(r) {
  if (!r || typeof r !== 'object') return '';
  const p = [];
  if (Array.isArray(r.referer) && r.referer.length) p.push(`${t('token.referer')}: ${r.referer.length}`);
  if (Array.isArray(r.ip) && r.ip.length) p.push(`IP: ${r.ip.length}`);
  return p.join(' · ');
}

async function carregarLista() {
  const estado = document.getElementById('estado');
  const tab = document.getElementById('tabela');
  if (!tab.linhas.length) estadoDeLista(estado, tab, null);
  const r = await obter(`/api/tokens${consulta({ todos: todos ? '1' : '' })}`);
  estadoDeLista(estado, tab, r, { vazio: t('tokens.vazio'), acoes: [{ id: 'novo', rotulo: t('tokens.novo'), classe: 'primario' }] });
  if (r.status !== 200) { tab.linhas = []; return; }
  const itens = Array.isArray(r.json) ? r.json : (r.json.itens || []);
  tab.linhas = itens;
  cabecalho(t('tokens.titulo'), { contagem: itens.length });
}

function mostrarTokenUmaVez(json, titulo) {
  const painel = document.getElementById('painel');
  const cod = h('code', { class: 'codigo grande', id: 'token-valor' }, json.token);
  const exemplo = h('code', { class: 'codigo' }, `Authorization: Bearer ${json.token}`);
  painel.abrir({
    titulo,
    corpo: h('div', {},
      h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('token.uma_vez')),
      h('span', { class: 'campo-rotulo' }, t('token.valor')), cod,
      h('div', { class: 'botoes espaco' }, botaoCopiar(json.token, cod, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })),
      h('p', { class: 'fraco' }, t('token.expira_texto', { quando: formatarData(json.expira_em) })),
      h('span', { class: 'campo-rotulo' }, t('token.exemplo_uso')), exemplo,
      json.antigo_expira_em ? h('p', { class: 'fraco' }, t('token.antigo_expira', { quando: formatarData(json.antigo_expira_em) })) : null),
    botoes: [{ id: 'ok', rotulo: t('acao.fechar'), classe: 'primario' }],
  }).then(() => {});
}

async function acao(id, tk) {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  if (id === 'acessos') { await abrirAcessos(tk); return; }
  if (id === 'renovar') {
    if (!(await confirmar(t('token.renovar'), t('token.renovar_confirma', { nome: tk.nome })))) return;
    const r = await enviar(`/api/tokens/${tk.id}/renovar`);
    if (r.status !== 201) { aviso.erro(mensagemDe(r)); return; }
    await carregarLista();
    mostrarTokenUmaVez(r.json, t('token.renovado', { nome: tk.nome }));
    eventoRegistrado();
    return;
  }
  if (id === 'revogar') {
    if (!(await confirmar(t('token.revogar'), t('token.revogar_confirma', { nome: tk.nome }), { perigo: true, ok: t('token.revogar') }))) return;
    const r = await apagar(`/api/tokens/${tk.id}`);
    if (r.status === 204) { await carregarLista(); aviso.ok(t('token.revogado_ok', { nome: tk.nome })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
  }
}

function abrirNovo() {
  const painel = document.getElementById('painel');
  document.getElementById('aviso').limpar();
  const f = h('plat-formulario');
  const admin = usuario.perfil === 'admin';
  f.campos = [
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: 128 } },
    { nome: 'escopos', rotulo: t('token.escopos'), tipo: 'caixas', padrao: ['catalogo:ler'],
      opcoes: ESCOPOS.filter((e) => e !== 'admin:inquilino' || admin).map((e) => ({ valor: e, rotulo: `${e} — ${t(`escopo.${e}`)}` })), ajuda: t('token.escopos_ajuda') },
    { nome: 'validade_dias', rotulo: t('token.validade_dias'), tipo: 'numero', padrao: padraoDias(), atributos: { min: 1, max: maxDias(), step: 1 }, ajuda: t('token.validade_ajuda', { padrao: padraoDias(), max: maxDias() }) },
    { nome: 'referer', rotulo: t('token.referer'), tipo: 'lista', linhas: 3, ajuda: t('token.referer_ajuda') },
    { nome: 'ip', rotulo: t('token.ip'), tipo: 'lista', linhas: 3, ajuda: t('token.ip_ajuda') },
  ];
  f.botoes = [{ id: 'criar', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (!v.escopos.length) { f.erro('escopos', t('token.escolha_escopo')); return; }
    if (v.validade_dias !== null && (v.validade_dias < 1 || v.validade_dias > maxDias())) { f.erro('validade_dias', t('token.validade_fora', { max: maxDias() })); return; }
    const corpo = { nome: v.nome, escopos: v.escopos };
    if (v.validade_dias !== null) corpo.validade_dias = v.validade_dias;
    const restricao = {};
    if (v.referer.length) restricao.referer = v.referer.slice(0, 20);
    if (v.ip.length) restricao.ip = v.ip.slice(0, 20);
    if (Object.keys(restricao).length) corpo.restricao = restricao;
    f.ocupado = true;
    const r = await enviar('/api/tokens', corpo);
    f.ocupado = false;
    if (r.status === 201) { painel.fechar('ok'); await carregarLista(); mostrarTokenUmaVez(r.json, t('token.criado', { nome: v.nome })); eventoRegistrado(); return; }
    const campo = { validade_acima_do_maximo: 'validade_dias', escopo_invalido: 'escopos', escopo_fora_do_teto: 'escopos', limite_tokens: 'nome' }[r.json.erro];
    let m = mensagemDe(r);
    if (r.json.detalhe?.maximo_dias) m += ` (${t('token.maximo_dias', { n: r.json.detalhe.maximo_dias })})`;
    if (campo) f.erro(campo, m); else f.mensagem(m, 'erro');
  });
  painel.abrir({ titulo: t('tokens.novo'), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

async function abrirAcessos(tk) {
  const painel = document.getElementById('painel');
  const aviso = h('plat-aviso');
  const tab = h('plat-tabela', { legenda: t('token.acessos') });
  const pag = h('plat-paginacao');
  const LIMITE = 50;
  let deslocamento = 0;
  tab.colunas = [
    { chave: 'em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'ip', titulo: t('sessao.ip'), classe: 'mono' },
    { chave: 'metodo', titulo: t('log.metodo'), classe: 'mono' },
    { chave: 'rota', titulo: t('log.rota'), classe: 'mono', formatar: (v) => (v || '').slice(0, 80) },
    { chave: 'status', titulo: t('log.status'), classe: 'num' },
    { chave: 'bytes', titulo: t('log.bytes'), classe: 'num' },
    { chave: 'tempo_ms', titulo: t('log.tempo_ms'), classe: 'num' },
    { chave: 'resultado', titulo: t('log.resultado'), formatar: (v) => v || '' },
  ];
  tab.vazio = t('token.sem_acessos');
  async function carregarPagina() {
    const r = await obter(`/api/tokens/${tk.id}/log${consulta({ limite: LIMITE, deslocamento })}`);
    if (r.status !== 200) { aviso.erro(mensagemDe(r)); tab.linhas = []; return; }
    tab.linhas = r.json.itens || [];
    pag.atualizar({ total: r.json.total ?? tab.linhas.length, limite: LIMITE, deslocamento });
  }
  pag.addEventListener('mudar', (e) => { deslocamento = e.detail.deslocamento; carregarPagina(); });
  const detalhe = await obter(`/api/tokens/${tk.id}`);
  const resumo = detalhe.status === 200 ? h('p', { class: 'fraco' }, t('token.resumo_acessos', { n: detalhe.json.acessos_30d ?? 0, status: detalhe.json.ultimo_status ?? '—' })) : null;
  painel.abrir({ titulo: `${t('token.acessos')}: ${tk.nome}`, corpo: h('div', {}, resumo, aviso, tab, pag), botoes: [{ id: 'ok', rotulo: t('acao.fechar') }] }).then(() => {});
  await carregarPagina();
}
