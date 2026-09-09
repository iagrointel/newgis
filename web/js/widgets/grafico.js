import { PlatWidget, definir } from './base.js';

export const contrato = Object.freeze({
  eventos: ['clique', 'selecao_mudou', 'filtro_mudou', 'registros_carregados'],
  acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'piscar'],
});

/* Gráfico de barras por categoria (L5-07): agrega `vista.registros()` por `campo` (contagem, soma ou média de
   `campo_valor`), SVG desenhado aqui sem biblioteca. Clique numa barra emite `clique` com os ids da categoria e
   `filtro_mudou` com o CQL2 `campo = valor` — a mensagem do documento decide o que fazer com isso. As barras das
   categorias com registros selecionados na vista aparecem destacadas. */
class PlatGrafico extends PlatWidget {
  renderizar() {
    const campo = this.configuracao.campo;
    const agreg = this.configuracao.agregacao || 'contagem';
    const campoValor = this.configuracao.campo_valor;
    const maximo = this.configuracao.maximo_barras || 20;
    const registros = this.vista ? this.vista.registros() : [];
    const selecao = this.vista ? this.vista.selecao : new Set();
    const grupos = new Map();
    for (const f of registros) {
      const chave = String(f.propriedades?.[campo] ?? '');
      const g = grupos.get(chave) || { valor: chave, n: 0, soma: 0, ids: [], selecionados: 0 };
      g.n += 1; g.ids.push(f.id);
      const v = Number(f.propriedades?.[campoValor]); if (!Number.isNaN(v)) g.soma += v;
      if (selecao.has(f.id)) g.selecionados += 1;
      grupos.set(chave, g);
    }
    const barras = [...grupos.values()].map((g) => ({ ...g, medida: agreg === 'soma' ? g.soma : (agreg === 'media' ? (g.n ? g.soma / g.n : 0) : g.n) }))
      .sort((a, b) => b.medida - a.medida).slice(0, maximo);
    const max = Math.max(1, ...barras.map((b) => b.medida));
    const L = 320; const linha = 18; const A = barras.length * linha + 8; const esq = 110;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${L} ${Math.max(A, 26)}`); svg.setAttribute('width', '100%');
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `${barras.length} categoria(s) de ${campo}`);
    barras.forEach((b, i) => {
      const y = 4 + i * linha;
      const larg = Math.round((L - esq - 44) * b.medida / max);
      const g = document.createElementNS(ns, 'g');
      g.setAttribute('class', 'barra' + (b.selecionados ? ' selecionada' : ''));
      g.dataset.valor = b.valor; g.dataset.n = String(b.n);
      g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
      const tx = document.createElementNS(ns, 'text'); tx.setAttribute('x', String(esq - 6)); tx.setAttribute('y', String(y + 12)); tx.setAttribute('text-anchor', 'end'); tx.textContent = b.valor || '(vazio)';
      const r = document.createElementNS(ns, 'rect'); r.setAttribute('x', String(esq)); r.setAttribute('y', String(y + 2)); r.setAttribute('width', String(Math.max(1, larg))); r.setAttribute('height', String(linha - 5));
      const tn = document.createElementNS(ns, 'text'); tn.setAttribute('x', String(esq + larg + 4)); tn.setAttribute('y', String(y + 12)); tn.textContent = Number.isInteger(b.medida) ? String(b.medida) : b.medida.toFixed(2);
      g.append(tx, r, tn);
      g.addEventListener('click', () => this.#clique(b));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#clique(b); } });
      svg.append(g);
    });
    const titulo = document.createElement('p');
    titulo.className = 'grafico-titulo';
    titulo.textContent = this.configuracao.titulo || `${agreg} por ${campo}`;
    this.dataset.total = String(registros.length);
    this.dataset.barras = String(barras.length);
    this.replaceChildren(titulo, svg);
  }

  #clique(b) {
    const campo = this.configuracao.campo;
    this.emitir('clique', { ids: b.ids, valor: b.valor, campo });
    this.emitir('filtro_mudou', { filtro: { op: '=', args: [{ property: campo }, b.valor] }, valor: b.valor, campo });
  }
}

definir('plat-grafico', PlatGrafico);
