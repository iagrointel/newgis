/* <plat-dialogo [modo="lateral"]> — sobre <dialog> nativo (foco preso, Escape, backdrop). abrir({titulo, corpo, botoes}) -> Promise<id|null>.
   corpo: Node. botoes: [{id, rotulo, classe}]. fechar(resultado). Devolve o foco a quem abriu. confirmar() é o atalho de sim/não.
   Estados: repouso (fechado), aberto com foco preso, ocupado (aria-busy: corpo esmaecido, botões desativados, giro no
   cabeçalho), vazio (corpo sem nós mostra "nada a mostrar"), erro (erro(texto) no rodapé, role=alert). */
import { h, limpar } from '../dom.js';
import { icone } from '../icones.js';
import { aoTraduzir, t } from '../i18n.js';

let seq = 0;
export class PlatDialogo extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const id = `dlg-${++seq}`;
    const lateral = this.getAttribute('modo') === 'lateral';
    this._titulo = h('h2', { id: `${id}-titulo` });
    this._fechar = h('button', { type: 'button', class: 'fechar-x icone-so', 'aria-label': t('dialogo.fechar') }, icone('fechar', { tamanho: 18 }));
    this._fechar.addEventListener('click', () => this.fechar(null));
    this._corpo = h('div', { class: 'dialogo-corpo', 'data-vazio': t('dialogo.vazio') });
    this._erro = h('span', { class: 'dialogo-erro', role: 'alert', hidden: true });
    this._botoes = h('div', { class: 'dialogo-botoes' });
    this._dlg = h('dialog', { class: `dialogo${lateral ? ' dialogo-lateral' : ''}`, 'aria-labelledby': `${id}-titulo` },
      h('div', { class: 'dialogo-cabecalho' }, this._titulo, this._fechar), this._corpo, this._botoes);
    this._dlg.addEventListener('cancel', (e) => { e.preventDefault(); this.fechar(null); });
    this._dlg.addEventListener('close', () => this._resolver?.(this._resultado ?? null));
    this.append(this._dlg);
    this._cancelar = aoTraduzir(() => { this._fechar.setAttribute('aria-label', t('dialogo.fechar')); this._corpo.dataset.vazio = t('dialogo.vazio'); });
  }
  disconnectedCallback() { this._cancelar?.(); }
  get corpo() { return this._corpo; }
  get aberto() { return !!this._dlg?.open; }
  set ocupado(v) {
    this._ocupado = !!v;
    this._dlg.setAttribute('aria-busy', String(this._ocupado));
    this._botoes.querySelectorAll('button').forEach((b) => { b.disabled = this._ocupado; });
  }
  get ocupado() { return !!this._ocupado; }
  erro(texto) {
    this._erro.textContent = texto || '';
    this._erro.hidden = !texto;
    if (texto && !this._erro.isConnected) this._botoes.prepend(this._erro);
    if (!texto && this._erro.isConnected) this._erro.remove();
  }
  abrir({ titulo, corpo, botoes = [] }) {
    this._quemAbriu = document.activeElement;
    this._titulo.textContent = titulo || '';
    limpar(this._corpo); limpar(this._botoes);
    this.erro('');
    this.ocupado = false;
    if (corpo) this._corpo.append(corpo);
    for (const b of botoes) {
      const btn = h('button', { type: 'button', class: b.classe || '' }, b.rotulo);
      btn.addEventListener('click', () => this.fechar(b.id));
      this._botoes.append(btn);
    }
    this._resultado = null;
    if (!this._dlg.open) this._dlg.showModal();
    const alvo = this._corpo.querySelector('input:not([type=hidden]):not([disabled]), select, textarea, button') || this._botoes.querySelector('button') || this._fechar;
    alvo.focus();
    return new Promise((res) => { this._resolver = res; });
  }
  fechar(resultado = null) {
    this._resultado = resultado;
    if (this._dlg.open) this._dlg.close();
    const q = this._quemAbriu;
    if (q && typeof q.focus === 'function' && document.contains(q)) q.focus();
  }
}
customElements.define('plat-dialogo', PlatDialogo);

let singular = null;
function dialogoSingular() {
  if (!singular) { singular = h('plat-dialogo'); document.body.append(singular); }
  return singular;
}

/* confirmar(titulo, texto, {ok, perigo}) -> Promise<boolean> */
export async function confirmar(titulo, texto, { ok = t('dialogo.confirmar'), perigo = false } = {}) {
  const d = dialogoSingular();
  const r = await d.abrir({
    titulo, corpo: h('p', {}, texto),
    botoes: [{ id: 'cancelar', rotulo: t('dialogo.cancelar') }, { id: 'ok', rotulo: ok, classe: perigo ? 'perigo' : 'primario' }],
  });
  return r === 'ok';
}

/* pedir(titulo, formularioEl) -> Promise<valores|null>: abre um <plat-formulario> num diálogo e resolve no 'enviar' */
export function pedir(titulo, form) {
  const d = dialogoSingular();
  return new Promise((res) => {
    const aoEnviar = (e) => { d.fechar('ok'); res(e.detail.valores); };
    form.addEventListener('enviar', aoEnviar, { once: true });
    form.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') d.fechar(null); }, { once: true });
    d.abrir({ titulo, corpo: form }).then((r) => { if (r !== 'ok') { form.removeEventListener('enviar', aoEnviar); res(null); } });
  });
}
