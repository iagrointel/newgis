import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: [], acoes: [] });

class PlatDivisor extends PlatWidget {
  renderizar() {
    const hr = document.createElement('hr');
    hr.className = `plat-divisor plat-divisor-${this.configuracao.estilo || 'linha'}`;
    if (this.configuracao.vertical) this.dataset.vertical = '1'; else delete this.dataset.vertical;
    this.replaceChildren(hr);
  }
}

definir('plat-divisor', PlatDivisor);
