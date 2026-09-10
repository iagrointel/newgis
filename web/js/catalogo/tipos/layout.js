/* plat · catálogo — módulo de abertura do tipo 'layout' (tipo_item.modulo_front, item L2-12-b): abre o visualizador
   com o painel Layout carregado no item (o mapa do quadro é o que o layout guardou em mapa_id, ou o da tela). */
export const tipo = 'layout';
export function abrir(item) {
  const mapa = item && item.dados && item.dados.mapa_id ? `&mapa=${encodeURIComponent(item.dados.mapa_id)}` : '';
  location.assign(`/mapa?layout=${encodeURIComponent(item.id)}${mapa}`);
}
