import { PlatWidget, definir } from './base.js';
import { carregarChart } from './util_dado.js';

export const contrato = Object.freeze({
  eventos: ['clique', 'selecao_mudou', 'filtro_mudou', 'registros_carregados', 'grafico.desenhado'],
  acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'piscar', 'grafico.definir'],
});

export const TIPOS = Object.freeze(['barra', 'linha', 'pizza', 'dispersao', 'histograma']);

/* Gráfico sobre uma VISTA (L5-01-c): barra, linha e pizza vêm de `vista.agregar()` (em fonte de camada é o
   FeatureServer `outStatistics` + `groupByFieldsForStatistics` com o filtro da vista — a soma bate com SQL
   direto, teste do item); histograma vem de `vista.histograma()` (min/max e uma contagem por faixa no
   servidor); dispersão desenha uma amostra de até `amostra` registros (x = campo, y = campo_y). Desenho com
   Chart.js 4.5.1 (web/vendor, D21), carregado só aqui; sem o Chart.js (rede fora, Node) cai no SVG de barras
   próprio. Clique numa barra/fatia emite `clique` {valor, campo} e `filtro_mudou` com o CQL2 `campo = valor`
   (ou `between` na faixa do histograma) — a mensagem do documento decide o que fazer. `this.dados` guarda a
   última série desenhada (o teste lê). */
class PlatGrafico extends PlatWidget {
  #pedido = 0;
  #chart = null;
  dados = [];

  renderizar(mudanca = null) {
    if (mudanca && mudanca.causa === 'selecao_mudou' && this.configuracao.tipo === 'dispersao') return;
    this.#carregar();
  }

  #cfg() {
    const c = this.configuracao;
    return { tipo: TIPOS.includes(c.tipo) ? c.tipo : 'barra', campo: c.campo, agregacao: c.agregacao || 'contagem', campo_valor: c.campo_valor || null,
      campo_y: c.campo_y || null, maximo: c.maximo_barras || 20, faixas: c.faixas || 10, amostra: c.amostra || 1000, altura: c.altura || 240 };
  }

  async #carregar() {
    const pedido = ++this.#pedido;
    const cfg = this.#cfg();
    this.dataset.carregando = '1';
    try {
      let serie = [];
      if (this.vista) {
        if (cfg.tipo === 'histograma') serie = (await this.vista.histograma({ campo: cfg.campo, faixas: cfg.faixas })).map((f) => ({ valor: `${arred(f.de)}–${arred(f.ate)}`, de: f.de, ate: f.ate, medida: f.n, n: f.n }));
        else if (cfg.tipo === 'dispersao') {
          const r = await this.vista.pagina({ deslocamento: 0, limite: cfg.amostra, campos: [cfg.campo, cfg.campo_y] });
          serie = r.registros.map((f) => ({ id: f.id, x: Number(f.propriedades?.[cfg.campo]), y: Number(f.propriedades?.[cfg.campo_y]) })).filter((p) => !Number.isNaN(p.x) && !Number.isNaN(p.y));
        } else serie = await this.vista.agregar({ campo: cfg.campo, agregacao: cfg.agregacao, campo_valor: cfg.campo_valor, maximo: cfg.maximo });
      }
      if (pedido !== this.#pedido) return;
      this.dados = serie;
      await this.#desenhar(serie, cfg);
      if (pedido !== this.#pedido) return;
      this.dataset.grupos = String(serie.length);
      this.dataset.tipo = cfg.tipo;
      this.dataset.pronto = '1';
      this.emitir('grafico.desenhado', { tipo: cfg.tipo, grupos: serie.length });
    } catch (e) {
      if (pedido !== this.#pedido) return;
      const p = document.createElement('p'); p.className = 'grafico-erro'; p.textContent = `gráfico: ${e.message}`;
      this.replaceChildren(p);
    } finally { if (pedido === this.#pedido) delete this.dataset.carregando; }
  }

  async #desenhar(serie, cfg) {
    const titulo = document.createElement('p');
    titulo.className = 'grafico-titulo';
    titulo.textContent = this.configuracao.titulo || (cfg.tipo === 'dispersao' ? `${cfg.campo} × ${cfg.campo_y}` : `${cfg.agregacao} por ${cfg.campo}`);
    const Chart = await carregarChart();
    if (!Chart) { this.replaceChildren(titulo, this.#svgBarras(serie, cfg)); return; }
    const caixa = document.createElement('div'); caixa.className = 'grafico-caixa'; caixa.style.height = `${cfg.altura}px`;
    const canvas = document.createElement('canvas'); canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', cfg.tipo === 'dispersao' ? `${serie.length} ponto(s)` : `${serie.length} categoria(s) de ${cfg.campo}`);
    caixa.append(canvas);
    this.replaceChildren(titulo, caixa);
    if (this.#chart) { this.#chart.destroy(); this.#chart = null; }
    const cores = paleta(serie.length);
    const selecao = this.vista ? this.vista.selecao : new Set();
    const tipoChart = { barra: 'bar', linha: 'line', pizza: 'pie', dispersao: 'scatter', histograma: 'bar' }[cfg.tipo];
    const rotulos = serie.map((g) => (g.valor === null || g.valor === undefined ? '(vazio)' : String(g.valor)));
    const dados = cfg.tipo === 'dispersao' ? serie.map((p) => ({ x: p.x, y: p.y })) : serie.map((g) => g.medida ?? 0);
    const destacada = (g) => g.ids && g.ids.some((id) => selecao.has(id));
    const cor = cfg.tipo === 'pizza' ? cores : serie.map((g, i) => (destacada(g) ? '#d98a2b' : cores[i % cores.length]));
    this.#chart = new Chart(canvas, {
      type: tipoChart,
      data: { labels: cfg.tipo === 'dispersao' ? undefined : rotulos, datasets: [{ label: titulo.textContent, data: dados, backgroundColor: cfg.tipo === 'linha' ? '#1f6f8b' : cor, borderColor: '#1f6f8b' }] },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: cfg.tipo === 'pizza' } },
        scales: cfg.tipo === 'pizza' ? {} : { y: { beginAtZero: true } },
        onClick: (evento, elementos) => { const el = elementos && elementos[0]; if (el) this.#clique(serie[el.index], cfg); },
      },
    });
  }

  #svgBarras(serie, cfg) {
    const max = Math.max(1, ...serie.map((b) => Number(b.medida) || 0));
    const L = 320; const linha = 18; const A = serie.length * linha + 8; const esq = 110;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${L} ${Math.max(A, 26)}`); svg.setAttribute('width', '100%');
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `${serie.length} categoria(s) de ${cfg.campo}`);
    serie.forEach((b, i) => {
      const y = 4 + i * linha; const medida = Number(b.medida) || 0;
      const larg = Math.round((L - esq - 44) * medida / max);
      const g = document.createElementNS(ns, 'g'); g.setAttribute('class', 'barra'); g.dataset.valor = String(b.valor ?? ''); g.dataset.n = String(b.n ?? '');
      g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
      const tx = document.createElementNS(ns, 'text'); tx.setAttribute('x', String(esq - 6)); tx.setAttribute('y', String(y + 12)); tx.setAttribute('text-anchor', 'end'); tx.textContent = b.valor === null || b.valor === undefined ? '(vazio)' : String(b.valor);
      const r = document.createElementNS(ns, 'rect'); r.setAttribute('x', String(esq)); r.setAttribute('y', String(y + 2)); r.setAttribute('width', String(Math.max(1, larg))); r.setAttribute('height', String(linha - 5));
      const tn = document.createElementNS(ns, 'text'); tn.setAttribute('x', String(esq + larg + 4)); tn.setAttribute('y', String(y + 12)); tn.textContent = Number.isInteger(medida) ? String(medida) : medida.toFixed(2);
      g.append(tx, r, tn);
      g.addEventListener('click', () => this.#clique(b, cfg));
      svg.append(g);
    });
    return svg;
  }

  #clique(g, cfg) {
    if (!g) return;
    if (cfg.tipo === 'dispersao') { this.emitir('clique', { ids: [g.id], id: g.id }); if (this.vista) this.vista.definirSelecao([g.id], this.noId); return; }
    let filtro;
    if (cfg.tipo === 'histograma') filtro = { op: 'between', args: [{ property: cfg.campo }, g.de, g.ate] };
    else filtro = g.valor === null || g.valor === undefined ? { op: 'isNull', args: [{ property: cfg.campo }] } : { op: '=', args: [{ property: cfg.campo }, g.valor] };
    this.emitir('clique', { ids: g.ids || [], valor: g.valor, campo: cfg.campo });
    this.emitir('filtro_mudou', { filtro, valor: g.valor, campo: cfg.campo });
  }

  acao_grafico_definir(detalhe) { this.configuracao = { ...this.configuracao, ...(detalhe || {}) }; }

  disconnectedCallback() { super.disconnectedCallback(); if (this.#chart) { this.#chart.destroy(); this.#chart = null; } }
}

function arred(v) { return Number.isInteger(v) ? String(v) : Number(v).toFixed(2); }
function paleta(n) { const base = ['#1f6f8b', '#2a9d8f', '#e9c46a', '#f4a261', '#e76f51', '#6d597a', '#355070', '#b56576', '#8ab17d', '#577590']; return Array.from({ length: Math.max(n, 1) }, (_, i) => base[i % base.length]); }

definir('plat-grafico', PlatGrafico);
