/* plat · catálogo — chamadas à API do ADR 0004 seção 13 (e ao upload do ADR 0005 seção 3) sobre o cliente comum
   js/base/api.js. Único módulo do catálogo com URL. Erro vira exceção ErroApi {status, codigo, detalhe, reqId};
   401 chama o tratador registrado por definirSemSessao. Parâmetros de lista com valor em array repetem a chave
   (tipo=a&tipo=b). Envio bruto (multipart da miniatura; octet-stream das partes do upload) não passa pelo cliente
   comum porque ele fixa Content-Type: application/json em toda escrita. */
import { chamar as chamarBase, normalizarErro } from '../base/api.js';

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
export function definirSemSessao(f) { aoSemSessao = typeof f === 'function' ? f : () => {}; }

function tratar(r) {
  if (r.status === 401) { aoSemSessao(r); throw new ErroApi(r); }
  if (r.status === 0 || r.status >= 400) throw new ErroApi(r);
  return r.json;
}

export async function chamar(metodo, url, corpo) {
  return tratar(await chamarBase(metodo, url, corpo));
}

/* PATCH não existe no cliente comum; mesma disciplina (same-origin, no-store, JSON) */
export const remendar = (url, corpo) => chamar('PATCH', url, corpo ?? {});

/* corpo bruto: Blob (parte de upload do ADR 0005) */
export async function enviarBruto(metodo, url, corpo, cabecalhos = {}) {
  let resp;
  try {
    resp = await fetch(url, { method: metodo, credentials: 'same-origin', cache: 'no-store', headers: cabecalhos, body: corpo });
  } catch {
    return tratar({ status: 0, json: normalizarErro(0, null, null) });
  }
  let json = null;
  if (resp.status !== 204 && (resp.headers.get('content-type') || '').includes('json')) {
    try { json = await resp.json(); } catch { json = null; }
  }
  if (resp.status >= 400) return tratar({ status: resp.status, json: normalizarErro(resp.status, json, resp.headers.get('X-Req-Id')) });
  return json ?? {};
}

/* ?a=1&tipo=x&tipo=y — ignora vazio, null, undefined e array vazio */
export function consulta(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue;
    if (Array.isArray(v)) { for (const x of v) if (x !== undefined && x !== null && x !== '') p.append(k, String(x)); continue; }
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

const id = (v) => encodeURIComponent(String(v));
const I = (itemId) => `/api/itens/${id(itemId)}`;

/* rotas publicadas no OpenAPI (conjunto de caminhos): a tela só mostra ação cuja rota existe (upload é do L0-04) */
export async function rotasPublicadas() {
  try { const r = await chamarBase('GET', '/api/openapi.json'); return new Set(Object.keys((r.json && r.json.paths) || {})); } catch { return new Set(); }
}

/* tipos */
export const tipos = () => chamar('GET', '/api/tipos-item');

/* itens */
export const listar = (filtros = {}) => chamar('GET', `/api/itens${consulta(filtros)}`);
export const facetas = (filtros = {}) => chamar('GET', `/api/itens/facetas${consulta(filtros)}`);
export const tagsSugerir = (q) => chamar('GET', `/api/itens/tags${consulta({ q })}`);
export const obter = (itemId) => chamar('GET', I(itemId));
export const criar = (corpo) => chamar('POST', '/api/itens', corpo);
export const substituir = (itemId, corpo) => chamar('PUT', I(itemId), corpo);
export const editar = (itemId, corpo) => remendar(I(itemId), corpo);
export const apagar = (itemId, cascata = false) => chamar('DELETE', `${I(itemId)}${cascata ? '?cascata=true' : ''}`);
export const lote = (corpo) => chamar('POST', '/api/itens/lote', corpo);
export const mover = (itemId, pastaId) => chamar('POST', `${I(itemId)}/mover`, { pasta_id: pastaId || null });
export const transferir = (corpo) => chamar('POST', '/api/itens/transferir', corpo);

/* miniatura */
export const miniaturaUrl = (itemId) => `${I(itemId)}/miniatura`;
/* miniatura em JSON base64 {conteudo, nome}: a escrita sob cookie exige application/json (ADR 0002 5.3); multipart entra com o L0-11 */
export async function miniaturaEnviar(itemId, arquivo) {
  const conteudo = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = () => rej(new Error('leitura do arquivo falhou')); r.readAsDataURL(arquivo); });
  return chamar('POST', `${I(itemId)}/miniatura`, { conteudo, nome: arquivo.name });
}
export const miniaturaGerar = (itemId) => chamar('POST', `${I(itemId)}/miniatura/gerar`);
export const miniaturaApagar = (itemId) => chamar('DELETE', `${I(itemId)}/miniatura`);

/* versões */
export const versoes = (itemId, filtros = {}) => chamar('GET', `${I(itemId)}/versoes${consulta(filtros)}`);
export const versao = (itemId, n, diffDe) => chamar('GET', `${I(itemId)}/versoes/${id(n)}${consulta({ diff_de: diffDe })}`);
export const versaoRestaurar = (itemId, n, comentario) => chamar('POST', `${I(itemId)}/versoes/${id(n)}/restaurar`, comentario ? { comentario } : {});
export const versaoPublicar = (itemId, n) => chamar('POST', `${I(itemId)}/versoes/${id(n)}/publicar`);

/* relações */
export const usadoPor = (itemId, profundidade = 2) => chamar('GET', `${I(itemId)}/usado-por${consulta({ profundidade })}`);
export const criadoAPartirDe = (itemId) => chamar('GET', `${I(itemId)}/criado-a-partir-de`);
export const ordemDeExclusao = (itemId) => chamar('GET', `${I(itemId)}/ordem-de-exclusao`);
export const relacoesDefinir = (itemId, relacoes) => chamar('PUT', `${I(itemId)}/relacoes`, { relacoes });

/* compartilhamento */
export const compartilhamento = (itemId) => chamar('GET', `${I(itemId)}/compartilhamento`);
export const compartilhar = (itemId, corpo) => chamar('PUT', `${I(itemId)}/compartilhamento`, corpo);
export const links = (itemId) => chamar('GET', `${I(itemId)}/links`);
export const linkCriar = (itemId, corpo) => chamar('POST', `${I(itemId)}/links`, corpo);
export const linkRevogar = (itemId, linkId) => chamar('DELETE', `${I(itemId)}/links/${id(linkId)}`);
export const compartilhado = (token) => chamar('GET', `/api/compartilhado/${id(token)}`);
export const compartilhadoMiniaturaUrl = (token, itemId) => `/api/compartilhado/${id(token)}/itens/${id(itemId)}/miniatura`;

/* pastas */
export const pastasArvore = () => chamar('GET', '/api/pastas/arvore');
export const pastaCriar = (nome, paiId) => chamar('POST', '/api/pastas', paiId ? { nome, pai_id: paiId } : { nome });
export const pastaEditar = (pastaId, corpo) => chamar('PUT', `/api/pastas/${id(pastaId)}`, corpo);
export const pastaApagar = (pastaId) => chamar('DELETE', `/api/pastas/${id(pastaId)}`);

/* categorias (só leitura nesta tela; a árvore editável é de /admin/categorias) */
export const categorias = () => chamar('GET', '/api/categorias');

/* favoritos */
export const favoritar = (itemId) => chamar('PUT', `/api/favoritos/${id(itemId)}`);
export const desfavoritar = (itemId) => chamar('DELETE', `/api/favoritos/${id(itemId)}`);

/* lixeira */
export const lixeira = (filtros = {}) => chamar('GET', `/api/lixeira${consulta(filtros)}`);
export const lixeiraRestaurar = (itemId) => chamar('POST', `/api/lixeira/${id(itemId)}/restaurar`);
export const lixeiraEsvaziar = (ids) => chamar('POST', '/api/lixeira/esvaziar', ids ? { ids } : {});

/* identidade (reuso das rotas do ADR 0002 para escolher grupo e usuário) */
export const meusGrupos = () => chamar('GET', '/api/grupos?meus=1&limite=200');
export const usuariosBuscar = (q) => chamar('GET', `/api/usuarios${consulta({ q, ativo: '1', limite: 20 })}`);

/* upload retomável (ADR 0005 seção 3): partes de parte_bytes em application/octet-stream; concluir cria o item 'arquivo' */
export const uploadIniciar = (corpo) => chamar('POST', '/api/uploads', corpo);
export const uploadParte = (uploadId, n, blob) => enviarBruto('PUT', `/api/uploads/${id(uploadId)}/partes/${n}`, blob, { 'Content-Type': 'application/octet-stream' });
export const uploadConcluir = (uploadId, inspecionar = true) => chamar('POST', `/api/uploads/${id(uploadId)}/concluir`, inspecionar ? {} : { inspecionar: false });
export const uploadAbortar = (uploadId) => chamar('DELETE', `/api/uploads/${id(uploadId)}`);
