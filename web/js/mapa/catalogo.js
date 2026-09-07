/* plat · mapa — camadas do catálogo dentro do MapLibre (item L2-01-mapa-web).

   Uma camada do catálogo vira, no mapa: uma FONTE (vector, TileJSON com token curto vindo de
   /api/mapa/camadas/{id}/tilejson) e uma ou mais CAMADAS de estilo (as que o servidor montou da
   simbologia — o navegador não inventa cor nenhuma, conceito C2). A ordem de desenho é a ordem da
   lista: o primeiro da lista é o de cima do mapa.

   Por que o TileJSON e não a URL montada aqui: o token é cunhado pelo servidor, tem escopo de UMA
   camada e validade de 12 h; se o navegador montasse a URL, teria de conhecer esquema e nome de
   função (nomes internos do banco). */
import { obter } from '../base/api.js';

const PREFIXO = 'plat-'; // toda camada nossa no estilo começa assim; o mapa-base nunca é tocado

export class Catalogo {
  constructor(map) {
    this.map = map;
    this.disponiveis = [];   // fichas vindas de /api/mapa/camadas
    this.ativas = [];        // ids na ordem de desenho, o primeiro é o de cima
    this.opacidade = new Map();
    this.ouvintes = new Set();
  }

  aoMudar(fn) { this.ouvintes.add(fn); return () => this.ouvintes.delete(fn); }
  _avisar() { for (const fn of this.ouvintes) fn(this); }

  ficha(id) { return this.disponiveis.find((c) => c.id === id) || null; }

  async carregar() {
    const r = await obter('/api/mapa/camadas');
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao listar camadas');
    this.disponiveis = (r.json.camadas || []).filter((c) => c.servivel);
    this._avisar();
    return this.disponiveis;
  }

  idsDeEstilo(id) {
    const f = this.ficha(id);
    return (f ? f.estilo : []).map((c) => c.id);
  }

  async ligar(id) {
    if (this.ativas.includes(id)) return;
    const f = this.ficha(id);
    if (!f) throw new Error(`camada desconhecida: ${id}`);
    const r = await obter(this._urlTilejson(f));
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao obter o TileJSON');
    const fonte = PREFIXO + id;
    if (!this.map.getSource(fonte)) {
      // ARMADILHA MEDIDA: o MapLibre VALIDA a especificação da fonte e recusa a fonte inteira, em
      // silêncio (só um evento 'error'), quando uma chave existe com valor `undefined` — `attribution:
      // undefined` bastava para a fonte não ser criada e todas as camadas dela falharem depois com
      // "source not found". Por isso a chave opcional só entra no objeto quando tem valor.
      const especificacao = {
        type: 'vector',
        tiles: r.json.tiles,
        minzoom: r.json.minzoom ?? 0,
        maxzoom: r.json.maxzoom ?? 20,
        bounds: r.json.bounds,
      };
      if (f.atribuicao) especificacao.attribution = f.atribuicao;
      this.map.addSource(fonte, especificacao);
      f.camada_fonte = (r.json.vector_layers && r.json.vector_layers[0] && r.json.vector_layers[0].id) || f.camada_fonte;
    }
    for (const camada of f.estilo) {
      if (!this.map.getLayer(camada.id)) this.map.addLayer(camada);
    }
    this.ativas.unshift(id);
    this.aplicarOrdem();
    this.definirOpacidade(id, this.opacidade.get(id) ?? 1);
    this._avisar();
  }

  desligar(id) {
    for (const idc of this.idsDeEstilo(id)) if (this.map.getLayer(idc)) this.map.removeLayer(idc);
    const fonte = PREFIXO + id;
    if (this.map.getSource(fonte)) this.map.removeSource(fonte);
    this.ativas = this.ativas.filter((a) => a !== id);
    this._avisar();
  }

  async alternar(id) {
    if (this.ativas.includes(id)) this.desligar(id);
    else await this.ligar(id);
  }

  mover(id, delta) {
    const i = this.ativas.indexOf(id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= this.ativas.length) return false;
    this.ativas.splice(j, 0, this.ativas.splice(i, 1)[0]);
    this.aplicarOrdem();
    this._avisar();
    return true;
  }

  reordenar(ids) {
    const validos = ids.filter((id) => this.ativas.includes(id));
    if (validos.length !== this.ativas.length) return false;
    // guarda (achado do item L2-01-d, repetido aqui no L2-02-c): ordem igual à atual não avisa ninguém — a árvore
    // reordena ao sincronizar e o aviso a faria sincronizar de novo, em recursão sem fim
    if (validos.every((id, i) => id === this.ativas[i])) return true;
    this.ativas = validos;
    this.aplicarOrdem();
    this._avisar();
    return true;
  }

  /* MapLibre desenha na ordem do array de camadas do estilo. Percorrendo a lista de BAIXO para CIMA e
     movendo cada camada para o fim, o primeiro da lista termina por último = no topo do desenho. */
  aplicarOrdem() {
    for (let i = this.ativas.length - 1; i >= 0; i -= 1) {
      for (const idc of this.idsDeEstilo(this.ativas[i])) {
        if (this.map.getLayer(idc)) this.map.moveLayer(idc);
      }
    }
  }

  definirOpacidade(id, valor) {
    const v = Math.max(0, Math.min(1, Number(valor)));
    this.opacidade.set(id, v);
    const f = this.ficha(id);
    if (!f) return v;
    for (const camada of f.estilo) {
      if (!this.map.getLayer(camada.id)) continue;
      const base = camada.paint || {};
      if (camada.type === 'circle') {
        this.map.setPaintProperty(camada.id, 'circle-opacity', (base['circle-opacity'] ?? 1) * v);
        this.map.setPaintProperty(camada.id, 'circle-stroke-opacity', v);
      } else if (camada.type === 'line') {
        this.map.setPaintProperty(camada.id, 'line-opacity', (base['line-opacity'] ?? 1) * v);
      } else if (camada.type === 'fill') {
        this.map.setPaintProperty(camada.id, 'fill-opacity', (base['fill-opacity'] ?? 1) * v);
      }
    }
    return v;
  }

  /* TileJSON da camada; agrupamento (clusters no tile, item L2-02-c) pede a variante `agrupar=<raio_px>` */
  _urlTilejson(f) {
    const raio = f.agrupamento && f.agrupamento.raio_px;
    return raio ? `${f.tilejson}?agrupar=${encodeURIComponent(raio)}` : f.tilejson;
  }

  /* Estilo ao vivo (editor de simbologia, item L2-02-c): troca as camadas de estilo desta camada do catálogo
     pelas compiladas no servidor (POST /api/estilos/compilar), sem recarregar a página. Quando o agrupamento
     muda (liga/desliga/raio), a FONTE muda de função de tile e é refeita; senão só as camadas de estilo. */
  async aplicarEstilo(id, layers, legenda, opcoes = {}) {
    const f = this.ficha(id);
    if (!f) throw new Error(`camada desconhecida: ${id}`);
    const fonte = PREFIXO + id;
    const agrupamentoAntes = JSON.stringify(f.agrupamento || null);
    f.agrupamento = opcoes.agrupamento || null;
    f.plat_construtor = opcoes.plat_construtor || f.plat_construtor || null;
    const estavaLigada = this.ativas.includes(id);
    if (estavaLigada) for (const idc of this.idsDeEstilo(id)) if (this.map.getLayer(idc)) this.map.removeLayer(idc);
    const mudouFonte = agrupamentoAntes !== JSON.stringify(f.agrupamento || null);
    if (estavaLigada && mudouFonte && this.map.getSource(fonte)) {
      this.map.removeSource(fonte);
      const r = await obter(this._urlTilejson(f));
      if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao obter o TileJSON');
      this.map.addSource(fonte, { type: 'vector', tiles: r.json.tiles, minzoom: r.json.minzoom ?? 0, maxzoom: r.json.maxzoom ?? 20, bounds: r.json.bounds });
      f.camada_fonte = (r.json.vector_layers && r.json.vector_layers[0] && r.json.vector_layers[0].id) || f.camada_fonte;
    }
    const camadaFonte = f.agrupamento ? `${f.camada_fonte || ''}`.replace(/_ag$/, '') + '_ag' : `${f.camada_fonte || ''}`.replace(/_ag$/, '');
    f.estilo = layers.map((l) => ({ ...l, source: fonte, 'source-layer': camadaFonte }));
    f.legenda = legenda || f.legenda;
    if (estavaLigada) {
      for (const camada of f.estilo) if (!this.map.getLayer(camada.id)) this.map.addLayer(camada);
      this.aplicarOrdem();
      this.definirOpacidade(id, this.opacidade.get(id) ?? 1);
    }
    this._avisar();
    return f;
  }

  /* extensão da camada (graus) para o botão "enquadrar"; pede ao servidor quando a lista não trouxe */
  async extensao(id) {
    const f = this.ficha(id);
    if (f && Array.isArray(f.extensao) && f.extensao.length === 4) return f.extensao;
    const r = await obter(`/api/mapa/camadas/${id}`);
    if (r.status !== 200) return null;
    if (f) { f.extensao = r.json.extensao; f.n_feicoes = r.json.n_feicoes ?? f.n_feicoes; }
    return r.json.extensao || null;
  }
}

export { PREFIXO };
