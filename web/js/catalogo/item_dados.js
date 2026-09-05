/* plat · catálogo — formulário gerado do JSON Schema do tipo (GET /api/tipos-item, ADR 0004 seção 3.3): string/enum,
   integer/number, boolean, array de primitivos (uma por linha), objeto e array de objetos como JSON com conferência
   local. Validação local cobre type, required, enum, minimum/maximum, minLength/maxLength, pattern, maxItems,
   additionalProperties=false; o erro do servidor (422 dados_invalidos, detalhe[{campo, erro}]) é ligado ao campo pelo
   caminho. O servidor é quem decide. */
import { h } from '../base/dom.js';
import { t } from '../base/i18n.js';

const TIPOS_SIMPLES = new Set(['string', 'integer', 'number', 'boolean']);

function tipoDe(esq) {
  if (!esq) return 'any';
  if (Array.isArray(esq.type)) return esq.type.find((x) => x !== 'null') || 'any';
  if (esq.type) return esq.type;
  if (esq.enum) return 'string';
  if (esq.properties) return 'object';
  if (esq.items) return 'array';
  return 'any';
}

function itemSimples(esq) { const it = esq.items || {}; return TIPOS_SIMPLES.has(tipoDe(it)) && !it.enum; }

/* campo do <plat-formulario> por propriedade */
function campoDe(nome, esq, valor, obrigatorio, prefixo) {
  const tipo = tipoDe(esq);
  const rotulo = esq.title || nome;
  const ajuda = esq.description || '';
  const base = { nome: prefixo ? `${prefixo}.${nome}` : nome, rotulo, obrigatorio, ajuda };
  if (esq.enum) return { ...base, tipo: 'select', opcoes: [...(obrigatorio ? [] : [{ valor: '', rotulo: '—' }]), ...esq.enum.map((v) => ({ valor: String(v), rotulo: String(v) }))], padrao: valor === undefined || valor === null ? '' : String(valor) };
  if (tipo === 'boolean') return { ...base, tipo: 'caixa', padrao: !!valor };
  if (tipo === 'integer' || tipo === 'number') return { ...base, tipo: 'numero', padrao: valor ?? '', atributos: { min: esq.minimum, max: esq.maximum, step: tipo === 'integer' ? 1 : 'any' } };
  if (tipo === 'string') return { ...base, tipo: (esq.maxLength || 0) > 250 ? 'area' : 'texto', padrao: valor ?? '', atributos: { maxlength: esq.maxLength, pattern: undefined } };
  if (tipo === 'array' && itemSimples(esq)) return { ...base, tipo: 'lista', padrao: Array.isArray(valor) ? valor.map(String) : [], ajuda: `${ajuda} ${t('catalogo.dados_lista_ajuda')}`.trim(), linhas: 4 };
  // objeto ou array de objetos: JSON
  return { ...base, tipo: 'area', json: true, padrao: valor === undefined ? (tipo === 'array' ? '[]' : '{}') : JSON.stringify(valor, null, 2), ajuda: `${ajuda} ${t('catalogo.dados_json_ajuda')}`.trim(), linhas: 8 };
}

/* campos do formulário para um esquema de objeto e um valor atual */
export function camposDoEsquema(esquema, dados = {}) {
  const props = (esquema && esquema.properties) || {};
  const obrig = new Set((esquema && esquema.required) || []);
  const campos = [];
  for (const [nome, esq] of Object.entries(props)) campos.push(campoDe(nome, esq, dados ? dados[nome] : undefined, obrig.has(nome), ''));
  // propriedades presentes no dado e ausentes no esquema aparecem como JSON (o servidor decide se aceita)
  for (const [nome, v] of Object.entries(dados || {})) if (!(nome in props)) campos.push({ nome, rotulo: nome, tipo: 'area', json: true, padrao: JSON.stringify(v, null, 2), linhas: 4, ajuda: t('catalogo.dados_fora_do_esquema') });
  return campos;
}

/* valores do <plat-formulario> -> objeto de dados tipado pelo esquema; devolve {dados, erros: {campo: msg}} */
export function dadosDosValores(campos, valores, esquema) {
  const props = (esquema && esquema.properties) || {};
  const dados = {};
  const erros = {};
  for (const c of campos) {
    const esq = props[c.nome] || {};
    const tipo = tipoDe(esq);
    let v = valores[c.nome];
    if (c.json) {
      const texto = String(v ?? '').trim();
      if (!texto) { if (c.obrigatorio) erros[c.nome] = t('form.obrigatorio'); continue; }
      try { v = JSON.parse(texto); } catch { erros[c.nome] = t('catalogo.dados_json_invalido'); continue; }
      dados[c.nome] = v;
      continue;
    }
    if (c.tipo === 'caixa') { dados[c.nome] = !!v; continue; }
    if (c.tipo === 'numero') { if (v === null || v === undefined || v === '') { if (c.obrigatorio) erros[c.nome] = t('form.obrigatorio'); continue; } dados[c.nome] = tipo === 'integer' ? Math.trunc(Number(v)) : Number(v); continue; }
    if (c.tipo === 'lista') { const l = Array.isArray(v) ? v : []; if (!l.length && !c.obrigatorio) continue; dados[c.nome] = l.map((x) => (tipoDe(esq.items || {}) === 'number' || tipoDe(esq.items || {}) === 'integer' ? Number(x) : x)); continue; }
    if (v === '' || v === undefined || v === null) { if (c.obrigatorio) erros[c.nome] = t('form.obrigatorio'); continue; }
    if (c.tipo === 'select' && (tipo === 'integer' || tipo === 'number')) v = Number(v);
    dados[c.nome] = v;
  }
  for (const [campo, msg] of Object.entries(validar(dados, esquema))) if (!erros[campo]) erros[campo] = msg;
  return { dados, erros };
}

/* validador local mínimo; devolve {caminho: mensagem} com o caminho no formato do servidor (a.b.0.c) */
export function validar(valor, esq, caminho = '') {
  const erros = {};
  if (!esq || typeof esq !== 'object') return erros;
  const aqui = caminho || '';
  const tipo = tipoDe(esq);
  const falha = (msg) => { erros[aqui || '$'] = msg; return erros; };
  if (valor === undefined || valor === null) { return erros; }
  if (esq.enum && !esq.enum.some((e) => String(e) === String(valor))) return falha(t('catalogo.dados_erro_enum', { valores: esq.enum.join(', ') }));
  if (tipo === 'integer' && !(typeof valor === 'number' && Number.isInteger(valor))) return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (tipo === 'number' && typeof valor !== 'number') return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (tipo === 'string' && typeof valor !== 'string') return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (tipo === 'boolean' && typeof valor !== 'boolean') return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (tipo === 'array' && !Array.isArray(valor)) return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (tipo === 'object' && (typeof valor !== 'object' || Array.isArray(valor))) return falha(t('catalogo.dados_erro_tipo', { tipo }));
  if (typeof valor === 'number') {
    if (esq.minimum !== undefined && valor < esq.minimum) return falha(t('catalogo.dados_erro_min', { n: esq.minimum }));
    if (esq.maximum !== undefined && valor > esq.maximum) return falha(t('catalogo.dados_erro_max', { n: esq.maximum }));
  }
  if (typeof valor === 'string') {
    if (esq.minLength !== undefined && valor.length < esq.minLength) return falha(t('catalogo.dados_erro_min_len', { n: esq.minLength }));
    if (esq.maxLength !== undefined && valor.length > esq.maxLength) return falha(t('catalogo.dados_erro_max_len', { n: esq.maxLength }));
    if (esq.pattern) { let ok = true; try { ok = new RegExp(esq.pattern).test(valor); } catch { ok = true; } if (!ok) return falha(t('catalogo.dados_erro_padrao', { padrao: esq.pattern })); }
  }
  if (Array.isArray(valor)) {
    if (esq.maxItems !== undefined && valor.length > esq.maxItems) return falha(t('catalogo.dados_erro_max_itens', { n: esq.maxItems }));
    if (esq.minItems !== undefined && valor.length < esq.minItems) return falha(t('catalogo.dados_erro_min_itens', { n: esq.minItems }));
    valor.forEach((v, i) => Object.assign(erros, validar(v, esq.items, aqui ? `${aqui}.${i}` : String(i))));
  }
  if (valor && typeof valor === 'object' && !Array.isArray(valor)) {
    const props = esq.properties || {};
    for (const r of esq.required || []) if (valor[r] === undefined) erros[aqui ? `${aqui}.${r}` : r] = t('form.obrigatorio');
    for (const [k, v] of Object.entries(valor)) {
      if (props[k]) Object.assign(erros, validar(v, props[k], aqui ? `${aqui}.${k}` : k));
      else if (esq.additionalProperties === false) erros[aqui ? `${aqui}.${k}` : k] = t('catalogo.dados_erro_desconhecido');
    }
  }
  return erros;
}

/* liga erros por caminho ao campo de topo do formulário (o resto do caminho vai no texto) */
export function aplicarErros(form, erros) {
  for (const [caminho, msg] of Object.entries(erros)) {
    const topo = String(caminho).split('.')[0];
    const resto = String(caminho).includes('.') ? ` (${caminho})` : '';
    form.erro(form.campo(topo) ? topo : '$', `${msg}${resto}`);
  }
}

/* erros do servidor: detalhe [{campo, erro, regra}] -> {campo: msg} */
export function errosDoServidor(detalhe) {
  const out = {};
  for (const d of Array.isArray(detalhe) ? detalhe : []) if (d && d.campo !== undefined) out[String(d.campo)] = d.erro || d.regra || t('catalogo.dados_invalidos');
  return out;
}

/* dado inicial por esquema (para "novo item" de um tipo): obrigatórios com valor vazio do tipo */
export function dadosIniciais(esquema) {
  const props = (esquema && esquema.properties) || {};
  const out = {};
  for (const r of (esquema && esquema.required) || []) {
    const tipo = tipoDe(props[r] || {});
    out[r] = tipo === 'object' ? {} : tipo === 'array' ? [] : tipo === 'boolean' ? false : tipo === 'integer' || tipo === 'number' ? (props[r].minimum ?? (props[r].enum ? props[r].enum[0] : 1)) : (props[r].enum ? props[r].enum[0] : '');
  }
  return out;
}

/* leitura: lista rótulo → valor do dado, sem editar */
export function resumoDados(dados) {
  const dl = h('dl', { class: 'dados-resumo' });
  for (const [k, v] of Object.entries(dados || {})) dl.append(h('dt', {}, k), h('dd', {}, h('code', {}, typeof v === 'object' ? JSON.stringify(v).slice(0, 200) : String(v))));
  if (!dl.childElementCount) dl.append(h('dd', { class: 'fraco' }, t('catalogo.dados_vazios')));
  return dl;
}
