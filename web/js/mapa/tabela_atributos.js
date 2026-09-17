/* plat · mapa — tabela de atributos sobre a parte inferior do mapa.

   A gaveta conhece feições GeoJSON completas, não o transporte: catálogo pagina por fid e rede
   carrega duas coleções por id. Buscar em segundo plano e desenhar de 200 em 200 mantém a primeira
   tela utilizável; uma geração descarta respostas antigas ao trocar de aba ou fechar. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { obter, consulta, mensagemDe } from '../base/api.js';
import { icone } from '../base/icones.js';

const TETO = 20000;
const LOTE = 200;
const CHAVE_ALTURA = 'plat.sig.tabela.altura';
const numero = (n) => n.toLocaleString('pt-BR');
const texto = (v) => v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);
const interno = (nome, idCampo) => nome === idCampo || nome.startsWith('_')
  || ['fid', 'globalid', 'tipo_id', 'fase_bitmask', 'geometry', 'geometria', 'geom'].includes(nome.toLowerCase());

async function buscar(url) {
  const r = await obter(url);
  if (r.status !== 200 || r.json.error) throw new Error(r.json.error?.message || mensagemDe(r));
  return r.json;
}

export function fonteDeCamada(catalogo, map, camadaId) {
  const ficha = catalogo.ficha(camadaId);
  const url = `/rest/services/${encodeURIComponent(camadaId)}/FeatureServer/0/query`;
  return {
    chave: `camada:${camadaId}`, titulo: ficha.titulo, idCampo: 'fid',
    campos: ficha.campos?.length ? ficha.campos.map((c) => ({ nome: c.nome, rotulo: c.rotulo || c.alias || c.nome })) : null,
    obterTotal: async () => (await buscar(url + consulta({ f: 'json', returnCountOnly: true, where: '1=1' }))).count,
    obterPagina: async (offset, limite) => (await buscar(url + consulta({ f: 'geojson', outFields: '*',
      returnGeometry: true, where: '1=1', resultRecordCount: limite, resultOffset: offset,
      orderByFields: 'fid ASC' }))).features,
    // Getter acompanha ligar/desligar e a recriação das camadas ao trocar o mapa-base.
    get camadas() {
      return catalogo.idsDeEstilo(camadaId).filter((id) => map.getLayer(id)).map((id) => ({
        id, type: ficha.estilo.find((c) => c.id === id)?.type, source: `plat-${camadaId}`,
      }));
    },
    abas: null,
  };
}

export function fonteDeRede(map, redeInfo, colecao = 'pontos') {
  const fontes = {};
  for (const parte of ['pontos', 'linhas']) {
    const cap = parte === 'pontos' ? 'Pontos' : 'Linhas';
    let dados;
    const carregar = () => {
      // A promessa é compartilhada por total/páginas/abas, inclusive antes de a resposta chegar.
      if (!dados) dados = buscar(`/api/rede/${encodeURIComponent(redeInfo.id)}/feicoes/${parte}.geojson`)
        .then((fc) => fc.features).catch((e) => { dados = null; throw e; });
      return dados;
    };
    fontes[parte] = {
      chave: `rede:${redeInfo.id}:${parte}`, titulo: `${redeInfo.nome} — ${t(`mapa.tabela_${parte}`)}`,
      idCampo: 'id', campos: null,
      obterTotal: async () => (await carregar()).length,
      obterPagina: async (offset, limite) => (await carregar()).slice(offset, offset + limite),
      get camadas() {
        const id = redeInfo[`layer${cap}`] || `plat-rede-${redeInfo.id}-${parte}-camada`;
        const source = redeInfo[`fonte${cap}`] || `plat-rede-${redeInfo.id}-${parte}`;
        return map.getLayer(id) ? [{ id, type: parte === 'pontos' ? 'circle' : 'line', source }] : [];
      },
    };
  }
  const abas = ['pontos', 'linhas'].map((parte) => ({ rotulo: t(`mapa.tabela_${parte}`), fonte: fontes[parte] }));
  for (const fonte of Object.values(fontes)) fonte.abas = abas;
  return fontes[colecao];
}

export function montarGaveta({ elGaveta, elAlca, elTitulo, elContagem, elFiltro, elAbas,
  elCabecalho, elCorpo, elFechar, elSentinela, map }) {
  const estado = { _linhas: [] };
  const rolagem = elCorpo.closest('.tabela-gaveta-rolagem');
  const area = elGaveta.closest('#mapa-area');
  let fonte = null, geracao = 0, total = 0, visiveis = [], campos = [], renderizadas = 0;
  let ordem = null, ancora = null, filtro = '', timer, erro = '', carregando = false, cliqueInstalado = false;
  let selecionados = new Set(), pendenteMapa = null;
  const realces = new Set();
  const elementos = new Map();
  const idDe = (f) => f.properties?.[fonte.idCampo];
  const chaveDe = (f) => String(idDe(f));

  elGaveta.setAttribute('role', 'region');
  elAlca.setAttribute('aria-label', t('mapa.tabela_redimensionar'));
  elFechar.setAttribute('aria-label', t('mapa.tabela_fechar'));
  elFiltro.placeholder = t('mapa.tabela_filtro');
  elFiltro.setAttribute('aria-label', t('mapa.tabela_filtrar_linhas'));
  elContagem.setAttribute('aria-live', 'polite');

  function limparRealces() {
    for (const id of realces) if (map.getLayer(id)) map.removeLayer(id);
    realces.clear();
  }

  function _realcar(ids) {
    const cor = getComputedStyle(elGaveta).getPropertyValue('--acento').trim() || '#d98a2b';
    const filtroRealce = ['in', ['get', fonte.idCampo], ['literal', ids.length ? ids : ['__nenhum__']]];
    for (const camada of fonte.camadas) {
      const original = map.getLayer(camada.id);
      if (!original || !['circle', 'line', 'fill', 'symbol'].includes(camada.type)) continue;
      const id = `${camada.id}--realce`;
      if (map.getLayer(id)) { map.setFilter(id, filtroRealce); continue; }
      const type = camada.type === 'fill' ? 'line' : camada.type === 'symbol' ? 'circle' : camada.type;
      // Conserva source-layer do MVT; GeoJSON não possui essa propriedade.
      const estilo = { id, type, source: camada.source, filter: filtroRealce };
      const sourceLayer = original['source-layer'] || original.sourceLayer;
      if (sourceLayer) estilo['source-layer'] = sourceLayer;
      const maior = (prop, padrao, soma) => {
        const valor = map.getPaintProperty(camada.id, prop);
        // Expressões de zoom precisam continuar no nível superior da pintura: use um tamanho seguro.
        return typeof valor === 'number' ? valor + soma : padrao + soma;
      };
      estilo.paint = type === 'circle'
        ? { 'circle-color': cor, 'circle-radius': camada.type === 'symbol' ? 10 : maior('circle-radius', 5, 5),
          'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' }
        : { 'line-color': cor, 'line-width': camada.type === 'fill' ? 4 : maior('line-width', 2, 4) };
      map.addLayer(estilo);
      realces.add(id);
    }
  }

  function atualizarSelecao() {
    for (const [id, tr] of elementos) {
      tr.classList.toggle('selecionada', selecionados.has(id));
      tr.setAttribute('aria-selected', String(selecionados.has(id)));
    }
    _realcar(estado._linhas.filter((f) => selecionados.has(chaveDe(f))).map(idDe));
  }

  function enquadrarSeUmaSo() {
    if (selecionados.size !== 1) return;
    const feicao = estado._linhas.find((f) => selecionados.has(chaveDe(f)));
    let bbox = null;
    const coordenadas = (c) => {
      if (!Array.isArray(c)) return;
      if (typeof c[0] === 'number' && Number.isFinite(c[0]) && Number.isFinite(c[1])) {
        bbox = bbox ? [Math.min(bbox[0], c[0]), Math.min(bbox[1], c[1]), Math.max(bbox[2], c[0]), Math.max(bbox[3], c[1])]
          : [c[0], c[1], c[0], c[1]];
      } else c.forEach(coordenadas);
    };
    const geometria = (g) => { if (g?.type === 'GeometryCollection') g.geometries.forEach(geometria); else coordenadas(g?.coordinates); };
    geometria(feicao?.geometry);
    if (bbox) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {
      padding: { top: 60, left: 60, right: 60, bottom: elGaveta.getBoundingClientRect().height + 60 },
      duration: 350, maxZoom: 18,
    });
  }

  function selecionar(indice, ev = {}, enquadrar = true) {
    const id = chaveDe(visiveis[indice]);
    const anterior = visiveis.findIndex((f) => chaveDe(f) === ancora);
    if (ev.shiftKey && anterior >= 0) {
      if (!ev.ctrlKey && !ev.metaKey) selecionados.clear();
      for (let i = Math.min(anterior, indice); i <= Math.max(anterior, indice); i++) selecionados.add(chaveDe(visiveis[i]));
    } else {
      if (ev.ctrlKey || ev.metaKey) {
        if (selecionados.has(id)) selecionados.delete(id); else selecionados.add(id);
      } else selecionados = new Set([id]);
      ancora = id;
    }
    atualizarSelecao();
    if (enquadrar) enquadrarSeUmaSo();
  }

  function contar() {
    const n = filtro ? visiveis.length : estado._linhas.length;
    const y = filtro ? estado._linhas.length : total;
    elContagem.textContent = erro || (carregando && !estado._linhas.length ? t('mapa.tabela_carregando')
      : t('mapa.tabela_contagem', { n: numero(n), total: numero(y) }));
    elTitulo.textContent = fonte.titulo + (total > TETO ? ` — ${t('mapa.tabela_limite', {
      n: numero(estado._linhas.length), total: numero(total),
    })}` : '');
  }

  function anexarLote() {
    const fim = Math.min(renderizadas + LOTE, visiveis.length);
    const fragmento = document.createDocumentFragment();
    for (let i = renderizadas; i < fim; i++) {
      const feicao = visiveis[i], id = chaveDe(feicao);
      const tr = h('tr', { tabindex: '0', class: selecionados.has(id) ? 'selecionada' : '',
        'aria-selected': String(selecionados.has(id)), dataset: { id }, onclick: (ev) => selecionar(i, ev),
        onkeydown: (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); selecionar(i, ev); }
        } });
      for (const c of campos) tr.append(h('td', {}, texto(feicao.properties?.[c.nome])));
      elementos.set(id, tr); fragmento.append(tr);
    }
    elCorpo.append(fragmento); renderizadas = fim;
    // A sentinela fica depois da tabela, nunca participa da ordenação nem da seleção.
    elSentinela.hidden = renderizadas >= visiveis.length;
  }

  function recalcular(reiniciar = true) {
    visiveis = estado._linhas.filter((f) => !filtro || Object.values(f.properties || {})
      .some((v) => texto(v).toLocaleLowerCase('pt-BR').includes(filtro)));
    if (ordem) visiveis.sort((a, b) => {
      const x = a.properties?.[ordem.nome], y = b.properties?.[ordem.nome];
      if (x == null) return y == null ? 0 : 1;
      if (y == null) return -1;
      const nx = typeof x === 'number' || typeof x === 'string' && x.trim() !== '' ? Number(x) : NaN;
      const ny = typeof y === 'number' || typeof y === 'string' && y.trim() !== '' ? Number(y) : NaN;
      return (Number.isFinite(nx) && Number.isFinite(ny) ? nx - ny : texto(x).localeCompare(texto(y), 'pt-BR')) * ordem.direcao;
    });
    const quantidade = reiniciar ? LOTE : Math.max(LOTE, renderizadas);
    const scroll = rolagem.scrollTop;
    limpar(elCorpo); elementos.clear(); renderizadas = 0;
    do { anexarLote(); } while (renderizadas < Math.min(quantidade, visiveis.length));
    if (!visiveis.length) elCorpo.append(h('tr', { class: 'tabela-gaveta-vazia' }, h('td', {
      colspan: Math.max(1, campos.length),
    }, erro || (carregando ? t('mapa.tabela_carregando') : t('mapa.tabela_sem_linhas')))));
    rolagem.scrollTop = reiniciar ? 0 : scroll;
    contar();
  }

  function cabecalho() {
    limpar(elCabecalho);
    const tr = h('tr');
    for (const c of campos) {
      const atual = ordem?.nome === c.nome ? ordem.direcao : 0;
      const ordenar = () => {
        ordem = atual === -1 ? null : { nome: c.nome, direcao: atual === 1 ? -1 : 1 };
        cabecalho(); recalcular();
      };
      tr.append(h('th', { scope: 'col', tabindex: '0', 'aria-sort': atual === 1 ? 'ascending' : atual === -1 ? 'descending' : 'none',
        onclick: ordenar, onkeydown: (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ordenar(); }
        } }, c.rotulo || c.nome, atual === 0 ? '' : icone(atual === 1 ? 'ordenar_asc' : 'ordenar_desc', { tamanho: 14 })));
    }
    elCabecalho.append(tr);
  }

  function selecionarDoMapa(id) {
    if (!estado._linhas.some((f) => chaveDe(f) === id)) return false;
    if (!visiveis.some((f) => chaveDe(f) === id)) {
      clearTimeout(timer); elFiltro.value = ''; filtro = ''; recalcular();
    }
    const indice = visiveis.findIndex((f) => chaveDe(f) === id);
    selecionar(indice, {}, false);
    while (renderizadas <= indice) anexarLote();
    elementos.get(id)?.scrollIntoView({ block: 'center' });
    return true;
  }

  function instalarClique() {
    if (cliqueInstalado) return;
    cliqueInstalado = true;
    map.on('click', (ev) => {
      if (map.getCanvas().style.cursor === 'crosshair') return;
      if (elGaveta.hidden || !fonte) return;
      const layers = fonte.camadas.map((c) => c.id).filter((id) => map.getLayer(id));
      if (!layers.length) return;
      const feicao = map.queryRenderedFeatures(ev.point, { layers })[0];
      if (!feicao) return;
      const id = String(idDe(feicao));
      pendenteMapa = selecionarDoMapa(id) ? null : id;
      if (pendenteMapa && !carregando) {
        elContagem.textContent = t('mapa.tabela_fora_limite'); pendenteMapa = null;
      }
    });
  }

  function desenharAbas(versao) {
    limpar(elAbas);
    for (const aba of fonte.abas || []) {
      const botao = h('button', { type: 'button', class: 'sig-botao-mini',
        'aria-pressed': String(aba.fonte.chave === fonte.chave), onclick: () => abrir(aba.fonte),
      }, `${aba.rotulo} (…)`);
      elAbas.append(botao);
      aba.fonte.obterTotal().then((n) => {
        if (versao === geracao) botao.textContent = `${aba.rotulo} (${numero(n)})`;
      }).catch(() => { if (versao === geracao) botao.textContent = `${aba.rotulo} — ${t('mapa.tabela_erro_aba')}`; });
    }
  }

  async function carregar(versao, atual) {
    try {
      const [n, primeira] = await Promise.all([atual.obterTotal(), atual.obterPagina(0, 500)]);
      if (versao !== geracao) return;
      total = n; estado._linhas = primeira.slice(0, TETO);
      campos = (atual.campos || Object.keys(primeira[0]?.properties || {}).map((nome) => ({ nome, rotulo: nome })))
        .filter((c) => !interno(c.nome, atual.idCampo));
      cabecalho(); recalcular();
      if (pendenteMapa && selecionarDoMapa(pendenteMapa)) pendenteMapa = null;
      while (estado._linhas.length < Math.min(total, TETO)) {
        // Dá ao navegador uma oportunidade de pintar a primeira tela antes da próxima página.
        await new Promise((r) => setTimeout(r, 0));
        if (versao !== geracao) return;
        const pagina = await atual.obterPagina(estado._linhas.length, Math.min(2000, TETO - estado._linhas.length));
        if (versao !== geracao) return;
        if (!pagina.length) throw new Error(t('mapa.tabela_pagina_vazia'));
        estado._linhas.push(...pagina.slice(0, TETO - estado._linhas.length));
        recalcular(false);
        if (pendenteMapa && selecionarDoMapa(pendenteMapa)) pendenteMapa = null;
      }
    } catch (e) {
      if (versao !== geracao) return;
      erro = t('mapa.tabela_erro', { erro: e.message });
    } finally {
      if (versao === geracao) {
        carregando = false; recalcular(false);
        if (pendenteMapa) {
          elContagem.textContent = t('mapa.tabela_fora_limite'); pendenteMapa = null;
        }
      }
    }
  }

  function altura(px) {
    const max = Math.max(120, area.getBoundingClientRect().height * .7);
    elGaveta.style.height = `${Math.max(120, Math.min(px, max))}px`;
  }

  function abrir(novaFonte) {
    if (!elGaveta.hidden && fonte?.chave === novaFonte.chave) { elFiltro.focus(); return; }
    limparRealces(); clearTimeout(timer); geracao++;
    fonte = novaFonte; estado._linhas = []; visiveis = []; campos = []; selecionados.clear();
    ancora = null; pendenteMapa = null; ordem = null; filtro = ''; total = 0; erro = ''; carregando = true;
    elFiltro.value = ''; elGaveta.hidden = false; elGaveta.setAttribute('aria-label', fonte.titulo);
    try { altura(Number(localStorage.getItem(CHAVE_ALTURA)) || window.innerHeight * .22); }
    catch { altura(window.innerHeight * .22); }
    cabecalho(); recalcular(); desenharAbas(geracao); instalarClique();
    elFiltro.focus();
    void carregar(geracao, fonte);
  }

  function fechar() {
    geracao++; clearTimeout(timer); limparRealces(); elGaveta.hidden = true;
    estado._linhas = []; visiveis = []; elementos.clear(); limpar(elCorpo); limpar(elAbas);
    fonte = null; pendenteMapa = null;
  }
  elFechar.addEventListener('click', fechar);
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape' || elGaveta.hidden || document.querySelector('.menu-contexto')) return;
    const foco = document.activeElement;
    if (!elGaveta.contains(foco) && foco?.matches('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
    ev.preventDefault(); ev.stopImmediatePropagation(); fechar();
  }, true);
  elFiltro.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { filtro = elFiltro.value.toLocaleLowerCase('pt-BR'); recalcular(); }, 150);
  });
  if (typeof IntersectionObserver !== 'undefined') {
    const observador = new IntersectionObserver((entradas) => {
      if (!elGaveta.hidden && entradas.some((e) => e.isIntersecting)) anexarLote();
    }, { root: rolagem, rootMargin: '0px 0px 80px 0px' });
    observador.observe(elSentinela);
  }
  // Também cobre navegadores sem IntersectionObserver e uma sentinela que permaneça visível.
  rolagem.addEventListener('scroll', () => {
    if (!elGaveta.hidden && rolagem.scrollTop + rolagem.clientHeight >= rolagem.scrollHeight - 80) anexarLote();
  });
  let arrastando = false;
  elAlca.addEventListener('pointerdown', (ev) => {
    ev.preventDefault(); arrastando = true;
    try { elAlca.setPointerCapture(ev.pointerId); } catch { /* captura indisponível no teste DOM */ }
  });
  elAlca.addEventListener('pointermove', (ev) => {
    if (arrastando) altura(area.getBoundingClientRect().bottom - 26 - ev.clientY);
  });
  const soltar = (ev) => {
    if (!arrastando) return;
    arrastando = false;
    try { elAlca.releasePointerCapture(ev.pointerId); } catch { /* captura já liberada */ }
    try { localStorage.setItem(CHAVE_ALTURA, String(elGaveta.getBoundingClientRect().height)); } catch { /* sem persistência */ }
  };
  elAlca.addEventListener('pointerup', soltar);
  elAlca.addEventListener('pointercancel', soltar);
  window.addEventListener('resize', () => { if (!elGaveta.hidden) altura(elGaveta.getBoundingClientRect().height); });
  return { abrir, fechar, estaAberta: () => !elGaveta.hidden, fonteAtual: () => fonte };
}
