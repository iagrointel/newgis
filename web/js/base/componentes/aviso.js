/* <plat-aviso> — mensagem de estado da tela (role=status; erro vira role=alert). mostrar(texto, tipo) / limpar(). */
export class PlatAviso extends HTMLElement {
  connectedCallback() {
    if (!this.hasAttribute('role')) this.setAttribute('role', 'status');
    this.setAttribute('aria-live', 'polite');
    if (!this.textContent.trim()) this.hidden = true;
  }
  mostrar(texto, tipo = 'info') {
    this.textContent = texto;
    this.dataset.tipo = tipo;
    this.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
    this.hidden = false;
  }
  erro(texto) { this.mostrar(texto, 'erro'); }
  ok(texto) { this.mostrar(texto, 'ok'); }
  limpar() { this.textContent = ''; this.hidden = true; }
}
customElements.define('plat-aviso', PlatAviso);
