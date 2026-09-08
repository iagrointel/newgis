import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['controlador.alternado'], acoes: ['controlador.abrir', 'controlador.fechar'] });

/* controlador de widgets: um botão por alvo (id de nó do documento); abre/fecha o alvo com `hidden` e o botão
   diz o estado (aria-expanded). O alvo é achado pelo `data-no-id` que o motor põe em todo widget. */
class PlatControlador extends PlatWidget {
  _alvo(id) { return document.querySelector(`[data-no-id="${CSS.escape(String(id))}"]`); }

  renderizar() {
    const c = this.configuracao;
    const barra = document.createElement('div'); barra.className = 'plat-w-controlador';
    for (const alvo of c.alvos || []) {
      const el = this._alvo(alvo.id);
      const b = document.createElement('button'); b.type = 'button'; b.textContent = alvo.rotulo || alvo.id;
      b.dataset.alvo = alvo.id;
      b.setAttribute('aria-expanded', el ? String(!el.hidden) : 'false');
      if (!el) b.title = 'widget não encontrado nesta página';
      b.addEventListener('click', () => this.alternar(alvo.id, b));
      barra.append(b);
    }
    this.replaceChildren(barra);
  }

  alternar(id, botao = null, forcar = null) {
    const el = this._alvo(id);
    if (!el) return false;
    el.hidden = forcar === null ? !el.hidden : !forcar;
    const b = botao || this.querySelector(`button[data-alvo="${CSS.escape(String(id))}"]`);
    if (b) b.setAttribute('aria-expanded', String(!el.hidden));
    this.emitir('controlador.alternado', { alvo: id, aberto: !el.hidden });
    return true;
  }

  acao_controlador_abrir(detalhe) { this.alternar(detalhe.alvo, null, true); }
  acao_controlador_fechar(detalhe) { this.alternar(detalhe.alvo, null, false); }
}

definir('plat-w-controlador', PlatControlador);
