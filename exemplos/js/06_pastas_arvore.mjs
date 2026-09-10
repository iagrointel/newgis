// Árvore de pastas do inquilino, impressa com recuo (GET /api/pastas/arvore, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

function imprimir(nos, nivel = 0) {
  for (const no of nos) {
    console.log("  ".repeat(nivel) + "- " + (no.nome ?? "(sem nome)"));
    imprimir(no.filhas ?? no.filhos ?? [], nivel + 1);
  }
}

exigirChave();
const { status, objeto } = await chamar("/api/pastas/arvore");
exigir(status === 200, `esperava 200 em /api/pastas/arvore, veio ${status}: ${JSON.stringify(objeto)}`);
const raiz = Array.isArray(objeto) ? objeto : (objeto.pastas ?? []);
console.log(`${raiz.length} pasta(s) na raiz`);
imprimir(raiz);
