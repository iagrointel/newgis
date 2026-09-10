/* <plat-paginacao> — "1–50 de 123" + Anterior/Próxima; evento 'mudar' {deslocamento}. atualizar({total, limite, deslocamento}).
   Estados: repouso, foco (botões), desativada nas pontas, carregando (ocupado = aria-busy + ícone girando), vazia
   (total 0: "0–0 de 0", botões desativados, oculta quando cabe numa página), erro (erro(texto)). O total é uma
   RÉGUA: leva a procedência da chamada que o produziu (item L0-14). */
import { h } from '../dom.js';
import { icone } from '../icones.js';
import { aoTraduzir, formatarNumero, t } from '../i18n.js';
import { regua } from '../regua.js';

export class PlatPaginacao extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.classList.add('paginacao');
    this.setAttribute('role', 'navigation');
    this.setAttribute('aria-label', t('paginacao.rotulo'));
    this._texto = h('span', { 'aria-live': 'polite', class: 'paginacao-faixa' });
    this._carregando = h('span', { class: 'paginacao-carregando', hidden: true }, icone('carregando', { tamanho: 14 }), t('paginacao.carregando'));
    this._erro = h('span', { class: 'paginacao-erro', role: 'alert', hidden: true });
    this._ant = h('button', { type: 'button', class: 'pequeno', 'aria-label': t('paginacao.anterior') }, icone('chevron_esq', { tamanho: 14 }), t('paginacao.anterior'));
    this._prox = h('button', { type: 'button', class: 'pequeno', 'aria-label': t('paginacao.proxima') }, t('paginacao.proxima'), icone('chevron_dir', { tamanho: 14 }));
    this._ant.addEventListener('click', () => this._ir(this._desl - this._lim));
    this._prox.addEventListener('click', () => this._ir(this._desl + this._lim));
    this.append(this._erro, this._carregando, this._texto, this._ant, this._prox);
    this.atualizar({ total: 0, limite: 50, deslocamento: 0 });
    this._cancelar = aoTraduzir(() => {
      this.setAttribute('aria-label', t('paginacao.rotulo'));
      this._ant.lastChild.textContent = t('paginacao.anterior');
      this._prox.firstChild.textContent = t('paginacao.proxima');
      this.atualizar({ total: this._tot, limite: this._lim, deslocamento: this._desl });
    });
  }
  disconnectedCallback() { this._cancelar?.(); }
  _ir(d) {
    const novo = Math.max(0, d);
    this.dispatchEvent(new CustomEvent('mudar', { detail: { deslocamento: novo } }));
  }
  set ocupado(v) {
    this._ocupado = !!v;
    this.setAttribute('aria-busy', String(this._ocupado));
    this._carregando.hidden = !this._ocupado;
    this._ant.disabled = this._ocupado || this._desl <= 0;
    this._prox.disabled = this._ocupado || Math.min(this._tot, this._desl + this._lim) >= this._tot;
  }
  get ocupado() { return !!this._ocupado; }
  erro(texto) { this._erro.textContent = texto || ''; this._erro.hidden = !texto; if (texto) this.hidden = false; }
  atualizar({ total = 0, limite = 50, deslocamento = 0, origem } = {}) {
    this._tot = total; this._lim = limite; this._desl = deslocamento;
    this._erro.hidden = true;
    const ini = total ? deslocamento + 1 : 0;
    const fim = Math.min(total, deslocamento + limite);
    while (this._texto.firstChild) this._texto.removeChild(this._texto.firstChild);
    this._texto.append(regua(t('paginacao.faixa', { ini: formatarNumero(ini), fim: formatarNumero(fim), total: formatarNumero(total) }), { classe: 'direita', ...(origem ? { origem } : {}) }));
    this._ant.disabled = this._ocupado || deslocamento <= 0;
    this._prox.disabled = this._ocupado || fim >= total;
    this.hidden = total <= limite && deslocamento === 0 && !this.hasAttribute('sempre');
  }
}
customElements.define('plat-paginacao', PlatPaginacao);
