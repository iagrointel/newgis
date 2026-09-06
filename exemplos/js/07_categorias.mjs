// Vocabulário de categorias do inquilino (GET /api/categorias, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/api/categorias");
exigir(status === 200, `esperava 200 em /api/categorias, veio ${status}: ${JSON.stringify(objeto)}`);
const lista = Array.isArray(objeto) ? objeto : (objeto.categorias ?? []);
console.log(`${lista.length} categoria(s)`);
for (const c of lista.slice(0, 20)) console.log("  " + (typeof c === "object" ? c.nome : c));
