/* plat · render — entrada da página headless do motor de render (item L2-12-a-motor-render-servidor). Módulo ES
   servido do mesmo `web/` do visualizador (`estilo.js` é o MESMO arquivo de web/js/mapa/mapa.js: WYSIWYG de
   verdade, não uma cópia). Sem `exigirSessao`, sem `fetch` de documento — o servidor já resolveu tudo antes de
   navegar aqui; esta página só desenha. `bbox`/`zoom`/`centro` vêm da query string (todos opcionais).

   Sinal de pronto: `body[data-pronto="1"]` só depois de `map.once('idle')` (tiles carregadas e desenhadas), não
   `'load'` (que dispara antes das tiles chegarem) — é o que o motor espera antes de tirar a captura. */
import { construirEstilo } from './estilo.js';

function urlDado(arquivo) {
  return `${location.origin}/static/dados/basemap/${arquivo}`;
}

function numero(nome) {
  const v = new URLSearchParams(location.search).get(nome);
  return v === null ? null : Number(v);
}

async function iniciar() {
  if (!window.maplibregl || !window.pmtiles) {
    document.body.dataset.erro = '1';
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);

  const zoom = numero('zoom') ?? 13;
  const lng = numero('lng') ?? -46.593018;
  const lat = numero('lat') ?? -23.493476;

  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(urlDado('guarulhos.pmtiles')),
    center: [lng, lat],
    zoom,
    attributionControl: false,
    hash: false,
    preserveDrawingBuffer: true, // exigido para o screenshot do playwright ler o canvas depois do 'idle'
  });

  const oeste = numero('oeste');
  const sul = numero('sul');
  const leste = numero('leste');
  const norte = numero('norte');
  if (oeste !== null && sul !== null && leste !== null && norte !== null) {
    map.fitBounds([[oeste, sul], [leste, norte]], { animate: false, padding: 0 });
  }

  map.on('error', (ev) => {
    document.body.dataset.erro = String((ev && ev.error && ev.error.message) || ev);
  });

  await new Promise((resolve) => map.once('idle', resolve));
  document.body.dataset.pronto = '1';
}

iniciar();
