/* plat · mapa — medição de distância e área (item L2-01-mapa-web).

   Geodésica, nunca planar: o mapa é desenhado em Mercator, onde 1 pixel vale muito mais metro perto do
   equador do que perto do polo. Distância por Haversine no raio médio da Terra (6.371.008,8 m, IUGG) e
   área pelo excesso esférico (fórmula de Chamberlain-Duquette), a mesma que o `ST_Area(geography)` do
   PostGIS usa como aproximação esférica. Erro contra o elipsoide: abaixo de 0,5 % nas escalas de uso.

   Regra da casa: comprimento e área SEMPRE geodésicos, com o CRS declarado. */

export const RAIO_M = 6371008.8;
const RAD = Math.PI / 180;

export function distancia(a, b) {
  const dLat = (b[1] - a[1]) * RAD;
  const dLon = (b[0] - a[0]) * RAD;
  const lat1 = a[1] * RAD;
  const lat2 = b[1] * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * RAIO_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function comprimento(pontos) {
  let soma = 0;
  for (let i = 1; i < pontos.length; i += 1) soma += distancia(pontos[i - 1], pontos[i]);
  return soma;
}

export function area(pontos) {
  /* excesso esférico; o anel é fechado aqui, o chamador não precisa repetir o primeiro ponto */
  if (pontos.length < 3) return 0;
  const anel = [...pontos, pontos[0]];
  let soma = 0;
  for (let i = 0; i < anel.length - 1; i += 1) {
    const [lon1, lat1] = anel[i];
    const [lon2, lat2] = anel[i + 1];
    soma += (lon2 - lon1) * RAD * (2 + Math.sin(lat1 * RAD) + Math.sin(lat2 * RAD));
  }
  return Math.abs((soma * RAIO_M * RAIO_M) / 2);
}

export function formatarDistancia(m) {
  if (m < 1000) return `${m.toFixed(1)} m`;
  return `${(m / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 3 })} km`;
}

export function formatarArea(m2) {
  if (m2 < 10000) return `${m2.toFixed(1)} m²`;
  if (m2 < 1e6) return `${(m2 / 10000).toLocaleString('pt-BR', { maximumFractionDigits: 3 })} ha`;
  return `${(m2 / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 3 })} km²`;
}

const FONTE = 'plat-medicao';

export class Medicao {
  constructor(map, saida) {
    this.map = map;
    this.saida = saida;      // elemento onde o resultado é escrito
    this.modo = null;        // null | 'distancia' | 'area'
    this.pontos = [];
    this._clique = (ev) => this._acrescentar([ev.lngLat.lng, ev.lngLat.lat]);
  }

  _garantirCamadas() {
    if (this.map.getSource(FONTE)) return;
    this.map.addSource(FONTE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    this.map.addLayer({ id: `${FONTE}-preenchimento`, type: 'fill', source: FONTE,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#d98a2b', 'fill-opacity': 0.2 } });
    this.map.addLayer({ id: `${FONTE}-linha`, type: 'line', source: FONTE,
      paint: { 'line-color': '#d98a2b', 'line-width': 2 } });
    this.map.addLayer({ id: `${FONTE}-vertice`, type: 'circle', source: FONTE,
      filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 4, 'circle-color': '#d98a2b', 'circle-stroke-color': '#10161a',
               'circle-stroke-width': 1 } });
  }

  iniciar(modo) {
    if (this.modo === modo) { this.parar(); return; }
    this._garantirCamadas();
    this.modo = modo;
    this.pontos = [];
    this.map.getCanvas().style.cursor = 'crosshair';
    this.map.on('click', this._clique);
    this._desenhar();
  }

  parar() {
    this.modo = null;
    this.map.getCanvas().style.cursor = '';
    this.map.off('click', this._clique);
  }

  limpar() {
    this.parar();
    this.pontos = [];
    this._desenhar();
    this.saida.textContent = '';
  }

  _acrescentar(p) {
    this.pontos.push(p);
    this._desenhar();
  }

  resultado() {
    if (this.modo === 'area' && this.pontos.length >= 3) {
      return { tipo: 'area', valor: area(this.pontos), texto: formatarArea(area(this.pontos)) };
    }
    if (this.pontos.length >= 2) {
      const c = comprimento(this.pontos);
      return { tipo: 'distancia', valor: c, texto: formatarDistancia(c) };
    }
    return null;
  }

  _desenhar() {
    const fonte = this.map.getSource(FONTE);
    if (!fonte) return;
    const feicoes = this.pontos.map((p) => ({ type: 'Feature', properties: {},
      geometry: { type: 'Point', coordinates: p } }));
    if (this.modo === 'area' && this.pontos.length >= 3) {
      feicoes.push({ type: 'Feature', properties: {},
        geometry: { type: 'Polygon', coordinates: [[...this.pontos, this.pontos[0]]] } });
    } else if (this.pontos.length >= 2) {
      feicoes.push({ type: 'Feature', properties: {},
        geometry: { type: 'LineString', coordinates: this.pontos } });
    }
    fonte.setData({ type: 'FeatureCollection', features: feicoes });
    const r = this.resultado();
    this.saida.textContent = r ? r.texto : '';
  }
}
