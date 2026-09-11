/* plat · catálogo — painel do tipo 'foto360' (tipo_item.modulo_front): mesma ideia de tipos/modelo3d.js, só
   que sem conversão nenhuma (a origem já é o JPEG enviado) — "abrir em 3D" leva ao mesmo /modelo/{id}, com
   ?tipo=foto360 para a página escolher o pannellum em vez do xeokit. */
import { h } from '../../base/dom.js';
import { t } from '../../base/i18n.js';

export const tipo = 'foto360';

export function abrir(item) { location.assign(`/modelo/${encodeURIComponent(item.id)}?tipo=foto360`); }

export async function previa(item) {
  const raiz = h('div', { class: 'tipo-previa tipo-foto360' });
  raiz.append(h('p', { class: 'fraco' }, t('tipo_foto360.ajuda')));
  raiz.append(h('p', {}, h('a', { href: `/modelo/${encodeURIComponent(item.id)}?tipo=foto360`, class: 'pequeno' }, t('tipo_foto360.abrir_360'))));
  return raiz;
}
