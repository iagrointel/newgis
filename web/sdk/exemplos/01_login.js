/* Exemplo 1/10 — login por usuário e senha, primeiro token de serviço; depois `eu()` por Bearer. */
import { Plataforma, preparar } from './_comum.js';

preparar('01_login', async ({ url, inquilino, login, senha, escrever }) => {
  const p = await Plataforma.entrar(url, inquilino, login, senha, { nomeToken: 'sdk-js-exemplo-01' });
  try {
    const eu = await p.eu();
    if (eu.login !== login) throw new Error(`eu.login ${eu.login} != ${login}`);
    if (!p.token.startsWith('plat_')) throw new Error('token sem prefixo plat_');
    escrever(`login ok: ${eu.login} (inquilino ${eu.inquilino.nome}, perfil ${eu.perfil})`);
    escrever(`token de serviço criado (id ${p.tokenId}); ${p}`); // toString nunca imprime o token
    return eu;
  } finally {
    await p.sair();
    escrever('token revogado; sessão encerrada');
  }
});
