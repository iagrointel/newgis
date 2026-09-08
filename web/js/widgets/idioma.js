import { PlatWidget, definir } from './base.js';
import { carregar, idiomaAtual } from '../base/i18n.js';

export const contrato = Object.freeze({ eventos: ['idioma.mudou'], acoes: ['idioma.definir'] });
const CHAVE = 'plat.idioma';
const NOMES = { 'pt-BR': 'Português (Brasil)', en: 'English', es: 'Español' };

/* seletor de idioma: só os idiomas que o documento lista (e que existem em web/js/i18n); lembra em localStorage */
class PlatIdioma extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const idiomas = (c.idiomas && c.idiomas.length ? c.idiomas : ['pt-BR']);
    const rotulo = document.createElement('label'); rotulo.textContent = c.rotulo || 'Idioma';
    const sel = document.createElement('select');
    for (const id of idiomas) { const o = document.createElement('option'); o.value = id; o.textContent = NOMES[id] || id; sel.append(o); }
    sel.value = idiomas.includes(idiomaAtual()) ? idiomaAtual() : idiomas[0];
    sel.addEventListener('change', () => this.definir(sel.value));
    rotulo.append(sel); this.replaceChildren(rotulo);
  }

  async definir(id) {
    try { await carregar(id); } catch { this.erro(`idioma indisponível: ${id}`); return; }
    try { localStorage.setItem(CHAVE, id); } catch { /* sem armazenamento: só nesta página */ }
    document.documentElement.lang = id;
    this.emitir('idioma.mudou', { idioma: id });
  }

  acao_idioma_definir(detalhe) { this.definir(String(detalhe.idioma || 'pt-BR')); }
}

definir('plat-w-idioma', PlatIdioma);
