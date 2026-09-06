// Primeiros itens do catálogo do inquilino (GET /api/itens, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/api/itens?limite=5");
exigir(status === 200, `esperava 200 em /api/itens, veio ${status}: ${JSON.stringify(objeto)}`);
const itens = objeto.itens ?? (Array.isArray(objeto) ? objeto : []);
console.log(`total no catálogo: ${objeto.total ?? itens.length}; mostrando ${itens.length}`);
for (const item of itens) console.log(`  ${(item.tipo ?? "?").padEnd(14)} ${item.titulo ?? "(sem título)"}`);
