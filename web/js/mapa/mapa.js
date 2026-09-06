/* plat · mapa — entrada da tela /mapa (item L2-01-a-basemap-local-pmtiles). Módulo ES sem build; cache resolvido
   por no-store no nginx: NUNCA ?v= nos imports. Requer sessão (ADR 0002, exigirSessao). MapLibre GL JS e o
   protocolo pmtiles vêm de <script> clássico (window.maplibregl / window.pmtiles, vendorizados em web/vendor/,
   VERSOES.txt) carregado ANTES deste módulo em mapa.html — os dois não são módulos ES.

   Mapa-base 100 % local: PMTiles estático (web/dados/basemap/guarulhos.pmtiles) lido por Range HTTP pelo próprio
   nginx do appliance (sem Martin, sem serviço de tiles dinâmico — isso é item futuro). Controles: navegação
   (zoom/pan, padrão MapLibre + arrastar/roda do mouse), escala, coordenadas do cursor (lê 'mousemove' do mapa) e
   seletor de camada base — mecanismo genérico por lista (BASES), uma opção hoje; a próxima base só entra na
   lista, o resto do fiação já funciona. body[data-pronto="1"] só depois do primeiro 'load' do mapa (o e2e espera
   por isso antes de tirar a captura que prova o canvas desenhado). */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from './estilo.js';
import * as api from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { AVISO_VENCIDA, selo } from '../acervo/frescor.js';

const BASES = [
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', arquivo: 'guarulhos.pmtiles' },
];

const el = (id) => document.getElementById(id);

function urlDado(arquivo) {
  return `${location.origin}/static/dados/basemap/${arquivo}`;
}

function montarSeletorBase(map) {
  const sel = el('seletor-base');
  for (const base of BASES) {
    const opt = document.createElement('option');
    opt.value = base.id;
    opt.textContent = t(base.rotuloChave);
    sel.append(opt);
  }
  sel.value = BASES[0].id;
  sel.addEventListener('change', () => {
    const base = BASES.find((b) => b.id === sel.value) || BASES[0];
    map.setStyle(construirEstilo(urlDado(base.arquivo)));
  });
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

/* item L6-01-h-frescor-verificacao: lista as camadas EXPOSTAS do acervo com o estado de verificação, para que
   quem for usar uma camada veja o aviso ANTES de confiar nela. O selo e o texto vêm de web/js/acervo/frescor.js
   — o mesmo módulo que a ficha em /acervo usa, para o aviso não divergir entre as duas telas. O painel fica
   escondido quando a API não responde ou quando não há camada exposta: painel vazio não é informação. */
async function montarPainelAcervo() {
  const painel = el('painel-acervo');
  if (!painel) return { total: 0, vencidas: 0 };
  const r = await api.obter('/api/acervo/camadas?limite=50');
  if (r.status !== 200 || !r.json || !Array.isArray(r.json.itens) || !r.json.itens.length) {
    painel.hidden = true;
    return { total: 0, vencidas: 0 };
  }
  const { itens, total, vencidas } = r.json;
  el('acervo-resumo').textContent = vencidas
    ? `${vencidas} de ${total} com ${AVISO_VENCIDA}`
    : `${total} camada(s), nenhuma com ${AVISO_VENCIDA}`;
  const lista = el('acervo-lista');
  limpar(lista);
  for (const c of itens) {
    lista.append(h('li', { 'data-camada': c.acervo_camada_id, 'data-vencida': c.verificacao_vencida ? '1' : '0' },
      h('code', { title: `${c.fonte_nome || c.fonte_id}` }, `${c.schema_nome}.${c.tabela}`),
      selo(c, h)));
  }
  painel.hidden = false;
  return { total, vencidas };
}

async function iniciarMapa() {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro(t('mapa.erro_biblioteca'));
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);

  const base = BASES[0];
  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(urlDado(base.arquivo)),
    center: [-46.593018, -23.493476], // centro do recorte (metadado do pmtiles, PROVENIENCIA.md)
    zoom: 13,
    attributionControl: false,
    hash: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new window.maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new window.maplibregl.AttributionControl({ compact: false }), 'bottom-right');

  montarSeletorBase(map);
  montarCoordenadas(map);

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  try {
    await montarPainelAcervo();
  } catch (e) {
    el('aviso').mostrar(`camadas do acervo indisponíveis: ${(e && e.message) || e}`, 'atencao');
  }
  document.body.dataset.pronto = '1';
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
