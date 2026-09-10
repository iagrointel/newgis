/* Exemplo 5/10 — tokens de serviço: criar com escopo, usar, ver o log, revogar, e a mensagem do token revogado
   (refutação do item: "usa token revogado e confere a mensagem"). */
import { ErroPlataforma, Plataforma, comSessao, preparar } from './_comum.js';

preparar('05_tokens_de_servico', (ctx) => comSessao(ctx, 'sdk-js-exemplo-05', async (p) => {
  const tk = await p.tokens.criar('sdk-js-exemplo-05-leitura', ['catalogo:ler'], { validadeDias: 1 });
  ctx.escrever(`token ${tk.id} criado com escopos ${tk.escopos.join(',')}`);
  const leitor = new Plataforma(ctx.url, tk.token);
  const pagina = await leitor.itens.listar({ limite: 1 });
  ctx.escrever(`leitor lê o catálogo: ${pagina.total} item(ns)`);
  const lista = await p.tokens.listar();
  if (!lista.some((t) => t.id === tk.id)) throw new Error('token criado não aparece em listar()');
  const log = await p.tokens.log(tk.id);
  ctx.escrever(`log do token: ${log.length} acesso(s)`);
  await p.tokens.revogar(tk.id);
  try {
    await leitor.eu();
    throw new Error('token revogado ainda autentica');
  } catch (e) {
    if (!(e instanceof ErroPlataforma) || e.tipo !== 'token_revogado' || e.status !== 401) throw e;
    ctx.escrever(`token revogado: ${e.status} ${e.tipo} — "${e.titulo}"`);
    return e.toProblemDetails();
  }
}));
