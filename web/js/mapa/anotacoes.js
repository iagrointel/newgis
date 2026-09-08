/* plat · mapa — painel de anotações de feição (item L2-01-k-desenho-anotacoes). Clique numa feição (modo
   "anotar" ligado) abre a lista de comentários dessa (camada, fid) e o formulário para acrescentar um novo,
   sempre em texto puro (h()/textContent — nunca innerHTML, a mesma regra do resto do app: ver web/js/base/dom.js).
   Backend: app/mapa/anotacoes.py (/api/anotacoes), visibilidade por grupo (RLS de plat.anotacao_feicao). */
import { alterar, enviar, mensagemDe, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

export class PainelAnotacoes {
  constructor(map, catalogo, els) {
    this.map = map;
    this.catalogo = catalogo;
    this.els = els; // {btnModo, corpo, alvo, lista, selGrupo, campoTexto, btnEnviar}
    this.modo = false;
    this.alvo = null; // {camadaId, fid}
    this._grupos = null;

    els.btnModo.addEventListener('click', () => this.alternarModo());
    els.btnEnviar.addEventListener('click', () => this._enviar());
    this._clique = (ev) => this._aoClicar(ev);
  }

  alternarModo(forcar) {
    this.modo = forcar !== undefined ? forcar : !this.modo;
    this.els.btnModo.setAttribute('aria-pressed', this.modo ? 'true' : 'false');
    if (this.modo) this.map.on('click', this._clique);
    else this.map.off('click', this._clique);
  }

  async _garantirGrupos() {
    if (this._grupos) return this._grupos;
    const r = await obter('/api/grupos?limite=200');
    this._grupos = r.status === 200 ? (r.json.itens || []) : [];
    limpar(this.els.selGrupo);
    for (const g of this._grupos) this.els.selGrupo.append(h('option', { value: g.id }, g.nome));
    return this._grupos;
  }

  async _aoClicar(ev) {
    const camadas = this.catalogo.ativas.flatMap((id) => this.catalogo.idsDeEstilo(id)).filter((idc) => this.map.getLayer(idc));
    if (!camadas.length) return;
    const feicoes = this.map.queryRenderedFeatures(ev.point, { layers: camadas });
    if (!feicoes.length) return;
    const f = feicoes[0];
    const camadaId = (f.layer && f.layer.source || '').replace(/^plat-/, '');
    const fid = String(f.id ?? (f.properties && f.properties.fid) ?? '');
    if (!camadaId || !fid) return;
    await this.abrir(camadaId, fid);
  }

  async abrir(camadaId, fid) {
    this.alvo = { camadaId, fid };
    this.els.corpo.hidden = false;
    const ficha = this.catalogo.ficha(camadaId);
    this.els.alvo.textContent = t('mapa.anotacao_alvo', { camada: (ficha && ficha.titulo) || camadaId, fid });
    await this._garantirGrupos();
    await this._recarregar();
  }

  async _recarregar() {
    if (!this.alvo) return;
    const r = await obter(`/api/anotacoes?camada_id=${encodeURIComponent(this.alvo.camadaId)}&fid=${encodeURIComponent(this.alvo.fid)}`);
    limpar(this.els.lista);
    if (r.status !== 200) { this.els.lista.append(h('li', {}, mensagemDe(r))); return; }
    for (const a of r.json.anotacoes || []) {
      const linha = h('li', { class: 'anotacao-item', dataset: { resolvido: a.resolvido ? '1' : '0' } },
        h('div', { class: 'anotacao-cabecalho' },
          h('strong', {}, a.autor_nome), ' · ', h('time', {}, new Date(a.criado_em).toLocaleString('pt-BR'))),
        h('p', {}, a.texto), // textContent — nunca HTML do usuário
        h('button', {
          type: 'button', class: 'botao-mini',
          onclick: () => this._alternarResolvido(a),
        }, t(a.resolvido ? 'mapa.anotacao_reabrir' : 'mapa.anotacao_resolver')));
      this.els.lista.append(linha);
    }
  }

  async _alternarResolvido(a) {
    await alterar(`/api/anotacoes/${a.id}`, { resolvido: !a.resolvido });
    await this._recarregar();
  }

  async _enviar() {
    const texto = this.els.campoTexto.value.trim();
    const grupoId = this.els.selGrupo.value;
    if (!texto || !this.alvo) return;
    if (!grupoId) { window.alert(t('mapa.anotacao_sem_grupo')); return; }
    const r = await enviar('/api/anotacoes', { camada_id: this.alvo.camadaId, fid: this.alvo.fid, grupo_id: grupoId, texto });
    if (r.status !== 201) { window.alert(mensagemDe(r)); return; }
    this.els.campoTexto.value = '';
    await this._recarregar();
  }
}
