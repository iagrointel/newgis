// Quem é o dono da chave e que escopos ela tem (GET /api/eu, escopo token:qualquer)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/api/eu");
exigir(status === 200, `esperava 200 em /api/eu, veio ${status}: ${JSON.stringify(objeto)}`);
exigir(objeto.token, "a resposta não traz o bloco token: a credencial usada foi sessão, não chave");
console.log(`chave ${JSON.stringify(objeto.token.nome)} do usuário ${objeto.login} no inquilino ${objeto.inquilino.slug}`);
console.log(`escopos: ${objeto.token.escopos.join(", ")}`);
console.log(`expira em: ${objeto.token.expira_em}`);
