import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['filtro.alterado'], acoes: ['filtro.definir'] });

class PlatFiltro extends PlatWidget {
  renderizar() {
    const rotulo = document.createElement('label'); rotulo.textContent = this.configuracao.rotulo || 'Filtrar';
    const campo = document.createElement('input'); campo.type = 'search'; campo.value = this.configuracao.valor || '';
    campo.addEventListener('input', () => this.emitir('filtro.alterado', { valor: campo.value }));
    rotulo.append(campo); this.replaceChildren(rotulo);
  }

  acao_filtro_definir(detalhe) { this.configuracao = { ...this.configuracao, valor: String(detalhe.valor || '') }; }
}

definir('plat-w-filtro', PlatFiltro);
