/* plat · catálogo — painel do tipo 'raster' (tipo_item.modulo_front), usado pelo painel do item (item.js) na
   aba Visão geral (prévia() → resumo + mapa) e na aba Compartilhamento (compartilhar() → URL de serviço). A
   porta de serviço (`/svc/<token>/raster/<item>/...`, app/imagens/rotas_tiles.py) não aceita cookie de sessão
   de propósito — é a porta para QGIS/ArcGIS/navegador de terceiro — então tanto a prévia quanto a seção
   Compartilhar usam o MESMO token de serviço reciclável (token_servico.js), nunca um por carregamento. */
import { h, limpar } from '../../base/dom.js';
import { obter } from '../../base/api.js';
import { botaoCopiar } from '../../base/dom.js';
import { t } from '../../base/i18n.js';
import { bytes } from '../formato.js';
import { tokenServico, renovarTokenServico } from './token_servico.js';

export const tipo = 'raster';

export function abrir() { location.assign('/mapa'); }

function campoUrl(valor) {
  const entrada = h('input', { type: 'text', readonly: true, value: valor, class: 'campo-url', 'aria-label': valor });
  const bt = botaoCopiar(valor, entrada, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') });
  return h('div', { class: 'linha-url' }, entrada, bt);
}

function linha(rotulo, valor) {
  return h('div', { class: 'campo-linha' }, h('div', { class: 'rotulo' }, rotulo), h('div', { class: 'valor' }, valor));
}

const NOME_TOKEN = (item) => `svc-raster:${item.id}`;
const ESCOPOS_TOKEN = ['imagens:ler'];

async function token(item) {
  return tokenServico(item, NOME_TOKEN(item), ESCOPOS_TOKEN);
}

/* ---------- Visão geral: resumo + prévia no mapa ---------- */
export async function previa(item) {
  const raiz = h('div', { class: 'tipo-previa tipo-raster' });
  const rImg = await obter(`/api/imagens/${encodeURIComponent(item.id)}`);
  if (rImg.status !== 200) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_raster.erro_ficha')));
    return raiz;
  }
  const im = rImg.json;
  raiz.append(h(
    'div', { class: 'tipo-resumo' },
    linha(t('tipo_raster.colecao'), im.colecao || '—'),
    linha(t('tipo_raster.epsg'), im.epsg ?? '—'),
    linha(t('tipo_raster.bandas'), t('tipo_raster.bandas_n', { n: (im.bandas || []).length })),
    linha(t('tipo_raster.tamanho'), bytes(im.tamanho_bytes)),
    linha(t('tipo_raster.bbox'), Array.isArray(im.bbox) ? im.bbox.map((v) => v.toFixed(4)).join(', ') : '—'),
  ));
  const mapaEl = h('div', { class: 'tipo-mapa', 'aria-label': t('tipo_raster.previa_mapa') });
  raiz.append(mapaEl);
  try {
    const tk = await token(item);
    const rTj = await obter(`/svc/${tk}/raster/${item.id}/tilejson.json`);
    if (rTj.status !== 200) throw new Error(rTj.json?.mensagem || 'tilejson');
    montarMapaRaster(mapaEl, rTj.json);
  } catch {
    mapaEl.replaceWith(h('p', { class: 'fraco' }, t('tipo_raster.erro_previa')));
  }
  return raiz;
}

function montarMapaRaster(container, tileJson) {
  if (!window.maplibregl) { container.replaceWith(h('p', { class: 'fraco' }, t('tipo_raster.erro_previa'))); return; }
  const map = new window.maplibregl.Map({
    container,
    style: {
      version: 8,
      sources: { raster: { type: 'raster', tiles: tileJson.tiles, tileSize: 256, bounds: tileJson.bounds, minzoom: tileJson.minzoom ?? 0, maxzoom: tileJson.maxzoom ?? 20 } },
      layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#eef1ee' } }, { id: 'raster', type: 'raster', source: 'raster' }],
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
function montarUrls(raiz, item, tk) {
  limpar(raiz);
  const origem = location.origin;
  const base = `${origem}/svc/${tk}/raster/${item.id}`;
  const aviso = h('p', { class: 'fraco' });
  const btRenovar = h('button', { type: 'button', class: 'pequeno' }, t('catalogo.servico_renovar'));
  btRenovar.addEventListener('click', async () => {
    btRenovar.disabled = true;
    try {
      const novo = await renovarTokenServico(item, NOME_TOKEN(item), ESCOPOS_TOKEN);
      montarUrls(raiz, item, novo);
      raiz.append(h('p', { class: 'fraco' }, t('catalogo.servico_renovado')));
    } catch (e) {
      aviso.textContent = e.message || t('catalogo.servico_erro_renovar');
      raiz.append(aviso);
    } finally {
      btRenovar.disabled = false;
    }
  });
  raiz.append(
    h('p', { class: 'fraco' }, t('tipo_raster.compartilhar_ajuda')),
    linha('TileJSON', campoUrl(`${base}/tilejson.json`)),
    linha('WMTS · GetCapabilities', campoUrl(`${base}/wmts/1.0.0/WMTSCapabilities.xml`)),
    linha(t('tipo_raster.tile_xyz'), campoUrl(`${base}/{z}/{x}/{y}.png`)),
    linha('STAC', campoUrl(`${origem}/svc/${tk}/stac/`)),
    h('p', {}, btRenovar),
    h('p', {}, h('a', { href: '/mapa', class: 'pequeno' }, t('tipo_raster.abrir_no_mapa'))),
  );
}

export async function compartilhar(item) {
  const raiz = h('div', { class: 'tipo-compartilhar' });
  let tk;
  try {
    tk = await token(item);
  } catch (e) {
    raiz.append(h('p', { class: 'erro' }, e.message));
    return raiz;
  }
  montarUrls(raiz, item, tk);
  return raiz;
}
