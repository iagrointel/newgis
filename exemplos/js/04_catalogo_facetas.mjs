// Contagem por tipo e por categoria, para montar um filtro (GET /api/itens/facetas, escopo catalogo:ler)
import { chamar, exigir, exigirChave } from "./_apoio.mjs";

exigirChave();
const { status, objeto } = await chamar("/api/itens/facetas");
exigir(status === 200, `esperava 200 em /api/itens/facetas, veio ${status}: ${JSON.stringify(objeto)}`);
exigir(objeto && typeof objeto === "object", "esperava um objeto de facetas");
for (const [nome, valores] of Object.entries(objeto)) {
  if (Array.isArray(valores)) console.log(`${nome}: ${valores.length} valor(es) distinto(s)`);
}
