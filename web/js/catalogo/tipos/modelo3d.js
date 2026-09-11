/* plat · catálogo — painel do tipo 'modelo3d' (tipo_item.modulo_front), usado pelo painel do item (item.js) na
   aba Visão geral (prévia() → resumo, sem embutir o visualizador 3D inteiro no painel lateral — pesado demais
   para uma prévia; "abrir em 3D" leva à tela cheia /modelo/{id}). Sem compartilhar(): o modelo 3D ainda não
   tem porta de serviço externo nesta passagem (a mesma regra honesta de "aditivo, não prometido" do raster.js
   antes do TiTiler existir). */
import { h } from '../../base/dom.js';
import { obter } from '../../base/api.js';
import { t } from '../../base/i18n.js';
import { bytes } from '../formato.js';

export const tipo = 'modelo3d';

export function abrir(item) { location.assign(`/modelo/${encodeURIComponent(item.id)}`); }

function linha(rotulo, valor) {
  return h('div', { class: 'campo-linha' }, h('div', { class: 'rotulo' }, rotulo), h('div', { class: 'valor' }, valor));
}

const ROTULO_ORIGEM = {
  ifc_convertido: 'tipo_modelo3d.origem_ifc',
  xkt_enviado: 'tipo_modelo3d.origem_xkt',
  amostra_gabarito: 'tipo_modelo3d.origem_gabarito',
};

export async function previa(item) {
  const raiz = h('div', { class: 'tipo-previa tipo-modelo3d' });
  const r = await obter(`/api/modelo3d/${encodeURIComponent(item.id)}`);
  if (r.status !== 200) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_modelo3d.erro_ficha')));
    return raiz;
  }
  const m = r.json;
  raiz.append(h(
    'div', { class: 'tipo-resumo' },
    linha(t('tipo_modelo3d.origem'), ROTULO_ORIGEM[m.origem] ? t(ROTULO_ORIGEM[m.origem]) : (m.origem || '—')),
    linha(t('tipo_modelo3d.tamanho'), bytes(m.bytes_xkt)),
    ...(m.n_ambientes != null ? [linha(t('tipo_modelo3d.ambientes'), m.n_ambientes)] : []),
    ...(m.n_elementos != null ? [linha(t('tipo_modelo3d.elementos'), m.n_elementos)] : []),
  ));
  raiz.append(h('p', {}, h('a', { href: `/modelo/${encodeURIComponent(item.id)}`, class: 'pequeno' }, t('tipo_modelo3d.abrir_3d'))));
  return raiz;
}
