import { PlatWidget, definir } from './base.js';
import { analisarTexto } from '../app/cql2.js';

export const contrato = Object.freeze({ eventos: ['selecao_mudou', 'selecao.alterada'], acoes: ['selecionar', 'limpar_selecao', 'selecao.por_atributo', 'selecao.tudo', 'selecao.inverter'] });

/* Seleção (L5-01-c): por atributo (CQL2-text ou `campo = valor` -> `vista.idsDoFiltro`, no servidor é
   `returnIdsOnly` com o filtro da vista), tudo o que o filtro atual devolve, inverter (sobre o que está
   carregado) e limpar; a seleção interativa (clique no mapa/tabela/lista) já é dos outros widgets. Mostra a
   contagem selecionada. */
class PlatSelecao extends PlatWidget {
  renderizar(mudanca = null) {
    if (mudanca) { this.#contar(); return; }
    const form = document.createElement('form'); form.className = 'selecao-form';
    const texto = document.createElement('input'); texto.className = 'selecao-cql2'; texto.setAttribute('aria-label', 'atributo (CQL2)'); texto.title = this.configuracao.campo ? `${this.configuracao.campo} = valor` : 'CQL2';
    const porAtributo = document.createElement('button'); porAtributo.type = 'submit'; porAtributo.className = 'selecao-atributo'; porAtributo.textContent = 'Selecionar por atributo';
    const tudo = document.createElement('button'); tudo.type = 'button'; tudo.className = 'selecao-tudo'; tudo.textContent = 'Tudo';
    const inverter = document.createElement('button'); inverter.type = 'button'; inverter.className = 'selecao-inverter'; inverter.textContent = 'Inverter';
    const limpar = document.createElement('button'); limpar.type = 'button'; limpar.className = 'selecao-limpar'; limpar.textContent = 'Limpar';
    const out = document.createElement('output'); out.className = 'selecao-total';
    form.append(texto, porAtributo, tudo, inverter, limpar, out);
    form.addEventListener('submit', (e) => { e.preventDefault(); this.acao_selecao_por_atributo({ cql2: texto.value }); });
    tudo.addEventListener('click', () => this.acao_selecao_tudo());
    inverter.addEventListener('click', () => this.acao_selecao_inverter());
    limpar.addEventListener('click', () => this.acao_limpar_selecao());
    this.replaceChildren(form);
    this.#contar();
  }

  #contar() {
    const n = this.vista ? this.vista.selecao.size : 0;
    const out = this.querySelector('.selecao-total'); if (out) out.textContent = `${n} selecionado(s)`;
    this.dataset.selecionados = String(n);
  }

  async acao_selecao_por_atributo(detalhe) {
    if (!this.vista) return;
    try {
      let filtro;
      if (detalhe.filtro) filtro = detalhe.filtro;
      else {
        const t = String(detalhe.cql2 || '').trim();
        filtro = t.includes(' ') || /[<>=]/.test(t) ? analisarTexto(t) : { op: '=', args: [{ property: this.configuracao.campo }, valorSimples(t)] };
      }
      const ids = await this.vista.idsDoFiltro(filtro);
      delete this.dataset.erro;
      this.vista.definirSelecao(ids, this.noId);
      this.emitir('selecao.alterada', { modo: 'atributo', n: ids.length });
    } catch (e) { this.dataset.erro = e.codigo || e.message; }
  }

  async acao_selecao_tudo() {
    if (!this.vista) return;
    const ids = await this.vista.idsDoFiltro(null);
    this.vista.definirSelecao(ids, this.noId);
    this.emitir('selecao.alterada', { modo: 'tudo', n: ids.length });
  }

  acao_selecao_inverter() {
    if (!this.vista) return;
    const atual = this.vista.selecao;
    const ids = this.vista.registros().map((f) => f.id).filter((id) => !atual.has(id));
    this.vista.definirSelecao(ids, this.noId);
    this.emitir('selecao.alterada', { modo: 'inverter', n: ids.length });
  }

  acao_limpar_selecao() { if (this.vista) this.vista.limparSelecao(this.noId); this.emitir('selecao.alterada', { modo: 'limpar', n: 0 }); }
}

function valorSimples(t) { const n = Number(t); return t !== '' && !Number.isNaN(n) ? n : t; }

definir('plat-selecao', PlatSelecao);
