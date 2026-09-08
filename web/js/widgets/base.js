export class PlatWidget extends HTMLElement {
  #configuracao = {};
  barramento = null;
  noId = '';

  set configuracao(valor) {
    this.#configuracao = Object.freeze({ ...(valor || {}) });
    if (this.isConnected) this.renderizar();
  }

  get configuracao() { return this.#configuracao; }

  emitir(nome, detalhe = {}) {
    const evento = { nome, origem: this.noId, detalhe };
    this.barramento?.publicar(evento);
    this.dispatchEvent(new CustomEvent(nome, { detail: detalhe, bubbles: true, composed: true }));
  }

  executar(acao, detalhe = {}) {
    const metodo = this[`acao_${acao.replaceAll('.', '_')}`];
    if (typeof metodo !== 'function') throw new Error(`ação desconhecida em ${this.localName}: ${acao}`);
    metodo.call(this, detalhe);
  }

  connectedCallback() { this.renderizar(); }

  renderizar() {}
}

export function definir(nome, classe) {
  if (!customElements.get(nome)) customElements.define(nome, classe);
}
