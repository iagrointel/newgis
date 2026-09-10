/* plat · painel — desenho do GRÁFICO SERIAL (item L2-06-b-elementos-basicos): barras, linhas e área, por
   categoria ou por faixa de data, com uma ou VÁRIAS séries, agrupadas ou empilhadas. Renderizador puro: recebe
   `{chaves, series:[{rotulo, valores}], granularidade}` (a forma que `app/paineis/dados.py::_serie` devolve, já
   agregada no servidor pelo motor do L2-06-e) e devolve a mesma árvore virtual `{tag, atrs, filhos}` do
   `web/js/mapa/grafico_svg.js` — nenhum número é calculado aqui além da escala do desenho.

   Por que um módulo próprio e não o `grafico_svg.js`: aquele desenha UMA série (é o gráfico de camada do
   L2-01-i); o painel precisa de N séries, empilhamento e eixo de data. As primitivas comuns (ticks, formatação,
   rótulo de data, cores, nó) vêm de lá — uma definição só. */
import { CORES, ticks, formatarNumero, rotuloData, no } from '../mapa/grafico_svg.js';

export const LARGURA = 420;
export const ALTURA = 240;
const MARGEM = { topo: 14, dir: 12, base: 46, esq: 52 };
export const MAX_CHAVES = 120;

function r2(v) { return Math.round(v * 100) / 100; }
function texto(x, y, conteudo, atrs = {}) { return no('text', { x: r2(x), y: r2(y), ...atrs }, [String(conteudo)]); }

export function rotuloDeChave(chave, granularidade) {
  if (chave === null || chave === undefined) return 'sem valor';
  if (granularidade) return rotuloData(String(chave), granularidade);
  return String(chave);
}

function escala(d0, d1, p0, p1) {
  const d = d1 - d0 || 1;
  return (v) => p0 + ((v - d0) / d) * (p1 - p0);
}

function eixoY(esc, valores, x0, x1) {
  const filhos = [];
  for (const v of valores) {
    const y = esc(v);
    filhos.push(no('line', { x1: r2(x0), y1: r2(y), x2: r2(x1), y2: r2(y), class: 'grade' }));
    filhos.push(texto(x0 - 6, y + 3, formatarNumero(v), { class: 'tick', 'text-anchor': 'end' }));
  }
  return filhos;
}

function vazio(mensagem, titulo) {
  return no('svg', { viewBox: `0 0 ${LARGURA} ${ALTURA}`, class: 'grafico grafico-vazio', role: 'img',
    'aria-label': titulo }, [texto(LARGURA / 2, ALTURA / 2, mensagem, { 'text-anchor': 'middle', class: 'vazio' })]);
}

/** `dados` = {chaves, series, granularidade}; `opcoes` = {tipo: barras|linhas|area, empilhado, titulo,
 *  mensagemVazio, mostrarLegenda}. Toda série é desenhada na mesma escala; empilhado soma na ordem das séries. */
export function desenharSerie(dados, opcoes = {}) {
  const tipo = opcoes.tipo || 'barras';
  const titulo = opcoes.titulo || `gráfico de ${tipo}`;
  const chaves = (dados.chaves || []).slice(0, MAX_CHAVES);
  const series = (dados.series || []).map((s) => ({ ...s, valores: (s.valores || []).slice(0, MAX_CHAVES) }));
  if (!chaves.length || !series.length) return vazio(opcoes.mensagemVazio || 'sem dado', titulo);

  const empilhado = !!opcoes.empilhado && series.length > 1;
  const num = (v) => (v === null || v === undefined ? 0 : Number(v) || 0);
  const somas = chaves.map((_, i) => series.reduce((t, s) => t + num(s.valores[i]), 0));
  const todos = empilhado ? somas : series.flatMap((s) => s.valores.map(num));
  const vmax = Math.max(0, ...todos);
  const vmin = Math.min(0, ...todos);
  const tk = ticks(vmin, vmax);
  const ymax = Math.max(vmax, tk[tk.length - 1]);
  const ymin = Math.min(vmin, tk[0]);
  const x0 = MARGEM.esq; const x1 = LARGURA - MARGEM.dir;
  const y0 = ALTURA - MARGEM.base; const y1 = MARGEM.topo;
  const ey = escala(ymin, ymax, y0, y1);
  const filhos = [...eixoY(ey, tk, x0, x1)];
  const passo = (x1 - x0) / chaves.length;
  const base = ey(Math.max(0, ymin));

  if (tipo === 'barras') {
    const nb = empilhado ? 1 : series.length;
    const largura = Math.max(2, (passo * 0.72) / nb);
    chaves.forEach((chave, i) => {
      let acumulado = 0;
      series.forEach((s, j) => {
        const v = num(s.valores[i]);
        const cor = CORES[j % CORES.length];
        let yTopo; let alturaBarra; let x;
        if (empilhado) {
          const de = ey(acumulado); const ate = ey(acumulado + v);
          acumulado += v;
          yTopo = Math.min(de, ate); alturaBarra = Math.abs(ate - de);
          x = x0 + i * passo + (passo - largura) / 2;
        } else {
          const ate = ey(v);
          yTopo = Math.min(base, ate); alturaBarra = Math.abs(ate - base);
          x = x0 + i * passo + (passo * 0.14) + j * largura;
        }
        filhos.push(no('rect', {
          x: r2(x), y: r2(yTopo), width: r2(largura), height: r2(Math.max(alturaBarra, v === 0 ? 0 : 1)),
          fill: cor, class: 'barra', 'data-serie': String(j), 'data-chave': String(chave ?? ''),
        }, [no('title', {}, [`${rotuloDeChave(chave, dados.granularidade)} · ${s.rotulo}: ${formatarNumero(v)}`])]));
      });
    });
  } else {
    // linhas e área: um caminho por série, ponto no centro de cada faixa
    series.forEach((s, j) => {
      const cor = CORES[j % CORES.length];
      const pontos = chaves.map((_, i) => [x0 + i * passo + passo / 2, ey(num(s.valores[i]))]);
      const d = pontos.map(([x, y], i) => `${i ? 'L' : 'M'}${r2(x)},${r2(y)}`).join(' ');
      if (tipo === 'area') {
        const fecha = `${d} L${r2(pontos[pontos.length - 1][0])},${r2(base)} L${r2(pontos[0][0])},${r2(base)} Z`;
        filhos.push(no('path', { d: fecha, fill: cor, 'fill-opacity': '0.25', class: 'area' }));
      }
      filhos.push(no('path', { d, fill: 'none', stroke: cor, 'stroke-width': '2', class: 'linha',
        'data-serie': String(j) }));
      pontos.forEach(([x, y], i) => filhos.push(no('circle', { cx: r2(x), cy: r2(y), r: 2.5, fill: cor,
        class: 'ponto', 'data-serie': String(j), 'data-chave': String(chaves[i] ?? '') },
      [no('title', {}, [`${rotuloDeChave(chaves[i], dados.granularidade)} · ${s.rotulo}: ${formatarNumero(num(s.valores[i]))}`])])));
    });
  }

  // eixo X: rótulos rareados para não colidir
  const cada = Math.max(1, Math.ceil(chaves.length / 8));
  chaves.forEach((chave, i) => {
    if (i % cada) return;
    filhos.push(texto(x0 + i * passo + passo / 2, y0 + 14, rotuloDeChave(chave, dados.granularidade),
      { 'text-anchor': 'middle', class: 'tick' }));
  });
  filhos.push(no('line', { x1: r2(x0), y1: r2(base), x2: r2(x1), y2: r2(base), class: 'eixo' }));

  if (opcoes.mostrarLegenda !== false && series.length > 1) {
    series.forEach((s, j) => {
      const x = x0 + j * ((x1 - x0) / series.length);
      filhos.push(no('rect', { x: r2(x), y: r2(ALTURA - 14), width: 9, height: 9, fill: CORES[j % CORES.length] }));
      filhos.push(texto(x + 13, ALTURA - 6, s.rotulo, { class: 'tick' }));
    });
  }
  return no('svg', { viewBox: `0 0 ${LARGURA} ${ALTURA}`, class: `grafico grafico-${tipo}`, role: 'img',
    'aria-label': titulo }, filhos);
}

/** Tabela equivalente do MESMO dado (leitor de tela e conferência): cabeçalho + uma linha por chave. */
export function tabelaDaSerie(dados) {
  const series = dados.series || [];
  return {
    cabecalho: [dados.chave || 'categoria', ...series.map((s) => s.rotulo)],
    linhas: (dados.chaves || []).map((chave, i) => [
      rotuloDeChave(chave, dados.granularidade),
      ...series.map((s) => (s.valores || [])[i]),
    ]),
  };
}
