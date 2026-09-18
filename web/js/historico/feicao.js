/* plat — tela /camadas/{id}/feicoes/{globalid}/historico (item L2-03-d-historico-restauracao).

   Uma entrada do histórico por cartão: o diff CAMPO A CAMPO e o diff DA GEOMETRIA já vêm calculados da
   API (`?dif=1` — área/comprimento antes/depois em metros), porque "o que mudou" tem de ter UMA resposta
   só (a tela nunca recalcula). A geometria é desenhada em DOIS MAPAS lado a lado, na MESMA extensão
   (união dos dois bboxes), para a comparação ser por posição; sem basemap — a trilha/appliance não têm
   internet e o que está em prova é o antes/depois, não o contexto.

   Paginação: o botão "carregar mais antigas" segue o `proximo_cursor` da API (chaveset), até acabar. */
import { obter, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const partes = location.pathname.split('/');
const CAMADA_ID = partes[2] || '';
const GLOBALID = partes[4] || '';

const aviso = () => document.getElementById('aviso');
const alvo = () => document.getElementById('entradas');
const resumo = () => document.getElementById('histfeicao-resumo');
const botaoMais = () => document.getElementById('btn-mais');

function falhar(resp) {
  aviso().setAttribute('tipo', 'erro');
  aviso().textContent = mensagemDe(resp) || t('histfeicao.erro');
}

function texto(valor) {
  if (valor === null || valor === undefined) return '—';
  if (typeof valor === 'object') return JSON.stringify(valor);
  return String(valor);
}

function numero(m) {
  if (m === null || m === undefined) return '—';
  return Number(m).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

function* posicoes(g) {
  if (!g) return;
  if (g.type && g.coordinates) {
    const pilha = [g.coordinates];
    while (pilha.length) {
      const no = pilha.pop();
      if (typeof no[0] === 'number') yield no; else pilha.push(...no);
    }
  }
}

function bboxUniao(geometrias) {
  let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
  for (const g of geometrias) {
    for (const [x, y] of posicoes(g)) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y);
      x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
  }
  if (x0 === Infinity) return null;
  if (x0 === x1) { x0 -= 0.0005; x1 += 0.0005; }
  if (y0 === y1) { y0 -= 0.0005; y1 += 0.0005; }
  return [[x0, y0], [x1, y1]];
}

function mapaCom(div, geometria, limites) {
  const mapa = new maplibregl.Map({  // eslint-disable-line no-undef — vendor global (mapa.html usa igual)
    container: div,
    style: { version: 8, sources: {}, layers: [
      { id: 'fundo', type: 'background', paint: { 'background-color': '#f5f5f4' } },
    ] },
    bounds: limites,
    fitBoundsOptions: { padding: 28, duration: 0 },
    attributionControl: false,
  });
  mapa.on('load', () => {
    mapa.addSource('g', { type: 'geojson', data: geometria });
    mapa.addLayer({ id: 'preenchimento', type: 'fill', source: 'g',
                    paint: { 'fill-color': '#1d4ed8', 'fill-opacity': 0.3 },
                    filter: ['==', ['geometry-type'], 'Polygon'] });
    mapa.addLayer({ id: 'contorno', type: 'line', source: 'g',
                    paint: { 'line-color': '#1d4ed8', 'line-width': 2 } });
    mapa.addLayer({ id: 'pontos', type: 'circle', source: 'g',
                    paint: { 'circle-radius': 6, 'circle-color': '#1d4ed8' },
                    filter: ['==', ['geometry-type'], 'Point'] });
  });
}

function blocoGeometria(e, pendentes) {
  const dif = e.dif && e.dif.geometria;
  const temLado = e.geometria_antes || e.geometria_depois;
  if (!dif && !temLado) return null;
  const numeros = dif ? h('div', { class: 'geom-numeros' },
    h('span', { class: 'area-antes' }, `${t('histfeicao.area')} ${t('histfeicao.antes').toLowerCase()}: ${numero(dif.area_antes_m2)}`),
    h('span', { class: 'area-depois' }, `${t('histfeicao.area')} ${t('histfeicao.depois').toLowerCase()}: ${numero(dif.area_depois_m2)}`),
    h('span', { class: 'comp-antes' }, `${t('histfeicao.comprimento')} ${t('histfeicao.antes').toLowerCase()}: ${numero(dif.comprimento_antes_m)}`),
    h('span', { class: 'comp-depois' }, `${t('histfeicao.comprimento')} ${t('histfeicao.depois').toLowerCase()}: ${numero(dif.comprimento_depois_m)}`),
  ) : null;
  const divAntes = h('div', { class: 'mapa mapa-antes' });
  const divDepois = h('div', { class: 'mapa mapa-depois' });
  const raiz = h('div', { class: 'geom-dif' },
    numeros,
    h('div', { class: 'mapas' },
      h('figure', {}, h('figcaption', { class: 'mapa-rotulo' }, t('histfeicao.antes')),
        e.geometria_antes ? divAntes : h('p', {}, t('histfeicao.sem_geometria'))),
      h('figure', {}, h('figcaption', { class: 'mapa-rotulo' }, t('histfeicao.depois')),
        e.geometria_depois ? divDepois : h('p', {}, t('histfeicao.sem_geometria')))));
  const limites = bboxUniao([e.geometria_antes, e.geometria_depois]);
  if (limites) {
    // o mapa só é criado DEPOIS do cartão entrar no DOM (medida do container); por isso a fila `pendentes`
    if (e.geometria_antes) pendentes.push([divAntes, e.geometria_antes, limites]);
    if (e.geometria_depois) pendentes.push([divDepois, e.geometria_depois, limites]);
  }
  return raiz;
}

function cartaoEntrada(e, pendentes) {
  const campos = (e.dif && e.dif.atributos) || {};
  const linhas = Object.keys(campos).map((campo) => h(
    'tr', { class: 'diff-linha', 'data-campo': campo },
    h('th', { scope: 'row' }, campo),
    h('td', { class: `valor-antes${campos[campo].mudou ? ' mudou' : ''}` }, texto(campos[campo].antes)),
    h('td', { class: `valor-depois${campos[campo].mudou ? ' mudou' : ''}` }, texto(campos[campo].depois)),
  ));
  const corpo = h('tbody', {}, ...linhas);
  const geom = blocoGeometria(e, pendentes);
  return h(
    'article', { class: 'entrada', 'data-id': e.id, 'data-operacao': e.operacao },
    h('h2', {}, `${e.operacao} · v${e.versao ?? '—'} · ${new Date(e.momento).toLocaleString('pt-BR')}`),
    h('table', { class: 'diff' },
      h('thead', {}, h('tr', {},
        h('th', { scope: 'col' }, t('histfeicao.campo')),
        h('th', { scope: 'col' }, t('histfeicao.antes')),
        h('th', { scope: 'col' }, t('histfeicao.depois')))),
      corpo),
    geom,
  );
}

async function carregarPagina(cursor) {
  const params = new URLSearchParams({ dif: '1', limite: '20' });
  if (cursor) params.set('cursor', cursor);
  const r = await obter(`/api/camadas/${CAMADA_ID}/feicoes/${GLOBALID}/historico?${params}`);
  if (r.status !== 200) return falhar(r);
  const { entradas, total, proximo_cursor: proximo } = r.json;
  resumo().textContent = t('histfeicao.resumo')
    .replace('{total}', String(total))
    .replace('{feicao}', GLOBALID);
  if (!entradas.length && !cursor) {
    alvo().append(h('p', {}, t('histfeicao.sem_historico')));
  }
  const pendentes = [];
  for (const e of entradas) alvo().append(cartaoEntrada(e, pendentes));
  for (const [div, geometria, limites] of pendentes) mapaCom(div, geometria, limites);
  botaoMais().hidden = !proximo;
  botaoMais().onclick = proximo ? () => carregarPagina(proximo) : null;
}

async function iniciar() {
  await carregarPagina(null);
}

// bootstrap por último: os `const` acima não são içados — chamar iniciar() antes deles é TDZ
await carregar();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario });
  await iniciar();
}
pronto();
