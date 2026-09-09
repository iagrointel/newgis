import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['botao.acionado'], acoes: ['botao.habilitar'] });

class PlatBotao extends PlatWidget {
  renderizar() {
    const botao = document.createElement('button');
    botao.type = 'button'; botao.textContent = this.configuracao.rotulo || 'Executar';
    botao.disabled = this.configuracao.habilitado === false;
    botao.addEventListener('click', () => this.emitir('botao.acionado', { valor: this.configuracao.valor }));
    this.replaceChildren(botao);
  }

  acao_botao_habilitar(detalhe) { this.configuracao = { ...this.configuracao, habilitado: detalhe.habilitado !== false }; }
}

definir('plat-botao', PlatBotao);
