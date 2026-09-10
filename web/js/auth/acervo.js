/* plat — tela /admin/acervo (item UX-06; fecha UX-10): as fontes do acervo da casa que têm licença escrita
   (GET /api/acervo, com busca e domínio), a ficha de procedência de cada uma (GET /api/acervo/{fonte_id}: endereço,
   licença, método, frescor, sha256, comando de reexecução, endpoints vivos) e "adicionar ao catálogo"
   (POST /api/acervo/{fonte_id}/adicionar) — que cria um item deste inquilino apontando para a fonte. Fonte marcada
   com risco de dado pessoal (LGPD) responde 409 na primeira tentativa: a tela mostra o motivo e pede confirmação
   explícita antes de repetir com confirma_risco_pii (nunca confirma sozinha). Estados por <plat-estado>. */
import { obter, enviar, mensagemDe, consulta } from '../base/api.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { estadoDeLista, eventoRegistrado, filtro, seletor } from './comum.js';

const LIMITE = 50;
const filtros = { q: '', dominio: '', limite: LIMITE, deslocamento: 0 };
let seqLista = 0;
let dominios = new Set();

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.registrar_fonte' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/acervo' });
  cabecalho(t('acervo.titulo'), { contagem: 0 });
  montarFiltros();
  montarTabela();
  document.getElementById('estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'tentar') carregarLista();
    if (ev.detail.id === 'limpar') { filtros.q = ''; filtros.dominio = ''; filtros.deslocamento = 0; document.querySelector('#filtros plat-busca').valor = ''; document.querySelector('#filtros select[name=dominio]').value = ''; carregarLista(); }
  });
  await carregarLista();
}

function montarFiltros() {
  const area = document.getElementById('filtros');
  const busca = h('plat-busca', { rotulo: t('acervo.buscar') });
  busca.addEventListener('buscar', (e) => { filtros.q = e.detail.q; filtros.deslocamento = 0; carregarLista(); });
  const dom = seletor('dominio', [{ valor: '', rotulo: t('geral.todos') }], '');
  dom.addEventListener('change', () => { filtros.dominio = dom.value; filtros.deslocamento = 0; carregarLista(); });
  area.append(busca, filtro(t('acervo.dominio'), dom).el);
  document.getElementById('paginacao').addEventListener('mudar', (e) => { filtros.deslocamento = e.detail.deslocamento; carregarLista(); });
}

function pontuacao(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  return marcador(`${formatarNumero(Math.round(n * 10) / 10)}/10`, n >= 8 ? 'ok' : (n >= 5 ? 'atencao' : 'falha'));
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  tab.chave = 'fonte_id';
  tab.colunas = [
    { chave: 'nome', titulo: t('campo.nome'), formatar: (v, f) => h('span', {}, h('strong', {}, v), f.orgao ? h('span', { class: 'ajuda' }, ` · ${f.orgao}`) : null) },
    { chave: 'dominio', titulo: t('acervo.dominio') },
    { chave: 'licenca', titulo: t('acervo.licenca'), classe: 'mono' },
    { chave: 'frescor', titulo: t('acervo.frescor'), formatar: (v) => v || '—' },
    { chave: 'numero_tabelas', titulo: t('acervo.tabelas'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'registros_estimados', titulo: t('acervo.registros'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'procedencia_pontuacao', titulo: t('acervo.procedencia'), formatar: pontuacao },
  ];
  tab.acoes = () => [{ id: 'ficha', rotulo: t('acervo.ficha') }, ...(tem('conteudo.criar') ? [{ id: 'adicionar', rotulo: t('acervo.adicionar'), classe: 'primario' }] : [])];
  tab.addEventListener('acao', (e) => { if (e.detail.id === 'ficha') abrirFicha(e.detail.linha); else adicionar(e.detail.linha); });
}

async function carregarLista() {
  const estado = document.getElementById('estado');
  const tab = document.getElementById('tabela');
  const seq = ++seqLista;
  if (!tab.linhas.length) estadoDeLista(estado, tab, null);
  const r = await obter(`/api/acervo${consulta(filtros)}`);
  if (seq !== seqLista) return;
  const filtrado = Boolean(filtros.q || filtros.dominio);
  estadoDeLista(estado, tab, r, { vazio: filtrado ? t('acervo.vazio_filtro') : t('acervo.vazio'), acoes: filtrado ? [{ id: 'limpar', rotulo: t('acervo.limpar_filtros') }] : [] });
  if (r.status !== 200) return;
  const itens = r.json.itens || [];
  tab.linhas = itens;
  for (const f of itens) if (f.dominio) dominios.add(f.dominio);
  const dom = document.querySelector('#filtros select[name=dominio]');
  const atuais = new Set([...dom.options].map((o) => o.value));
  for (const d of [...dominios].sort()) if (!atuais.has(d)) dom.append(h('option', { value: d }, d));
  const total = r.json.total ?? itens.length;
  document.getElementById('paginacao').atualizar({ total, limite: LIMITE, deslocamento: filtros.deslocamento });
  cabecalho(t('acervo.titulo'), { contagem: total });
}

function linhaFicha(rotulo, valor, { mono = false } = {}) {
  const vazio = valor === null || valor === undefined || valor === '';
  const conteudo = vazio ? h('em', { class: 'fraco' }, t('acervo.nao_registrado')) : (valor instanceof Node || typeof valor === 'string' ? valor : String(valor));
  return [h('dt', {}, rotulo), h('dd', { class: mono ? 'mono' : '' }, conteudo)];
}

async function abrirFicha(f) {
  const painel = document.getElementById('painel');
  const estado = h('plat-estado');
  const corpo = h('div', {}, estado);
  painel.abrir({ titulo: f.nome, corpo, botoes: [{ id: 'ok', rotulo: t('acao.fechar') }] }).then(() => {});
  estado.carregando();
  const r = await obter(`/api/acervo/${encodeURIComponent(f.fonte_id)}`);
  if (r.status !== 200) { estado.erro(r, []); return; }
  const d = r.json;
  estado.limpar();
  const dl = h('dl', { class: 'espaco ficha-acervo' },
    ...linhaFicha(t('acervo.orgao'), d.orgao),
    ...linhaFicha(t('acervo.dominio'), d.dominio),
    ...linhaFicha(t('acervo.licenca'), d.licenca, { mono: true }),
    ...linhaFicha(t('acervo.url'), d.url ? h('a', { href: d.url, rel: 'noopener', target: '_blank' }, d.url) : null),
    ...linhaFicha(t('acervo.url_http'), d.url_http ? `${d.url_http}${d.url_conferida_em ? ` · ${formatarData(d.url_conferida_em)}` : ''}` : null),
    ...linhaFicha(t('acervo.data_dado'), d.data_dado),
    ...linhaFicha(t('acervo.data_acesso'), d.data_acesso ? formatarData(d.data_acesso) : null),
    ...linhaFicha(t('acervo.frescor'), d.frescor),
    ...linhaFicha(t('acervo.proxima_verificacao'), d.proxima_verificacao ? formatarData(d.proxima_verificacao) : null),
    ...linhaFicha(t('acervo.metodo'), d.metodo),
    ...linhaFicha(t('acervo.confianca'), d.confianca),
    ...linhaFicha(t('acervo.script'), d.script_gerador, { mono: true }),
    ...linhaFicha(t('acervo.sha256'), d.sha256, { mono: true }),
    ...linhaFicha(t('acervo.reexecucao'), d.comando_reexecucao, { mono: true }),
    ...linhaFicha(t('acervo.tabelas'), formatarNumero(d.numero_tabelas)),
    ...linhaFicha(t('acervo.registros'), formatarNumero(d.registros_estimados)),
    ...linhaFicha(t('acervo.procedencia'), pontuacao(d.procedencia_pontuacao)),
  );
  corpo.append(dl);
  if (d.completude_texto) corpo.append(h('p', { class: 'ajuda' }, d.completude_texto));
  if (d.limites) corpo.append(h('p', { class: 'ajuda' }, `${t('acervo.limites')}: ${d.limites}`));
  const endpoints = Array.isArray(d.endpoints) ? d.endpoints : [];
  if (endpoints.length) {
    const tab = h('plat-tabela', { legenda: t('acervo.endpoints') });
    tab.chave = 'url';
    tab.colunas = [
      { chave: 'url', titulo: t('acervo.url'), classe: 'mono', formatar: (v) => (v || '').slice(0, 90) },
      { chave: 'vivo', titulo: t('acervo.vivo'), formatar: (v) => marcador(v ? t('geral.sim') : t('geral.nao'), v ? 'ok' : 'falha') },
      { chave: 'http', titulo: 'HTTP', classe: 'mono' },
      { chave: 'testado_em', titulo: t('acervo.testado_em'), formatar: (v) => (v ? formatarData(v) : '—') },
    ];
    tab.linhas = endpoints;
    corpo.append(h('h3', {}, t('acervo.endpoints')), tab);
  }
  if (tem('conteudo.criar')) {
    const bt = h('button', { type: 'button', class: 'primario', id: 'ficha-adicionar' }, t('acervo.adicionar'));
    bt.addEventListener('click', () => adicionar(f, bt));
    corpo.append(h('div', { class: 'botoes espaco' }, bt));
  }
}

async function adicionar(f, botao = null, confirmaPii = false) {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  if (botao) botao.disabled = true;
  const r = await enviar(`/api/acervo/${encodeURIComponent(f.fonte_id)}/adicionar`, confirmaPii ? { confirma_risco_pii: true } : {});
  if (botao) botao.disabled = false;
  if (r.status === 201) {
    document.getElementById('painel').fechar('ok');
    limpar(aviso);
    aviso.mostrar(t('acervo.adicionado', { nome: f.nome }), 'ok');
    aviso.append(' ', h('a', { href: `/conteudo/${encodeURIComponent(r.json.id)}` }, t('acervo.abrir_item')));
    await eventoRegistrado();
    return;
  }
  if (r.status === 409 && r.json.erro && String(r.json.erro).includes('pii') && !confirmaPii) {
    const motivo = r.json.detalhe?.motivo || r.json.detalhe?.risco_pii_motivo || r.json.mensagem || '';
    const ok = await confirmar(t('acervo.pii_titulo'), t('acervo.pii_texto', { nome: f.nome, motivo }), { ok: t('acervo.pii_confirmar'), perigo: true });
    if (ok) await adicionar(f, botao, true);
    return;
  }
  aviso.erro(`${t('acervo.erro_adicionar', { nome: f.nome })}: ${mensagemDe(r)}`);
}
