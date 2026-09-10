/* plat · render — página headless do QUADRO DE MAPA de um layout (item L2-12-b-layouts-elementos-exportacao).
   Sem sessão, sem cookie: a URL traz um token interno assinado (≤ 60 s, só do próprio host) que a página troca
   pelo estilo completo em GET /api/render/layout/estilo — fontes vetoriais com token de tile cunhado agora e as
   camadas de estilo da simbologia (as mesmas cores da legenda do layout, por construção). O mapa-base local
   (PMTiles) é o mesmo `estilo.js` do visualizador. Centro, zoom e rotação vêm da query string, calculados no
   servidor por app/layout/geometria.py (escala 1:N ↔ zoom no DPI pedido); o viewport É a imagem.

   Sinal de pronto: body[data-pronto="1"] só depois de `map.once('idle')` (tiles carregadas e desenhadas). Falha
   nomeada em body[data-erro] — o motor devolve erro de render em vez de uma imagem em branco fingindo. */
import { construirEstilo } from './estilo.js';

function urlDado(arquivo) { return `${location.origin}/static/dados/basemap/${arquivo}`; }

function numero(nome, padrao) {
  const v = new URLSearchParams(location.search).get(nome);
  return v === null || v === '' ? padrao : Number(v);
}

async function iniciar() {
  if (!window.maplibregl || !window.pmtiles) { document.body.dataset.erro = 'bibliotecas ausentes'; return; }
  const params = new URLSearchParams(location.search);
  const token = params.get('token') || '';
  let extra = { fontes: {}, camadas: [], base: 'osm-guarulhos' };
  try {
    const r = await fetch(`/api/render/layout/estilo?token=${encodeURIComponent(token)}`, { cache: 'no-store' });
    if (!r.ok) { document.body.dataset.erro = `estilo ${r.status}`; return; }
    extra = await r.json();
  } catch (e) {
    document.body.dataset.erro = `estilo: ${(e && e.message) || e}`;
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);
  const estilo = extra.base === 'sem-base'
    ? { version: 8, name: 'plat-sem-base', sources: {}, layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#ffffff' } }] }
    : construirEstilo(urlDado('guarulhos.pmtiles'));
  Object.assign(estilo.sources, extra.fontes || {});
  estilo.layers.push(...(extra.camadas || []));

  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: estilo,
    center: [numero('lng', -46.593018), numero('lat', -23.493476)],
    zoom: numero('zoom', 13),
    bearing: numero('rotacao', 0),
    attributionControl: false,
    hash: false,
    interactive: false,
    fadeDuration: 0,
    preserveDrawingBuffer: true,
  });
  map.on('error', (ev) => {
    // erro de tile de UMA camada não é erro de página: o quadro sai com o que carregou e o servidor registra
    const msg = String((ev && ev.error && ev.error.message) || ev);
    document.body.dataset.aviso = `${document.body.dataset.aviso || ''}${msg}; `.slice(0, 500);
  });
  await new Promise((resolve) => map.once('idle', resolve));
  document.body.dataset.pronto = '1';
}

iniciar();
