// Motor de formulário de coleta no navegador (item L2-07-b): estado da resposta, relevância, cálculo na ordem
// topológica, restrição, cascata por choice_filter, repetições e rascunho. Módulo puro (sem DOM) sobre o
// avaliador da linguagem própria (web/js/expressao/avaliador.js); as convenções de contexto são as mesmas do
// motor Python (app/coleta/motor.py): $campo, $_valor, $rep (linhas), $rep__col (colunas), $_lista_<nome>,
// $_linha. O servidor reavalia tudo ao gravar; aqui a regra serve para a tela reagir e para barrar o envio.
import { astDeJson, avaliar } from '../expressao/avaliador.js';

const MS_DIA = 86400000;

function msDeData(v) {
  const t = Date.parse(`${String(v).slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(t) ? null : t;
}
function msDeDataHora(v) {
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

export function valorParaContexto(campo, valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  const tipo = campo.tipo;
  if (tipo === 'data' && typeof valor === 'string') return msDeData(valor);
  if (tipo === 'data_hora' && typeof valor === 'string') return msDeDataHora(valor);
  if (tipo === 'inteiro' || tipo === 'decimal') {
    if (typeof valor === 'boolean') return null;
    const n = tipo === 'decimal' ? Number(valor) : Math.trunc(Number(valor));
    return Number.isFinite(n) ? n : null;
  }
  if (tipo === 'meta' && (campo.meta === 'start' || campo.meta === 'end') && typeof valor === 'string') return msDeDataHora(valor);
  return valor;
}

export function* folhas(campos, repeticao = null) {
  for (const c of campos) {
    if (c.tipo === 'grupo' || c.tipo === 'repeticao') yield* folhas(c.filhos || [], c.tipo === 'repeticao' ? c.nome : repeticao);
    else yield [c, repeticao];
  }
}
export function* nos(campos) {
  for (const c of campos) {
    yield c;
    if (c.tipo === 'grupo' || c.tipo === 'repeticao') yield* nos(c.filhos || []);
  }
}

function camposDoAst(ast, saida = new Set()) {
  if (!ast || typeof ast !== 'object') return saida;
  if (ast.tipo === 'campo') {
    const n = ast.nome || '';
    if (n === '_valor' || n === '_linha' || n.startsWith('_lista_')) return saida;
    saida.add(n.split('__')[0]);
    return saida;
  }
  for (const v of Object.values(ast)) {
    if (Array.isArray(v)) v.forEach((x) => camposDoAst(x, saida));
    else if (v && typeof v === 'object') camposDoAst(v, saida);
  }
  return saida;
}

// Mesmo algoritmo do servidor (documento.ordem_de_calculo): ciclo é erro nomeado, nunca laço infinito.
export function ordemDeCalculo(doc) {
  const calculos = new Map();
  for (const c of nos(doc.campos)) if (c.calculo) calculos.set(c.nome, camposDoAst(c.calculo.ast));
  const pendentes = new Map();
  for (const [n, deps] of calculos) pendentes.set(n, new Set([...deps].filter((d) => calculos.has(d) && d !== n)));
  const ordem = [];
  while (pendentes.size) {
    const prontos = [...pendentes].filter(([, deps]) => deps.size === 0).map(([n]) => n).sort();
    if (!prontos.length) {
      const erro = new Error('cálculo com dependência circular');
      erro.codigo = 'dependencia_circular';
      erro.campos = [...pendentes.keys()].sort();
      throw erro;
    }
    for (const n of prontos) { ordem.push(n); pendentes.delete(n); }
    for (const deps of pendentes.values()) prontos.forEach((p) => deps.delete(p));
  }
  return ordem;
}

export class Motor {
  constructor(doc, { idioma } = {}) {
    this.doc = doc;
    this.idioma = idioma || doc.idioma_padrao || (doc.idiomas || [])[0] || 'default';
    this.porNome = new Map();
    this.repeticaoDe = new Map();
    for (const [c, rep] of folhas(doc.campos)) { this.porNome.set(c.nome, c); this.repeticaoDe.set(c.nome, rep); }
    this.nomesRep = [...nos(doc.campos)].filter((c) => c.tipo === 'repeticao').map((c) => c.nome);
    this.ordem = ordemDeCalculo(doc);
    this.valores = {};
    this.repeticoes = {};
    for (const [c, rep] of folhas(doc.campos)) if (rep === null && c.padrao !== undefined && c.padrao !== null && c.padrao !== '') this.valores[c.nome] = c.padrao;
    for (const r of this.nomesRep) this.repeticoes[r] = [];
    this.asts = new Map();
  }

  rotulo(campo) {
    const r = campo.rotulo || {};
    return r[this.idioma] ?? Object.values(r)[0] ?? campo.nome;
  }
  rotuloOpcao(linha) {
    const r = linha.rotulo || {};
    return r[this.idioma] ?? Object.values(r)[0] ?? linha.nome;
  }

  _ast(regra) {
    if (!regra || !regra.ast) return null;
    let no = this.asts.get(regra);
    if (!no) { no = astDeJson(regra.ast); this.asts.set(regra, no); }
    return no;
  }

  _avaliar(regra, ctx) {
    const no = this._ast(regra);
    if (!no) return [null, null];
    try { return [avaliar(no, ctx), null]; } catch (e) { return [null, e.codigo || 'erro']; }
  }

  contexto(linha = null) {
    const ctx = {};
    for (const [c, rep] of folhas(this.doc.campos)) if (rep === null) ctx[c.nome] = valorParaContexto(c, this.valores[c.nome]);
    for (const r of this.nomesRep) {
      const no = [...nos(this.doc.campos)].find((n) => n.nome === r);
      const filhos = [...folhas(no.filhos || [])].map(([c]) => c);
      const convertidas = (this.repeticoes[r] || []).map((l) => Object.fromEntries(filhos.map((c) => [c.nome, valorParaContexto(c, l[c.nome])])));
      ctx[r] = convertidas;
      for (const c of filhos) ctx[`${r}__${c.nome}`] = convertidas.map((l) => l[c.nome]);
    }
    for (const [nome, linhas] of Object.entries(this.doc.listas || {})) ctx[`_lista_${nome}`] = Object.fromEntries(linhas.map((l) => [String(l.nome), l]));
    for (const nome of this.porNome.keys()) if (!(nome in ctx)) ctx[nome] = null;
    if (linha) for (const [k, v] of Object.entries(linha)) if (this.porNome.has(k)) ctx[k] = valorParaContexto(this.porNome.get(k), v);
    return ctx;
  }

  recalcular() {
    for (const nome of this.ordem) {
      const campo = this.porNome.get(nome);
      const rep = this.repeticaoDe.get(nome);
      if (!campo) continue;
      if (rep === null) {
        const [v] = this._avaliar(campo.calculo, this.contexto());
        this.valores[nome] = v;
      } else {
        for (const linha of this.repeticoes[rep] || []) {
          const [v] = this._avaliar(campo.calculo, this.contexto(linha));
          linha[nome] = v;
        }
      }
    }
  }

  definir(nome, valor, { repeticao = null, indice = 0 } = {}) {
    if (repeticao) this.repeticoes[repeticao][indice][nome] = valor;
    else this.valores[nome] = valor;
    this.recalcular();
  }

  adicionarLinha(repeticao) {
    const linha = {};
    const no = [...nos(this.doc.campos)].find((n) => n.nome === repeticao);
    for (const [c] of folhas(no.filhos || [])) if (c.padrao !== undefined && c.padrao !== null && c.padrao !== '') linha[c.nome] = c.padrao;
    this.repeticoes[repeticao].push(linha);
    this.recalcular();
    return this.repeticoes[repeticao].length - 1;
  }

  removerLinha(repeticao, indice) {
    this.repeticoes[repeticao].splice(indice, 1);
    this.recalcular();
  }

  // relevância herdada: um campo só é relevante se ele e todos os grupos acima forem
  relevante(campo, { linha = null, pais = [] } = {}) {
    const ctx = this.contexto(linha);
    for (const no of [...pais, campo]) {
      if (!no.relevante) continue;
      const [v, erro] = this._avaliar(no.relevante, ctx);
      if (erro || !v) return false;
    }
    return true;
  }

  // cascata: aplica filtro_lista linha a linha com $_linha
  opcoes(campo, { linha = null } = {}) {
    const linhas = (this.doc.listas || {})[campo.lista] || [];
    if (!campo.filtro_lista) return linhas;
    const ctx = this.contexto(linha);
    return linhas.filter((l) => { const [v] = this._avaliar(campo.filtro_lista, { ...ctx, _linha: l }); return !!v; });
  }

  mensagemRestricao(campo) {
    const m = (campo.restricao || {}).mensagem || {};
    if (typeof m === 'string') return m;
    return m[this.idioma] ?? Object.values(m)[0] ?? 'valor fora da regra';
  }

  // erros por campo, no mesmo vocabulário do servidor (campo_obrigatorio, fora_da_lista, restricao_violada)
  validar() {
    const erros = [];
    const visitar = (no, pais, valores, linha, repeticao, indice) => {
      if (!this.relevante(no, { linha, pais })) { if (no.tipo !== 'grupo' && no.tipo !== 'repeticao') valores[no.nome] = null; return; }
      if (no.tipo === 'grupo') { for (const f of no.filhos || []) visitar(f, [...pais, no], valores, linha, repeticao, indice); return; }
      if (no.tipo === 'repeticao') {
        (this.repeticoes[no.nome] || []).forEach((l, i) => { for (const f of no.filhos || []) visitar(f, [], l, l, no.nome, i); });
        return;
      }
      if (['nota', 'calculo', 'meta'].includes(no.tipo)) return;
      let valor = valores[no.nome];
      if (valor === '' || valor === undefined) valor = null;
      const onde = repeticao ? { campo: no.nome, repeticao, indice } : { campo: no.nome };
      if (no.obrigatorio && valor === null) { erros.push({ ...onde, erro: 'campo_obrigatorio', mensagem: 'campo obrigatório' }); return; }
      if (valor === null) return;
      if ((no.tipo === 'select_one' || no.tipo === 'select_multiple') && no.lista) {
        const permitidas = new Set(this.opcoes(no, { linha }).map((o) => String(o.nome)));
        const escolhidos = no.tipo === 'select_multiple' ? String(valor).split(' ') : [String(valor)];
        const fora = escolhidos.filter((e) => e && !permitidas.has(e));
        if (fora.length) { erros.push({ ...onde, erro: 'fora_da_lista', mensagem: 'valor fora das opções', valores: fora }); return; }
      }
      if (no.restricao) {
        const [v, erro] = this._avaliar(no.restricao, { ...this.contexto(linha), _valor: valorParaContexto(no, valor) });
        if (erro || !v) erros.push({ ...onde, erro: 'restricao_violada', mensagem: this.mensagemRestricao(no) });
      }
    };
    for (const no of this.doc.campos) visitar(no, [], this.valores, null, null, null);
    return erros;
  }

  // corpo de POST /api/formularios/{id}/respostas
  resposta({ inicio, dispositivo } = {}) {
    this.recalcular();
    const valores = {};
    for (const [c, rep] of folhas(this.doc.campos)) if (rep === null && c.tipo !== 'nota') valores[c.nome] = this.valores[c.nome] ?? null;
    return { valores, repeticoes: this.repeticoes, inicio: inicio || null, fim: new Date().toISOString(), dispositivo: dispositivo || null };
  }

  serializar() { return JSON.stringify({ valores: this.valores, repeticoes: this.repeticoes }); }
  restaurar(texto) {
    try {
      const d = JSON.parse(texto);
      if (d && typeof d === 'object') {
        this.valores = { ...this.valores, ...(d.valores || {}) };
        for (const r of this.nomesRep) this.repeticoes[r] = Array.isArray((d.repeticoes || {})[r]) ? d.repeticoes[r] : [];
        this.recalcular();
        return true;
      }
    } catch { /* rascunho ilegível: começa em branco */ }
    return false;
  }
}
