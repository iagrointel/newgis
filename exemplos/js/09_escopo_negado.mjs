// Prova de que uma chave de leitura NÃO escreve: POST /api/itens exige o escopo admin:inquilino
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/api/itens", {
  metodo: "POST",
  corpo: { tipo: "pasta", titulo: "não deve ser criado" },
});
exigir(status === 403, `esperava 403 (escopo insuficiente) e veio ${status}: ${JSON.stringify(objeto)}`);
exigir(objeto.erro === "escopo_insuficiente", `esperava erro escopo_insuficiente, veio ${objeto.erro}`);
console.log(`recusado como se espera: ${objeto.mensagem}`);
console.log(`exigido: ${objeto.detalhe.exigido}; a chave tem: ${objeto.detalhe.token_tem.join(", ")}`);
