/* plat · cena — tela da cena 3D (item L2-09-b-cena-extrusao-slides).

   Abre com `?item=<id de um item do tipo cena>`. Tudo o que se vê sai do documento: câmera, terreno
   (fonte raster-dem com o exagero do documento), iluminação (posição do Sol calculada no servidor a
   partir da data/hora do documento), atmosfera, camadas com extrusão por atributo e slides.

   Mesmo motor do visualizador 2D (MapLibre GL JS 4.7.1, vendorizado): `setTerrain` para o relevo e
   `fill-extrusion` para os volumes. Nenhuma segunda biblioteca 3D entra aqui.

   Módulo ES sem empacotador; nunca `?v=` num import (duas instâncias do mesmo módulo derrubam a tela). */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { exigirSessao } from '../auth/sessao.js';
import { obter } from '../base/api.js';
import { construirEstilo } from '../mapa/estilo.js';
import { Documento } from './documento.js';
import { Camadas3D, PREFIXO } from './camadas3d.js';
import { Slides } from './slides.js';
import { Medicao3D } from './medicao3d.js';
import { Modelos3D } from './modelospainel.js';

const FONTE_TERRENO = 'plat-cena-terreno';
const el = (id) => document.getElementById(id);
const BASE_PADRAO = '/static/dados/basemap/guarulhos.pmtiles';

function idDoItem() {
  const p = new URLSearchParams(location.search).get('item');
  return p && /^[0-9a-f-]{36}$/.test(p) ? p : null;
}

/* --- terreno: fonte raster-dem do documento (o job do terreno grava os tiles; a cena só os consome) */
function aplicarTerreno(map, terreno) {
  const ligado = terreno.ligado && terreno.url;
  if (!ligado) {
    if (map.getTerrain()) map.setTerrain(null);
    if (map.getSource(FONTE_TERRENO)) map.removeSource(FONTE_TERRENO);
    return false;
  }
  if (!map.getSource(FONTE_TERRENO)) {
    map.addSource(FONTE_TERRENO, {
      type: 'raster-dem',
      tiles: [terreno.url],
      tileSize: terreno.tamanho_tile || 256,
      maxzoom: terreno.zoom_maximo ?? 14,
      // `mapbox` é o nome do MapLibre para a codificação terrain-RGB do item L2-09-a
      encoding: terreno.codificacao === 'terrarium' ? 'terrarium' : 'mapbox',
    });
  }
  map.setTerrain({ source: FONTE_TERRENO, exaggeration: Number(terreno.exagero) || 0 });
  return true;
}

function aplicarAtmosfera(map, atmosfera) {
  if (!atmosfera.ceu) { map.setSky(null); return; }
  const nevoa = atmosfera.nevoa || {};
  map.setSky({
    'sky-color': '#71aae0',
    'horizon-color': atmosfera.cor_horizonte || '#a8c6dd',
    'fog-color': nevoa.cor || '#c9d6de',
    'horizon-fog-blend': 0.5,
    'fog-ground-blend': nevoa.ligada === false ? 1 : Math.max(0, Math.min(1, nevoa.inicio ?? 0.7)),
    'atmosphere-blend': 0.8,
  });
}

/* --- iluminação: a posição do Sol vem do servidor (app/cena/sol.py), uma implementação só */
async function aplicarSol(map, iluminacao, centro, aviso) {
  if (iluminacao.modo === 'fixa') {
    const polar = 90 - Math.max(0, Math.min(90, Number(iluminacao.elevacao) || 0));
    map.setLight({ anchor: 'map', position: [1.5, Number(iluminacao.azimute) || 0, polar],
      color: iluminacao.cor || '#ffffff', intensity: iluminacao.intensidade ?? 0.35 });
    return null;
  }
  const url = `/api/cena/sol?lat=${centro[1]}&lon=${centro[0]}`
    + `&instante=${encodeURIComponent(iluminacao.instante)}&intensidade=${iluminacao.intensidade ?? 0.35}`;
  const r = await obter(url);
  if (r.status !== 200) { if (aviso) aviso.erro(t('cena.erro_sol')); return null; }
  const luz = { ...r.json.luz, color: iluminacao.cor || '#ffffff' };
  map.setLight(luz);
  return r.json;
}

function textoDoSol(s) {
  if (!s) return '';
  return t('cena.sol_posicao', { azimute: s.azimute.toFixed(1), elevacao: s.elevacao.toFixed(1) });
}

async function iniciar() {
  const maplibregl = window.maplibregl;
  if (!maplibregl || !window.pmtiles) { el('aviso').erro(t('cena.erro_biblioteca')); return; }
  const id = idDoItem();
  if (!id) { el('aviso').erro(t('cena.sem_item')); pronto(); return; }
  maplibregl.addProtocol('pmtiles', new window.pmtiles.Protocol().tile);

  const documento = await Documento.carregar(id);
  const corpo = documento.corpo;
  document.title = `${documento.item.titulo} · plat`;
  el('titulo').textContent = documento.item.titulo;

  const map = new maplibregl.Map({
    container: 'cena',
    style: construirEstilo(location.origin + BASE_PADRAO),
    center: corpo.camera.centro,
    zoom: corpo.camera.zoom,
    pitch: corpo.camera.inclinacao,
    bearing: corpo.camera.rotacao,
    attributionControl: false,
    preserveDrawingBuffer: true,  // a miniatura do slide lê o canvas depois do quadro composto
    maxPitch: 85,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');

  const camadas = new Camadas3D(map);
  const camadaDaCena = (idDeEstilo) => corpo.camadas.find((c) => PREFIXO + c.id === idDeEstilo) || null;
  const medicao = new Medicao3D(map, el('medicao-saida'), camadaDaCena);
  const modelos = new Modelos3D(map, { lista: el('lista-modelos'),
    propriedades: el('modelo-propriedades'), aviso: el('aviso') });
  const slides = new Slides(map, documento, () => ({
    camadas_visiveis: corpo.camadas.filter((c) => c.visivel !== false).map((c) => c.id),
    instante: corpo.iluminacao.instante,
    exagero: corpo.terreno.exagero,
  }));

  const desenharListaCamadas = () => {
    const lista = el('lista-camadas');
    limpar(lista);
    for (const c of corpo.camadas) {
      const caixa = h('input', { type: 'checkbox', id: `cam-${c.id}`, checked: c.visivel !== false });
      caixa.addEventListener('change', async () => {
        c.visivel = caixa.checked;
        await camadas.aplicar(corpo.camadas);
      });
      lista.append(h('li', { class: 'camada-cena' }, caixa,
        h('label', { for: `cam-${c.id}`, class: 'camada-titulo' }, c.titulo || c.camada_id)));
    }
  };

  const desenharSlides = () => {
    const lista = el('lista-slides');
    limpar(lista);
    for (const s of slides.lista) {
      const botao = h('button', { type: 'button', class: 'slide', 'data-slide': s.id },
        s.miniatura ? h('img', { src: s.miniatura, alt: '', class: 'slide-miniatura' }) : h('span', { class: 'slide-sem-miniatura' }, '—'),
        h('span', { class: 'slide-nome' }, s.nome));
      botao.addEventListener('click', async () => {
        slides.aplicar(s);
        await aplicarCena();
        desenharListaCamadas();
        el('slides-saida').textContent = t('cena.slide_aplicado', { nome: s.nome });
      });
      const remover = h('button', { type: 'button', class: 'botao-mini', 'data-remover': s.id,
        'aria-label': t('cena.remover_slide') }, '×');
      remover.addEventListener('click', async () => { slides.remover(s.id); desenharSlides(); await gravar(); });
      lista.append(h('li', {}, botao, remover));
    }
  };

  const aplicarCena = async () => {
    aplicarTerreno(map, corpo.terreno);
    aplicarAtmosfera(map, corpo.atmosfera);
    const sol = await aplicarSol(map, corpo.iluminacao, map.getCenter().toArray(), el('aviso'));
    el('sol-saida').textContent = textoDoSol(sol);
    await camadas.aplicar(corpo.camadas);
    await modelos.aplicar(corpo.modelos || []);
  };

  const gravar = async () => {
    try {
      await documento.gravar();
      el('gravar-saida').textContent = t('cena.gravado');
    } catch (e) {
      el('aviso').erro(`${t('cena.erro_gravar')}: ${(e && e.message) || e}`);
    }
  };

  // --- controles
  el('exagero').value = String(corpo.terreno.exagero ?? 1);
  el('exagero').addEventListener('input', () => {
    corpo.terreno.exagero = Number(el('exagero').value);
    el('exagero-saida').textContent = `${corpo.terreno.exagero.toFixed(1)}×`;
    aplicarTerreno(map, corpo.terreno);
  });
  el('exagero-saida').textContent = `${Number(corpo.terreno.exagero ?? 1).toFixed(1)}×`;
  el('terreno-ligado').checked = !!corpo.terreno.ligado;
  el('terreno-ligado').addEventListener('change', () => {
    corpo.terreno.ligado = el('terreno-ligado').checked;
    aplicarTerreno(map, corpo.terreno);
  });
  el('instante').value = (corpo.iluminacao.instante || '').slice(0, 16);
  el('instante').addEventListener('change', async () => {
    const valor = el('instante').value;
    if (!valor) return;
    const fuso = corpo.iluminacao.instante.slice(19) || 'Z';
    corpo.iluminacao.instante = `${valor}:00${fuso}`;
    const sol = await aplicarSol(map, corpo.iluminacao, map.getCenter().toArray(), el('aviso'));
    el('sol-saida').textContent = textoDoSol(sol);
  });
  el('btn-slide-novo').addEventListener('click', async () => {
    slides.capturar(el('slide-nome').value);
    el('slide-nome').value = '';
    desenharSlides();
    await gravar();
  });
  el('btn-distancia3d').addEventListener('click', () => medicao.iniciar('distancia'));
  el('btn-altura').addEventListener('click', () => medicao.iniciar('altura'));
  el('btn-medicao-limpar').addEventListener('click', () => medicao.limpar());
  el('btn-gravar').addEventListener('click', async () => {
    corpo.camera = { centro: map.getCenter().toArray().map((v) => Number(v.toFixed(6))),
      zoom: Number(map.getZoom().toFixed(4)), inclinacao: Number(map.getPitch().toFixed(4)),
      rotacao: Number(((((map.getBearing() % 360) + 360) % 360)).toFixed(4)) };
    await gravar();
  });

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('cena.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  try {
    await aplicarCena();
  } catch (e) {
    el('aviso').erro(`${t('cena.erro_camada')}: ${(e && e.message) || e}`);
  }
  desenharListaCamadas();
  desenharSlides();
  window.plat = window.plat || {};
  window.plat.cena = { map, documento, camadas, slides, medicao, modelos, aplicarCena };  // ponto de inspeção do e2e
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/cena' });
  try {
    await iniciar();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
