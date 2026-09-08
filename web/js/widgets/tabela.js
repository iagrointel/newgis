import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['tabela.linha_selecionada'], acoes: ['tabela.definir', 'tabela.filtrar'] });

class PlatTabela extends PlatWidget {
  #filtro = '';

  renderizar() {
    const colunas = this.configuracao.colunas || [];
    const linhas = (this.configuracao.linhas || []).filter((linha) => !this.#filtro
      || Object.values(linha).some((valor) => String(valor ?? '').toLocaleLowerCase('pt-BR').includes(this.#filtro)));
    const tabela = document.createElement('table');
    const cabecalho = document.createElement('tr');
    for (const coluna of colunas) {
      const th = document.createElement('th'); th.textContent = coluna.rotulo; cabecalho.append(th);
    }
    const thead = document.createElement('thead'); thead.append(cabecalho); tabela.append(thead);
    const tbody = document.createElement('tbody');
    for (const linha of linhas) {
      const tr = document.createElement('tr'); tr.tabIndex = 0;
      for (const coluna of colunas) { const td = document.createElement('td'); td.textContent = linha[coluna.campo] ?? ''; tr.append(td); }
      tr.addEventListener('click', () => this.emitir('tabela.linha_selecionada', { linha }));
      tbody.append(tr);
    }
    tabela.append(tbody); this.replaceChildren(tabela);
  }

  acao_tabela_definir(detalhe) { this.configuracao = { ...this.configuracao, linhas: detalhe.linhas || [] }; }
  acao_tabela_filtrar(detalhe) { this.#filtro = String(detalhe.valor || '').toLocaleLowerCase('pt-BR'); this.renderizar(); }
}

definir('plat-tabela', PlatTabela);
