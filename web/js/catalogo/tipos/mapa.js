/* plat · catálogo — módulo de abertura do tipo 'mapa' (tipo_item.modulo_front). Nesta versão abre a página do item;
   a linha dona do tipo troca este módulo pelo visualizador próprio sem mudar o registro. */
export const tipo = 'mapa';
export function abrir(item) { location.assign(`/conteudo/${encodeURIComponent(item.id)}`); }
