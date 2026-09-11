/* plat · catálogo — módulo de abertura do tipo 'ferramenta_script' (tipo_item.modulo_front, item
   L2-16-c): abre a tela /ferramenta?item=<id>, que renderiza o formulário gerado do cabeçalho
   e executa por job. (fusão 11/09: /ferramentas, no plural, é o catálogo de ferramentas — path
   próprio para não colidir.) */
export const tipo = 'ferramenta_script';
export function abrir(item) { location.assign(`/ferramenta?item=${encodeURIComponent(item.id)}`); }
