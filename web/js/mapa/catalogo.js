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
    const vetores = (r.json.camadas || []).filter((c) => c.servivel);
    const rasters = await this._carregarRaster();
    this.disponiveis = [...vetores, ...rasters];
    this._avisar();
    return this.disponiveis;
  }

  /* imagens publicadas (item raster) entram na MESMA lista de camadas do mapa (pedido do dono 10/09: "ao
     abrir o mapa tem de haver dado visível", a ortofoto não pode ficar invisível ao catálogo). Não há rota
     de listagem dedicada — usa-se `GET /api/itens?tipo=raster` (o catálogo geral) para os ids e depois
     `GET /api/imagens/{id}` por item (painel de sessão, sem token) para bbox/EPSG/URL de tile; falha de UM
     item raster não derruba o carregamento dos vetores. */
  async _carregarRaster() {
    try {
      const r = await obter('/api/itens?tipo=raster&limite=50');
      if (r.status !== 200) return [];
      const itens = (r.json && r.json.itens) || [];
      const fichas = [];
      for (const it of itens) {
        try {
          const d = await obter(`/api/imagens/${it.id}`);
          if (d.status !== 200 || !d.json || !Array.isArray(d.json.bbox) || d.json.bbox.length !== 4) continue;
          const fonte = PREFIXO + it.id;
          fichas.push({
            id: it.id,
            titulo: d.json.titulo || it.titulo,
            tipo: 'raster',
            servivel: true,
            geometria: null,
            familia: 'raster',
            n_feicoes: null,
            extensao: d.json.bbox,
            criado_em: d.json.criado_em || null,
            // absoluta: MapLibre não resolve template de tile relativo à página em todos os navegadores.
            tiles: [`${location.origin}${d.json.tiles_url}`],
            minzoom: 0,
            maxzoom: 22,
            estilo: [{ id: `${fonte}-raster`, type: 'raster', source: fonte, paint: { 'raster-opacity': 1 } }],
          });
        } catch { /* um item raster com falha não derruba o resto do catálogo */ }
      }
      return fichas;
    } catch {
      return [];
    }
  }

  idsDeEstilo(id) {
    const f = this.ficha(id);
    return (f ? f.estilo : []).map((c) => c.id);
  }

  async ligar(id) {
    if (this.ativas.includes(id)) return;
    const f = this.ficha(id);
    if (!f) throw new Error(`camada desconhecida: ${id}`);
    const fonte = PREFIXO + id;
    if (!this.map.getSource(fonte)) {
      if (f.tipo === 'raster') {
        // imagem publicada: fonte raster XYZ servida por sessão (cookie cobre a autorização, sem token na
        // URL — GET /api/imagens/{id}/tiles/{z}/{x}/{y}.png).
        const especificacaoRaster = {
          type: 'raster',
          tiles: f.tiles,
          tileSize: 256,
          minzoom: f.minzoom ?? 0,
          maxzoom: f.maxzoom ?? 22,
        };
        if (Array.isArray(f.extensao) && f.extensao.length === 4) especificacaoRaster.bounds = f.extensao;
        this.map.addSource(fonte, especificacaoRaster);
      } else {
        const r = await obter(f.tilejson);
        if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao obter o TileJSON');
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
      }
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
    // Aviso só quando a ordem MUDOU de verdade. Sem esta guarda o desenho da tela do mapa entra em
    // recursão infinita ("Maximum call stack size exceeded") e a árvore de camadas fica vazia: a
    // árvore ouve o catálogo (`catalogo.aoMudar` em web/js/camadas.js) e, ao ser avisada, chama
    // `_aplicarOrdemNoMapa`, que chama esta função de volta. Com a ordem já igual — inclusive o caso
    // comum de NENHUMA camada ligada, em que os dois lados são a lista vazia — o ciclo nunca fecha.
    if (validos.length === this.ativas.length && validos.every((id, i) => this.ativas[i] === id)) return true;
    this.ativas = validos;
    this.aplicarOrdem();
    this._avisar();
    return true;
  }

  /* MapLibre desenha na ordem do array de camadas do estilo. Percorrendo a lista de BAIXO para CIMA e
     movendo cada camada para o fim, o primeiro da lista termina por último = no topo do desenho.
     Imagem (raster) sempre embaixo dos vetores, qualquer que seja a posição em `ativas` — por isso dois
     grupos processados em sequência (raster primeiro): o segundo grupo termina sempre por cima do primeiro. */
  aplicarOrdem() {
    const ehRaster = (id) => (this.ficha(id) || {}).tipo === 'raster';
    const grupos = [this.ativas.filter(ehRaster), this.ativas.filter((id) => !ehRaster(id))];
    for (const grupo of grupos) {
      for (let i = grupo.length - 1; i >= 0; i -= 1) {
        for (const idc of this.idsDeEstilo(grupo[i])) {
          if (this.map.getLayer(idc)) this.map.moveLayer(idc);
        }
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
      } else if (camada.type === 'raster') {
        this.map.setPaintProperty(camada.id, 'raster-opacity', (base['raster-opacity'] ?? 1) * v);
      }
    }
    return v;
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
