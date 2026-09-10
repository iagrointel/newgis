// Coleções do catálogo externo OGC API Records (GET /ogc/records/collections, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/ogc/records/collections");
exigir(status === 200, `esperava 200 em /ogc/records/collections, veio ${status}: ${JSON.stringify(objeto)}`);
const colecoes = objeto.collections ?? [];
console.log(`${colecoes.length} coleção(ões) publicada(s) em OGC API Records`);
for (const c of colecoes) console.log(`  ${c.id}: ${c.title ?? ""}`);
