/* plat — tela /redes/fluxo (item L4-07-fluxo-de-potencia): escolhe a rede e o alimentador, declara os
   parâmetros, manda analisar e desenha o resultado no mapa em três camadas — tensão (ponto por barra e
   fase, em por unidade), corrente e carregamento (a linha do trecho).

   Regra dura da tela, e é o ponto do item: nenhum número aparece sem o ESTADO DE CONVERGÊNCIA ao lado. A
   tarja `#convergencia` é escrita antes das camadas e leva a classe `convergiu` ou `nao-convergiu`; quando
   o alimentador não fechou, as camadas nem são pedidas — desenhar um mapa colorido de um cálculo que parou
   seria a pior coisa que esta tela poderia fazer.

   MapLibre GL vem de <script> clássico (window.maplibregl, vendorizado), carregado antes deste módulo.
   Não há mapa-base aqui de propósito: o alimentador pode estar em qualquer lugar do país e o PMTiles local
   da plataforma cobre um município só. O fundo é neutro e o que se vê é a rede. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const GRANDEZAS = ['tensao', 'corrente', 'carregamento'];
const MODELOS_DE_CARGA = ['potencia_constante', 'impedancia_constante', 'corrente_constante'];
const CORES = {
  tensao: ['interpolate', ['linear'], ['coalesce', ['get', 'valor'], 1],
    0.90, '#b02a37', 0.93, '#d98324', 0.95, '#2f6f4e', 1.05, '#1f4f8b'],
  corrente: ['interpolate', ['linear'], ['coalesce', ['get', 'valor'], 0],
    0, '#2f6f4e', 200, '#d98324', 400, '#b02a37'],
  carregamento: ['interpolate', ['linear'], ['coalesce', ['get', 'valor'], 0],
    0, '#2f6f4e', 80, '#d98324', 100, '#b02a37'],
};

await carregar();
const usuario = await exigirSessao({ privilegio: 'rede.editar' });
if (usuario) iniciar();
pronto();

const el = (id) => document.getElementById(id);

function novoMapa() {
  if (!window.maplibregl) return null;
  return new window.maplibregl.Map({
    container: 'mapa',
    style: { version: 8, sources: {}, layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#101418' } }] },
    center: [-51.3, -29.8],
    zoom: 9,
    attributionControl: false,
  });
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/redes/fluxo' });
  cabecalho(t('fluxo.titulo'));
  const aviso = el('aviso');
  const painel = el('painel');
  const mapa = novoMapa();
  if (!mapa) { aviso.mostrar(t('fluxo.sem_biblioteca'), 'erro'); return; }
  let carregado = false;
  mapa.on('load', () => { carregado = true; });

  const redes = await obter('/api/rede?limite=200');
  const selRede = h('select', { id: 'rede', 'aria-label': t('fluxo.rede') },
    h('option', { value: '' }, t('fluxo.escolha')),
    ...((redes.status === 200 ? redes.json.itens : []) || []).map((i) => h('option', { value: i.id }, i.nome)));
  const selAlim = h('select', { id: 'alimentador', 'aria-label': t('fluxo.alimentador') });
  const selModo = h('select', { id: 'modo' },
    h('option', { value: 'anual' }, t('fluxo.modo_anual')),
    h('option', { value: 'hora' }, t('fluxo.modo_hora')));
  const campoPonto = h('input', { id: 'ponto', type: 'number', min: '0', max: '863', value: '0' });
  const campoFator = h('input', { id: 'fator', type: 'number', min: '0.01', step: '0.05', value: '1' });
  const campoNominal = h('input', { id: 'nominal', type: 'number', min: '1', step: '10', value: '400' });
  const selCarga = h('select', { id: 'modelo-de-carga' },
    ...MODELOS_DE_CARGA.map((m) => h('option', { value: m }, t(`fluxo.carga_${m}`))));
  const botao = h('button', { id: 'analisar', type: 'button', class: 'primario' }, t('fluxo.analisar'));

  async function alimentadores() {
    limpar(selAlim);
    if (!selRede.value) return;
    const r = await obter(`/api/rede/${selRede.value}/subredes?limite=500`);
    const itens = (r.status === 200 ? r.json.itens : []) || [];
    for (const s of itens) selAlim.append(h('option', { value: s.nome, 'data-tier': s.tier }, `${s.nome} (${s.tier})`));
  }
  selRede.addEventListener('change', alimentadores);

  function escreverFicha(doc) {
    limpar(painel);
    const c = doc.convergencia || {};
    const okConv = !!doc.convergiu;
    painel.append(
      h('p', {
        id: 'convergencia', class: okConv ? 'convergiu' : 'nao-convergiu',
        'data-convergiu': okConv ? '1' : '0',
      }, okConv
        ? t('fluxo.convergiu').replace('{sem}', String(c.pontos_sem_convergencia)).replace('{total}', String(c.pontos))
        : t('fluxo.nao_convergiu').replace('{total}', String(c.pontos))),
      h('dl', { id: 'ficha' },
        h('dt', {}, t('fluxo.parametros')), h('dd', { id: 'f-parametros' }, JSON.stringify(doc.parametros || {})),
        h('dt', {}, t('fluxo.topologia_versao')), h('dd', { id: 'f-topologia' }, doc.topologia_versao || '—'),
        h('dt', {}, t('fluxo.ponto_critico')), h('dd', { id: 'f-ponto' }, JSON.stringify(doc.ponto_critico || {})),
        h('dt', {}, t('fluxo.tensao_minima')), h('dd', { id: 'f-tensao-minima' },
          String((doc.resumo || {}).tensao_pu_minima ?? '—')),
        h('dt', {}, t('fluxo.energia_perdida')), h('dd', { id: 'f-perda' },
          String((doc.energia || {}).energia_perdida_kwh ?? '—'))));
  }

  function desenhar(grandeza, colecao) {
    const idFonte = `fluxo-${grandeza}`;
    if (mapa.getLayer(idFonte)) mapa.removeLayer(idFonte);
    if (mapa.getSource(idFonte)) mapa.removeSource(idFonte);
    mapa.addSource(idFonte, { type: 'geojson', data: colecao });
    mapa.addLayer(grandeza === 'tensao'
      ? { id: idFonte, type: 'circle', source: idFonte, paint: { 'circle-radius': 4, 'circle-color': CORES.tensao } }
      : { id: idFonte, type: 'line', source: idFonte, paint: { 'line-width': 3, 'line-color': CORES[grandeza] } });
  }

  function enquadrar(colecoes) {
    let x1 = 180; let y1 = 90; let x2 = -180; let y2 = -90; let achou = false;
    const ver = (c) => { if (c.length === 2 && Number.isFinite(c[0])) { achou = true; x1 = Math.min(x1, c[0]); y1 = Math.min(y1, c[1]); x2 = Math.max(x2, c[0]); y2 = Math.max(y2, c[1]); } else c.forEach(ver); };
    for (const colecao of colecoes) for (const f of colecao.features || []) ver(f.geometry.coordinates);
    if (achou) mapa.fitBounds([[x1, y1], [x2, y2]], { padding: 40, duration: 0 });
  }

  function caixaCamadas(disponiveis) {
    const caixa = el('camadas');
    limpar(caixa);
    for (const g of GRANDEZAS) {
      const marca = h('input', { type: 'checkbox', id: `ver-${g}`, checked: true, disabled: !disponiveis });
      marca.addEventListener('change', () => {
        if (mapa.getLayer(`fluxo-${g}`)) {
          mapa.setLayoutProperty(`fluxo-${g}`, 'visibility', marca.checked ? 'visible' : 'none');
        }
      });
      caixa.append(h('label', { for: `ver-${g}` }, marca, t(`fluxo.camada_${g}`)));
    }
  }

  botao.addEventListener('click', async () => {
    if (!selRede.value || !selAlim.value) { aviso.mostrar(t('fluxo.escolha'), 'erro'); return; }
    const tier = selAlim.selectedOptions[0].dataset.tier;
    const corpo = {
      modo: selModo.value,
      fator_de_carga: Number(campoFator.value),
      modelo_de_carga: selCarga.value,
      corrente_nominal_a: Number(campoNominal.value),
    };
    if (selModo.value === 'hora') corpo.ponto = Number(campoPonto.value);
    botao.disabled = true;
    try {
      const alvo = `/api/rede/${selRede.value}/subrede/${encodeURIComponent(selAlim.value)}/fluxo?tier=${tier}&jusante=true`;
      const r = await enviar(alvo, corpo);
      if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
      escreverFicha(r.json);
      if (!r.json.convergiu) {
        caixaCamadas(false);
        aviso.mostrar(t('fluxo.sem_camada_por_convergencia'), 'erro');
        return;
      }
      const colecoes = [];
      for (const g of GRANDEZAS) {
        const c = await obter(`${alvo.split('?')[0]}/camada?grandeza=${g}`);
        if (c.status !== 200) { aviso.mostrar(mensagemDe(c), 'erro'); return; }
        colecoes.push(c.json);
      }
      if (!carregado) await new Promise((ok) => mapa.once('load', ok));
      GRANDEZAS.forEach((g, i) => desenhar(g, colecoes[i]));
      caixaCamadas(true);
      enquadrar(colecoes);
      aviso.mostrar(t('fluxo.pronto'), 'ok');
    } finally {
      botao.disabled = false;
    }
  });

  el('ferramentas').after(h('div', { class: 'formulario', id: 'controles' },
    h('label', { for: 'rede' }, t('fluxo.rede')), selRede,
    h('label', { for: 'alimentador' }, t('fluxo.alimentador')), selAlim,
    h('label', { for: 'modo' }, t('fluxo.modo')), selModo,
    h('label', { for: 'ponto' }, t('fluxo.ponto')), campoPonto,
    h('label', { for: 'fator' }, t('fluxo.fator_de_carga')), campoFator,
    h('label', { for: 'modelo-de-carga' }, t('fluxo.modelo_de_carga')), selCarga,
    h('label', { for: 'nominal' }, t('fluxo.corrente_nominal')), campoNominal,
    botao));
  caixaCamadas(false);
}
