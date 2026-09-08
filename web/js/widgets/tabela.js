import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({
  eventos: ['clique', 'selecao_mudou', 'registros_carregados', 'tabela.linha_selecionada'],
  acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'piscar', 'tabela.definir', 'tabela.filtrar'],
});

/* Tabela ligada a uma VISTA (L5-07): as linhas são `vista.registros()` (filtro CQL2 já aplicado), a seleção da
   vista destaca linhas (`aria-selected`), e o clique numa linha muda a seleção da vista — o barramento de
   mensagens leva isso aos outros widgets. Sem vista, continua como no L5-06 (linhas na configuração). */
class PlatTabela extends PlatWidget {
  #filtro = '';

  #linhas() {
    if (this.vista) return this.vista.registros().map((f) => ({ __id: f.id, ...f.propriedades }));
    return this.configuracao.linhas || [];
  }

  renderizar() {
    const colunas = this.configuracao.colunas || [];
    const limite = this.configuracao.linhas_por_pagina || 200;
    const selecao = this.vista ? this.vista.selecao : new Set();
    const linhas = this.#linhas().filter((linha) => !this.#filtro
      || Object.values(linha).some((valor) => String(valor ?? '').toLocaleLowerCase('pt-BR').includes(this.#filtro)));
    const tabela = document.createElement('table');
    const cabecalho = document.createElement('tr');
    for (const coluna of colunas) {
      const th = document.createElement('th'); th.textContent = coluna.rotulo; cabecalho.append(th);
    }
    const thead = document.createElement('thead'); thead.append(cabecalho); tabela.append(thead);
    const tbody = document.createElement('tbody');
    for (const linha of linhas.slice(0, limite)) {
      const tr = document.createElement('tr'); tr.tabIndex = 0;
      if (linha.__id !== undefined) tr.dataset.id = String(linha.__id);
      if (linha.__id !== undefined && selecao.has(linha.__id)) tr.setAttribute('aria-selected', 'true');
      for (const coluna of colunas) { const td = document.createElement('td'); td.textContent = linha[coluna.campo] ?? ''; tr.append(td); }
      tr.addEventListener('click', () => this.#clique(linha));
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#clique(linha); } });
      tbody.append(tr);
    }
    tabela.append(tbody);
    const rodape = document.createElement('caption');
    rodape.textContent = `${linhas.length} registro(s)` + (linhas.length > limite ? `, mostrando ${limite}` : '');
    tabela.prepend(rodape);
    this.dataset.total = String(linhas.length);
    const acoes = this.montarAcoesUsuario();
    this.replaceChildren(tabela, ...(acoes ? [acoes] : []));
  }

  #clique(linha) {
    this.emitir('tabela.linha_selecionada', { linha });
    if (linha.__id === undefined) return;
    this.emitir('clique', { id: linha.__id, ids: [linha.__id] });
    if (this.vista) this.vista.definirSelecao([linha.__id], this.noId);
  }

  acao_tabela_definir(detalhe) { this.configuracao = { ...this.configuracao, linhas: detalhe.linhas || [] }; }
  acao_tabela_filtrar(detalhe) { this.#filtro = String(detalhe.valor || '').toLocaleLowerCase('pt-BR'); this.renderizar(); }
}

definir('plat-tabela', PlatTabela);
