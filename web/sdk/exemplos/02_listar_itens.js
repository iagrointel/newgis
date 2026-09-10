/* Exemplo 2/10 — listar itens: uma página, todas as páginas (cursor embutido) e facetas. */
import { comSessao, preparar } from './_comum.js';

preparar('02_listar_itens', (ctx) => comSessao(ctx, 'sdk-js-exemplo-02', async (p) => {
  const pagina = await p.itens.listar({ limite: 5 });
  ctx.escrever(`primeira página: ${pagina.itens.length} de ${pagina.total} item(ns)`);
  for (const it of pagina.itens) ctx.escrever(`  ${it.tipo}  ${it.titulo}`);
  let n = 0;
  for await (const it of p.itens.todos({ limite: 5 })) { n += 1; if (n >= 50) break; }
  ctx.escrever(`todos(): ${n} item(ns) percorridos sem ler proximo_cursor`);
  const facetas = await p.itens.facetas();
  ctx.escrever(`facetas por tipo: ${facetas.tipo.map((f) => `${f.valor}=${f.n}`).join(', ')}`);
  return { total: pagina.total, percorridos: n };
}));
