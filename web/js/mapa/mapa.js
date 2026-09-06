/* plat · mapa — entrada da tela /mapa (item L2-01-a-basemap-local-pmtiles). Módulo ES sem build; cache resolvido
   por no-store no nginx: NUNCA ?v= nos imports. Requer sessão (ADR 0002, exigirSessao). MapLibre GL JS e o
   protocolo pmtiles vêm de <script> clássico (window.maplibregl / window.pmtiles, vendorizados em web/vendor/,
   VERSOES.txt) carregado ANTES deste módulo em mapa.html — os dois não são módulos ES.

   Mapa-base 100 % local: PMTiles estático (web/dados/basemap/guarulhos.pmtiles) lido por Range HTTP pelo próprio
   nginx do appliance (sem Martin, sem serviço de tiles dinâmico — isso é item futuro). Controles: navegação
   (zoom/pan, padrão MapLibre + arrastar/roda do mouse), escala, coordenadas do cursor (lê 'mousemove' do mapa) e
   seletor de camada base — mecanismo genérico por lista (BASES), uma opção hoje; a próxima base só entra na
   lista, o resto do fiação já funciona. body[data-pronto="1"] só depois do primeiro 'load' do mapa (o e2e espera
   por isso antes de tirar a captura que prova o canvas desenhado). */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from './estilo.js';
import { carregar as carregarMapa, camadasDoTopo, salvarOrdem, alternarVisivel, salvarDocumento } from './documento.js';
import { montarPainel } from './painel_camadas.js';

const BASES = [
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', arquivo: 'guarulhos.pmtiles' },
];

const el = (id) => document.getElementById(id);

function urlDado(arquivo) {
  return `${location.origin}/static/dados/basemap/${arquivo}`;
}

function montarSeletorBase(map) {
  const sel = el('seletor-base');
  for (const base of BASES) {
    const opt = document.createElement('option');
    opt.value = base.id;
    opt.textContent = t(base.rotuloChave);
    sel.append(opt);
  }
  sel.value = BASES[0].id;
  sel.addEventListener('change', () => {
    const base = BASES.find((b) => b.id === sel.value) || BASES[0];
    map.setStyle(construirEstilo(urlDado(base.arquivo)));
  });
}

function montarCoordenadas(map) {
  const caixa = el('coordenadas');
  const escrever = (lng, lat, zoom) => {
    caixa.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} · z${zoom.toFixed(1)}`;
  };
  const mostrarCentro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', mostrarCentro);
  map.on('zoomend', mostrarCentro);
  mostrarCentro();
}

/* Documento de mapa (item L2-01-a-documento-mapa): /mapa?id=<uuid> abre um mapa do catálogo. Sem `id` a tela
   segue sendo só o mapa-base local, como no item que a criou — nada de mapa de exemplo embutido. */
async function iniciarDocumento(map) {
  const id = new URLSearchParams(location.search).get('id');
  if (!id) return;
  const { completo, documento, erro } = await carregarMapa(id);
  if (erro) {
    el('aviso').erro(`${t('mapa.erro_documento')}: ${erro.mensagem}`);
    return;
  }
  let doc = documento;
  let ordem = camadasDoTopo(completo).map((c) => c.id);
  el('mapa-nome').textContent = completo.titulo;
  const painel = el('painel-camadas');
  painel.hidden = false;
  const salvar = el('salvar-mapa');
  salvar.hidden = false;
  if (!completo.camadas.length) {
    el('camadas').textContent = t('mapa.sem_camadas');
  } else {
    montarPainel({
      raiz: el('camadas'),
      camadas: camadasDoTopo(completo),
      aoReordenar: (ids) => { ordem = ids; salvar.dataset.sujo = '1'; },
      aoAlternarVisivel: (idLocal) => { doc = alternarVisivel(doc, idLocal); salvar.dataset.sujo = '1'; },
    });
  }
  salvar.addEventListener('click', async () => {
    salvar.disabled = true;
    const gravado = await (ordem.length ? salvarOrdem(id, doc, ordem) : salvarDocumento(id, doc));
    salvar.disabled = false;
    if (gravado.erro) {
      el('aviso').erro(`${t('mapa.erro_salvar')}: ${gravado.erro.mensagem}`);
      return;
    }
    doc = gravado.documento;
    delete salvar.dataset.sujo;
    el('aviso').ok(t('mapa.salvo'));
  });
  if (completo.extensao_inicial) {
    const [oeste, sul, leste, norte] = completo.extensao_inicial;
    map.fitBounds([[oeste, sul], [leste, norte]], { animate: false, padding: 20 });
  }
}


async function iniciarMapa() {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro(t('mapa.erro_biblioteca'));
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);

  const base = BASES[0];
  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(urlDado(base.arquivo)),
    center: [-46.593018, -23.493476], // centro do recorte (metadado do pmtiles, PROVENIENCIA.md)
    zoom: 13,
    attributionControl: false,
    hash: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new window.maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new window.maplibregl.AttributionControl({ compact: false }), 'bottom-right');

  montarSeletorBase(map);
  montarCoordenadas(map);

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  await iniciarDocumento(map);
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  try {
    await iniciarMapa();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
