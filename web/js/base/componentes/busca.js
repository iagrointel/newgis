/* <plat-busca rotulo="..."> — campo de busca com rótulo acessível e atraso de 300 ms; evento 'buscar' {q}. */
import { h } from '../dom.js';

let seq = 0;
export class PlatBusca extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const id = `busca-${++seq}`;
    const rotulo = this.getAttribute('rotulo') || 'Buscar';
    this.classList.add('busca');
    this._input = h('input', { type: 'search', id, autocomplete: 'off', 'aria-label': rotulo, spellcheck: 'false' });
    this.append(h('label', { for: id, class: 'sr-only' }, rotulo), this._input);
    let t = null;
    this._input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => this._emitir(), Number(this.getAttribute('atraso') || 300));
    });
    this._input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); clearTimeout(t); this._emitir(); }
    });
  }
  _emitir() { this.dispatchEvent(new CustomEvent('buscar', { detail: { q: this.valor } })); }
  get valor() { return (this._input?.value || '').trim(); }
  set valor(v) { if (this._input) this._input.value = v ?? ''; }
  focar() { this._input?.focus(); }
}
customElements.define('plat-busca', PlatBusca);
