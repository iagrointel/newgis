/* plat · catálogo — painel do tipo 'camada_vetorial' (tipo_item.modulo_front), usado pelo painel do item
   (item.js) na aba Visão geral (prévia() → resumo + mapa) e na aba Compartilhamento (compartilhar() → URL de
   serviço). Reusa o que a rota do mapa já monta: `GET /api/mapa/camadas/{id}` devolve geometria/campos/
   n_feicoes/tilejson/estilo prontos (app/mapa/rotas.py); a prévia sob sessão não cunha token nenhum — quem
   cunha é a própria rota de tilejson, escopada só àquela camada, 12 h. As URLs da seção Compartilhar (WFS/
   OGC API Features/Esri FeatureServer) são para cliente EXTERNO (QGIS, ArcGIS, um script) e por isso levam
   um token de serviço de verdade (token_servico.js). */
import { h } from '../../base/dom.js';
import { obter } from '../../base/api.js';
import { botaoCopiar } from '../../base/dom.js';
import { t } from '../../base/i18n.js';
import { tokenServico } from './token_servico.js';

export const tipo = 'camada_vetorial';

/* mantido pelo contrato de tipo_item.modulo_front (ADR 0004 seção 15.1): abrir este tipo é ir ao mapa, onde
   a camada aparece na árvore de camadas do catálogo. */
export function abrir() { location.assign('/mapa'); }

function campoUrl(valor) {
  const entrada = h('input', { type: 'text', readonly: true, value: valor, class: 'campo-url', 'aria-label': valor });
  const bt = botaoCopiar(valor, entrada, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') });
  return h('div', { class: 'linha-url' }, entrada, bt);
}

function linha(rotulo, valor) {
  return h('div', { class: 'campo-linha' }, h('div', { class: 'rotulo' }, rotulo), h('div', { class: 'valor' }, valor));
}

/* ---------- Visão geral: resumo + prévia no mapa ---------- */
export async function previa(item) {
  const raiz = h('div', { class: 'tipo-previa tipo-camada-vetorial' });
  let ficha;
  try {
    ficha = await obter(`/api/mapa/camadas/${encodeURIComponent(item.id)}`);
  } catch {
    ficha = { status: 0 };
  }
  if (ficha.status !== 200) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.erro_ficha')));
    return raiz;
  }
  const f = ficha.json;
  const campos = h(
    'div', { class: 'tipo-resumo' },
    linha(t('tipo_camada.geometria'), f.geometria),
    linha(t('tipo_camada.srid'), f.srid ?? '—'),
    linha(t('tipo_camada.n_feicoes'), f.n_feicoes === null || f.n_feicoes === undefined ? t('tipo_camada.n_feicoes_desconhecido') : f.n_feicoes.toLocaleString('pt-BR')),
    linha(t('tipo_camada.campos'), t('tipo_camada.campos_n', { n: (f.campos || []).length })),
  );
  raiz.append(campos);
  if (!f.servivel || !f.tilejson) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_camada.sem_previa')));
    return raiz;
  }
  const mapaEl = h('div', { class: 'tipo-mapa', 'aria-label': t('tipo_camada.previa_mapa') });
  raiz.append(mapaEl);
  try {
    const rTj = await obter(f.tilejson);
    if (rTj.status !== 200) throw new Error(rTj.json?.mensagem || 'tilejson');
    montarMapaVetor(mapaEl, rTj.json, f);
  } catch {
    mapaEl.replaceWith(h('p', { class: 'fraco' }, t('tipo_camada.erro_previa')));
  }
  return raiz;
}

function montarMapaVetor(container, tileJson, ficha) {
  if (!window.maplibregl) { container.replaceWith(h('p', { class: 'fraco' }, t('tipo_camada.erro_previa'))); return; }
  const fonteId = `plat-${ficha.id}`;
  const layers = Array.isArray(ficha.estilo) ? ficha.estilo : [];
  const map = new window.maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: { [fonteId]: { type: 'vector', tiles: tileJson.tiles, bounds: tileJson.bounds, minzoom: tileJson.minzoom ?? 0, maxzoom: tileJson.maxzoom ?? 20 } },
      layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#eef1ee' } }, ...layers],
    },
    interactive: true,
    attributionControl: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.on('load', () => {
    const b = tileJson.bounds;
    if (Array.isArray(b) && b.length === 4) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { animate: false, padding: 16 });
  });
}

/* ---------- Compartilhamento: URL de serviço para cliente externo ---------- */
export async function compartilhar(item) {
  const raiz = h('div', { class: 'tipo-compartilhar' });
  let tk;
  try {
    tk = await tokenServico(`svc-camada:${item.id}`, [`camada:ler:${item.id}`]);
  } catch (e) {
    raiz.append(h('p', { class: 'erro' }, e.message));
    return raiz;
  }
  const origem = location.origin;
  const q = (url) => `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(tk)}`;
  raiz.append(
    h('p', { class: 'fraco' }, t('tipo_camada.compartilhar_ajuda')),
    linha('WFS · GetCapabilities', campoUrl(q(`${origem}/wfs/${item.id}?SERVICE=WFS&REQUEST=GetCapabilities`))),
    linha('OGC API Features', campoUrl(q(`${origem}/ogc/features/${item.id}/collections`))),
    linha('Esri FeatureServer', campoUrl(q(`${origem}/rest/services/${item.id}/FeatureServer/0/query?where=1%3D1&f=json`))),
    h('p', {}, h('a', { href: '/mapa', class: 'pequeno' }, t('tipo_camada.abrir_no_mapa'))),
  );
  return raiz;
}
