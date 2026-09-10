/* plat · catálogo — módulo de abertura do tipo 'camada_tracado' (tipo_item.modulo_front, item
   L4-02-f-resultados-e-exportacao). Abre a página do item, onde a procedência do traçado (rede,
   configuração, pontos de partida, versão da topologia e data) e a tabela do resultado já aparecem. */
export const tipo = 'camada_tracado';
export function abrir(item) { location.assign(`/conteudo/${encodeURIComponent(item.id)}`); }
