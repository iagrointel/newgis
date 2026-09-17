/* plat — tela /rede/medicao/ficha (item L4-13-integracao-telemetria): última leitura de cada grandeza,
   gráfico de 7 dias e o alarme declarado ("carregamento > 100% por 30 min") aparecendo no mapa — um ponto
   colorido na posição real do ativo (vermelho = alarme ativo, verde = normal, cinza = sem placa cadastrada).

   `?ativo=<uuid>` obrigatório; `?rede_id=<uuid>&terminal=<n>` opcional (sem ele a ficha funciona igual,
   só sem o mapa — o ativo não precisa pertencer a nenhuma rede para ter leitura, mesma decisão do módulo
   campo). Atualiza sozinha a cada 5 s: é o que prova "última leitura em <= 5 s" na instância viva. */
import { obter, mensagemDe, consulta } from '../base/api.js';
import { anexar, h, limpar } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const params = new URLSearchParams(location.search);
const ativo = params.get('ativo');
const redeId = params.get('rede_id');
const ATUALIZAR_MS = 5000;
const GRANDEZA_GRAFICO_PADRAO = 'corrente_a';

await carregar();
const usuario = await exigirSessao({});
if (usuario) iniciar();
pronto();

function estiloVazio(cor) {
  return { version: 8, sources: {}, layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': cor } }] };
}

function svgLinha(pontos, unidade) {
  const largura = 640;
  const altura = 140;
  const margem = 28;
  if (!pontos.length) {
    return h('p', { class: 'fraco' }, t('rede_medicao.ficha.grafico_sem_ponto'));
  }
  const xs = pontos.map((p) => new Date(p.ts).getTime());
  const ys = pontos.map((p) => p.valor);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(0, ...ys);
  const yMax = Math.max(...ys, yMin + 1);
  const sx = (x) => margem + ((x - xMin) / Math.max(1, xMax - xMin)) * (largura - 2 * margem);
  const sy = (y) => altura - margem - ((y - yMin) / Math.max(1e-9, yMax - yMin)) * (altura - 2 * margem);
  const d = pontos.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(new Date(p.ts).getTime()).toFixed(1)} ${sy(p.valor).toFixed(1)}`).join(' ');
  const svg = h('svg', {
    viewBox: `0 0 ${largura} ${altura}`, width: '100%', height: altura, role: 'img',
    'aria-label': `${t('rede_medicao.ficha.grafico_7_dias')} (${unidade || ''})`,
  });
  svg.append(
    h('line', { x1: margem, y1: altura - margem, x2: largura - margem, y2: altura - margem, class: 'grafico-eixo' }),
    h('path', { d, class: 'grafico-linha', fill: 'none' }),
  );
  return svg;
}

function linhaDl(rotulo, valor) {
  return [h('dt', {}, rotulo), h('dd', {}, valor)];
}

async function montarMapa(el, lon, lat, alarmeAtivo, placaCadastrada) {
  if (!window.maplibregl) return;
  const cor = !placaCadastrada ? '#8a8f98' : (alarmeAtivo ? '#c4342f' : '#1f8a4c');
  const map = new window.maplibregl.Map({
    container: el, style: estiloVazio('#eef1f4'), center: [lon, lat], zoom: 15, attributionControl: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.on('load', () => {
    const marcador = document.createElement('div');
    marcador.style.cssText = `width:18px;height:18px;border-radius:50%;background:${cor};border:2px solid #fff;box-shadow:0 0 0 2px ${cor}`;
    new window.maplibregl.Marker({ element: marcador }).setLngLat([lon, lat]).addTo(map);
  });
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/rede/medicao/ficha' });
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const conteudo = document.getElementById('conteudo');
  if (!ativo) { aviso.mostrar(t('rede_medicao.ficha.sem_ativo'), 'erro'); return; }
  cabecalho(t('rede_medicao.ficha.titulo'));
  conteudo.hidden = false;

  const secUltima = h('section', { class: 'ficha-secao' }, h('h2', {}, t('rede_medicao.ficha.ultima_leitura')));
  const secPlaca = h('section', { class: 'ficha-secao' }, h('h2', {}, t('rede_medicao.ficha.placa')));
  const secGrafico = h('section', { class: 'ficha-secao' }, h('h2', {}, t('rede_medicao.ficha.grafico_7_dias')));
  const secMapa = h('section', { class: 'ficha-secao' }, h('h2', {}, t('rede_medicao.ficha.mapa')));
  const mapaEl = h('div', { id: 'mapa-ficha', class: 'ficha-mapa' });
  const marcaTempo = h('p', { class: 'fraco', id: 'atualizado-em' }, '');
  anexar(principal, [secUltima, secPlaca, secGrafico, secMapa, marcaTempo]);
  if (redeId) secMapa.append(mapaEl);
  else secMapa.append(h('p', { class: 'fraco' }, '—'));

  let mapaMontado = false;

  async function atualizar() {
    const [rUlt, rConfig] = await Promise.all([
      obter(`/api/rede/medicao/ativos/${ativo}/ultimas`),
      obter(`/api/rede/medicao/ativos/${ativo}`),
    ]);
    if (rUlt.status !== 200) { aviso.mostrar(mensagemDe(rUlt), 'erro'); return; }
    const leituras = rUlt.json.leituras || [];
    const placa = rConfig.status === 200 ? rConfig.json : { placa_cadastrada: false };

    limpar(secUltima);
    secUltima.append(h('h2', {}, t('rede_medicao.ficha.ultima_leitura')));
    if (!leituras.length) {
      secUltima.append(h('p', { class: 'fraco' }, t('rede_medicao.ficha.sem_leitura')));
    } else {
      const tabela = h('table', { class: 'tabela' },
        h('thead', {}, h('tr', {},
          h('th', {}, t('rede_medicao.ficha.grandeza')), h('th', {}, t('rede_medicao.ficha.valor')),
          h('th', {}, t('rede_medicao.ficha.ts')), h('th', {}, t('rede_medicao.ficha.fonte')))),
        h('tbody', {}, ...leituras.map((l) => h('tr', { class: l.grandeza === 'carregamento_pct' && l.valor > 100 ? 'alarme' : '' },
          h('td', {}, l.grandeza), h('td', {}, `${l.valor} ${l.unidade}`),
          h('td', {}, formatarData(l.ts)), h('td', {}, l.fonte)))));
      secUltima.append(tabela);
    }

    limpar(secPlaca);
    secPlaca.append(h('h2', {}, t('rede_medicao.ficha.placa')));
    if (!placa.placa_cadastrada) {
      secPlaca.append(h('p', { class: 'fraco' }, t('rede_medicao.ficha.placa_ausente')));
    } else {
      const dl = h('dl', { class: 'lista-definicao' });
      dl.append(...linhaDl(t('rede_medicao.ficha.kva_nominal'), `${placa.kva_nominal} kVA`),
               ...linhaDl(t('rede_medicao.ficha.tensao_nominal'), `${placa.tensao_nominal_v} V`));
      secPlaca.append(dl);
    }

    const carregamento = leituras.find((l) => l.grandeza === 'carregamento_pct');
    const alarmeAtivo = !!(carregamento && carregamento.valor > 100);
    const faixaAlarme = h('p', { class: alarmeAtivo ? 'alarme-texto' : 'fraco' },
      alarmeAtivo
        ? t('rede_medicao.ficha.alarme_ativo', { desde: formatarData(carregamento.ts) })
        : t('rede_medicao.ficha.alarme_normal'));
    secPlaca.append(faixaAlarme);

    const grandezaGrafico = carregamento ? 'carregamento_pct' : GRANDEZA_GRAFICO_PADRAO;
    const rSerie = await obter(`/api/rede/medicao/ativos/${ativo}/serie${consulta({ grandeza: grandezaGrafico, dias: 7 })}`);
    limpar(secGrafico);
    secGrafico.append(h('h2', {}, `${t('rede_medicao.ficha.grafico_7_dias')} · ${grandezaGrafico}`));
    if (rSerie.status === 200) {
      secGrafico.append(svgLinha(rSerie.json.pontos || [], rSerie.json.unidade));
    } else {
      secGrafico.append(h('p', { class: 'fraco' }, mensagemDe(rSerie)));
    }

    if (redeId && !mapaMontado) {
      const rGeo = await obter(`/api/rede/${redeId}/feicoes/pontos.geojson${consulta({ limite: 5000 })}`);
      if (rGeo.status === 200) {
        const feicao = (rGeo.json.features || []).find((f) => f.properties && f.properties.id === ativo);
        if (feicao && feicao.geometry && feicao.geometry.type === 'Point') {
          const [lon, lat] = feicao.geometry.coordinates;
          await montarMapa(mapaEl, lon, lat, alarmeAtivo, placa.placa_cadastrada);
          mapaMontado = true;
        }
      }
    }

    document.getElementById('atualizado-em').textContent =
      t('rede_medicao.ficha.atualizado_em', { quando: formatarData(new Date().toISOString()) });
  }

  await atualizar();
  setInterval(atualizar, ATUALIZAR_MS);
}
