import { PlatWidget, definir } from './base.js';
import { urlSegura } from './seguro.js';

export const contrato = Object.freeze({ eventos: ['botao.acionado', 'botao.pagina'], acoes: ['botao.habilitar'] });

/* botão: `acao.tipo` = evento (barramento), link (URL segura) ou pagina (o executor troca de página) */
class PlatBotao extends PlatWidget {
  renderizar() {
    const c = this.configuracao;
    const acao = c.acao || { tipo: 'evento' };
    const rotulo = c.rotulo || 'Executar';
    if (acao.tipo === 'link') {
      const url = urlSegura(acao.url);
      if (!url) { this.erro('endereço do link recusado'); return; }
      const a = document.createElement('a');
      a.className = 'botao'; a.href = url; a.textContent = rotulo; a.rel = 'noopener noreferrer';
      if (acao.nova_aba) a.target = '_blank';
      if (c.habilitado === false) { a.setAttribute('aria-disabled', 'true'); a.removeAttribute('href'); }
      this.replaceChildren(a);
      return;
    }
    const botao = document.createElement('button');
    botao.type = 'button'; botao.textContent = rotulo;
    botao.disabled = c.habilitado === false;
    botao.addEventListener('click', () => {
      if (acao.tipo === 'pagina') this.emitir('botao.pagina', { pagina: String(acao.pagina || '') });
      else this.emitir('botao.acionado', { valor: c.valor });
    });
    this.replaceChildren(botao);
  }

  acao_botao_habilitar(detalhe) { this.configuracao = { ...this.configuracao, habilitado: detalhe.habilitado !== false }; }
}

definir('plat-w-botao', PlatBotao);
