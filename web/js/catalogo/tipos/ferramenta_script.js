/* plat · catálogo — módulo de abertura do tipo 'ferramenta_script' (tipo_item.modulo_front, item
   L2-16-c): abre a tela /ferramentas?item=<id>, que renderiza o formulário gerado do cabeçalho
   e executa por job. */
export const tipo = 'ferramenta_script';
export function abrir(item) { location.assign(`/ferramentas?item=${encodeURIComponent(item.id)}`); }
