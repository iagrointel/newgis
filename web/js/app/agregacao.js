/* plat — agregação e exportação em memória (item L5-01-c). Só o que o navegador faz sobre REGISTROS JÁ
   CARREGADOS (fonte embutida/arquivo/URL ou a janela em cache de uma fonte de servidor). Para fonte de camada
   a agregação é do servidor (FeatureServer `outStatistics`, consulta.js) — L5_CONCEITO D21: nunca agregar no
   navegador sobre a camada inteira. Funções puras, sem DOM, testadas em Node (tests/app/executar_js.mjs). */

export const AGREGACOES = Object.freeze(['contagem', 'soma', 'media', 'minimo', 'maximo']);

export function agregarEmMemoria(registros, { campo, agregacao = 'contagem', campo_valor = null, maximo = 20 }) {
  const grupos = new Map();
  for (const f of registros) {
    const chave = f.propriedades?.[campo];
    const nome = chave === null || chave === undefined ? null : chave;
    const g = grupos.get(nome) || { valor: nome, n: 0, soma: 0, minimo: null, maximo: null, ids: [] };
    g.n += 1; g.ids.push(f.id);
    const v = campo_valor ? Number(f.propriedades?.[campo_valor]) : NaN;
    if (!Number.isNaN(v)) {
      g.soma += v;
      g.minimo = g.minimo === null ? v : Math.min(g.minimo, v);
      g.maximo = g.maximo === null ? v : Math.max(g.maximo, v);
    }
    grupos.set(nome, g);
  }
  const linhas = [...grupos.values()].map((g) => ({ ...g, medida: medidaDe(g, agregacao) }));
  linhas.sort((a, b) => (b.medida ?? -Infinity) - (a.medida ?? -Infinity));
  return maximo ? linhas.slice(0, maximo) : linhas;
}

function medidaDe(g, agregacao) {
  if (agregacao === 'soma') return g.soma;
  if (agregacao === 'media') return g.n ? g.soma / g.n : null;
  if (agregacao === 'minimo') return g.minimo;
  if (agregacao === 'maximo') return g.maximo;
  return g.n;
}

/* faixas iguais entre min e max; devolve [{de, ate, n}] */
export function histogramaEmMemoria(registros, { campo, faixas = 10 }) {
  const valores = registros.map((f) => Number(f.propriedades?.[campo])).filter((v) => !Number.isNaN(v));
  return histogramaDeValores(valores, faixas);
}

export function histogramaDeValores(valores, faixas = 10) {
  if (!valores.length) return [];
  const min = Math.min(...valores); const max = Math.max(...valores);
  return contarFaixas(valores, faixasEntre(min, max, faixas));
}

export function faixasEntre(min, max, n = 10) {
  const largura = (max - min) / n || 1;
  const faixas = [];
  for (let i = 0; i < n; i += 1) faixas.push({ de: min + i * largura, ate: i === n - 1 ? max : min + (i + 1) * largura, n: 0 });
  return faixas;
}

export function contarFaixas(valores, faixas) {
  for (const v of valores) {
    const i = faixas.findIndex((fx, k) => v >= fx.de && (v < fx.ate || (k === faixas.length - 1 && v <= fx.ate)));
    if (i >= 0) faixas[i].n += 1;
  }
  return faixas;
}

/* CSV (RFC 4180, separador vírgula, UTF-8 com BOM para planilha em pt-BR abrir com acento) */
export function paraCsv(linhas, colunas) {
  const cols = colunas && colunas.length ? colunas : Object.keys(linhas[0] || {}).filter((k) => k !== '__id').map((k) => ({ campo: k, rotulo: k }));
  const celula = (v) => {
    if (v === null || v === undefined) return '';
    const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const cabecalho = cols.map((c) => celula(c.rotulo || c.campo)).join(',');
  const corpo = linhas.map((l) => cols.map((c) => celula(l[c.campo])).join(','));
  return '﻿' + [cabecalho, ...corpo].join('\r\n') + '\r\n';
}

export function paraGeoJson(feicoes) {
  return {
    type: 'FeatureCollection',
    features: feicoes.map((f) => {
      const { __id, ...props } = f.propriedades || {};
      return { type: 'Feature', id: f.id, properties: props, geometry: f.geometria || null };
    }),
  };
}

/* modelo de texto dos cartões e da informação da feição: `{campo}` vira o valor; `{= expressão }` (campos como `$campo`, gramática do docs/EXPRESSAO.md) é avaliada
   pela linguagem de expressão (L2-10-c) quando o avaliador for fornecido; campo inexistente vira vazio */
export function preencherModelo(modelo, propriedades, avaliar = null) {
  return String(modelo || '').replace(/\{(=?)([^{}]+)\}/g, (_, sinal, corpo) => {
    if (sinal === '=') {
      if (!avaliar) return '';
      try { const v = avaliar(corpo.trim(), propriedades); return v === null || v === undefined ? '' : String(v); } catch { return ''; }
    }
    const v = propriedades?.[corpo.trim()];
    return v === null || v === undefined ? '' : String(v);
  });
}
