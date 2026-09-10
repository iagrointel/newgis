/* plat · mapa — estilos MapLibre da galeria de mapas base (item L2-01-e-mapas-base, que generaliza o
   estilo único do item L2-01-a-basemap-local-pmtiles). Três paletas próprias (claro/escuro/cinza) para a
   fonte vetorial local; raster (proxy OSM, satélite via TiTiler) e "nenhum" (fundo cor) são estilos MapLibre
   de uma fonte só, montados aqui também — nenhuma lib nova, é JSON puro que o MapLibre já lê.

   Fonte do PMTiles: web/dados/basemap/guarulhos.pmtiles (proveniência em PROVENIENCIA.md ao lado — OSM,
   ODbL 1.0, recorte de Guarulhos-SP, ≤ 50 MB). `sourceUrl` é resolvido em tempo de execução (mapa.js) a
   partir da origem da própria página, para funcionar tanto atrás do domínio interno quanto em `base_url` de
   teste. Camada `lugares` fica no tileset mas não é desenhada como texto — rótulo de nome exige servidor de
   glifos (L2-02-e-simbolos-sprites-glifos), fora do escopo desta fatia; aqui é só um ponto pequeno para não
   perder o dado. */

const PALETAS = {
  escuro: {
    fundo: '#0b0f10', agua: '#12303a', cobertura: '#182420', edificacao: '#1a2224', edificacaoBorda: '#263133',
    viaMenor: '#4d5b57', viaMedia: '#8fa19c', viaMaior: '#d98a2b', lugar: '#d98a2b',
  },
  claro: {
    fundo: '#f6f4ee', agua: '#a9cbe0', cobertura: '#e4e1d6', edificacao: '#d8d3c4', edificacaoBorda: '#b7ae97',
    viaMenor: '#c9c2ae', viaMedia: '#9c8f6f', viaMaior: '#b45309', lugar: '#b45309',
  },
  cinza: {
    fundo: '#e7e7e7', agua: '#c7c7c7', cobertura: '#dedede', edificacao: '#cfcfcf', edificacaoBorda: '#b9b9b9',
    viaMenor: '#b3b3b3', viaMedia: '#8f8f8f', viaMaior: '#5c5c5c', lugar: '#5c5c5c',
  },
};

export function construirEstilo(urlPmtiles, variante = 'escuro') {
  const COR = PALETAS[variante] || PALETAS.escuro;
  return {
    version: 8,
    name: `plat-instrumento-guarulhos-${variante}`,
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

export function construirEstiloRaster(urlTiles, atribuicao, zoomMin, zoomMax) {
  return {
    version: 8,
    name: 'plat-raster',
    sources: {
      base: {
        type: 'raster', tiles: [urlTiles], tileSize: 256,
        minzoom: zoomMin ?? 0, maxzoom: zoomMax ?? 19,
        attribution: atribuicao || '',
      },
    },
    layers: [{ id: 'base', type: 'raster', source: 'base' }],
  };
}

export function construirEstiloNenhum() {
  return {
    version: 8,
    name: 'plat-nenhum',
    sources: {},
    layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#dedede' } }],
  };
}
