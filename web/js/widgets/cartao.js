import { PlatWidget, definir } from './base.js';
import { markdownParaHtml, substituirCampos, urlSegura } from './seguro.js';

export const contrato = Object.freeze({ eventos: ['cartao.acionado', 'cartao.pagina'], acoes: ['cartao.feicao'] });

class PlatCartao extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const raiz = document.createElement('article'); raiz.className = 'plat-cartao';
    const img = c.imagem ? urlSegura(c.imagem, { imagem: true }) : null;
    if (c.imagem && !img) { this.erro('endereço de imagem recusado'); return; }
    if (img) { const i = document.createElement('img'); i.src = img; i.alt = c.imagem_alternativo || ''; raiz.append(i); }
    const titulo = document.createElement('h3');
    titulo.append(this.fragmentoSeguro(substituirCampos(c.titulo || '', this.feicao)));
    const corpo = document.createElement('div'); corpo.className = 'plat-texto-rico';
    corpo.append(this.fragmentoSeguro(markdownParaHtml(substituirCampos(c.texto || '', this.feicao))));
    raiz.append(titulo, corpo);
    if (c.link) {
      const url = urlSegura(c.link);
      if (!url) { this.erro('endereço do link recusado'); return; }
      const a = document.createElement('a'); a.href = url; a.rel = 'noopener noreferrer'; a.textContent = c.link_rotulo || 'Abrir';
      raiz.append(a);
    } else if (c.pagina) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = c.link_rotulo || 'Abrir';
      b.addEventListener('click', () => this.emitir('cartao.pagina', { pagina: c.pagina }));
      raiz.append(b);
    }
    this.replaceChildren(raiz);
  }

  acao_cartao_feicao(detalhe) { this.definirFeicao(detalhe); }
}

definir('plat-cartao', PlatCartao);
