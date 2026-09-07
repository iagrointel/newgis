import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: [], acoes: ['texto.definir'] });

class PlatTexto extends PlatWidget {
  renderizar() {
    const elemento = document.createElement(this.configuracao.nivel ? `h${this.configuracao.nivel}` : 'p');
    elemento.textContent = this.configuracao.texto || '';
    this.replaceChildren(elemento);
  }

  acao_texto_definir(detalhe) { this.configuracao = { ...this.configuracao, texto: String(detalhe.texto || '') }; }
}

definir('plat-texto', PlatTexto);
