import { PlatWidget, definir } from './base.js';
import { markdownParaHtml, substituirCampos } from './seguro.js';

export const contrato = Object.freeze({ eventos: [], acoes: ['texto.definir', 'texto.feicao'] });

function desescapar(s) {
  return s.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

class PlatTexto extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const bruto = substituirCampos(c.texto || '', this.feicao);
    if (c.formato === 'markdown') {
      // Markdown → HTML mínimo → DOMPurify (D23): script, on*, javascript: e afins nunca chegam ao DOM
      const raiz = document.createElement('div'); raiz.className = 'plat-texto-rico';
      raiz.append(this.fragmentoSeguro(markdownParaHtml(bruto)));
      this.replaceChildren(raiz);
      return;
    }
    // texto puro entra só por textContent (HTML fica inerte); {campo} veio escapado, aqui volta a texto
    const elemento = document.createElement(Number.isInteger(c.nivel) ? `h${c.nivel}` : 'p');
    elemento.textContent = desescapar(bruto);
    this.replaceChildren(elemento);
  }

  acao_texto_definir(detalhe) { this.configuracao = { ...this.configuracao, texto: String(detalhe.texto || '') }; }
  acao_texto_feicao(detalhe) { this.definirFeicao(detalhe); }
}

definir('plat-texto', PlatTexto);
