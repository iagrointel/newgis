/* <plat-painel titulo="..." [recolhivel] [fechavel] [denso]> — o chrome único de painel do produto (UX-01): cabeçalho
   com título, ações e botões de recolher/fechar; corpo rolável; rodapé opcional. É o mesmo componente para o cartão
   de uma tela, para cada painel do visualizador de mapa (camadas, legenda, atributos, medição...) e para a gaveta em
   celular — um painel novo de qualquer item futuro entra sem CSS próprio (refutação do UX-04).
   Filhos: o conteúdo vai para o corpo; um filho com slot="acoes" vai para as ações do cabeçalho; slot="rodape" para o
   rodapé. Propriedade `titulo`; métodos recolher(bool) / fechar(); eventos 'recolher' {recolhido} e 'fechar'.
   Sem shadow DOM (as folhas globais e o axe alcançam tudo): a distribuição por slot é feita à mão em connectedCallback. */
import { h } from '../dom.js';
import { aoTraduzir, t } from '../i18n.js';

let seq = 0;
export class PlatPainel extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const id = `painel-${++seq}`;
    const filhos = [...this.childNodes];
    const acoes = filhos.filter((n) => n.nodeType === 1 && n.getAttribute('slot') === 'acoes');
    const rodape = filhos.filter((n) => n.nodeType === 1 && n.getAttribute('slot') === 'rodape');
    const corpo = filhos.filter((n) => !acoes.includes(n) && !rodape.includes(n));
    this._titulo = h('h2', { id: `${id}-titulo` }, this.getAttribute('titulo') || '');
    this._acoes = h('div', { class: 'painel-acoes' }, ...acoes);
    this._corpo = h('div', { class: 'painel-corpo', id: `${id}-corpo` }, ...corpo);
    this._cabecalho = h('div', { class: 'painel-cabecalho' }, this._titulo, this._acoes);
    if (this.hasAttribute('recolhivel')) {
      this._btRecolher = h('button', { type: 'button', class: 'pequeno texto', 'aria-expanded': String(!this.hasAttribute('recolhido')), 'aria-controls': `${id}-corpo` }, this._rotuloRecolher());
      this._btRecolher.addEventListener('click', () => this.recolher(!this.hasAttribute('recolhido')));
      this._acoes.append(this._btRecolher);
    }
    if (this.hasAttribute('fechavel')) {
      const bt = h('button', { type: 'button', class: 'fechar-x', 'aria-label': t('painel.fechar') }, '×');
      bt.addEventListener('click', () => this.fechar());
      this._btFechar = bt;
      this._acoes.append(bt);
    }
    this.setAttribute('role', 'region');
    this.setAttribute('aria-labelledby', `${id}-titulo`);
    this.append(this._cabecalho, this._corpo);
    if (rodape.length) this.append(h('div', { class: 'painel-rodape' }, ...rodape));
    this._cancelar = aoTraduzir(() => {
      if (this._btRecolher) this._btRecolher.textContent = this._rotuloRecolher();
      if (this._btFechar) this._btFechar.setAttribute('aria-label', t('painel.fechar'));
    });
  }
  disconnectedCallback() { this._cancelar?.(); }
  _rotuloRecolher() { return this.hasAttribute('recolhido') ? t('painel.expandir') : t('painel.recolher'); }
  get corpo() { return this._corpo; }
  get titulo() { return this._titulo?.textContent || ''; }
  set titulo(v) { this.setAttribute('titulo', v); if (this._titulo) this._titulo.textContent = v; }
  recolher(sim = true) {
    this.toggleAttribute('recolhido', sim);
    if (this._btRecolher) { this._btRecolher.setAttribute('aria-expanded', String(!sim)); this._btRecolher.textContent = this._rotuloRecolher(); }
    this.dispatchEvent(new CustomEvent('recolher', { detail: { recolhido: sim } }));
  }
  fechar() { this.hidden = true; this.dispatchEvent(new CustomEvent('fechar')); }
  abrir() { this.hidden = false; this.recolher(false); }
}
customElements.define('plat-painel', PlatPainel);
