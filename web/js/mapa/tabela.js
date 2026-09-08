/* plat · tabela de atributos acoplada ao mapa (item L2-01-g-tabela-atributos). Módulo ES sem build; nunca ?v=
   nos imports (duas instâncias do módulo derrubam a tela — o cache é resolvido por no-store no nginx).

   Divisão de trabalho com o servidor, que é o ponto do item: a tela NUNCA carrega a camada inteira. Página,
   ordem, busca, extensão, seleção e estatísticas são calculadas no banco (app/tabela/rotas.py); o que chega
   aqui é uma página de no máximo 1.000 linhas e um total. Por isso rolar cem páginas não faz a memória do
   navegador crescer: cada página SUBSTITUI o corpo da tabela, e o desenho no mapa vem de uma consulta própria
   limitada pela extensão visível.

   Duas consultas por atualização, de propósito:
   - `linhas` da TABELA aplica a seleção (fids) — é o que faz "3 feições selecionadas = 3 linhas";
   - `linhas` do MAPA não aplica a seleção, senão selecionar uma feição apagaria as outras da tela e não
     haveria como acrescentar a segunda.

   Realce: uma camada MapLibre separada, filtrada pelo identificador da chave primária; a linha da tabela e a
   feição do mapa compartilham esse identificador, que é o mesmo `id` que a API devolve. */
import { obter, enviar, alterar } from '../base/api.js';
import { t } from '../base/i18n.js';
import { h, limpar } from '../base/dom.js';

const FONTE = 'plat-tabela-feicoes';
const CAMADAS = ['plat-tabela-poligono', 'plat-tabela-linha', 'plat-tabela-ponto'];
const REALCE = ['plat-tabela-poligono-realce', 'plat-tabela-linha-realce', 'plat-tabela-ponto-realce'];
const PAGINAS = [50, 200, 1000];
const FEICOES_NO_MAPA = 1000;

const el = (id) => document.getElementById(id);

export function criarTabela(map, aviso) {
  const estado = {
    camadaId: null, colunas: [], chave: null, temGeometria: false,
    pagina: 1, porPagina: PAGINAS[0], ordenarPor: null, ordem: 'asc',
    busca: '', soExtensao: false, selecionados: new Set(), linhas: [], total: 0, foco: -1,
    // o total só é recontado quando o FILTRO muda: paginar e reordenar não mudam quantas linhas passam pelo
    // filtro, e a contagem numa camada de um milhão custa mais que a página inteira (ver app/tabela/rotas.py)
    recontar: true,
  };
  let popup = null;

  // ---------------------------------------------------------------- fontes e camadas do mapa
  function garantirCamadasDoMapa() {
    if (map.getSource(FONTE)) return;
    map.addSource(FONTE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: CAMADAS[0], type: 'fill', source: FONTE, filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#2f7f6f', 'fill-opacity': 0.35, 'fill-outline-color': '#1c4d43' } });
    map.addLayer({ id: CAMADAS[1], type: 'line', source: FONTE, filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': '#2f7f6f', 'line-width': 2 } });
    map.addLayer({ id: CAMADAS[2], type: 'circle', source: FONTE, filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 5, 'circle-color': '#2f7f6f', 'circle-stroke-color': '#0d1b18', 'circle-stroke-width': 1 } });
    map.addLayer({ id: REALCE[0], type: 'fill', source: FONTE,
      filter: ['all', ['==', ['geometry-type'], 'Polygon'], ['in', ['get', 'plat_id'], ['literal', []]]],
      paint: { 'fill-color': '#e8b33a', 'fill-opacity': 0.55, 'fill-outline-color': '#7a5c12' } });
    map.addLayer({ id: REALCE[1], type: 'line', source: FONTE,
      filter: ['all', ['==', ['geometry-type'], 'LineString'], ['in', ['get', 'plat_id'], ['literal', []]]],
      paint: { 'line-color': '#e8b33a', 'line-width': 4 } });
    map.addLayer({ id: REALCE[2], type: 'circle', source: FONTE,
      filter: ['all', ['==', ['geometry-type'], 'Point'], ['in', ['get', 'plat_id'], ['literal', []]]],
      paint: { 'circle-radius': 8, 'circle-color': '#e8b33a', 'circle-stroke-color': '#3a2c06', 'circle-stroke-width': 2 } });
    for (const camada of CAMADAS) {
      map.on('click', camada, (ev) => {
        const f = ev.features && ev.features[0];
        if (!f) return;
        const id = f.properties && f.properties.plat_id;
        if (id === undefined || id === null) return;
        if (!(ev.originalEvent && (ev.originalEvent.shiftKey || ev.originalEvent.ctrlKey))) estado.selecionados.clear();
        if (estado.selecionados.has(id)) estado.selecionados.delete(id); else estado.selecionados.add(id);
        estado.pagina = 1;
        estado.recontar = true;
        aplicarRealce();
        atualizarTabela();
      });
      map.on('mouseenter', camada, () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', camada, () => { map.getCanvas().style.cursor = ''; });
    }
  }

  function aplicarRealce() {
    if (!map.getLayer(REALCE[0])) return;
    const ids = [...estado.selecionados];
    const tipos = ['Polygon', 'LineString', 'Point'];
    REALCE.forEach((camada, i) => {
      map.setFilter(camada, ['all', ['==', ['geometry-type'], tipos[i]], ['in', ['get', 'plat_id'], ['literal', ids]]]);
    });
    el('tabela-selecao').textContent = t('tabela.selecionadas', { n: ids.length });
    el('tabela-limpar').disabled = ids.length === 0;
  }

  // ---------------------------------------------------------------- chamadas à API
  const base = () => `/api/camadas/${encodeURIComponent(estado.camadaId)}/tabela`;

  function extensao() {
    const b = map.getBounds();
    return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  }

  function filtroDaTabela() {
    const f = {};
    if (estado.busca) f.busca = estado.busca;
    if (estado.soExtensao && estado.temGeometria) f.bbox = extensao();
    if (estado.selecionados.size) f.fids = [...estado.selecionados];
    return f;
  }

  async function carregarColunas() {
    const r = await obter(`${base()}/colunas`);
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return false; }
    estado.colunas = r.json.colunas || [];
    estado.chave = r.json.chave;
    estado.temGeometria = !!r.json.tem_geometria;
    if (estado.ordenarPor && !estado.colunas.some((c) => c.nome === estado.ordenarPor)) estado.ordenarPor = null;
    return true;
  }

  async function atualizarTabela() {
    if (!estado.camadaId) return;
    const corpo = {
      ...filtroDaTabela(), pagina: estado.pagina, por_pagina: estado.porPagina,
      ordenar_por: estado.ordenarPor, ordem: estado.ordem, contar: estado.recontar,
    };
    const r = await enviar(`${base()}/linhas`, corpo);
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return; }
    estado.linhas = r.json.linhas || [];
    if (r.json.total !== null && r.json.total !== undefined) estado.total = r.json.total;
    estado.recontar = false;
    estado.colunas = r.json.colunas || estado.colunas;
    desenharGrade();
  }

  async function atualizarMapa() {
    if (!estado.camadaId || !estado.temGeometria) return;
    garantirCamadasDoMapa();
    const corpo = { bbox: extensao(), geometria: true, por_pagina: FEICOES_NO_MAPA, pagina: 1 };
    if (estado.busca) corpo.busca = estado.busca;
    const r = await enviar(`${base()}/linhas`, corpo);
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return; }
    const features = (r.json.linhas || []).filter((l) => l.geometria).map((l) => ({
      type: 'Feature', geometry: l.geometria, properties: { ...l.valores, plat_id: l.id },
    }));
    map.getSource(FONTE).setData({ type: 'FeatureCollection', features });
    aplicarRealce();
  }

  async function gravarVista(colunas) {
    const r = await alterar(`${base()}/vista`, { colunas });
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return false; }
    return true;
  }

  // ---------------------------------------------------------------- desenho da grade
  function rotulo(coluna, valor) {
    if (valor === null || valor === undefined) return '';
    if (coluna.dominio) {
      const descricao = coluna.dominio[String(valor)];
      if (descricao !== undefined) return descricao;
    }
    return String(valor);
  }

  function desenharCabecalho() {
    const tr = limpar(el('tabela-cabecalho'));
    for (const c of estado.colunas) {
      const seta = estado.ordenarPor === c.nome ? (estado.ordem === 'asc' ? ' ▲' : ' ▼') : '';
      const th = h('th', {
        scope: 'col', dataset: { coluna: c.nome },
        title: c.nome,
        'aria-sort': estado.ordenarPor === c.nome ? (estado.ordem === 'asc' ? 'ascending' : 'descending') : 'none',
      }, h('button', {
        type: 'button', class: 'tabela-ordenar',
        onclick: () => {
          if (estado.ordenarPor === c.nome) estado.ordem = estado.ordem === 'asc' ? 'desc' : 'asc';
          else { estado.ordenarPor = c.nome; estado.ordem = 'asc'; }
          estado.pagina = 1;
          atualizarTabela();
        },
      }, c.alias + seta), h('span', { class: 'tabela-puxador', dataset: { puxador: c.nome } }));
      if (c.largura) th.style.width = `${c.largura}px`;
      tr.append(th);
    }
  }

  function desenharGrade() {
    desenharCabecalho();
    const corpo = limpar(el('tabela-corpo'));
    estado.linhas.forEach((linha, i) => {
      const tr = h('tr', {
        tabindex: '-1', dataset: { id: String(linha.id), indice: String(i) },
        class: estado.selecionados.has(linha.id) ? 'selecionada' : '',
        onclick: (ev) => selecionarLinha(i, ev.shiftKey || ev.ctrlKey),
      });
      for (const c of estado.colunas) tr.append(h('td', {}, rotulo(c, linha.valores[c.nome])));
      corpo.append(tr);
    });
    const paginas = Math.max(1, Math.ceil(estado.total / estado.porPagina));
    el('tabela-contagem').textContent = t('tabela.contagem', { total: estado.total });
    el('tabela-paginacao').textContent = t('tabela.pagina_de', { pagina: estado.pagina, paginas });
    el('tabela-anterior').disabled = estado.pagina <= 1;
    el('tabela-proxima').disabled = estado.pagina >= paginas;
    aplicarRealce();
  }

  function selecionarLinha(indice, acrescentar) {
    const linha = estado.linhas[indice];
    if (!linha || linha.id === undefined || linha.id === null) return;
    if (!acrescentar) estado.selecionados.clear();
    if (estado.selecionados.has(linha.id) && acrescentar) estado.selecionados.delete(linha.id);
    else estado.selecionados.add(linha.id);
    estado.foco = indice;
    for (const tr of el('tabela-corpo').children) {
      tr.classList.toggle('selecionada', estado.selecionados.has(Number(tr.dataset.id)));
    }
    aplicarRealce();
    centrarNaFeicao(linha.id);
  }

  function centrarNaFeicao(id) {
    if (!estado.temGeometria || !map.getSource(FONTE)) return;
    const dados = map.getSource(FONTE)._data;
    const f = dados && dados.features && dados.features.find((x) => x.properties.plat_id === id);
    if (!f) return;
    const centro = centroide(f.geometry);
    if (centro) map.easeTo({ center: centro, duration: 300 });
  }

  function centroide(geometria) {
    const pontos = [];
    const juntar = (c) => {
      if (typeof c[0] === 'number') pontos.push(c);
      else for (const p of c) juntar(p);
    };
    if (!geometria || !geometria.coordinates) return null;
    juntar(geometria.coordinates);
    if (!pontos.length) return null;
    const soma = pontos.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]);
    return [soma[0] / pontos.length, soma[1] / pontos.length];
  }

  // ---------------------------------------------------------------- popup de uma linha
  function abrirPopup(indice) {
    const linha = estado.linhas[indice];
    if (!linha) return;
    const lista = h('dl', { class: 'tabela-popup' });
    for (const c of estado.colunas) {
      lista.append(h('dt', {}, c.alias), h('dd', {}, rotulo(c, linha.valores[c.nome])));
    }
    const caixa = el('tabela-popup');
    limpar(caixa).append(h('div', { class: 'tabela-popup-topo' },
      h('strong', {}, t('tabela.popup_titulo', { id: linha.id })),
      h('button', { type: 'button', class: 'secundario', onclick: fecharPopup }, t('tabela.fechar'))), lista);
    caixa.hidden = false;
    if (estado.temGeometria && map.getSource(FONTE)) {
      const dados = map.getSource(FONTE)._data;
      const f = dados && dados.features && dados.features.find((x) => x.properties.plat_id === linha.id);
      const centro = f && centroide(f.geometry);
      if (centro && window.maplibregl) {
        if (popup) popup.remove();
        popup = new window.maplibregl.Popup({ closeOnClick: true })
          .setLngLat(centro).setText(String(linha.id)).addTo(map);
      }
    }
    caixa.querySelector('button').focus();
  }

  function fecharPopup() {
    el('tabela-popup').hidden = true;
    if (popup) { popup.remove(); popup = null; }
    const tr = el('tabela-corpo').children[estado.foco];
    if (tr) tr.focus();
  }

  // ---------------------------------------------------------------- teclado (setas + Enter)
  function moverFoco(delta) {
    const linhas = el('tabela-corpo').children;
    if (!linhas.length) return;
    const proximo = Math.min(linhas.length - 1, Math.max(0, (estado.foco < 0 ? 0 : estado.foco + delta)));
    estado.foco = proximo;
    linhas[proximo].focus();
  }

  function ligarTeclado() {
    el('tabela-corpo').addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); moverFoco(1); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); moverFoco(-1); }
      else if (ev.key === 'Enter') { ev.preventDefault(); abrirPopup(estado.foco); }
      else if (ev.key === 'Escape') fecharPopup();
    });
    el('tabela-corpo').addEventListener('focusin', (ev) => {
      const tr = ev.target.closest('tr');
      if (tr) estado.foco = Number(tr.dataset.indice);
    });
  }

  // ---------------------------------------------------------------- largura de coluna (arrastar e persistir)
  function ligarRedimensionamento() {
    let alvo = null, xInicial = 0, larguraInicial = 0;
    el('tabela-cabecalho').addEventListener('mousedown', (ev) => {
      const puxador = ev.target.closest('[data-puxador]');
      if (!puxador) return;
      ev.preventDefault();
      alvo = puxador.closest('th');
      xInicial = ev.clientX;
      larguraInicial = alvo.getBoundingClientRect().width;
    });
    document.addEventListener('mousemove', (ev) => {
      if (!alvo) return;
      alvo.style.width = `${Math.max(40, Math.round(larguraInicial + ev.clientX - xInicial))}px`;
    });
    document.addEventListener('mouseup', async () => {
      if (!alvo) return;
      alvo = null;
      await persistirLarguras();
    });
  }

  async function persistirLarguras() {
    const r = await obter(`${base()}/vista`);
    if (r.status !== 200) return;
    const colunas = (r.json.colunas || []).map((c) => {
      const th = el('tabela-cabecalho').querySelector(`th[data-coluna="${CSS.escape(c.nome)}"]`);
      const largura = th ? Math.round(th.getBoundingClientRect().width) : c.largura;
      const saida = { nome: c.nome, oculta: !!c.oculta };
      if (largura) saida.largura = Math.min(2000, Math.max(40, largura));
      if (c.alias && c.alias !== c.nome) saida.alias = c.alias;
      if (c.dominio) saida.dominio = c.dominio;
      return saida;
    });
    await gravarVista(colunas);
  }

  // ---------------------------------------------------------------- painel de colunas (mostrar/ocultar, alias)
  async function abrirPainelColunas() {
    const r = await obter(`${base()}/vista`);
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return; }
    const caixa = el('tabela-colunas-painel');
    const atuais = (r.json.colunas || []).filter((c) => c.tipo !== 'geometria');
    const linhas = atuais.map((c) => h('li', {},
      h('label', {}, h('input', {
        type: 'checkbox', checked: !c.oculta, dataset: { coluna: c.nome }, class: 'tabela-visivel',
      }), ' ', c.nome),
      h('input', { type: 'text', value: c.alias || c.nome, dataset: { alias: c.nome }, class: 'tabela-alias',
        maxlength: '200', 'aria-label': c.nome })));
    limpar(caixa).append(
      h('div', { class: 'tabela-popup-topo' }, h('strong', {}, t('tabela.colunas')),
        h('button', { type: 'button', class: 'secundario', onclick: () => { caixa.hidden = true; } }, t('tabela.fechar'))),
      h('ul', {}, linhas),
      h('button', {
        type: 'button', id: 'tabela-colunas-gravar',
        onclick: async () => {
          const colunas = atuais.map((c) => {
            const visivel = caixa.querySelector(`input.tabela-visivel[data-coluna="${CSS.escape(c.nome)}"]`);
            const alias = caixa.querySelector(`input.tabela-alias[data-alias="${CSS.escape(c.nome)}"]`);
            const saida = { nome: c.nome, oculta: !visivel.checked };
            if (c.largura) saida.largura = c.largura;
            if (alias && alias.value && alias.value !== c.nome) saida.alias = alias.value;
            if (c.dominio) saida.dominio = c.dominio;
            return saida;
          });
          if (await gravarVista(colunas)) {
            caixa.hidden = true;
            await carregarColunas();
            await atualizarTabela();
          }
        },
      }, t('tabela.gravar')));
    caixa.hidden = false;
  }

  // ---------------------------------------------------------------- estatísticas por coluna numérica
  async function abrirEstatisticas() {
    const r = await enviar(`${base()}/estatisticas`, filtroDaTabela());
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return; }
    const caixa = el('tabela-estatisticas-painel');
    const entradas = Object.entries(r.json.colunas || {});
    const cabecalho = ['coluna', 'contagem', 'soma', 'media', 'minimo', 'maximo', 'nulos'];
    const tabela = h('table', { class: 'tabela-estatisticas' },
      h('thead', {}, h('tr', {}, cabecalho.map((c) => h('th', { scope: 'col' }, t(`tabela.est_${c}`))))),
      h('tbody', {}, entradas.map(([nome, e]) => h('tr', {},
        h('th', { scope: 'row' }, nome),
        [e.contagem, e.soma, e.media, e.minimo, e.maximo, e.nulos].map((v) => h('td', {}, v === null || v === undefined ? '' : String(v)))))));
    limpar(caixa).append(
      h('div', { class: 'tabela-popup-topo' }, h('strong', {}, t('tabela.estatisticas')),
        h('button', { type: 'button', class: 'secundario', onclick: () => { caixa.hidden = true; } }, t('tabela.fechar'))),
      entradas.length ? tabela : h('p', {}, t('tabela.sem_numericas')));
    caixa.hidden = false;
  }

  // ---------------------------------------------------------------- barra e ligação dos controles
  async function listarCamadas() {
    const r = await obter('/api/itens?tipo=camada_vetorial&limite=100');
    if (r.status !== 200) { aviso.erro(r.json.mensagem); return []; }
    return (r.json.itens || []).map((i) => ({ id: i.id, titulo: i.titulo }));
  }

  async function trocarCamada(id) {
    estado.camadaId = id;
    estado.pagina = 1;
    estado.selecionados.clear();
    estado.ordenarPor = null;
    estado.recontar = true;
    if (!id) return;
    if (!await carregarColunas()) return;
    await atualizarTabela();
    await atualizarMapa();
  }

  async function iniciar() {
    const camadas = await listarCamadas();
    const sel = el('tabela-camada');
    // espalhar a lista: `append(no, array)` converte o array em texto e o <select> fica só com a opção vazia
    limpar(sel).append(h('option', { value: '' }, t('tabela.escolha_camada')),
      ...camadas.map((c) => h('option', { value: c.id }, c.titulo)));
    sel.addEventListener('change', () => trocarCamada(sel.value));

    el('tabela-busca').addEventListener('change', () => {
      estado.busca = el('tabela-busca').value.trim();
      estado.pagina = 1;
      estado.recontar = true;
      atualizarTabela();
      atualizarMapa();
    });
    el('tabela-extensao').addEventListener('change', () => {
      estado.soExtensao = el('tabela-extensao').checked;
      estado.pagina = 1;
      estado.recontar = true;
      atualizarTabela();
    });
    const porPagina = el('tabela-por-pagina');
    limpar(porPagina).append(PAGINAS.map((n) => h('option', { value: String(n) }, String(n))));
    porPagina.value = String(estado.porPagina);
    porPagina.addEventListener('change', () => {
      estado.porPagina = Number(porPagina.value);
      estado.pagina = 1;
      estado.recontar = true;
      atualizarTabela();
    });
    el('tabela-anterior').addEventListener('click', () => { estado.pagina = Math.max(1, estado.pagina - 1); atualizarTabela(); });
    el('tabela-proxima').addEventListener('click', () => { estado.pagina += 1; atualizarTabela(); });
    el('tabela-limpar').addEventListener('click', () => {
      estado.selecionados.clear();
      estado.pagina = 1;
      estado.recontar = true;
      aplicarRealce();
      atualizarTabela();
    });
    el('tabela-colunas-abrir').addEventListener('click', abrirPainelColunas);
    el('tabela-estatisticas-abrir').addEventListener('click', abrirEstatisticas);
    el('tabela-alternar').addEventListener('click', () => {
      const painel = el('painel-tabela');
      painel.hidden = !painel.hidden;
      el('tabela-alternar').setAttribute('aria-expanded', String(!painel.hidden));
      if (!painel.hidden) atualizarMapa();
    });
    map.on('moveend', () => {
      atualizarMapa();
      if (estado.soExtensao) atualizarTabela();
    });
    ligarTeclado();
    ligarRedimensionamento();
    if (camadas.length === 1) { sel.value = camadas[0].id; await trocarCamada(camadas[0].id); }
  }

  return { iniciar, estado };
}
