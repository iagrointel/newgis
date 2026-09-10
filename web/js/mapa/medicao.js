/* plat · mapa — medição de distância e área (itens L2-01-mapa-web e L2-01-f-navegacao-medicao-coordenadas).

   Geodésica no ELIPSOIDE, nunca planar nem esférica: o portão do L2-01-f exige erro ≤ 0,1 % contra
   `ST_Length(geography)`/`ST_Area(geography)` do PostGIS, que calculam no esferoide, e a esfera erra até
   0,5 %. Distância pela fórmula inversa de Vincenty (GRS80; converge em mm), área pela projeção azimutal
   equivalente local do proj4 (área preservada por definição) com a fórmula do laço; sem proj4 na página a
   área cai para o excesso esférico (declarado em `metodo`). Segmentos parciais expostos para a lista da tela
   e `copiar()` para a área de transferência.

   Regra da casa: comprimento e área SEMPRE geodésicos, com o CRS declarado. */
import { laeaLocal } from './crs.js';

export const RAIO_M = 6371008.8;
const A = 6378137.0;            // GRS80
const F = 1 / 298.257222101;
const B = A * (1 - F);
const RAD = Math.PI / 180;

/* inversa de Vincenty (1975): distância e azimute inicial; antipodais caem para a esfera (não convergem) — raro
   num mapa de trabalho */
export function distancia(p1, p2) { return inversa(p1, p2).distancia; }

export function inversa(p1, p2) {
  const [lon1, lat1] = p1;
  const [lon2, lat2] = p2;
  if (lon1 === lon2 && lat1 === lat2) return { distancia: 0, azimute: 0 };
  const U1 = Math.atan((1 - F) * Math.tan(lat1 * RAD));
  const U2 = Math.atan((1 - F) * Math.tan(lat2 * RAD));
  const L = (lon2 - lon1) * RAD;
  const sinU1 = Math.sin(U1); const cosU1 = Math.cos(U1);
  const sinU2 = Math.sin(U2); const cosU2 = Math.cos(U2);
  let lambda = L; let lambdaAnt;
  let sinSigma; let cosSigma; let sigma; let sinAlpha; let cos2Alpha; let cos2SigmaM;
  for (let i = 0; i < 200; i += 1) {
    const sinLambda = Math.sin(lambda); const cosLambda = Math.cos(lambda);
    sinSigma = Math.sqrt((cosU2 * sinLambda) ** 2 + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2);
    if (sinSigma === 0) return { distancia: 0, azimute: 0 };
    cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda;
    sigma = Math.atan2(sinSigma, cosSigma);
    sinAlpha = (cosU1 * cosU2 * sinLambda) / sinSigma;
    cos2Alpha = 1 - sinAlpha * sinAlpha;
    cos2SigmaM = cos2Alpha === 0 ? 0 : cosSigma - (2 * sinU1 * sinU2) / cos2Alpha;
    const C = (F / 16) * cos2Alpha * (4 + F * (4 - 3 * cos2Alpha));
    lambdaAnt = lambda;
    lambda = L + (1 - C) * F * sinAlpha * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)));
    if (Math.abs(lambda - lambdaAnt) < 1e-12) break;
  }
  if (!Number.isFinite(lambda) || Math.abs(lambda - lambdaAnt) >= 1e-12) {
    return { distancia: distanciaEsferica(p1, p2), azimute: azimuteEsferico(p1, p2) };
  }
  const u2 = (cos2Alpha * (A * A - B * B)) / (B * B);
  const k1 = (Math.sqrt(1 + u2) - 1) / (Math.sqrt(1 + u2) + 1);
  const Acoef = (1 + (k1 * k1) / 4) / (1 - k1);
  const Bcoef = k1 * (1 - (3 * k1 * k1) / 8);
  const deltaSigma = Bcoef * sinSigma * (cos2SigmaM + (Bcoef / 4) * (cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)
    - (Bcoef / 6) * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)));
  const sinLambda = Math.sin(lambda); const cosLambda = Math.cos(lambda);
  const azimute = Math.atan2(cosU2 * sinLambda, cosU1 * sinU2 - sinU1 * cosU2 * cosLambda);
  return { distancia: B * Acoef * (sigma - deltaSigma), azimute };
}

function azimuteEsferico(a, b) {
  const lat1 = a[1] * RAD; const lat2 = b[1] * RAD; const dLon = (b[0] - a[0]) * RAD;
  return Math.atan2(Math.sin(dLon) * Math.cos(lat2), Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon));
}

/* direta de Vincenty: ponto a `s` metros de p1 no azimute `alfa1` (radianos) — usada para densificar cada aresta
   ao longo da GEODÉSICA, que é a aresta que o PostGIS mede em geography (uma reta em lon/lat não é geodésica) */
export function direta(p1, alfa1, s) {
  const [lon1, lat1] = p1;
  const sinAlpha1 = Math.sin(alfa1); const cosAlpha1 = Math.cos(alfa1);
  const tanU1 = (1 - F) * Math.tan(lat1 * RAD);
  const cosU1 = 1 / Math.sqrt(1 + tanU1 * tanU1); const sinU1 = tanU1 * cosU1;
  const sigma1 = Math.atan2(tanU1, cosAlpha1);
  const sinAlpha = cosU1 * sinAlpha1;
  const cos2Alpha = 1 - sinAlpha * sinAlpha;
  const u2 = (cos2Alpha * (A * A - B * B)) / (B * B);
  const k1 = (Math.sqrt(1 + u2) - 1) / (Math.sqrt(1 + u2) + 1);
  const Acoef = (1 + (k1 * k1) / 4) / (1 - k1);
  const Bcoef = k1 * (1 - (3 * k1 * k1) / 8);
  let sigma = s / (B * Acoef); let sigmaAnt; let cos2SigmaM; let sinSigma; let cosSigma;
  for (let i = 0; i < 200; i += 1) {
    cos2SigmaM = Math.cos(2 * sigma1 + sigma);
    sinSigma = Math.sin(sigma); cosSigma = Math.cos(sigma);
    const deltaSigma = Bcoef * sinSigma * (cos2SigmaM + (Bcoef / 4) * (cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)
      - (Bcoef / 6) * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)));
    sigmaAnt = sigma;
    sigma = s / (B * Acoef) + deltaSigma;
    if (Math.abs(sigma - sigmaAnt) < 1e-12) break;
  }
  const tmp = sinU1 * sinSigma - cosU1 * cosSigma * cosAlpha1;
  const lat2 = Math.atan2(sinU1 * cosSigma + cosU1 * sinSigma * cosAlpha1, (1 - F) * Math.sqrt(sinAlpha * sinAlpha + tmp * tmp));
  const lambda = Math.atan2(sinSigma * sinAlpha1, cosU1 * cosSigma - sinU1 * sinSigma * cosAlpha1);
  const C = (F / 16) * cos2Alpha * (4 + F * (4 - 3 * cos2Alpha));
  const L = lambda - (1 - C) * F * sinAlpha * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)));
  return [lon1 + L / RAD, lat2 / RAD];
}

/* pontos ao longo da geodésica p1→p2 (sem o último), a cada `passo` metros no máximo */
export function densificar(p1, p2, passo = 1000) {
  const { distancia: d, azimute } = inversa(p1, p2);
  const n = Math.max(1, Math.ceil(d / passo));
  const saida = [p1];
  for (let k = 1; k < n; k += 1) saida.push(direta(p1, azimute, (d * k) / n));
  return saida;
}

export function distanciaEsferica(a, b) {
  const dLat = (b[1] - a[1]) * RAD;
  const dLon = (b[0] - a[0]) * RAD;
  const lat1 = a[1] * RAD;
  const lat2 = b[1] * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * RAIO_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function segmentos(pontos) {
  const saida = [];
  for (let i = 1; i < pontos.length; i += 1) saida.push(distancia(pontos[i - 1], pontos[i]));
  return saida;
}

export function comprimento(pontos) {
  return segmentos(pontos).reduce((s, v) => s + v, 0);
}

/* área esférica (excesso), reserva quando não há proj4 */
export function areaEsferica(pontos) {
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

/* área no elipsoide: projeção equivalente local centrada no centroide dos vértices + fórmula do laço; cada aresta
   é densificada ao longo da GEODÉSICA (Vincenty direta, passos ≤ 1 km): é a aresta que o PostGIS mede */
export function area(pontos) {
  if (pontos.length < 3) return 0;
  let projetar;
  try {
    const lon0 = pontos.reduce((s, p) => s + p[0], 0) / pontos.length;
    const lat0 = pontos.reduce((s, p) => s + p[1], 0) / pontos.length;
    projetar = laeaLocal(lon0, lat0);
  } catch {
    return areaEsferica(pontos);
  }
  const anel = [...pontos, pontos[0]];
  const denso = [];
  for (let i = 0; i < anel.length - 1; i += 1) denso.push(...densificar(anel[i], anel[i + 1], 1000));
  const xy = denso.map((p) => projetar(p[0], p[1]));
  let soma = 0;
  for (let i = 0; i < xy.length; i += 1) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    soma += x1 * y2 - x2 * y1;
  }
  return Math.abs(soma / 2);
}

export function metodoArea() {
  try { laeaLocal(0, 0); return 'elipsoide (GRS80, projeção equivalente local)'; } catch { return 'esfera (excesso esférico)'; }
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
  constructor(map, saida, { lista = null } = {}) {
    this.map = map;
    this.saida = saida;      // elemento onde o resultado é escrito
    this.lista = lista;      // elemento (ul) com os segmentos parciais, opcional
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
    if (this.lista) this.lista.replaceChildren();
  }

  _acrescentar(p) {
    this.pontos.push(p);
    this._desenhar();
  }

  /* desfaz o último vértice (atalho Backspace) */
  voltar() {
    if (!this.pontos.length) return;
    this.pontos.pop();
    this._desenhar();
  }

  resultado() {
    if (this.modo === 'area' && this.pontos.length >= 3) {
      const a = area(this.pontos);
      return { tipo: 'area', valor: a, texto: formatarArea(a), perimetro: comprimento([...this.pontos, this.pontos[0]]),
               segmentos: segmentos([...this.pontos, this.pontos[0]]), metodo: metodoArea() };
    }
    if (this.pontos.length >= 2) {
      const s = segmentos(this.pontos);
      const c = s.reduce((x, y) => x + y, 0);
      return { tipo: 'distancia', valor: c, texto: formatarDistancia(c), segmentos: s, metodo: 'elipsoide (GRS80, Vincenty)' };
    }
    return null;
  }

  /* texto para a área de transferência: resultado, segmentos e vértices em graus decimais */
  textoParaCopiar() {
    const r = this.resultado();
    if (!r) return '';
    const linhas = [r.tipo === 'area' ? `área ${r.texto} · perímetro ${formatarDistancia(r.perimetro)}` : `distância ${r.texto}`];
    r.segmentos.forEach((s, i) => linhas.push(`segmento ${i + 1}: ${formatarDistancia(s)}`));
    linhas.push(`vértices (lat, lon WGS 84): ${this.pontos.map((p) => `${p[1].toFixed(6)}, ${p[0].toFixed(6)}`).join(' | ')}`);
    linhas.push(`método: ${r.metodo}`);
    return linhas.join('\n');
  }

  async copiar() {
    const texto = this.textoParaCopiar();
    if (!texto) return false;
    try { await navigator.clipboard.writeText(texto); return true; } catch { return false; }
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
    if (this.lista) {
      this.lista.replaceChildren();
      for (const [i, s] of (r ? r.segmentos : []).entries()) {
        const li = document.createElement('li');
        li.textContent = `${i + 1}: ${formatarDistancia(s)}`;
        this.lista.append(li);
      }
    }
  }
}
