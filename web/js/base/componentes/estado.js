/* <plat-estado tipo="vazio|carregando|erro|negado"> — o estado explícito de uma área da tela (sistema de design,
   UX-01). Toda lista, painel e formulário mostra um destes em vez de ficar em branco. mostrar({tipo, titulo, texto,
   acoes: [{id, rotulo, classe}], ref}) / vazio(texto) / carregando(texto) / erro(texto|resposta) / negado(texto) /
   limpar(). Evento 'acao' {id}. Textos padrão por i18n (estado.*); `ref` (req_id) aparece em fonte de dado para o
   usuário citar ao suporte. carregando: aria-busy no próprio elemento + esqueleto; erro: role=alert. */
import { h, limpar } from '../dom.js';
import { aoTraduzir, t } from '../i18n.js';

const PADRAO = {
  vazio: { titulo: 'estado.vazio_titulo', texto: 'estado.vazio_texto' },
  carregando: { titulo: 'estado.carregando_titulo', texto: '' },
  erro: { titulo: 'estado.erro_titulo', texto: 'estado.erro_texto' },
  negado: { titulo: 'estado.negado_titulo', texto: 'estado.negado_texto' },
};

export class PlatEstado extends HTMLElement {
  connectedCallback() {
    if (this._montado) return;
    this._montado = true;
    this._ultimo = null;
    if (this.getAttribute('tipo')) this.mostrar({ tipo: this.getAttribute('tipo') });
    else this.hidden = true;
    this._cancelar = aoTraduzir(() => { if (this._ultimo) this.mostrar(this._ultimo); });
  }
  disconnectedCallback() { this._cancelar?.(); }
  mostrar({ tipo = 'vazio', titulo, texto, acoes = [], ref } = {}) {
    this._ultimo = { tipo, titulo, texto, acoes, ref };
    const p = PADRAO[tipo] || PADRAO.vazio;
    limpar(this);
    this.setAttribute('tipo', tipo);
    this.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
    this.setAttribute('aria-live', tipo === 'erro' ? 'assertive' : 'polite');
    this.setAttribute('aria-busy', String(tipo === 'carregando'));
    this.append(h('p', { class: 'estado-titulo' }, titulo ?? t(p.titulo)));
    const tx = texto ?? (p.texto ? t(p.texto) : '');
    if (tx) this.append(h('p', { class: 'estado-texto' }, tx));
    if (tipo === 'carregando') this.append(h('div', { class: 'esqueleto', 'aria-hidden': 'true' }, h('span'), h('span'), h('span')));
    if (ref) this.append(h('p', { class: 'ref-suporte' }, t('estado.ref', { ref })));
    if (acoes.length) {
      const div = h('div', { class: 'estado-acoes' });
      for (const a of acoes) {
        const b = h('button', { type: 'button', class: a.classe || '', dataset: { acao: a.id } }, a.rotulo);
        b.addEventListener('click', () => this.dispatchEvent(new CustomEvent('acao', { detail: { id: a.id } })));
        div.append(b);
      }
      this.append(div);
    }
    this.hidden = false;
  }
  vazio(texto, acoes) { this.mostrar({ tipo: 'vazio', texto, acoes }); }
  carregando(texto) { this.mostrar({ tipo: 'carregando', texto }); }
  negado(texto) { this.mostrar({ tipo: 'negado', texto }); }
  /* erro(texto) ou erro(resposta {status, json:{mensagem, req_id}}): 403 vira negado, 0 vira "sem rede" */
  erro(x, acoes) {
    if (x && typeof x === 'object') {
      const j = x.json || {};
      if (x.status === 403) return this.mostrar({ tipo: 'negado', texto: j.mensagem, acoes });
      const texto = x.status === 0 ? t('estado.sem_rede') : (j.mensagem || undefined);
      return this.mostrar({ tipo: 'erro', texto, acoes: acoes ?? [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }], ref: j.req_id });
    }
    return this.mostrar({ tipo: 'erro', texto: x, acoes: acoes ?? [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
  }
  limpar() { this._ultimo = null; limpar(this); this.removeAttribute('tipo'); this.setAttribute('aria-busy', 'false'); this.hidden = true; }
}
customElements.define('plat-estado', PlatEstado);
