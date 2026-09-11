/* plat · SIG — Comparar (item L2-01-j-comparacao-cortina-tempo).

   Quatro ferramentas, uma barra de instrumento:
     1. Cortina (swipe) vertical/horizontal entre dois CONJUNTOS de camadas (A = esquerda, B = direita),
        alça arrastável.
     2. Lado a lado: dois mapas independentes com centro/zoom/rotação sincronizados por evento.
     3. Lupa: círculo que segue o cursor mostrando o conjunto B por cima do mapa principal.
     4. Tempo: filtro de janela (instantânea/acumulativa) sobre uma camada vetorial com campo de
        data/hora — o filtro é aplicado NO SERVIDOR (operação `query` do FeatureServer, mesmo motor
        Esri-compatível de app/consulta/motor.py: `where=<campo> >= TIMESTAMP '...' AND <campo> <
        TIMESTAMP '...'`), nunca escondido no cliente — o cliente só desenha o GeoJSON que o servidor
        já filtrou e mostra a contagem que o servidor mesmo devolveu (`returnCountOnly=true`).

   Cortina/lado-a-lado/lupa reaproveitam `Catalogo` (web/js/mapa/catalogo.js) em DUAS instâncias, uma
   por mapa secundário — mesmo motor de fonte/estilo do mapa principal, sem reescrever tile/TileJSON.

   Estado do modo de comparação e das camadas escolhidas fica na URL (`cmp`, `cmpa`, `cmpb`) — item
   pede "estado na URL"; tempo NÃO entra na URL (a janela é efêmera, reproduzida, não um destino
   para compartilhar).
*/
import { h, limpar } from '../base/dom.js';
import { obter } from '../base/api.js';
import { t } from '../base/i18n.js';
import { construirEstilo } from '../mapa/estilo.js';
import { Catalogo } from '../mapa/catalogo.js';

const MODOS = ['desligado', 'cortina-v', 'cortina-h', 'lado-a-lado', 'lupa'];
const RAIO_LUPA = 130; // px

function camadasVetoriais(disponiveis) {
  return disponiveis.filter((f) => Array.isArray(f.campos));
}

function campoTemporal(ficha) {
  return (ficha.campos || []).find((c) => /timestamp|^date$/i.test(c.tipo || ''));
}

function isoParaLiteralEsri(d) {
  // "YYYY-MM-DDTHH:MM:SS.sssZ" -> "YYYY-MM-DD HH:MM:SS" (UTC; sessão do Postgres é Etc/UTC — sem
  // isto o literal TIMESTAMP do dialeto Esri (where_ast) rejeita o "Z"/milissegundo).
  return d.toISOString().slice(0, 19).replace('T', ' ');
}

function mesesEntre(a, b) {
  return Math.max(1, (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth()));
}

/* ---------------------------------------------------------------------------------- cortina/lado-a-lado/lupa */

class MotorComparacao {
  constructor({ maplibregl, elArea, mapaPrincipal, catalogoPrincipal, aoErro }) {
    this.maplibregl = maplibregl;
    this.elArea = elArea; // #comparar-area
    this.elMapaA = elArea.querySelector('#comparar-mapa-a');
    this.elMapaB = elArea.querySelector('#comparar-mapa-b');
    this.elAlca = elArea.querySelector('#comparar-alca');
    this.elDivisor = elArea.querySelector('#comparar-divisor');
    this.mapaPrincipal = mapaPrincipal;
    this.catalogoPrincipal = catalogoPrincipal;
    this.aoErro = aoErro || (() => {});
    this.modo = 'desligado';
    this.mapaA = null;
    this.mapaB = null;
    this.pararSync = null;
    this.pos = 50; // % da cortina, 0-100
    this._onMoveLupa = null;
    this.diferencaMaximaCentro = 0; // medido a cada sincronismo — o que o e2e lê
    this.movimentosSincronizados = 0;
  }

  ativo() {
    return this.modo !== 'desligado';
  }

  async _mapaSecundario(container) {
    const map = new this.maplibregl.Map({
      container,
      style: construirEstilo({ tipo: 'raster' }),
      center: this.mapaPrincipal.getCenter(),
      zoom: this.mapaPrincipal.getZoom(),
      bearing: this.mapaPrincipal.getBearing(),
      pitch: this.mapaPrincipal.getPitch(),
      attributionControl: false,
    });
    await new Promise((resolve) => map.once('load', resolve));
    return map;
  }

  _sincronizar(origemRef, destinoRef) {
    // origemRef/destinoRef: {map} — objeto mutável porque em modo lupa o "destino" pode trocar de
    // mapa (o principal nunca troca, só o B). Guarda reentrância: jumpTo dispara 'move' de novo,
    // de forma síncrona — sem a trava, os dois mapas ficam alternando `move` para sempre.
    let ocupado = false;
    const copiar = (de, para) => {
      if (ocupado) return;
      ocupado = true;
      para.jumpTo({ center: de.getCenter(), zoom: de.getZoom(), bearing: de.getBearing(), pitch: de.getPitch() });
      ocupado = false;
      const ca = origemRef.map.getCenter();
      const cb = destinoRef.map.getCenter();
      this.diferencaMaximaCentro = Math.max(
        this.diferencaMaximaCentro,
        Math.abs(ca.lng - cb.lng), Math.abs(ca.lat - cb.lat),
      );
      this.movimentosSincronizados += 1;
    };
    const onA = () => copiar(origemRef.map, destinoRef.map);
    const onB = () => copiar(destinoRef.map, origemRef.map);
    origemRef.map.on('move', onA);
    destinoRef.map.on('move', onB);
    return () => { origemRef.map.off('move', onA); destinoRef.map.off('move', onB); };
  }

  async _carregarConjunto(map, ids) {
    const cat = new Catalogo(map);
    await cat.carregar();
    for (const id of ids) {
      try { await cat.ligar(id); } catch (e) { this.aoErro(e); }
    }
    return cat;
  }

  _aplicarVisual() {
    this.elArea.className = `comparar-area modo-${this.modo}`;
    if (this.modo === 'cortina-v') {
      this.elArea.style.setProperty('--comparar-clip', `inset(0 0 0 ${this.pos}%)`);
      this.elAlca.style.left = `${this.pos}%`;
      this.elAlca.style.top = '';
      this.elAlca.hidden = false;
    } else if (this.modo === 'cortina-h') {
      this.elArea.style.setProperty('--comparar-clip', `inset(${this.pos}% 0 0 0)`);
      this.elAlca.style.top = `${this.pos}%`;
      this.elAlca.style.left = '';
      this.elAlca.hidden = false;
    } else {
      this.elAlca.hidden = true;
    }
    this.elDivisor.hidden = this.modo !== 'lado-a-lado';
  }

  definirPosicaoCortina(pct) {
    this.pos = Math.max(2, Math.min(98, pct));
    this._aplicarVisual();
  }

  // Fila, não chamada direta: duas invocações de `ligar`/`desligar` que se sobrepõem (ex.: o rádio do
  // modo disparar `change` mais de uma vez antes da primeira terminar) intercalavam — a 2ª chamada dava
  // `desligar()` no meio do `await` da 1ª (apagando o mapa/listener que a 1ª estava montando), e a 1ª
  // terminava DEPOIS, sobrescrevendo o estado consistente da 2ª com o seu próprio, já obsoleto
  // (`_onMoveLupa` ficava `null` mesmo com `modo` correto — achado do e2e rodando sob contenção de CPU/
  // RAM, nunca reproduzido à mão em máquina ociosa). Serializar por fila elimina a classe inteira do bug
  // sem precisar provar qual caminho exato disparava duas chamadas.
  async ligar(modo, idsA, idsB) {
    this._fila = (this._fila || Promise.resolve()).then(() => this._ligarInterno(modo, idsA, idsB));
    return this._fila;
  }

  async _ligarInterno(modo, idsA, idsB) {
    await this._desligarInterno();
    this.modo = modo;
    this.diferencaMaximaCentro = 0;
    this.movimentosSincronizados = 0;
    if (modo === 'desligado') return;

    this.elArea.hidden = false;
    // _aplicarVisual() põe a classe `modo-<x>` no container ANTES de qualquer outra coisa — é dela
    // que depende `.modo-lupa { pointer-events: none }` (sig.css), sem a qual #comparar-area (cheio,
    // z-index acima de #mapa) intercepta todo pointermove destinado ao mapa principal por baixo e a
    // lupa nunca recebe a posição real do cursor (achado do e2e: ficava presa no canto 0,0).
    this._aplicarVisual();
    if (modo === 'lupa') {
      this.mapaPrincipal.getContainer().hidden = false;
      this.elMapaA.hidden = true;
      this.elMapaB.hidden = false;
      this.elMapaB.classList.add('comparar-lupa');
      this.mapaB = await this._mapaSecundario(this.elMapaB);
      await this._carregarConjunto(this.mapaB, idsB);
      this.pararSync = this._sincronizar({ map: this.mapaPrincipal }, { map: this.mapaB });
      this._ativarSeguirCursor();
    } else {
      this.mapaPrincipal.getContainer().hidden = true;
      this.elMapaA.hidden = false;
      this.elMapaB.hidden = false;
      this.elMapaB.classList.remove('comparar-lupa');
      this.mapaA = await this._mapaSecundario(this.elMapaA);
      this.mapaB = await this._mapaSecundario(this.elMapaB);
      await Promise.all([this._carregarConjunto(this.mapaA, idsA), this._carregarConjunto(this.mapaB, idsB)]);
      this.pararSync = this._sincronizar({ map: this.mapaA }, { map: this.mapaB });
      requestAnimationFrame(() => { this.mapaA.resize(); this.mapaB.resize(); });
    }
  }

  _ativarSeguirCursor() {
    const mover = (ev) => {
      const r = this.mapaPrincipal.getContainer().getBoundingClientRect();
      const x = ev.clientX - r.left;
      const y = ev.clientY - r.top;
      this.elMapaB.style.left = `${x - RAIO_LUPA}px`;
      this.elMapaB.style.top = `${y - RAIO_LUPA}px`;
    };
    this._onMoveLupa = mover;
    this.mapaPrincipal.getContainer().addEventListener('pointermove', mover);
    requestAnimationFrame(() => this.mapaB.resize());
  }

  // Chamável de fora (ex.: `aoErro`/limpeza) — passa pela MESMA fila que `ligar`, nunca concorrente com
  // ela. Por dentro de `_ligarInterno` usa-se `_desligarInterno` direto (já se está na fila).
  async desligar() {
    this._fila = (this._fila || Promise.resolve()).then(() => this._desligarInterno());
    return this._fila;
  }

  async _desligarInterno() {
    if (this.pararSync) { this.pararSync(); this.pararSync = null; }
    if (this._onMoveLupa) {
      this.mapaPrincipal.getContainer().removeEventListener('pointermove', this._onMoveLupa);
      this._onMoveLupa = null;
    }
    if (this.mapaA) { this.mapaA.remove(); this.mapaA = null; }
    if (this.mapaB) { this.mapaB.remove(); this.mapaB = null; }
    this.elMapaB.classList.remove('comparar-lupa');
    this.mapaPrincipal.getContainer().hidden = false;
    this.elArea.hidden = true;
    this.modo = 'desligado';
  }
}

/* ---------------------------------------------------------------------------------------------- tempo */

class MotorTempo {
  constructor({ map, catalogo, elCamada, elJanela, elPasso, elTocar, elRotuloPasso, elContagem, aoErro }) {
    this.map = map;
    this.catalogo = catalogo;
    this.elCamada = elCamada;
    this.elJanela = elJanela; // NodeList de radios
    this.elPasso = elPasso;
    this.elTocar = elTocar;
    this.elRotuloPasso = elRotuloPasso;
    this.elContagem = elContagem;
    this.aoErro = aoErro || (() => {});
    this.camadas = [];
    this.atual = null; // {item, campo, inicio(ms), fim(ms), passos}
    this.passoAtual = 0;
    this.tocando = false;
    this.ultimaMedidaMs = null;
    this.FONTE = 'plat-tempo';
    this.CAMADA_PONTO = 'plat-tempo-camada';

    this.elCamada.addEventListener('change', () => this._selecionar(this.elCamada.value));
    for (const r of this.elJanela) r.addEventListener('change', () => this._aoPasso(this.passoAtual));
    this.elPasso.addEventListener('input', () => this._aoPasso(Number(this.elPasso.value)));
    this.elTocar.addEventListener('click', () => (this.tocando ? this._parar() : this._reproduzir()));
  }

  async preencher() {
    this.camadas = camadasVetoriais(this.catalogo.disponiveis)
      .map((f) => ({ ficha: f, campo: campoTemporal(f) }))
      .filter((x) => x.campo);
    limpar(this.elCamada);
    if (!this.camadas.length) {
      this.elCamada.append(h('option', { value: '' }, t('comparar.tempo_sem_camada')));
      this.elCamada.disabled = true;
      return;
    }
    this.elCamada.disabled = false;
    for (const { ficha } of this.camadas) this.elCamada.append(h('option', { value: ficha.id }, ficha.titulo));
    await this._selecionar(this.camadas[0].ficha.id);
  }

  _janela() {
    return [...this.elJanela].find((r) => r.checked)?.value || 'instantanea';
  }

  async _minMax(item, campo) {
    const outStatistics = JSON.stringify([
      { statisticType: 'min', onStatisticField: campo, outStatisticFieldName: 'minv' },
      { statisticType: 'max', onStatisticField: campo, outStatisticFieldName: 'maxv' },
    ]);
    const url = `/rest/services/${item}/FeatureServer/0/query?f=json&outStatistics=${encodeURIComponent(outStatistics)}`;
    const r = await obter(url);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao calcular a faixa de tempo');
    const attrs = r.json.features && r.json.features[0] && r.json.features[0].attributes;
    if (!attrs || attrs.minv == null || attrs.maxv == null) throw new Error('camada sem valor de data');
    return [attrs.minv, attrs.maxv];
  }

  async _selecionar(itemId) {
    const entrada = this.camadas.find((x) => x.ficha.id === itemId);
    if (!entrada) return;
    try {
      const [minv, maxv] = await this._minMax(itemId, entrada.campo.nome);
      const passos = Math.max(4, Math.min(24, mesesEntre(new Date(minv), new Date(maxv))));
      this.atual = { item: itemId, campo: entrada.campo.nome, inicio: minv, fim: maxv, passos };
      this.elPasso.max = String(passos - 1);
      this.elPasso.value = '0';
      this.passoAtual = 0;
      await this._aoPasso(0);
    } catch (e) {
      this.aoErro(e);
    }
  }

  _limitesDoPasso(passo) {
    const { inicio, fim, passos } = this.atual;
    const duracao = (fim - inicio) / passos;
    const fimJanela = inicio + duracao * (passo + 1);
    const inicioJanela = this._janela() === 'acumulativa' ? inicio : inicio + duracao * passo;
    return [new Date(inicioJanela), new Date(fimJanela)];
  }

  _where(campo, ini, fim) {
    return `${campo} >= TIMESTAMP '${isoParaLiteralEsri(ini)}' AND ${campo} < TIMESTAMP '${isoParaLiteralEsri(fim)}'`;
  }

  async _aoPasso(passo) {
    if (!this.atual) return;
    const t0 = performance.now();
    this.passoAtual = passo;
    this.elPasso.value = String(passo);
    const [ini, fim] = this._limitesDoPasso(passo);
    const where = this._where(this.atual.campo, ini, fim);
    const base = `/rest/services/${this.atual.item}/FeatureServer/0/query`;
    const qsConta = `${base}?f=json&returnCountOnly=true&where=${encodeURIComponent(where)}`;
    const qsGeo = `${base}?f=geojson&returnGeometry=true&outFields=*&resultRecordCount=5000&where=${encodeURIComponent(where)}`;
    const [conta, geo] = await Promise.all([obter(qsConta), obter(qsGeo)]);
    if (conta.status !== 200 || geo.status !== 200) {
      this.aoErro(new Error('falha ao consultar a janela de tempo'));
      return;
    }
    this._desenhar(geo.json);
    const n = conta.json.count ?? 0;
    this.elContagem.textContent = t('comparar.tempo_contagem', { n: n.toLocaleString('pt-BR'), truncado: geo.json.features.length < n ? ' (mapa mostra até 5.000)' : '' });
    this.elRotuloPasso.textContent = `${ini.toISOString().slice(0, 10)} → ${fim.toISOString().slice(0, 10)}`;
    this.ultimaMedidaMs = Math.round(performance.now() - t0);
    return { count: n, ms: this.ultimaMedidaMs, inicio: ini.toISOString(), fim: fim.toISOString() };
  }

  _desenhar(geojson) {
    if (this.map.getSource(this.FONTE)) {
      this.map.getSource(this.FONTE).setData(geojson);
      return;
    }
    this.map.addSource(this.FONTE, { type: 'geojson', data: geojson });
    this.map.addLayer({
      id: this.CAMADA_PONTO, source: this.FONTE, type: 'circle',
      paint: { 'circle-radius': 4, 'circle-color': '#d98a2b', 'circle-stroke-color': '#1a1002', 'circle-stroke-width': .5, 'circle-opacity': .85 },
    });
  }

  _parar() {
    this.tocando = false;
    this.elTocar.textContent = t('comparar.tempo_reproduzir');
  }

  async _reproduzir() {
    this.tocando = true;
    this.elTocar.textContent = t('comparar.tempo_pausar');
    const intervaloMs = 500; // 2 passos/s — cada passo espera a própria consulta responder antes de avançar
    while (this.tocando && this.atual) {
      const t0 = performance.now();
      const proximo = (this.passoAtual + 1) % this.atual.passos;
      await this._aoPasso(proximo); // esperado até o fim: nunca agenda o próximo passo com pedido pendente
      const decorrido = performance.now() - t0;
      if (!this.tocando) break;
      await new Promise((resolve) => setTimeout(resolve, Math.max(0, intervaloMs - decorrido)));
    }
  }

  limpar() {
    if (this.map.getLayer(this.CAMADA_PONTO)) this.map.removeLayer(this.CAMADA_PONTO);
    if (this.map.getSource(this.FONTE)) this.map.removeSource(this.FONTE);
  }
}

/* ------------------------------------------------------------------------------------------- instalação */

function itemLista(ficha, marcada, aoMudar) {
  const caixa = h('input', { type: 'checkbox', checked: marcada, onchange: () => aoMudar(ficha.id, caixa.checked) });
  return h('li', { class: 'camada-linha' }, h('label', { class: 'camada-cabecalho' }, caixa, h('span', { class: 'camada-titulo' }, ficha.titulo)));
}

function lerListaUrl(param) {
  const v = new URLSearchParams(location.search).get(param);
  return v ? v.split(',').filter(Boolean) : [];
}

function gravarEstadoUrl(modo, idsA, idsB) {
  const p = new URLSearchParams(location.search);
  if (modo === 'desligado') { p.delete('cmp'); p.delete('cmpa'); p.delete('cmpb'); } else {
    p.set('cmp', modo); p.set('cmpa', idsA.join(',')); p.set('cmpb', idsB.join(','));
  }
  const q = p.toString();
  history.replaceState(null, '', location.pathname + (q ? `?${q}` : ''));
}

export async function instalarComparar({ map, catalogo, maplibregl, el, aoErro }) {
  const elArea = el('comparar-area');
  const motor = new MotorComparacao({ maplibregl, elArea, mapaPrincipal: map, catalogoPrincipal: catalogo, aoErro });

  const listaA = el('comparar-lista-a');
  const listaB = el('comparar-lista-b');
  const idsA = new Set(lerListaUrl('cmpa'));
  const idsB = new Set(lerListaUrl('cmpb'));

  function redesenharListas() {
    limpar(listaA); limpar(listaB);
    for (const f of catalogo.disponiveis) {
      listaA.append(itemLista(f, idsA.has(f.id), (id, v) => { v ? idsA.add(id) : idsA.delete(id); }));
      listaB.append(itemLista(f, idsB.has(f.id), (id, v) => { v ? idsB.add(id) : idsB.delete(id); }));
    }
  }
  redesenharListas();
  catalogo.aoMudar(redesenharListas);

  const elSincronismo = el('comparar-sincronismo');
  let cronometro = null;
  async function aplicar(modo) {
    motor.aoErro = (e) => el('aviso').erro(`comparar: ${(e && e.message) || e}`);
    await motor.ligar(modo, [...idsA], [...idsB]);
    gravarEstadoUrl(modo, [...idsA], [...idsB]);
    if (cronometro) clearInterval(cronometro);
    if (motor.ativo()) {
      cronometro = setInterval(() => {
        elSincronismo.textContent = t('comparar.sincronismo', {
          n: motor.movimentosSincronizados, dif: motor.diferencaMaximaCentro.toExponential(2),
        });
      }, 400);
    } else {
      elSincronismo.textContent = '';
    }
  }

  for (const r of document.querySelectorAll('input[name="comparar-modo"]')) {
    r.addEventListener('change', () => { if (r.checked) aplicar(r.value); });
  }
  el('comparar-aplicar').addEventListener('click', () => {
    const modo = document.querySelector('input[name="comparar-modo"]:checked')?.value || 'desligado';
    aplicar(modo);
  });

  let arrastando = null;
  el('comparar-alca').addEventListener('pointerdown', (ev) => {
    arrastando = motor.modo;
    ev.target.setPointerCapture(ev.pointerId);
  });
  el('comparar-alca').addEventListener('pointermove', (ev) => {
    if (!arrastando) return;
    const r = elArea.getBoundingClientRect();
    const pct = arrastando === 'cortina-h'
      ? ((ev.clientY - r.top) / r.height) * 100
      : ((ev.clientX - r.left) / r.width) * 100;
    motor.definirPosicaoCortina(pct);
  });
  el('comparar-alca').addEventListener('pointerup', () => { arrastando = null; });

  const modoUrl = new URLSearchParams(location.search).get('cmp');
  if (modoUrl && MODOS.includes(modoUrl)) {
    const radio = document.querySelector(`input[name="comparar-modo"][value="${modoUrl}"]`);
    if (radio) { radio.checked = true; await aplicar(modoUrl); }
  }

  const tempo = new MotorTempo({
    map, catalogo,
    elCamada: el('tempo-camada'), elJanela: document.querySelectorAll('input[name="tempo-janela"]'),
    elPasso: el('tempo-passo'), elTocar: el('tempo-tocar'), elRotuloPasso: el('tempo-rotulo-passo'),
    elContagem: el('tempo-contagem'),
    aoErro: (e) => el('aviso').erro(`tempo: ${(e && e.message) || e}`),
  });
  await tempo.preencher();
  catalogo.aoMudar(() => tempo.preencher());

  return { motor, tempo };
}
