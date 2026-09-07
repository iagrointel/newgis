/* plat · catálogo — sintaxe da busca por campo (ADR 0004 seção 7.2) validada no cliente para mostrar
   "campo desconhecido" antes de enviar; o servidor é quem decide. Puro (sem DOM): a ajuda é montada por quem chama.
   Gramática: termos, "frase", campo:valor, campo:"frase com espaço", campo:[a TO b], operadores AND/OR/NOT/-,
   parênteses. Devolve {ok, erros: [{posicao, mensagem}], partes: [{tipo, campo, valor}]}. */
import { t } from '../base/i18n.js';

export const CAMPOS_TEXTO = ['titulo', 'tags', 'resumo', 'descricao'];
export const CAMPOS_EXATOS = ['dono', 'tipo', 'status', 'acesso', 'pasta', 'categoria', 'grupo', 'id', 'origem', 'familia', 'licenca'];
export const CAMPOS_DATA = ['criado', 'modificado'];
/* item L0-09-a: intervalo NUMÉRICO de 0 a 10 (pontuação de procedência), aceito também como valor solto = mínimo */
export const CAMPOS_NUMERO = ['procedencia'];
export const CAMPOS = [...CAMPOS_TEXTO, ...CAMPOS_EXATOS, ...CAMPOS_DATA, ...CAMPOS_NUMERO];
export const OPERADORES = ['AND', 'OR', 'NOT'];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATA = /^(\*|\d{4}(-\d{2}(-\d{2})?)?)$/;

function lerToken(q, i) {
  /* devolve [token, fim] a partir de i (sem espaço inicial); aspas e colchetes fecham o token */
  let j = i;
  let out = '';
  while (j < q.length) {
    const c = q[j];
    if (c === '"') {
      const fim = q.indexOf('"', j + 1);
      if (fim < 0) return [out + q.slice(j), q.length, 'aspas'];
      out += q.slice(j, fim + 1); j = fim + 1; continue;
    }
    if (c === '[') {
      const fim = q.indexOf(']', j + 1);
      if (fim < 0) return [out + q.slice(j), q.length, 'colchete'];
      out += q.slice(j, fim + 1); j = fim + 1; continue;
    }
    if (/\s/.test(c) || c === '(' || c === ')') break;
    out += c; j += 1;
  }
  return [out, j, null];
}

export function analisar(q) {
  const texto = String(q || '');
  const erros = [];
  const partes = [];
  let i = 0;
  let termos = 0;
  let parenteses = 0;
  while (i < texto.length) {
    const c = texto[i];
    if (/\s/.test(c)) { i += 1; continue; }
    if (c === '(') { parenteses += 1; partes.push({ tipo: 'abre' }); i += 1; continue; }
    if (c === ')') { parenteses -= 1; if (parenteses < 0) erros.push({ posicao: i, mensagem: t('catalogo.busca_erro_parentese') }); partes.push({ tipo: 'fecha' }); i += 1; continue; }
    const [token, fim, aberto] = lerToken(texto, i);
    if (aberto === 'aspas') erros.push({ posicao: i, mensagem: t('catalogo.busca_erro_aspas') });
    if (aberto === 'colchete') erros.push({ posicao: i, mensagem: t('catalogo.busca_erro_intervalo') });
    const inicio = i;
    i = fim;
    if (!token) { i += 1; continue; }
    if (OPERADORES.includes(token)) { partes.push({ tipo: 'operador', valor: token }); continue; }
    if (token === ':' || token.startsWith(':')) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_sem_campo') }); continue; }
    const doisPontos = token.startsWith('"') ? -1 : token.indexOf(':');
    if (doisPontos > 0) {
      const campo = token.slice(0, doisPontos).toLowerCase();
      const valor = token.slice(doisPontos + 1);
      if (!CAMPOS.includes(campo)) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_campo', { campo }) }); continue; }
      if (!valor) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_valor', { campo }) }); continue; }
      if (CAMPOS_NUMERO.includes(campo)) {
        const m = /^\[\s*(\S+)\s+TO\s+(\S+)\s*\]$/i.exec(valor);
        const numeros = m ? [m[1], m[2]] : [valor];
        const invalido = numeros.some((x) => x !== '*' && (Number.isNaN(Number(x.replace(',', '.'))) || Number(x.replace(',', '.')) < 0 || Number(x.replace(',', '.')) > 10));
        if (invalido) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_numero_0_10', { campo }) }); continue; }
        partes.push(m ? { tipo: 'intervalo', campo, de: m[1], ate: m[2] } : { tipo: 'campo', campo, valor });
      } else if (CAMPOS_DATA.includes(campo)) {
        const m = /^\[\s*(\S+)\s+TO\s+(\S+)\s*\]$/i.exec(valor);
        if (!m) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_intervalo') }); continue; }
        if (!DATA.test(m[1]) || !DATA.test(m[2])) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_data') }); continue; }
        partes.push({ tipo: 'intervalo', campo, de: m[1], ate: m[2] });
      } else if (campo === 'id' || campo === 'grupo') {
        if (!UUID.test(valor)) { erros.push({ posicao: inicio, mensagem: t('catalogo.busca_erro_uuid', { campo }) }); continue; }
        partes.push({ tipo: 'campo', campo, valor });
      } else partes.push({ tipo: 'campo', campo, valor: valor.replace(/^"|"$/g, '') });
      termos += 1;
      continue;
    }
    termos += 1;
    partes.push({ tipo: token.startsWith('-') ? 'negado' : 'termo', valor: token.replace(/^-/, '').replace(/^"|"$/g, '') });
  }
  if (parenteses > 0) erros.push({ posicao: texto.length, mensagem: t('catalogo.busca_erro_parentese') });
  if (termos > 200) erros.push({ posicao: 0, mensagem: t('catalogo.busca_erro_termos', { max: 200 }) });
  if (texto.length > 1000) erros.push({ posicao: 0, mensagem: t('catalogo.busca_erro_tamanho', { max: 1000 }) });
  return { ok: erros.length === 0, erros, partes, termos };
}

/* exemplos clicáveis da ajuda: [consulta, chave i18n da explicação] */
export const EXEMPLOS = [
  ['titulo:municipio', 'catalogo.busca_ex_titulo'],
  ['tags:ibge tipo:camada_vetorial', 'catalogo.busca_ex_tags_tipo'],
  ['"setor censitario"', 'catalogo.busca_ex_frase'],
  ['rodovia OR ferrovia', 'catalogo.busca_ex_ou'],
  ['municipio -limite', 'catalogo.busca_ex_negado'],
  ['modificado:[2026-08 TO *]', 'catalogo.busca_ex_modificado'],
  ['dono:maria status:autoritativo', 'catalogo.busca_ex_dono_status'],
  ['criado:[2026-01-01 TO 2026-03-31] acesso:inquilino', 'catalogo.busca_ex_criado'],
];
