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

// `util.types.isProxy` só existe no Node (onde os testes rodam); no navegador o import falha e o
// detector fica nulo — ver contextoSimples() e docs/EXPRESSAO.md §7.
let detectorProxy = null;
try { detectorProxy = (await import('node:util')).types.isProxy; } catch { detectorProxy = null; }

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
    this.profundidadeOk(p, this.olha()?.posicao ?? this.texto.length);
    const esquerda = this.unario(p);
    const tok = this.olha();
    if (tok !== null && tok.tipo === 'op' && PREC_POTENCIA.has(tok.valor)) {
      this.i += 1;
      const direita = this.potencia(p + 1); // associatividade à direita
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
function astDados(d) {
  if(!d || typeof d!=='object' || Array.isArray(d) || (Object.getPrototypeOf(d)!==Object.prototype && Object.getPrototypeOf(d)!==null)) falha('no_desconhecido');
  for(const k of Object.keys(d)) if(!possui(Object.getOwnPropertyDescriptor(d,k),'value')) falha('no_desconhecido');
}
function validarAst(no) {
  const stack=[[no,1]]; let count=0;
  while(stack.length) {
    const [n,p]=stack.pop(); count++;
    if(p>MAX_PROFUNDIDADE) falha('profundidade_excedida');
    if(count>MAX_TOKENS) falha('expressao_grande');
    astDados(n);
    if(!possui(n,'no')) falha('no_desconhecido');
    const ident=x=>typeof x==='string' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(x);
    if(n.no==='literal') {
      const valid={nulo:n.valor===null,numero:typeof n.valor==='number',texto:typeof n.valor==='string',booleano:typeof n.valor==='boolean'};
      if(!possui(n,'valor') || !possui(valid,n.tipoValor) || !valid[n.tipoValor]) falha('no_desconhecido');
    } else if(n.no==='campo') { if(!ident(n.nome)) falha('no_desconhecido'); }
    else if(n.no==='unario') {
      if(!['-','!'].includes(n.operador)) falha('no_desconhecido');
      stack.push([n.operando,p+1]);
    } else if(n.no==='binario') {
      if(!['+','-','*','/','%','^','==','!=','<','<=','>','>=','&&','||'].includes(n.operador)) falha('no_desconhecido');
      stack.push([n.esquerda,p+1],[n.direita,p+1]);
    } else if(n.no==='chamada') {
      if(!ident(n.nome) || !Array.isArray(n.argumentos)) falha('no_desconhecido');
      if(n.argumentos.length>MAX_ARGUMENTOS) falha('expressao_grande');
      for(let i=0;i<n.argumentos.length;i++) stack.push([proprio(n.argumentos,String(i)),p+1]);
    } else falha('no_desconhecido');
  }
}
export function astDeJson(d, profundidade=1) {
  let count=0;
  function build(d,p) {
    count++;
    if(p>MAX_PROFUNDIDADE) falha('profundidade_excedida');
    if(count>MAX_TOKENS) falha('expressao_grande');
    astDados(d);
    const required={literal:['tipo_valor','valor'],campo:['nome'],unario:['operador','operando'],binario:['operador','esquerda','direita'],chamada:['nome','argumentos']};
    if(!possui(d,'tipo') || !possui(required,proprio(d,'tipo'))) falha('no_desconhecido');
    // todo campo do nó é lido por DESCRITOR (nunca `d.x`): um objeto com getter ou uma armadilha de
    // Proxy não roda código nosso. E a forma é FECHADA: campo a mais no nó é recusado, não ignorado.
    const tipo=proprio(d,'tipo');
    const esperados=['tipo',...required[tipo]];
    const chaves=Object.getOwnPropertyNames(d);
    if(chaves.length!==esperados.length || !chaves.every(k=>esperados.includes(k))) falha('no_desconhecido');
    if(tipo==='literal') return {no:'literal',tipoValor:proprio(d,'tipo_valor'),valor:proprio(d,'valor')};
    if(tipo==='campo') return {no:'campo',nome:proprio(d,'nome')};
    if(tipo==='unario') return {no:'unario',operador:proprio(d,'operador'),operando:build(proprio(d,'operando'),p+1)};
    if(tipo==='binario') return {no:'binario',operador:proprio(d,'operador'),esquerda:build(proprio(d,'esquerda'),p+1),direita:build(proprio(d,'direita'),p+1)};
    const argumentos=proprio(d,'argumentos');
    if(!Array.isArray(argumentos)) falha('no_desconhecido');
    if(argumentos.length>MAX_ARGUMENTOS) falha('expressao_grande');
    const args=[];
    for(let i=0;i<argumentos.length;i++) args.push(build(proprio(argumentos,String(i)),p+1));
    return {no:'chamada',nome:proprio(d,'nome'),argumentos:args};
  }
  const result=build(d,profundidade); validarAst(result); return result;
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
  // inteiro: dígitos exatos também acima de 1e21 (String(1e21) daria '1e+21'; o Python dá str(int(n)))
  if (Number.isInteger(n)) return Math.abs(n) < 1e21 ? String(n) : BigInt(n).toString();
  // toFixed arredonda o valor binário EXATO com empate para longe de zero — o Python replica com Decimal
  let s = n.toFixed(6);
  s = s.replace(/0+$/, '').replace(/\.$/, '');
  return s;
}

const MESES_PT = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
  'outubro', 'novembro', 'dezembro'];
const FORMATOS_DATA = ['data', 'data_hora', 'data_hora_segundos', 'extenso'];

/** pt-BR: milhar '.', decimal ',', exatamente `casas` decimais (0-15), empate para longe de zero
 * sobre o valor binário exato (toFixed); zero nunca leva sinal. Mesmo algoritmo de _texto_numero_pt. */
function textoNumeroPt(n, casas) {
  if (casas > 15 || Math.abs(n) >= 1e21) falha('numero_invalido');
  const fixo = Math.abs(n).toFixed(casas);
  const [inteiroBruto, fracao] = fixo.split('.');
  let inteiro = inteiroBruto;
  const grupos = [];
  while (inteiro.length > 3) { grupos.unshift(inteiro.slice(-3)); inteiro = inteiro.slice(0, -3); }
  grupos.unshift(inteiro);
  const texto = grupos.join('.') + (casas ? ',' + fracao : '');
  const negativo = n < 0 && /[1-9]/.test(texto);
  return (negativo ? '-' : '') + texto;
}

function textoDataPt(ms, formato) {
  anoMesDiaUtc(ms); // mesma faixa (anos 1-9999) e mesmo erro nomeado que Ano/Mes/Dia/Weekday
  const d = new Date(Math.floor(ms));
  const p2 = (x) => String(x).padStart(2, '0');
  const ano = String(d.getUTCFullYear()).padStart(4, '0');
  if (formato === 'extenso') return `${d.getUTCDate()} de ${MESES_PT[d.getUTCMonth()]} de ${ano}`;
  const texto = `${p2(d.getUTCDate())}/${p2(d.getUTCMonth() + 1)}/${ano}`;
  if (formato === 'data_hora') return `${texto} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
  if (formato === 'data_hora_segundos') {
    return `${texto} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`;
  }
  return texto;
}

/** Valor de SAÍDA como o JSON o carrega: -0 vira 0 (JSON.stringify(-0) é '0'; o Python devolve int 0). */
function canonico(v) {
  if (typeof v === 'number') return Object.is(v, -0) ? 0 : v;
  if (Array.isArray(v)) return v.map(canonico);
  if (v && typeof v === 'object') {
    const out = Object.create(null);
    for (const k of Object.keys(v)) out[k] = canonico(v[k]);
    return out;
  }
  return v;
}

function arredondarNumero(x, casas) {
  if (Math.abs(casas)>15) falha('numero_invalido');
  const fator = 10 ** casas;
  if (x >= 0) return Math.floor(x * fator + 0.5) / fator;
  return Math.ceil(x * fator - 0.5) / fator;
}

function diasDesdeEpoca(ms) {
  if (ms >= 0) return Math.floor(ms / DIA_MS);
  return -Math.floor((-ms + DIA_MS - 1) / DIA_MS);
}

function anoMesDiaUtc(ms) {
  ms = Math.floor(ms); // data arredonda SEMPRE para baixo (EXPRESSAO.md §3.1); `new Date` truncaria para zero
  if(ms < -62135596800000 || ms >= 253402300800000) falha('numero_invalido');
  const d = new Date(ms);
  return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()];
}

function exigirNumero(v, onde) {
  if (!ehNumero(v)) throw new ErroExpressao('tipo_invalido', `${onde} espera número, recebeu ${tipoNome(v)}`, { onde });
  return finito(v);
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

export const MAX_COLECAO = 1024;
export const MAX_VALOR_NOS = 4096;
export const MAX_VALOR_TEXTO = 20000;
export const MAX_VALOR_PROFUNDIDADE = 20;
const PROIBIDOS = new Set(['__proto__', 'prototype', 'constructor']);
const EXT_ARIDADES = {Trim:[1,1],Left:[2,2],Right:[2,2],Mid:[2,3],Find:[2,3],Split:[2,2],Replace:[3,3],
  Floor:[1,1],Ceil:[1,1],Sqrt:[1,1],Weekday:[1,1],Decode:[4,null],Lista:[0,null],Contagem:[1,1],
  Primeiro:[1,1],Ultimo:[1,1],Obter:[2,3],Contem:[2,2],Soma:[1,1],Media:[1,1],Reverter:[1,1],Unicos:[1,1],Juntar:[1,2],
  TextoNumero:[1,2],TextoData:[1,2]};
Object.assign(TABELA_FUNCOES, EXT_ARIDADES);
const possui = (o,k) => Object.prototype.hasOwnProperty.call(o,k);
function falha(codigo='tipo_invalido') { throw new ErroExpressao(codigo,'valor ou operação fora do contrato'); }
function finito(n) { if (!Number.isFinite(n)) falha('numero_invalido'); return n; }
function potenciaSegura(a,b) { if (Math.abs(b)>1024) falha('numero_invalido'); return finito(a ** b); }
// ---- texto medido em PONTO DE CÓDIGO (EXPRESSAO.md §3.1). O `String` do JavaScript é UTF-16: `<`,
// `indexOf` e `split` trabalham em UNIDADE, casam meia-substituta e ordenam emoji antes de U+E000–U+FFFF.
// O `str` do Python trabalha em ponto de código. As funções abaixo dão a semântica do Python ao lado JS.
const TEM_SUBSTITUTA = /[\uD800-\uDFFF]/;
function compararTexto(a,b) {
  if (a===b) return 0;
  if (!TEM_SUBSTITUTA.test(a) && !TEM_SUBSTITUTA.test(b)) return a<b?-1:1; // sem substituta, unidade = ponto de código
  const A=Array.from(a), B=Array.from(b), n=Math.min(A.length,B.length);
  for (let i=0;i<n;i++) { const x=A[i].codePointAt(0), y=B[i].codePointAt(0); if(x!==y) return x<y?-1:1; }
  return A.length===B.length?0:(A.length<B.length?-1:1);
}
function alta(c) { return c>=0xD800 && c<=0xDBFF; }
function baixa(c) { return c>=0xDC00 && c<=0xDFFF; }
function acharAlinhado(t,agulha,desde) {
  // índice UTF-16 da agulha, recusando casamento que parta um par substituto (= o que o Python não casa)
  if (!TEM_SUBSTITUTA.test(t) && !TEM_SUBSTITUTA.test(agulha)) return t.indexOf(agulha,desde);
  let i=t.indexOf(agulha,desde);
  while (i>=0) {
    const fim=i+agulha.length;
    const inicioOk = !(baixa(t.charCodeAt(i)) && i>0 && alta(t.charCodeAt(i-1)));
    const fimOk = !(alta(t.charCodeAt(fim-1)) && fim<t.length && baixa(t.charCodeAt(fim)));
    if (inicioOk && fimOk) return i;
    i=t.indexOf(agulha,i+1);
  }
  return -1;
}
function dividirAlinhado(t,sep,limite) {
  // `limite` undefined = sem limite (String.prototype.split converteria Infinity para 0)
  if (!TEM_SUBSTITUTA.test(t) && !TEM_SUBSTITUTA.test(sep)) return limite===undefined?t.split(sep):t.split(sep,limite);
  const out=[]; let i=0;
  for(;;) {
    const j=acharAlinhado(t,sep,i);
    if (j<0 || (limite!==undefined && out.length>=limite-1)) { out.push(t.slice(i)); return out; }
    out.push(t.slice(i,j)); i=j+sep.length;
  }
}
/* O contexto de TOPO tem de ser objeto simples, como o `type(contexto) is not dict` do Python:
   dicionário de dados, sem protótipo estranho, sem armadilha. `detectorProxy` só existe no Node
   (`util.types.isProxy`); NO NAVEGADOR NÃO HÁ COMO DETECTAR UM Proxy — lá a defesa é o contrato de
   que o contexto é montado pela aplicação, mais a lista branca por campo e a leitura por descritor
   (que nunca executa getter). Está escrito assim em docs/EXPRESSAO.md §7. */
function contextoSimples(c) {
  if (c===null || typeof c!=='object' || Array.isArray(c)) falha('tipo_invalido');
  const proto=Object.getPrototypeOf(c);
  if (proto!==Object.prototype && proto!==null) falha('tipo_invalido');
  if (detectorProxy && detectorProxy(c)) falha('tipo_invalido');
}
function proprio(o,k) {
  const d=Object.getOwnPropertyDescriptor(o,k);
  if (!d || !possui(d,'value')) falha('tipo_invalido');
  return d.value;
}
function valorSeguro(valor,contador) {
  let nos=0, texto=0;
  function copiar(v,p) {
    contador.passo(); nos++;
    if (nos>MAX_VALOR_NOS || p>MAX_VALOR_PROFUNDIDADE) falha('valor_grande');
    if (v===null || typeof v==='boolean') return v;
    if (typeof v==='number') return finito(v);
    if (typeof v==='string') {
      if (v.length>MAX_VALOR_TEXTO*2) falha('valor_grande');
      texto+=Array.from(v).length;
      if (texto>MAX_VALOR_TEXTO) falha('valor_grande');
      return v;
    }
    if (!v || typeof v!=='object') falha();
    if (Array.isArray(v)) {
      if (v.length>MAX_COLECAO) falha('valor_grande');
      const out=[];
      for(let i=0;i<v.length;i++) out.push(copiar(proprio(v,String(i)),p+1));
      return out;
    }
    if (Object.getPrototypeOf(v)!==Object.prototype && Object.getPrototypeOf(v)!==null) falha();
    const keys=Object.keys(v);
    if(keys.length>MAX_COLECAO) falha('valor_grande');
    const out=Object.create(null);
    for(const k of keys) { copiar(k,p+1); out[k]=copiar(proprio(v,k),p+1); }
    return out;
  }
  return copiar(valor,0);
}
function igualJson(a,b,contador) {
  contador.passo();
  if (a===null || b===null || typeof a!=='object' || typeof b!=='object') return a===b;
  if (Array.isArray(a)!==Array.isArray(b)) return false;
  const ka=Object.keys(a), kb=Object.keys(b);
  return ka.length===kb.length && ka.every(k=>possui(b,k) && igualJson(a[k],b[k],contador));
}
function indice(a) { if(typeof a!=='number' || !Number.isInteger(a) || a<0) falha(); return a; }
function extFuncao(nome,a,contador) {
  const [min,max]=EXT_ARIDADES[nome];
  if(a.length<min || (max!==null && a.length>max)) falha('aridade_invalida');
  if(nome==='Lista') return a;
  if(nome==='Obter') {
    const [c,k]=a, def=a.length===3?a[2]:null;
    if(c===null) return def;
    if(Array.isArray(c)) { indice(k); return k<c.length?c[k]:def; }
    if(typeof c!=='object' || typeof k!=='string') falha();
    if(PROIBIDOS.has(k)) falha('campo_nao_permitido');
    return possui(c,k)?proprio(c,k):def;
  }
  if(nome==='Contem') {
    if(a[0]===null) return null;
    if(!Array.isArray(a[0])) falha();
    return a[0].some(x=>igualJson(x,a[1],contador));
  }
  if(a.some(x=>x===null)) return null;
  if(['Trim','Left','Right','Mid','Find','Split','Replace'].includes(nome)) {
    if(typeof a[0]!=='string') falha();
    const t=a[0], points=Array.from(t);
    if(nome==='Trim') return t.replace(/^[ \t\r\n\f\v]+|[ \t\r\n\f\v]+$/g,'');
    if(nome==='Left') return points.slice(0,indice(a[1])).join('');
    if(nome==='Right') { const n=indice(a[1]); return n?points.slice(-n).join(''):''; }
    if(nome==='Mid') { const n=indice(a[1]); return points.slice(n,a.length===3?n+indice(a[2]):undefined).join(''); }
    if(typeof a[1]!=='string') falha();
    if(nome==='Find') {
      const start=a.length===3?indice(a[2]):0, textPoints=Array.from(a[1]);
      if(start>textPoints.length) return -1;
      const offset=textPoints.slice(0,start).join('').length, idx=acharAlinhado(a[1],t,offset);
      return idx<0?-1:Array.from(a[1].slice(0,idx)).length;
    }
    if(nome==='Split') {
      const out=a[1]?dividirAlinhado(t,a[1],MAX_COLECAO+1):points;
      if(out.length>MAX_COLECAO) falha('valor_grande');
      return out;
    }
    if(typeof a[2]!=='string') falha();
    if(!a[1]) return t;
    const parts=dividirAlinhado(t,a[1],undefined);
    const size=points.length+(parts.length-1)*(Array.from(a[2]).length-Array.from(a[1]).length);
    if(size>MAX_VALOR_TEXTO) falha('valor_grande');
    return parts.join(a[2]);
  }
  if(nome==='TextoNumero') return textoNumeroPt(exigirNumero(a[0],nome), a.length===2?indice(a[1]):2);
  if(nome==='TextoData') {
    const formato=a.length===2?a[1]:'data';
    if(typeof formato!=='string' || !FORMATOS_DATA.includes(formato)) falha();
    return textoDataPt(exigirNumero(a[0],nome), formato);
  }
  if(['Floor','Ceil','Sqrt','Weekday'].includes(nome)) {
    const n=exigirNumero(a[0],nome);
    if(nome==='Floor') return Math.floor(n);
    if(nome==='Ceil') return Math.ceil(n);
    if(nome==='Sqrt') return finito(Math.sqrt(n));
    anoMesDiaUtc(n); return ((Math.floor(n/DIA_MS)+4)%7+7)%7;
  }
  const c=a[0];
  if(nome==='Contagem') {
    if(typeof c==='string') return Array.from(c).length;
    if(typeof c!=='object') falha();
    return Array.isArray(c)?c.length:Object.keys(c).length;
  }
  if(!Array.isArray(c)) falha();
  if(nome==='Primeiro') return c.length?c[0]:null;
  if(nome==='Ultimo') return c.length?c[c.length-1]:null;
  if(nome==='Reverter') return c.slice().reverse();
  if(nome==='Soma'||nome==='Media') {
    if(c.some(x=>x===null)) return null;
    let sum=0;
    for(const x of c) { contador.passo(); sum=finito(sum+exigirNumero(x,nome)); }
    return nome==='Soma'?sum:c.length?sum/c.length:null;
  }
  if(nome==='Unicos') {
    const out=[];
    for(const x of c) if(!out.some(y=>igualJson(x,y,contador))) out.push(x);
    return out;
  }
  if(nome==='Juntar') {
    const sep=a.length===2?a[1]:'';
    if(typeof sep!=='string') falha();
    const parts=c.map(x=>chamarFuncao('Texto',[x]));
    const size=parts.reduce((n,x)=>n+Array.from(x).length,0)+Array.from(sep).length*Math.max(0,c.length-1);
    if(size>MAX_VALOR_TEXTO) falha('valor_grande');
    return parts.join(sep);
  }
  falha('funcao_desconhecida');
}

function chamarFuncao(nome, args) {
  if (!possui(TABELA_FUNCOES, nome)) {
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
      return potenciaSegura(exigirNumero(args[0], 'Potencia'), exigirNumero(args[1], 'Potencia'));
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
    // relógio conferido a CADA passo (uma operação de coleção custa mais do que um nó; amostrar a
    // cada N passos deixaria um único `Unicos` de 1.024 elementos passar do orçamento)
    const agora = (typeof performance !== 'undefined' ? performance.now() : Date.now());
    if (agora - this.inicio > this.limiteMs) {
      throw new ErroExpressao(
        'tempo_excedido', `avaliação acima de ${this.limiteMs} ms`, { limite_ms: this.limiteMs },
      );
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
  contextoSimples(contexto);
  const limitePassos = (opcoes && opcoes.limitePassos) ?? MAX_PASSOS_PADRAO;
  const limiteMs = (opcoes && opcoes.limiteMs) ?? LIMITE_MS_CLIENTE;
  const contador = new Contador(limitePassos, limiteMs);

  validarAst(no);
  function v(nodo) { return valorSeguro(executar(nodo),contador); }
  function executar(nodo) {
    contador.passo();
    if (nodo.no === 'literal') return nodo.valor;
    if (nodo.no === 'campo') {
      if (PROIBIDOS.has(nodo.nome) || !possui(contexto, nodo.nome)) {
        throw new ErroExpressao('campo_nao_permitido', `campo não permitido: ${nodo.nome}`, { campo: nodo.nome });
      }
      return proprio(contexto,nodo.nome);
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
      if(nodo.nome==='Decode') {
        const a=nodo.argumentos;
        if(a.length<4 || a.length%2) falha('aridade_invalida');
        const valor=v(a[0]);
        for(let i=1;i<a.length-1;i+=2) if(igualJson(valor,v(a[i]),contador)) return v(a[i+1]);
        return v(a[a.length-1]);
      }
      const args = nodo.argumentos.map(v);
      if(possui(EXT_ARIDADES,nodo.nome)) return extFuncao(nodo.nome,args,contador);
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
      if (typeof a === 'string') { // ordem por PONTO DE CÓDIGO, não por unidade UTF-16 (§3.1)
        const c = compararTexto(a,b);
        if (op === '<') return c<0;
        if (op === '<=') return c<=0;
        if (op === '>') return c>0;
        return c>=0;
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
    if (op === '^') return potenciaSegura(a, b);
    throw new ErroExpressao('operador_desconhecido', `operador desconhecido: ${op}`); // pragma: no cover
  }

  return canonico(v(no));
}

export function avaliarTexto(texto, contexto, opcoes) {
  return avaliar(analisar(texto), contexto, opcoes);
}
