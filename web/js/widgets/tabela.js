import { PlatWidget, definir } from './base.js';
import { baixarTexto } from './util_dado.js';

export const contrato = Object.freeze({
  eventos: ['clique', 'selecao_mudou', 'registros_carregados', 'tabela.linha_selecionada', 'tabela.exportada'],
  acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'piscar', 'tabela.definir', 'tabela.filtrar', 'tabela.ordenar', 'tabela.pagina'],
});

/* Tabela ligada a uma VISTA (L5-07) com paginação, ordenação e exportação no SERVIDOR (L5-01-c): cada página é
   `vista.pagina({deslocamento, limite, ordenacao})` — em fonte de camada isso é uma consulta ao FeatureServer
   (resultOffset/resultRecordCount/orderByFields com o filtro da vista em `where`), em fonte de memória é um
   recorte local; nunca a camada inteira no navegador. Clique no cabeçalho ordena (asc -> desc -> sem), clique na
   linha muda a seleção da vista (o barramento leva aos outros widgets), `aria-selected` marca as selecionadas;
   "Exportar CSV/GeoJSON" pede à vista todas as feições DO FILTRO ATIVO (páginas de 5 mil no servidor). Sem
   vista, continua como no L5-06 (linhas na configuração). HTML próprio, sem biblioteca (L5_CONCEITO D22). */
class PlatTabela extends PlatWidget {
  #filtro = '';
  #pagina = 0;
  #ordenacao = null;
  #ultima = { registros: [], total: 0 };
  #pedido = 0;

  #colunas() {
    const cfg = this.configuracao.colunas || [];
    if (cfg.length) return cfg;
    if (this.vista) return this.vista.fonte.camposDeclarados.map((c) => ({ campo: c.nome, rotulo: c.nome }));
    const primeira = (this.configuracao.linhas || [])[0] || {};
    return Object.keys(primeira).filter((k) => k !== '__id').map((k) => ({ campo: k, rotulo: k }));
  }

  #limite() { return this.configuracao.linhas_por_pagina || 50; }

  #ordenacaoAtual() { return this.#ordenacao || (this.vista ? this.vista.ordenacao : []) || []; }

  renderizar(mudanca = null) {
    if (!this.querySelector('table')) this.#esqueleto();
    if (mudanca && mudanca.causa === 'selecao_mudou') { this.#marcarSelecao(); return; }
    if (mudanca && (mudanca.causa === 'filtro_mudou' || mudanca.causa === 'dado_adicionado' || mudanca.causa === 'registros_carregados')) this.#pagina = 0;
    this.#carregar();
  }

  #esqueleto() {
    const barra = document.createElement('div'); barra.className = 'tabela-barra';
    const caption = document.createElement('span'); caption.className = 'tabela-resumo';
    const ant = botao('Anterior', 'tabela-anterior', () => { if (this.#pagina > 0) { this.#pagina -= 1; this.#carregar(); } });
    const prox = botao('Próxima', 'tabela-proxima', () => { this.#pagina += 1; this.#carregar(); });
    barra.append(caption, ant, prox);
    if (this.configuracao.exportar !== false) {
      barra.append(botao('Exportar CSV', 'tabela-exportar-csv', () => this.#exportar('csv')),
        botao('Exportar GeoJSON', 'tabela-exportar-geojson', () => this.#exportar('geojson')));
    }
    const tabela = document.createElement('table');
    tabela.append(document.createElement('thead'), document.createElement('tbody'));
    const erro = document.createElement('p'); erro.className = 'tabela-erro'; erro.hidden = true;
    this.replaceChildren(barra, tabela, erro);
  }

  async #carregar() {
    const pedido = ++this.#pedido;
    const limite = this.#limite();
    this.dataset.carregando = '1';
    try {
      let resultado;
      if (this.vista) resultado = await this.vista.pagina({ deslocamento: this.#pagina * limite, limite, ordenacao: this.#ordenacao });
      else {
        const linhas = (this.configuracao.linhas || []).map((l, i) => ({ id: l.__id ?? i, propriedades: { ...l, __id: l.__id ?? i } }));
        resultado = { registros: linhas.slice(this.#pagina * limite, (this.#pagina + 1) * limite), total: linhas.length };
      }
      if (pedido !== this.#pedido) return;  // resposta velha
      this.#ultima = resultado;
      this.#desenhar();
      this.querySelector('.tabela-erro').hidden = true;
    } catch (e) {
      if (pedido !== this.#pedido) return;
      const p = this.querySelector('.tabela-erro'); p.textContent = `tabela: ${e.message}`; p.hidden = false;
    } finally { if (pedido === this.#pedido) delete this.dataset.carregando; }
  }

  #desenhar() {
    const colunas = this.#colunas();
    const limite = this.#limite();
    const selecao = this.vista ? this.vista.selecao : new Set();
    const ord = this.#ordenacaoAtual();
    const filtroLocal = this.#filtro;
    const linhas = this.#ultima.registros.map((f) => ({ __id: f.id, ...f.propriedades })).filter((linha) => !filtroLocal
      || Object.values(linha).some((valor) => String(valor ?? '').toLocaleLowerCase('pt-BR').includes(filtroLocal)));
    const total = this.#ultima.total;
    const paginas = Math.max(1, Math.ceil(total / limite));
    const thead = this.querySelector('thead');
    const cabecalho = document.createElement('tr');
    for (const coluna of colunas) {
      const th = document.createElement('th'); th.textContent = coluna.rotulo || coluna.campo; th.dataset.campo = coluna.campo;
      const o = ord.find((x) => x.campo === coluna.campo);
      th.setAttribute('aria-sort', o ? (o.direcao === 'desc' ? 'descending' : 'ascending') : 'none');
      th.tabIndex = 0; th.setAttribute('role', 'columnheader');
      th.addEventListener('click', () => this.#ordenarPor(coluna.campo));
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#ordenarPor(coluna.campo); } });
      cabecalho.append(th);
    }
    thead.replaceChildren(cabecalho);
    const tbody = this.querySelector('tbody');
    const frag = document.createDocumentFragment();
    for (const linha of linhas) {
      const tr = document.createElement('tr'); tr.tabIndex = 0;
      tr.dataset.id = String(linha.__id);
      if (selecao.has(linha.__id)) tr.setAttribute('aria-selected', 'true');
      for (const coluna of colunas) { const td = document.createElement('td'); td.textContent = formatar(linha[coluna.campo]); tr.append(td); }
      tr.addEventListener('click', () => this.#clique(linha));
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#clique(linha); } });
      frag.append(tr);
    }
    tbody.replaceChildren(frag);
    this.querySelector('.tabela-resumo').textContent = `${total} registro(s) · página ${this.#pagina + 1} de ${paginas}`;
    this.querySelector('.tabela-anterior').disabled = this.#pagina === 0;
    this.querySelector('.tabela-proxima').disabled = this.#pagina + 1 >= paginas;
    this.dataset.total = String(total);
    this.dataset.pagina = String(this.#pagina + 1);
    this.dataset.paginas = String(paginas);
    this.dataset.ordenacao = ord.map((o) => `${o.campo}:${o.direcao || 'asc'}`).join(',');
    this.dataset.linhas = String(linhas.length);
  }

  #marcarSelecao() {
    const selecao = this.vista ? this.vista.selecao : new Set();
    for (const tr of this.querySelectorAll('tbody tr')) {
      const id = tr.dataset.id;
      const sel = selecao.has(id) || selecao.has(Number(id));
      if (sel) tr.setAttribute('aria-selected', 'true'); else tr.removeAttribute('aria-selected');
    }
  }

  #ordenarPor(campo) {
    const atual = this.#ordenacaoAtual().find((o) => o.campo === campo);
    if (!atual) this.#ordenacao = [{ campo, direcao: 'asc' }];
    else if (atual.direcao !== 'desc') this.#ordenacao = [{ campo, direcao: 'desc' }];
    else this.#ordenacao = [];
    this.#pagina = 0;
    this.#carregar();
  }

  #clique(linha) {
    this.emitir('tabela.linha_selecionada', { linha });
    if (linha.__id === undefined) return;
    this.emitir('clique', { id: linha.__id, ids: [linha.__id] });
    if (this.vista) this.vista.definirSelecao([linha.__id], this.noId);
  }

  async #exportar(formato) {
    if (!this.vista) return;
    try {
      const colunas = this.#colunas();
      const saida = await this.vista.exportar(formato, colunas);
      const nome = `${(this.vista.nome || 'dados').replace(/[^\w.-]+/g, '_')}.${formato}`;
      const texto = formato === 'geojson' ? JSON.stringify(saida) : saida;
      baixarTexto(nome, texto, formato === 'geojson' ? 'application/geo+json' : 'text/csv;charset=utf-8');
      this.dataset.exportado = nome;
      this.emitir('tabela.exportada', { formato, nome, bytes: texto.length });
    } catch (e) {
      const p = this.querySelector('.tabela-erro'); p.textContent = `exportação: ${e.message}`; p.hidden = false;
    }
  }

  acao_tabela_definir(detalhe) { this.configuracao = { ...this.configuracao, linhas: detalhe.linhas || [] }; }
  acao_tabela_filtrar(detalhe) { this.#filtro = String(detalhe.valor || '').toLocaleLowerCase('pt-BR'); this.#desenhar(); }
  acao_tabela_ordenar(detalhe) { this.#ordenacao = detalhe.campo ? [{ campo: detalhe.campo, direcao: detalhe.direcao === 'desc' ? 'desc' : 'asc' }] : []; this.#pagina = 0; this.#carregar(); }
  acao_tabela_pagina(detalhe) { this.#pagina = Math.max(0, Number(detalhe.pagina || 1) - 1); this.#carregar(); }
}

function botao(rotulo, classe, aoClicar) {
  const b = document.createElement('button'); b.type = 'button'; b.className = classe; b.textContent = rotulo;
  b.addEventListener('click', aoClicar); return b;
}

function formatar(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toLocaleString('pt-BR', { maximumFractionDigits: 4 });
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

definir('plat-tabela', PlatTabela);
