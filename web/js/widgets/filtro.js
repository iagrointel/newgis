import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['filtro_mudou', 'filtro.alterado'], acoes: ['filtro.definir', 'limpar_filtro', 'definir_parametro'] });

/* Caixa de filtro (L5-06) que, ligada a uma vista e a um campo (L5-07), emite `filtro_mudou` com CQL2
   `campo like '%texto%'` (texto vazio = filtro nulo); a mensagem do documento leva o filtro à vista certa. */
class PlatFiltro extends PlatWidget {
  #campo = null;

  renderizar() {
    const rotulo = document.createElement('label'); rotulo.textContent = this.configuracao.rotulo || 'Filtrar';
    const campo = document.createElement('input'); campo.type = 'search'; campo.value = this.configuracao.valor || '';
    campo.addEventListener('input', () => {
      this.emitir('filtro.alterado', { valor: campo.value });
      const nome = this.configuracao.campo;
      const filtro = nome && campo.value ? { op: 'like', args: [{ property: nome }, `%${campo.value}%`] } : null;
      this.emitir('filtro_mudou', { valor: campo.value, filtro });
    });
    rotulo.append(campo); this.replaceChildren(rotulo); this.#campo = campo;
  }

  acao_filtro_definir(detalhe) { this.configuracao = { ...this.configuracao, valor: String(detalhe.valor || '') }; }
  acao_limpar_filtro() { if (this.#campo) { this.#campo.value = ''; } this.configuracao = { ...this.configuracao, valor: '' }; }
}

definir('plat-filtro', PlatFiltro);
