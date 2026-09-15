/* plat · modelo3d — bootstrap da tela /modelo/{id} (item L1-03-modelo3d). Dois visualizadores na mesma
   página, escolhidos por `?tipo=` (modelo3d, padrão | foto360): xeokit (módulo ES, carregado sob demanda —
   o mesmo jeito que o visualizador 3D do SIG anterior faz) para .xkt, pannellum (script clássico, já
   carregado por modelo.html) para a foto equirretangular. `body[data-pronto="1"]` só depois do primeiro
   modelo carregado — o e2e/Playwright espera por isso. */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { exigirSessao } from '../auth/sessao.js';
import { obter } from '../base/api.js';

const el = (id) => document.getElementById(id);

/* o h1 desta tela vive dentro da barra de ferramentas (ao lado do link "voltar" e da etiqueta de origem),
   não como filho direto de <main> — por isso não usa base/layout.js::cabecalho() (que exige `main > h1`,
   convenção das telas de lista tipo /conteudo e /mapa, sem título por item). */
function titulo(texto) {
  el('modelo3d-titulo').textContent = texto;
  document.title = `${texto} · ${t('app.nome')}`;
}

function idDaUrl() {
  const partes = location.pathname.split('/').filter(Boolean); // ['modelo', '<uuid>']
  return partes[1] || '';
}

function tipoDaUrl() {
  const q = new URLSearchParams(location.search).get('tipo');
  return q === 'foto360' ? 'foto360' : 'modelo3d';
}

function linha(rotulo, valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  return h('div', { class: 'campo-linha' }, h('span', { class: 'rotulo' }, rotulo), h('span', {}, String(valor)));
}

function formatarBytes(n) {
  if (n === null || n === undefined) return null;
  const unidades = ['B', 'KB', 'MB', 'GB'];
  let v = n; let i = 0;
  while (v >= 1024 && i < unidades.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${unidades[i]}`;
}

const ROTULO_ORIGEM = {
  ifc_convertido: () => t('modelo3d.origem_ifc'),
  xkt_enviado: () => t('modelo3d.origem_xkt'),
  amostra_gabarito: () => t('modelo3d.origem_gabarito'),
  enviada: () => t('foto360.origem_enviada'),
  amostra: () => t('foto360.origem_amostra'),
};

async function carregarXeokit(url) {
  const mod = await import('/static/vendor/xeokit-sdk-2.6.113.js');
  const { Viewer, XKTLoaderPlugin } = mod;
  el('pano').hidden = true;
  const canvas = el('xcanvas');
  canvas.hidden = false;
  const viewer = new Viewer({ canvasId: 'xcanvas', transparent: false });
  viewer.scene.canvas.backgroundColor = [0.11, 0.15, 0.16];
  viewer.camera.eye = [-18, 14, 22];
  viewer.camera.look = [6, 1, 6];
  viewer.camera.up = [0, 1, 0];
  const modelo = new XKTLoaderPlugin(viewer).load({ id: 'modelo', src: url, edges: true });
  modelo.on('loaded', () => {
    viewer.cameraFlight.flyTo({ aabb: modelo.aabb, duration: 0.6 });
    el('modelo3d-carregando').hidden = true;
    pronto();
  });
  modelo.on('error', (e) => {
    el('modelo3d-carregando').hidden = true;
    const erro = el('modelo3d-erro');
    erro.hidden = false;
    erro.textContent = t('modelo3d.erro_carregar', { erro: String(e) });
    pronto();
  });
}

function carregarPannellum(url) {
  el('xcanvas').hidden = true;
  const pano = el('pano');
  pano.hidden = false;
  if (!window.pannellum) {
    el('modelo3d-carregando').hidden = true;
    const erro = el('modelo3d-erro');
    erro.hidden = false;
    erro.textContent = t('modelo3d.erro_pannellum_ausente');
    pronto();
    return;
  }
  try {
    const visor = window.pannellum.viewer('pano', { type: 'equirectangular', panorama: url, autoLoad: true, showControls: true });
    visor.on('load', () => { el('modelo3d-carregando').hidden = true; pronto(); });
    visor.on('error', (msg) => {
      el('modelo3d-carregando').hidden = true;
      const erro = el('modelo3d-erro');
      erro.hidden = false;
      erro.textContent = t('modelo3d.erro_carregar', { erro: String(msg) });
      pronto();
    });
  } catch (e) {
    el('modelo3d-carregando').hidden = true;
    const erro = el('modelo3d-erro');
    erro.hidden = false;
    erro.textContent = t('modelo3d.erro_carregar', { erro: e.message || String(e) });
    pronto();
  }
}

function montarInfoModelo3d(m) {
  const caixa = el('modelo3d-info');
  limpar(caixa);
  caixa.append(
    h('h2', {}, t('modelo3d.info')),
    ...[linha(t('modelo3d.tamanho'), formatarBytes(m.bytes_xkt)),
        linha(t('modelo3d.schema_ifc'), m.schema_ifc),
        linha(t('modelo3d.projeto'), m.projeto),
        linha(t('modelo3d.n_ambientes'), m.n_ambientes),
        linha(t('modelo3d.n_elementos'), m.n_elementos),
        linha(t('modelo3d.conversao_duracao'), m.conversao?.duracao_s ? `${m.conversao.duracao_s} s` : null),
        linha(t('modelo3d.conversao_destino'), m.conversao?.destino_ssh)].filter(Boolean),
  );
  if ((m.pavimentos || []).length || (m.ambientes || []).length) {
    el('modelo3d-ambientes').hidden = false;
    const ul = el('modelo3d-lista-ambientes');
    limpar(ul);
    for (const p of m.pavimentos || []) ul.append(h('li', {}, `${t('modelo3d.pavimento')}: ${p || t('modelo3d.sem_nome')}`));
    for (const a of m.ambientes || []) ul.append(h('li', {}, a.nome || t('modelo3d.sem_nome')));
  }
}

function montarInfoFoto360(f) {
  const caixa = el('modelo3d-info');
  limpar(caixa);
  caixa.append(h('h2', {}, t('modelo3d.info')), h('p', { class: 'fraco' }, t('foto360.ajuda')));
}

async function iniciar() {
  await carregarIdioma();
  const usuario = await exigirSessao();
  if (!usuario) return;
  montarLayout({ usuario, ativo: '/modelo' });
  const id = idDaUrl();
  const tipo = tipoDaUrl();
  if (!id) {
    el('aviso').erro(t('modelo3d.sem_id'));
    pronto();
    return;
  }
  const caminho = tipo === 'foto360' ? `/api/foto360/${encodeURIComponent(id)}` : `/api/modelo3d/${encodeURIComponent(id)}`;
  const r = await obter(caminho);
  if (r.status !== 200) {
    titulo(t('modelo3d.titulo'));
    el('aviso').erro((r.json && r.json.mensagem) || t('modelo3d.erro_item'));
    el('modelo3d-carregando').hidden = true;
    pronto();
    return;
  }
  const item = r.json;
  titulo(item.titulo || t('modelo3d.titulo'));
  const rotuloOrigem = ROTULO_ORIGEM[item.origem];
  el('modelo3d-origem-etiqueta').textContent = rotuloOrigem ? rotuloOrigem() : '';
  if (tipo === 'foto360') {
    montarInfoFoto360(item);
    if (!item.imagem_url) { el('aviso').erro(t('modelo3d.sem_url')); el('modelo3d-carregando').hidden = true; pronto(); return; }
    carregarPannellum(item.imagem_url);
  } else {
    montarInfoModelo3d(item);
    if (!item.xkt_url) { el('aviso').erro(t('modelo3d.sem_url')); el('modelo3d-carregando').hidden = true; pronto(); return; }
    await carregarXeokit(item.xkt_url);
  }
}

iniciar();
