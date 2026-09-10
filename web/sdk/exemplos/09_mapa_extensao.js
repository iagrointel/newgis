/* Exemplo 9/10 — MapLibre: `fonte(item)` (extensão do item como GeoJSON), `camada(item)` e `enquadrar()` sobre
   o mapa-base PMTiles local (/static/dados/basemap/guarulhos.pmtiles), com `transformRequest` do SDK. */
import { DADOS_MAPA, comSessao, esperarMapa, preparar } from './_comum.js';

const EXTENSAO = [-46.62, -23.56, -46.40, -23.40]; // recorte de Guarulhos-SP, o mesmo do mapa-base

preparar('09_mapa_extensao', (ctx) => comSessao(ctx, 'sdk-js-exemplo-09', async (p) => {
  const item = await p.mapas.criar('sdk js exemplo 09 — item com extensão', { dados: DADOS_MAPA, extent: EXTENSAO });
  try {
    const lido = await p.itens.obter(item.id);
    const fonte = p.maplibre.fonte(lido);
    ctx.escrever(`fonte(item): type=${fonte.type}, ${fonte.data.features.length} feição (polígono da extensão)`);
    const basemap = `${location.origin}/static/dados/basemap/guarulhos.pmtiles`;
    window.maplibregl.addProtocol('pmtiles', new window.pmtiles.Protocol().tile);
    const mapa = new window.maplibregl.Map({
      container: 'mapa', center: [-46.51, -23.48], zoom: 10, attributionControl: true,
      transformRequest: p.maplibre.transformRequest,
      style: p.maplibre.estilo(null, { basemapUrl: basemap }),
    });
    await esperarMapa(mapa);
    mapa.addSource('item', fonte);
    mapa.addLayer(p.maplibre.camada(lido, { id: 'item' }));
    p.maplibre.enquadrar(mapa, lido);
    await new Promise((r) => mapa.once('idle', r));
    const n = mapa.querySourceFeatures('item').length;
    ctx.escrever(`camada "${p.maplibre.camada(lido, { id: 'item' }).id}" desenhada; ${n} feição visível; zoom ${mapa.getZoom().toFixed(2)}`);
    window.exemplo.mapa = mapa;
    return { feicoes: n, zoom: mapa.getZoom() };
  } finally {
    await p.itens.apagar(item.id);
  }
}));
