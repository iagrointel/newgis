import { PlatWidget, definir } from './base.js';
import { analisarTexto } from '../app/cql2.js';

export const contrato = Object.freeze({ eventos: ['filtro_mudou', 'consulta.executada'], acoes: ['limpar_filtro', 'consulta.executar', 'definir_parametro'] });

const OPERADORES = ['=', '<>', '>', '>=', '<', '<=', 'like', 'in'];

/* Consulta (L5-01-c): atributo (campo, operador, valor) + espacial opcional (dentro da SELEÇÃO do mapa, isto é,
   `s_intersects` com o envelope dos registros selecionados da vista) ou CQL2-text livre; ao executar, emite
   `filtro_mudou` {filtro} — a mensagem do documento aplica na vista alvo — e `consulta.executada` com o total
   que a própria vista devolve (`vista.total()`, no servidor quando é camada). "Limpar" emite filtro nulo. */
class PlatConsulta extends PlatWidget {
  renderizar(mudanca = null) {
    if (mudanca) { this.#atualizarTotal(); return; }
    const form = document.createElement('form'); form.className = 'consulta-form';
    const campos = (this.configuracao.campos && this.configuracao.campos.length) ? this.configuracao.campos : (this.vista ? this.vista.fonte.camposDeclarados.map((c) => c.nome) : []);
    const selCampo = document.createElement('select'); selCampo.className = 'consulta-campo'; selCampo.setAttribute('aria-label', 'campo');
    for (const c of campos) { const o = document.createElement('option'); o.value = c; o.textContent = c; selCampo.append(o); }
    const selOp = document.createElement('select'); selOp.className = 'consulta-operador'; selOp.setAttribute('aria-label', 'operador');
    for (const op of OPERADORES) { const o = document.createElement('option'); o.value = op; o.textContent = op; selOp.append(o); }
    const valor = document.createElement('input'); valor.className = 'consulta-valor'; valor.setAttribute('aria-label', 'valor');
    const texto = document.createElement('input'); texto.className = 'consulta-cql2'; texto.setAttribute('aria-label', 'CQL2'); texto.title = 'CQL2-text opcional; substitui campo/operador/valor';
    const espacial = document.createElement('input'); espacial.type = 'checkbox'; espacial.className = 'consulta-espacial';
    const rotEsp = document.createElement('label'); rotEsp.append(espacial, ' dentro da seleção do mapa');
    const executar = document.createElement('button'); executar.type = 'submit'; executar.className = 'consulta-executar'; executar.textContent = this.configuracao.rotulo || 'Consultar';
    const limpar = document.createElement('button'); limpar.type = 'button'; limpar.className = 'consulta-limpar'; limpar.textContent = 'Limpar';
    const total = document.createElement('output'); total.className = 'consulta-total';
    form.append(selCampo, selOp, valor, texto, this.configuracao.espacial === false ? '' : rotEsp, executar, limpar, total);
    form.addEventListener('submit', (e) => { e.preventDefault(); this.#executar({ campo: selCampo.value, operador: selOp.value, valor: valor.value, cql2: texto.value, espacial: espacial.checked }); });
    limpar.addEventListener('click', () => { valor.value = ''; texto.value = ''; this.emitir('filtro_mudou', { filtro: null, valor: null }); });
    this.replaceChildren(form);
  }

  #executar({ campo, operador, valor, cql2, espacial }) {
    let filtro = null;
    try {
      if (cql2 && cql2.trim()) filtro = analisarTexto(cql2);
      else if (campo && valor !== '') {
        const v = valorTipado(valor, this.vista?.fonte.campo(campo)?.tipo);
        if (operador === 'in') filtro = { op: 'in', args: [{ property: campo }, String(valor).split(',').map((x) => valorTipado(x.trim(), this.vista?.fonte.campo(campo)?.tipo))] };
        else if (operador === 'like') filtro = { op: 'like', args: [{ property: campo }, String(valor).includes('%') ? String(valor) : `%${valor}%`] };
        else filtro = { op: operador, args: [{ property: campo }, v] };
      }
      if (espacial && this.vista) {
        const env = this.vista.envelopeSelecao();
        if (env) {
          const caixa = { type: 'Polygon', coordinates: [[[env[0], env[1]], [env[2], env[1]], [env[2], env[3]], [env[0], env[3]], [env[0], env[1]]]] };
          const esp = { op: 's_intersects', args: [{ property: 'geometria' }, caixa] };
          filtro = filtro ? { op: 'and', args: [filtro, esp] } : esp;
        }
      }
    } catch (e) { this.dataset.erro = e.codigo || e.message; this.querySelector('.consulta-total').textContent = `consulta inválida: ${e.message}`; return; }
    delete this.dataset.erro;
    this.emitir('filtro_mudou', { filtro, valor });
    this.#atualizarTotal(filtro);
  }

  async #atualizarTotal(filtro = undefined) {
    if (!this.vista) return;
    try {
      const total = await this.vista.total();
      const out = this.querySelector('.consulta-total'); if (out) out.textContent = `${total} registro(s)`;
      this.dataset.total = String(total);
      if (filtro !== undefined) this.emitir('consulta.executada', { filtro, total });
    } catch (e) { this.dataset.erro = e.message; }
  }

  acao_consulta_executar(detalhe) { this.#executar({ campo: detalhe.campo, operador: detalhe.operador || '=', valor: detalhe.valor ?? '', cql2: detalhe.cql2 || '', espacial: !!detalhe.espacial }); }
  acao_limpar_filtro() { this.emitir('filtro_mudou', { filtro: null, valor: null }); }
}

function valorTipado(v, tipo) {
  if (tipo === 'inteiro' || tipo === 'decimal') { const n = Number(v); return Number.isNaN(n) ? v : n; }
  if (tipo === 'booleano') return v === 'true' || v === '1' || v === 'sim';
  return v;
}

definir('plat-consulta', PlatConsulta);
