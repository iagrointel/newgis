/* plat · mapa — entrada da tela /mapa (item L2-01-e-mapas-base, que generaliza o item
   L2-01-a-basemap-local-pmtiles: mapa-base único → galeria por inquilino). Módulo ES sem build; cache
   resolvido por no-store no nginx: NUNCA ?v= nos imports. Requer sessão (ADR 0002, exigirSessao).
   MapLibre GL JS e o protocolo pmtiles vêm de <script> clássico (window.maplibregl / window.pmtiles,
   vendorizados em web/vendor/, VERSOES.txt) carregado ANTES deste módulo em mapa.html.

   Galeria: GET /api/mapas-base devolve os itens `mapa_base` do inquilino (instalados por
   POST /api/mapas-base/instalar, quatro fontes abertas — docs/DADO_DEMO.md), já na ordem de exibição.
   Quatro tipos de fonte (dados.tipo): `pmtiles` (vetorial local, estilo próprio claro/escuro/cinza),
   `osm_raster_proxy` (raster pelo proxy da casa, cache em disco), `satelite_titiler` (raster direto de um
   TiTiler externo) e `nenhum` (fundo cor, sem fonte). O item com dados.padrao=true abre por padrão; sem
   nenhum padrão, abre o primeiro da lista (ordem crescente, já vinda da API).

   Trocar de mapa base troca o `style` inteiro do MapLibre — que descarta toda fonte/camada que não estiver
   no novo JSON. Para as camadas OPERACIONAIS (as que representam dado do inquilino, não o mapa base)
   sobreviverem à troca, este módulo expõe `window.platMapa.adicionarCamadaOperacional`/
   `removerCamadaOperacional`: quem monta uma camada por cima do mapa registra aqui, e `trocarBase` guarda
   center/zoom/bearing/pitch antes de `setStyle`, reaplica as camadas registradas no `styledata` seguinte e
   restaura a posição com `jumpTo` (sem animação: a troca de base não é uma navegação do usuário). */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo, construirEstiloNenhum, construirEstiloRaster } from './estilo.js';

const ROTULO_LICENCA = {
  pmtiles: 'ODbL 1.0',
  osm_raster_proxy: 'ODbL 1.0 / CC BY-SA 2.0',
  satelite_titiler: 'Copernicus',
  nenhum: '',
};
const CENTRO_PADRAO = [-46.593018, -23.493476]; // recorte do PMTiles local (PROVENIENCIA.md)
const ZOOM_PADRAO = 13;

const el = (id) => document.getElementById(id);

function absoluta(url) {
  return /^https?:\/\//i.test(url) ? url : `${location.origin}${url}`;
}

function atribuicaoDe(base) {
  const rotulo = ROTULO_LICENCA[base.dados?.tipo] || '';
  if (!base.creditos) return '';
  return rotulo ? `${base.creditos} — ${rotulo}` : base.creditos;
}

function estiloDe(base) {
  const dados = base.dados || {};
  if (dados.tipo === 'pmtiles') return construirEstilo(absoluta(dados.url), dados.estilo || 'escuro');
  if (dados.tipo === 'osm_raster_proxy' || dados.tipo === 'satelite_titiler') {
    return construirEstiloRaster(absoluta(dados.url), atribuicaoDe(base), dados.zoom_min, dados.zoom_max);
  }
  return construirEstiloNenhum();
}

async function buscarGaleria() {
  const r = await fetch('/api/mapas-base', { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`GET /api/mapas-base → ${r.status}`);
  return r.json();
}

async function instalarGaleria() {
  const r = await fetch('/api/mapas-base/instalar', { method: 'POST', headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`POST /api/mapas-base/instalar → ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- camadas operacionais (sobrevivem à troca)
const camadasOperacionais = new Map(); // layerId -> {sourceId, sourceDef, layerDef}

function montarCamada(map, entrada) {
  if (!map.getSource(entrada.sourceId)) map.addSource(entrada.sourceId, entrada.sourceDef);
  if (!map.getLayer(entrada.layerDef.id)) map.addLayer(entrada.layerDef);
}

function adicionarCamadaOperacional(map, { sourceId, sourceDef, layerDef }) {
  const entrada = { sourceId, sourceDef, layerDef };
  camadasOperacionais.set(layerDef.id, entrada);
  montarCamada(map, entrada);
}

function removerCamadaOperacional(map, layerId) {
  camadasOperacionais.delete(layerId);
  if (map.getLayer(layerId)) map.removeLayer(layerId);
}

function restaurarCamadasOperacionais(map) {
  for (const entrada of camadasOperacionais.values()) montarCamada(map, entrada);
}

function trocarBase(map, base) {
  const centro = map.getCenter();
  const zoom = map.getZoom();
  const bearing = map.getBearing();
  const pitch = map.getPitch();
  map.setStyle(estiloDe(base));
  map.once('styledata', () => {
    restaurarCamadasOperacionais(map);
    map.jumpTo({ center: centro, zoom, bearing, pitch });
  });
}

function montarSeletorBase(map, galeria) {
  const sel = el('seletor-base');
  sel.replaceChildren();
  for (const base of galeria) {
    const opt = document.createElement('option');
    opt.value = base.id;
    opt.textContent = base.titulo;
    sel.append(opt);
  }
  const padrao = galeria.find((b) => b.dados?.padrao) || galeria[0];
  if (padrao) sel.value = padrao.id;
  sel.addEventListener('change', () => {
    const base = galeria.find((b) => b.id === sel.value);
    if (base) trocarBase(map, base);
  });
  return padrao;
}

async function iniciarMapa() {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro(t('mapa.erro_biblioteca'));
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);

  // primeira visita do inquilino: instala as fontes padrão (idempotente — item L2-01-e-mapas-base). Sem
  // privilégio conteudo.criar a instalação falha e a galeria some vazia; a mensagem já diz o que fazer.
  let galeria = await buscarGaleria();
  if (galeria.length === 0) {
    try {
      galeria = await instalarGaleria();
    } catch {
      el('aviso').erro(t('mapa.erro_galeria_vazia'));
      return;
    }
  }
  if (galeria.length === 0) {
    el('aviso').erro(t('mapa.erro_galeria_vazia'));
    return;
  }
  const inicial = galeria.find((b) => b.dados?.padrao) || galeria[0];

  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: estiloDe(inicial),
    center: CENTRO_PADRAO,
    zoom: ZOOM_PADRAO,
    attributionControl: false,
    hash: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new window.maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new window.maplibregl.AttributionControl({ compact: false }), 'bottom-right');

  montarSeletorBase(map, galeria);
  montarCoordenadas(map);

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  // ganchos para quem monta camada operacional por cima do mapa (L2-01-c e adiante) e para o e2e deste item
  window.platMapa = { map, adicionarCamadaOperacional, removerCamadaOperacional, trocarBase, galeria };
  document.body.dataset.pronto = '1';
}

function montarCoordenadas(map) {
  const caixa = el('coordenadas');
  const escrever = (lng, lat, zoom) => {
    caixa.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} · z${zoom.toFixed(1)}`;
  };
  const mostrarCentro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', mostrarCentro);
  map.on('zoomend', mostrarCentro);
  mostrarCentro();
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  try {
    await iniciarMapa();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
