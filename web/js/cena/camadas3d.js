/* plat · cena — as camadas do documento de cena dentro do MapLibre (item L2-09-b-cena-extrusao-slides).

   Mesmo motor do visualizador 2D: o dado chega pelo TileJSON de /api/mapa/camadas/{id}/tilejson (token
   curto cunhado pelo servidor) e vira uma FONTE vetorial. O que muda é o desenho — `fill-extrusion` com
   altura vinda de um ATRIBUTO, ícone preso a uma altura, ou linha elevada. Nenhuma segunda biblioteca 3D:
   o MapLibre já desenha extrusão sobre o terreno.

   Duas regras que nasceram do caso ruim, não da vontade:
   - altura nula ou não numérica vira 0 (`to-number` com reserva) e altura negativa é presa em 0 (`max`),
     senão o MapLibre desenha caixa invertida e a cena fica com buraco sem erro nenhum;
   - a escala multiplica o atributo (pavimentos → metros, por exemplo) e é sempre explícita no documento. */
import { obter } from '../base/api.js';

export const PREFIXO = 'plat-cena-';

export function alturaExpressao(config = {}) {
  const escala = Number.isFinite(config.escala) ? config.escala : 1;
  if (config.campo_altura) {
    return ['max', 0, ['*', escala, ['to-number', ['get', config.campo_altura], 0]]];
  }
  return Math.max(0, (Number(config.altura_fixa) || 0) * escala);
}

export function baseExpressao(config = {}) {
  const escala = Number.isFinite(config.escala) ? config.escala : 1;
  if (config.campo_base) {
    return ['max', 0, ['*', escala, ['to-number', ['get', config.campo_base], 0]]];
  }
  return Math.max(0, (Number(config.base_fixa) || 0) * escala);
}

export function corExpressao(camada) {
  const porCampo = camada.cor_por_campo;
  if (porCampo && porCampo.campo && Array.isArray(porCampo.paradas) && porCampo.paradas.length) {
    const paradas = [...porCampo.paradas].sort((a, b) => a.valor - b.valor);
    const expressao = ['interpolate', ['linear'], ['to-number', ['get', porCampo.campo], 0]];
    for (const p of paradas) expressao.push(p.valor, p.cor);
    return expressao;
  }
  return camada.cor || '#c8b89a';
}

/* A especificação MapLibre de uma camada da cena. `fonteCamada` é o nome da camada dentro do tile
   vetorial (o `vector_layers[0].id` do TileJSON), nunca um nome inventado aqui. */
export function especificacao(camada, fonte, fonteCamada) {
  const id = PREFIXO + camada.id;
  const opacidade = Number.isFinite(camada.opacidade) ? camada.opacidade : 1;
  const desenho = camada.desenho || 'extrusao';
  if (desenho === 'icone') {
    const cfg = camada.icone || {};
    return {
      id, type: 'circle', source: fonte, 'source-layer': fonteCamada,
      paint: {
        'circle-color': corExpressao(camada),
        'circle-radius': Number.isFinite(cfg.tamanho) ? cfg.tamanho : 4,
        'circle-opacity': opacidade,
        'circle-pitch-alignment': 'viewport',  // o ícone fica sempre voltado à câmera
      },
    };
  }
  if (desenho === 'linha_elevada') {
    const cfg = camada.linha || {};
    return {
      id, type: 'line', source: fonte, 'source-layer': fonteCamada,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': corExpressao(camada),
        'line-width': Number.isFinite(cfg.largura) ? cfg.largura : 2,
        'line-opacity': opacidade,
      },
    };
  }
  const ext = camada.extrusao || {};
  return {
    id, type: 'fill-extrusion', source: fonte, 'source-layer': fonteCamada,
    paint: {
      'fill-extrusion-color': corExpressao(camada),
      'fill-extrusion-height': alturaExpressao(ext),
      'fill-extrusion-base': baseExpressao(ext),
      'fill-extrusion-opacity': opacidade,
      'fill-extrusion-vertical-gradient': ext.gradiente_vertical !== false,
    },
  };
}

export class Camadas3D {
  constructor(map) {
    this.map = map;
    this.fichas = new Map();     // camada_id do catálogo → ficha de /api/mapa/camadas/{id}
    this.desenhadas = new Set(); // id da camada DA CENA já no estilo
  }

  async ficha(camadaId) {
    if (this.fichas.has(camadaId)) return this.fichas.get(camadaId);
    const r = await obter(`/api/mapa/camadas/${camadaId}`);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'camada da cena indisponível');
    this.fichas.set(camadaId, r.json);
    return r.json;
  }

  async ligar(camada) {
    if (this.desenhadas.has(camada.id)) return;
    const ficha = await this.ficha(camada.camada_id);
    const fonte = PREFIXO + camada.camada_id;
    let fonteCamada = null;
    if (!this.map.getSource(fonte)) {
      const r = await obter(ficha.tilejson);
      if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao obter o TileJSON');
      const especificacaoFonte = {
        type: 'vector', tiles: r.json.tiles,
        minzoom: r.json.minzoom ?? 0, maxzoom: r.json.maxzoom ?? 20, bounds: r.json.bounds,
      };
      this.map.addSource(fonte, especificacaoFonte);
      fonteCamada = (r.json.vector_layers || [{}])[0].id;
      this.fichas.set(`fonte:${camada.camada_id}`, fonteCamada);
    } else {
      fonteCamada = this.fichas.get(`fonte:${camada.camada_id}`);
    }
    this.map.addLayer(especificacao(camada, fonte, fonteCamada));
    this.desenhadas.add(camada.id);
  }

  desligar(camadaCena) {
    const id = PREFIXO + camadaCena.id;
    if (this.map.getLayer(id)) this.map.removeLayer(id);
    this.desenhadas.delete(camadaCena.id);
  }

  async aplicar(camadas) {
    for (const c of camadas) {
      const visivel = c.visivel !== false;
      if (visivel) await this.ligar(c);
      else this.desligar(c);
    }
    // camada que saiu do documento sai do mapa também
    const vivos = new Set(camadas.map((c) => c.id));
    for (const id of [...this.desenhadas]) if (!vivos.has(id)) this.desligar({ id });
  }

  async redesenhar(camada) {
    this.desligar(camada);
    if (camada.visivel !== false) await this.ligar(camada);
  }
}
