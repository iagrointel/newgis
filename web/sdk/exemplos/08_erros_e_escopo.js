/* Exemplo 8/10 — erros como Problem Details (RFC 9457) e escopo: token só de leitura não escreve. */
import { ErroPlataforma, Plataforma, comSessao, preparar } from './_comum.js';

preparar('08_erros_e_escopo', (ctx) => comSessao(ctx, 'sdk-js-exemplo-08', async (p) => {
  const saida = {};
  try {
    await p.itens.obter('00000000-0000-4000-8000-000000000000');
  } catch (e) {
    if (!(e instanceof ErroPlataforma) || e.status !== 404) throw e;
    saida.inexistente = e.toProblemDetails();
    ctx.escrever(`404 -> ${e.tipo}: ${e.titulo} (instance=${e.instancia})`);
  }
  const tk = await p.tokens.criar('sdk-js-exemplo-08-leitura', ['catalogo:ler']);
  try {
    const leitor = new Plataforma(ctx.url, tk.token);
    await leitor.itens.listar({ limite: 1 });
    try {
      await leitor.mapas.criar('sdk js exemplo 08 — não deveria criar', { dados: { esquema_versao: 1, corpo: {} } });
      throw new Error('token de leitura criou item');
    } catch (e) {
      if (!(e instanceof ErroPlataforma) || e.status !== 403 || e.tipo !== 'escopo_insuficiente') throw e;
      saida.escopo = e.toProblemDetails();
      ctx.escrever(`403 -> ${e.tipo}: ${e.titulo} detalhe=${JSON.stringify(e.detalhe)}`);
    }
  } finally {
    await p.tokens.revogar(tk.id);
  }
  return saida;
}));
