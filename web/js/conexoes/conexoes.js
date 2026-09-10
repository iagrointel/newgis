/* plat · conexões — entrada da tela /conexoes (itens L6-02-l-saude, L6-05-proveniencia-camada-externa e
   L6-02-conectores-vivos). Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos
   imports (duas URLs do mesmo módulo = duas instâncias, app morre — regra da casa).
   Lista as conexões do inquilino com estado agregado de saúde (ok/degradado/fora/nunca_testada, calculado por
   `plat.v_conexao_saude`), disponibilidade em 30 dias e ações por linha: testar agora, ver histórico (últimos
   10 testes), camadas (descobrir/listar nome-título-CRS-extensão e pré-visualizar via o proxy de tile da
   própria conexão) e publicar camada (cria um item de catálogo com a ficha de procedência lida do serviço).
   "nova conexão" cadastra por URL (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles/banco/S3/HTTP). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma, formatarData } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

// os 3 primeiros são os únicos com operação de tile/imagem no proxy (app/conexao/proxy.py,
// limites.CONEXAO_PROXY_TIPOS) — só eles ganham o botão "pré-visualizar" na ficha de camadas.
const TIPOS_COM_PROXY = new Set(['wms', 'wmts', 'esri_rest']);
const TIPOS_CONEXAO = [
  { valor: 'wms', rotulo: 'WMS' },
  { valor: 'wmts', rotulo: 'WMTS' },
  { valor: 'wfs', rotulo: 'WFS' },
  { valor: 'ogc_api', rotulo: 'OGC API - Features' },
  { valor: 'esri_rest', rotulo: 'ArcGIS REST' },
  { valor: 'stac', rotulo: 'STAC' },
  { valor: 'geoparquet', rotulo: 'GeoParquet' },
  { valor: 'pmtiles', rotulo: 'PMTiles' },
  { valor: 'postgres_fdw', rotulo: 'banco externo (Postgres)' },
  { valor: 's3', rotulo: 'objetos (S3)' },
  { valor: 'http', rotulo: 'HTTP genérico' },
];

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

// ---------------------------------------------------------------- camadas (item L6-02-conectores-vivos)

function celulaExtensao(extensao) {
  if (!extensao) return '—';
  const num = (v) => (typeof v === 'number' ? v.toFixed(4) : v ?? '—');
  return `${num(extensao.minx)}, ${num(extensao.miny)}, ${num(extensao.maxx)}, ${num(extensao.maxy)} (${extensao.crs || 'CRS não declarado'})`;
}

function preverCamada(conexao, camada) {
  // só wms tem o bastante (LAYERS + BBOX geográfico em EPSG:4326) para montar um GetMap sem contexto de
  // mapa; wmts/esri_rest têm proxy (ver TIPOS_COM_PROXY), mas escolher tile/zoom pede um mapa de verdade —
  // fica para a fatia que liga isto ao MapLibre (web/js/mapa/mapa.js).
  if (conexao.tipo !== 'wms') return;
  const extensao = camada.extensao;
  const bbox = extensao ? `${extensao.minx},${extensao.miny},${extensao.maxx},${extensao.maxy}` : '-74,-34,-28.8,5.3';
  const crs = (extensao && extensao.crs) || 'EPSG:4326';
  const params = new URLSearchParams({
    SERVICE: 'WMS', VERSION: '1.3.0', REQUEST: 'GetMap', LAYERS: camada.nome, STYLES: '',
    CRS: crs, BBOX: bbox, WIDTH: '512', HEIGHT: '512', FORMAT: 'image/png', TRANSPARENT: 'true',
  });
  const src = `/api/conexoes/${encodeURIComponent(conexao.id)}/tile?${params.toString()}`;
  const corpo = h('div', {},
    h('p', {}, `${camada.titulo || camada.nome} — GetMap real pelo proxy da conexão (não uma amostra salva)`),
    h('img', { src, alt: camada.nome, style: 'max-width: 100%; border: 1px solid var(--borda, #ccc);' }));
  porId('dialogo').abrir({ titulo: 'pré-visualização da camada', corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
}

function linhaCamada(camada, conexao) {
  let acao = h('span', { class: 'ajuda' }, '—');
  if (TIPOS_COM_PROXY.has(conexao.tipo) && conexao.tipo === 'wms') {
    const bt = h('button', { type: 'button', class: 'pequeno' }, 'pré-visualizar');
    bt.addEventListener('click', () => preverCamada(conexao, camada));
    acao = bt;
  }
  return h('tr', {},
    h('td', {}, camada.nome),
    h('td', {}, camada.titulo || '—'),
    h('td', {}, (camada.crs || []).join(', ') || '—'),
    h('td', {}, celulaExtensao(camada.extensao)),
    h('td', {}, acao));
}

async function verCamadas(conexao) {
  const dialogo = porId('dialogo');
  const avisoLocal = h('plat-aviso');
  const tabelaWrap = h('div', { class: 'tabela-rolagem' });
  const btDescobrir = h('button', { type: 'button', class: 'primario' }, 'descobrir agora');

  function montarTabela(itens) {
    limpar(tabelaWrap);
    if (!itens.length) {
      tabelaWrap.append(h('p', { class: 'ajuda' }, 'nenhuma camada descoberta ainda — clique em "descobrir agora".'));
      return;
    }
    tabelaWrap.append(h('table', { class: 'tabela' },
      h('caption', { class: 'sr-only' }, `camadas de ${conexao.nome}`),
      h('thead', {}, h('tr', {}, h('th', {}, 'nome'), h('th', {}, 'título'), h('th', {}, 'CRS'), h('th', {}, 'extensão'),
        h('th', {}, h('span', { class: 'sr-only' }, 'ações')))),
      h('tbody', {}, ...itens.map((c) => linhaCamada(c, conexao)))));
  }

  btDescobrir.addEventListener('click', async () => {
    btDescobrir.disabled = true;
    avisoLocal.limpar();
    const r = await api.enviar(`/api/conexoes/${encodeURIComponent(conexao.id)}/descobrir`, {});
    btDescobrir.disabled = false;
    if (r.status !== 200) {
      avisoLocal.mostrar(`não foi possível descobrir as camadas de ${conexao.nome}: ${api.mensagemDe(r)}`, 'erro');
      return;
    }
    montarTabela(r.json.itens || []);
    avisoLocal.mostrar(r.json.mensagem, 'ok');
  });

  const r0 = await api.obter(`/api/conexoes/${encodeURIComponent(conexao.id)}/camadas`);
  if (r0.status === 200) montarTabela(r0.json.itens || []);
  else avisoLocal.mostrar(`não foi possível ler as camadas de ${conexao.nome}: ${api.mensagemDe(r0)}`, 'erro');

  const corpo = h('div', {}, h('div', { class: 'linha-ferramentas' }, btDescobrir), avisoLocal, tabelaWrap);
  await dialogo.abrir({ titulo: `camadas de ${conexao.nome}`, corpo, botoes: [{ id: 'fechar', rotulo: 'fechar' }] });
}

// ---------------------------------------------------------------- nova conexão (cadastro por URL)

async function novaConexao() {
  const dialogo = porId('dialogo');
  const f = h('plat-formulario');
  f.campos = [
    { nome: 'nome', rotulo: 'nome', tipo: 'texto', obrigatorio: true, atributos: { maxlength: 200 } },
    { nome: 'tipo', rotulo: 'tipo', tipo: 'select', obrigatorio: true, padrao: 'wms', opcoes: TIPOS_CONEXAO },
    {
      nome: 'url', rotulo: 'URL', tipo: 'texto', obrigatorio: true, atributos: { maxlength: 2048 },
      ajuda: 'raiz do serviço WMS/WMTS/WFS, /collections do OGC API - Features ou do MapServer/FeatureServer/'
        + 'ImageServer do ArcGIS REST; a descoberta de camada busca GetCapabilities/f=json a partir daqui',
    },
    {
      nome: 'credencial', rotulo: 'token de acesso (opcional)', tipo: 'senha',
      ajuda: 'só quando o serviço exige Authorization: Bearer; fica cifrado e nunca reaparece na tela',
    },
  ];
  f.botoes = [{ id: 'ok', rotulo: 'cadastrar', tipo: 'submit' }, { id: 'cancelar', rotulo: 'cancelar' }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') dialogo.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (!/^https?:\/\/\S+$/.test(v.url)) { f.erro('url', 'url inválida (precisa começar com http:// ou https://)'); return; }
    f.ocupado = true;
    const r = await api.enviar('/api/conexoes', {
      tipo: v.tipo, nome: v.nome, url: v.url, ...(v.credencial ? { credencial: v.credencial } : {}),
    });
    f.ocupado = false;
    if (r.status !== 201) {
      if (r.json.erro === 'nome_existente') f.erro('nome', 'já existe uma conexão com esse nome');
      else if (r.json.erro === 'url_insegura') f.erro('url', `url recusada: ${(r.json.detalhe && r.json.detalhe.motivo) || r.json.mensagem}`);
      else f.mensagem(api.mensagemDe(r), 'erro');
      return;
    }
    dialogo.fechar('ok');
    aviso('lista-aviso', `conexão "${v.nome}" cadastrada`, 'ok');
    await carregar();
  });
  await dialogo.abrir({ titulo: 'nova conexão externa', corpo: f });
}

function linha(c) {
  const tr = h('tr', { dataset: { id: c.id, estado: c.estado_saude } });
  const btTestar = h('button', { type: 'button', class: 'pequeno' }, 'testar agora');
  btTestar.addEventListener('click', () => testarAgora(c, btTestar));
  const btHistorico = h('button', { type: 'button', class: 'pequeno' }, 'histórico');
  btHistorico.addEventListener('click', () => verHistorico(c));
  const btCamadas = h('button', { type: 'button', class: 'pequeno' }, 'camadas');
  btCamadas.addEventListener('click', () => verCamadas(c));
  const btPublicar = h('button', { type: 'button', class: 'pequeno' }, 'publicar camada');
  btPublicar.addEventListener('click', () => publicarCamada(c));
  tr.append(
    h('td', {}, c.nome),
    h('td', {}, c.tipo),
    h('td', {}, c.modo),
    h('td', {}, badgeEstado(c.estado_saude)),
    h('td', {}, celulaDisponibilidade(c)),
    h('td', {}, c.saude_verificada_em ? formatarData(c.saude_verificada_em) : h('span', { class: 'ajuda' }, 'nunca testada')),
    h('td', {}, btTestar, ' ', btHistorico, ' ', btCamadas, ' ', btPublicar),
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
      'nenhuma conexão configurada ainda; fale com a equipe iAgroIntel para conectar um serviço externo.')));
    return;
  }
  for (const c of s.itens) corpo.append(linha(c));
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
  await carregar();
}

// achado na varredura QA de 10/09 (o botão existia sem nenhum ouvinte): agora abre o formulário de
// cadastro por URL (item L6-02-conectores-vivos) — nome, tipo, URL, credencial opcional.
document.getElementById('conexao-nova')?.addEventListener('click', () => { novaConexao(); });

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
