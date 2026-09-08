import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: [], acoes: ['texto.definir'] });

class PlatTexto extends PlatWidget {
  renderizar() {
    const elemento = document.createElement(this.configuracao.nivel ? `h${this.configuracao.nivel}` : 'p');
    // ponytail: o campo `texto` é texto puro e entra só por textContent; HTML vindo do documento fica
    // inerte (sem DOMPurify na página). Texto rico (Markdown + DOMPurify, L5_CONCEITO D23) é campo à parte
    // de um item futuro, não este.
    elemento.textContent = this.configuracao.texto || '';
    this.replaceChildren(elemento);
  }

  acao_texto_definir(detalhe) { this.configuracao = { ...this.configuracao, texto: String(detalhe.texto || '') }; }
}

definir('plat-texto', PlatTexto);
