/* <plat-tema> — escolha de tema (sistema / claro / escuro) do sistema de design (UX-01). Grava em localStorage
   plat_tema e aplica data-theme em <html> na hora; js/base/tema_cedo.js reaplica a escolha antes da primeira pintura
   em toda página. Três botões de opção com rótulo por i18n; o estado "sistema" remove o atributo e deixa
   prefers-color-scheme decidir (regra da casa, tokens.css). aplicarTema(valor) e temaAtual() exportados. */
import { h } from '../dom.js';
import { aoTraduzir, t } from '../i18n.js';

export const CHAVE = 'plat_tema';
export const TEMAS = ['sistema', 'claro', 'escuro'];
const ATRIBUTO = { claro: 'light', escuro: 'dark' };

export function temaAtual() {
  try { const v = localStorage.getItem(CHAVE); return TEMAS.includes(v) ? v : 'sistema'; } catch { return 'sistema'; }
}

export function aplicarTema(valor) {
  const v = TEMAS.includes(valor) ? valor : 'sistema';
  if (ATRIBUTO[v]) document.documentElement.setAttribute('data-theme', ATRIBUTO[v]);
  else document.documentElement.removeAttribute('data-theme');
  try { if (v === 'sistema') localStorage.removeItem(CHAVE); else localStorage.setItem(CHAVE, v); } catch { /* sem armazenamento: só aplica */ }
  document.dispatchEvent(new CustomEvent('plat:tema', { detail: { tema: v } }));
  return v;
}

let seq = 0;
export class PlatTema extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    const nome = `tema-${++seq}`;
    this.setAttribute('role', 'radiogroup');
    this._rotulos = {};
    const atual = temaAtual();
    for (const v of TEMAS) {
      const input = h('input', { type: 'radio', name: nome, value: v, id: `${nome}-${v}` });
      input.checked = v === atual;
      input.addEventListener('change', () => { if (input.checked) aplicarTema(v); });
      const span = h('span', {}, t(`tema.${v}`));
      this._rotulos[v] = span;
      this.append(h('label', { for: `${nome}-${v}` }, input, span));
    }
    this._cancelar = aoTraduzir(() => {
      this.setAttribute('aria-label', t('tema.rotulo'));
      for (const v of TEMAS) this._rotulos[v].textContent = t(`tema.${v}`);
    });
  }
  disconnectedCallback() { this._cancelar?.(); }
  get valor() { return temaAtual(); }
  set valor(v) { const a = aplicarTema(v); this.querySelectorAll('input').forEach((i) => { i.checked = i.value === a; }); }
}
customElements.define('plat-tema', PlatTema);
