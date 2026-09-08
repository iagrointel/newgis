/* plat · tela /redes/serie (item L4-15-serie-temporal-da-rede): o CONTROLE DE TEMPO do mapa.

   A série amarra várias safras da mesma rede (na BDGD, uma por ano). O controle deslizante anda pelas
   safras: a cada posição a tela busca `GET /api/rede-serie/{id}/mapa?ano=…` (os transformadores daquela
   safra, com o carregamento e a classe de linhagem em relação à safra anterior) e troca a fonte GeoJSON
   do mapa. Sem recarregar a página, sem outro mapa: uma camada, uma fonte, o ano é o que muda.

   A cor do ponto sai do carregamento: até 80 % folgado, 80-100 % atenção, acima de 100 % passou da
   potência nominal. Quando a safra tem a potência nominal marcada como não confiável (troca em massa de
   placa medida pela série), a tela mostra a ressalva ao lado do ano — o número aparece, mas nunca sozinho.

   Módulo ES sem build; cache resolvido por no-store no nginx: NUNCA ?v= nos imports. MapLibre GL e o
   protocolo pmtiles vêm de <script> clássico carregado antes deste módulo (window.maplibregl/window.pmtiles). */
import { obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from '../mapa/estilo.js';

const FONTE = 'serie-trafos';
const CAMADA = 'serie-trafos-ponto';
const CARGA_ATENCAO = 80;
const CARGA_SOBRECARGA = 100;
const VAZIO = { type: 'FeatureCollection', features: [] };

const el = (id) => document.getElementById(id);

let mapa = null;
let serieAtual = null;
let anos = [];

function urlBase() {
  return `${location.origin}/static/dados/basemap/guarulhos.pmtiles`;
}

async function series() {
  const r = await obter('/api/rede-serie');
  return r.status === 200 ? (r.json.itens || []) : [];
}

function pintarCamada() {
  if (mapa.getLayer(CAMADA)) return;
  mapa.addSource(FONTE, { type: 'geojson', data: VAZIO });
  mapa.addLayer({
    id: CAMADA,
    type: 'circle',
    source: FONTE,
    paint: {
      'circle-radius': 5,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#20242b',
      'circle-color': [
        'case',
        ['==', ['get', 'carga_pct'], null], '#8a8f98',
        ['>', ['get', 'carga_pct'], CARGA_SOBRECARGA], '#c0392b',
        ['>=', ['get', 'carga_pct'], CARGA_ATENCAO], '#d68910',
        '#1e8449',
      ],
    },
  });
}

function enquadrar(feicoes) {
  if (!feicoes.length) return;
  let [oe, sul, le, norte] = [180, 90, -180, -90];
  for (const f of feicoes) {
    const [lon, lat] = f.geometry.coordinates;
    oe = Math.min(oe, lon); le = Math.max(le, lon);
    sul = Math.min(sul, lat); norte = Math.max(norte, lat);
  }
  mapa.fitBounds([[oe, sul], [le, norte]], { padding: 60, maxZoom: 15, duration: 0 });
}

async function mostrarSafra(indice, enquadrarNoPrimeiro) {
  const ano = anos[indice];
  if (ano === undefined) return;
  el('safra-atual').textContent = String(ano);
  const r = await obter(`/api/rede-serie/${serieAtual.id}/mapa?ano=${ano}`);
  if (r.status !== 200) {
    el('aviso').erro(t('redeserie.erro_safra'));
    return;
  }
  const feicoes = r.json.features || [];
  mapa.getSource(FONTE).setData({ type: 'FeatureCollection', features: feicoes });
  const acima = feicoes.filter((f) => (f.properties.carga_pct || 0) > CARGA_SOBRECARGA).length;
  const novos = feicoes.filter((f) => f.properties.classe === 'novo').length;
  el('safra-resumo').textContent = t('redeserie.resumo')
    .replace('{trafos}', String(feicoes.length))
    .replace('{acima}', String(acima))
    .replace('{novos}', String(novos));
  el('safra-ressalva').textContent = r.json.pot_nom_confiavel ? '' : t('redeserie.pot_nom_suspeita');
  document.body.dataset.safra = String(ano);
  if (enquadrarNoPrimeiro) enquadrar(feicoes);
}

async function trocarSerie(serie) {
  serieAtual = serie;
  anos = (serie.safras || []).map((s) => s.ano).sort((a, b) => a - b);
  const controle = el('controle-safra');
  controle.max = String(Math.max(anos.length - 1, 0));
  controle.value = String(Math.max(anos.length - 1, 0));
  controle.disabled = anos.length < 2;
  const marcas = el('safras-marcas');
  limpar(marcas);
  anos.forEach((ano, i) => marcas.append(h('option', { value: String(i), label: String(ano) })));
  document.body.dataset.safras = String(anos.length);
  if (!anos.length) {
    el('safra-atual').textContent = '—';
    el('safra-resumo').textContent = t('redeserie.sem_safra');
    mapa.getSource(FONTE).setData(VAZIO);
    return;
  }
  await mostrarSafra(anos.length - 1, true);
}

async function iniciarMapa() {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro(t('mapa.erro_biblioteca'));
    return false;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);
  mapa = new window.maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(urlBase()),
    center: [-46.593018, -23.493476],
    zoom: 4,
    attributionControl: false,
    hash: false,
  });
  mapa.addControl(new window.maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  mapa.addControl(new window.maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  await new Promise((resolve) => mapa.once('load', resolve));
  pintarCamada();
  return true;
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/redes/serie' });
  try {
    if (await iniciarMapa()) {
      const lista = await series();
      const sel = el('seletor-serie');
      limpar(sel);
      for (const s of lista) sel.append(h('option', { value: s.id }, s.nome));
      sel.addEventListener('change', () => {
        const s = lista.find((x) => x.id === sel.value);
        if (s) trocarSerie(s);
      });
      el('controle-safra').addEventListener('input', (ev) => {
        mostrarSafra(Number(ev.target.value), false);
      });
      if (lista.length) await trocarSerie(lista[0]);
      else el('safra-resumo').textContent = t('redeserie.sem_serie');
    }
    document.body.dataset.pronto = '1';
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
  }
  pronto();
}
