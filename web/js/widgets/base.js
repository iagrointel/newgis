/* plat — base dos widgets (L5-06), com a ligação a VISTA do L5-07: `widget.vista` (objeto Vista do
   app/vistas.js) chega pelo motor quando `configuracao.vista` aponta para uma vista do documento; o widget
   ouve `vista_mudou` e repinta. `emitir(nome, detalhe)` publica no barramento de widgets do L5-06 (ligações
   simples) E no barramento de mensagens do L5-07 (`barramentoApp.disparar`), quando houver. As ações de dado
   (filtrar/selecionar/limpar_*) chegam ao widget já resolvidas na vista pelo barramento; aqui ficam as ações de
   widget (piscar, abrir, fechar, definir_parametro) com comportamento padrão. */
export class PlatWidget extends HTMLElement {
  #configuracao = {};
  #vista = null;
  #aoMudarVista = null;
  barramento = null;
  barramentoApp = null;
  noId = '';

  set configuracao(valor) {
    this.#configuracao = Object.freeze({ ...(valor || {}) });
    if (this.isConnected) this.renderizar();
  }

  get configuracao() { return this.#configuracao; }

  set vista(v) {
    if (this.#vista && this.#aoMudarVista) this.#vista.removeEventListener('vista_mudou', this.#aoMudarVista);
    this.#vista = v || null;
    if (this.#vista) {
      this.#aoMudarVista = () => { if (this.isConnected) this.renderizar(); };
      this.#vista.addEventListener('vista_mudou', this.#aoMudarVista);
    }
    if (this.isConnected) this.renderizar();
  }

  get vista() { return this.#vista; }

  emitir(nome, detalhe = {}) {
    const evento = { nome, origem: this.noId, detalhe };
    this.barramento?.publicar(evento);
    this.barramentoApp?.disparar(this.noId, nome, detalhe);
    this.dispatchEvent(new CustomEvent(nome, { detail: detalhe, bubbles: true, composed: true }));
  }

  executar(acao, detalhe = {}) {
    const metodo = this[`acao_${acao.replaceAll('.', '_')}`];
    if (typeof metodo !== 'function') throw new Error(`ação desconhecida em ${this.localName}: ${acao}`);
    metodo.call(this, detalhe);
  }

  /* ações de widget com comportamento padrão (o widget pode sobrescrever) */
  acao_piscar() {
    this.setAttribute('data-piscando', '1');
    clearTimeout(this._piscar);
    this._piscar = setTimeout(() => this.removeAttribute('data-piscando'), 1200);
  }

  acao_abrir() { this.hidden = false; this.setAttribute('data-aberto', '1'); }

  acao_fechar() { this.hidden = true; this.removeAttribute('data-aberto'); }

  acao_definir_parametro(detalhe) {
    if (!detalhe || typeof detalhe.nome !== 'string') return;
    this.dataset[`parametro${detalhe.nome.replace(/[^a-z0-9]/gi, '')}`] = String(detalhe.valor ?? '');
    this.configuracao = { ...this.configuracao, [detalhe.nome]: detalhe.valor };
  }

  connectedCallback() { this.renderizar(); }

  disconnectedCallback() { if (this.#vista && this.#aoMudarVista) this.#vista.removeEventListener('vista_mudou', this.#aoMudarVista); }

  renderizar() {}
}

export function definir(nome, classe) {
  if (!customElements.get(nome)) customElements.define(nome, classe);
}
