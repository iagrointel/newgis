/* plat · mapa — estilo MapLibre da base do mapa (item L2-01-a-basemap-local-pmtiles + correção 10/09: base
   mundial). Cores copiadas à mão dos tokens escuros de web/estilo/tokens.css (--i-fundo/--i-superficie-2/
   --i-linha/--i-texto-fraco/--i-acento): o MapLibre lê JSON puro, não var() de CSS, então uma paleta nova em
   tokens.css exige repetir aqui (documentado no handoff do item; não há hoje um passo de build que gere isto
   dos tokens).

   Medido 10/09 (captura de tela real): `/mapa` abria SEMPRE no recorte vetorial de Guarulhos (19 MB, só o
   canto superior direito da tela em qualquer outro lugar do Brasil) — "isso não é um SIG" (o dono). A base
   PADRÃO agora é o raster aberto `tile.openstreetmap.org` (mundial, mesma pilha MapLibre-sobre-OSM do SIG da
   FGR); o recorte vetorial de Guarulhos continua no seletor "camada base" como opção (uso: instrumento local
   de alto detalhe, viário/edificação/lugar vetorizados) — nenhum dos dois é removido.

   `construirEstilo(base)` aceita um descritor `{ tipo, url? }`:
     { tipo: 'raster', url }   → fonte raster XYZ (OSM aberto; tileSize 256, cache padrão do navegador)
     { tipo: 'pmtiles', url }  → fonte vetorial do recorte local (mesmo estilo desenhado à mão de antes)
     { tipo: 'nenhuma' }       → só o fundo (para quem quer olhar as camadas do catálogo sem nenhuma base)
   `url` do pmtiles é resolvida em tempo de execução por mapa.js a partir da origem da própria página, para
   funcionar tanto atrás do domínio interno quanto em `base_url` de teste; a do raster é fixa (OSM público). */

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

export const ATRIBUICAO_OSM = '© colaboradores do OpenStreetMap — ODbL 1.0';

/* mundial, sem recorte — https://operations.osmfoundation.org/policies/tiles/ (uso direto, sem chave) */
export const URL_OSM_RASTER = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

function estiloSemBase() {
  return {
    version: 8,
    name: 'plat-sem-base',
    sources: {},
    layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': COR.fundo } }],
  };
}

function estiloRasterMundial(url) {
  return {
    version: 8,
    name: 'plat-instrumento-osm-mundial',
    sources: {
      base: {
        type: 'raster',
        tiles: [url || URL_OSM_RASTER],
        tileSize: 256,
        maxzoom: 19,
        attribution: ATRIBUICAO_OSM,
      },
    },
    layers: [
      { id: 'fundo', type: 'background', paint: { 'background-color': COR.fundo } },
      { id: 'base-raster', type: 'raster', source: 'base' },
    ],
  };
}

function estiloPmtilesGuarulhos(urlPmtiles) {
  return {
    version: 8,
    name: 'plat-instrumento-guarulhos',
    sources: {
      base: {
        type: 'vector',
        url: `pmtiles://${urlPmtiles}`,
        attribution: ATRIBUICAO_OSM,
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
        // camada `lugares` fica no tileset mas não é desenhada como texto — rótulo de nome exige servidor
        // de glifos (L2-02-e-simbolos-sprites-glifos), fora do escopo desta fatia; aqui é só um ponto pequeno
        // para não perder o dado.
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

export function construirEstilo(base) {
  const b = base || { tipo: 'nenhuma' };
  if (b.tipo === 'raster') return estiloRasterMundial(b.url);
  if (b.tipo === 'pmtiles') return estiloPmtilesGuarulhos(b.url);
  return estiloSemBase();
}
