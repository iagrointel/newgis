/* plat · cena — medição em 3D (item L2-09-b-cena-extrusao-slides).

   Duas medidas, as duas sobre o que a cena está DESENHANDO, nunca sobre um número lido do banco:

   * distância 3D: a distância horizontal geodésica (a mesma função do visualizador 2D, sem cópia) com a
     diferença de cota entre os dois pontos — sqrt(horizontal² + Δz²);
   * altura: a diferença de cota entre dois cliques. A cota de um ponto é a altura do terreno ali
     (`map.queryTerrainElevation`, 0 quando a cena está sem terreno) mais o topo da extrusão sob o
     cursor (`queryRenderedFeatures` + a MESMA conta de altura que pintou a caixa). Clicar no chão ao
     lado e depois no telhado dá a altura do prédio.

   A conta de altura é a de `camadas3d.alturaExpressao` aplicada às propriedades da feição — a mesma
   regra (escala, atributo, reserva 0, nada negativo), num lugar só. */
import { distancia as distanciaHorizontal } from '../mapa/medicao.js';
import { PREFIXO } from './camadas3d.js';

export { distanciaHorizontal };

export function distancia3D(a, b) {
  const horizontal = distanciaHorizontal(a, b);
  const dz = (b.z || 0) - (a.z || 0);
  return Math.sqrt(horizontal * horizontal + dz * dz);
}

/* altura da extrusão de uma feição, pela configuração da camada da cena (mesma regra do desenho) */
export function alturaDaFeicao(camada, propriedades) {
  const ext = (camada && camada.extrusao) || {};
  const escala = Number.isFinite(ext.escala) ? ext.escala : 1;
  if (ext.campo_altura) {
    const bruto = Number(propriedades ? propriedades[ext.campo_altura] : NaN);
    return Math.max(0, (Number.isFinite(bruto) ? bruto : 0) * escala);
  }
  return Math.max(0, (Number(ext.altura_fixa) || 0) * escala);
}

export function formatar(m) {
  return m < 1000 ? `${m.toFixed(1)} m` : `${(m / 1000).toFixed(3)} km`;
}

export class Medicao3D {
  /** `camadaDaCena(idDeEstilo)` devolve a camada do documento a partir do id de camada do MapLibre. */
  constructor(map, saida, camadaDaCena) {
    this.map = map;
    this.saida = saida;
    this.camadaDaCena = camadaDaCena;
    this.modo = null;
    this.pontos = [];
    this._clique = (ev) => this._aoClicar(ev);
  }

  iniciar(modo) {
    if (this.modo === modo) { this.limpar(); return; }
    this.limpar();
    this.modo = modo;
    this.map.on('click', this._clique);
    this.map.getCanvas().style.cursor = 'crosshair';
  }

  limpar() {
    if (this.modo) this.map.off('click', this._clique);
    this.modo = null;
    this.pontos = [];
    this.map.getCanvas().style.cursor = '';
    if (this.saida) this.saida.textContent = '';
  }

  /* cota do ponto: terreno + topo da extrusão sob o cursor */
  cota(lngLat, ponto) {
    let z = 0;
    if (this.map.getTerrain && this.map.getTerrain()) {
      const t = this.map.queryTerrainElevation(lngLat);
      if (Number.isFinite(t)) z = t;
    }
    const camadas = this.map.getStyle().layers
      .filter((c) => c.id.startsWith(PREFIXO) && c.type === 'fill-extrusion')
      .map((c) => c.id);
    if (camadas.length && ponto) {
      const feicoes = this.map.queryRenderedFeatures(ponto, { layers: camadas });
      if (feicoes.length) {
        const camada = this.camadaDaCena(feicoes[0].layer.id);
        z += alturaDaFeicao(camada, feicoes[0].properties);
      }
    }
    return z;
  }

  _aoClicar(ev) {
    const p = { lng: ev.lngLat.lng, lat: ev.lngLat.lat, z: this.cota(ev.lngLat, ev.point) };
    this.pontos.push(p);
    if (this.pontos.length > 2) this.pontos = [p];
    if (this.pontos.length < 2) { this.escrever(null); return; }
    const [a, b] = this.pontos;
    this.escrever(this.modo === 'altura' ? Math.abs((b.z || 0) - (a.z || 0)) : distancia3D(a, b));
  }

  escrever(valor) {
    if (!this.saida) return;
    this.saida.textContent = valor === null ? '' : formatar(valor);
    this.saida.dataset.valor = valor === null ? '' : String(valor);
  }
}
