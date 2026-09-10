/* Exemplo 3/10 — criar um item (mapa), editar parcialmente (PATCH) e apagar. */
import { DADOS_MAPA, comSessao, preparar } from './_comum.js';

preparar('03_criar_atualizar_apagar', (ctx) => comSessao(ctx, 'sdk-js-exemplo-03', async (p) => {
  const item = await p.mapas.criar('sdk js exemplo 03 — mapa de teste', { dados: DADOS_MAPA, tags: ['sdk-js'] });
  ctx.escrever(`criado: ${item.id} (${item.tipo}) "${item.titulo}"`);
  try {
    const editado = await p.itens.atualizar(item.id, { titulo: 'sdk js exemplo 03 — renomeado', resumo: 'editado pelo SDK JS' });
    if (editado.titulo !== 'sdk js exemplo 03 — renomeado') throw new Error('PATCH não aplicou o título');
    ctx.escrever(`atualizado: "${editado.titulo}" (versão ${editado.versao_atual})`);
    const lido = await p.itens.obter(item.id);
    if (lido.resumo !== 'editado pelo SDK JS') throw new Error('resumo não persistiu');
    return lido;
  } finally {
    await p.itens.apagar(item.id);
    ctx.escrever(`apagado: ${item.id}`);
  }
}));
