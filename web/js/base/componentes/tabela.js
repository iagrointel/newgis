/* <plat-tabela> — tabela declarativa. Propriedades: colunas [{chave, titulo, formatar(valor, linha) -> texto|Node, classe}],
   linhas [], chave ('id'), selecionavel (bool), acoes (linha -> [{id, rotulo, classe, titulo}]) , vazio (texto).
   Eventos: 'acao' {id, linha}, 'selecao' {ids}. Getter selecionados; limparSelecao(). Sem HTML em string. */
import { h, limpar } from '../dom.js';
import { aoTraduzir, t } from '../i18n.js';

export class PlatTabela extends HTMLElement {
  constructor() {
    super();
    this._colunas = []; this._linhas = []; this._chave = 'id'; this._sel = new Set(); this._selecionavel = false;
    this._acoes = null; this._vazio = null; this._limiteSelecao = Infinity;
  }
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.classList.add('tabela-rolagem');
    this._tabela = h('table', { class: 'tabela' });
    // legenda como aria-label (não <caption class="sr-only">: a caption absoluta de 1 px deixava um traço visível no canto)
    if (this.getAttribute('legenda')) this._tabela.setAttribute('aria-label', this.getAttribute('legenda'));
    this._thead = h('thead'); this._tbody = h('tbody');
    this._tabela.append(this._thead, this._tbody);
    this.append(this._tabela);
    this.render();
    this._cancelar = aoTraduzir(() => this.render());
  }
  disconnectedCallback() { this._cancelar?.(); }
  set colunas(v) { this._colunas = v || []; this.render(); }
  get colunas() { return this._colunas; }
  set linhas(v) { this._linhas = Array.isArray(v) ? v : []; this._sel.clear(); this.render(); this._emitirSelecao(); }
  get linhas() { return this._linhas; }
  set chave(v) { this._chave = v; }
  set selecionavel(v) { this._selecionavel = !!v; this.render(); }
  set limiteSelecao(n) { this._limiteSelecao = n; }
  set acoes(v) { this._acoes = v; this.render(); }
  set vazio(v) { this._vazio = v; this.render(); }
  get selecionados() { return [...this._sel]; }
  limparSelecao() { this._sel.clear(); this.render(); this._emitirSelecao(); }
  _emitirSelecao() { this.dispatchEvent(new CustomEvent('selecao', { detail: { ids: this.selecionados } })); }
  _acoesDe(linha) {
    if (!this._acoes) return [];
    return typeof this._acoes === 'function' ? (this._acoes(linha) || []) : this._acoes;
  }
  render() {
    if (!this._montado) return;
    limpar(this._thead); limpar(this._tbody);
    const temAcoes = !!this._acoes;
    const tr = h('tr');
    if (this._selecionavel) {
      const todos = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_todos') });
      todos.checked = this._linhas.length > 0 && this._linhas.every((l) => this._sel.has(l[this._chave]));
      todos.addEventListener('change', () => {
        this._sel.clear();
        if (todos.checked) this._linhas.slice(0, this._limiteSelecao).forEach((l) => this._sel.add(l[this._chave]));
        this.render(); this._emitirSelecao();
      });
      tr.append(h('th', { scope: 'col' }, todos));
    }
    for (const c of this._colunas) tr.append(h('th', { scope: 'col', class: c.classe }, c.titulo));
    if (temAcoes) tr.append(h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, t('tabela.acoes'))));
    this._thead.append(tr);
    if (!this._linhas.length) {
      const n = this._colunas.length + (this._selecionavel ? 1 : 0) + (temAcoes ? 1 : 0);
      this._tbody.append(h('tr', {}, h('td', { colspan: n, class: 'vazio' }, this._vazio ?? t('tabela.vazio'))));
      return;
    }
    for (const linha of this._linhas) {
      const id = linha[this._chave];
      const trl = h('tr', { 'aria-selected': this._selecionavel ? String(this._sel.has(id)) : undefined });
      if (this._selecionavel) {
        const cx = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_linha') });
        cx.checked = this._sel.has(id);
        cx.addEventListener('change', () => {
          if (cx.checked) {
            if (this._sel.size >= this._limiteSelecao) { cx.checked = false; return; }
            this._sel.add(id);
          } else this._sel.delete(id);
          trl.setAttribute('aria-selected', String(cx.checked));
          this._emitirSelecao();
        });
        trl.append(h('td', {}, cx));
      }
      for (const c of this._colunas) {
        const bruto = c.chave ? linha[c.chave] : undefined;
        const v = c.formatar ? c.formatar(bruto, linha) : bruto;
        trl.append(h('td', { class: c.classe }, v === undefined || v === null ? '' : v));
      }
      if (temAcoes) {
        const cel = h('td', { class: 'acoes-linha' });
        for (const a of this._acoesDe(linha)) {
          const b = h('button', { type: 'button', class: `pequeno ${a.classe || ''}`.trim(), title: a.titulo }, a.rotulo);
          b.addEventListener('click', () => this.dispatchEvent(new CustomEvent('acao', { detail: { id: a.id, linha } })));
          cel.append(b);
        }
        trl.append(cel);
      }
      this._tbody.append(trl);
    }
  }
}
customElements.define('plat-tabela', PlatTabela);
