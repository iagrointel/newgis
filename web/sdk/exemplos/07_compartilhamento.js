/* Exemplo 7/10 — compartilhar um item com o inquilino inteiro e conferir. */
import { DADOS_MAPA, comSessao, preparar } from './_comum.js';

preparar('07_compartilhamento', (ctx) => comSessao(ctx, 'sdk-js-exemplo-07', async (p) => {
  const item = await p.mapas.criar('sdk js exemplo 07 — item a compartilhar', { dados: DADOS_MAPA });
  try {
    if (item.acesso !== 'privado') throw new Error(`acesso inicial ${item.acesso}`);
    await p.itens.compartilhar(item.id, { acesso: 'inquilino' });
    const estado = await p.itens.compartilhamento(item.id);
    if (estado.acesso !== 'inquilino') throw new Error(`acesso ${estado.acesso}`);
    ctx.escrever(`compartilhado: acesso=${estado.acesso}`);
    return estado;
  } finally {
    await p.itens.apagar(item.id);
  }
}));
