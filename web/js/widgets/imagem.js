import { PlatWidget, definir } from './base.js';
import { urlSegura } from './seguro.js';

export const contrato = Object.freeze({ eventos: ['imagem.acionada'], acoes: ['imagem.definir', 'imagem.feicao'] });

class PlatImagem extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const props = (this.feicao && (this.feicao.properties || this.feicao.atributos || this.feicao)) || {};
    const origem = c.campo && props[c.campo] !== undefined ? props[c.campo] : c.url;
    const url = urlSegura(origem, { imagem: true });
    if (!url) { this.erro(origem ? 'endereço de imagem recusado' : 'sem imagem (url ou campo)'); return; }
    const img = document.createElement('img');
    img.src = url; img.alt = c.alternativo || ''; img.loading = 'lazy';
    if (c.ajuste) img.style.objectFit = c.ajuste;
    if (c.altura) img.style.height = `${c.altura}px`;
    img.addEventListener('click', () => this.emitir('imagem.acionada', { url }));
    const figura = document.createElement('figure');
    figura.append(img);
    if (c.legenda) { const l = document.createElement('figcaption'); l.textContent = c.legenda; figura.append(l); }
    this.replaceChildren(figura);
  }

  acao_imagem_definir(detalhe) { this.configuracao = { ...this.configuracao, url: String(detalhe.url || '') }; }
  acao_imagem_feicao(detalhe) { this.definirFeicao(detalhe); }
}

definir('plat-w-imagem', PlatImagem);
