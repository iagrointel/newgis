/* plat · cena — o painel dos modelos 3D e a ligação clique → propriedades (item L2-09-c).

   Junta as três peças: o que o documento de cena declara (`corpo.modelos`), a camada que desenha
   (glTF por three.js ou tileset por deck.gl, em `modelos3d.js`) e a API (`/api/modelos/...`).

   O clique é a razão de o modelo ter elemento: o nó do glTF carrega `extras.guid`, o painel pede
   `/api/modelos/{id}/elementos/{guid}` e mostra o tipo, o pavimento e cada conjunto de propriedade que o
   IFC declara. Sem o GUID não haveria o que perguntar — índice de nó muda a cada conversão. */
import { obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { CamadaModeloGltf, Tilesets3D, urlDoModelo } from './modelos3d.js';

export class Modelos3D {
  constructor(map, { lista, propriedades, aviso } = {}) {
    this.map = map;
    this.lista = lista;
    this.propriedades = propriedades;
    this.aviso = aviso;
    this.camadas = new Map();     // id do modelo -> CamadaModeloGltf
    this.tilesets = new Tilesets3D(map);
    this.fichas = new Map();      // id do modelo -> ficha da API
    this.selecionado = null;
    map.on('click', (ev) => this.aoClicar(ev));
  }

  async ficha(modeloId) {
    if (this.fichas.has(modeloId)) return this.fichas.get(modeloId);
    const r = await obter(`/api/modelos/${modeloId}`);
    if (r.status !== 200) throw new Error(t('modelos3d.erro_ficha'));
    this.fichas.set(modeloId, r.json);
    return r.json;
  }

  /** Aplica a lista `corpo.modelos` do documento: liga o que está visível, desliga o resto. */
  async aplicar(declarados = []) {
    const vistos = new Set();
    for (const decl of declarados) {
      if (decl.visivel === false) continue;
      vistos.add(decl.modelo_id);
      if (this.camadas.has(decl.modelo_id) || this.tilesets.camadas.has(decl.modelo_id)) continue;
      try {
        await this.ligar(decl);
      } catch (e) {
        if (this.aviso) this.aviso.erro(`${t('modelos3d.erro_camada')}: ${(e && e.message) || e}`);
      }
    }
    for (const id of [...this.camadas.keys()]) {
      if (!vistos.has(id)) {
        if (this.map.getLayer(`plat-modelo-${id}`)) this.map.removeLayer(`plat-modelo-${id}`);
        this.camadas.delete(id);
      }
    }
    for (const id of [...this.tilesets.camadas.keys()]) {
      if (!vistos.has(id)) this.tilesets.desativar(id);
    }
    this.desenharLista(declarados);
  }

  async ligar(decl) {
    const ficha = await this.ficha(decl.modelo_id);
    const urls = urlDoModelo(decl.modelo_id);
    if (decl.modo === 'tileset') {
      if (!ficha.tileset) throw new Error(t('modelos3d.sem_tileset'));
      this.tilesets.ativar({ id: decl.modelo_id, url_tileset: urls.tileset });
      return;
    }
    const camada = new CamadaModeloGltf({ ...ficha, url_glb: urls.glb });
    this.map.addLayer(camada);
    this.camadas.set(decl.modelo_id, camada);
  }

  aoClicar(ev) {
    for (const [id, camada] of this.camadas) {
      const achado = camada.elementoNoPonto(ev.point);
      if (achado && achado.guid) {
        this.mostrar(id, achado.guid);
        return;
      }
    }
  }

  async mostrar(modeloId, guid) {
    if (!this.propriedades) return;
    this.selecionado = { modelo_id: modeloId, guid };
    const r = await obter(`/api/modelos/${modeloId}/elementos/${encodeURIComponent(guid)}`);
    limpar(this.propriedades);
    if (r.status !== 200) {
      this.propriedades.append(h('p', { class: 'saida' }, t('modelos3d.elemento_nao_achado')));
      return;
    }
    const e = r.json;
    this.propriedades.dataset.guid = e.guid;
    this.propriedades.append(
      h('h3', { class: 'elemento-nome' }, e.nome || e.guid),
      h('dl', { class: 'elemento-cabecalho' },
        h('dt', {}, t('modelos3d.tipo')), h('dd', { 'data-campo': 'tipo' }, e.tipo),
        h('dt', {}, t('modelos3d.pavimento')), h('dd', { 'data-campo': 'pavimento' }, e.pavimento || '—'),
        h('dt', {}, t('modelos3d.guid')), h('dd', { 'data-campo': 'guid' }, e.guid)),
    );
    for (const [conjunto, campos] of Object.entries(e.propriedades || {})) {
      const dl = h('dl', { class: 'elemento-conjunto', 'data-conjunto': conjunto });
      for (const [chave, valor] of Object.entries(campos)) {
        dl.append(h('dt', {}, chave), h('dd', {}, valor === null ? '—' : String(valor)));
      }
      this.propriedades.append(h('h4', {}, conjunto), dl);
    }
  }

  desenharLista(declarados = []) {
    if (!this.lista) return;
    limpar(this.lista);
    for (const decl of declarados) {
      const ficha = this.fichas.get(decl.modelo_id);
      const caixa = h('input', { type: 'checkbox', id: `mod-${decl.id}`, checked: decl.visivel !== false });
      caixa.addEventListener('change', async () => {
        decl.visivel = caixa.checked;
        await this.aplicar(declarados);
      });
      this.lista.append(h('li', { class: 'modelo-cena', 'data-modelo': decl.modelo_id }, caixa,
        h('label', { for: `mod-${decl.id}`, class: 'camada-titulo' },
          decl.titulo || (ficha && ficha.nome) || decl.modelo_id)));
    }
  }
}
