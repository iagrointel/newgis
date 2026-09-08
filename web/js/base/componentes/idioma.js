/* <plat-idioma> — seletor de idioma (pt-BR / en / es) das telas públicas e da conta (UX-02). Um <select> com rótulo
   acessível; a troca grava localStorage plat_idioma e recarrega o dicionário na hora (definirIdioma), sem recarregar
   a página: todo [data-i18n] e todo componente que ouve aoTraduzir re-traduzem. Nome de cada idioma no próprio idioma
   (não traduz "English"): quem não lê o idioma atual precisa reconhecer o dele. */
import { h } from '../dom.js';
import { IDIOMAS, aoTraduzir, definirIdioma, idiomaAtual, t } from '../i18n.js';

const NOMES = { 'pt-BR': 'Português (Brasil)', en: 'English', es: 'Español' };
let seq = 0;

export class PlatIdioma extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const id = `idioma-${++seq}`;
    this._rotulo = h('label', { for: id, class: this.hasAttribute('rotulo-visivel') ? 'campo-rotulo' : 'sr-only' }, t('idioma.rotulo'));
    this._select = h('select', { id, class: 'controle' });
    for (const v of IDIOMAS) this._select.append(h('option', { value: v }, NOMES[v]));
    this._select.value = idiomaAtual();
    this._select.addEventListener('change', async () => {
      const efetivo = await definirIdioma(this._select.value);
      this.dispatchEvent(new CustomEvent('idioma', { detail: { idioma: efetivo } }));
    });
    this.append(this._rotulo, this._select);
    this._cancelar = aoTraduzir(() => { this._rotulo.textContent = t('idioma.rotulo'); this._select.value = idiomaAtual(); });
  }
  disconnectedCallback() { this._cancelar?.(); }
  get valor() { return this._select?.value; }
}
customElements.define('plat-idioma', PlatIdioma);
