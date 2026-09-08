/* plat · narrativa — bloco de mapa com VISTA SALVA (item L5-04-a-blocos-de-conteudo).

   A vista gravada no bloco é {bbox:[oeste, sul, leste, norte], centro, zoom, rotacao, proporcao, camadas}.
   O que faz o bbox reabrir igual em qualquer viewport (portão: bbox comparado, tolerância 1 %; refutação: dois
   viewports) é a PROPORÇÃO: o quadro do mapa recebe altura = largura × proporcao (a proporção do quadro em que
   o autor salvou), e `fitBounds(bbox, padding 0)` com zoom fracionário devolve exatamente a mesma caixa —
   centro e zoom são gravados só como reserva (mapa sem bbox de versões futuras) e para leitura humana.

   Camadas do catálogo (ids de item camada_vetorial) entram pelo mesmo `Catalogo` do visualizador
   (web/js/mapa/catalogo.js): TileJSON com token curto da sessão; sem sessão (página publicada anônima) a camada
   falha em silêncio e o mapa-base com a vista salva continua — o escopo de tile por token de publicação é a
   cláusula pendente do L5-14 (depende do L1-02), registrada no handoff. */
import { construirEstilo } from '../mapa/estilo.js';
import { Catalogo } from '../mapa/catalogo.js';

const BASE = '/static/dados/basemap/guarulhos.pmtiles';

function proporcaoDe(vista) {
  const p = Number(vista && vista.proporcao);
  return Number.isFinite(p) && p >= 0.2 && p <= 3 ? p : 0.6;
}

export function vistaAtual(map, camadas = []) {
  const b = map.getBounds();
  const c = map.getCenter();
  const el = map.getContainer();
  return {
    bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
    centro: [c.lng, c.lat],
    zoom: map.getZoom(),
    rotacao: map.getBearing(),
    proporcao: Math.round((el.clientHeight / Math.max(1, el.clientWidth)) * 1000) / 1000,
    camadas: [...camadas],
  };
}

/* aplica a vista: bbox por fitBounds (exato, zoom fracionário); sem bbox cai em centro/zoom */
export function aplicarVista(map, vista) {
  if (!vista) return;
  if (Array.isArray(vista.bbox) && vista.bbox.length === 4) {
    map.fitBounds([[vista.bbox[0], vista.bbox[1]], [vista.bbox[2], vista.bbox[3]]],
      { padding: 0, duration: 0, bearing: vista.rotacao || 0, maxZoom: 24 });
  } else if (Array.isArray(vista.centro)) {
    map.jumpTo({ center: vista.centro, zoom: vista.zoom ?? 10, bearing: vista.rotacao || 0 });
  }
}

/* quadro com a proporção salva: a largura é a da coluna de leitura, a altura segue a proporção */
export function dimensionar(quadro, vista) {
  quadro.style.aspectRatio = `1 / ${proporcaoDe(vista)}`;
  quadro.style.width = '100%';
}

/* monta um MapLibre no quadro; devolve {map, catalogo, pronto} — `pronto` resolve depois do 'load' e da vista */
export function montarMapa(quadro, { vista = null, interativo = true, camadas = [] } = {}) {
  const maplibregl = window.maplibregl;
  if (!maplibregl) throw new Error('MapLibre ausente: inclua /static/vendor/maplibre-gl-4.7.1.js antes do módulo');
  if (window.pmtiles && !montarMapa._protocolo) {
    montarMapa._protocolo = new window.pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', montarMapa._protocolo.tile);
  }
  dimensionar(quadro, vista);
  const map = new maplibregl.Map({
    container: quadro,
    style: construirEstilo(`${location.origin}${BASE}`),
    center: (vista && vista.centro) || [-46.593018, -23.493476],
    zoom: (vista && vista.zoom) || 11,
    attributionControl: false,
    interactive: interativo,
    hash: false,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
  if (interativo) map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  const catalogo = new Catalogo(map);
  const pronto = new Promise((resolve) => {
    map.once('load', async () => {
      aplicarVista(map, vista);
      try {
        await catalogo.carregar();
        for (const id of [...camadas].reverse()) {
          try { await catalogo.ligar(id); } catch { /* sem sessão ou sem tile: a vista fica, a camada não */ }
        }
      } catch { /* sem sessão: página publicada anônima */ }
      // a vista é reaplicada depois de ligar as camadas: addLayer não move o mapa, mas o fitBounds inicial pode
      // ter corrido antes de o quadro ter a altura final (fontes web) — aplicar de novo é idempotente
      aplicarVista(map, vista);
      resolve(map);
    });
  });
  return { map, catalogo, pronto };
}

/* deriva da vista salva, em fração (o teste e o adversário medem isto): máximo entre largura, altura e centro */
export function derivaDaVista(map, vista) {
  if (!vista || !Array.isArray(vista.bbox)) return null;
  const b = map.getBounds();
  const [o, s, l, n] = vista.bbox;
  const largura = l - o;
  const altura = n - s;
  return Math.max(
    Math.abs((b.getEast() - b.getWest()) - largura) / largura,
    Math.abs((b.getNorth() - b.getSouth()) - altura) / altura,
    Math.abs(((b.getEast() + b.getWest()) / 2) - (o + l) / 2) / largura,
    Math.abs(((b.getNorth() + b.getSouth()) / 2) - (s + n) / 2) / altura,
  );
}
