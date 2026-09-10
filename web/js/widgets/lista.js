import { PlatWidget, definir } from './base.js';
import { preencherModelo } from '../app/agregacao.js';
import { avaliarTexto } from '../expressao/avaliador.js';

export const contrato = Object.freeze({ eventos: ['clique', 'selecao_mudou', 'lista.item_selecionado'], acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'piscar', 'lista.pagina'] });

/* Lista/cartões (L5-01-c): cada registro da vista vira um cartão com um MODELO de texto — `{campo}` é o valor,
   `{= expressão }` é a linguagem de expressão do L2-10-c avaliada sobre os campos do registro (lista branca:
   só os campos; 50 ms de orçamento). Paginada pela vista como a tabela; clique seleciona. */
class PlatLista extends PlatWidget {
  #pagina = 0;
  #pedido = 0;

  renderizar(mudanca = null) {
    if (mudanca && mudanca.causa === 'selecao_mudou') { this.#marcar(); return; }
    if (mudanca && mudanca.causa !== 'vista_mudou') this.#pagina = 0;
    this.#carregar();
  }

  async #carregar() {
    const pedido = ++this.#pedido;
    const limite = this.configuracao.linhas_por_pagina || 20;
    try {
      const r = this.vista ? await this.vista.pagina({ deslocamento: this.#pagina * limite, limite }) : { registros: [], total: 0 };
      if (pedido !== this.#pedido) return;
      const ul = document.createElement('ul'); ul.className = 'lista-cartoes';
      const selecao = this.vista ? this.vista.selecao : new Set();
      const modelo = this.configuracao.modelo || '{__id}';
      for (const f of r.registros) {
        const li = document.createElement('li'); li.dataset.id = String(f.id); li.tabIndex = 0; li.setAttribute('role', 'option');
        if (selecao.has(f.id)) li.setAttribute('aria-selected', 'true');
        li.textContent = preencherModelo(modelo, f.propriedades, (expr, props) => avaliarTexto(expr, props));
        li.addEventListener('click', () => this.#clique(f));
        li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#clique(f); } });
        ul.append(li);
      }
      const paginas = Math.max(1, Math.ceil(r.total / limite));
      const barra = document.createElement('div'); barra.className = 'lista-barra';
      const resumo = document.createElement('span'); resumo.textContent = `${r.total} registro(s) · página ${this.#pagina + 1} de ${paginas}`;
      const ant = document.createElement('button'); ant.type = 'button'; ant.className = 'lista-anterior'; ant.textContent = 'Anterior'; ant.disabled = this.#pagina === 0;
      ant.addEventListener('click', () => { this.#pagina -= 1; this.#carregar(); });
      const prox = document.createElement('button'); prox.type = 'button'; prox.className = 'lista-proxima'; prox.textContent = 'Próxima'; prox.disabled = this.#pagina + 1 >= paginas;
      prox.addEventListener('click', () => { this.#pagina += 1; this.#carregar(); });
      barra.append(resumo, ant, prox);
      this.dataset.total = String(r.total); this.dataset.pagina = String(this.#pagina + 1);
      this.replaceChildren(barra, ul);
    } catch (e) {
      if (pedido !== this.#pedido) return;
      const p = document.createElement('p'); p.className = 'lista-erro'; p.textContent = `lista: ${e.message}`; this.replaceChildren(p);
    }
  }

  #marcar() {
    const selecao = this.vista ? this.vista.selecao : new Set();
    for (const li of this.querySelectorAll('li[data-id]')) {
      const id = li.dataset.id;
      if (selecao.has(id) || selecao.has(Number(id))) li.setAttribute('aria-selected', 'true'); else li.removeAttribute('aria-selected');
    }
  }

  #clique(f) {
    this.emitir('lista.item_selecionado', { id: f.id });
    this.emitir('clique', { id: f.id, ids: [f.id] });
    if (this.vista) this.vista.definirSelecao([f.id], this.noId);
  }

  acao_lista_pagina(detalhe) { this.#pagina = Math.max(0, Number(detalhe.pagina || 1) - 1); this.#carregar(); }
}

definir('plat-lista', PlatLista);
