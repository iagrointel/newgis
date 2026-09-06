// Versão da plataforma sem chave nenhuma (GET /api/versao, escopo publico)
import { chamar, exigir } from "./_apoio.mjs";

const { status, objeto } = await chamar("/api/versao", { chave: "" });
exigir(status === 200, `esperava 200 em /api/versao, veio ${status}`);
exigir("versao" in objeto, `resposta sem o campo versao: ${JSON.stringify(objeto)}`);
console.log(`plat versao ${objeto.versao}`);
