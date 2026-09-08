import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['tema.mudou'], acoes: ['tema.definir'] });
const CHAVE = 'plat.tema';
const TEMAS = [['sistema', 'Sistema'], ['light', 'Claro'], ['dark', 'Escuro']];

/* seletor de tema (tokens.css: sem atributo = sistema; data-theme=light|dark no <html> vence) */
class PlatTema extends PlatWidget {
  renderizar() {
    const atual = document.documentElement.dataset.theme || 'sistema';
    const grupo = document.createElement('div'); grupo.className = 'plat-tema'; grupo.setAttribute('role', 'group');
    grupo.setAttribute('aria-label', this.configuracao.rotulo || 'Tema');
    for (const [valor, rotulo] of TEMAS) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = rotulo; b.dataset.tema = valor;
      b.setAttribute('aria-pressed', String(valor === atual));
      b.addEventListener('click', () => this.definir(valor));
      grupo.append(b);
    }
    this.replaceChildren(grupo);
  }

  definir(valor) {
    if (valor === 'sistema') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = valor;
    try { if (valor === 'sistema') localStorage.removeItem(CHAVE); else localStorage.setItem(CHAVE, valor); } catch { /* sem armazenamento */ }
    this.emitir('tema.mudou', { tema: valor });
    this.renderizar();
  }

  acao_tema_definir(detalhe) { this.definir(String(detalhe.tema || 'sistema')); }
}

definir('plat-tema', PlatTema);
