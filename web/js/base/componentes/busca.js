/* <plat-busca rotulo="..."> — campo de busca com rótulo acessível e atraso de 300 ms; evento 'buscar' {q}.
   Estados: repouso (lupa), foco, com valor (botão limpar), desativada (atributo disabled), carregando
   (atributo ocupado / propriedade ocupado = ícone girando + aria-busy), vazia (só a lupa e o rótulo), erro
   (erro(texto) = aria-invalid + mensagem). */
import { h } from '../dom.js';
import { icone } from '../icones.js';
import { t } from '../i18n.js';

let seq = 0;
export class PlatBusca extends HTMLElement {
  static get observedAttributes() { return ['disabled', 'ocupado']; }
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const id = `busca-${++seq}`;
    const rotulo = this.getAttribute('rotulo') || t('busca.rotulo');
    this.classList.add('busca');
    this._input = h('input', { type: 'search', id, autocomplete: 'off', 'aria-label': rotulo, spellcheck: 'false' });
    this._limpar = h('button', { type: 'button', class: 'pequeno texto icone-so busca-limpar', 'aria-label': t('busca.limpar'), hidden: true }, icone('fechar', { tamanho: 14 }));
    this._ocupado = h('span', { class: 'busca-ocupado', hidden: true }, icone('carregando', { tamanho: 14 }));
    this._erro = h('span', { class: 'busca-erro', role: 'alert', id: `${id}-erro`, hidden: true });
    this.append(h('label', { for: id, class: 'sr-only' }, rotulo), icone('buscar', { tamanho: 14 }), this._input, this._limpar, this._ocupado, this._erro);
    let tm = null;
    this._input.addEventListener('input', () => {
      this._limpar.hidden = !this._input.value;
      this.limparErro();
      clearTimeout(tm);
      tm = setTimeout(() => this._emitir(), Number(this.getAttribute('atraso') || 300));
    });
    this._input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); clearTimeout(tm); this._emitir(); }
    });
    this._limpar.addEventListener('click', () => { this.valor = ''; this._limpar.hidden = true; this._input.focus(); this._emitir(); });
    this._aplicarAtributos();
  }
  attributeChangedCallback() { if (this._montado) this._aplicarAtributos(); }
  _aplicarAtributos() {
    const desativada = this.hasAttribute('disabled');
    this._input.disabled = desativada;
    this._limpar.disabled = desativada;
    const ocupado = this.hasAttribute('ocupado');
    this._ocupado.hidden = !ocupado;
    this.setAttribute('aria-busy', String(ocupado));
  }
  _emitir() { this.dispatchEvent(new CustomEvent('buscar', { detail: { q: this.valor } })); }
  get valor() { return (this._input?.value || '').trim(); }
  set valor(v) { if (this._input) { this._input.value = v ?? ''; this._limpar.hidden = !this._input.value; } }
  set ocupado(v) { if (v) this.setAttribute('ocupado', ''); else this.removeAttribute('ocupado'); }
  get ocupado() { return this.hasAttribute('ocupado'); }
  set desativada(v) { if (v) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); }
  erro(texto) {
    this._erro.textContent = texto || '';
    this._erro.hidden = !texto;
    if (texto) { this._input.setAttribute('aria-invalid', 'true'); this._input.setAttribute('aria-describedby', this._erro.id); }
    else this.limparErro();
  }
  limparErro() { this._erro.hidden = true; this._erro.textContent = ''; this._input.removeAttribute('aria-invalid'); this._input.removeAttribute('aria-describedby'); }
  focar() { this._input?.focus(); }
}
customElements.define('plat-busca', PlatBusca);
