/* plat · tela /amc/pareto — fronteira de Pareto do motor multicritério (item L3-08-pareto).
   Módulo ES sem build; cache resolvido por no-store no nginx: NUNCA ?v= nos imports.

   A tela mostra a mesma análise em dois lugares ao mesmo tempo: um gráfico de dispersão de dois
   objetivos e um mapa das unidades. Arrastar um retângulo no gráfico (escovar) realça no mapa
   exatamente as unidades escovadas; passar o ponteiro sobre o mapa realça o ponto no gráfico. A conta
   da seleção é a de ./pareto.js, testada fora do navegador.

   Nenhum peso entra aqui: a fronteira é a resposta anterior à escolha de peso, e a frase que diz isso
   vem do servidor em `metadados.aviso` e é escrita na tela. */
import '../base/componentes.js';
import { chamar } from '../base/api.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from '../mapa/estilo.js';
import { caixaDeDado, corDaOrdem, escovar, faixa, filtroDeRealce, pontos, projetar } from './pareto.js';

const NS = 'http://www.w3.org/2000/svg';
const ORDENS = 3;
const el = (id) => document.getElementById(id);

const estado = {
  execucao: null,
  fatores: [],
  colecao: null,
  unidades: [],
  desenhados: [],
  faixaX: null,
  faixaY: null,
  map: null,
};

function avisar(mensagem) { el('aviso').erro(mensagem); }

// ------------------------------------------------------------------ dados

async function carregarExecucoes() {
  const { status, json } = await chamar('GET', '/api/multiescala/execucoes?limite=50');
  if (status !== 200) { avisar(json.mensagem); return []; }
  return json.itens || [];
}

async function carregarFatores(execucaoId) {
  const { status, json } = await chamar('GET', `/api/multiescala/execucoes/${execucaoId}`);
  if (status !== 200) { avisar(json.mensagem); return []; }
  return json.fatores || [];
}

function objetivosEscolhidos() {
  return [...document.querySelectorAll('.objetivo')]
    .filter((linha) => linha.querySelector('input[type=checkbox]').checked)
    .map((linha) => ({
      fator_id: linha.dataset.fator,
      direcao: linha.querySelector('select').value,
      base: 'favorabilidade',
    }));
}

async function rodar() {
  const objetivos = objetivosEscolhidos();
  if (objetivos.length < 2 || objetivos.length > 4) { avisar(t('pareto.escolha_objetivos')); return; }
  const corpo = {
    execucao_id: estado.execucao,
    objetivos,
    ordens: ORDENS,
    ordens_incluidas: [1, 2, 3],
  };
  const { status, json } = await chamar('POST', '/api/amc/pareto/camada', corpo);
  if (status !== 200) { avisar(json.mensagem); return; }
  estado.colecao = json;
  estado.unidades = json.features.map((f) => ({
    unidade_id: f.properties.unidade_id,
    ordem: f.properties.ordem,
    valores: objetivos.map((o, i) => f.properties[json.metadados.objetivos[i].nome]),
  }));
  el('resumo').textContent = resumo(json.metadados);
  el('aviso-pesos').textContent = json.metadados.aviso;
  el('baixar').disabled = false;
  desenharGrafico(json.metadados.objetivos);
  desenharMapa();
}

function resumo(m) {
  const partes = m.contagem_por_ordem.map((c) => `${c.unidades} na ${c.ordem}ª ordem`);
  return `${m.unidades_avaliadas} unidades avaliadas: ${partes.join(', ')}; ${m.sem_dado} sem dado em algum objetivo.`;
}

// ------------------------------------------------------------------ gráfico de dispersão

function desenharGrafico(objetivos) {
  const svg = el('grafico');
  const largura = svg.clientWidth || 480;
  const altura = svg.clientHeight || 360;
  svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  estado.desenhados = pontos(estado.unidades, 0, 1);
  estado.faixaX = faixa(estado.unidades, 0);
  estado.faixaY = faixa(estado.unidades, 1);
  el('eixo-x').textContent = `${objetivos[0].nome} (${objetivos[0].direcao})`;
  el('eixo-y').textContent = `${objetivos[1].nome} (${objetivos[1].direcao})`;

  for (const p of estado.desenhados) {
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx', projetar(p.x, estado.faixaX, largura));
    c.setAttribute('cy', projetar(p.y, estado.faixaY, altura, true));
    c.setAttribute('r', p.ordem === 1 ? 5 : 3);
    c.setAttribute('fill', corDaOrdem(p.ordem));
    c.dataset.unidade = p.unidade_id;
    c.classList.add('ponto');
    svg.append(c);
  }
  const selecao = document.createElementNS(NS, 'rect');
  selecao.setAttribute('id', 'escova');
  selecao.classList.add('escova');
  selecao.setAttribute('width', 0);
  selecao.setAttribute('height', 0);
  svg.append(selecao);
  ligarEscova(svg, largura, altura);
}

function ligarEscova(svg, largura, altura) {
  const retangulo = el('escova');
  let inicio = null;
  const posicao = (ev) => {
    const r = svg.getBoundingClientRect();
    return { x: ((ev.clientX - r.left) / r.width) * largura, y: ((ev.clientY - r.top) / r.height) * altura };
  };
  svg.addEventListener('pointerdown', (ev) => {
    inicio = posicao(ev);
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener('pointermove', (ev) => {
    if (!inicio) return;
    const p = posicao(ev);
    retangulo.setAttribute('x', Math.min(inicio.x, p.x));
    retangulo.setAttribute('y', Math.min(inicio.y, p.y));
    retangulo.setAttribute('width', Math.abs(p.x - inicio.x));
    retangulo.setAttribute('height', Math.abs(p.y - inicio.y));
  });
  svg.addEventListener('pointerup', (ev) => {
    if (!inicio) return;
    const p = posicao(ev);
    const caixa = caixaDeDado(
      { x0: inicio.x, x1: p.x, y0: inicio.y, y1: p.y },
      estado.faixaX, estado.faixaY, largura, altura,
    );
    inicio = null;
    aplicarSelecao(escovar(estado.desenhados, caixa));
  });
}

function aplicarSelecao(ids) {
  const conjunto = new Set(ids);
  for (const c of document.querySelectorAll('#grafico .ponto')) {
    c.classList.toggle('escovado', conjunto.has(Number(c.dataset.unidade)));
  }
  el('selecao').textContent = `${ids.length} unidades escovadas`;
  el('selecao').dataset.ids = JSON.stringify(ids);
  if (estado.map && estado.map.getLayer('pareto-realce')) {
    estado.map.setFilter('pareto-realce', filtroDeRealce(ids));
    // relê do MapLibre o filtro que ficou valendo (não a variável local): é este número que o e2e
    // confere contra os pontos escovados no gráfico, e ele só bate se o mapa recebeu mesmo a seleção
    const aplicado = estado.map.getFilter('pareto-realce');
    el('mapa').dataset.realcadas = String(aplicado[2][1].length);
  }
}

// ------------------------------------------------------------------ mapa

function limites(colecao) {
  let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
  for (const f of colecao.features) {
    for (const anel of f.geometry.coordinates) {
      for (const [x, y] of anel) {
        if (x < x0) x0 = x; if (x > x1) x1 = x;
        if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  return Number.isFinite(x0) ? [[x0, y0], [x1, y1]] : null;
}

function camadas(map) {
  map.addSource('pareto', { type: 'geojson', data: estado.colecao });
  map.addLayer({
    id: 'pareto-preenchimento',
    type: 'fill',
    source: 'pareto',
    paint: {
      'fill-color': [
        'match', ['get', 'ordem'],
        1, corDaOrdem(1), 2, corDaOrdem(2), 3, corDaOrdem(3),
        '#263133',
      ],
      'fill-opacity': 0.45,
    },
  });
  map.addLayer({
    id: 'pareto-realce',
    type: 'line',
    source: 'pareto',
    filter: filtroDeRealce([]),
    paint: { 'line-color': '#ffffff', 'line-width': 2.5 },
  });
}

async function desenharMapa() {
  if (!window.maplibregl || !window.pmtiles) { avisar(t('pareto.erro_biblioteca')); return; }
  if (!estado.map) {
    const protocolo = new window.pmtiles.Protocol();
    window.maplibregl.addProtocol('pmtiles', protocolo.tile);
    estado.map = new window.maplibregl.Map({
      container: 'mapa',
      style: construirEstilo(`${location.origin}/static/dados/basemap/guarulhos.pmtiles`),
      center: [-46.60, -23.50],
      zoom: 12,
      attributionControl: false,
    });
    estado.map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    estado.map.addControl(new window.maplibregl.AttributionControl({ compact: false }), 'bottom-right');
    await new Promise((resolve) => estado.map.once('load', resolve));
    camadas(estado.map);
  } else {
    estado.map.getSource('pareto').setData(estado.colecao);
    estado.map.setFilter('pareto-realce', filtroDeRealce([]));
  }
  const caixa = limites(estado.colecao);
  if (caixa) estado.map.fitBounds(caixa, { padding: 40, duration: 0 });
}

// ------------------------------------------------------------------ baixar a fronteira como camada

async function baixar() {
  const objetivos = objetivosEscolhidos();
  const { status, json } = await chamar('POST', '/api/amc/pareto/camada', {
    execucao_id: estado.execucao, objetivos, ordens: ORDENS, ordens_incluidas: [1],
  });
  if (status !== 200) { avisar(json.mensagem); return; }
  const url = URL.createObjectURL(new Blob([JSON.stringify(json)], { type: 'application/geo+json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `fronteira-${estado.execucao}.geojson`;
  a.click();
  URL.revokeObjectURL(url);
}

// ------------------------------------------------------------------ montagem

function montarObjetivos(fatores) {
  const caixa = el('objetivos');
  while (caixa.firstChild) caixa.removeChild(caixa.firstChild);
  for (const f of fatores) {
    const linha = document.createElement('label');
    linha.className = 'objetivo';
    linha.dataset.fator = f.fator_id;
    const marca = document.createElement('input');
    marca.type = 'checkbox';
    const nome = document.createElement('span');
    nome.textContent = f.nome;
    const direcao = document.createElement('select');
    for (const [valor, rotulo] of [['maximizar', t('pareto.maximizar')], ['minimizar', t('pareto.minimizar')]]) {
      const opt = document.createElement('option');
      opt.value = valor;
      opt.textContent = rotulo;
      direcao.append(opt);
    }
    linha.append(marca, nome, direcao);
    caixa.append(linha);
  }
}

async function iniciar() {
  const execucoes = await carregarExecucoes();
  const sel = el('execucao');
  for (const e of execucoes) {
    const opt = document.createElement('option');
    opt.value = e.id;
    opt.textContent = `${e.nivel} · ${e.celulas} células · ${e.criado_em}`;
    sel.append(opt);
  }
  const pedida = new URLSearchParams(location.search).get('execucao');
  if (pedida && execucoes.some((e) => e.id === pedida)) sel.value = pedida;
  const trocar = async () => {
    estado.execucao = sel.value;
    if (!estado.execucao) return;
    estado.fatores = await carregarFatores(estado.execucao);
    montarObjetivos(estado.fatores);
  };
  sel.addEventListener('change', trocar);
  if (execucoes.length) await trocar();
  el('rodar').addEventListener('click', rodar);
  el('baixar').addEventListener('click', baixar);
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/amc/pareto' });
  try {
    await iniciar();
  } catch (e) {
    avisar(`${t('erro.carregar')}: ${(e && e.message) || e}`);
  }
  pronto();
}
