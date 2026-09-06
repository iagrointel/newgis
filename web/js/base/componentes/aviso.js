/* <plat-aviso> — mensagem de estado da tela (role=status; erro vira role=alert e recebe foco).
   Estados: vazio (oculto), info, ok, atencao, erro, carregando (ícone girando + aria-busy).
   mostrar(texto, tipo) / erro() / ok() / atencao() / carregando() / limpar(). Ícone da família única. */
import { icone } from '../icones.js';

const ICONE = { info: 'info', ok: 'ok', atencao: 'atencao', erro: 'erro', carregando: 'carregando' };

export class PlatAviso extends HTMLElement {
  connectedCallback() {
    if (!this.hasAttribute('role')) this.setAttribute('role', 'status');
    this.setAttribute('aria-live', 'polite');
    if (!this.hasAttribute('tabindex')) this.setAttribute('tabindex', '-1');
    const texto = this.textContent.trim();
    if (!texto) this.hidden = true;
    else this._render(texto, this.dataset.tipo || 'info');
  }
  _render(texto, tipo) {
    while (this.firstChild) this.removeChild(this.firstChild);
    this.append(icone(ICONE[tipo] || 'info', { tamanho: 16 }), document.createTextNode(texto));
  }
  mostrar(texto, tipo = 'info') {
    this._render(texto, tipo);
    this.dataset.tipo = tipo;
    this.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
    this.setAttribute('aria-busy', String(tipo === 'carregando'));
    this.hidden = false;
    if (tipo === 'erro') this.focus({ preventScroll: true });
  }
  erro(texto) { this.mostrar(texto, 'erro'); }
  ok(texto) { this.mostrar(texto, 'ok'); }
  atencao(texto) { this.mostrar(texto, 'atencao'); }
  carregando(texto) { this.mostrar(texto, 'carregando'); }
  get texto() { return (this.textContent || '').trim(); }
  limpar() { while (this.firstChild) this.removeChild(this.firstChild); this.removeAttribute('aria-busy'); this.hidden = true; }
}
customElements.define('plat-aviso', PlatAviso);
