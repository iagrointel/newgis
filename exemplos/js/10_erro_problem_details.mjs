// Formato de erro da API: RFC 9457 (application/problem+json) com os campos da casa junto
import { chamar, exigir } from "./_apoio.mjs";

const { status, cabecalhos, objeto } = await chamar("/api/eu", { chave: "plat_" + "z".repeat(43) });
exigir(status === 401, `esperava 401 com chave inválida, veio ${status}: ${JSON.stringify(objeto)}`);
const tipo = cabecalhos.get("content-type") ?? "";
exigir(tipo.includes("application/problem+json"), `esperava application/problem+json, veio ${tipo}`);
for (const campo of ["type", "title", "status", "detail", "instance", "erro", "mensagem", "req_id"]) {
  exigir(campo in objeto, `Problem Details sem o campo ${campo}: ${Object.keys(objeto).sort().join(",")}`);
}
exigir(objeto.status === 401, `campo status divergente do HTTP: ${objeto.status} != 401`);
console.log(`${objeto.type} -> ${objeto.detail} (req_id ${objeto.req_id})`);
