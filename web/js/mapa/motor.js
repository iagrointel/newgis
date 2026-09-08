/* plat · mapa — painel "Motor" (item UX-08; tela do motor multicritério de grades aninhadas L3-19; fecha UX-21).
   Quatro passos, na ordem em que aparecem no painel:
     1. ÁREA DE ESTUDO — escolher uma existente (GET /api/multiescala/conjuntos) ou criar a partir da VISTA ATUAL
        do mapa (POST /api/multiescala/conjuntos com o polígono dos limites); a área desenha no mapa e apaga com
        confirmação (DELETE);
     2. FATORES — lista (GET /api/multiescala/fatores) com "usar" e PESO por controle deslizante; novo fator com a
        escala nativa DECLARADA (POST /api/multiescala/fatores); amostras por texto "lon, lat, valor" ou por grade
        constante sobre a área (POST /api/multiescala/fatores/{id}/amostras); apagar (DELETE);
     3. RODAR — resolução da grade macro e regra de aprovação (limiar ou top_pct) → POST /conjuntos/{id}/macro;
        depois REFINAR (POST /execucoes/{id}/micro) só dentro das células aprovadas;
     4. EXPLICAR — o relatório por fator que o servidor devolve (escala declarada × escala da grade, razão,
        `escala_grosseira`) vira texto; as células (GET /execucoes/{id}/celulas) pintam o mapa por nota 0-100, as
        aprovadas com contorno, e o clique numa célula mostra nota, cobertura e aprovação.
   Os pesos são escolhidos pelo usuário — o painel repete AVISO_PESOS de web/js/amc/combinacao.js em toda saída.
   Estados por <plat-estado> em cada passo; erro da API nomeado (422 de aprovação/resolução, 404, 403). */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { obter, enviar, apagar, mensagemDe } from '../base/api.js';
import { confirmar } from '../base/componentes.js';
import { AVISO_PESOS } from '../amc/combinacao.js';

const cor = (nome, reserva) => (getComputedStyle(document.documentElement).getPropertyValue(nome) || '').trim() || reserva;
const FONTE_AREA = 'plat-motor-area';
const FONTE_CELULAS = { macro: 'plat-motor-macro', micro: 'plat-motor-micro' };

const num = (v, casas = 0) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: casas }));

export class PainelMotor {
  constructor(map, maplibregl, raiz) {
    this.map = map; this.gl = maplibregl; this.raiz = raiz;
    this.conjuntos = []; this.conjunto = null;
    this.fatores = []; this.uso = new Map(); // fator_id -> { usar, peso }
    this.execucoes = { macro: null, micro: null };
    this.popup = null;
    this._montar();
    map.on('click', (ev) => this._cliqueCelula(ev));
  }

  /* ---------------------------------------------------------------- montagem */
  _montar() {
    limpar(this.raiz);
    this.raiz.append(
      h('p', { class: 'ajuda' }, t('motor.ajuda')),
      this._secaoArea(), this._secaoFatores(), this._secaoRodar(),
      h('div', { class: 'motor-saida', id: 'motor-saida', 'aria-live': 'polite' }),
    );
    this.carregarConjuntos();
    this.carregarFatores();
  }

  _secao(id, titulo, ...filhos) {
    return h('section', { class: 'motor-secao', id: `motor-secao-${id}` }, h('h3', {}, titulo), ...filhos);
  }

  _secaoArea() {
    this.estadoArea = h('plat-estado', { id: 'motor-area-estado' });
    this.estadoArea.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.carregarConjuntos(); });
    this.selArea = h('select', { id: 'motor-area', class: 'controle', 'aria-label': t('motor.area') });
    this.selArea.addEventListener('change', () => this.escolherConjunto(this.selArea.value));
    const nome = h('input', { type: 'text', id: 'motor-area-nome', class: 'controle', maxlength: '200', autocomplete: 'off' });
    const bbox = h('input', { type: 'text', id: 'motor-area-bbox', class: 'controle', autocomplete: 'off', spellcheck: 'false' });
    const btCriar = h('button', { type: 'button', class: 'primario pequeno', id: 'motor-area-criar' }, t('motor.area_criar'));
    btCriar.addEventListener('click', () => this.criarConjunto(nome.value.trim(), bbox.value.trim()));
    const btEnquadrar = h('button', { type: 'button', class: 'pequeno', id: 'motor-area-enquadrar' }, t('mapa.enquadrar'));
    btEnquadrar.addEventListener('click', () => this._enquadrarArea());
    const btApagar = h('button', { type: 'button', class: 'pequeno perigo', id: 'motor-area-apagar' }, t('acao.apagar'));
    btApagar.addEventListener('click', () => this.apagarConjunto());
    this.infoArea = h('p', { class: 'ajuda', id: 'motor-area-info' });
    return this._secao('area', t('motor.area'),
      this.estadoArea,
      h('div', { class: 'campo' }, h('label', { for: 'motor-area' }, t('motor.area_existente')), this.selArea),
      h('div', { class: 'botoes' }, btEnquadrar, btApagar),
      this.infoArea,
      h('div', { class: 'campo' }, h('label', { for: 'motor-area-nome' }, t('motor.area_nome')), nome),
      h('div', { class: 'campo' }, h('label', { for: 'motor-area-bbox' }, t('motor.area_bbox')), bbox, h('span', { class: 'ajuda' }, t('motor.area_da_vista_ajuda'))),
      h('div', { class: 'botoes' }, btCriar));
  }

  _secaoFatores() {
    this.estadoFatores = h('plat-estado', { id: 'motor-fatores-estado' });
    this.estadoFatores.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.carregarFatores(); if (ev.detail.id === 'novo') this.raiz.querySelector('#motor-fator-nome')?.focus(); });
    this.listaFatores = h('ul', { class: 'motor-fatores', id: 'motor-fatores-lista', 'aria-label': t('motor.fatores') });
    const nome = h('input', { type: 'text', id: 'motor-fator-nome', class: 'controle', maxlength: '200', autocomplete: 'off' });
    const res = h('input', { type: 'number', id: 'motor-fator-res', class: 'controle', min: '1', step: 'any', value: '100' });
    const papel = h('select', { id: 'motor-fator-papel', class: 'controle' }, h('option', { value: 'atrai' }, t('motor.papel_atrai')), h('option', { value: 'custo' }, t('motor.papel_custo')));
    const unidade = h('input', { type: 'text', id: 'motor-fator-unidade', class: 'controle', maxlength: '40', autocomplete: 'off' });
    const btCriar = h('button', { type: 'button', class: 'primario pequeno', id: 'motor-fator-criar' }, t('motor.fator_criar'));
    btCriar.addEventListener('click', () => this.criarFator({ nome: nome.value.trim(), resolucao_fonte_m: Number(res.value), papel: papel.value, unidade: unidade.value.trim() }));
    this.formFator = { nome, res, papel, unidade };
    return this._secao('fatores', t('motor.fatores'),
      this.estadoFatores, this.listaFatores,
      h('details', { class: 'motor-novo' }, h('summary', {}, t('motor.fator_novo')),
        h('div', { class: 'campo' }, h('label', { for: 'motor-fator-nome' }, t('campo.nome')), nome),
        h('div', { class: 'campo' }, h('label', { for: 'motor-fator-res' }, t('motor.fator_resolucao')), res, h('span', { class: 'ajuda' }, t('motor.fator_resolucao_ajuda'))),
        h('div', { class: 'campo' }, h('label', { for: 'motor-fator-papel' }, t('motor.fator_papel')), papel),
        h('div', { class: 'campo' }, h('label', { for: 'motor-fator-unidade' }, t('motor.fator_unidade')), unidade),
        h('div', { class: 'botoes' }, btCriar)));
  }

  _secaoRodar() {
    this.res = h('input', { type: 'number', id: 'motor-resolucao', class: 'controle', min: '1', step: 'any', value: '1000' });
    this.aprovTipo = h('select', { id: 'motor-aprovacao-tipo', class: 'controle' }, h('option', { value: 'top_pct' }, t('motor.aprovacao_top_pct')), h('option', { value: 'limiar' }, t('motor.aprovacao_limiar')));
    this.aprovValor = h('input', { type: 'number', id: 'motor-aprovacao-valor', class: 'controle', min: '0', max: '100', step: 'any', value: '50' });
    const btRodar = h('button', { type: 'button', class: 'primario', id: 'motor-rodar' }, t('motor.rodar'));
    btRodar.addEventListener('click', () => this.rodar('macro'));
    this.resMicro = h('input', { type: 'number', id: 'motor-resolucao-micro', class: 'controle', min: '1', step: 'any', value: '250' });
    const btRefinar = h('button', { type: 'button', id: 'motor-refinar', disabled: true }, t('motor.refinar'));
    btRefinar.addEventListener('click', () => this.rodar('micro'));
    this.btRefinar = btRefinar;
    const btLimpar = h('button', { type: 'button', class: 'pequeno', id: 'motor-limpar' }, t('motor.limpar_resultado'));
    btLimpar.addEventListener('click', () => this.limparResultado());
    this.estadoRodar = h('plat-estado', { id: 'motor-rodar-estado' });
    this.estadoRodar.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.rodar(this.ultimoNivel || 'macro'); });
    return this._secao('rodar', t('motor.rodar_titulo'),
      h('div', { class: 'campo' }, h('label', { for: 'motor-resolucao' }, t('motor.resolucao_macro')), this.res),
      h('div', { class: 'linha' },
        h('div', { class: 'campo' }, h('label', { for: 'motor-aprovacao-tipo' }, t('motor.aprovacao')), this.aprovTipo),
        h('div', { class: 'campo' }, h('label', { for: 'motor-aprovacao-valor' }, t('motor.aprovacao_valor')), this.aprovValor)),
      h('div', { class: 'botoes' }, btRodar, btLimpar),
      h('div', { class: 'campo' }, h('label', { for: 'motor-resolucao-micro' }, t('motor.resolucao_micro')), this.resMicro),
      h('div', { class: 'botoes' }, btRefinar),
      h('p', { class: 'ajuda' }, AVISO_PESOS),
      this.estadoRodar);
  }

  /* ---------------------------------------------------------------- área de estudo */
  async carregarConjuntos(selecionar = null) {
    this.estadoArea.carregando(t('motor.carregando'));
    const r = await obter('/api/multiescala/conjuntos?limite=100');
    if (r.status !== 200) { this.estadoArea.erro(r); return; }
    this.conjuntos = r.json.itens || [];
    limpar(this.selArea);
    this.selArea.append(h('option', { value: '' }, t('motor.area_escolha')));
    for (const c of this.conjuntos) this.selArea.append(h('option', { value: c.id }, c.nome));
    if (!this.conjuntos.length) { this.estadoArea.vazio(t('motor.area_vazio')); this.escolherConjunto(''); return; }
    this.estadoArea.limpar();
    const alvo = selecionar || (this.conjunto && this.conjunto.id) || '';
    this.selArea.value = alvo && this.conjuntos.some((c) => c.id === alvo) ? alvo : '';
    this.escolherConjunto(this.selArea.value);
  }

  escolherConjunto(id) {
    this.conjunto = this.conjuntos.find((c) => c.id === id) || null;
    this.limparResultado();
    const c = this.conjunto;
    this.infoArea.textContent = c ? t('motor.area_info', { largura: num(c.largura_m), altura: num(c.altura_m), srid: c.srid_nome || c.srid_trabalho }) : '';
    this._desenharArea(c && c.area ? c.area : null);
    this.raiz.querySelector('#motor-area-apagar').disabled = !c;
    this.raiz.querySelector('#motor-area-enquadrar').disabled = !c;
  }

  _poligonoDaVista() {
    const b = this.map.getBounds();
    const o = b.getWest(); const e = b.getEast(); const s = b.getSouth(); const n = b.getNorth();
    return { type: 'Polygon', coordinates: [[[o, s], [e, s], [e, n], [o, n], [o, s]]] };
  }

  /* "oeste, sul, leste, norte" em graus → polígono; null quando vazio; false quando inválido */
  _poligonoDoTexto(texto) {
    if (!texto) return null;
    const n = texto.split(/[,;\s]+/).filter(Boolean).map(Number);
    if (n.length !== 4 || n.some((x) => Number.isNaN(x))) return false;
    const [o, s, e, nn] = n;
    if (o < -180 || e > 180 || s < -90 || nn > 90 || o >= e || s >= nn) return false;
    return { type: 'Polygon', coordinates: [[[o, s], [e, s], [e, nn], [o, nn], [o, s]]] };
  }

  async criarConjunto(nome, bboxTexto = '') {
    if (!nome) { this.estadoArea.erro(t('motor.area_nome_obrigatorio'), []); this.raiz.querySelector('#motor-area-nome').focus(); return; }
    const doTexto = this._poligonoDoTexto(bboxTexto);
    if (doTexto === false) { this.estadoArea.erro(t('motor.area_bbox_invalido'), []); this.raiz.querySelector('#motor-area-bbox').focus(); return; }
    this.estadoArea.carregando(t('motor.criando'));
    const r = await enviar('/api/multiescala/conjuntos', { nome, area: doTexto || this._poligonoDaVista() });
    if (r.status !== 201) { this.estadoArea.erro(r, []); return; }
    this.raiz.querySelector('#motor-area-nome').value = '';
    this.raiz.querySelector('#motor-area-bbox').value = '';
    await this.carregarConjuntos(r.json.id);
  }

  async apagarConjunto() {
    const c = this.conjunto;
    if (!c) return;
    if (!(await confirmar(t('acao.apagar'), t('motor.area_apagar_confirma', { nome: c.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/multiescala/conjuntos/${encodeURIComponent(c.id)}`);
    if (r.status !== 204) { this.estadoArea.erro(r, []); return; }
    this.conjunto = null;
    await this.carregarConjuntos();
  }

  _desenharArea(area) {
    const geo = { type: 'FeatureCollection', features: area ? [{ type: 'Feature', geometry: area, properties: {} }] : [] };
    const src = this.map.getSource(FONTE_AREA);
    if (src) { src.setData(geo); return; }
    this.map.addSource(FONTE_AREA, { type: 'geojson', data: geo });
    this.map.addLayer({ id: `${FONTE_AREA}-borda`, type: 'line', source: FONTE_AREA, paint: { 'line-color': cor('--acento', '#d98a2b'), 'line-width': 2, 'line-dasharray': [2, 2] } });
  }

  _enquadrarArea() {
    const a = this.conjunto && this.conjunto.area;
    if (!a) return;
    const c = a.coordinates[0];
    const lons = c.map((p) => p[0]); const lats = c.map((p) => p[1]);
    this.map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40 });
  }

  /* ---------------------------------------------------------------- fatores */
  async carregarFatores() {
    this.estadoFatores.carregando(t('motor.carregando'));
    const r = await obter('/api/multiescala/fatores?limite=200');
    if (r.status !== 200) { this.estadoFatores.erro(r); return; }
    this.fatores = r.json.itens || [];
    for (const f of this.fatores) if (!this.uso.has(f.id)) this.uso.set(f.id, { usar: true, peso: 1 });
    this._listaFatores();
    if (!this.fatores.length) this.estadoFatores.vazio(t('motor.fatores_vazio'), [{ id: 'novo', rotulo: t('motor.fator_novo') }]);
    else this.estadoFatores.limpar();
  }

  _listaFatores() {
    limpar(this.listaFatores);
    for (const f of this.fatores) {
      const u = this.uso.get(f.id);
      const usar = h('input', { type: 'checkbox', id: `motor-usar-${f.id}` });
      usar.checked = u.usar;
      usar.addEventListener('change', () => { u.usar = usar.checked; });
      const peso = h('input', { type: 'range', id: `motor-peso-${f.id}`, min: '0.1', max: '10', step: '0.1', value: String(u.peso), 'aria-label': t('motor.peso_de', { nome: f.nome }) });
      const pesoTexto = h('output', { for: `motor-peso-${f.id}`, class: 'mono' }, String(u.peso));
      peso.addEventListener('input', () => { u.peso = Number(peso.value); pesoTexto.textContent = String(u.peso); });
      const btAmostras = h('button', { type: 'button', class: 'pequeno', dataset: { amostras: f.id } }, t('motor.amostras'));
      btAmostras.addEventListener('click', () => this._abrirAmostras(f, li));
      const btApagar = h('button', { type: 'button', class: 'pequeno perigo', dataset: { apagarFator: f.id }, 'aria-label': t('motor.fator_apagar', { nome: f.nome }) }, '×');
      btApagar.addEventListener('click', () => this.apagarFator(f));
      const li = h('li', { class: 'motor-fator', dataset: { fator: f.id } },
        h('label', { class: 'caixa', for: `motor-usar-${f.id}` }, usar, h('strong', {}, f.nome)),
        h('span', { class: 'ajuda' }, `${t(`motor.papel_${f.papel}`)} · ${t('motor.fator_escala', { m: num(f.resolucao_fonte_m) })}${f.unidade ? ` · ${f.unidade}` : ''}`),
        h('div', { class: 'linha' }, h('label', { for: `motor-peso-${f.id}` }, t('motor.peso')), peso, pesoTexto),
        h('div', { class: 'botoes' }, btAmostras, btApagar));
      this.listaFatores.append(li);
    }
  }

  async criarFator(dados) {
    if (!dados.nome) { this.estadoFatores.erro(t('motor.fator_nome_obrigatorio'), []); this.formFator.nome.focus(); return; }
    if (!(dados.resolucao_fonte_m > 0)) { this.estadoFatores.erro(t('motor.fator_resolucao_invalida'), []); this.formFator.res.focus(); return; }
    this.estadoFatores.carregando(t('motor.criando'));
    const r = await enviar('/api/multiescala/fatores', { ...dados, fonte: '' });
    if (r.status !== 201) { this.estadoFatores.erro(r, []); return; }
    this.formFator.nome.value = ''; this.formFator.unidade.value = '';
    await this.carregarFatores();
  }

  async apagarFator(f) {
    if (!(await confirmar(t('acao.apagar'), t('motor.fator_apagar_confirma', { nome: f.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/multiescala/fatores/${encodeURIComponent(f.id)}`);
    if (r.status !== 204) { this.estadoFatores.erro(r, []); return; }
    this.uso.delete(f.id);
    await this.carregarFatores();
  }

  _abrirAmostras(f, li) {
    const existente = li.querySelector('.motor-amostras');
    if (existente) { existente.remove(); return; }
    const area = h('textarea', { rows: '4', class: 'controle', 'aria-label': t('motor.amostras_texto') });
    const valor = h('input', { type: 'number', class: 'controle', step: 'any', value: '10', 'aria-label': t('motor.amostras_valor') });
    const estado = h('plat-estado');
    const btGrade = h('button', { type: 'button', class: 'pequeno', dataset: { amostrasGrade: f.id } }, t('motor.amostras_grade'));
    btGrade.addEventListener('click', () => {
      const a = this.conjunto && this.conjunto.area;
      if (!a) { estado.erro(t('motor.amostras_sem_area'), []); return; }
      area.value = this._gradeConstante(a, Number(valor.value)).map((p) => `${p.lon.toFixed(6)}, ${p.lat.toFixed(6)}, ${p.valor}`).join('\n');
    });
    const btEnviar = h('button', { type: 'button', class: 'pequeno primario', dataset: { amostrasEnviar: f.id } }, t('motor.amostras_enviar'));
    btEnviar.addEventListener('click', async () => {
      const amostras = [];
      for (const linha of area.value.split('\n')) {
        const m = linha.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)$/);
        if (m) amostras.push({ lon: Number(m[1]), lat: Number(m[2]), valor: Number(m[3]) });
      }
      if (!amostras.length) { estado.erro(t('motor.amostras_invalidas'), []); return; }
      estado.carregando(t('motor.amostras_enviando', { n: amostras.length }));
      const r = await enviar(`/api/multiescala/fatores/${encodeURIComponent(f.id)}/amostras`, { amostras });
      if (r.status !== 201) { estado.erro(r, []); return; }
      estado.mostrar({ tipo: 'vazio', titulo: t('motor.amostras_gravadas', { n: r.json.gravadas }), texto: '' });
    });
    li.append(h('div', { class: 'motor-amostras' },
      h('p', { class: 'ajuda' }, t('motor.amostras_ajuda')), area,
      h('div', { class: 'linha' }, h('label', {}, t('motor.amostras_valor'), valor), btGrade, btEnviar), estado));
  }

  _gradeConstante(area, valor, n = 6) {
    const c = area.coordinates[0];
    const lons = c.map((p) => p[0]); const lats = c.map((p) => p[1]);
    const x0 = Math.min(...lons); const x1 = Math.max(...lons); const y0 = Math.min(...lats); const y1 = Math.max(...lats);
    const fx = (x1 - x0) * 0.05; const fy = (y1 - y0) * 0.05;
    const pontos = [];
    for (let i = 0; i < n; i += 1) for (let j = 0; j < n; j += 1) {
      pontos.push({ lon: x0 + fx + (x1 - x0 - 2 * fx) * i / (n - 1), lat: y0 + fy + (y1 - y0 - 2 * fy) * j / (n - 1), valor });
    }
    return pontos;
  }

  /* ---------------------------------------------------------------- rodar */
  _fatoresPedidos() {
    return this.fatores.filter((f) => this.uso.get(f.id)?.usar).map((f) => ({ fator_id: f.id, peso: this.uso.get(f.id).peso }));
  }

  async rodar(nivel) {
    this.ultimoNivel = nivel;
    const fatores = this._fatoresPedidos();
    if (!this.conjunto) { this.estadoRodar.erro(t('motor.sem_area'), []); return; }
    if (!fatores.length) { this.estadoRodar.erro(t('motor.sem_fatores'), []); return; }
    const resolucao = Number(nivel === 'macro' ? this.res.value : this.resMicro.value);
    if (!(resolucao > 0)) { this.estadoRodar.erro(t('motor.resolucao_invalida'), []); return; }
    if (nivel === 'micro' && !this.execucoes.macro) { this.estadoRodar.erro(t('motor.micro_sem_macro'), []); return; }
    const corpo = { resolucao_m: resolucao, fatores, aprovacao_tipo: this.aprovTipo.value, aprovacao_valor: Number(this.aprovValor.value) };
    const url = nivel === 'macro'
      ? `/api/multiescala/conjuntos/${encodeURIComponent(this.conjunto.id)}/macro`
      : `/api/multiescala/execucoes/${encodeURIComponent(this.execucoes.macro.id)}/micro`;
    this.estadoRodar.carregando(t('motor.rodando', { nivel: t(`motor.nivel_${nivel}`) }));
    this.raiz.querySelector('#motor-rodar').disabled = true;
    const r = await enviar(url, corpo);
    this.raiz.querySelector('#motor-rodar').disabled = false;
    if (r.status !== 201) {
      this.estadoRodar.mostrar({ tipo: r.status === 403 ? 'negado' : 'erro', texto: mensagemDe(r), acoes: r.status === 403 ? [] : [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }], ref: r.json?.req_id });
      return;
    }
    this.estadoRodar.limpar();
    this.execucoes[nivel] = r.json;
    if (nivel === 'macro') { this.execucoes.micro = null; this._removerCamada('micro'); }
    this.btRefinar.disabled = !this.execucoes.macro;
    this._relatorio();
    await this._pintarCelulas(nivel, r.json.id);
  }

  _relatorio() {
    const saida = this.raiz.querySelector('#motor-saida');
    limpar(saida);
    for (const nivel of ['macro', 'micro']) {
      const e = this.execucoes[nivel];
      if (!e) continue;
      const fatores = h('ul', { class: 'motor-relatorio-fatores' });
      for (const f of e.fatores || []) {
        fatores.append(h('li', { class: f.escala_grosseira ? 'grosseira' : '' },
          h('strong', {}, f.nome), ` · ${t('motor.peso')} ${num(f.peso, 1)} · `,
          t('motor.rel_escala', { fonte: num(f.resolucao_fonte_m), grade: num(f.resolucao_grade_m), razao: num(f.razao_escala, 2) }),
          f.escala_grosseira ? h('span', { class: 'marcador atencao' }, t('motor.rel_grosseira')) : h('span', { class: 'marcador ok' }, t('motor.rel_fina')),
          f.escala_grosseira ? h('p', { class: 'ajuda' }, t('motor.rel_grosseira_explica', { fonte: num(f.resolucao_fonte_m), grade: num(f.resolucao_grade_m) })) : null,
          h('span', { class: 'ajuda' }, ` ${t('motor.rel_cobertura', { com_dado: num(f.celulas_com_dado), blocos: num(f.blocos_usados) })}`)));
      }
      saida.append(h('div', { class: 'cartao-interno motor-execucao', dataset: { nivel } },
        h('h3', {}, `${t(`motor.nivel_${nivel}`)} · ${t('motor.rel_resolucao', { m: num(e.grade.resolucao_m) })}`),
        h('p', {}, t('motor.rel_celulas', { celulas: num(e.celulas), possiveis: num(e.celulas_possiveis), aprovadas: num(e.celulas_aprovadas), ms: num(e.duracao_ms) })),
        nivel === 'micro' && e.celulas_possiveis ? h('p', { class: 'ajuda' }, t('motor.rel_economia', { pct: num(100 * (1 - e.celulas / e.celulas_possiveis), 1) })) : null,
        h('p', { class: 'ajuda' }, t('motor.rel_aprovacao', { tipo: t(`motor.aprovacao_${e.aprovacao_tipo}`), valor: num(e.aprovacao_valor, 1) })),
        fatores,
        h('p', { class: 'ajuda' }, AVISO_PESOS)));
    }
  }

  /* ---------------------------------------------------------------- células no mapa */
  async _pintarCelulas(nivel, execucaoId) {
    const r = await obter(`/api/multiescala/execucoes/${encodeURIComponent(execucaoId)}/celulas`);
    if (r.status !== 200) { this.estadoRodar.erro(r, []); return; }
    const id = FONTE_CELULAS[nivel];
    const geo = { type: 'FeatureCollection', features: r.json.features || [] };
    const src = this.map.getSource(id);
    if (src) src.setData(geo);
    else {
      this.map.addSource(id, { type: 'geojson', data: geo });
      const escala = ['interpolate', ['linear'], ['coalesce', ['get', 'nota'], 0], 0, cor('--falha', '#b42318'), 50, cor('--atencao', '#c98a1a'), 100, cor('--ok', '#2c7347')];
      this.map.addLayer({ id: `${id}-fill`, type: 'fill', source: id, paint: { 'fill-color': escala, 'fill-opacity': nivel === 'macro' ? 0.35 : 0.55 } });
      this.map.addLayer({ id: `${id}-borda`, type: 'line', source: id, paint: { 'line-color': cor('--texto', '#111'), 'line-width': ['case', ['get', 'aprovada'], 2, 0.5], 'line-opacity': 0.8 } });
    }
    if (r.json.truncado) this.estadoRodar.mostrar({ tipo: 'vazio', titulo: t('motor.celulas_truncadas_titulo'), texto: t('motor.celulas_truncadas', { mostradas: geo.features.length, total: r.json.total }) });
  }

  _removerCamada(nivel) {
    const id = FONTE_CELULAS[nivel];
    for (const suf of ['-fill', '-borda']) if (this.map.getLayer(id + suf)) this.map.removeLayer(id + suf);
    if (this.map.getSource(id)) this.map.removeSource(id);
  }

  limparResultado() {
    this.execucoes = { macro: null, micro: null };
    this._removerCamada('macro'); this._removerCamada('micro');
    this.btRefinar.disabled = true;
    limpar(this.raiz.querySelector('#motor-saida'));
    this.estadoRodar.limpar();
    if (this.popup) { this.popup.remove(); this.popup = null; }
  }

  _cliqueCelula(ev) {
    const camadas = ['micro', 'macro'].map((n) => `${FONTE_CELULAS[n]}-fill`).filter((l) => this.map.getLayer(l));
    if (!camadas.length) return;
    const feicoes = this.map.queryRenderedFeatures(ev.point, { layers: camadas });
    if (!feicoes.length) return;
    const f = feicoes[0];
    const p = f.properties;
    const nivel = f.layer.id.includes('micro') ? 'micro' : 'macro';
    const texto = `${t(`motor.nivel_${nivel}`)} · ${t('motor.celula_pos', { col: p.col, lin: p.lin })}\n${t('motor.celula_nota', { nota: p.nota === null || p.nota === undefined ? '—' : num(p.nota, 1) })}\n${t('motor.celula_cobertura', { pct: num(100 * Number(p.cobertura), 0) })}\n${p.aprovada ? t('motor.celula_aprovada') : t('motor.celula_reprovada')}`;
    if (this.popup) this.popup.remove();
    this.popup = new this.gl.Popup({ closeButton: true, className: 'motor-popup' }).setLngLat(ev.lngLat).setText(texto).addTo(this.map);
  }
}
