/* plat · tarefas — chamadas à API de jobs e agendas (ADR 0003 seção 9) sobre o cliente comum js/base/api.js
   (credentials same-origin, no-store, erro normalizado no formato D18 {erro, mensagem, detalhe?, req_id}).
   Aqui o erro vira exceção ErroApi para o chamador tratar por status; 401 chama o tratador de sessão
   registrado por definirSemSessao (a tela usa irParaLogin de js/auth/sessao.js). */
import { chamar as chamarBase, consulta } from '../base/api.js';

export { consulta };

export class ErroApi extends Error {
  constructor(resposta) {
    const j = (resposta && resposta.json) || {};
    super(j.mensagem || `erro ${resposta ? resposta.status : '?'}`);
    this.status = resposta ? resposta.status : 0;
    this.codigo = j.erro || null;
    this.detalhe = j.detalhe === undefined ? null : j.detalhe;
    this.reqId = j.req_id || null;
  }
}

let aoSemSessao = () => {};
export function definirSemSessao(f) {
  aoSemSessao = typeof f === 'function' ? f : () => {};
}

export async function chamar(metodo, url, corpo) {
  const r = await chamarBase(metodo, url, corpo);
  if (r.status === 401) {
    aoSemSessao(r);
    throw new ErroApi(r);
  }
  if (r.status === 0 || r.status >= 400) throw new ErroApi(r);
  return r.json;
}

const id = (v) => encodeURIComponent(String(v));

/* jobs */
export const listar = (filtros = {}) => chamar('GET', `/api/jobs${consulta(filtros)}`);
export const obter = (jobId) => chamar('GET', `/api/jobs/${id(jobId)}`);
export const criar = (tipo, parametros = {}, extras = {}) => chamar('POST', '/api/jobs', { tipo, parametros, ...extras });
export const cancelar = (jobId) => chamar('POST', `/api/jobs/${id(jobId)}/cancelar`);
export const repetir = (jobId, parametros) => chamar('POST', `/api/jobs/${id(jobId)}/repetir`, parametros ? { parametros } : {});
export const log = (jobId, apos = 0, limite = 500, nivel) =>
  chamar('GET', `/api/jobs/${id(jobId)}/log${consulta({ apos, limite, nivel })}`);
export const resumo = () => chamar('GET', '/api/jobs/resumo');
export const tipos = () => chamar('GET', '/api/jobs/tipos');

/* agendas */
export const agendas = {
  listar: (filtros = {}) => chamar('GET', `/api/agendas${consulta(filtros)}`),
  obter: (agendaId) => chamar('GET', `/api/agendas/${id(agendaId)}`),
  criar: (dados) => chamar('POST', '/api/agendas', dados),
  atualizar: (agendaId, dados) => chamar('PUT', `/api/agendas/${id(agendaId)}`, dados),
  apagar: (agendaId) => chamar('DELETE', `/api/agendas/${id(agendaId)}`),
  pausar: (agendaId) => chamar('POST', `/api/agendas/${id(agendaId)}/pausar`),
  retomar: (agendaId) => chamar('POST', `/api/agendas/${id(agendaId)}/retomar`),
  rodarAgora: (agendaId) => chamar('POST', `/api/agendas/${id(agendaId)}/rodar-agora`),
};
