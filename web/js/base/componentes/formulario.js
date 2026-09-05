/* <plat-formulario> — formulário declarativo. campos: [{nome, rotulo, tipo, obrigatorio, ajuda, padrao, opcoes, atributos, desabilitado}]
   tipos: texto | senha | email | numero | select | caixa | caixas | area | lista | info | oculto
   botoes: [{id, rotulo, tipo: 'submit'|'button', classe}]. Eventos: 'enviar' {valores}, 'botao' {id}.
   valores() / definir(obj) / erro(nome, texto) / limparErros() / ocupado / mensagem(texto, tipo). Rótulo ligado por for/id;
   erro por aria-describedby + aria-invalid; senha com botão mostrar/ocultar (aria-pressed). */
import { h, limpar } from '../dom.js';
import { aoTraduzir, t } from '../i18n.js';

let seq = 0;
export class PlatFormulario extends HTMLElement {
  constructor() { super(); this._campos = []; this._botoes = []; this._els = {}; this._erros = {}; this._id = `f${++seq}`; }
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.render();
    this._cancelar = aoTraduzir(() => { if (this._campos.length && !this._ocupado) this.render(); });
  }
  disconnectedCallback() { this._cancelar?.(); }
  set campos(v) { this._campos = v || []; this.render(); }
  get campos() { return this._campos; }
  set botoes(v) { this._botoes = v || []; this.render(); }
  set ocupado(v) {
    this._ocupado = !!v;
    this.querySelectorAll('button, input, select, textarea').forEach((el) => { el.disabled = this._ocupado || el.dataset.fixo === '1'; });
    this.setAttribute('aria-busy', String(this._ocupado));
  }
  get ocupado() { return !!this._ocupado; }
  mensagem(texto, tipo = 'info') { if (this._aviso) { if (texto) this._aviso.mostrar(texto, tipo); else this._aviso.limpar(); } }
  campo(nome) { return this._els[nome]?.input; }
  focarPrimeiro() {
    const el = this.querySelector('input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])');
    el?.focus();
  }
  render() {
    if (!this._montado) return;
    limpar(this);
    this._els = {}; this._erros = {};
    this._form = h('form', { class: 'form', novalidate: true, autocomplete: this.getAttribute('autocompletar') || 'off' });
    for (const c of this._campos) this._form.append(this._campoEl(c));
    this._aviso = h('plat-aviso');
    this._form.append(this._aviso);
    if (this._botoes.length) {
      const div = h('div', { class: 'botoes' });
      for (const b of this._botoes) {
        const btn = h('button', { type: b.tipo === 'submit' ? 'submit' : 'button', class: b.classe || (b.tipo === 'submit' ? 'primario' : '') }, b.rotulo);
        if (b.tipo !== 'submit') btn.addEventListener('click', () => this.dispatchEvent(new CustomEvent('botao', { detail: { id: b.id } })));
        div.append(btn);
      }
      this._form.append(div);
    }
    this._form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.limparErros();
      if (!this._validar()) return;
      this.dispatchEvent(new CustomEvent('enviar', { detail: { valores: this.valores() } }));
    });
    this.append(this._form);
  }
  _campoEl(c) {
    const id = `${this._id}-${c.nome}`;
    const wrap = h('div', { class: 'campo', dataset: { campo: c.nome } });
    const rot = h('label', { for: id }, c.rotulo, c.obrigatorio ? h('span', { class: 'obrigatorio', 'aria-hidden': 'true' }, ' *') : null);
    let input;
    const base = { id, name: c.nome, required: !!c.obrigatorio, ...(c.atributos || {}) };
    switch (c.tipo) {
      case 'select':
        input = h('select', base);
        for (const o of c.opcoes || []) input.append(h('option', { value: o.valor }, o.rotulo));
        if (c.padrao !== undefined) input.value = String(c.padrao);
        break;
      case 'caixa':
        input = h('input', { ...base, type: 'checkbox' });
        input.checked = !!c.padrao;
        wrap.classList.add('caixa');
        wrap.append(input, h('label', { for: id }, c.rotulo));
        if (c.ajuda) wrap.append(h('span', { class: 'ajuda', id: `${id}-ajuda` }, c.ajuda));
        this._els[c.nome] = { input, wrap, def: c };
        if (c.desabilitado) input.dataset.fixo = '1';
        if (c.desabilitado) input.disabled = true;
        return wrap;
      case 'caixas': {
        input = h('fieldset', { class: 'caixas', id });
        input.append(h('legend', { class: 'campo-rotulo' }, c.rotulo));
        let grupo = null;
        const marcados = new Set(c.padrao || []);
        for (const o of c.opcoes || []) {
          if (o.grupo && o.grupo !== grupo) { grupo = o.grupo; input.append(h('div', { class: 'grupo-caixas' }, grupo)); }
          const cid = `${id}-${o.valor}`.replace(/[^a-zA-Z0-9_-]/g, '_');
          const cx = h('input', { type: 'checkbox', id: cid, name: c.nome, value: o.valor, title: o.titulo });
          cx.checked = marcados.has(o.valor);
          if (o.desabilitado) { cx.disabled = true; cx.dataset.fixo = '1'; }
          input.append(h('div', { class: 'caixa' }, cx, h('label', { for: cid, title: o.titulo }, o.rotulo, o.marca ? h('span', { class: 'marcador' }, ` ${o.marca}`) : null)));
        }
        wrap.append(input);
        if (c.ajuda) wrap.append(h('span', { class: 'ajuda', id: `${id}-ajuda` }, c.ajuda));
        this._els[c.nome] = { input, wrap, def: c };
        return wrap;
      }
      case 'area': case 'lista':
        input = h('textarea', { ...base, rows: c.linhas || 4 });
        input.value = c.tipo === 'lista' ? (c.padrao || []).join('\n') : (c.padrao ?? '');
        break;
      case 'info':
        wrap.append(h('span', { class: 'campo-rotulo' }, c.rotulo), h('span', { class: 'info', id }, c.padrao ?? ''));
        this._els[c.nome] = { input: null, wrap, def: c };
        return wrap;
      case 'oculto':
        input = h('input', { ...base, type: 'hidden', value: c.padrao ?? '' });
        wrap.classList.add('oculto');
        wrap.append(input);
        this._els[c.nome] = { input, wrap, def: c };
        return wrap;
      default: {
        const tipo = { texto: 'text', senha: 'password', email: 'email', numero: 'number' }[c.tipo] || 'text';
        input = h('input', { ...base, type: tipo, value: c.padrao ?? '' });
        if (c.tipo === 'senha' && c.mostrar !== false) {
          const bt = h('button', { type: 'button', class: 'pequeno', 'aria-pressed': 'false', 'aria-controls': id }, t('form.mostrar'));
          bt.addEventListener('click', () => {
            const ver = input.type === 'password';
            input.type = ver ? 'text' : 'password';
            bt.setAttribute('aria-pressed', String(ver));
            bt.textContent = ver ? t('form.ocultar') : t('form.mostrar');
          });
          wrap.append(rot, h('div', { class: 'linha-senha' }, input, bt));
          if (c.ajuda) wrap.append(h('span', { class: 'ajuda', id: `${id}-ajuda` }, c.ajuda));
          input.setAttribute('aria-describedby', c.ajuda ? `${id}-ajuda` : '');
          this._els[c.nome] = { input, wrap, def: c };
          if (c.desabilitado) { input.disabled = true; input.dataset.fixo = '1'; }
          return wrap;
        }
      }
    }
    wrap.append(rot, input);
    if (c.ajuda) { wrap.append(h('span', { class: 'ajuda', id: `${id}-ajuda` }, c.ajuda)); input.setAttribute('aria-describedby', `${id}-ajuda`); }
    if (c.desabilitado) { input.disabled = true; input.dataset.fixo = '1'; }
    this._els[c.nome] = { input, wrap, def: c };
    return wrap;
  }
  _validar() {
    let ok = true;
    for (const c of this._campos) {
      const e = this._els[c.nome];
      if (!e?.input || !c.obrigatorio || c.tipo === 'caixa' || c.tipo === 'caixas') continue;
      if (!String(e.input.value ?? '').trim()) { this.erro(c.nome, t('form.obrigatorio')); ok = false; }
    }
    if (!ok) this.querySelector('[aria-invalid="true"]')?.focus();
    return ok;
  }
  valores() {
    const v = {};
    for (const c of this._campos) {
      const e = this._els[c.nome];
      if (!e?.input) continue;
      switch (c.tipo) {
        case 'caixa': v[c.nome] = !!e.input.checked; break;
        case 'caixas': v[c.nome] = [...e.input.querySelectorAll('input:checked')].map((x) => x.value); break;
        case 'lista': v[c.nome] = e.input.value.split('\n').map((s) => s.trim()).filter(Boolean); break;
        case 'numero': v[c.nome] = e.input.value === '' ? null : Number(e.input.value); break;
        default: v[c.nome] = e.input.value.trim();
      }
    }
    return v;
  }
  definir(obj) {
    for (const [k, val] of Object.entries(obj || {})) {
      const e = this._els[k];
      if (!e) continue;
      if (!e.input) { e.wrap.querySelector('.info').textContent = val ?? ''; continue; }
      if (e.def.tipo === 'caixa') e.input.checked = !!val;
      else if (e.def.tipo === 'caixas') e.input.querySelectorAll('input').forEach((x) => { x.checked = (val || []).includes(x.value); });
      else if (e.def.tipo === 'lista') e.input.value = (val || []).join('\n');
      else e.input.value = val ?? '';
    }
  }
  erro(nome, texto) {
    const e = this._els[nome];
    if (!e) { this.mensagem(texto, 'erro'); return; }
    const id = `${this._id}-${nome}-erro`;
    let el = e.wrap.querySelector('.erro-campo');
    if (!el) { el = h('span', { class: 'erro-campo', id, role: 'alert' }); e.wrap.append(el); }
    el.textContent = texto;
    if (e.input) {
      e.input.setAttribute('aria-invalid', 'true');
      const desc = (e.input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
      if (!desc.includes(id)) desc.push(id);
      e.input.setAttribute('aria-describedby', desc.join(' '));
    }
  }
  limparErros() {
    this.querySelectorAll('.erro-campo').forEach((el) => el.remove());
    this.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
    this.mensagem('');
  }
}
customElements.define('plat-formulario', PlatFormulario);
