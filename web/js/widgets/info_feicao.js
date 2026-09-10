import { PlatWidget, definir } from './base.js';
import { preencherModelo } from '../app/agregacao.js';
import { avaliarTexto } from '../expressao/avaliador.js';

export const contrato = Object.freeze({ eventos: ['info.mostrada'], acoes: ['piscar', 'info.mostrar', 'abrir', 'fechar'] });

/* Informação da feição (L5-01-c): mostra a feição SELECIONADA da vista (a primeira, com "n de m" quando há
   várias) — modelo de texto (`{campo}`, `{= expressão }`) quando configurado, senão a lista de campos. O popup
   configurável por construtor é o item L5-26; aqui é a leitura dos atributos dentro do app. */
class PlatInfoFeicao extends PlatWidget {
  #indice = 0;

  renderizar(mudanca = null) {
    if (mudanca && mudanca.causa === 'selecao_mudou') this.#indice = 0;
    const sel = this.vista ? this.vista.selecionados() : [];
    const raiz = document.createElement('div'); raiz.className = 'info-feicao';
    if (!sel.length) {
      const p = document.createElement('p'); p.className = 'info-vazia'; p.textContent = this.configuracao.vazio || 'nenhuma feição selecionada';
      raiz.append(p); delete this.dataset.id; this.replaceChildren(raiz); return;
    }
    const f = sel[Math.min(this.#indice, sel.length - 1)];
    this.dataset.id = String(f.id);
    if (sel.length > 1) {
      const nav = document.createElement('div'); nav.className = 'info-nav';
      const ant = document.createElement('button'); ant.type = 'button'; ant.textContent = 'Anterior'; ant.disabled = this.#indice === 0; ant.addEventListener('click', () => { this.#indice -= 1; this.renderizar(); });
      const prox = document.createElement('button'); prox.type = 'button'; prox.textContent = 'Próxima'; prox.disabled = this.#indice >= sel.length - 1; prox.addEventListener('click', () => { this.#indice += 1; this.renderizar(); });
      const pos = document.createElement('span'); pos.textContent = `${this.#indice + 1} de ${sel.length}`;
      nav.append(ant, pos, prox); raiz.append(nav);
    }
    if (this.configuracao.modelo) {
      const p = document.createElement('p'); p.className = 'info-modelo';
      p.textContent = preencherModelo(this.configuracao.modelo, f.propriedades, (expr, props) => avaliarTexto(expr, props));
      raiz.append(p);
    } else {
      const dl = document.createElement('dl');
      const campos = (this.configuracao.campos && this.configuracao.campos.length) ? this.configuracao.campos : Object.keys(f.propriedades || {}).filter((k) => k !== '__id');
      for (const k of campos) {
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = String(f.propriedades?.[k] ?? ''); dd.dataset.campo = k;
        dl.append(dt, dd);
      }
      raiz.append(dl);
    }
    this.replaceChildren(raiz);
    this.emitir('info.mostrada', { id: f.id });
  }

  acao_info_mostrar(detalhe) {
    const regs = detalhe?.registros || [];
    if (regs.length && this.vista) this.vista.definirSelecao(regs.map((r) => r.id), this.noId);
  }
}

definir('plat-info-feicao', PlatInfoFeicao);
