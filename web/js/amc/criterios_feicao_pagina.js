/* plat · AMC — item L3-06-criterios-de-feicao: tela /amc/criterios-feicao.
   O usuário descreve as feições (imóvel, loja, lote), os critérios sobre a própria feição e as camadas de
   apoio; a tela chama POST /api/amc/criterios-feicao e mostra o ranque, o HISTOGRAMA de cada critério e a
   MATRIZ DE CORRELAÇÃO entre critérios. O botão de CSV chama /api/amc/criterios-feicao/exportar.
   Sem `?v=` no import (no-store no nginx resolve o cache). */
import { chamar, enviar } from '../base/api.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { irParaLogin, marcarSessao } from '../auth/sessao.js';
import { h, limpar } from '../base/dom.js';

const EXEMPLO = {
  feicoes: [
    { id: 'a', geometry: { type: 'Point', coordinates: [-46.53, -23.45] }, properties: { area_m2: 300 } },
    { id: 'b', geometry: { type: 'Point', coordinates: [-46.52, -23.46] }, properties: { area_m2: 900 } },
    { id: 'c', geometry: { type: 'Point', coordinates: [-46.55, -23.44] }, properties: { area_m2: 120 } },
  ],
  camadas: {
    pontos: [
      { id: 'p1', geometry: { type: 'Point', coordinates: [-46.531, -23.451] }, properties: {} },
      { id: 'p2', geometry: { type: 'Point', coordinates: [-46.54, -23.44] }, properties: {} },
    ],
  },
  criterios: [
    { id: 'area', tipo: 'atributo', campo: 'area_m2', influencia: 'positiva', peso: 3 },
    { id: 'pontos_1km', tipo: 'contagem_raio', camada: 'pontos', raio_m: 1000, influencia: 'positiva', peso: 2 },
    { id: 'distancia', tipo: 'distancia_mais_proxima', camada: 'pontos', influencia: 'inversa', peso: 2 },
    { id: 'area_ideal', tipo: 'atributo', campo: 'area_m2', influencia: 'ideal', alvo: 300, alcance: 300, peso: 1 },
  ],
};

function numero(v, casas = 2) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(casas) : '—';
}

function pedidoDoTexto(aviso) {
  try {
    return JSON.parse(document.getElementById('pedido').value);
  } catch (e) {
    aviso.erro(`o pedido não é JSON válido: ${e.message}`);
    return null;
  }
}

function montarResumo(r) {
  const dl = document.getElementById('resumo-lista');
  limpar(dl);
  const linha = (rotulo, valor) => dl.append(h('dt', {}, rotulo), h('dd', {}, valor));
  linha('feições', String(r.n_feicoes));
  linha('incluídas no ranque', String(r.n_incluidas));
  linha('filtradas (fora da faixa de inclusão)', String(r.n_filtradas));
  linha('combinador', r.combinador);
  linha('pesos', r.aviso_pesos);
  if (r.crs) linha('CRS de trabalho', `EPSG:${r.crs.srid_trabalho} — ${r.crs.origem || ''}`);
  const ul = document.getElementById('avisos-lista');
  limpar(ul);
  for (const a of r.avisos || []) ul.append(h('li', {}, a));
  document.getElementById('resumo-cartao').hidden = false;
}

function montarRanque(r) {
  const cab = document.getElementById('ranque-cabecalho');
  const corpo = document.getElementById('ranque-corpo');
  limpar(cab); limpar(corpo);
  const ids = r.criterios.map((c) => c.id);
  cab.append(h('th', {}, 'posição'), h('th', {}, 'feição'), h('th', {}, 'nota'), h('th', {}, 'estado'));
  for (const cid of ids) cab.append(h('th', {}, cid));
  cab.append(h('th', {}, 'motivo do filtro'));
  const linhas = [...r.linhas].sort((a, b) => (a.posicao ?? 1e9) - (b.posicao ?? 1e9));
  for (const l of linhas) {
    const tr = h('tr', { 'data-estado': l.estado, 'data-feicao': l.id });
    tr.append(h('td', {}, l.posicao === null ? '—' : String(l.posicao)),
      h('td', {}, String(l.id)), h('td', {}, numero(l.nota)), h('td', {}, l.estado));
    for (const cid of ids) {
      tr.append(h('td', { title: `favorabilidade ${numero(l.favorabilidades[cid])}` }, numero(l.valores[cid], 2)));
    }
    tr.append(h('td', {}, l.motivo_filtro || ''));
    corpo.append(tr);
  }
  document.getElementById('ranque-cartao').hidden = false;
}

/* barras em SVG desenhadas à mão: sem biblioteca de gráfico, sem rede, e o texto do rótulo continua legível
   para leitor de tela na legenda da figura. */
function montarHistogramas(r) {
  const alvo = document.getElementById('histogramas');
  limpar(alvo);
  for (const hist of r.histogramas) {
    const fig = h('figure', { class: 'histograma', 'data-criterio': hist.criterio });
    const largura = 280; const altura = 100;
    const maximo = Math.max(1, ...hist.contagens);
    const n = hist.contagens.length || 1;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `histograma de ${hist.criterio}`);
    hist.contagens.forEach((c, i) => {
      const barra = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      const alt = (c / maximo) * (altura - 2);
      barra.setAttribute('x', String((i * largura) / n));
      barra.setAttribute('y', String(altura - alt));
      barra.setAttribute('width', String(Math.max(1, largura / n - 1)));
      barra.setAttribute('height', String(alt));
      barra.setAttribute('fill', 'currentColor');
      svg.append(barra);
    });
    fig.append(svg);
    const de = hist.bordas.length ? numero(hist.bordas[0], 2) : '—';
    const ate = hist.bordas.length ? numero(hist.bordas[hist.bordas.length - 1], 2) : '—';
    fig.append(h('figcaption', {},
      `${hist.criterio}: ${hist.n} feição(ões) com dado de ${de} a ${ate}; ${hist.n_sem_dado} sem dado`));
    alvo.append(fig);
  }
  document.getElementById('histogramas-cartao').hidden = false;
}

function montarCorrelacao(r) {
  const c = r.correlacao;
  const cab = document.getElementById('correlacao-cabecalho');
  const corpo = document.getElementById('correlacao-corpo');
  limpar(cab); limpar(corpo);
  cab.append(h('th', {}, 'critério'));
  for (const id of c.criterios) cab.append(h('th', {}, id));
  c.criterios.forEach((id, i) => {
    const tr = h('tr', {});
    tr.append(h('th', { scope: 'row' }, id));
    c.criterios.forEach((_, j) => {
      const v = c.matriz[i][j];
      const sinal = v === null ? 'sem' : (v >= 0 ? 'positivo' : 'negativo');
      tr.append(h('td', { 'data-sinal': sinal, 'data-par': `${i}-${j}`,
        title: `${c.pares_com_dado[i][j]} feição(ões) com dado nos dois critérios` },
      v === null ? '—' : v.toFixed(3)));
    });
    corpo.append(tr);
  });
  document.getElementById('correlacao-nota').textContent =
    `${c.metodo} sobre a ${c.sobre}, par a par, só nas feições em que os dois critérios têm dado; `
    + 'traço quer dizer que não há variação suficiente para calcular.';
  document.getElementById('correlacao-cartao').hidden = false;
}

async function avaliar(aviso) {
  const pedido = pedidoDoTexto(aviso);
  if (!pedido) return;
  aviso.limpar?.();
  const resp = await enviar('/api/amc/criterios-feicao', pedido);
  if (resp.status !== 200) {
    aviso.erro((resp.json && resp.json.mensagem) || `a avaliação falhou (${resp.status})`);
    return;
  }
  montarResumo(resp.json);
  montarRanque(resp.json);
  montarHistogramas(resp.json);
  montarCorrelacao(resp.json);
}

async function baixarCsv(aviso) {
  const pedido = pedidoDoTexto(aviso);
  if (!pedido) return;
  /* a resposta é text/csv, não JSON: `chamar` de base/api.js só decodifica JSON, então aqui o fetch é direto
     (mesmas credenciais e mesmo cabeçalho de escrita que ela usa). */
  let resp;
  try {
    resp = await fetch('/api/amc/criterios-feicao/exportar?formato=csv', {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pedido),
    });
  } catch {
    aviso.erro('a exportação não chegou ao servidor');
    return;
  }
  if (resp.status !== 200) {
    aviso.erro(`a exportação falhou (${resp.status})`);
    return;
  }
  const texto = await resp.text();
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }));
  const a = h('a', { href: url, download: 'criterios-de-feicao.csv', id: 'csv-baixado' });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function principal() {
  const aviso = document.getElementById('aviso');
  const r = await chamar('GET', '/api/eu');
  if (r.status === 401) { irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  marcarSessao(!!usuario);
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/amc/criterios-feicao' });
  document.getElementById('pedido').value = JSON.stringify(EXEMPLO, null, 2);
  document.getElementById('rodar').addEventListener('click', () => avaliar(aviso));
  document.getElementById('baixar-csv').addEventListener('click', () => baixarCsv(aviso));
  pronto();
}

principal();
