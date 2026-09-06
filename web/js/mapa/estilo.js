/* plat · mapa — estilo MapLibre do mapa-base local (item L2-01-a-basemap-local-pmtiles). Cores lidas em tempo
   de execução dos tokens --i-carta-* de web/estilo/tokens.css (coresDaCarta): a cartografia é de cor fixa, não
   segue o tema claro/escuro, e nenhuma cor é escrita aqui. Camada `lugares` fica no tileset
   mas não é desenhada como texto — rótulo de nome exige servidor de glifos (L2-02-e-simbolos-sprites-glifos),
   fora do escopo desta fatia; aqui é só um ponto pequeno para não perder o dado.

   Fonte do PMTiles: web/dados/basemap/guarulhos.pmtiles (proveniência em PROVENIENCIA.md ao lado — OSM, ODbL 1.0,
   recorte de Guarulhos-SP, ≤ 50 MB). `sourceUrl` é resolvido em tempo de execução (mapa.js) a partir da origem
   da própria página, para funcionar tanto atrás do domínio interno quanto em `base_url` de teste. */

/* cores lidas dos tokens (--i-carta-* em web/estilo/tokens.css): o MapLibre lê JSON puro, não var() de CSS,
   por isso o valor é resolvido aqui por getComputedStyle na hora de construir o estilo — nenhuma cor escrita à
   mão neste arquivo (regra do item L0-14). */
const TOKEN = {
  fundo: '--i-carta-fundo',
  agua: '--i-carta-agua',
  cobertura: '--i-carta-cobertura',
  edificacao: '--i-carta-edificacao',
  edificacaoBorda: '--i-carta-edificacao-borda',
  viaMenor: '--i-carta-via-menor',
  viaMedia: '--i-carta-via-media',
  viaMaior: '--i-carta-via-maior',
  lugar: '--i-carta-lugar',
};
export function coresDaCarta() {
  const estilo = getComputedStyle(document.documentElement);
  const cor = {};
  for (const [nome, token] of Object.entries(TOKEN)) {
    const v = estilo.getPropertyValue(token).trim();
    if (!v) throw new Error(`token ${token} ausente em web/estilo/tokens.css`);
    cor[nome] = v;
  }
  return cor;
}

export function construirEstilo(urlPmtiles) {
  const COR = coresDaCarta();
  return {
    version: 8,
    name: 'plat-instrumento-guarulhos',
    sources: {
      base: {
        type: 'vector',
        url: `pmtiles://${urlPmtiles}`,
        attribution: '© colaboradores do OpenStreetMap — ODbL 1.0',
      },
    },
    layers: [
      { id: 'fundo', type: 'background', paint: { 'background-color': COR.fundo } },
      {
        id: 'cobertura-agua', type: 'fill', source: 'base', 'source-layer': 'cobertura',
        filter: ['==', ['get', 'natural'], 'water'],
        paint: { 'fill-color': COR.agua },
      },
      {
        id: 'cobertura-solo', type: 'fill', source: 'base', 'source-layer': 'cobertura',
        filter: ['!=', ['get', 'natural'], 'water'],
        paint: { 'fill-color': COR.cobertura, 'fill-opacity': 0.8 },
      },
      {
        id: 'edificacoes', type: 'fill', source: 'base', 'source-layer': 'edificacoes',
        paint: { 'fill-color': COR.edificacao, 'fill-outline-color': COR.edificacaoBorda },
        minzoom: 12,
      },
      {
        id: 'vias', type: 'line', source: 'base', 'source-layer': 'estradas',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['match', ['get', 'highway'],
            ['motorway', 'trunk', 'primary'], COR.viaMaior,
            ['secondary', 'tertiary'], COR.viaMedia,
            COR.viaMenor],
          'line-width': ['interpolate', ['linear'], ['zoom'],
            10, ['match', ['get', 'highway'], ['motorway', 'trunk', 'primary'], 1.4, 0.6],
            16, ['match', ['get', 'highway'], ['motorway', 'trunk', 'primary'], 5, 2]],
        },
      },
      {
        id: 'lugares', type: 'circle', source: 'base', 'source-layer': 'lugares',
        paint: {
          'circle-color': COR.lugar,
          'circle-radius': 3,
          'circle-stroke-color': COR.fundo,
          'circle-stroke-width': 1,
        },
      },
    ],
  };
}
