import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({ eventos: ['filtro_mudou', 'filtro.alterado'], acoes: ['filtro.definir', 'limpar_filtro', 'definir_parametro'] });

export const MODOS = Object.freeze(['texto', 'valores', 'intervalo', 'data']);

/* Filtro por campo (L5-06 caixa de texto; L5-01-c modos): `texto` emite `campo like '%texto%'`; `valores`
   carrega os valores únicos do campo pela vista (`vista.distintos` — em camada é `returnDistinctValues` no
   servidor) e emite `campo = valor` (ou `in` com vários); `intervalo` emite `between`/`>=`/`<=` numérico;
   `data` emite `>=`/`<=` com datas ISO. Sempre `filtro_mudou` {filtro} (null = sem filtro); a mensagem do
   documento leva o filtro à vista certa. */
class PlatFiltro extends PlatWidget {
  #campo = null;
  #pedido = 0;

  renderizar(mudanca = null) {
    if (mudanca && mudanca.causa !== 'registros_carregados' && mudanca.causa !== 'dado_adicionado') return;
    const modo = MODOS.includes(this.configuracao.modo) ? this.configuracao.modo : 'texto';
    const rotulo = document.createElement('label'); rotulo.textContent = this.configuracao.rotulo || 'Filtrar';
    this.dataset.modo = modo;
    if (modo === 'texto') this.#texto(rotulo);
    else if (modo === 'valores') this.#valores(rotulo);
    else if (modo === 'intervalo') this.#intervalo(rotulo, 'number');
    else this.#intervalo(rotulo, 'date');
  }

  #emitirFiltro(filtro, valor) {
    this.emitir('filtro.alterado', { valor });
    this.emitir('filtro_mudou', { valor, filtro });
  }

  #texto(rotulo) {
    const campo = document.createElement('input'); campo.type = 'search'; campo.value = this.configuracao.valor || '';
    campo.addEventListener('input', () => {
      const nome = this.configuracao.campo;
      const filtro = nome && campo.value ? { op: 'like', args: [{ property: nome }, `%${campo.value}%`] } : null;
      this.#emitirFiltro(filtro, campo.value);
    });
    rotulo.append(campo); this.replaceChildren(rotulo); this.#campo = campo;
  }

  async #valores(rotulo) {
    const sel = document.createElement('select'); sel.multiple = !!this.configuracao.multiplo;
    const todos = document.createElement('option'); todos.value = ''; todos.textContent = '(todos)'; sel.append(todos);
    rotulo.append(sel); this.replaceChildren(rotulo); this.#campo = sel;
    const pedido = ++this.#pedido;
    if (this.vista && this.configuracao.campo) {
      try {
        const valores = await this.vista.distintos(this.configuracao.campo, this.configuracao.maximo_valores || 200);
        if (pedido !== this.#pedido) return;
        for (const v of valores) { const o = document.createElement('option'); o.value = String(v); o.textContent = String(v); o.dataset.tipo = typeof v; sel.append(o); }
        this.dataset.valores = String(valores.length);
        if (this.configuracao.valor) sel.value = String(this.configuracao.valor);
      } catch (e) { this.dataset.erro = e.message; }
    }
    sel.addEventListener('change', () => {
      const nome = this.configuracao.campo;
      const escolhidos = [...sel.selectedOptions].filter((o) => o.value !== '').map((o) => (o.dataset.tipo === 'number' ? Number(o.value) : o.value));
      let filtro = null;
      if (nome && escolhidos.length === 1) filtro = { op: '=', args: [{ property: nome }, escolhidos[0]] };
      else if (nome && escolhidos.length > 1) filtro = { op: 'in', args: [{ property: nome }, escolhidos] };
      this.#emitirFiltro(filtro, escolhidos.length === 1 ? escolhidos[0] : escolhidos);
    });
  }

  #intervalo(rotulo, tipo) {
    const de = document.createElement('input'); de.type = tipo; de.className = 'filtro-de'; de.setAttribute('aria-label', 'de');
    const ate = document.createElement('input'); ate.type = tipo; ate.className = 'filtro-ate'; ate.setAttribute('aria-label', 'até');
    const emitir = () => {
      const nome = this.configuracao.campo;
      const a = de.value === '' ? null : (tipo === 'number' ? Number(de.value) : de.value);
      const b = ate.value === '' ? null : (tipo === 'number' ? Number(ate.value) : ate.value);
      let filtro = null;
      if (nome && a !== null && b !== null) filtro = { op: 'between', args: [{ property: nome }, a, b] };
      else if (nome && a !== null) filtro = { op: '>=', args: [{ property: nome }, a] };
      else if (nome && b !== null) filtro = { op: '<=', args: [{ property: nome }, b] };
      this.#emitirFiltro(filtro, { de: a, ate: b });
    };
    de.addEventListener('change', emitir); ate.addEventListener('change', emitir);
    rotulo.append(de, ate); this.replaceChildren(rotulo); this.#campo = de;
  }

  acao_filtro_definir(detalhe) { this.configuracao = { ...this.configuracao, valor: String(detalhe.valor || '') }; }
  acao_limpar_filtro() { if (this.#campo) { this.#campo.value = ''; } this.configuracao = { ...this.configuracao, valor: '' }; }
}

definir('plat-filtro', PlatFiltro);
