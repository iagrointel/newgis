import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({
  eventos: ['mapa.selecao', 'mapa.extensao_alterada'],
  acoes: ['mapa.enquadrar', 'mapa.destacar'],
});

class PlatMapa extends PlatWidget {
  renderizar() {
    this.setAttribute('role', 'application');
    this.setAttribute('aria-label', this.configuracao.rotulo || 'mapa');
  }

  acao_mapa_enquadrar(detalhe) {
    this.dispatchEvent(new CustomEvent('plat-mapa-enquadrar', { detail: detalhe }));
  }

  acao_mapa_destacar(detalhe) {
    this.dispatchEvent(new CustomEvent('plat-mapa-destacar', { detail: detalhe }));
  }
}

definir('plat-mapa', PlatMapa);
