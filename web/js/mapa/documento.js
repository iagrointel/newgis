/* plat · mapa — documento de mapa no navegador (item L2-01-a-documento-mapa). Módulo ES sem build; nunca ?v=
   no import (duas instâncias do módulo quebram o estado). Este arquivo NÃO desenha nada: ele carrega
   `GET /api/mapas/{id}/completo?incluir_documento=true` (uma chamada: documento + camadas resolvidas) e
   devolve o documento de volta com `PUT /api/mapas/{id}`, preservando cada campo que a tela não edita.

   A ordem da lista `corpo.camadas` é a ordem de desenho, do fundo para o topo — a mesma convenção do
   `layers` da Style Spec do MapLibre. O painel mostra o topo primeiro (é como o usuário lê uma legenda),
   então a lista da tela é o INVERSO da lista do documento; a conversão mora aqui, num lugar só. */
import { obter, alterar } from '../base/api.js';

export async function carregar(id) {
  const { status, json } = await obter(`/api/mapas/${encodeURIComponent(id)}/completo?incluir_documento=true`);
  if (status !== 200) return { erro: json };
  return { completo: json, documento: json.documento };
}

/** camadas do topo para o fundo (ordem de leitura do painel), já resolvidas pelo servidor */
export function camadasDoTopo(completo) {
  return [...(completo.camadas || [])].reverse();
}

/** grava a ordem nova: recebe os ids locais do topo para o fundo e devolve o documento gravado */
export async function salvarOrdem(id, documento, idsDoTopo) {
  const camadas = documento?.corpo?.camadas || [];
  const porId = new Map(camadas.map((c) => [c.id, c]));
  const novas = [...idsDoTopo].reverse().map((cid) => porId.get(cid)).filter(Boolean);
  if (novas.length !== camadas.length) return { erro: { erro: 'ordem_incompleta', mensagem: 'ordem incompleta' } };
  const corpo = { ...documento, corpo: { ...documento.corpo, camadas: novas } };
  const { status, json } = await alterar(`/api/mapas/${encodeURIComponent(id)}`, { dados: corpo });
  if (status !== 200) return { erro: json };
  return { item: json, documento: json.dados };
}

/** liga/desliga a visibilidade de uma camada no documento (não grava; quem grava é salvarDocumento) */
export function alternarVisivel(documento, idLocal) {
  const camadas = (documento?.corpo?.camadas || []).map((c) =>
    c.id === idLocal ? { ...c, visivel: c.visivel === false } : c);
  return { ...documento, corpo: { ...documento.corpo, camadas } };
}

export async function salvarDocumento(id, documento) {
  const { status, json } = await alterar(`/api/mapas/${encodeURIComponent(id)}`, { dados: documento });
  if (status !== 200) return { erro: json };
  return { item: json, documento: json.dados };
}
