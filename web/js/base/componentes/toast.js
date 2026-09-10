/* <plat-toasts> + notificar(texto, {tipo, duracao, acoes}) — aviso passageiro do sistema de design (UX-01), para
   confirmar uma ação sem ocupar a tela (salvo, copiado, item apagado com "desfazer"). Uma região por página (montada
   sozinha no primeiro uso), aria-live polite (erro: assertive); no máximo 3 visíveis, a mais velha sai; fecha por
   botão, por Escape com foco dentro, ou por tempo (padrão 6 s; erro não fecha sozinho). acoes: [{id, rotulo}] →
   Promise<id|null>. Quem quer estado persistente usa <plat-aviso>; toast é para o que já aconteceu. */
import { h } from '../dom.js';
import { t } from '../i18n.js';

const MAXIMO = 3;
const DURACAO = 6000;

export class PlatToasts extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this.setAttribute('role', 'region');
    this.setAttribute('aria-label', t('toast.regiao'));
  }
  notificar(texto, { tipo = 'info', duracao, acoes = [] } = {}) {
    while (this.children.length >= MAXIMO) this.firstElementChild.remove();
    const vivo = tipo === 'erro' ? 'assertive' : 'polite';
    const fechar = h('button', { type: 'button', class: 'fechar-x', 'aria-label': t('toast.fechar') }, '×');
    const el = h('div', { class: 'toast', dataset: { tipo }, role: tipo === 'erro' ? 'alert' : 'status', 'aria-live': vivo, tabindex: '-1' },
      h('span', { class: 'toast-texto' }, texto), fechar);
    let resolver = () => {};
    const prometido = new Promise((res) => { resolver = res; });
    const encerrar = (id) => { clearTimeout(relogio); el.remove(); resolver(id); };
    fechar.addEventListener('click', () => encerrar(null));
    el.addEventListener('keydown', (e) => { if (e.key === 'Escape') encerrar(null); });
    if (acoes.length) {
      const div = h('div', { class: 'toast-acoes' });
      for (const a of acoes) {
        const b = h('button', { type: 'button', class: `pequeno ${a.classe || ''}`.trim() }, a.rotulo);
        b.addEventListener('click', () => encerrar(a.id));
        div.append(b);
      }
      el.append(div);
    }
    const tempo = duracao ?? (tipo === 'erro' ? 0 : DURACAO);
    const relogio = tempo > 0 ? setTimeout(() => encerrar(null), tempo) : null;
    el.addEventListener('mouseenter', () => clearTimeout(relogio));
    this.append(el);
    return prometido;
  }
}
customElements.define('plat-toasts', PlatToasts);

let regiao = null;
export function notificar(texto, opcoes) {
  if (!regiao || !document.body.contains(regiao)) { regiao = h('plat-toasts'); document.body.append(regiao); }
  return regiao.notificar(texto, opcoes);
}
