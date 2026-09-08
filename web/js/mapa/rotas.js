/* plat · mapa — painel "Rotas" (item UX-08; fecha UX-19): as três rotas de rede que o backend já tinha e nenhuma
   tela chamava — POST /api/rota (caminho entre dois pontos), POST /api/isocrona (área alcançável em N minutos) e
   POST /api/matriz (durações origens × destinos). Tudo sobre o OSRM do recorte (dado aberto, OSM); a resposta
   traz a proveniência e a tela a mostra.
   Pontos entram de dois jeitos, sempre os dois: clicando no mapa (botão "marcar" liga a captura do próximo
   clique) ou digitando "lon, lat" no campo. Resultado vai para o mapa (linha, polígono, marcadores) e para o
   painel (distância, duração, instruções, tabela da matriz). Estados por <plat-estado>: vazio (o que fazer),
   carregando, erro nomeado (422 isocrona_vazia, 422 matriz_grande_demais, OSRM fora do ar) com tentar de novo. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { enviar, mensagemDe } from '../base/api.js';

const FONTE_ROTA = 'plat-rotas-rota';
const FONTE_ISO = 'plat-rotas-isocrona';
/* cores do sistema de design lidas dos tokens (nunca literal solto na tela; o mapa não lê CSS, por isso a leitura) */
const cor = (nome, reserva) => (getComputedStyle(document.documentElement).getPropertyValue(nome) || '').trim() || reserva;
const COR_ROTA = cor('--acento', '#d98a2b');
const COR_ISO = cor('--ok', '#4f9e6e');
const COR_DESTINO = cor('--falha', '#b42318');

function lerPonto(texto) {
  const m = String(texto || '').trim().match(/^\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*$/);
  if (!m) return null;
  const lon = Number(m[1].replace(',', '.')); const lat = Number(m[2].replace(',', '.'));
  if (!(lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90)) return null;
  return [lon, lat];
}
const textoPonto = (p) => (p ? `${p[0].toFixed(5)}, ${p[1].toFixed(5)}` : '');
const km = (m) => `${(m / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} km`;
const minutos = (s) => `${Math.round(s / 60)} min`;

export class PainelRotas {
  constructor(map, maplibregl, raiz) {
    this.map = map; this.gl = maplibregl; this.raiz = raiz;
    this.marcadores = [];
    this.captura = null; // função que recebe o próximo clique no mapa
    this.modo = 'rota';
    this.pontos = { origem: null, destino: null, ponto: null, origens: [], destinos: [] };
    this.ultimaProveniencia = null;
    this._montar();
    map.on('click', (ev) => {
      if (!this.captura) return;
      const p = [ev.lngLat.lng, ev.lngLat.lat];
      const fn = this.captura; this.captura = null;
      map.getCanvas().style.cursor = '';
      fn(p);
    });
  }

  /* ---------------------------------------------------------------- montagem */
  _montar() {
    const r = this.raiz;
    limpar(r);
    this.estado = h('plat-estado', { id: 'rotas-estado' });
    this.estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.executar(); });
    const modos = h('div', { class: 'rotas-modos', role: 'radiogroup', 'aria-label': t('rotas.modo') });
    for (const m of ['rota', 'isocrona', 'matriz']) {
      const bt = h('button', { type: 'button', class: 'pequeno', role: 'radio', 'aria-checked': String(m === this.modo), dataset: { modo: m } }, t(`rotas.modo_${m}`));
      bt.addEventListener('click', () => this.definirModo(m));
      modos.append(bt);
    }
    this.blocoRota = this._blocoRota();
    this.blocoIso = this._blocoIsocrona();
    this.blocoMatriz = this._blocoMatriz();
    const btLimpar = h('button', { type: 'button', class: 'pequeno', id: 'rotas-limpar' }, t('rotas.limpar'));
    btLimpar.addEventListener('click', () => this.limpar());
    this.saida = h('div', { class: 'rotas-saida', id: 'rotas-saida', 'aria-live': 'polite' });
    r.append(modos, this.blocoRota, this.blocoIso, this.blocoMatriz, h('div', { class: 'botoes' }, btLimpar), this.estado, this.saida);
    this.definirModo('rota');
    this.estado.vazio(t('rotas.vazio'));
  }

  _campoPonto(chave, rotulo) {
    const id = `rotas-${chave}`;
    const entrada = h('input', { type: 'text', id, class: 'controle', autocomplete: 'off', spellcheck: 'false' });
    entrada.addEventListener('change', () => {
      const p = lerPonto(entrada.value);
      if (!p && entrada.value.trim()) { entrada.setAttribute('aria-invalid', 'true'); this.estado.erro(t('rotas.ponto_invalido'), []); return; }
      entrada.removeAttribute('aria-invalid');
      this.pontos[chave] = p;
      this._marcadores();
    });
    const btMarcar = h('button', { type: 'button', class: 'pequeno', dataset: { marcar: chave }, 'aria-pressed': 'false' }, t('rotas.marcar_no_mapa'));
    btMarcar.addEventListener('click', () => {
      this.raiz.querySelectorAll('[data-marcar]').forEach((b) => b.setAttribute('aria-pressed', 'false'));
      btMarcar.setAttribute('aria-pressed', 'true');
      this.map.getCanvas().style.cursor = 'crosshair';
      this.estado.mostrar({ tipo: 'vazio', titulo: t('rotas.clique_no_mapa'), texto: t('rotas.clique_no_mapa_texto', { ponto: rotulo }) });
      this.captura = (p) => {
        btMarcar.setAttribute('aria-pressed', 'false');
        this.pontos[chave] = p; entrada.value = textoPonto(p); entrada.removeAttribute('aria-invalid');
        this._marcadores(); this.estado.limpar();
      };
    });
    return h('div', { class: 'campo' }, h('label', { for: id }, rotulo), h('span', { class: 'ajuda' }, t('rotas.exemplo_ponto')), h('div', { class: 'linha' }, entrada, btMarcar));
  }

  _blocoRota() {
    const bt = h('button', { type: 'button', class: 'primario', id: 'rotas-calcular-rota' }, t('rotas.calcular'));
    bt.addEventListener('click', () => this.executar());
    return h('div', { class: 'rotas-bloco', dataset: { bloco: 'rota' } },
      this._campoPonto('origem', t('rotas.origem')), this._campoPonto('destino', t('rotas.destino')),
      h('div', { class: 'botoes' }, bt));
  }

  _blocoIsocrona() {
    this.minutos = h('input', { type: 'number', id: 'rotas-minutos', class: 'controle', min: '1', max: '120', step: '1', value: '10' });
    const bt = h('button', { type: 'button', class: 'primario', id: 'rotas-calcular-isocrona' }, t('rotas.calcular'));
    bt.addEventListener('click', () => this.executar());
    return h('div', { class: 'rotas-bloco', dataset: { bloco: 'isocrona' }, hidden: true },
      this._campoPonto('ponto', t('rotas.ponto')),
      h('div', { class: 'campo' }, h('label', { for: 'rotas-minutos' }, t('rotas.minutos')), this.minutos),
      h('div', { class: 'botoes' }, bt));
  }

  _blocoMatriz() {
    const lista = (chave, rotulo) => {
      const ul = h('ul', { class: 'rotas-lista', dataset: { lista: chave }, 'aria-label': rotulo });
      const entrada = h('input', { type: 'text', class: 'controle', 'aria-label': t('rotas.acrescentar_ponto', { lista: rotulo }), autocomplete: 'off', spellcheck: 'false' });
      const btAdd = h('button', { type: 'button', class: 'pequeno', dataset: { acrescentar: chave } }, t('rotas.acrescentar'));
      btAdd.addEventListener('click', () => {
        const p = lerPonto(entrada.value);
        if (!p) { entrada.setAttribute('aria-invalid', 'true'); this.estado.erro(t('rotas.ponto_invalido'), []); return; }
        entrada.removeAttribute('aria-invalid'); entrada.value = '';
        this.pontos[chave].push(p); this._listas(); this._marcadores();
      });
      const btMarcar = h('button', { type: 'button', class: 'pequeno', dataset: { marcarLista: chave }, 'aria-pressed': 'false' }, t('rotas.marcar_no_mapa'));
      btMarcar.addEventListener('click', () => {
        btMarcar.setAttribute('aria-pressed', 'true');
        this.map.getCanvas().style.cursor = 'crosshair';
        this.captura = (p) => { btMarcar.setAttribute('aria-pressed', 'false'); this.pontos[chave].push(p); this._listas(); this._marcadores(); };
      });
      return h('fieldset', { class: 'rotas-conjunto' }, h('legend', {}, rotulo), ul, h('div', { class: 'linha' }, entrada, btAdd, btMarcar));
    };
    const bt = h('button', { type: 'button', class: 'primario', id: 'rotas-calcular-matriz' }, t('rotas.calcular'));
    bt.addEventListener('click', () => this.executar());
    return h('div', { class: 'rotas-bloco', dataset: { bloco: 'matriz' }, hidden: true },
      lista('origens', t('rotas.origens')), lista('destinos', t('rotas.destinos')), h('div', { class: 'botoes' }, bt));
  }

  _listas() {
    for (const chave of ['origens', 'destinos']) {
      const ul = this.raiz.querySelector(`[data-lista="${chave}"]`);
      limpar(ul);
      this.pontos[chave].forEach((p, i) => {
        const bt = h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('rotas.remover_ponto', { n: i + 1 }) }, '×');
        bt.addEventListener('click', () => { this.pontos[chave].splice(i, 1); this._listas(); this._marcadores(); });
        ul.append(h('li', {}, h('span', { class: 'mono' }, `${chave === 'origens' ? 'O' : 'D'}${i + 1} ${textoPonto(p)}`), bt));
      });
      if (!this.pontos[chave].length) ul.append(h('li', { class: 'fraco' }, t('rotas.lista_vazia')));
    }
  }

  definirModo(modo) {
    this.modo = modo;
    this.raiz.querySelectorAll('[data-modo]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.modo === modo)));
    for (const b of this.raiz.querySelectorAll('[data-bloco]')) b.hidden = b.dataset.bloco !== modo;
    if (modo === 'matriz') this._listas();
    this._marcadores();
  }

  /* ---------------------------------------------------------------- mapa */
  _marcadores() {
    for (const m of this.marcadores) m.remove();
    this.marcadores = [];
    const por = (p, cor, rotulo) => {
      if (!p) return;
      const m = new this.gl.Marker({ color: cor }).setLngLat(p);
      if (rotulo) m.setPopup(new this.gl.Popup({ closeButton: true }).setText(rotulo));
      m.addTo(this.map); this.marcadores.push(m);
      // o MapLibre põe aria-label num <div> sem papel (axe: aria-prohibited-attr); marcador é imagem com nome
      const el = m.getElement();
      el.setAttribute('role', 'img');
      el.setAttribute('aria-label', rotulo ? t('rotas.marcador', { rotulo }) : t('rotas.marcador_sem_nome'));
    };
    if (this.modo === 'rota') { por(this.pontos.origem, COR_ROTA, t('rotas.origem')); por(this.pontos.destino, COR_DESTINO, t('rotas.destino')); }
    if (this.modo === 'isocrona') por(this.pontos.ponto, COR_ISO, t('rotas.ponto'));
    if (this.modo === 'matriz') {
      this.pontos.origens.forEach((p, i) => por(p, COR_ROTA, `O${i + 1}`));
      this.pontos.destinos.forEach((p, i) => por(p, COR_DESTINO, `D${i + 1}`));
    }
  }

  _fonte(id, geojson) {
    const src = this.map.getSource(id);
    if (src) { src.setData(geojson); return; }
    this.map.addSource(id, { type: 'geojson', data: geojson });
    if (id === FONTE_ROTA) {
      this.map.addLayer({ id: `${id}-linha`, type: 'line', source: id, paint: { 'line-color': COR_ROTA, 'line-width': 5, 'line-opacity': 0.9 } });
    } else {
      this.map.addLayer({ id: `${id}-area`, type: 'fill', source: id, paint: { 'fill-color': COR_ISO, 'fill-opacity': 0.25 } });
      this.map.addLayer({ id: `${id}-borda`, type: 'line', source: id, paint: { 'line-color': COR_ISO, 'line-width': 2 } });
    }
  }

  _enquadrar(geometria) {
    const coords = [];
    const junta = (c) => { if (typeof c[0] === 'number') coords.push(c); else c.forEach(junta); };
    junta(geometria.coordinates);
    if (!coords.length) return;
    const lons = coords.map((c) => c[0]); const lats = coords.map((c) => c[1]);
    this.map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40, maxZoom: 15 });
  }

  limpar() {
    for (const id of [FONTE_ROTA, FONTE_ISO]) {
      for (const suf of ['-linha', '-area', '-borda']) if (this.map.getLayer(id + suf)) this.map.removeLayer(id + suf);
      if (this.map.getSource(id)) this.map.removeSource(id);
    }
    this.pontos = { origem: null, destino: null, ponto: null, origens: [], destinos: [] };
    this.raiz.querySelectorAll('input[type=text]').forEach((i) => { i.value = ''; i.removeAttribute('aria-invalid'); });
    this._marcadores(); this._listas();
    limpar(this.saida);
    this.estado.vazio(t('rotas.vazio'));
  }

  /* ---------------------------------------------------------------- execução */
  async executar() {
    limpar(this.saida);
    const p = this.pontos;
    let url; let corpo;
    if (this.modo === 'rota') {
      if (!p.origem || !p.destino) { this.estado.erro(t('rotas.falta_origem_destino'), []); return; }
      url = '/api/rota'; corpo = { origem: p.origem, destino: p.destino, perfil: 'carro' };
    } else if (this.modo === 'isocrona') {
      const min = Number(this.minutos.value);
      if (!p.ponto) { this.estado.erro(t('rotas.falta_ponto'), []); return; }
      if (!(min > 0)) { this.estado.erro(t('rotas.minutos_invalidos'), []); return; }
      url = '/api/isocrona'; corpo = { ponto: p.ponto, minutos: min, perfil: 'carro' };
    } else {
      if (!p.origens.length || !p.destinos.length) { this.estado.erro(t('rotas.falta_matriz'), []); return; }
      url = '/api/matriz'; corpo = { origens: p.origens, destinos: p.destinos, perfil: 'carro' };
    }
    this.estado.carregando(t('rotas.calculando'));
    this.raiz.querySelectorAll('button.primario').forEach((b) => { b.disabled = true; });
    const r = await enviar(url, corpo);
    this.raiz.querySelectorAll('button.primario').forEach((b) => { b.disabled = false; });
    if (r.status !== 200) {
      const j = r.json || {};
      let texto = mensagemDe(r);
      if (j.erro === 'isocrona_vazia') texto = t('rotas.erro_isocrona_vazia', { minutos: corpo.minutos });
      else if (j.erro === 'matriz_grande_demais') texto = t('rotas.erro_matriz_grande', { n: j.detalhe?.origens, m: j.detalhe?.destinos, teto: j.detalhe?.teto });
      else if (r.status === 502 || r.status === 503 || r.status === 504) texto = t('rotas.erro_osrm', { erro: mensagemDe(r) });
      this.estado.mostrar({ tipo: r.status === 403 ? 'negado' : 'erro', texto, acoes: r.status === 403 ? [] : [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }], ref: j.req_id });
      return;
    }
    this.estado.limpar();
    this.ultimaProveniencia = r.json.proveniencia || null;
    if (this.modo === 'rota') this._mostrarRota(r.json);
    else if (this.modo === 'isocrona') this._mostrarIsocrona(r.json);
    else this._mostrarMatriz(r.json);
  }

  _mostrarRota(j) {
    const geo = { type: 'Feature', geometry: j.geometria, properties: {} };
    this._fonte(FONTE_ROTA, geo);
    this._enquadrar(j.geometria);
    const passos = Array.isArray(j.instrucoes) ? j.instrucoes : [];
    this.saida.append(
      h('p', { class: 'rotas-resumo' }, h('strong', {}, km(j.distancia_m)), ' · ', h('strong', {}, minutos(j.duracao_s)), ` · ${t('rotas.perfil_carro')}`),
      passos.length ? h('ol', { class: 'rotas-instrucoes' }, ...passos.slice(0, 40).map((s) => h('li', {}, typeof s === 'string' ? s : (s.texto || s.instrucao || JSON.stringify(s))))) : null,
      this._proveniencia(j.proveniencia),
    );
  }

  _mostrarIsocrona(j) {
    const geo = { type: 'Feature', geometry: j.poligono, properties: {} };
    this._fonte(FONTE_ISO, geo);
    this._enquadrar(j.poligono);
    const g = j.grade || {};
    this.saida.append(
      h('p', { class: 'rotas-resumo' }, t('rotas.isocrona_resumo', { minutos: j.minutos })),
      h('p', { class: 'ajuda' }, `${j.metodo || ''}${g.alcancados !== undefined ? ` · ${t('rotas.isocrona_grade', { alcancados: g.alcancados, total: g.total ?? g.pontos ?? '' })}` : ''}`),
      this._proveniencia(j.proveniencia),
    );
  }

  _mostrarMatriz(j) {
    const dur = j.duracoes_s || []; const dist = j.distancias_m || [];
    const cab = h('tr', {}, h('th', { scope: 'col' }, ''), ...this.pontos.destinos.map((_, i) => h('th', { scope: 'col' }, `D${i + 1}`)));
    const corpo = this.pontos.origens.map((_, i) => h('tr', {}, h('th', { scope: 'row' }, `O${i + 1}`), ...this.pontos.destinos.map((__, k) => {
      const d = dur[i]?.[k]; const m = dist[i]?.[k];
      return h('td', { class: 'num' }, d === null || d === undefined ? '—' : `${minutos(d)}${m !== null && m !== undefined ? ` · ${km(m)}` : ''}`);
    })));
    this.saida.append(
      h('p', { class: 'rotas-resumo' }, t('rotas.matriz_resumo', { n: j.origens, m: j.destinos })),
      h('div', { class: 'tabela-rolagem' }, h('table', { class: 'tabela', 'aria-label': t('rotas.modo_matriz') }, h('thead', {}, cab), h('tbody', {}, ...corpo))),
      this._proveniencia(j.proveniencia),
    );
  }

  _proveniencia(p) {
    if (!p || typeof p !== 'object') return null;
    const partes = [p.fonte, p.licenca, p.recorte, p.data || p.data_acesso].filter(Boolean);
    return partes.length ? h('p', { class: 'ajuda rotas-proveniencia' }, `${t('rotas.proveniencia')}: ${partes.join(' · ')}`) : null;
  }
}
