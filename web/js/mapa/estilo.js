/* plat · mapa — estilo MapLibre do mapa-base local (item L2-01-a-basemap-local-pmtiles). Cores copiadas à mão
   dos tokens escuros de web/estilo/tokens.css (--i-fundo/--i-superficie-2/--i-linha/--i-texto-fraco/--i-acento):
   o MapLibre lê JSON puro, não var() de CSS, então uma paleta nova em tokens.css exige repetir aqui (documentado
   no handoff do item; não há hoje um passo de build que gere isto dos tokens). Camada `lugares` fica no tileset
   mas não é desenhada como texto — rótulo de nome exige servidor de glifos (L2-02-e-simbolos-sprites-glifos),
   fora do escopo desta fatia; aqui é só um ponto pequeno para não perder o dado.

   Fonte do PMTiles: web/dados/basemap/guarulhos.pmtiles (proveniência em PROVENIENCIA.md ao lado — OSM, ODbL 1.0,
   recorte de Guarulhos-SP, ≤ 50 MB). `sourceUrl` é resolvido em tempo de execução (mapa.js) a partir da origem
   da própria página, para funcionar tanto atrás do domínio interno quanto em `base_url` de teste. */

const COR = {
  fundo: '#0b0f10',
  agua: '#12303a',
  cobertura: '#182420',
  edificacao: '#1a2224',
  edificacaoBorda: '#263133',
  viaMenor: '#4d5b57',
  viaMedia: '#8fa19c',
  viaMaior: '#d98a2b',
  lugar: '#d98a2b',
};

export function construirEstilo(urlPmtiles, { sprite = null, glyphs = null } = {}) {
  // sprite/glyphs do inquilino (item L2-02-e via L2-02-c): ícones e rótulos das camadas do catálogo; só entram
  // quando informados — chave com valor nulo faz o MapLibre recusar o estilo inteiro (armadilha medida em catalogo.js)
  return {
    version: 8,
    name: 'plat-instrumento-guarulhos',
    ...(sprite ? { sprite } : {}),
    ...(glyphs ? { glyphs } : {}),
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
