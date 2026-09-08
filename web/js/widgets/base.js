import { htmlSeguro } from '../base/dom.js';

export class PlatWidget extends HTMLElement {
  #configuracao = {};
  barramento = null;
  noId = '';
  feicao = null; // feição selecionada (mapa/tabela) que os widgets de página leem por {campo}

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

  /* ação comum `<widget>.feicao`: guarda a feição selecionada e redesenha (texto, imagem, cartão a usam) */
  definirFeicao(detalhe) {
    this.feicao = (detalhe && (detalhe.feicao || detalhe.linha || detalhe)) || null;
    if (this.isConnected) this.renderizar();
  }

  /* HTML vindo do documento entra só pelo DOMPurify (D23); sem DOMPurify na página, cai para texto puro */
  fragmentoSeguro(html) {
    try { return htmlSeguro(html, { proibir: ['style', 'form', 'input', 'button'] }); }
    catch { return document.createTextNode(String(html)); }
  }

  /* caixa de erro nomeada dentro do próprio widget (config inválida em tempo de execução) */
  erro(mensagem) {
    const e = document.createElement('section');
    e.className = 'plat-widget-erro'; e.setAttribute('role', 'alert');
    e.textContent = `Widget “${this.dataset.tipo || this.localName}”: ${mensagem}`;
    this.replaceChildren(e);
  }

  connectedCallback() { this.renderizar(); }

  renderizar() {}
}

export function definir(nome, classe) {
  if (!customElements.get(nome)) customElements.define(nome, classe);
}
