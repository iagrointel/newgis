/* <plat-tabela> — tabela declarativa. Propriedades: colunas [{chave, titulo, formatar(valor, linha) -> texto|Node, classe, ordenavel}],
   linhas [], chave ('id'), selecionavel (bool), acoes (linha -> [{id, rotulo, classe, titulo, icone}]), vazio (texto), ordem {campo, dir}.
   Eventos: 'acao' {id, linha}, 'selecao' {ids}, 'ordenar' {campo, dir}. Getter selecionados; limparSelecao(). Sem HTML em string.
   Estados: repouso, foco (caixas e botões), ativo (linha aria-selected), desativada (atributo disabled), carregando (ocupado =
   aria-busy + linhas-esqueleto), vazia (desenho com ícone + texto), erro (erro(texto, aoRepetir) = linha com ícone e botão
   "tentar de novo"). Cabeçalho ordenável com ícone da família (nunca glifo de texto). */
import { h, limpar } from '../dom.js';
import { icone } from '../icones.js';
import { aoTraduzir, t } from '../i18n.js';

export class PlatTabela extends HTMLElement {
  static get observedAttributes() { return ['disabled']; }
  constructor() {
    super();
    this._colunas = []; this._linhas = []; this._chave = 'id'; this._sel = new Set(); this._selecionavel = false;
    this._acoes = null; this._vazio = null; this._limiteSelecao = Infinity; this._ocupado = false; this._erro = null; this._ordem = null;
  }
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.classList.add('tabela-rolagem');
    this._tabela = h('table', { class: 'tabela' });
    if (this.getAttribute('legenda')) this._tabela.append(h('caption', { class: 'sr-only' }, this.getAttribute('legenda')));
    this._thead = h('thead'); this._tbody = h('tbody');
    this._tabela.append(this._thead, this._tbody);
    this.append(this._tabela);
    this.render();
    this._cancelar = aoTraduzir(() => this.render());
  }
  disconnectedCallback() { this._cancelar?.(); }
  attributeChangedCallback() { if (this._montado) this.render(); }
  set colunas(v) { this._colunas = v || []; this.render(); }
  get colunas() { return this._colunas; }
  set linhas(v) { this._linhas = Array.isArray(v) ? v : []; this._sel.clear(); this._erro = null; this.render(); this._emitirSelecao(); }
  get linhas() { return this._linhas; }
  set chave(v) { this._chave = v; }
  set selecionavel(v) { this._selecionavel = !!v; this.render(); }
  set limiteSelecao(n) { this._limiteSelecao = n; }
  set acoes(v) { this._acoes = v; this.render(); }
  set vazio(v) { this._vazio = v; this.render(); }
  set ordem(v) { this._ordem = v || null; this.render(); }
  get ordem() { return this._ordem; }
  set ocupado(v) { this._ocupado = !!v; this.setAttribute('aria-busy', String(this._ocupado)); if (this._ocupado && !this._linhas.length) this.render(); }
  get ocupado() { return this._ocupado; }
  get desativada() { return this.hasAttribute('disabled'); }
  set desativada(v) { if (v) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); }
  erro(texto, aoRepetir) { this._erro = texto ? { texto, aoRepetir } : null; this._ocupado = false; this.setAttribute('aria-busy', 'false'); this.render(); }
  get selecionados() { return [...this._sel]; }
  limparSelecao() { this._sel.clear(); this.render(); this._emitirSelecao(); }
  _emitirSelecao() { this.dispatchEvent(new CustomEvent('selecao', { detail: { ids: this.selecionados } })); }
  _acoesDe(linha) {
    if (!this._acoes) return [];
    return typeof this._acoes === 'function' ? (this._acoes(linha) || []) : this._acoes;
  }
  _colunasTotais() { return this._colunas.length + (this._selecionavel ? 1 : 0) + (this._acoes ? 1 : 0); }
  _cabecalhoOrdenavel(c) {
    const ativa = this._ordem && this._ordem.campo === c.chave;
    const dir = ativa ? this._ordem.dir : null;
    const th = h('th', { scope: 'col', class: c.classe, tabindex: '0', 'aria-sort': ativa ? (dir === 'desc' ? 'descending' : 'ascending') : 'none' },
      c.titulo, ' ', icone(ativa ? (dir === 'desc' ? 'ordenar_desc' : 'ordenar_asc') : 'ordenar', { tamanho: 12 }));
    const alternar = () => {
      const nova = ativa && dir === 'asc' ? 'desc' : 'asc';
      this._ordem = { campo: c.chave, dir: nova };
      this.dispatchEvent(new CustomEvent('ordenar', { detail: { campo: c.chave, dir: nova } }));
      this.render();
    };
    th.addEventListener('click', alternar);
    th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); alternar(); } });
    return th;
  }
  render() {
    if (!this._montado) return;
    limpar(this._thead); limpar(this._tbody);
    const temAcoes = !!this._acoes;
    const desativada = this.desativada;
    const tr = h('tr');
    if (this._selecionavel) {
      const todos = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_todos') });
      todos.checked = this._linhas.length > 0 && this._linhas.every((l) => this._sel.has(l[this._chave]));
      todos.disabled = desativada || !this._linhas.length;
      todos.addEventListener('change', () => {
        this._sel.clear();
        if (todos.checked) this._linhas.slice(0, this._limiteSelecao).forEach((l) => this._sel.add(l[this._chave]));
        this.render(); this._emitirSelecao();
      });
      tr.append(h('th', { scope: 'col' }, todos));
    }
    for (const c of this._colunas) tr.append(c.ordenavel ? this._cabecalhoOrdenavel(c) : h('th', { scope: 'col', class: c.classe }, c.titulo));
    if (temAcoes) tr.append(h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, t('tabela.acoes'))));
    this._thead.append(tr);
    const n = this._colunasTotais();
    if (this._erro) {
      const cel = h('td', { colspan: n, class: 'erro-linha', role: 'alert' }, icone('erro', { tamanho: 16 }), this._erro.texto);
      if (this._erro.aoRepetir) {
        const bt = h('button', { type: 'button', class: 'pequeno' }, icone('atualizar', { tamanho: 14 }), t('tabela.tentar_de_novo'));
        bt.addEventListener('click', () => this._erro.aoRepetir());
        cel.append(bt);
      }
      this._tbody.append(h('tr', {}, cel));
      return;
    }
    if (!this._linhas.length) {
      if (this._ocupado) {
        for (let i = 0; i < 3; i++) {
          const trl = h('tr', { class: 'linha-esqueleto', 'aria-hidden': 'true' });
          for (let j = 0; j < n; j++) trl.append(h('td', {}, ' '));
          this._tbody.append(trl);
        }
        this._tbody.append(h('tr', {}, h('td', { colspan: n, class: 'vazio sr-only' }, t('tabela.carregando'))));
        return;
      }
      this._tbody.append(h('tr', {}, h('td', { colspan: n, class: 'vazio' },
        h('div', { class: 'vazio-desenho' }, icone('vazio', { tamanho: 32 }), h('span', {}, this._vazio ?? t('tabela.vazio'))))));
      return;
    }
    for (const linha of this._linhas) {
      const id = linha[this._chave];
      const trl = h('tr', { 'aria-selected': this._selecionavel ? String(this._sel.has(id)) : undefined });
      if (this._selecionavel) {
        const cx = h('input', { type: 'checkbox', 'aria-label': t('tabela.selecionar_linha') });
        cx.checked = this._sel.has(id);
        cx.disabled = desativada;
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
          const b = h('button', { type: 'button', class: `pequeno ${a.classe || ''}`.trim(), title: a.titulo }, a.icone ? icone(a.icone, { tamanho: 12 }) : null, a.rotulo);
          b.disabled = desativada;
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
