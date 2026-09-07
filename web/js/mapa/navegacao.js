/* plat · mapa — navegação (item L2-01-f-navegacao-medicao-coordenadas): favoritos de extensão, histórico
   voltar/avançar, mostrador de coordenada do cursor em CRS escolhido, tela cheia, minha localização e atalhos
   de teclado. Tudo aqui é pequeno e sem framework; a barra de escala e o controle de zoom/rotação/norte são os
   nativos do MapLibre (a barra usa a distância geodésica na latitude do centro da tela — é isso que o teste
   confere contra a medição).

   Favoritos: {nome, centro, zoom, rotacao, inclinacao} por mapa, em localStorage (mesma decisão da ordem das
   camadas em camadas.js). Gravar no documento do item de mapa (L2-01-a) espera o esquema mapa-v1 ganhar o
   campo `favoritos` — o ramo daquele item ainda está na fila; declarado em PARIDADE.md. */
import { h, limpar } from '../base/dom.js';
import { CRS, formatarCoordenada } from './crs.js';
import { escalaNumerica } from './impressao.js';

const CHAVE_CRS = 'plat.mapa.crs';

/* ------------------------------------------------------------------ coordenada do cursor em CRS escolhido */
export function montarCoordenadas(map, caixa, seletor) {
  let srid = 4326;
  try { srid = Number(localStorage.getItem(CHAVE_CRS)) || 4326; } catch { /* sem armazenamento */ }
  limpar(seletor);
  for (const c of CRS) seletor.append(h('option', { value: String(c.srid) }, `${c.nome} (${c.srid})`));
  seletor.value = String(srid);
  let ultimo = null;
  const escrever = (lng, lat, zoom) => {
    ultimo = [lng, lat, zoom];
    let texto;
    try { texto = formatarCoordenada(lng, lat, srid); } catch (e) { texto = `${lat.toFixed(5)}, ${lng.toFixed(5)} (${e.message})`; }
    caixa.textContent = `${texto} · z${zoom.toFixed(1)} · 1:${escalaNumerica(lat, zoom).toLocaleString('pt-BR')}`;
    caixa.dataset.srid = String(srid);
    caixa.dataset.lon = String(lng);
    caixa.dataset.lat = String(lat);
  };
  const centro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  seletor.addEventListener('change', () => {
    srid = Number(seletor.value);
    try { localStorage.setItem(CHAVE_CRS, String(srid)); } catch { /* sem armazenamento */ }
    if (ultimo) escrever(...ultimo); else centro();
  });
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', centro);
  map.on('zoomend', centro);
  map.on('moveend', centro);
  centro();
  return { srid: () => srid, escrever };
}

/* ------------------------------------------------------------------ histórico de extensão (voltar/avançar) */
export class Historico {
  constructor(map, { botaoVoltar, botaoAvancar, maximo = 50 } = {}) {
    this.map = map;
    this.pilha = [];
    this.indice = -1;
    this.maximo = maximo;
    this.aplicando = false;
    this.botaoVoltar = botaoVoltar;
    this.botaoAvancar = botaoAvancar;
    map.on('moveend', () => this._registrar());
    if (botaoVoltar) botaoVoltar.addEventListener('click', () => this.voltar());
    if (botaoAvancar) botaoAvancar.addEventListener('click', () => this.avancar());
    this._registrar();
  }

  _estado() {
    const c = this.map.getCenter();
    return { centro: [c.lng, c.lat], zoom: this.map.getZoom(), rotacao: this.map.getBearing(), inclinacao: this.map.getPitch() };
  }

  _igual(a, b) {
    return a && b && Math.abs(a.centro[0] - b.centro[0]) < 1e-9 && Math.abs(a.centro[1] - b.centro[1]) < 1e-9
      && Math.abs(a.zoom - b.zoom) < 1e-6 && Math.abs(a.rotacao - b.rotacao) < 1e-6 && Math.abs(a.inclinacao - b.inclinacao) < 1e-6;
  }

  _registrar() {
    if (this.aplicando) return;
    const e = this._estado();
    if (this._igual(this.pilha[this.indice], e)) return;
    this.pilha = this.pilha.slice(0, this.indice + 1);
    this.pilha.push(e);
    if (this.pilha.length > this.maximo) this.pilha.shift();
    this.indice = this.pilha.length - 1;
    this._botoes();
  }

  _aplicar(e) {
    this.aplicando = true;
    this.map.jumpTo({ center: e.centro, zoom: e.zoom, bearing: e.rotacao, pitch: e.inclinacao });
    // o jumpTo dispara moveend de forma síncrona no MapLibre; a flag fica até o próximo ciclo por segurança
    setTimeout(() => { this.aplicando = false; }, 0);
    this._botoes();
  }

  voltar() { if (this.indice > 0) { this.indice -= 1; this._aplicar(this.pilha[this.indice]); return true; } return false; }
  avancar() { if (this.indice < this.pilha.length - 1) { this.indice += 1; this._aplicar(this.pilha[this.indice]); return true; } return false; }

  _botoes() {
    if (this.botaoVoltar) this.botaoVoltar.disabled = this.indice <= 0;
    if (this.botaoAvancar) this.botaoAvancar.disabled = this.indice >= this.pilha.length - 1;
  }
}

/* ------------------------------------------------------------------ favoritos (nome + extensão + rotação) */
export class Favoritos {
  constructor(map, { chave, lista, campoNome, botaoSalvar }) {
    this.map = map;
    this.chave = chave;
    this.lista = lista;
    this.campoNome = campoNome;
    this.itens = this._ler();
    if (botaoSalvar) botaoSalvar.addEventListener('click', () => this.salvar(campoNome ? campoNome.value.trim() : ''));
    this.desenhar();
  }

  _ler() {
    try { const b = localStorage.getItem(this.chave); return b ? JSON.parse(b) : []; } catch { return []; }
  }

  _gravar() {
    try { localStorage.setItem(this.chave, JSON.stringify(this.itens)); return true; } catch { return false; }
  }

  salvar(nome) {
    const c = this.map.getCenter();
    const f = { nome: (nome || `favorito ${this.itens.length + 1}`).slice(0, 80), centro: [c.lng, c.lat],
                zoom: this.map.getZoom(), rotacao: this.map.getBearing(), inclinacao: this.map.getPitch() };
    this.itens = this.itens.filter((x) => x.nome !== f.nome);
    this.itens.push(f);
    this._gravar();
    if (this.campoNome) this.campoNome.value = '';
    this.desenhar();
    return f;
  }

  ir(nome) {
    const f = this.itens.find((x) => x.nome === nome);
    if (!f) return false;
    this.map.jumpTo({ center: f.centro, zoom: f.zoom, bearing: f.rotacao, pitch: f.inclinacao || 0 });
    return true;
  }

  remover(nome) {
    this.itens = this.itens.filter((x) => x.nome !== nome);
    this._gravar();
    this.desenhar();
  }

  desenhar() {
    if (!this.lista) return;
    limpar(this.lista);
    for (const f of this.itens) {
      this.lista.append(h('li', { dataset: { favorito: f.nome } },
        h('button', { type: 'button', class: 'sugestao', dataset: { irFavorito: f.nome }, onclick: () => this.ir(f.nome) }, f.nome),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': `remover ${f.nome}`, onclick: () => this.remover(f.nome) }, '✕')));
    }
  }
}

/* ------------------------------------------------------------------ minha localização: controle nativo do
   MapLibre (Geolocation API), com o círculo de precisão ligado; não segue o usuário (um clique = uma posição) */
export function montarLocalizacao(map, maplibregl) {
  const controle = new maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: true, timeout: 10000 },
    trackUserLocation: false, showAccuracyCircle: true, showUserLocation: true,
  });
  map.addControl(controle, 'top-right');
  return controle;
}

export function montarTelaCheia(map, maplibregl, container) {
  const controle = new maplibregl.FullscreenControl({ container });
  map.addControl(controle, 'top-right');
  return controle;
}

/* ------------------------------------------------------------------ atalhos de teclado (documentados no painel) */
export const ATALHOS = [
  ['+ / -', 'aproximar / afastar'], ['setas', 'deslocar o mapa'], ['Shift+setas', 'deslocar mais'],
  ['N', 'norte para cima'], ['F', 'tela cheia'], ['L', 'minha localização'], ['D', 'medir distância'],
  ['A', 'medir área'], ['Backspace', 'desfaz o último vértice da medição'], ['Esc', 'limpa a medição'],
  ['Alt+←', 'extensão anterior'], ['Alt+→', 'extensão seguinte'], ['B', 'salvar favorito'], ['G', 'ir para coordenada'],
  ['C', 'copiar coordenada do centro'], ['?', 'mostra esta lista'],
];

export function instalarAtalhos(map, acoes) {
  const emCampo = (ev) => ['INPUT', 'TEXTAREA', 'SELECT'].includes((ev.target && ev.target.tagName) || '') || (ev.target && ev.target.isContentEditable);
  document.addEventListener('keydown', (ev) => {
    if (emCampo(ev)) { if (ev.key === 'Escape') ev.target.blur(); return; }
    if (ev.ctrlKey || ev.metaKey) return;
    const k = ev.key;
    if (ev.altKey && k === 'ArrowLeft') { ev.preventDefault(); acoes.voltar?.(); return; }
    if (ev.altKey && k === 'ArrowRight') { ev.preventDefault(); acoes.avancar?.(); return; }
    if (ev.altKey) return;
    const tabela = {
      '+': () => map.zoomIn(), '=': () => map.zoomIn(), '-': () => map.zoomOut(),
      n: () => map.resetNorth(), N: () => map.resetNorth(),
      f: () => acoes.telaCheia?.(), F: () => acoes.telaCheia?.(),
      l: () => acoes.localizacao?.(), L: () => acoes.localizacao?.(),
      d: () => acoes.distancia?.(), D: () => acoes.distancia?.(),
      a: () => acoes.area?.(), A: () => acoes.area?.(),
      b: () => acoes.favorito?.(), B: () => acoes.favorito?.(),
      g: () => acoes.irPara?.(), G: () => acoes.irPara?.(),
      c: () => acoes.copiarCoordenada?.(), C: () => acoes.copiarCoordenada?.(),
      '?': () => acoes.ajuda?.(),
      Backspace: () => acoes.voltarVertice?.(), Escape: () => acoes.limpar?.(),
    };
    const f = tabela[k];
    if (f) { ev.preventDefault(); f(); }
  });
}

export function listaDeAtalhos() {
  return h('dl', { class: 'atalhos' }, ...ATALHOS.flatMap(([tecla, o]) => [h('dt', {}, h('kbd', {}, tecla)), h('dd', {}, o)]));
}
