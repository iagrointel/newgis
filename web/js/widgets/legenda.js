import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['legenda.item_acionado'], acoes: ['legenda.definir'] });

class PlatLegenda extends PlatWidget {
  renderizar() {
    const titulo = document.createElement('strong');
    titulo.textContent = this.configuracao.titulo || 'Legenda';
    const lista = document.createElement('ul');
    for (const item of this.configuracao.itens || []) {
      const botao = document.createElement('button');
      botao.type = 'button';
      botao.textContent = item.rotulo;
      botao.style.setProperty('--cor', item.cor || 'transparent');
      botao.addEventListener('click', () => this.emitir('legenda.item_acionado', { valor: item.valor }));
      const linha = document.createElement('li');
      linha.append(botao);
      lista.append(linha);
    }
    this.replaceChildren(titulo, lista);
  }

  acao_legenda_definir(detalhe) { this.configuracao = { ...this.configuracao, itens: detalhe.itens || [] }; }
}

definir('plat-legenda', PlatLegenda);
