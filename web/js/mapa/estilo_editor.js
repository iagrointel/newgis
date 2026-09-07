/* plat · mapa — editor de simbologia vetorial (item L2-02-c-editor-simbologia-vetor).
   Um painel ao lado do mapa que edita o `plat_construtor` (o documento do L2-02-a) de UMA camada do catálogo:
   tipos do Map Viewer (símbolo único, por categoria, por classe de cor e de tamanho, proporcional, mapa de
   calor, agrupamento), efeitos por camada, faixa de escala por camada e por classe, ícones do sprite do
   inquilino (L2-02-e), rampas ColorBrewer (vendor, Apache-2.0), classificação pelo servidor (L2-02-b).
   Pré-visualização ao vivo pela MESMA função que grava (POST /api/estilos/compilar → catalogo.aplicarEstilo);
   nenhum compilador no navegador. Desfazer/refazer por instantâneos do documento. Salvar grava um item
   `estilo` com `camada_id` (relação estilo_de_camada); o visualizador passa a desenhar a camada com ele. */
import { obter, enviar, alterar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { cores as coresDaRampa, sugerirCategorias, sugerirClasses, normalizar, COR_OUTROS } from './estilo_sugestao.js';

const TIPOS = [
  ['unico', 'símbolo único'], ['categoria', 'por categoria'], ['classes', 'por classe (cor / tamanho)'],
  ['proporcional', 'proporcional'], ['calor', 'mapa de calor'], ['agrupamento', 'agrupamento (clusters)'],
];
const CLASSIFICACOES = [['quantil', 'quantil'], ['intervalo_igual', 'intervalo igual'], ['quebras_naturais', 'quebras naturais'],
  ['desvio_padrao', 'desvio padrão'], ['manual', 'manual']];
const GEOMETRIA = { Point: 'ponto', MultiPoint: 'ponto', LineString: 'linha', MultiLineString: 'linha', Polygon: 'poligono', MultiPolygon: 'poligono' };
const RAMPAS_CALOR = [['Magma', ['#000004', '#3b0f70', '#8c2981', '#de4968', '#fe9f6d', '#fcfdbf']], ['Viridis', ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725']]];

function esquemas() { return window.colorbrewer || {}; }
function grupo(nome) { const g = (esquemas().schemeGroups || {}); return Object.entries(g).find(([, lista]) => lista.includes(nome))?.[0] || 'sequential'; }
function rampasDe(grupoNome) { const g = esquemas().schemeGroups || {}; return (g[grupoNome] || []).concat(grupoNome === 'sequential' ? (g.singlehue || []) : []); }
function clonar(o) { return JSON.parse(JSON.stringify(o)); }

export class EditorEstilo {
  constructor({ catalogo, map, raiz, aoFechar = () => {} }) {
    this.catalogo = catalogo; this.map = map; this.raiz = raiz; this.aoFechar = aoFechar;
    this.camadaId = null; this.ficha = null; this.doc = null; this.estiloId = null;
    this.passado = []; this.futuro = []; this._compilar = null; this.icones = null;
  }

  /* ---------- ciclo de vida ---------- */
  async abrir(camadaId) {
    const f = this.catalogo.ficha(camadaId);
    if (!f) return;
    this.camadaId = camadaId; this.ficha = f; this.passado = []; this.futuro = [];
    this.estiloId = f.estilo_id || null;
    this.doc = f.plat_construtor ? clonar(f.plat_construtor) : this._padrao(f);
    if (!this.catalogo.ativas.includes(camadaId)) await this.catalogo.ligar(camadaId);
    if (!this.icones) {
      const r = await obter('/api/simbolos');
      this.icones = r.status === 200 ? ((r.json.itens || r.json.icones || r.json) || []).map((i) => i.nome || i).filter(Boolean) : [];
    }
    this.raiz.hidden = false;
    this.render();
    await this.previsualizar();
  }

  fechar() { this.raiz.hidden = true; this.camadaId = null; this.aoFechar(); }

  _padrao(f) {
    const geometria = GEOMETRIA[f.geometria] || 'poligono';
    const cor = (f.legenda && f.legenda[0] && f.legenda[0].cor) || '#4e79a7';
    const simbolo = { cor, contorno_cor: '#10161a', contorno_largura: geometria === 'poligono' ? 0.6 : 0.5, opacidade: geometria === 'poligono' ? 0.55 : 0.9 };
    if (geometria === 'ponto') simbolo.raio = 5; else if (geometria === 'linha') simbolo.largura = 1.5;
    return { tipo: 'unico', geometria, versao: 1, simbolo, campos: (f.campos || []).map((c) => c.nome) };
  }

  /* ---------- histórico ---------- */
  _mudar(fn, { previsualizar = true, registrar = true } = {}) {
    const antes = clonar(this.doc);
    fn(this.doc);
    if (JSON.stringify(antes) === JSON.stringify(this.doc)) return; // alteração sem efeito: nada no histórico
    if (registrar) { this.passado.push(antes); if (this.passado.length > 100) this.passado.shift(); this.futuro = []; }
    this.render();
    if (previsualizar) this.previsualizar();
  }

  desfazer() { if (!this.passado.length) return; this.futuro.push(clonar(this.doc)); this.doc = this.passado.pop(); this.render(); this.previsualizar(); }
  refazer() { if (!this.futuro.length) return; this.passado.push(clonar(this.doc)); this.doc = this.futuro.pop(); this.render(); this.previsualizar(); }

  /* ---------- servidor ---------- */
  documento() { return normalizar(clonar(this.doc), (this.ficha.campos || []).map((c) => c.nome)); }

  previsualizar() {
    clearTimeout(this._compilar);
    return new Promise((resolve) => {
      this._compilar = setTimeout(async () => {
        const pc = this.documento();
        const r = await enviar('/api/estilos/compilar', { plat_construtor: pc, id_base: `plat-${this.camadaId}` });
        const aviso = this.raiz.querySelector('#estilo-aviso');
        if (r.status !== 200) {
          if (aviso) { aviso.textContent = (r.json && r.json.mensagem) || `erro ${r.status}`; aviso.dataset.tipo = 'erro'; }
          resolve(false); return;
        }
        if (aviso) { aviso.textContent = ''; delete aviso.dataset.tipo; }
        const agrupamento = pc.tipo === 'agrupamento' ? { raio_px: (pc.agrupamento && pc.agrupamento.raio_px) || 40 } : null;
        try { await this.catalogo.aplicarEstilo(this.camadaId, r.json.maplibre.layers, r.json.legenda, { agrupamento, plat_construtor: pc }); }
        catch (e) { if (aviso) { aviso.textContent = e.message; aviso.dataset.tipo = 'erro'; } }
        this.raiz.dataset.previsualizado = String((Number(this.raiz.dataset.previsualizado) || 0) + 1);
        resolve(true);
      }, 150);
    });
  }

  async salvar() {
    const pc = this.documento();
    const aviso = this.raiz.querySelector('#estilo-aviso');
    const dados = { esquema_versao: 1, camada_id: this.camadaId, corpo: { plat_construtor: pc, maplibre: { version: 8, layers: [] } } };
    const rc = await enviar('/api/estilos/compilar', { plat_construtor: pc });
    if (rc.status === 200) dados.corpo.maplibre = rc.json.maplibre;
    const titulo = `estilo · ${this.ficha.titulo}`.slice(0, 250);
    const r = this.estiloId
      ? await alterar(`/api/itens/${this.estiloId}`, { dados })
      : await enviar('/api/itens', { tipo: 'estilo', titulo, dados });
    if (r.status !== 200 && r.status !== 201) {
      aviso.textContent = `não salvo: ${(r.json && r.json.mensagem) || r.status}` + (r.json && r.json.detalhe ? ` (${JSON.stringify(r.json.detalhe)})` : '');
      aviso.dataset.tipo = 'erro';
      return false;
    }
    this.estiloId = r.json.id;
    this.ficha.estilo_id = this.estiloId; this.ficha.plat_construtor = pc;
    aviso.textContent = `salvo (${this.estiloId.slice(0, 8)})`; aviso.dataset.tipo = 'ok';
    this.raiz.dataset.salvo = this.estiloId;
    return true;
  }

  exportar() {
    const texto = JSON.stringify({ esquema_versao: 1, camada_id: this.camadaId, corpo: { plat_construtor: this.documento(), maplibre: this.ficha.estilo ? { version: 8, layers: this.ficha.estilo.map(({ source, 'source-layer': sl, ...l }) => l) } : { version: 8, layers: [] } } }, null, 1);
    const a = h('a', { href: `data:application/json;charset=utf-8,${encodeURIComponent(texto)}`, download: `estilo-${this.camadaId.slice(0, 8)}.json` });
    document.body.append(a); a.click(); a.remove();
    return texto;
  }

  importar(texto) {
    let d;
    try { d = JSON.parse(texto); } catch (e) { return false; }
    const pc = d && d.corpo && d.corpo.plat_construtor ? d.corpo.plat_construtor : (d && d.tipo ? d : null);
    if (!pc) return false;
    this._mudar((doc) => { for (const k of Object.keys(doc)) delete doc[k]; Object.assign(doc, clonar(pc)); });
    return true;
  }

  /* ---------- dados do servidor para sugestões ---------- */
  async classes(campo, metodo, n, cortes) {
    const q = new URLSearchParams({ campo });
    if (metodo) q.set('metodo', metodo); if (n) q.set('n', String(n)); if (cortes) q.set('cortes', cortes);
    const r = await obter(`/api/camadas/${this.camadaId}/classes?${q}`);
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || `classes: ${r.status}`);
    return r.json;
  }

  async sugerirCategoria() {
    const d = this.doc;
    if (!d.campo) return;
    const resposta = await this.classes(d.campo);
    const nome = d.rampa || 'Set3';
    const paleta = coresDaRampa(esquemas(), nome, Math.min(12, Math.max(3, resposta.valores.length)), !!d.rampa_invertida);
    const s = sugerirCategorias(resposta, paleta);
    this.raiz.dataset.totalDistintos = String(s.total_distintos);
    this.raiz.dataset.agrupadosEmOutros = String(s.agrupados_em_outros);
    this._mudar((doc) => { doc.rampa = nome; doc.categorias = s.categorias; if (s.outros) doc.outros = s.outros; else delete doc.outros; });
  }

  async sugerirClasses() {
    const d = this.doc;
    if (!d.campo) return;
    const metodo = d.metodo && d.metodo !== 'nenhum' ? d.metodo : 'quantil';
    const n = d.n_classes || 5;
    const resposta = await this.classes(d.campo, metodo, n, metodo === 'manual' ? d.cortes_manuais : null);
    const nome = d.rampa || 'YlGnBu';
    const paleta = coresDaRampa(esquemas(), nome, resposta.cortes.length - 1, !!d.rampa_invertida);
    const tamanhos = d.classes_de_tamanho ? [d.tamanho_min || 2, d.tamanho_max || 14] : null;
    this._mudar((doc) => { doc.metodo = metodo; doc.rampa = nome; doc.cortes = resposta.cortes; doc.classes = sugerirClasses(resposta.cortes, paleta, tamanhos); });
    this.raiz.dataset.cortes = JSON.stringify(resposta.cortes);
  }

  async sugerirProporcional() {
    const d = this.doc; if (!d.campo) return;
    const r = await this.classes(d.campo, 'intervalo_igual', 1);
    this._mudar((doc) => { doc.proporcional = { ...(doc.proporcional || {}), valor_min: r.cortes[0], valor_max: r.cortes[r.cortes.length - 1], raio_min: (doc.proporcional && doc.proporcional.raio_min) || 3, raio_max: (doc.proporcional && doc.proporcional.raio_max) || 24, cor: (doc.simbolo && doc.simbolo.cor) || '#4e79a7' }; });
  }

  /* ---------- render ---------- */
  render() {
    const d = this.doc; const raiz = this.raiz; limpar(raiz);
    const campos = (this.ficha.campos || []);
    const numericos = campos.filter((c) => /int|numeric|double|real|decimal|float/i.test(c.tipo || '')).map((c) => c.nome);
    const cab = h('div', { class: 'estilo-cabecalho' },
      h('h2', {}, 'simbologia'), h('span', { class: 'estilo-camada', id: 'estilo-camada' }, this.ficha.titulo),
      h('button', { type: 'button', class: 'botao-mini', id: 'estilo-fechar', 'aria-label': 'fechar', onclick: () => this.fechar() }, '✕'));
    const tipo = this._campo('tipo', 'tipo', this._select('tipo', d.tipo, TIPOS.filter(([t]) => !(d.geometria !== 'ponto' && ['proporcional', 'calor', 'agrupamento'].includes(t))), (v) => this._mudar((doc) => this._trocarTipo(doc, v))));
    const secoes = [cab, h('p', { class: 'estilo-aviso', id: 'estilo-aviso', 'aria-live': 'polite' }), tipo];
    if (['categoria', 'classes', 'proporcional'].includes(d.tipo)) {
      const opcoes = (d.tipo === 'categoria' ? campos.map((c) => c.nome) : numericos).map((n) => [n, n]);
      secoes.push(this._campo('campo', 'campo', this._select('campo', d.campo || '', [['', '—'], ...opcoes], (v) => this._mudar((doc) => { doc.campo = v || null; }, { previsualizar: false }))));
    }
    if (d.tipo === 'unico') secoes.push(this._secaoSimbolo(d));
    if (d.tipo === 'categoria') secoes.push(this._secaoCategoria(d));
    if (d.tipo === 'classes') secoes.push(this._secaoClasses(d, numericos));
    if (d.tipo === 'proporcional') secoes.push(this._secaoProporcional(d));
    if (d.tipo === 'calor') secoes.push(this._secaoCalor(d));
    if (d.tipo === 'agrupamento') secoes.push(this._secaoAgrupamento(d));
    secoes.push(this._secaoEfeitos(d), this._secaoEscala(d), this._rodape());
    raiz.append(...secoes);
    raiz.dataset.tipo = d.tipo;
  }

  _trocarTipo(doc, tipo) {
    doc.tipo = tipo;
    // a rampa acompanha a família do tipo: qualitativa em categoria, sequencial/divergente em classes
    if (doc.rampa && ((tipo === 'categoria' && grupo(doc.rampa) !== 'qualitative')
      || (tipo === 'classes' && !['sequential', 'diverging'].includes(grupo(doc.rampa))))) delete doc.rampa;
    if (tipo === 'calor' && !doc.calor) doc.calor = { raio_px: 20, intensidade: 1, rampa: RAMPAS_CALOR[0][1] };
    if (tipo === 'agrupamento' && !doc.agrupamento) doc.agrupamento = { raio_px: 40, degraus: [{ ate: 10, cor: '#9ecae1', raio: 12 }, { ate: 100, cor: '#6baed6', raio: 18 }, { cor: '#08519c', raio: 26 }] };
    if (tipo === 'unico' && !doc.simbolo) doc.simbolo = { cor: '#4e79a7' };
    if (tipo === 'categoria') { doc.categorias = doc.categorias || []; }
    if (tipo === 'classes') { doc.classes = doc.classes || []; doc.metodo = doc.metodo || 'quantil'; }
  }

  _campo(id, rotulo, controle) { return h('div', { class: 'estilo-campo', dataset: { campo: id } }, h('label', { for: `estilo-${id}` }, rotulo), controle); }
  _select(id, valor, opcoes, aoMudar) {
    const s = h('select', { id: `estilo-${id}`, name: id });
    for (const [v, r] of opcoes) s.append(h('option', { value: v }, r));
    s.value = valor ?? ''; s.addEventListener('change', () => aoMudar(s.value)); return s;
  }
  _cor(id, valor, aoMudar) { const i = h('input', { type: 'color', id: `estilo-${id}`, name: id, value: valor || '#4e79a7' }); i.addEventListener('input', () => aoMudar(i.value)); return i; }
  _numero(id, valor, aoMudar, atributos = {}) { const i = h('input', { type: 'number', id: `estilo-${id}`, name: id, value: valor ?? '', ...atributos }); i.addEventListener('change', () => aoMudar(i.value === '' ? null : Number(i.value))); return i; }
  _caixa(id, valor, aoMudar) { const i = h('input', { type: 'checkbox', id: `estilo-${id}`, name: id }); i.checked = !!valor; i.addEventListener('change', () => aoMudar(i.checked)); return i; }
  _icone(id, valor, aoMudar) { return this._select(id, valor || '', [['', 'sem ícone'], ...(this.icones || []).map((n) => [n, n])], (v) => aoMudar(v || null)); }
  _rampa(id, valor, grupoNome, aoMudar) { return this._select(id, valor || '', [['', '—'], ...rampasDe(grupoNome).map((n) => [n, n])], (v) => aoMudar(v || null)); }

  _secaoSimbolo(d) {
    const s = d.simbolo = d.simbolo || {};
    const mud = (k) => (v) => this._mudar((doc) => { doc.simbolo = { ...(doc.simbolo || {}), [k]: v }; if (v === null || v === '') delete doc.simbolo[k]; });
    const itens = [this._campo('cor', 'cor', this._cor('cor', s.cor, mud('cor')))];
    if (d.geometria === 'ponto') {
      itens.push(this._campo('raio', 'tamanho (px)', this._numero('raio', s.raio ?? 5, mud('raio'), { min: 0, max: 100, step: 0.5 })),
        this._campo('icone', 'ícone', this._icone('icone', s.icone, mud('icone'))),
        this._campo('icone_tamanho', 'fator do ícone', this._numero('icone_tamanho', s.icone_tamanho ?? 1, mud('icone_tamanho'), { min: 0.1, max: 8, step: 0.1 })));
    }
    if (d.geometria === 'linha') {
      itens.push(this._campo('largura', 'largura (px)', this._numero('largura', s.largura ?? 1.5, mud('largura'), { min: 0, max: 40, step: 0.5 })),
        this._campo('tracejado', 'tracejado (ex.: 2,1)', (() => { const i = h('input', { type: 'text', id: 'estilo-tracejado', name: 'tracejado', value: (s.tracejado || []).join(',') }); i.addEventListener('change', () => mud('tracejado')(i.value.trim() ? i.value.split(',').map(Number).filter((n) => !Number.isNaN(n)) : null)); return i; })()),
        this._campo('seta', 'seta ao longo da linha', this._icone('seta', s.seta, mud('seta'))));
    }
    if (d.geometria === 'poligono') {
      itens.push(this._campo('padrao', 'padrão de preenchimento', this._icone('padrao', s.padrao, mud('padrao'))));
    }
    if (d.geometria !== 'linha') itens.push(this._campo('contorno_cor', 'contorno', this._cor('contorno_cor', s.contorno_cor || '#10161a', mud('contorno_cor'))),
      this._campo('contorno_largura', 'largura do contorno', this._numero('contorno_largura', s.contorno_largura ?? 0.6, mud('contorno_largura'), { min: 0, max: 40, step: 0.1 })));
    itens.push(this._campo('transparencia', 'transparência', this._numero('transparencia', d.transparencia ?? 0, (v) => this._mudar((doc) => { doc.transparencia = v || 0; }), { min: 0, max: 1, step: 0.05 })));
    return h('section', { class: 'estilo-secao', dataset: { secao: 'simbolo' } }, h('h3', {}, 'símbolo'), ...itens);
  }

  _linhaClasse(lista, i, item, extras) {
    const mud = (k) => (v) => this._mudar((doc) => { const alvo = doc[lista][i]; if (v === null || v === '') delete alvo[k]; else alvo[k] = v; });
    const li = h('li', { class: 'estilo-classe', dataset: { indice: String(i) } },
      this._cor(`${lista}-${i}-cor`, item.cor, mud('cor')),
      h('input', { type: 'text', class: 'estilo-rotulo', name: `${lista}-${i}-rotulo`, value: item.rotulo ?? (item.valor ?? `${item.min} a ${item.max}`), 'aria-label': 'rótulo', onchange: (e) => mud('rotulo')(e.target.value) }),
      ...extras(mud),
      h('button', { type: 'button', class: 'botao-mini', 'aria-label': 'subir', onclick: () => this._mudar((doc) => { if (i > 0) doc[lista].splice(i - 1, 0, doc[lista].splice(i, 1)[0]); }) }, '↑'),
      h('button', { type: 'button', class: 'botao-mini', 'aria-label': 'remover', onclick: () => this._mudar((doc) => { doc[lista].splice(i, 1); }) }, '✕'));
    return li;
  }

  _secaoCategoria(d) {
    const cab = h('div', { class: 'estilo-linha' },
      this._campo('rampa', 'rampa qualitativa', this._rampa('rampa', d.rampa, 'qualitative', (v) => this._mudar((doc) => { doc.rampa = v; }, { previsualizar: false }))),
      h('label', {}, this._caixa('rampa_invertida', d.rampa_invertida, (v) => this._mudar((doc) => { doc.rampa_invertida = v; }, { previsualizar: false })), ' inverter'),
      h('button', { type: 'button', class: 'botao', id: 'estilo-sugerir-categorias', onclick: () => this.sugerirCategoria().catch((e) => { this.raiz.querySelector('#estilo-aviso').textContent = e.message; }) }, 'valores do campo'));
    const ul = h('ul', { class: 'estilo-classes', id: 'estilo-categorias' });
    (d.categorias || []).forEach((c, i) => ul.append(this._linhaClasse('categorias', i, c, (mud) => [
      this._icone(`categorias-${i}-icone`, c.icone, mud('icone')),
      this._numero(`categorias-${i}-escala_max`, c.escala_max ?? '', mud('escala_max'), { title: 'até 1:N', title: 'só aparece de 1:N para mais perto', min: 0 }),
    ])));
    const outros = d.outros || null;
    const secOutros = h('div', { class: 'estilo-linha', id: 'estilo-outros' },
      h('label', {}, this._caixa('outros_visivel', outros && outros.visivel !== false, (v) => this._mudar((doc) => { doc.outros = { cor: (doc.outros && doc.outros.cor) || COR_OUTROS, rotulo: (doc.outros && doc.outros.rotulo) || 'outros', visivel: v }; })), ' outros (demais valores)'),
      this._cor('outros_cor', (outros && outros.cor) || COR_OUTROS, (v) => this._mudar((doc) => { doc.outros = { ...(doc.outros || { rotulo: 'outros', visivel: true }), cor: v }; })));
    const info = h('p', { class: 'estilo-info', id: 'estilo-categorias-info' }, `${(d.categorias || []).length} categorias` + (this.raiz.dataset.agrupadosEmOutros && Number(this.raiz.dataset.agrupadosEmOutros) > 0 ? ` · ${this.raiz.dataset.agrupadosEmOutros} valores em "outros"` : ''));
    return h('section', { class: 'estilo-secao', dataset: { secao: 'categoria' } }, h('h3', {}, 'categorias'), cab, info, ul, secOutros);
  }

  _secaoClasses(d, numericos) {
    const mudSemPre = (k) => (v) => this._mudar((doc) => { doc[k] = v; }, { previsualizar: false });
    const cab = h('div', { class: 'estilo-linha' },
      this._campo('metodo', 'método', this._select('metodo', d.metodo || 'quantil', CLASSIFICACOES, mudSemPre('metodo'))),
      this._campo('n_classes', 'classes', this._numero('n_classes', d.n_classes || 5, mudSemPre('n_classes'), { min: 1, max: 32 })),
      d.metodo === 'manual' ? this._campo('cortes_manuais', 'cortes (a,b,c)', (() => { const i = h('input', { type: 'text', id: 'estilo-cortes_manuais', name: 'cortes_manuais', value: d.cortes_manuais || '' }); i.addEventListener('change', () => mudSemPre('cortes_manuais')(i.value)); return i; })()) : null,
      this._campo('rampa', 'rampa', this._rampa('rampa', d.rampa, d.rampa && grupo(d.rampa) === 'diverging' ? 'diverging' : 'sequential', mudSemPre('rampa'))),
      this._campo('rampa_grupo', 'família', this._select('rampa_grupo', d.rampa && grupo(d.rampa) === 'diverging' ? 'diverging' : 'sequential', [['sequential', 'sequencial'], ['diverging', 'divergente']], (v) => this._mudar((doc) => { doc.rampa = rampasDe(v)[0]; }, { previsualizar: false }))),
      h('label', {}, this._caixa('rampa_invertida', d.rampa_invertida, mudSemPre('rampa_invertida')), ' inverter'),
      h('label', {}, this._caixa('classes_de_tamanho', d.classes_de_tamanho, mudSemPre('classes_de_tamanho')), ' também por tamanho'),
      d.classes_de_tamanho ? this._campo('tamanho_min', 'tamanho mín', this._numero('tamanho_min', d.tamanho_min || 2, mudSemPre('tamanho_min'), { min: 0, max: 100 })) : null,
      d.classes_de_tamanho ? this._campo('tamanho_max', 'tamanho máx', this._numero('tamanho_max', d.tamanho_max || 14, mudSemPre('tamanho_max'), { min: 0, max: 100 })) : null,
      h('button', { type: 'button', class: 'botao', id: 'estilo-sugerir-classes', onclick: () => this.sugerirClasses().catch((e) => { this.raiz.querySelector('#estilo-aviso').textContent = e.message; }) }, 'classificar'));
    const ul = h('ul', { class: 'estilo-classes', id: 'estilo-classes-lista' });
    (d.classes || []).forEach((c, i) => ul.append(this._linhaClasse('classes', i, c, (mud) => [
      this._numero(`classes-${i}-min`, c.min, mud('min'), { step: 'any', 'aria-label': 'mínimo' }),
      this._numero(`classes-${i}-max`, c.max, mud('max'), { step: 'any', 'aria-label': 'máximo' }),
      this._numero(`classes-${i}-tamanho`, c.tamanho ?? '', mud('tamanho'), { step: 0.5, title: 'tam.', 'aria-label': 'tamanho', min: 0, max: 100 }),
      this._numero(`classes-${i}-escala_max`, c.escala_max ?? '', mud('escala_max'), { title: 'até 1:N', min: 0 }),
    ])));
    return h('section', { class: 'estilo-secao', dataset: { secao: 'classes' } }, h('h3', {}, 'classes'), cab, ul);
  }

  _secaoProporcional(d) {
    const p = d.proporcional || {};
    const mud = (k) => (v) => this._mudar((doc) => { doc.proporcional = { valor_min: 0, valor_max: 1, raio_min: 3, raio_max: 24, ...(doc.proporcional || {}), [k]: v }; });
    return h('section', { class: 'estilo-secao', dataset: { secao: 'proporcional' } }, h('h3', {}, 'proporcional'),
      h('button', { type: 'button', class: 'botao', id: 'estilo-sugerir-proporcional', onclick: () => this.sugerirProporcional().catch((e) => { this.raiz.querySelector('#estilo-aviso').textContent = e.message; }) }, 'mín/máx do campo'),
      this._campo('valor_min', 'valor mín', this._numero('valor_min', p.valor_min, mud('valor_min'), { step: 'any' })),
      this._campo('valor_max', 'valor máx', this._numero('valor_max', p.valor_max, mud('valor_max'), { step: 'any' })),
      this._campo('raio_min', 'raio mín (px)', this._numero('raio_min', p.raio_min ?? 3, mud('raio_min'), { min: 0, max: 100 })),
      this._campo('raio_max', 'raio máx (px)', this._numero('raio_max', p.raio_max ?? 24, mud('raio_max'), { min: 0, max: 100 })),
      this._campo('cor', 'cor', this._cor('cor', p.cor || '#4e79a7', mud('cor'))));
  }

  _secaoCalor(d) {
    const c = d.calor || {};
    const mud = (k) => (v) => this._mudar((doc) => { doc.calor = { raio_px: 20, intensidade: 1, ...(doc.calor || {}), [k]: v }; });
    return h('section', { class: 'estilo-secao', dataset: { secao: 'calor' } }, h('h3', {}, 'mapa de calor'),
      this._campo('raio_px', 'raio (px)', this._numero('raio_px', c.raio_px ?? 20, mud('raio_px'), { min: 1, max: 200 })),
      this._campo('intensidade', 'intensidade', this._numero('intensidade', c.intensidade ?? 1, mud('intensidade'), { min: 0, max: 20, step: 0.1 })),
      this._campo('rampa_calor', 'rampa', this._select('rampa_calor', RAMPAS_CALOR.find(([, r]) => JSON.stringify(r) === JSON.stringify(c.rampa))?.[0] || RAMPAS_CALOR[0][0], RAMPAS_CALOR.map(([n]) => [n, n]), (v) => mud('rampa')(RAMPAS_CALOR.find(([n]) => n === v)[1]))));
  }

  _secaoAgrupamento(d) {
    const a = d.agrupamento || { raio_px: 40, degraus: [] };
    const mudRaio = (v) => this._mudar((doc) => { doc.agrupamento = { ...(doc.agrupamento || { degraus: [] }), raio_px: v || 40 }; });
    const ul = h('ul', { class: 'estilo-classes', id: 'estilo-degraus' });
    (a.degraus || []).forEach((g, i) => ul.append(h('li', { class: 'estilo-classe', dataset: { indice: String(i) } },
      this._cor(`degrau-${i}-cor`, g.cor, (v) => this._mudar((doc) => { doc.agrupamento.degraus[i].cor = v; })),
      this._numero(`degrau-${i}-ate`, g.ate ?? '', (v) => this._mudar((doc) => { if (v === null) delete doc.agrupamento.degraus[i].ate; else doc.agrupamento.degraus[i].ate = v; }), { title: 'até (contagem)', min: 1 }),
      this._numero(`degrau-${i}-raio`, g.raio, (v) => this._mudar((doc) => { doc.agrupamento.degraus[i].raio = v; }), { min: 1, max: 100 }))));
    return h('section', { class: 'estilo-secao', dataset: { secao: 'agrupamento' } }, h('h3', {}, 'agrupamento'),
      this._campo('raio_px', 'raio do agrupamento (px)', this._numero('raio_px', a.raio_px ?? 40, mudRaio, { min: 8, max: 200 })),
      h('p', { class: 'estilo-info' }, 'degraus por contagem (cor e raio do círculo; o último é aberto)'), ul);
  }

  _secaoEfeitos(d) {
    const e = d.efeitos || {};
    const mud = (k) => (v) => this._mudar((doc) => { doc.efeitos = { ...(doc.efeitos || {}), [k]: v }; });
    const itens = [this._campo('mistura', 'mistura (registrada; sem blend na Style Spec)', this._select('mistura', e.mistura || 'normal', [['normal', 'normal'], ['multiply', 'multiplicar'], ['screen', 'tela']], mud('mistura')))];
    if (d.geometria === 'poligono') itens.push(h('label', { class: 'estilo-campo' }, this._caixa('sombra', e.sombra, mud('sombra')), ' sombra'));
    if (d.geometria === 'linha') itens.push(this._campo('brilho', 'brilho (px)', this._numero('brilho', e.brilho ?? 0, mud('brilho'), { min: 0, max: 20 })));
    return h('section', { class: 'estilo-secao', dataset: { secao: 'efeitos' } }, h('h3', {}, 'efeitos'), ...itens);
  }

  _secaoEscala(d) {
    const mud = (k) => (v) => this._mudar((doc) => { if (v) doc[k] = v; else delete doc[k]; });
    return h('section', { class: 'estilo-secao', dataset: { secao: 'escala' } }, h('h3', {}, 'faixa de escala da camada'),
      this._campo('escala_max', 'visível de 1:N (mais longe)', this._numero('escala_max', d.escala_max ?? '', mud('escala_max'), { min: 0, title: 'ex.: 2000000' })),
      this._campo('escala_min', 'até 1:N (mais perto)', this._numero('escala_min', d.escala_min ?? '', mud('escala_min'), { min: 0, title: 'ex.: 1000' })));
  }

  _rodape() {
    const arquivo = h('input', { type: 'file', accept: 'application/json', id: 'estilo-importar-arquivo', hidden: true });
    arquivo.addEventListener('change', async () => { const f = arquivo.files[0]; if (f) this.importar(await f.text()); arquivo.value = ''; });
    return h('div', { class: 'estilo-rodape' },
      h('button', { type: 'button', class: 'botao-mini', id: 'estilo-desfazer', title: 'desfazer', onclick: () => this.desfazer() }, '↶'),
      h('button', { type: 'button', class: 'botao-mini', id: 'estilo-refazer', title: 'refazer', onclick: () => this.refazer() }, '↷'),
      h('button', { type: 'button', class: 'botao', id: 'estilo-exportar', onclick: () => this.exportar() }, 'exportar JSON'),
      h('button', { type: 'button', class: 'botao', id: 'estilo-importar', onclick: () => arquivo.click() }, 'importar JSON'), arquivo,
      h('button', { type: 'button', class: 'botao primario', id: 'estilo-salvar', onclick: () => this.salvar() }, 'salvar'));
  }
}
