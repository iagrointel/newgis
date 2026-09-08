/* Exemplo 6/10 — criar um job de diagnóstico do próprio produto (prova.progresso) e esperar com tempo-limite.
   Sem worker vivo o job fica "pendente" para sempre: o e2e sobe um worker de verdade. */
import { comSessao, preparar } from './_comum.js';

preparar('06_jobs', (ctx) => comSessao(ctx, 'sdk-js-exemplo-06', async (p) => {
  const tipos = await p.jobs.tipos();
  ctx.escrever(`${tipos.length} tipo(s) de job cadastrados`);
  const job = await p.jobs.criar('prova.progresso', { passos: 3, duracao_s: 1 });
  ctx.escrever(`job criado: ${job.id}`);
  const fim = await p.jobs.esperar(job.id, { tempoLimiteMs: 30000, intervaloMs: 500 });
  if (fim.estado !== 'concluido') throw new Error(`job terminou em ${fim.estado}`);
  ctx.escrever(`job ${fim.estado}: progresso=${fim.progresso}`);
  return fim;
}));
