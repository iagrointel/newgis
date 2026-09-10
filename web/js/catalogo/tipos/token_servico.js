/* plat · catálogo — token de serviço reciclável por nome, usado pelos painéis de tipo (camada_vetorial.js,
   raster.js) para montar URL de compartilhamento externo (WFS/OGC/Esri/raster: essas portas não aceitam
   cookie de sessão, só Authorization: Bearer ou ?token=). Antes de cunhar, revoga qualquer token vivo do
   MESMO nome (mesmo padrão do TileJSON do mapa em app/mapa/rotas.py): um usuário nunca acumula um token por
   visita ao painel. Cache em memória por nome — um recarregamento de página cunha de novo, de propósito
   (o valor do token só existe na resposta de criação; não há como reler depois). */
import { obter, enviar, apagar } from '../../base/api.js';

const cache = new Map();

export async function tokenServico(nome, escopos, validadeDias = 365) {
  if (cache.has(nome)) return cache.get(nome);
  const promessa = (async () => {
    const rLista = await obter('/api/tokens');
    if (rLista.status === 200) {
      const antigo = (rLista.json || []).find((tk) => tk.nome === nome && !tk.revogado_em);
      if (antigo) { try { await apagar(`/api/tokens/${antigo.id}`); } catch { /* segue e cunha mesmo assim */ } }
    }
    const r = await enviar('/api/tokens', { nome, escopos, validade_dias: validadeDias });
    if (r.status !== 201) throw new Error((r.json && r.json.mensagem) || 'não foi possível preparar o link de serviço');
    return r.json.token;
  })();
  cache.set(nome, promessa);
  try {
    return await promessa;
  } catch (e) {
    cache.delete(nome);
    throw e;
  }
}
