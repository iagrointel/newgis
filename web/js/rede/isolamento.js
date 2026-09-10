/* plat — tela /redes/isolamento (item L4-02-c-isolamento): o operador escolhe a rede, aponta o ponto com
   falha (coordenada e tolerância), manda traçar, e vê TRÊS coisas na mesma tela — a lista dos dispositivos
   que precisam abrir, o resumo do que fica sem energia (clientes, transformadores, km por nível) e o mapa
   com o traçado, onde os dispositivos a abrir aparecem em COR PRÓPRIA, diferente da cor do trecho isolado.

   O mapa é o MapLibre já vendorizado (web/vendor/, mesma versão da tela /mapa), sem mapa de fundo: esta tela
   desenha só a geometria que o traçado devolve, e o enquadramento vem dela. Módulo ES sem build; nunca `?v=`
   nos imports (o cache é resolvido por no-store no nginx). */
import { obter, enviar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

/* as duas cores da tela: o trecho isolado e, em cor própria, os dispositivos que precisam abrir. Ficam aqui,
   nomeadas, porque a legenda e o e2e leem as mesmas constantes. */
export const COR_ISOLADO = '#3b6ea5';
export const COR_DISPOSITIVO = '#e07b00';

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) await iniciar();
pronto();

function colecao(geometria) {
  /* o traçado devolve uma GeometryCollection (ST_Collect); o MapLibre quer feições. */
  if (!geometria) return { type: 'FeatureCollection', features: [] };
  const geometrias = geometria.type === 'GeometryCollection' ? geometria.geometries : [geometria];
  return {
    type: 'FeatureCollection',
    features: geometrias.map((g) => ({ type: 'Feature', geometry: g, properties: {} })),
  };
}

function envelope(colecoes) {
  let [oe, su, le, no] = [Infinity, Infinity, -Infinity, -Infinity];
  const ver = (c) => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === 'number') {
      oe = Math.min(oe, c[0]); le = Math.max(le, c[0]);
      su = Math.min(su, c[1]); no = Math.max(no, c[1]);
      return;
    }
    c.forEach(ver);
  };
  for (const fc of colecoes) for (const f of fc.features) ver(f.geometry && f.geometry.coordinates);
  return Number.isFinite(oe) ? [[oe, su], [le, no]] : null;
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/isolamento' });
  cabecalho(t('isolamento.titulo'));
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const alvoMapa = document.getElementById('mapa');

  const r = await obter('/api/rede?limite=200');
  const lista = r.status === 200 ? (r.json.itens || []) : [];
  const selRede = h('select', { id: 'rede', 'aria-label': t('isolamento.rede') },
    h('option', { value: '' }, t('isolamento.escolha')),
    ...lista.map((i) => h('option', { value: i.id }, i.nome)));
  const lon = h('input', { id: 'lon', type: 'number', step: 'any', 'aria-label': t('isolamento.lon') });
  const lat = h('input', { id: 'lat', type: 'number', step: 'any', 'aria-label': t('isolamento.lat') });
  const tolerancia = h('input', { id: 'tolerancia', type: 'number', step: 'any', value: '1',
    'aria-label': t('isolamento.tolerancia') });
  const incluir = h('input', { id: 'incluir-isolados', type: 'checkbox' });
  const inoperante = h('input', { id: 'ignorar-inoperante', type: 'checkbox', checked: true });
  const botao = h('button', { id: 'tracar', type: 'button', class: 'primario' }, t('isolamento.tracar'));
  const dispositivos = h('div', { id: 'dispositivos', class: 'resultado' });
  const resumo = h('div', { id: 'resumo', class: 'resultado', hidden: true });

  const mapa = window.maplibregl
    ? new window.maplibregl.Map({
      container: alvoMapa,
      style: { version: 8, sources: {}, layers: [
        { id: 'fundo', type: 'background', paint: { 'background-color': '#0f1419' } }] },
      center: [0, 0], zoom: 1, attributionControl: false,
    })
    : null;
  if (!mapa) aviso.mostrar(t('isolamento.sem_biblioteca'), 'erro');
  if (mapa) {
    await new Promise((resolve) => mapa.once('load', resolve));
    mapa.addSource('isolados', { type: 'geojson', data: colecao(null) });
    mapa.addSource('dispositivos', { type: 'geojson', data: colecao(null) });
    mapa.addLayer({ id: 'isolados-linha', type: 'line', source: 'isolados',
      paint: { 'line-color': COR_ISOLADO, 'line-width': 3 } });
    mapa.addLayer({ id: 'isolados-ponto', type: 'circle', source: 'isolados',
      paint: { 'circle-color': COR_ISOLADO, 'circle-radius': 4 } });
    mapa.addLayer({ id: 'dispositivos-ponto', type: 'circle', source: 'dispositivos',
      paint: { 'circle-color': COR_DISPOSITIVO, 'circle-radius': 9, 'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff' } });
    /* o mapa fica alcançável pelo console e pelo e2e: a prova de "cor própria" é lida do próprio MapLibre
       (getPaintProperty), não da folha de estilo nem da figura. */
    window.__mapa_isolamento = mapa;
  }

  async function tracar() {
    limpar(dispositivos);
    resumo.hidden = true;
    if (!selRede.value || lon.value === '' || lat.value === '') {
      aviso.mostrar(t('isolamento.falta_ponto'), 'erro');
      return;
    }
    const corpo = {
      tipo: 'isolamento',
      pontos_partida: [{ lon: Number(lon.value), lat: Number(lat.value),
        tolerancia_m: Number(tolerancia.value) || undefined }],
      incluir_isolados: incluir.checked,
      ignorar_inoperante: inoperante.checked,
    };
    const resp = await enviar(`/api/rede/${selRede.value}/tracar`, corpo);
    if (resp.status !== 200) {
      aviso.mostrar((resp.json && resp.json.mensagem) || t('isolamento.falhou'), 'erro');
      return;
    }
    const j = resp.json;
    dispositivos.dataset.total = String(j.dispositivos_a_abrir.length);
    dispositivos.dataset.isolavel = j.isolavel ? '1' : '0';
    if (j.mensagem) aviso.mostrar(j.mensagem, j.isolavel ? 'ok' : 'erro');
    if (!j.dispositivos_a_abrir.length) {
      dispositivos.append(h('p', { class: 'ajuda' }, t('isolamento.sem_dispositivo')));
    } else {
      dispositivos.append(h('table', { class: 'grade' },
        h('thead', {}, h('tr', {},
          h('th', {}, t('isolamento.dispositivo')), h('th', {}, t('isolamento.tipo')),
          h('th', {}, t('isolamento.estado')))),
        h('tbody', {}, ...j.dispositivos_a_abrir.map((d) => h('tr', { 'data-feicao': d.feicao_id },
          h('td', {}, d.feicao_id), h('td', {}, d.tipo_nome || '—'), h('td', {}, d.estado || '—'))))));
    }
    limpar(resumo);
    resumo.append(h('dl', {},
      h('dt', {}, t('isolamento.clientes')), h('dd', { id: 'r-clientes' }, String(j.resumo.clientes)),
      h('dt', {}, t('isolamento.trafos')), h('dd', { id: 'r-trafos' }, String(j.resumo.trafos)),
      h('dt', {}, t('isolamento.km')), h('dd', { id: 'r-km' }, j.resumo.km_total.toFixed(3)),
      h('dt', {}, t('isolamento.elementos')), h('dd', { id: 'r-elementos' }, String(j.contagem)),
      h('dt', {}, t('isolamento.inoperantes')),
      h('dd', { id: 'r-inoperantes' }, String(j.dispositivos_inoperantes.length))));
    resumo.hidden = false;
    if (mapa) {
      const isolados = colecao(j.geometria);
      const marcados = colecao(j.geometria_dispositivos);
      mapa.getSource('isolados').setData(isolados);
      mapa.getSource('dispositivos').setData(marcados);
      const caixa = envelope([isolados, marcados]);
      if (caixa) mapa.fitBounds(caixa, { padding: 60, maxZoom: 17, duration: 0 });
    }
  }

  botao.addEventListener('click', tracar);
  principal.insertBefore(h('div', {},
    h('p', { class: 'ajuda' }, t('isolamento.ajuda')),
    h('div', { class: 'formulario' },
      h('label', { for: 'rede' }, t('isolamento.rede')), selRede,
      h('label', { for: 'lon' }, t('isolamento.lon')), lon,
      h('label', { for: 'lat' }, t('isolamento.lat')), lat,
      h('label', { for: 'tolerancia' }, t('isolamento.tolerancia')), tolerancia,
      h('label', { for: 'incluir-isolados' }, t('isolamento.incluir_isolados')), incluir,
      h('label', { for: 'ignorar-inoperante' }, t('isolamento.ignorar_inoperante')), inoperante,
      botao),
    h('ul', { class: 'legenda', id: 'legenda' },
      h('li', {}, h('span', { class: 'amostra', id: 'cor-isolado',
        style: `background:${COR_ISOLADO}` }), t('isolamento.legenda_isolado')),
      h('li', {}, h('span', { class: 'amostra', id: 'cor-dispositivo',
        style: `background:${COR_DISPOSITIVO}` }), t('isolamento.legenda_dispositivo'))),
    dispositivos, resumo), alvoMapa);
}
