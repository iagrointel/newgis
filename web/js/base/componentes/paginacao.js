/* <plat-paginacao> — "1–50 de 123" + Anterior/Próxima; evento 'mudar' {deslocamento}. atualizar({total, limite, deslocamento}). */
import { h } from '../dom.js';
import { aoTraduzir, formatarNumero, t } from '../i18n.js';

export class PlatPaginacao extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.classList.add('paginacao');
    this.setAttribute('role', 'navigation');
    this.setAttribute('aria-label', t('paginacao.rotulo'));
    this._texto = h('span', { 'aria-live': 'polite' });
    this._ant = h('button', { type: 'button', class: 'pequeno' }, t('paginacao.anterior'));
    this._prox = h('button', { type: 'button', class: 'pequeno' }, t('paginacao.proxima'));
    this._ant.addEventListener('click', () => this._ir(this._desl - this._lim));
    this._prox.addEventListener('click', () => this._ir(this._desl + this._lim));
    this.append(this._texto, this._ant, this._prox);
    this.atualizar({ total: 0, limite: 50, deslocamento: 0 });
    this._cancelar = aoTraduzir(() => {
      this.setAttribute('aria-label', t('paginacao.rotulo'));
      this._ant.textContent = t('paginacao.anterior');
      this._prox.textContent = t('paginacao.proxima');
      this.atualizar({ total: this._tot, limite: this._lim, deslocamento: this._desl });
    });
  }
  disconnectedCallback() { this._cancelar?.(); }
  _ir(d) {
    const novo = Math.max(0, d);
    this.dispatchEvent(new CustomEvent('mudar', { detail: { deslocamento: novo } }));
  }
  atualizar({ total = 0, limite = 50, deslocamento = 0 }) {
    this._tot = total; this._lim = limite; this._desl = deslocamento;
    const ini = total ? deslocamento + 1 : 0;
    const fim = Math.min(total, deslocamento + limite);
    this._texto.textContent = t('paginacao.faixa', { ini: formatarNumero(ini), fim: formatarNumero(fim), total: formatarNumero(total) });
    this._ant.disabled = deslocamento <= 0;
    this._prox.disabled = fim >= total;
    this.hidden = total <= limite && deslocamento === 0;
  }
}
customElements.define('plat-paginacao', PlatPaginacao);
