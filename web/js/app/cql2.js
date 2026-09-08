/* plat — CQL2-JSON no navegador (item L5-07-fontes-vistas-mensagens; L5_CONCEITO D4). O filtro de uma vista é
   CQL2-JSON (OGC 21-065r2): este módulo AVALIA um filtro sobre feições em memória (propriedades + geometria
   GeoJSON) e ACEITA CQL2-text na entrada, convertendo para JSON — o mesmo subconjunto que o servidor compila
   para SQL (app/consulta, L2-04-g): comparação (=, <>, <, <=, >, >=), and/or/not, in, like, between, isNull e
   s_intersects (por envelope; interseção exata de polígono é do servidor). Nenhum eval, nenhum acesso a rede;
   limites de tamanho para o adversário que manda um filtro gigante. */

export const MAX_TEXTO = 4000;
export const MAX_TOKENS = 400;
export const MAX_PROFUNDIDADE = 20;
export const OPERADORES = ['=', '<>', '<', '<=', '>', '>=', 'and', 'or', 'not', 'in', 'like', 'between', 'isNull', 's_intersects'];

export class ErroCql2 extends Error {
  constructor(codigo, mensagem, detalhe = null) { super(mensagem); this.codigo = codigo; this.detalhe = detalhe; }
}

const eProp = (x) => x && typeof x === 'object' && !Array.isArray(x) && typeof x.property === 'string';
const eGeom = (x) => x && typeof x === 'object' && typeof x.type === 'string' && ('coordinates' in x || x.type === 'GeometryCollection');

/* ---------------------------------------------------------------- validação estrutural (sem dado) */
export function validar(no, profundidade = 0, caminho = 'filtro') {
  if (profundidade > MAX_PROFUNDIDADE) throw new ErroCql2('profundidade', `${caminho}: filtro aninhado além de ${MAX_PROFUNDIDADE} níveis`);
  if (!no || typeof no !== 'object' || Array.isArray(no)) throw new ErroCql2('forma', `${caminho}: nó precisa ser um objeto {op, args}`);
  const { op, args } = no;
  if (!OPERADORES.includes(op)) throw new ErroCql2('operador', `${caminho}: operador desconhecido ${JSON.stringify(op)}`);
  if (!Array.isArray(args)) throw new ErroCql2('forma', `${caminho}: args precisa ser lista`);
  if (op === 'and' || op === 'or') {
    if (args.length < 1) throw new ErroCql2('forma', `${caminho}: ${op} exige ao menos um argumento`);
    args.forEach((a, i) => validar(a, profundidade + 1, `${caminho}.args.${i}`));
    return true;
  }
  if (op === 'not') {
    if (args.length !== 1) throw new ErroCql2('forma', `${caminho}: not exige um argumento`);
    validar(args[0], profundidade + 1, `${caminho}.args.0`);
    return true;
  }
  if (op === 'isNull') {
    if (args.length !== 1 || !eProp(args[0])) throw new ErroCql2('forma', `${caminho}: isNull exige uma propriedade`);
    return true;
  }
  if (op === 'between') {
    if (args.length !== 3 || !eProp(args[0])) throw new ErroCql2('forma', `${caminho}: between exige propriedade, mínimo e máximo`);
    return true;
  }
  if (op === 'in') {
    if (args.length !== 2 || !eProp(args[0]) || !Array.isArray(args[1])) throw new ErroCql2('forma', `${caminho}: in exige propriedade e lista`);
    if (args[1].length > 10000) throw new ErroCql2('tamanho', `${caminho}: lista do in acima de 10000 valores`);
    return true;
  }
  if (op === 's_intersects') {
    if (args.length !== 2 || !eProp(args[0]) || !eGeom(args[1])) throw new ErroCql2('forma', `${caminho}: s_intersects exige propriedade e geometria`);
    return true;
  }
  if (args.length !== 2 || !(eProp(args[0]) || eProp(args[1]))) throw new ErroCql2('forma', `${caminho}: ${op} exige uma propriedade e um valor`);
  return true;
}

/* propriedades citadas pelo filtro (para o validador de tipos do modelo) */
export function propriedades(no, saida = new Set()) {
  if (!no || typeof no !== 'object') return saida;
  for (const a of no.args || []) {
    if (eProp(a)) saida.add(a.property);
    else if (a && typeof a === 'object' && 'op' in a) propriedades(a, saida);
  }
  return saida;
}

/* ---------------------------------------------------------------- avaliação sobre uma feição */
function valorDe(arg, feicao) {
  if (eProp(arg)) return arg.property === '__id' ? feicao.id : feicao.propriedades?.[arg.property];
  if (arg && typeof arg === 'object' && arg.timestamp) return Date.parse(arg.timestamp);
  if (arg && typeof arg === 'object' && arg.date) return Date.parse(arg.date);
  return arg;
}

function comparar(a, b) {
  if (a === null || a === undefined || b === null || b === undefined) return null;
  if (typeof a === 'number' && typeof b === 'string' && b !== '' && !Number.isNaN(Number(b))) b = Number(b);
  if (typeof b === 'number' && typeof a === 'string' && a !== '' && !Number.isNaN(Number(a))) a = Number(a);
  if (typeof a !== typeof b) { a = String(a); b = String(b); }
  return a < b ? -1 : (a > b ? 1 : 0);
}

function like(valor, padrao) {
  if (valor === null || valor === undefined) return false;
  const re = '^' + String(padrao).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/%/g, '.*').replace(/_/g, '.') + '$';
  return new RegExp(re, 'i').test(String(valor));
}

export function envelope(geometria) {
  if (!geometria) return null;
  let xmin = Infinity; let ymin = Infinity; let xmax = -Infinity; let ymax = -Infinity;
  const visita = (c) => {
    if (typeof c[0] === 'number') { xmin = Math.min(xmin, c[0]); xmax = Math.max(xmax, c[0]); ymin = Math.min(ymin, c[1]); ymax = Math.max(ymax, c[1]); return; }
    for (const f of c) visita(f);
  };
  if (geometria.type === 'GeometryCollection') for (const g of geometria.geometries || []) { const e = envelope(g); if (e) { xmin = Math.min(xmin, e[0]); ymin = Math.min(ymin, e[1]); xmax = Math.max(xmax, e[2]); ymax = Math.max(ymax, e[3]); } }
  else if (geometria.coordinates) visita(geometria.coordinates);
  if (xmin === Infinity) return null;
  return [xmin, ymin, xmax, ymax];
}

export function envelopesCruzam(a, b) {
  return !!a && !!b && a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];
}

export function avaliar(no, feicao) {
  const { op, args } = no;
  switch (op) {
    case 'and': return args.every((a) => avaliar(a, feicao));
    case 'or': return args.some((a) => avaliar(a, feicao));
    case 'not': return !avaliar(args[0], feicao);
    case 'isNull': { const v = valorDe(args[0], feicao); return v === null || v === undefined; }
    case 'in': { const v = valorDe(args[0], feicao); return args[1].some((x) => comparar(v, valorDe(x, feicao)) === 0); }
    case 'like': return like(valorDe(args[0], feicao), valorDe(args[1], feicao));
    case 'between': { const v = valorDe(args[0], feicao); const c1 = comparar(v, valorDe(args[1], feicao)); const c2 = comparar(v, valorDe(args[2], feicao)); return c1 !== null && c2 !== null && c1 >= 0 && c2 <= 0; }
    case 's_intersects': { const g = eProp(args[0]) ? feicao.geometria : args[0]; return envelopesCruzam(envelope(g), envelope(args[1])); }
    default: {
      const c = comparar(valorDe(args[0], feicao), valorDe(args[1], feicao));
      if (c === null) return false;
      return { '=': c === 0, '<>': c !== 0, '<': c < 0, '<=': c <= 0, '>': c > 0, '>=': c >= 0 }[op];
    }
  }
}

/* compila uma vez (valida) e devolve um predicado reutilizável */
export function predicado(filtro) {
  if (!filtro) return () => true;
  validar(filtro);
  return (feicao) => avaliar(filtro, feicao);
}

/* ---------------------------------------------------------------- CQL2-text -> CQL2-JSON (subconjunto)
   expr := termo (OR termo)* ; termo := fator (AND fator)* ; fator := NOT fator | '(' expr ')' | comparacao
   comparacao := ident ( IS [NOT] NULL | IN '(' lit {, lit} ')' | [NOT] LIKE lit | BETWEEN lit AND lit | op lit ) */
function tokenizar(texto) {
  if (typeof texto !== 'string') throw new ErroCql2('forma', 'filtro em texto precisa ser string');
  if (texto.length > MAX_TEXTO) throw new ErroCql2('tamanho', `filtro acima de ${MAX_TEXTO} caracteres`);
  const re = /\s*(?:('(?:[^']|'')*')|(-?\d+(?:\.\d+)?)|(<=|>=|<>|!=|=|<|>|\(|\)|,)|([A-Za-z_][A-Za-z0-9_]*))/y;
  const tokens = [];
  let i = 0;
  while (i < texto.length) {
    re.lastIndex = i;
    const m = re.exec(texto);
    if (!m || m.index !== i) {
      if (/^\s*$/.test(texto.slice(i))) break;
      throw new ErroCql2('sintaxe', `caractere inesperado na posição ${i}`, { posicao: i });
    }
    if (m[1] !== undefined) tokens.push({ t: 'str', v: m[1].slice(1, -1).replace(/''/g, "'") });
    else if (m[2] !== undefined) tokens.push({ t: 'num', v: Number(m[2]) });
    else if (m[3] !== undefined) tokens.push({ t: 'op', v: m[3] === '!=' ? '<>' : m[3] });
    else tokens.push({ t: 'id', v: m[4] });
    i = re.lastIndex;
    if (tokens.length > MAX_TOKENS) throw new ErroCql2('tamanho', `filtro acima de ${MAX_TOKENS} termos`);
  }
  return tokens;
}

export function analisarTexto(texto) {
  const tk = tokenizar(texto);
  let p = 0;
  const olhar = () => tk[p];
  const palavra = (w) => olhar() && olhar().t === 'id' && olhar().v.toLowerCase() === w;
  const comer = (t, v) => { const x = tk[p]; if (!x || x.t !== t || (v !== undefined && String(x.v).toLowerCase() !== v)) throw new ErroCql2('sintaxe', `esperado ${v ?? t} na posição do termo ${p}`, { termo: p }); p += 1; return x; };
  const literal = () => { const x = olhar(); if (!x || (x.t !== 'str' && x.t !== 'num')) throw new ErroCql2('sintaxe', `esperado valor no termo ${p}`); p += 1; return x.v; };
  let profundidade = 0;
  function expr() { const termos = [termo()]; while (palavra('or')) { p += 1; termos.push(termo()); } return termos.length === 1 ? termos[0] : { op: 'or', args: termos }; }
  function termo() { const fs = [fator()]; while (palavra('and')) { p += 1; fs.push(fator()); } return fs.length === 1 ? fs[0] : { op: 'and', args: fs }; }
  function fator() {
    if (palavra('not')) { p += 1; return { op: 'not', args: [fator()] }; }
    if (olhar() && olhar().t === 'op' && olhar().v === '(') {
      p += 1; profundidade += 1;
      if (profundidade > MAX_PROFUNDIDADE) throw new ErroCql2('profundidade', 'parênteses além do limite');
      const e = expr(); comer('op', '('.replace('(', ')')); profundidade -= 1; return e;
    }
    const campo = comer('id').v;
    const prop = { property: campo };
    if (palavra('is')) { p += 1; let neg = false; if (palavra('not')) { p += 1; neg = true; } comer('id', 'null'); const n = { op: 'isNull', args: [prop] }; return neg ? { op: 'not', args: [n] } : n; }
    if (palavra('in')) { p += 1; comer('op', '('); const lista = [literal()]; while (olhar() && olhar().t === 'op' && olhar().v === ',') { p += 1; lista.push(literal()); } comer('op', ')'); return { op: 'in', args: [prop, lista] }; }
    let neg = false;
    if (palavra('not')) { p += 1; neg = true; }
    if (palavra('like')) { p += 1; const n = { op: 'like', args: [prop, literal()] }; return neg ? { op: 'not', args: [n] } : n; }
    if (palavra('between')) { p += 1; const a = literal(); comer('id', 'and'); const b = literal(); const n = { op: 'between', args: [prop, a, b] }; return neg ? { op: 'not', args: [n] } : n; }
    if (neg) throw new ErroCql2('sintaxe', `NOT sem LIKE/BETWEEN no termo ${p}`);
    const op = comer('op').v;
    if (!['=', '<>', '<', '<=', '>', '>='].includes(op)) throw new ErroCql2('sintaxe', `operador inválido ${op}`);
    return { op, args: [prop, literal()] };
  }
  if (!tk.length) throw new ErroCql2('sintaxe', 'filtro vazio');
  const arvore = expr();
  if (p !== tk.length) throw new ErroCql2('sintaxe', `sobra de texto a partir do termo ${p}`, { termo: p });
  validar(arvore);
  return arvore;
}

/* texto ou JSON: sempre devolve JSON validado (ou null para vazio) */
export function normalizar(filtro) {
  if (filtro === null || filtro === undefined || filtro === '') return null;
  if (typeof filtro === 'string') return analisarTexto(filtro);
  validar(filtro);
  return filtro;
}
