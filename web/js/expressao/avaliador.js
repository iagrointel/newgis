/* plat · linguagem de expressão própria (item L2-10-c-linguagem-expressao) — MESMO analisador/
   avaliador de `app/expressao/avaliador_py.py`, escrito à mão, sem `eval`/`new Function`/`Function`
   dinâmico. Gramática publicada em `docs/EXPRESSAO.md`; os dois avaliadores têm de concordar byte a
   byte para o mesmo texto + mesmo contexto (é o que `tests/expressoes/vetores.json` prova, com
   `executar_js.mjs` chamando exatamente as funções exportadas aqui).

   Puro (sem DOM, sem import de outro módulo do app): roda tanto no navegador quanto no Node de
   teste. `$campo` só lê do `contexto` que quem chama passa — nunca acessa propriedade de objeto
   arbitrário (sem `obj[nome]` fora do dicionário de contexto, sem protótipo, sem `window`/`globalThis`). */

// ---------------------------------------------------------------- limites (negação-de-serviço)
export const MAX_TEXTO = 20_000;
export const MAX_TOKENS = 2_000;
export const MAX_PROFUNDIDADE = 60;
export const MAX_ARGUMENTOS = 64;
export const MAX_PASSOS_PADRAO = 100_000;
export const LIMITE_MS_CLIENTE = 50; // orçamento do cliente (o servidor usa 500 ms, ver avaliador_py.py)

const OPERADORES = ['<=', '>=', '==', '!=', '&&', '||', '<', '>', '+', '-', '*', '/', '%', '^', '!'];
const PALAVRAS_CHAVE = new Set(['verdadeiro', 'falso', 'nulo']);

export class ErroExpressao extends Error {
  constructor(codigo, mensagem, detalhe) {
    super(mensagem);
    this.codigo = codigo;
    this.mensagem = mensagem;
    this.detalhe = detalhe === undefined ? null : detalhe;
  }
}

// =================================================================== 1. tokenizador
function linhaColuna(texto, posicao) {
  const ate = texto.slice(0, posicao);
  const linha = (ate.match(/\n/g) || []).length + 1;
  const ultimaQuebra = ate.lastIndexOf('\n');
  const coluna = ultimaQuebra >= 0 ? posicao - ultimaQuebra : posicao + 1;
  return { linha, coluna };
}

function ehDigito(c) {
  return c >= '0' && c <= '9';
}
function ehLetra(c) {
  return /[A-Za-z_]/.test(c);
}
function ehAlfanumerico(c) {
  return /[A-Za-z0-9_]/.test(c);
}

function tokenizar(texto) {
  const tokens = [];
  let i = 0;
  const n = texto.length;
  while (i < n) {
    const c = texto[i];
    if (/\s/.test(c)) { i += 1; continue; }
    if (c === '(') { tokens.push({ tipo: '(', posicao: i }); i += 1; continue; }
    if (c === ')') { tokens.push({ tipo: ')', posicao: i }); i += 1; continue; }
    if (c === ',') { tokens.push({ tipo: ',', posicao: i }); i += 1; continue; }
    if (c === "'") {
      let j = i + 1;
      let partes = '';
      let fechou = false;
      while (j < n) {
        const k = texto.indexOf("'", j);
        if (k < 0) break;
        partes += texto.slice(j, k);
        if (k + 1 < n && texto[k + 1] === "'") { partes += "'"; j = k + 2; continue; }
        j = k + 1; fechou = true; break;
      }
      if (!fechou) {
        const { linha, coluna } = linhaColuna(texto, i);
        throw new ErroExpressao('sintaxe_invalida', 'texto sem aspa de fechamento', { linha, coluna });
      }
      tokens.push({ tipo: 'string', valor: partes, posicao: i });
      i = j;
      continue;
    }
    if (c === '$') {
      const j = i + 1;
      if (j >= n || !ehLetra(texto[j])) {
        const { linha, coluna } = linhaColuna(texto, i);
        throw new ErroExpressao('sintaxe_invalida', "'$' precisa ser seguido de nome de campo", { linha, coluna });
      }
      let k = j;
      while (k < n && ehAlfanumerico(texto[k])) k += 1;
      tokens.push({ tipo: 'campo', valor: texto.slice(j, k), posicao: i });
      i = k;
      continue;
    }
    const opCasado = OPERADORES.find((op) => texto.startsWith(op, i));
    if (opCasado) {
      tokens.push({ tipo: 'op', valor: opCasado, posicao: i });
      i += opCasado.length;
      continue;
    }
    if (ehDigito(c) || (c === '.' && i + 1 < n && ehDigito(texto[i + 1]))) {
      let j = i;
      while (j < n && ehDigito(texto[j])) j += 1;
      let ehFloat = false;
      if (j < n && texto[j] === '.' && j + 1 < n && ehDigito(texto[j + 1])) {
        ehFloat = true;
        j += 1;
        while (j < n && ehDigito(texto[j])) j += 1;
      }
      const bruto = texto.slice(i, j);
      tokens.push({ tipo: 'numero', valor: Number(bruto), ehFloat, posicao: i });
      i = j;
      continue;
    }
    if (ehLetra(c)) {
      let j = i;
      while (j < n && ehAlfanumerico(texto[j])) j += 1;
      const palavra = texto.slice(i, j);
      const baixa = palavra.toLowerCase();
      if (PALAVRAS_CHAVE.has(baixa)) tokens.push({ tipo: baixa, posicao: i });
      else tokens.push({ tipo: 'ident', valor: palavra, posicao: i });
      i = j;
      continue;
    }
    const { linha, coluna } = linhaColuna(texto, i);
    throw new ErroExpressao('caractere_invalido', `caractere não reconhecido: '${c}'`, { linha, coluna });
  }
  return tokens;
}

// =================================================================== 2. AST tipada (objetos simples)
// Literal: {no:'literal', tipoValor, valor}; Campo: {no:'campo', nome}
// Unario: {no:'unario', operador, operando}; Binario: {no:'binario', operador, esquerda, direita}
// Chamada: {no:'chamada', nome, argumentos:[...]}

const PREC_OU = new Set(['||']);
const PREC_E = new Set(['&&']);
const PREC_IGUALDADE = new Set(['==', '!=']);
const PREC_COMPARACAO = new Set(['<', '<=', '>', '>=']);
const PREC_ADITIVA = new Set(['+', '-']);
const PREC_MULTIPLICATIVA = new Set(['*', '/', '%']);
const PREC_POTENCIA = new Set(['^']);

class Parser {
  constructor(tokens, texto) {
    this.t = tokens;
    this.i = 0;
    this.texto = texto;
  }
  olha() { return this.i < this.t.length ? this.t[this.i] : null; }
  erroPosicao(posicao) { return linhaColuna(this.texto, posicao); }
  espera(tipo) {
    const tok = this.olha();
    const posicao = tok ? tok.posicao : this.texto.length;
    if (!tok || tok.tipo !== tipo) {
      throw new ErroExpressao(
        'sintaxe_invalida',
        `esperava '${tipo}'` + (tok ? `, obtive '${tok.tipo}'` : ', a expressão terminou antes'),
        { ...this.erroPosicao(posicao), esperado: tipo, obtido: tok ? tok.tipo : null },
      );
    }
    this.i += 1;
    return tok;
  }
  profundidadeOk(p, posicao) {
    if (p > MAX_PROFUNDIDADE) {
      throw new ErroExpressao(
        'profundidade_excedida',
        `aninhamento acima de ${MAX_PROFUNDIDADE}`,
        { ...this.erroPosicao(posicao), limite: MAX_PROFUNDIDADE },
      );
    }
  }
  analisarTudo() {
    const no = this.ou(0);
    const sobra = this.olha();
    if (sobra !== null) {
      throw new ErroExpressao('sintaxe_invalida', 'texto após o fim da expressão', this.erroPosicao(sobra.posicao));
    }
    return no;
  }
  ou(p) {
    this.profundidadeOk(p, this.i < this.t.length ? this.t[this.i].posicao : this.texto.length);
    let esquerda = this.e(p + 1);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_OU.has(tok.valor)) {
      this.i += 1;
      const direita = this.e(p + 1);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  e(p) {
    let esquerda = this.igualdade(p);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_E.has(tok.valor)) {
      this.i += 1;
      const direita = this.igualdade(p);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  igualdade(p) {
    let esquerda = this.comparacao(p);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_IGUALDADE.has(tok.valor)) {
      this.i += 1;
      const direita = this.comparacao(p);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  comparacao(p) {
    let esquerda = this.aditiva(p);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_COMPARACAO.has(tok.valor)) {
      this.i += 1;
      const direita = this.aditiva(p);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  aditiva(p) {
    let esquerda = this.multiplicativa(p);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_ADITIVA.has(tok.valor)) {
      this.i += 1;
      const direita = this.multiplicativa(p);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  multiplicativa(p) {
    let esquerda = this.potencia(p);
    let tok;
    while ((tok = this.olha()) !== null && tok.tipo === 'op' && PREC_MULTIPLICATIVA.has(tok.valor)) {
      this.i += 1;
      const direita = this.potencia(p);
      esquerda = { no: 'binario', operador: tok.valor, esquerda, direita };
    }
    return esquerda;
  }
  potencia(p) {
    const esquerda = this.unario(p);
    const tok = this.olha();
    if (tok !== null && tok.tipo === 'op' && PREC_POTENCIA.has(tok.valor)) {
      this.i += 1;
      const direita = this.potencia(p); // associatividade à direita
      return { no: 'binario', operador: '^', esquerda, direita };
    }
    return esquerda;
  }
  unario(p) {
    const tok = this.olha();
    if (tok !== null && tok.tipo === 'op' && (tok.valor === '-' || tok.valor === '!')) {
      this.profundidadeOk(p + 1, tok.posicao);
      this.i += 1;
      const operando = this.unario(p + 1);
      return { no: 'unario', operador: tok.valor, operando };
    }
    return this.primario(p);
  }
  primario(p) {
    const tok = this.olha();
    if (tok === null) {
      throw new ErroExpressao('sintaxe_invalida', 'expressão incompleta', this.erroPosicao(this.texto.length));
    }
    if (tok.tipo === 'numero') { this.i += 1; return { no: 'literal', tipoValor: 'numero', valor: tok.valor }; }
    if (tok.tipo === 'string') { this.i += 1; return { no: 'literal', tipoValor: 'texto', valor: tok.valor }; }
    if (tok.tipo === 'verdadeiro') { this.i += 1; return { no: 'literal', tipoValor: 'booleano', valor: true }; }
    if (tok.tipo === 'falso') { this.i += 1; return { no: 'literal', tipoValor: 'booleano', valor: false }; }
    if (tok.tipo === 'nulo') { this.i += 1; return { no: 'literal', tipoValor: 'nulo', valor: null }; }
    if (tok.tipo === 'campo') { this.i += 1; return { no: 'campo', nome: tok.valor }; }
    if (tok.tipo === '(') {
      this.profundidadeOk(p + 1, tok.posicao);
      this.i += 1;
      const no = this.ou(p + 1);
      this.espera(')');
      return no;
    }
    if (tok.tipo === 'ident') {
      const nome = tok.valor;
      this.i += 1;
      this.espera('(');
      this.profundidadeOk(p + 1, tok.posicao);
      const argumentos = [];
      let prox = this.olha();
      if (prox !== null && prox.tipo !== ')') {
        argumentos.push(this.ou(p + 1));
        let t2;
        while ((t2 = this.olha()) !== null && t2.tipo === ',') {
          this.i += 1;
          if (argumentos.length >= MAX_ARGUMENTOS) {
            throw new ErroExpressao(
              'expressao_grande',
              `mais de ${MAX_ARGUMENTOS} argumentos em '${nome}'`,
              { ...this.erroPosicao(t2.posicao), funcao: nome },
            );
          }
          argumentos.push(this.ou(p + 1));
        }
      }
      this.espera(')');
      return { no: 'chamada', nome, argumentos };
    }
    throw new ErroExpressao('sintaxe_invalida', `token inesperado: '${tok.tipo}'`, this.erroPosicao(tok.posicao));
  }
}

// mesma defesa dupla do lado Python (avaliador_py.py, `_profundidade_da_arvore`): uma cadeia longa
// do MESMO operador ("1+1+1+...+1") é montada por um laço do parser (não recursa por termo, então
// o contador de descida nunca dispara) mas gera uma árvore tão funda quanto o número de termos —
// sem medir a árvore de novo com pilha própria (nunca recursão), o avaliador (que É recursivo em
// `v()`) estouraria a pilha do motor JS na mesma cadeia.
function profundidadeDaArvore(no) {
  const pilha = [[no, 1]];
  let maior = 0;
  while (pilha.length) {
    const [atual, profundidade] = pilha.pop();
    if (profundidade > maior) maior = profundidade;
    if (profundidade > MAX_PROFUNDIDADE * 4) return profundidade; // corta cedo
    if (atual.no === 'unario') pilha.push([atual.operando, profundidade + 1]);
    else if (atual.no === 'binario') {
      pilha.push([atual.esquerda, profundidade + 1]);
      pilha.push([atual.direita, profundidade + 1]);
    } else if (atual.no === 'chamada') {
      for (const a of atual.argumentos) pilha.push([a, profundidade + 1]);
    }
  }
  return maior;
}

export function analisar(texto) {
  texto = texto === null || texto === undefined ? '' : texto;
  if (texto.trim() === '') throw new ErroExpressao('expressao_vazia', 'expressão vazia');
  if (texto.length > MAX_TEXTO) {
    throw new ErroExpressao('expressao_grande', `expressão maior que ${MAX_TEXTO} caracteres`, { limite: MAX_TEXTO });
  }
  const tokens = tokenizar(texto);
  if (tokens.length > MAX_TOKENS) {
    throw new ErroExpressao('expressao_grande', `expressão com mais de ${MAX_TOKENS} tokens`, { limite: MAX_TOKENS });
  }
  const no = new Parser(tokens, texto).analisarTudo();
  const profundidade = profundidadeDaArvore(no);
  if (profundidade > MAX_PROFUNDIDADE) {
    throw new ErroExpressao(
      'profundidade_excedida',
      `árvore da expressão acima de ${MAX_PROFUNDIDADE} níveis (${profundidade})`,
      { limite: MAX_PROFUNDIDADE, medido: profundidade },
    );
  }
  return no;
}

// =================================================================== 3. AST ↔ JSON
export function astParaJson(no) {
  if (no.no === 'literal') return { tipo: 'literal', tipo_valor: no.tipoValor, valor: no.valor };
  if (no.no === 'campo') return { tipo: 'campo', nome: no.nome };
  if (no.no === 'unario') return { tipo: 'unario', operador: no.operador, operando: astParaJson(no.operando) };
  if (no.no === 'binario') {
    return {
      tipo: 'binario', operador: no.operador,
      esquerda: astParaJson(no.esquerda), direita: astParaJson(no.direita),
    };
  }
  if (no.no === 'chamada') {
    return { tipo: 'chamada', nome: no.nome, argumentos: no.argumentos.map(astParaJson) };
  }
  throw new ErroExpressao('no_desconhecido', 'nó de AST fora dos tipos esperados');
}

// entrada NÃO CONFIÁVEL da mesma classe que o texto (mesmo comentário de avaliador_py.py): aplica
// os MESMOS limites de profundidade e aridade que `analisar` aplica ao texto, para um JSON
// fabricado à mão não contornar os dois guarda-corpos do lado texto.
export function astDeJson(d, profundidade = 1) {
  if (profundidade > MAX_PROFUNDIDADE) {
    throw new ErroExpressao('profundidade_excedida', `AST acima de ${MAX_PROFUNDIDADE} níveis`, { limite: MAX_PROFUNDIDADE });
  }
  if (typeof d !== 'object' || d === null || !('tipo' in d)) {
    throw new ErroExpressao('no_desconhecido', 'JSON de AST malformado');
  }
  if (d.tipo === 'literal') return { no: 'literal', tipoValor: d.tipo_valor, valor: d.valor ?? null };
  if (d.tipo === 'campo') return { no: 'campo', nome: d.nome };
  if (d.tipo === 'unario') {
    return { no: 'unario', operador: d.operador, operando: astDeJson(d.operando, profundidade + 1) };
  }
  if (d.tipo === 'binario') {
    return {
      no: 'binario', operador: d.operador,
      esquerda: astDeJson(d.esquerda, profundidade + 1), direita: astDeJson(d.direita, profundidade + 1),
    };
  }
  if (d.tipo === 'chamada') {
    const argumentos = d.argumentos || [];
    if (argumentos.length > MAX_ARGUMENTOS) {
      throw new ErroExpressao('expressao_grande', `mais de ${MAX_ARGUMENTOS} argumentos em '${d.nome}'`, { limite: MAX_ARGUMENTOS });
    }
    return { no: 'chamada', nome: d.nome, argumentos: argumentos.map((a) => astDeJson(a, profundidade + 1)) };
  }
  throw new ErroExpressao('no_desconhecido', `tipo de nó desconhecido: ${d.tipo}`);
}

// =================================================================== 4. avaliador
const DIA_MS = 86_400_000;

function ehNumero(v) { return typeof v === 'number' && !Number.isNaN(v); }
function tipoNome(v) {
  if (v === null || v === undefined) return 'nulo';
  if (typeof v === 'boolean') return 'booleano';
  if (ehNumero(v)) return 'numero';
  if (typeof v === 'string') return 'texto';
  return typeof v; // pragma: no cover
}

function formatarNumero(n) {
  if (Number.isInteger(n)) return String(n);
  let s = n.toFixed(6);
  s = s.replace(/0+$/, '').replace(/\.$/, '');
  return s;
}

function arredondarNumero(x, casas) {
  const fator = 10 ** casas;
  if (x >= 0) return Math.floor(x * fator + 0.5) / fator;
  return Math.ceil(x * fator - 0.5) / fator;
}

function diasDesdeEpoca(ms) {
  if (ms >= 0) return Math.floor(ms / DIA_MS);
  return -Math.floor((-ms + DIA_MS - 1) / DIA_MS);
}

function anoMesDiaUtc(ms) {
  const d = new Date(ms);
  return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()];
}

function exigirNumero(v, onde) {
  if (!ehNumero(v)) throw new ErroExpressao('tipo_invalido', `${onde} espera número, recebeu ${tipoNome(v)}`, { onde });
  return v;
}

// nome → [minArgs, maxArgs (null=variádico), descrição, exemplo] — mesmo conteúdo de TABELA_FUNCOES
// em avaliador_py.py (test_expressao_doc_sincronizada.py confere os dois contra docs/EXPRESSAO.md)
export const TABELA_FUNCOES = {
  Maiuscula: [1, 1], Minuscula: [1, 1], Concatenar: [1, null], Texto: [1, 1],
  Arredondar: [1, 2], Absoluto: [1, 1], Minimo: [1, null], Maximo: [1, null], Numero: [1, 1], Potencia: [2, 2],
  AgoraUTC: [0, 0], Ano: [1, 1], Mes: [1, 1], Dia: [1, 1], DiferencaDias: [2, 2],
  SeNulo: [2, 2], EhNulo: [1, 1],
  Se: [3, 3],
};

function chamarFuncao(nome, args) {
  if (!(nome in TABELA_FUNCOES)) {
    throw new ErroExpressao('funcao_desconhecida', `função desconhecida: ${nome}`, { nome });
  }
  const [minimo, maximo] = TABELA_FUNCOES[nome];
  if (args.length < minimo || (maximo !== null && args.length > maximo)) {
    const faixa = maximo === minimo ? `${minimo}` : (maximo !== null ? `${minimo}-${maximo}` : `≥${minimo}`);
    throw new ErroExpressao(
      'aridade_invalida', `${nome} espera ${faixa} argumento(s), recebeu ${args.length}`,
      { nome, recebido: args.length },
    );
  }
  switch (nome) {
    case 'Maiuscula':
      if (typeof args[0] !== 'string') throw new ErroExpressao('tipo_invalido', 'Maiuscula espera texto', {});
      return args[0].toUpperCase();
    case 'Minuscula':
      if (typeof args[0] !== 'string') throw new ErroExpressao('tipo_invalido', 'Minuscula espera texto', {});
      return args[0].toLowerCase();
    case 'Concatenar':
      return args.map((a) => {
        if (a === null || a === undefined) return '';
        if (typeof a === 'boolean') return a ? 'verdadeiro' : 'falso';
        if (typeof a === 'string') return a;
        if (ehNumero(a)) return formatarNumero(a);
        throw new ErroExpressao('tipo_invalido', 'Concatenar recebeu tipo não suportado', {});
      }).join('');
    case 'Texto': {
      const v0 = args[0];
      if (v0 === null || v0 === undefined) return '';
      if (typeof v0 === 'boolean') return v0 ? 'verdadeiro' : 'falso';
      if (typeof v0 === 'string') return v0;
      return formatarNumero(exigirNumero(v0, 'Texto'));
    }
    case 'Arredondar': {
      const casas = args.length === 2 ? Math.trunc(exigirNumero(args[1], 'Arredondar (casas)')) : 0;
      const valor = exigirNumero(args[0], 'Arredondar');
      const r = arredondarNumero(valor, casas);
      return Number.isInteger(r) ? r : r;
    }
    case 'Absoluto':
      return Math.abs(exigirNumero(args[0], 'Absoluto'));
    case 'Minimo':
      return Math.min(...args.map((a) => exigirNumero(a, 'Minimo')));
    case 'Maximo':
      return Math.max(...args.map((a) => exigirNumero(a, 'Maximo')));
    case 'Numero': {
      const v0 = args[0];
      if (ehNumero(v0)) return v0;
      if (typeof v0 === 'boolean') return v0 ? 1 : 0;
      if (typeof v0 === 'string') {
        const texto = v0.trim();
        if (/^-?\d+$/.test(texto)) return parseInt(texto, 10);
        if (/^-?\d+\.\d+$/.test(texto)) return parseFloat(texto);
        return null;
      }
      return null;
    }
    case 'Potencia':
      return exigirNumero(args[0], 'Potencia') ** exigirNumero(args[1], 'Potencia');
    case 'AgoraUTC':
      return Date.now();
    case 'Ano': case 'Mes': case 'Dia': {
      const ms = exigirNumero(args[0], nome);
      const [ano, mes, dia] = anoMesDiaUtc(ms);
      return { Ano: ano, Mes: mes, Dia: dia }[nome];
    }
    case 'DiferencaDias': {
      const a = exigirNumero(args[0], 'DiferencaDias');
      const b = exigirNumero(args[1], 'DiferencaDias');
      return diasDesdeEpoca(b) - diasDesdeEpoca(a);
    }
    case 'EhNulo':
      return args[0] === null || args[0] === undefined;
    default:
      throw new ErroExpressao('funcao_desconhecida', `função desconhecida: ${nome}`, { nome }); // pragma: no cover
  }
}

class Contador {
  constructor(limitePassos, limiteMs) {
    this.passos = 0;
    this.limitePassos = limitePassos;
    this.inicio = (typeof performance !== 'undefined' ? performance.now() : Date.now());
    this.limiteMs = limiteMs;
  }
  passo() {
    this.passos += 1;
    if (this.passos > this.limitePassos) {
      throw new ErroExpressao(
        'limite_passos', `avaliação acima de ${this.limitePassos} passos`, { limite: this.limitePassos },
      );
    }
    if (this.passos % 256 === 0) {
      const agora = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      const decorridoMs = agora - this.inicio;
      if (decorridoMs > this.limiteMs) {
        throw new ErroExpressao(
          'tempo_excedido', `avaliação acima de ${this.limiteMs} ms`, { limite_ms: this.limiteMs },
        );
      }
    }
  }
}

function exigirBooleanoOuNulo(valor, op) {
  if (valor !== null && valor !== undefined && typeof valor !== 'boolean') {
    throw new ErroExpressao('tipo_invalido', `'${op}' espera booleano ou nulo, recebeu ${tipoNome(valor)}`, { operador: op });
  }
}

function igual(a, b) {
  const aNulo = a === null || a === undefined;
  const bNulo = b === null || b === undefined;
  if (aNulo && bNulo) return true;
  if (aNulo || bNulo) return false;
  if (typeof a === 'boolean' || typeof b === 'boolean') return typeof a === 'boolean' && typeof b === 'boolean' && a === b;
  if (ehNumero(a) && ehNumero(b)) return a === b;
  if (typeof a === 'string' && typeof b === 'string') return a === b;
  return false;
}

/** AST → valor. `contexto` é a lista BRANCA de campos (nunca acesso a propriedade fora dela);
 * `limitePassos`/`limiteMs` cortam laço/recursão profunda com erro nomeado — o cliente chama com
 * `LIMITE_MS_CLIENTE` (50 ms), o servidor com 500 ms (avaliador_py.py). */
export function avaliar(no, contexto, opcoes) {
  contexto = contexto || {};
  const limitePassos = (opcoes && opcoes.limitePassos) || MAX_PASSOS_PADRAO;
  const limiteMs = (opcoes && opcoes.limiteMs) || LIMITE_MS_CLIENTE;
  const contador = new Contador(limitePassos, limiteMs);

  function v(nodo) {
    contador.passo();
    if (nodo.no === 'literal') return nodo.valor;
    if (nodo.no === 'campo') {
      if (!Object.prototype.hasOwnProperty.call(contexto, nodo.nome)) {
        throw new ErroExpressao('campo_nao_permitido', `campo não permitido: ${nodo.nome}`, { campo: nodo.nome });
      }
      return contexto[nodo.nome];
    }
    if (nodo.no === 'unario') {
      const operando = v(nodo.operando);
      if (nodo.operador === '-') {
        if (operando === null || operando === undefined) return null;
        return -exigirNumero(operando, 'operador unário -');
      }
      if (nodo.operador === '!') {
        if (operando === null || operando === undefined) return null;
        if (typeof operando !== 'boolean') throw new ErroExpressao('tipo_invalido', "operador '!' espera booleano", {});
        return !operando;
      }
      throw new ErroExpressao('operador_desconhecido', `operador unário desconhecido: ${nodo.operador}`); // pragma: no cover
    }
    if (nodo.no === 'binario') return binario(nodo);
    if (nodo.no === 'chamada') {
      if (nodo.nome === 'Se') {
        if (nodo.argumentos.length !== 3) throw new ErroExpressao('aridade_invalida', 'Se espera 3 argumentos', { nome: 'Se' });
        const cond = v(nodo.argumentos[0]);
        if (typeof cond !== 'boolean') {
          throw new ErroExpressao('tipo_invalido', `Se espera condição booleana, recebeu ${tipoNome(cond)}`, { nome: 'Se' });
        }
        return cond ? v(nodo.argumentos[1]) : v(nodo.argumentos[2]);
      }
      if (nodo.nome === 'SeNulo') {
        if (nodo.argumentos.length !== 2) throw new ErroExpressao('aridade_invalida', 'SeNulo espera 2 argumentos', { nome: 'SeNulo' });
        const primeiro = v(nodo.argumentos[0]);
        return (primeiro === null || primeiro === undefined) ? v(nodo.argumentos[1]) : primeiro;
      }
      const args = nodo.argumentos.map(v);
      return chamarFuncao(nodo.nome, args);
    }
    throw new ErroExpressao('no_desconhecido', 'nó de AST fora dos tipos esperados'); // pragma: no cover
  }

  function binario(nodo) {
    const op = nodo.operador;
    if (op === '&&') {
      const esquerda = v(nodo.esquerda);
      exigirBooleanoOuNulo(esquerda, '&&');
      if (esquerda === false) return false;
      const direita = v(nodo.direita);
      exigirBooleanoOuNulo(direita, '&&');
      if (direita === false) return false;
      if (esquerda === null || direita === null) return null;
      return true;
    }
    if (op === '||') {
      const esquerda = v(nodo.esquerda);
      exigirBooleanoOuNulo(esquerda, '||');
      if (esquerda === true) return true;
      const direita = v(nodo.direita);
      exigirBooleanoOuNulo(direita, '||');
      if (direita === true) return true;
      if (esquerda === null || direita === null) return null;
      return false;
    }
    const esquerda = v(nodo.esquerda);
    const direita = v(nodo.direita);
    if (op === '==') return igual(esquerda, direita);
    if (op === '!=') { const r = igual(esquerda, direita); return r === null ? null : !r; }
    if (op === '<' || op === '<=' || op === '>' || op === '>=') {
      if (esquerda === null || direita === null) return null;
      let a, b;
      if (ehNumero(esquerda) && ehNumero(direita)) { a = esquerda; b = direita; }
      else if (typeof esquerda === 'string' && typeof direita === 'string') { a = esquerda; b = direita; }
      else {
        throw new ErroExpressao(
          'tipo_invalido',
          `'${op}' espera dois números ou dois textos, recebeu ${tipoNome(esquerda)}/${tipoNome(direita)}`,
          { operador: op },
        );
      }
      if (op === '<') return a < b;
      if (op === '<=') return a <= b;
      if (op === '>') return a > b;
      return a >= b;
    }
    if (esquerda === null || direita === null) return null;
    const a = exigirNumero(esquerda, `operador '${op}'`);
    const b = exigirNumero(direita, `operador '${op}'`);
    if (op === '+') return a + b;
    if (op === '-') return a - b;
    if (op === '*') return a * b;
    if (op === '/') {
      if (b === 0) throw new ErroExpressao('divisao_por_zero', 'divisão por zero', {});
      return a / b;
    }
    if (op === '%') {
      if (b === 0) throw new ErroExpressao('divisao_por_zero', 'resto da divisão por zero', {});
      return a % b;
    }
    if (op === '^') return a ** b;
    throw new ErroExpressao('operador_desconhecido', `operador desconhecido: ${op}`); // pragma: no cover
  }

  return v(no);
}

export function avaliarTexto(texto, contexto, opcoes) {
  return avaliar(analisar(texto), contexto, opcoes);
}
