import { PlatWidget, definir } from './base.js';
import { urlSegura } from './seguro.js';

export const contrato = Object.freeze({ eventos: ['menu.pagina', 'menu.acionado'], acoes: ['menu.definir'] });

/* menu: itens com página (o executor troca de página) ou link (URL segura); horizontal ou vertical */
class PlatMenu extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const nav = document.createElement('nav');
    nav.className = `plat-w-menu plat-menu-${c.orientacao || 'horizontal'}`;
    nav.setAttribute('aria-label', c.rotulo || 'menu');
    const ul = document.createElement('ul');
    for (const item of c.itens || []) {
      const li = document.createElement('li');
      if (item.url) {
        const url = urlSegura(item.url);
        const a = document.createElement('a'); a.textContent = item.rotulo || item.url; a.rel = 'noopener noreferrer';
        if (url) a.href = url; else { a.setAttribute('aria-disabled', 'true'); a.title = 'endereço recusado'; }
        li.append(a);
      } else {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = item.rotulo || item.pagina || '';
        b.dataset.pagina = item.pagina || '';
        b.addEventListener('click', () => this.emitir(item.pagina ? 'menu.pagina' : 'menu.acionado', { pagina: item.pagina, valor: item.valor }));
        li.append(b);
      }
      ul.append(li);
    }
    nav.append(ul); this.replaceChildren(nav);
  }

  acao_menu_definir(detalhe) { this.configuracao = { ...this.configuracao, itens: detalhe.itens || [] }; }
}

definir('plat-w-menu', PlatMenu);
