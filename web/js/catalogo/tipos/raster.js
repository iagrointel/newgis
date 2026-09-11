/* plat · catálogo — painel do tipo 'raster' (tipo_item.modulo_front), usado pelo painel do item (item.js) na
   aba Visão geral (prévia() → resumo + mapa) e na aba Compartilhamento (compartilhar() → URL de serviço). A
   porta de serviço (`/svc/<token>/raster/<item>/...`, app/imagens/rotas_tiles.py) não aceita cookie de sessão
   de propósito — é a porta para QGIS/ArcGIS/navegador de terceiro — então tanto a prévia quanto a seção
   Compartilhar usam o MESMO token de serviço reciclável (token_servico.js), nunca um por carregamento. */
import { h, limpar } from '../../base/dom.js';
import { obter, enviar } from '../../base/api.js';
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
  raiz.append(painelProveniencia(item, im.proveniencia));
  const mapaEl = h('div', { class: 'tipo-mapa', 'aria-label': t('tipo_raster.previa_mapa') });
  raiz.append(mapaEl);
  let tk;
  try {
    tk = await token(item);
    const rTj = await obter(`/svc/${tk}/raster/${item.id}/tilejson.json`);
    if (rTj.status !== 200) throw new Error(rTj.json?.mensagem || 'tilejson');
    const mapa = montarMapaRaster(mapaEl, rTj.json);
    raiz.append(await painelRenderizacao(item, tk, mapa));
  } catch {
    mapaEl.replaceWith(h('p', { class: 'fraco' }, t('tipo_raster.erro_previa')));
  }
  return raiz;
}

/* ---------- Proveniência: a cadeia de conversão em texto simples (item L1-01-j) ----------
   Nunca uma promessa em prosa: o que aparece aqui é o comando exato + o sha256 de entrada/saída de
   cada passo, tirado direto de `plat:cadeia` do item STAC — e um botão "Conferir" que baixa os
   objetos de novo e recalcula, no MESMO endpoint que `plat raster verificar` usa. */
function linhaComando(passo) {
  const comandos = (passo.comando || []).map((argv) => (Array.isArray(argv) ? argv.join(' ') : String(argv)));
  return h(
    'div', { class: 'proveniencia-passo' },
    h('p', { class: 'proveniencia-passo-titulo' }, passo.passo),
    ...comandos.map((c) => h('pre', { class: 'proveniencia-comando' }, c)),
    h('p', { class: 'fraco' }, t('tipo_raster.proveniencia_entrada_saida', {
      entrada: (passo.entrada_sha256 || '').slice(0, 16), saida: (passo.saida_sha256 || '').slice(0, 16),
    })),
  );
}

function painelProveniencia(item, prov) {
  const raiz = h('div', { class: 'tipo-proveniencia' });
  raiz.append(h('h4', {}, t('tipo_raster.proveniencia_titulo')));
  if (!prov || !prov.manifesto_sha256) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_raster.proveniencia_ausente')));
    return raiz;
  }
  const software = Object.entries(prov.processing_software || {}).map(([k, v]) => `${k} ${v}`).join(' · ');
  raiz.append(
    linha(t('tipo_raster.proveniencia_origem'), t(`tipo_raster.proveniencia_origem_${prov.cadeia_origem || 'ausente'}`)),
    linha(t('tipo_raster.proveniencia_software'), software || '—'),
  );
  if (Array.isArray(prov.cadeia) && prov.cadeia.length) {
    raiz.append(...prov.cadeia.map(linhaComando));
  } else {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_raster.proveniencia_sem_cadeia')));
  }
  raiz.append(linha('plat:manifesto_sha256', h('code', {}, prov.manifesto_sha256)));

  const resultado = h('div', { class: 'proveniencia-resultado' });
  const btConferir = h('button', { type: 'button', class: 'pequeno' }, t('tipo_raster.proveniencia_conferir'));
  btConferir.addEventListener('click', async () => {
    btConferir.disabled = true;
    limpar(resultado);
    resultado.append(h('p', { class: 'fraco' }, t('tipo_raster.proveniencia_conferindo')));
    try {
      const r = await enviar(`/api/imagens/${encodeURIComponent(item.id)}/conferir`);
      limpar(resultado);
      if (r.status !== 200) {
        resultado.append(h('p', { class: 'erro' }, t('tipo_raster.proveniencia_conferir_erro')));
        return;
      }
      const c = r.json;
      resultado.append(h(
        'p', { class: c.ok ? 'ok' : 'erro' },
        c.ok ? t('tipo_raster.proveniencia_ok', { n: c.ativos.length })
             : t('tipo_raster.proveniencia_divergente'),
      ));
      if (!c.ok) {
        resultado.append(...c.ativos.filter((a) => !a.ok).map((a) => h(
          'p', { class: 'fraco' }, `${a.asset}: ${a.erro || t('tipo_raster.proveniencia_sha_diverge')}`,
        )));
      }
    } catch {
      limpar(resultado);
      resultado.append(h('p', { class: 'erro' }, t('tipo_raster.proveniencia_conferir_erro')));
    } finally {
      btConferir.disabled = false;
    }
  });
  raiz.append(h('p', {}, btConferir), resultado);
  return raiz;
}

/* ---------- Renderização: predefinição (item L1-02-f) ----------
   Seção nova do painel do item raster: lista as 6 predefinições de fábrica + as CUSTOM do inquilino
   (GET /api/imagens/<item>/predefinicoes, sessão), troca a fonte do mapa (mesma predefinição = mesma
   query string, ver app/imagens/rotas_tiles.py::_consulta_render) e mostra a legenda (`legenda.png`) —
   nunca duas fontes de verdade: a imagem de legenda vem do MESMO endpoint que o WMS GetLegendGraphic. */
async function painelRenderizacao(item, tk, mapa) {
  const raiz = h('div', { class: 'tipo-renderizacao' });
  raiz.append(h('h4', {}, t('tipo_raster.renderizacao_titulo')));
  const r = await obter(`/api/imagens/${encodeURIComponent(item.id)}/predefinicoes`);
  if (r.status !== 200) {
    raiz.append(h('p', { class: 'fraco' }, t('tipo_raster.renderizacao_erro')));
    return raiz;
  }
  const opcoes = [
    { nome: '', titulo: t('tipo_raster.renderizacao_padrao') },
    ...r.json.fabrica.map((f) => ({ nome: f.nome, titulo: f.titulo })),
    ...r.json.custom.map((c) => ({ nome: c.nome, titulo: `${c.titulo}${c.padrao ? ' ★' : ''}` })),
  ];
  const select = h('select', { class: 'campo-select', 'aria-label': t('tipo_raster.renderizacao_titulo') },
    ...opcoes.map((o) => h('option', { value: o.nome }, o.titulo)));
  const legendaImg = h('img', { class: 'renderizacao-legenda', alt: t('tipo_raster.renderizacao_legenda'), hidden: true });
  const base = `${location.origin}/svc/${tk}/raster/${item.id}`;
  const aplicar = () => {
    const predef = select.value;
    const consulta = predef ? `?predef=${encodeURIComponent(predef)}` : '';
    const tiles = [`${base}/{z}/{x}/{y}.png${consulta}`];
    mapa?.getSource?.('raster')?.setTiles?.(tiles);
    if (predef) {
      legendaImg.src = `${base}/legenda.png?predef=${encodeURIComponent(predef)}`;
      legendaImg.hidden = false;
    } else {
      legendaImg.hidden = true;
    }
  };
  select.addEventListener('change', aplicar);
  raiz.append(
    h('p', { class: 'fraco' }, t('tipo_raster.renderizacao_ajuda')),
    h('div', { class: 'renderizacao-controle' }, select, legendaImg),
    linha(t('tipo_raster.renderizacao_url'), campoUrl(`${base}/{z}/{x}/{y}.png?predef=<nome>`)),
  );
  return raiz;
}

function montarMapaRaster(container, tileJson) {
  if (!window.maplibregl) {
    container.replaceWith(h('p', { class: 'fraco' }, t('tipo_raster.erro_previa')));
    return null;
  }
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
  return map;
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
