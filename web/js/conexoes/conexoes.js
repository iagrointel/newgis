/* plat · conexões — entrada da tela /conexoes (itens L6-02-l-saude e L6-05-proveniencia-camada-externa).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do mesmo
   módulo = duas instâncias, app morre — regra da casa).
   Lista as conexões do inquilino com estado agregado de saúde (ok/degradado/fora/nunca_testada, calculado por
   `plat.v_conexao_saude`), disponibilidade em 30 dias e ações por linha: testar agora, ver histórico (últimos
   10 testes) e publicar camada (cria um item de catálogo com a ficha de procedência lida do serviço). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma, formatarData } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const ESTADO_ROTULO = { ok: 'ok', degradado: 'degradado', fora: 'fora', nunca_testada: 'nunca testada' };
const ESTADO_CLASSE = { ok: 'ok', degradado: 'atencao', fora: 'falha', nunca_testada: 'info' };

let saindo = false;
const s = { itens: [], usuario: null };

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

function badgeEstado(estado) {
  const classe = ESTADO_CLASSE[estado] || 'info';
  const rotulo = ESTADO_ROTULO[estado] || estado || 'nunca testada';
  return h('span', { class: `marcador ${classe}`, title: `estado de saúde: ${rotulo}` }, rotulo);
}

function celulaDisponibilidade(c) {
  if (c.disponibilidade_30d_total === 0 || c.disponibilidade_30d_pct === null || c.disponibilidade_30d_pct === undefined) {
    return h('span', { class: 'ajuda' }, 'sem verificação em 30 d');
  }
  return h('span', {}, `${c.disponibilidade_30d_pct}% (${c.disponibilidade_30d_total} verificações)`);
}

async function testarAgora(c, botao) {
  botao.disabled = true;
  aviso('lista-aviso', '');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/testar`, {});
  botao.disabled = false;
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível testar ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  await carregar();
}

function linhaHistoricoTabela(item) {
  return h('tr', {},
    h('td', {}, formatarData(item.verificada_em)),
    h('td', {}, h('span', { class: `marcador ${item.ok ? 'ok' : 'falha'}` }, item.ok ? 'ok' : 'erro')),
    h('td', {}, item.status === null || item.status === undefined ? '—' : String(item.status)),
    h('td', {}, item.mensagem || '—'),
    h('td', {}, item.latencia_ms === null || item.latencia_ms === undefined ? '—' : `${item.latencia_ms} ms`));
}

async function verHistorico(c) {
  const dialogo = porId('dialogo');
  const r = await api.obter(`/api/conexoes/${encodeURIComponent(c.id)}/saude-historico?limite=10`);
  if (r.status !== 200) {
    aviso('lista-aviso', `não foi possível ler o histórico de ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  const itens = r.json.itens || [];
  const corpo = h('div', {},
    h('p', {}, `${c.nome} — últimos ${itens.length} teste(s) de saúde`),
    itens.length
      ? h('table', { class: 'tabela' },
          h('thead', {}, h('tr', {}, h('th', {}, 'quando'), h('th', {}, 'resultado'), h('th', {}, 'status'),
            h('th', {}, 'mensagem'), h('th', {}, 'latência'))),
          h('tbody', {}, ...itens.map(linhaHistoricoTabela)))
      : h('p', { class: 'ajuda' }, 'nenhum teste registrado ainda — clique em "testar agora" ou aguarde o periódico (a cada 15 min).'));
  await dialogo.abrir({ titulo: 'histórico de saúde', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
}

function linhaProcedencia(rotulo, valor) {
  return h('div', { class: 'campo' },
    h('strong', {}, rotulo), ': ',
    valor === null || valor === undefined || valor === '' ? h('em', {}, 'não registrado') : h('span', {}, String(valor)));
}

async function publicarCamada(c) {
  const dialogo = porId('dialogo');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/publicar`, {});
  if (r.status !== 201) {
    aviso('lista-aviso', `não foi possível publicar a camada de ${c.nome}: ${api.mensagemDe(r)}`);
    return;
  }
  const item = r.json;
  const proc = (item.dados && item.dados.procedencia) || {};
  const corpo = h('div', {},
    h('p', {}, h('a', { href: `/conteudo/${encodeURIComponent(item.id)}` }, `abrir "${item.titulo}" no catálogo →`)),
    linhaProcedencia('fonte', proc.fonte),
    linhaProcedencia('url', proc.url),
    linhaProcedencia('licença', proc.licenca),
    linhaProcedencia('data de acesso', proc.data_de_acesso),
    linhaProcedencia('método', proc.metodo),
    linhaProcedencia('confiança', proc.confianca),
    linhaProcedencia('frescor', proc.frescor),
    linhaProcedencia('sha256', proc.sha256),
    linhaProcedencia('comando de reexecução', proc.comando_reexecucao),
    linhaProcedencia('atribuição (créditos)', item.creditos),
    proc.limites && proc.limites.length ? h('p', { class: 'ajuda' }, `ressalvas: ${proc.limites.join('; ')}`) : null);
  await dialogo.abrir({ titulo: 'camada publicada com ficha de procedência', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
  aviso('lista-aviso', `camada publicada a partir de ${c.nome}`, 'ok');
}

function linha(c) {
  const tr = h('tr', { dataset: { id: c.id, estado: c.estado_saude } });
  const btTestar = h('button', { type: 'button', class: 'pequeno' }, 'testar agora');
  btTestar.addEventListener('click', () => testarAgora(c, btTestar));
  const btHistorico = h('button', { type: 'button', class: 'pequeno' }, 'histórico');
  btHistorico.addEventListener('click', () => verHistorico(c));
  const btPublicar = h('button', { type: 'button', class: 'pequeno' }, 'publicar camada');
  btPublicar.addEventListener('click', () => publicarCamada(c));
  tr.append(
    h('td', {}, c.nome),
    h('td', {}, c.tipo),
    h('td', {}, c.modo),
    h('td', {}, badgeEstado(c.estado_saude)),
    h('td', {}, celulaDisponibilidade(c)),
    h('td', {}, c.saude_verificada_em ? formatarData(c.saude_verificada_em) : h('span', { class: 'ajuda' }, 'nunca testada')),
    h('td', {}, btTestar, ' ', btHistorico, ' ', btPublicar),
  );
  return tr;
}

async function carregar() {
  aviso('lista-aviso', '');
  const r = await api.obter('/api/conexoes');
  if (r.status !== 200) {
    if (r.status === 401) return;
    aviso('lista-aviso', `não foi possível carregar as conexões (${api.mensagemDe(r)})`);
    return;
  }
  s.itens = r.json.itens || [];
  porId('lista-total').textContent = `(${r.json.total})`;
  const corpo = porId('lista-corpo');
  limpar(corpo);
  if (!s.itens.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '7', class: 'ajuda' },
      'nenhuma conexão ainda — crie uma pela API (POST /api/conexoes) ou aguarde o conector por protocolo (L6-02-b em diante).')));
    return;
  }
  for (const c of s.itens) corpo.append(linha(c));
}

/* ---- catálogo de conectores públicos (item L6-02-m-catalogo-endpoints-brasil): GET /api/endpoints-publicos lista
   as entradas vivas no último teste HTTP (filtro por tipo e texto); ?vivo=false é a seção "fora do ar";
   POST /api/endpoints-publicos/{id}/adicionar cria a conexão num clique (idempotente: segundo clique reaproveita). */
const TIPO_ROTULO = { wms: 'WMS', wfs: 'WFS', wmts: 'WMTS', esri_rest: 'ArcGIS REST', stac: 'STAC', ogc_api: 'OGC API' };

async function adicionarDoCatalogo(e, botao) {
  botao.disabled = true;
  aviso('catalogo-aviso', '');
  const r = await api.enviar(`/api/endpoints-publicos/${encodeURIComponent(e.id)}/adicionar`, {});
  botao.disabled = false;
  if (r.status !== 201) {
    const erro = r.json && r.json.erro;
    aviso('catalogo-aviso', erro === 'endpoint_fora_do_ar'
      ? `"${e.nome}" está fora do ar no último teste do catálogo: não vira conexão por aqui`
      : `não foi possível adicionar "${e.nome}": ${api.mensagemDe(r)}`);
    return;
  }
  botao.textContent = r.json.criada ? 'adicionada' : 'já existia';
  botao.dataset.resultado = r.json.criada ? 'criada' : 'existente';
  aviso('catalogo-aviso', r.json.criada
    ? `conexão "${r.json.nome}" criada a partir do catálogo, com a ficha de procedência do órgão`
    : `"${r.json.nome}" já existia: conexão reaproveitada`, 'ok');
  await carregar();
}

function linhaCatalogo(e) {
  const bt = h('button', { type: 'button', class: 'pequeno primario' }, 'adicionar');
  bt.addEventListener('click', () => adicionarDoCatalogo(e, bt));
  return h('tr', { dataset: { endpoint: String(e.id), tipo: e.tipo } },
    h('td', {}, e.orgao),
    h('td', {}, h('span', { title: e.url }, e.nome)),
    h('td', {}, h('span', { class: 'marcador info' }, TIPO_ROTULO[e.tipo] || e.tipo)),
    h('td', {}, e.licenca === 'nao-declarada' ? h('em', {}, 'não declarada') : e.licenca),
    h('td', {}, e.testado_em ? formatarData(e.testado_em) : h('em', {}, 'nunca')),
    h('td', {}, bt));
}

function linhaForaDoAr(e) {
  return h('tr', { dataset: { endpoint: String(e.id), tipo: e.tipo } },
    h('td', {}, e.orgao),
    h('td', {}, h('span', { title: e.url }, e.nome)),
    h('td', {}, TIPO_ROTULO[e.tipo] || e.tipo),
    h('td', {}, h('span', { class: 'marcador falha', title: `HTTP ${e.http === null ? '—' : e.http}` }, e.motivo || '—')),
    h('td', {}, e.testado_em ? formatarData(e.testado_em) : h('em', {}, 'nunca')));
}

async function carregarCatalogo() {
  aviso('catalogo-aviso', '');
  const tipo = porId('catalogo-tipo').value;
  const q = porId('catalogo-q').value.trim();
  const params = api.consulta({ tipo: tipo || undefined, q: q || undefined, limite: 500 });
  const [vivos, fora] = await Promise.all([
    api.obter(`/api/endpoints-publicos${params}`),
    api.obter(`/api/endpoints-publicos${params}${params ? '&' : '?'}vivo=false`),
  ]);
  if (vivos.status !== 200 || fora.status !== 200) {
    if (vivos.status === 401) return;
    aviso('catalogo-aviso', `não foi possível carregar o catálogo (${api.mensagemDe(vivos.status !== 200 ? vivos : fora)})`);
    return;
  }
  porId('catalogo-total').textContent = `(${vivos.json.total})`;
  porId('catalogo-fora-total').textContent = `(${fora.json.total})`;
  porId('catalogo-resumo').textContent = vivos.json.testado_em_ultimo
    ? `${vivos.json.vivos} vivos, ${vivos.json.fora_do_ar} fora do ar, ${vivos.json.nunca_testados} nunca testados; último teste ${formatarData(vivos.json.testado_em_ultimo)}`
    : 'catálogo ainda não testado nesta instalação (o job endpoints_publicos.retestar roda toda semana)';
  const corpo = porId('catalogo-corpo');
  limpar(corpo);
  if (!vivos.json.itens.length) {
    corpo.append(h('tr', {}, h('td', { colspan: '6', class: 'ajuda' }, 'nenhum conector vivo com esse filtro')));
  }
  for (const e of vivos.json.itens) corpo.append(linhaCatalogo(e));
  const corpoFora = porId('catalogo-fora-corpo');
  limpar(corpoFora);
  for (const e of fora.json.itens) corpoFora.append(linhaForaDoAr(e));
}

function ligarCatalogo() {
  if (!document.getElementById('catalogo-cartao')) return;
  porId('catalogo-buscar').addEventListener('click', () => carregarCatalogo());
  porId('catalogo-tipo').addEventListener('change', () => carregarCatalogo());
  porId('catalogo-q').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); carregarCatalogo(); } });
}

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/conexoes' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Conexões');
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
  } else {
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API de conexões`, 'atencao');
  }
  s.usuario = usuario;
  layout(usuario);
  ligarCatalogo();
  await carregar();
  await carregarCatalogo();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
