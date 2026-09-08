/* plat · mapa — desenho de gráficos em SVG próprio (item L2-01-i-graficos-de-camada).

   Módulo PURO: recebe a resposta de POST /api/camadas/{id}/grafico (já agregada no servidor) e devolve uma
   árvore {tag, atrs, filhos} que o painel converte em elementos SVG (createElementNS) e que o teste serializa
   em texto (paraTexto) para conferir tamanho e conteúdo no node, sem navegador. Nenhuma dependência, nenhum
   HTML em string, nenhum dado cru: o que chega aqui já são no máximo centenas de números.

   Cinco tipos: barras, pizza, linha (por faixa de data), histograma e dispersão (com a reta de regressão e o r²
   que o servidor calculou sobre TODAS as linhas — os pontos desenhados são uma amostra declarada). Cada barra,
   fatia, ponto de linha e faixa carrega data-chave/data-de/data-ate para o painel ligar o clique à seleção no
   mapa. A tabela oculta (tabela()) e o CSV (csv()) saem dos MESMOS dados que o desenho. */

export const LARGURA = 320;
export const ALTURA = 220;
const MARGEM = { topo: 22, dir: 10, base: 42, esq: 46 };
export const CORES = ['#d98a2b', '#4f9e6e', '#5b8fd9', '#c75c8a', '#8fa19c', '#e0c24a', '#7c5cc7', '#4fb0b8',
  '#b8623b', '#6b9e3a', '#a05c9e', '#3c7f9e'];
const COR_OUTROS = '#5b6467';
const COR_SEL = '#ffd54a';
/* tetos de DESENHO (a tabela oculta e o CSV guardam tudo): é o que segura o SVG em ≤ 40 kB por construção,
   qualquer que seja a resposta do servidor (que por sua vez é ≤ 1 MB) */
export const MAX_BARRAS = 100;
export const MAX_FATIAS = 50;
export const MAX_PONTOS_LINHA = 400;
export const MAX_PONTOS_DISPERSAO = 1500;

export function no(tag, atrs = {}, filhos = []) { return { tag, atrs, filhos }; }
function texto(x, y, conteudo, atrs = {}) { return no('text', { x: r2(x), y: r2(y), ...atrs }, [String(conteudo)]); }
function r2(v) { return Math.round(v * 100) / 100; }

export function formatarNumero(v, casas = null) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (casas !== null) return n.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const abs = Math.abs(n);
  const c = abs >= 1000 || Number.isInteger(n) ? 0 : abs >= 10 ? 1 : abs >= 1 ? 2 : 3;
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: c });
}

export function rotuloChave(chave, tipo, granularidade) {
  if (chave === null || chave === undefined) return 'sem valor';
  if (tipo === 'linha') return rotuloData(String(chave), granularidade);
  const s = String(chave);
  return s.length > 18 ? `${s.slice(0, 17)}…` : s;
}

export function rotuloData(iso, granularidade) {
  if (iso === 'infinity' || iso === '-infinity') return iso === 'infinity' ? '+∞' : '−∞';
  const m = /^(-?\d{4,})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const bc = / BC$/.test(iso) ? ' a.C.' : '';
  const [, a, me, d] = m;
  if (granularidade === 'ano') return `${a}${bc}`;
  if (granularidade === 'mes') return `${me}/${a}${bc}`;
  if (granularidade === 'trimestre') return `T${Math.floor((Number(me) - 1) / 3) + 1}/${a}${bc}`;
  return `${d}/${me}/${a}${bc}`;
}

/* ticks "bonitos" (1-2-5) para um eixo de 0 (ou mínimo) a máximo */
export function ticks(minimo, maximo, alvo = 4) {
  if (!(maximo > minimo)) return [minimo];
  const bruto = (maximo - minimo) / alvo;
  const pot = 10 ** Math.floor(Math.log10(bruto));
  const f = bruto / pot;
  const passo = (f <= 1.5 ? 1 : f <= 3 ? 2 : f <= 7 ? 5 : 10) * pot;
  const casas = Math.max(0, -Math.floor(Math.log10(passo)));
  const saida = [];
  for (let v = Math.ceil(minimo / passo - 1e-9) * passo; v <= maximo + passo * 1e-9; v += passo) saida.push(Number(v.toFixed(casas)));
  return saida;
}

function eixoY(escala, valores, x0, x1) {
  const filhos = [];
  for (const v of valores) {
    const y = escala(v);
    filhos.push(no('line', { x1: x0, x2: x1, y1: r2(y), y2: r2(y), class: 'grade' }));
    filhos.push(texto(x0 - 4, y + 3, formatarNumero(v), { class: 'eixo', 'text-anchor': 'end' }));
  }
  return no('g', { class: 'eixo-y' }, filhos);
}

function escalaLinear(d0, d1, p0, p1) {
  const span = d1 - d0 || 1;
  return (v) => p0 + ((v - d0) / span) * (p1 - p0);
}

function raiz(filhos, titulo) {
  return no('svg', {
    xmlns: 'http://www.w3.org/2000/svg', viewBox: `0 0 ${LARGURA} ${ALTURA}`, width: '100%', role: 'img',
    'aria-label': titulo, class: 'grafico-svg', 'font-family': 'IBM Plex Sans, system-ui, sans-serif', 'font-size': '10',
  }, [no('style', {}, ['.grade{stroke:#3a4649;stroke-width:.5}.eixo{fill:#8fa19c}.rot{fill:#e7ece9}'
    + '.barra{cursor:pointer}.barra:hover,.fatia:hover{opacity:.8}.sel{stroke:#ffd54a;stroke-width:2}'
    + '.vazio{fill:#8fa19c;font-size:11px}']), ...filhos]);
}

function vazio(mensagem, titulo) {
  return raiz([texto(LARGURA / 2, ALTURA / 2, mensagem, { class: 'vazio', 'text-anchor': 'middle' })], titulo);
}

function serieComOutros(dados, maximo = Infinity) {
  let s = dados.series.map((e) => ({ ...e }));
  let outros = dados.outros ? { ...dados.outros } : null;
  if (s.length > maximo) {
    // corte no CLIENTE só para o desenho: o excedente vira (ou engorda) o grupo "outros"; a tabela guarda tudo
    const resto = s.slice(maximo);
    s = s.slice(0, maximo);
    const n = resto.reduce((t, e) => t + (e.n || 0), 0);
    const soma = resto.reduce((t, e) => t + (e.valor === null ? 0 : Number(e.valor)), 0);
    const valor = dados.estatistica === 'avg' ? (n ? soma / resto.length : null) : (outros ? Number(outros.valor || 0) + soma : soma);
    outros = { categorias: (outros ? outros.categorias : 0) + resto.length, n: (outros ? outros.n : 0) + n,
      valor: dados.estatistica === 'avg' && outros ? outros.valor : valor };
  }
  if (outros) s.push({ chave: '__outros__', n: outros.n, valor: outros.valor, outros: true, categorias: outros.categorias });
  return s;
}

function rotuloDeSerie(e, dados, opcoes) {
  if (e.outros) return `outros (${formatarNumero(e.categorias)})`;
  return rotuloChave(e.chave, dados.tipo, dados.granularidade || opcoes.granularidade);
}

/* ------------------------------------------------------------------ barras (categoria) e histograma (faixas) */
function barras(dados, opcoes) {
  const serie = dados.tipo === 'histograma' ? dados.series : serieComOutros(dados, MAX_BARRAS);
  if (!serie.length) return vazio(opcoes.mensagemVazio, opcoes.titulo);
  const valores = serie.map((e) => (e.valor === null ? 0 : Number(e.valor)));
  const vmax = Math.max(0, ...valores);
  const vmin = Math.min(0, ...valores);
  const x0 = MARGEM.esq;
  const x1 = LARGURA - MARGEM.dir;
  const y0 = ALTURA - MARGEM.base;
  const y1 = MARGEM.topo;
  const tk = ticks(vmin, vmax);
  const ymax = Math.max(vmax, tk[tk.length - 1]);
  const ymin = Math.min(vmin, tk[0]);
  const ey = escalaLinear(ymin, ymax, y0, y1);
  const n = serie.length;
  const contiguo = dados.tipo === 'histograma';
  const largura = (x1 - x0) / n;
  const folga = contiguo ? 0.5 : Math.min(6, largura * 0.2);
  const filhos = [eixoY(ey, tk, x0, x1)];
  const baseY = ey(0);
  filhos.push(no('line', { x1: x0, x2: x1, y1: r2(baseY), y2: r2(baseY), stroke: '#8fa19c', 'stroke-width': 1 }));
  const rotulos = [];
  const cada = Math.max(1, Math.ceil(n / 8));
  serie.forEach((e, i) => {
    const v = valores[i];
    const xa = x0 + i * largura + folga;
    const w = Math.max(1, largura - 2 * folga);
    const ya = ey(Math.max(v, 0));
    const h = Math.max(v === 0 ? 0 : 1, Math.abs(ey(v) - baseY));
    const atrs = {
      x: r2(xa), y: r2(ya), width: r2(w), height: r2(h), class: 'barra', role: 'button', tabindex: '0',
      fill: e.outros ? COR_OUTROS : (opcoes.selecionado && opcoes.selecionado(e) ? COR_SEL : (dados.tipo === 'histograma' ? CORES[0] : CORES[i % CORES.length])),
      'data-i': String(i),
    };
    if (contiguo) { atrs['data-de'] = String(e.de); atrs['data-ate'] = String(e.ate); if (i === n - 1) atrs['data-ultima'] = '1'; }
    else if (e.outros) atrs['data-outros'] = '1';
    else atrs['data-chave'] = e.chave === null ? '' : String(e.chave);
    if (e.chave === null && !contiguo) atrs['data-nulo'] = '1';
    const rot = contiguo ? `${formatarNumero(e.de)} – ${formatarNumero(e.ate)}` : rotuloDeSerie(e, dados, opcoes);
    const dica = n <= 60 ? [no('title', {}, [`${rot}: ${formatarNumero(e.valor)} (${formatarNumero(e.n)} linhas)`])] : [];
    filhos.push(no('rect', atrs, dica));
    if (n <= 24) filhos.push(texto(xa + w / 2, ya - 3, formatarNumero(e.valor), { class: 'rot', 'text-anchor': 'middle', 'font-size': '8' }));
    if (contiguo) {
      if (i % cada === 0) rotulos.push(texto(xa, y0 + 12, formatarNumero(e.de), { class: 'eixo', 'text-anchor': 'middle', 'font-size': '8' }));
      if (i === n - 1) rotulos.push(texto(xa + w, y0 + 12, formatarNumero(e.ate), { class: 'eixo', 'text-anchor': 'middle', 'font-size': '8' }));
    } else if (i % cada === 0 || n <= 12 || e.outros) {
      const r = rot.length > 12 ? `${rot.slice(0, 11)}…` : rot;
      rotulos.push(texto(xa + w / 2, y0 + 10, r, n > 6
        ? { class: 'eixo', 'text-anchor': 'end', transform: `rotate(-35 ${r2(xa + w / 2)} ${y0 + 10})`, 'font-size': '8' }
        : { class: 'eixo', 'text-anchor': 'middle', 'font-size': '9' }));
    }
  });
  filhos.push(no('g', { class: 'eixo-x' }, rotulos));
  return raiz(filhos, opcoes.titulo);
}

/* ------------------------------------------------------------------ pizza (anel) */
function pizza(dados, opcoes) {
  const serie = serieComOutros(dados, MAX_FATIAS).filter((e) => e.valor !== null && Number(e.valor) > 0);
  if (!serie.length) return vazio(opcoes.mensagemVazio, opcoes.titulo);
  const total = serie.reduce((s, e) => s + Number(e.valor), 0);
  const cx = 90;
  const cy = ALTURA / 2;
  const R = 78;
  // rosca por padrão (o painel do L2-06-b pede as duas formas; `rosca: false` fecha o meio e vira pizza)
  const r = opcoes.rosca === false ? 0 : 40;
  const filhos = [];
  let ang = -Math.PI / 2;
  const legenda = [];
  serie.forEach((e, i) => {
    const frac = Number(e.valor) / total;
    const a0 = ang;
    const a1 = ang + frac * 2 * Math.PI;
    ang = a1;
    const grande = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a, rr) => [r2(cx + rr * Math.cos(a)), r2(cy + rr * Math.sin(a))];
    const [x0, y0] = p(a0, R);
    const [x1, y1] = p(a1 - 1e-6, R);
    const [x2, y2] = p(a1 - 1e-6, r);
    const [x3, y3] = p(a0, r);
    const d = frac >= 0.999999
      ? `M ${cx + R} ${cy} A ${R} ${R} 0 1 1 ${cx - R} ${cy} A ${R} ${R} 0 1 1 ${cx + R} ${cy} M ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy}`
      : `M ${x0} ${y0} A ${R} ${R} 0 ${grande} 1 ${x1} ${y1} L ${x2} ${y2} A ${r} ${r} 0 ${grande} 0 ${x3} ${y3} Z`;
    const cor = e.outros ? COR_OUTROS : CORES[i % CORES.length];
    const atrs = { d, fill: cor, class: 'fatia barra', role: 'button', tabindex: '0', 'fill-rule': 'evenodd', 'data-i': String(i) };
    if (e.outros) atrs['data-outros'] = '1'; else atrs['data-chave'] = e.chave === null ? '' : String(e.chave);
    if (e.chave === null) atrs['data-nulo'] = '1';
    if (opcoes.selecionado && opcoes.selecionado(e)) atrs.class += ' sel';
    const rot = rotuloDeSerie(e, dados, opcoes);
    filhos.push(no('path', atrs, [no('title', {}, [`${rot}: ${formatarNumero(e.valor)} (${(frac * 100).toFixed(1)} %)`])]));
    if (legenda.length < 12) {
      const y = 22 + legenda.length * 16;
      legenda.push(no('rect', { x: 186, y: y - 9, width: 10, height: 10, fill: cor }));
      legenda.push(texto(200, y, `${rot.length > 14 ? `${rot.slice(0, 13)}…` : rot} ${(frac * 100).toFixed(1)} %`, { class: 'rot', 'font-size': '9' }));
    }
  });
  if (serie.length > 12) filhos.push(texto(200, 22 + 12 * 16, `+ ${serie.length - 12} na tabela`, { class: 'eixo', 'font-size': '9' }));
  filhos.push(texto(cx, cy + 4, formatarNumero(total), { class: 'rot', 'text-anchor': 'middle', 'font-size': '11' }));
  return raiz([...filhos, ...legenda], opcoes.titulo);
}

/* ------------------------------------------------------------------ linha por faixa de data */
function linha(dados, opcoes) {
  const completa = dados.series.filter((e) => e.chave !== null);
  if (!completa.length) return vazio(opcoes.mensagemVazio, opcoes.titulo);
  // mais pontos do que pixels: desenha uma subamostra uniforme (a tabela e o CSV têm a série inteira)
  const passo = Math.max(1, Math.ceil(completa.length / MAX_PONTOS_LINHA));
  const serie = passo === 1 ? completa : completa.filter((_, i) => i % passo === 0 || i === completa.length - 1);
  const valores = serie.map((e) => (e.valor === null ? 0 : Number(e.valor)));
  const x0 = MARGEM.esq;
  const x1 = LARGURA - MARGEM.dir;
  const y0 = ALTURA - MARGEM.base;
  const y1 = MARGEM.topo;
  const tk = ticks(Math.min(0, ...valores), Math.max(...valores));
  const ey = escalaLinear(Math.min(tk[0], ...valores), Math.max(tk[tk.length - 1], ...valores), y0, y1);
  const ex = (i) => (serie.length === 1 ? (x0 + x1) / 2 : x0 + (i / (serie.length - 1)) * (x1 - x0));
  const pontos = serie.map((e, i) => `${r2(ex(i))},${r2(ey(valores[i]))}`).join(' ');
  const filhos = [eixoY(ey, tk, x0, x1), no('polyline', { points: pontos, fill: 'none', stroke: CORES[0], 'stroke-width': 1.5 })];
  const cada = Math.max(1, Math.ceil(serie.length / 6));
  serie.forEach((e, i) => {
    if (serie.length <= 120) {
      const atrs = { cx: r2(ex(i)), cy: r2(ey(valores[i])), r: serie.length > 60 ? 1.5 : 3, fill: CORES[0], class: 'barra ponto',
        role: 'button', tabindex: '0', 'data-i': String(i), 'data-chave': String(e.chave),
        'data-ate': serie[i + 1] ? String(serie[i + 1].chave) : '' };
      if (opcoes.selecionado && opcoes.selecionado(e)) atrs.class += ' sel';
      filhos.push(no('circle', atrs, [no('title', {}, [`${rotuloChave(e.chave, 'linha', dados.granularidade)}: ${formatarNumero(e.valor)}`])]));
    }
    if (i % cada === 0 || i === serie.length - 1) {
      filhos.push(texto(ex(i), y0 + 12, rotuloData(String(e.chave), dados.granularidade), { class: 'eixo', 'text-anchor': 'middle', 'font-size': '8' }));
    }
  });
  if (dados.nulos) filhos.push(texto(x1, y1 + 2, `${formatarNumero(dados.nulos)} sem data`, { class: 'eixo', 'text-anchor': 'end', 'font-size': '8' }));
  if (passo > 1) filhos.push(texto(x0, y1 + 2, `${formatarNumero(serie.length)} de ${formatarNumero(completa.length)} faixas desenhadas`, { class: 'eixo', 'font-size': '8' }));
  return raiz(filhos, opcoes.titulo);
}

/* ------------------------------------------------------------------ dispersão com reta de regressão */
function dispersao(dados, opcoes) {
  const todos = dados.series;
  if (!todos.length) return vazio(opcoes.mensagemVazio, opcoes.titulo);
  const passo = Math.max(1, Math.ceil(todos.length / MAX_PONTOS_DISPERSAO));
  const pts = passo === 1 ? todos : todos.filter((_, i) => i % passo === 0);
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const xmin = Math.min(dados.x_min ?? Infinity, ...xs);
  const xmax = Math.max(dados.x_max ?? -Infinity, ...xs);
  const ymin = Math.min(dados.y_min ?? Infinity, ...ys);
  const ymax = Math.max(dados.y_max ?? -Infinity, ...ys);
  const x0 = MARGEM.esq;
  const x1 = LARGURA - MARGEM.dir;
  const y0 = ALTURA - MARGEM.base;
  const y1 = MARGEM.topo;
  const tky = ticks(ymin, ymax);
  const tkx = ticks(xmin, xmax);
  const ex = escalaLinear(Math.min(xmin, tkx[0]), Math.max(xmax, tkx[tkx.length - 1]), x0, x1);
  const ey = escalaLinear(Math.min(ymin, tky[0]), Math.max(ymax, tky[tky.length - 1]), y0, y1);
  const filhos = [eixoY(ey, tky, x0, x1)];
  for (const v of tkx) filhos.push(texto(ex(v), y0 + 12, formatarNumero(v), { class: 'eixo', 'text-anchor': 'middle', 'font-size': '8' }));
  // todos os pontos num só <path> de traços de comprimento zero com ponta redonda: ~14 bytes por ponto,
  // contra ~75 de um <circle> — é o que mantém 1.500 pontos dentro dos 40 kB
  const d = pts.map((p) => `M${r2(ex(p.x))} ${r2(ey(p.y))}h.01`).join('');
  filhos.push(no('path', { d, class: 'pontos', stroke: CORES[2], 'stroke-width': pts.length > 800 ? 2 : 3, 'stroke-linecap': 'round',
    'stroke-opacity': '.7', fill: 'none', 'data-pontos': String(pts.length) }));
  const reg = dados.regressao;
  if (reg) {
    const xa = Math.min(xmin, tkx[0]);
    const xb = Math.max(xmax, tkx[tkx.length - 1]);
    filhos.push(no('line', { x1: r2(ex(xa)), y1: r2(ey(reg.a * xa + reg.b)), x2: r2(ex(xb)), y2: r2(ey(reg.a * xb + reg.b)),
      stroke: CORES[0], 'stroke-width': 1.5, class: 'regressao', 'data-a': String(reg.a), 'data-b': String(reg.b), 'data-r2': String(reg.r2) }));
    const eq = `y = ${formatarNumero(reg.a, 4)}·x ${reg.b < 0 ? '−' : '+'} ${formatarNumero(Math.abs(reg.b), 4)} · r² = ${reg.r2 === null ? '—' : reg.r2.toFixed(4)} · n = ${formatarNumero(reg.n)}`;
    filhos.push(texto(x1, y1 + 2, eq, { class: 'rot', 'text-anchor': 'end', 'font-size': '8' }));
  }
  if (dados.amostra || passo > 1) filhos.push(texto(x0, y1 + 2, `amostra de ${formatarNumero(pts.length)} pontos`, { class: 'eixo', 'font-size': '8' }));
  return raiz(filhos, opcoes.titulo);
}

const DESENHOS = { barras, histograma: barras, pizza, linha, dispersao };

export function desenhar(dados, opcoes = {}) {
  const f = DESENHOS[dados.tipo];
  if (!f) throw new Error(`tipo de gráfico sem desenho: ${dados.tipo}`);
  return f(dados, { mensagemVazio: 'sem valores para desenhar', titulo: `gráfico de ${dados.tipo}`, ...opcoes });
}

/* ------------------------------------------------------------------ tabela oculta e CSV, dos mesmos dados */
export function tabela(dados, opcoes = {}) {
  const gran = dados.granularidade || opcoes.granularidade;
  if (dados.tipo === 'dispersao') {
    const linhas = dados.series.map((p) => [p.x, p.y]);
    return { cabecalho: [dados.campo, dados.campo_y], linhas, rodape: dados.regressao
      ? [['a', dados.regressao.a], ['b', dados.regressao.b], ['r2', dados.regressao.r2], ['n', dados.regressao.n]] : [] };
  }
  if (dados.tipo === 'histograma') {
    return { cabecalho: ['de', 'ate', 'n'], linhas: dados.series.map((e) => [e.de, e.ate, e.n]), rodape: [['nulos', dados.nulos]] };
  }
  const valorNome = dados.estatistica === 'count' ? 'n' : `${dados.estatistica}_${dados.campo_y}`;
  const linhas = serieComOutros(dados).map((e) => [e.outros ? `outros (${e.categorias})` : (e.chave === null ? null : (dados.tipo === 'linha' ? rotuloData(String(e.chave), gran) : e.chave)), e.n, e.valor]);
  return { cabecalho: [dados.campo, 'n', valorNome], linhas, rodape: [['total', dados.total], ['nulos', dados.nulos]] };
}

export function csv(dados, opcoes = {}) {
  const t = tabela(dados, opcoes);
  const cel = (v) => {
    if (v === null || v === undefined) return '';
    const s = typeof v === 'number' ? String(v).replace('.', ',') : String(v);
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const linhas = [t.cabecalho.map(cel).join(';'), ...t.linhas.map((l) => l.map(cel).join(';'))];
  for (const [k, v] of t.rodape) linhas.push(`${cel(k)};${cel(v)}`);
  return `﻿${linhas.join('\r\n')}\r\n`;
}

/* ------------------------------------------------------------------ serialização em texto (teste no node e PNG) */
function escapar(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* árvore virtual -> DOM SVG real (sem innerHTML: nada de texto do dado vira marcação) */
export function paraDom(arvore, doc = (typeof document !== 'undefined' ? document : null)) {
  const NS = 'http://www.w3.org/2000/svg';
  if (typeof arvore === 'string') return doc.createTextNode(arvore);
  const el = doc.createElementNS(NS, arvore.tag);
  for (const [k, v] of Object.entries(arvore.atrs || {})) el.setAttribute(k, String(v));
  for (const f of arvore.filhos || []) el.append(paraDom(f, doc));
  return el;
}

export function paraTexto(arvore) {
  if (typeof arvore === 'string') return escapar(arvore);
  const atrs = Object.entries(arvore.atrs || {}).map(([k, v]) => ` ${k}="${escapar(v)}"`).join('');
  const filhos = (arvore.filhos || []).map(paraTexto).join('');
  return `<${arvore.tag}${atrs}>${filhos}</${arvore.tag}>`;
}
