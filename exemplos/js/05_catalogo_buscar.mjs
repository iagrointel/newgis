// Busca por texto no catálogo, paginando de 20 em 20 (GET /api/itens?q=, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const termo = process.argv[2] ?? "a";
let vistos = 0;
let deslocamento = 0;
for (;;) {
  const { status, objeto } = await chamar(`/api/itens?q=${encodeURIComponent(termo)}&limite=20&deslocamento=${deslocamento}`);
  exigir(status === 200, `esperava 200 na busca, veio ${status}: ${JSON.stringify(objeto)}`);
  const pagina = objeto.itens ?? [];
  vistos += pagina.length;
  if (pagina.length < 20 || vistos >= 100) break;
  deslocamento += 20;
}
console.log(`busca por ${JSON.stringify(termo)}: ${vistos} item(ns) percorrido(s) em páginas de 20`);
