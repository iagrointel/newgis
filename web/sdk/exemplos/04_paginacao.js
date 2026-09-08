/* Exemplo 4/10 — paginação: 7 itens com uma tag única, páginas de 3, todos() entrega os 7. */
import { DADOS_MAPA, comSessao, preparar } from './_comum.js';

preparar('04_paginacao', (ctx) => comSessao(ctx, 'sdk-js-exemplo-04', async (p) => {
  const tag = `sdkjs04-${Math.random().toString(16).slice(2, 8)}`;
  const criados = [];
  try {
    for (let i = 1; i <= 7; i++) {
      criados.push(await p.mapas.criar(`sdk js exemplo 04 — item ${i}`, { dados: DADOS_MAPA, tags: [tag] }));
    }
    const primeira = await p.itens.listar({ tags: tag, limite: 3 });
    ctx.escrever(`página 1: ${primeira.itens.length} itens, proximo_cursor ${primeira.proximo_cursor ? 'presente' : 'ausente'}`);
    if (primeira.itens.length !== 3 || !primeira.proximo_cursor) throw new Error('esperava 3 itens e um cursor');
    const vistos = [];
    for await (const it of p.itens.todos({ tags: tag, limite: 3 })) vistos.push(it.id);
    ctx.escrever(`todos(): ${vistos.length} itens em ${Math.ceil(vistos.length / 3)} páginas`);
    if (new Set(vistos).size !== 7) throw new Error(`esperava 7 ids distintos, veio ${vistos.length}`);
    return vistos;
  } finally {
    for (const it of criados) await p.itens.apagar(it.id);
    ctx.escrever(`${criados.length} itens apagados`);
  }
}));
