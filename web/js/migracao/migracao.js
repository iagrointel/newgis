/* plat · migração de Portal — entrada da tela /migracao (item L2-08-a-leitor-portal-inventario).
   Módulos ES sem build; NUNCA ?v= nos imports (duas URLs do mesmo módulo = duas instâncias — regra da casa).
   A tela tem as duas metades que o item pede: a CONEXÃO (escolher o Portal registrado e, se preciso, trocar
   usuário e senha por token) e o INVENTÁRIO (o que existe no portal, por tipo, com contagem, tamanho, dono,
   último acesso, dependências e a classificação prévia migra/migra parcial/não migra), em tela e em CSV. */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma, formatarData } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const CLASSE_ROTULO = {
  migra: 'migra', migra_parcial: 'migra parcial', nao_migra: 'não migra', desconhecido: 'desconhecido',
};
const CLASSE_MARCADOR = {
  migra: 'ok', migra_parcial: 'atencao', nao_migra: 'falha', desconhecido: 'info',
};
const ESTADO_MARCADOR = {
  concluido: 'ok', rodando: 'atencao', pendente: 'info', falhou: 'falha', cancelado: 'info',
};

let saindo = false;
const s = { conexoes: [], inventarios: [], atual: null };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function numero(valor) {
  if (valor === null || valor === undefined) return '—';
  return Number(valor).toLocaleString('pt-BR');
}

function tamanho(bytes) {
  if (!bytes) return '—';
  const unidades = ['B', 'kB', 'MB', 'GB', 'TB'];
  let n = Number(bytes);
  let i = 0;
  while (n >= 1024 && i < unidades.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i ? 1 : 0)} ${unidades[i]}`;
}

function badgeClasse(classe) {
  return h('span', { class: `marcador ${CLASSE_MARCADOR[classe] || 'info'}` }, CLASSE_ROTULO[classe] || classe);
}

// ------------------------------------------------------------------ conexões
async function carregarConexoes() {
  const r = await api.obter('/api/conexoes?tipo=esri_rest');
  if (r.status !== 200) {
    aviso('conexao-aviso', `não foi possível listar as conexões: ${api.mensagemDe(r)}`);
    return;
  }
  s.conexoes = r.json.itens || [];
  const select = porId('conexao');
  limpar(select);
  if (!s.conexoes.length) {
    select.append(h('option', { value: '' }, 'nenhuma conexão do tipo ArcGIS REST registrada'));
    select.disabled = true;
    porId('inventariar').disabled = true;
    aviso('conexao-aviso', 'registre o Portal em /conexoes (tipo ArcGIS REST) antes de inventariar', 'atencao');
    return;
  }
  select.disabled = false;
  porId('inventariar').disabled = false;
  for (const c of s.conexoes) select.append(h('option', { value: c.id }, c.nome));
  mostrarUrl();
}

function mostrarUrl() {
  const c = s.conexoes.find((x) => x.id === porId('conexao').value);
  porId('conexao-url').textContent = c ? `${c.url} — estado de saúde: ${c.estado_saude}` : '';
}

async function inventariar(evento) {
  evento.preventDefault();
  aviso('conexao-aviso', '');
  const botao = porId('inventariar');
  const corpo = { conexao_id: porId('conexao').value };
  const usuario = porId('usuario').value.trim();
  const senha = porId('senha').value;
  if (usuario || senha) { corpo.usuario = usuario; corpo.senha = senha; }
  botao.disabled = true;
  const r = await api.enviar('/api/migracao/inventarios', corpo);
  botao.disabled = false;
  porId('senha').value = '';
  if (r.status !== 201) {
    aviso('conexao-aviso', `não foi possível iniciar a leitura: ${api.mensagemDe(r)}`);
    return;
  }
  aviso('conexao-aviso', 'leitura enfileirada; acompanhe o estado na lista abaixo', 'sucesso');
  await carregarLista();
  await abrir(r.json.id);
}

// ------------------------------------------------------------------ lista
function linhaInventario(inv) {
  const totais = inv.totais || {};
  const ver = h('button', { type: 'button', class: 'ligacao' }, 'ver relatório');
  ver.addEventListener('click', () => abrir(inv.id));
  return h('tr', { 'data-id': inv.id },
    h('td', {}, inv.portal_nome || inv.portal_url),
    h('td', {}, h('span', { class: `marcador ${ESTADO_MARCADOR[inv.estado] || 'info'}` }, inv.estado)),
    h('td', {}, numero(totais.itens)),
    h('td', {}, numero(totais.grupos)),
    h('td', {}, numero(totais.usuarios)),
    h('td', {}, formatarData(inv.criado_em)),
    h('td', {}, ver));
}

async function carregarLista() {
  const r = await api.obter('/api/migracao/inventarios');
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível listar os inventários: ${api.mensagemDe(r)}`);
    return;
  }
  s.inventarios = r.json.itens || [];
  porId('lista-total').textContent = `(${s.inventarios.length})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!s.inventarios.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '7', class: 'ajuda' },
      'nenhum inventário ainda — escolha a conexão acima e leia o portal.')));
    return;
  }
  for (const inv of s.inventarios) corpo.append(linhaInventario(inv));
}

// ------------------------------------------------------------------ relatório
function cartaoResumo(rotulo, valor) {
  return h('div', { class: 'medida' }, h('span', { class: 'medida-valor' }, valor),
    h('span', { class: 'medida-rotulo' }, rotulo));
}

function linhaTipo(linha) {
  const classes = Object.entries(linha.classes || {})
    .map(([classe, n]) => h('span', { class: 'par' }, badgeClasse(classe), ` ${numero(n)}`));
  return h('tr', {},
    h('td', {}, linha.tipo),
    h('td', {}, numero(linha.itens)),
    h('td', {}, numero(linha.feicoes)),
    h('td', {}, tamanho(linha.bytes)),
    h('td', {}, ...classes));
}

function linhaItem(item) {
  return h('tr', {},
    h('td', {}, item.titulo || item.item_esri_id),
    h('td', {}, item.tipo),
    h('td', {}, item.dono_login || '—'),
    h('td', {}, numero(item.contagem_total)),
    h('td', {}, numero((item.dependencias || []).length)),
    h('td', { title: item.classificacao_motivo || '' }, badgeClasse(item.classificacao)),
    h('td', {}, item.ultimo_acesso_em ? formatarData(item.ultimo_acesso_em) : '—'));
}

async function abrir(id) {
  const r = await api.obter(`/api/migracao/inventarios/${encodeURIComponent(id)}`);
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível abrir o relatório: ${api.mensagemDe(r)}`);
    return;
  }
  const detalhe = r.json;
  s.atual = detalhe;
  porId('relatorio-cartao').hidden = false;
  porId('relatorio-portal').textContent = detalhe.portal_nome || detalhe.portal_url;
  porId('csv').setAttribute('href', `/api/migracao/inventarios/${encodeURIComponent(id)}/relatorio.csv`);

  const totais = detalhe.totais || {};
  const resumo = porId('resumo');
  limpar(resumo);
  resumo.append(
    cartaoResumo('itens', numero(totais.itens)),
    cartaoResumo('feições contadas', numero(totais.feicoes)),
    cartaoResumo('tamanho declarado', tamanho(totais.bytes_declarados)),
    cartaoResumo('grupos', numero(detalhe.grupos)),
    cartaoResumo('usuários', numero(detalhe.usuarios)),
  );
  for (const [classe, n] of Object.entries(detalhe.por_classificacao || {})) {
    resumo.append(h('div', { class: 'medida' }, h('span', { class: 'medida-valor' }, numero(n)),
      h('span', { class: 'medida-rotulo' }, badgeClasse(classe))));
  }
  if (detalhe.mensagem) aviso('lista-aviso', `última mensagem da leitura: ${detalhe.mensagem}`, 'atencao');

  const corpoTipo = porId('por-tipo-corpo');
  limpar(corpoTipo);
  for (const linha of detalhe.por_tipo || []) corpoTipo.append(linhaTipo(linha));

  const ri = await api.obter(`/api/migracao/inventarios/${encodeURIComponent(id)}/itens?limite=200`);
  const corpoItens = porId('itens-corpo');
  limpar(corpoItens);
  if (ri.status === 200) {
    for (const item of ri.json.itens || []) corpoItens.append(linhaItem(item));
  }
}

// ------------------------------------------------------------------ entrada
function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/migracao' });
  cabecalho('Migração de Portal');
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) { saindo = true; location.replace(destino); return; }
  }
  layout(usuario);
  porId('form-inventario').addEventListener('submit', inventariar);
  porId('conexao').addEventListener('change', mostrarUrl);
  await carregarConexoes();
  await carregarLista();
  const alvo = new URLSearchParams(location.search).get('inventario');
  if (alvo) await abrir(alvo);
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
