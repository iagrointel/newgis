/* plat · catálogo — token de serviço ESTÁVEL por item, usado pelos painéis de tipo (camada_vetorial.js,
   raster.js) para montar URL de compartilhamento externo (WFS/OGC/Esri/raster: essas portas não aceitam
   cookie de sessão, só Authorization: Bearer ou ?token=).

   Medido 10/09: a versão anterior revogava o token do MESMO nome e cunhava outro a cada carregamento de
   página — a URL que o usuário colou no QGIS ontem parava de funcionar hoje (12 tokens cunhados em 1 h de
   teste manual). Agora o token nasce UMA vez e o VALOR fica gravado no próprio item
   (`item.dados.servico`, PATCH /api/itens/{id}; esquema do tipo em db/migracoes/20260910T1500_
   item_servico_estavel.sql); reabrir o painel ou recarregar a página relê do item, nunca cunha de novo.
   Só `renovarTokenServico` troca o valor — de propósito, é o único jeito de revogar o link antigo.

   Risco aceito no beta: quem tem permissão de LER o item lê também o token gravado nele; o token em si só
   dá ESCOPO de leitura daquele item (nunca escrita, nunca outro item) — equivalente ao que a URL já expõe
   depois de copiada, então gravar o valor no item não abre superfície nova. */
import { obter, enviar, chamar } from '../../base/api.js';

const cache = new Map(); // por item.id — evita duas montagens simultâneas da mesma prévia cunharem 2×

async function salvarNoItem(item, servico) {
  const dadosNovo = { ...(item.dados || {}), servico };
  const r = await chamar('PATCH', `/api/itens/${encodeURIComponent(item.id)}`, { dados: dadosNovo });
  if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'não foi possível gravar o link no item');
  item.dados = r.json.dados; // reflete o item em memória para quem já o segura (item.js)
  return item.dados.servico;
}

async function cunhar(nome, escopos, validadeDias) {
  const r = await enviar('/api/tokens', { nome, escopos, validade_dias: validadeDias });
  if (r.status !== 201) throw new Error((r.json && r.json.mensagem) || 'não foi possível preparar o link de serviço');
  return { token_id: r.json.id, nome, token: r.json.token, criado_em: new Date().toISOString() };
}

/* Lê o token gravado no item; só cunha se o item ainda não tiver um (nome bate) — nunca revoga sozinho. */
export async function tokenServico(item, nome, escopos, validadeDias = 365) {
  const salvo = item?.dados?.servico;
  if (salvo && salvo.nome === nome && salvo.token) return salvo.token;
  const chave = `${item.id}:${nome}`;
  if (cache.has(chave)) return cache.get(chave);
  const promessa = (async () => {
    // corrida com outra aba/visita: relê o item antes de cunhar, pode já ter sido gravado nesse meio-tempo
    const rItem = await obter(`/api/itens/${encodeURIComponent(item.id)}`);
    if (rItem.status === 200) {
      item.dados = rItem.json.dados;
      const ja = item.dados && item.dados.servico;
      if (ja && ja.nome === nome && ja.token) return ja.token;
    }
    const servico = await cunhar(nome, escopos, validadeDias);
    const gravado = await salvarNoItem(item, servico);
    return gravado.token;
  })();
  cache.set(chave, promessa);
  try {
    return await promessa;
  } finally {
    cache.delete(chave);
  }
}

/* Botão "renovar link": troca o link por um novo, de propósito — é o único jeito de aposentar uma URL
   que vazou ou que não deveria mais circular. Usa POST /api/tokens/{id}/renovar quando há um token_id
   conhecido: o antigo ganha só 24 h de sobreposição (ADR 0002 seção 8, mesma regra de qualquer token de
   serviço), não é revogado na hora — quem já tinha a URL antiga não perde o acesso NO MESMO INSTANTE,
   mas para de funcionar em até 24 h. Sem token_id conhecido, cunha um novo do zero. */
export async function renovarTokenServico(item, nome, escopos, validadeDias = 365) {
  const salvo = item?.dados?.servico;
  let servico;
  if (salvo && salvo.token_id) {
    const r = await chamar('POST', `/api/tokens/${salvo.token_id}/renovar`);
    if (r.status !== 201) throw new Error((r.json && r.json.mensagem) || 'não foi possível renovar o link');
    servico = { token_id: r.json.id, nome, token: r.json.token, criado_em: new Date().toISOString() };
  } else {
    servico = await cunhar(nome, escopos, validadeDias);
  }
  const gravado = await salvarNoItem(item, servico);
  return gravado.token;
}
