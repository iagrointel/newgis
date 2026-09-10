/* Exemplo 10/10 — MapLibre: `estilo(mapaItem, {itens})` monta o estilo de um item mapa com as extensões dos itens
   que ele referencia; `catalogo({bbox})` liga o catálogo OGC API Records como fonte GeoJSON autenticada (o
   Bearer vai pelo `transformRequest`). */
import { comSessao, esperarMapa, preparar } from './_comum.js';

const BBOX = [-46.7, -23.6, -46.3, -23.3];
// camada hospedada mínima (mesmo `dados` do exemplo 03 do SDK Python): o mapa referencia CAMADAS em corpo.camadas
const camada = (sufixo) => ({
  schema: 'plat_trabalho', tabela: `zt_sdk_js_10_${sufixo}`, geometria: 'Point', srid: 4326,
  campos: [{ nome: 'rotulo', tipo: 'text' }], fonte: 'hospedada',
});

preparar('10_catalogo_no_mapa', (ctx) => comSessao(ctx, 'sdk-js-exemplo-10', async (p) => {
  const sufixo = Math.random().toString(16).slice(2, 8);
  const a = await p.camadas.criar('sdk js exemplo 10 — camada a', { dados: camada(`a${sufixo}`), extent: [-46.60, -23.55, -46.50, -23.45] });
  const b = await p.camadas.criar('sdk js exemplo 10 — camada b', { dados: camada(`b${sufixo}`), extent: [-46.48, -23.50, -46.40, -23.42] });
  const mapaItem = await p.mapas.criar('sdk js exemplo 10 — mapa', { dados: { esquema_versao: 1, corpo: { camadas: [a.id, b.id] } } });
  try {
    const itens = await Promise.all(mapaItem.dados.corpo.camadas.map((id) => p.itens.obter(id)));
    const basemap = `${location.origin}/static/dados/basemap/guarulhos.pmtiles`;
    const estilo = p.maplibre.estilo(mapaItem, { basemapUrl: basemap, itens });
    ctx.escrever(`estilo(mapa): ${Object.keys(estilo.sources).length} fontes, ${estilo.layers.length} camadas`);
    window.maplibregl.addProtocol('pmtiles', new window.pmtiles.Protocol().tile);
    const mapa = new window.maplibregl.Map({ container: 'mapa', center: [-46.5, -23.48], zoom: 9, style: estilo, transformRequest: p.maplibre.transformRequest });
    await esperarMapa(mapa);
    mapa.addSource('catalogo', p.maplibre.catalogo({ bbox: BBOX, limit: 50 }));
    mapa.addLayer({ id: 'catalogo-extensoes', type: 'line', source: 'catalogo', paint: { 'line-color': '#8fa19c', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
    await new Promise((r) => mapa.once('idle', r));
    const n = mapa.querySourceFeatures('catalogo').length;
    ctx.escrever(`catálogo OGC no mapa: ${n} extensão(ões) dentro de ${BBOX.join(',')} (Bearer via transformRequest)`);
    if (n < 2) throw new Error(`esperava ao menos os 2 itens deste exemplo no catálogo, veio ${n}`);
    window.exemplo.mapa = mapa;
    return { fontes: Object.keys(estilo.sources).length, feicoes: n };
  } finally {
    for (const it of [mapaItem, a, b]) await p.itens.apagar(it.id);
  }
}));
