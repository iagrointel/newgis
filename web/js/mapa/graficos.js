/* plat · mapa — painel "Gráficos" do visualizador (item L2-01-i-graficos-de-camada).

   Um gráfico por camada ligada: o painel monta o pedido (tipo, campo, estatística, filtro, extensão) e manda
   para POST /api/camadas/{id}/grafico — a agregação é SEMPRE no servidor; o que volta são centenas de números,
   nunca a tabela crua (refutação: nenhuma resposta > 1 MB). O desenho é o SVG próprio de grafico_svg.js.

   Reage ao que muda ao redor: extensão visível (moveend, quando marcado), filtro digitado aqui, e o evento
   `plat:filtro-camada` {camada, filtro} que o construtor de filtro do L2-01-h dispara quando entrar (o
   backend dele já existe; o front-end está na fila). O clique numa barra/fatia/faixa SELECIONA no mapa: uma
   camada de destaque com o mesmo filtro em expressão MapLibre e a contagem pedida ao servidor com o filtro
   equivalente (`campo = 'valor'`, `IS NULL`, faixa numérica) — o e2e prova que a contagem selecionada é a da
   barra. Gráficos ficam guardados por camada em localStorage (mesma decisão da ordem das camadas e dos
   favoritos); gravar no documento do item de mapa espera o esquema do L2-01-a, declarado em PARIDADE.md. */
import { h, limpar } from '../base/dom.js';
import { enviar, mensagemDe } from '../base/api.js';
import { t } from '../base/i18n.js';
import { desenhar, tabela, csv, paraTexto, LARGURA, ALTURA } from './grafico_svg.js';

const NS = 'http://www.w3.org/2000/svg';
const CHAVE = 'plat.mapa.graficos';
const TIPOS = ['barras', 'pizza', 'linha', 'histograma', 'dispersao'];
const ESTATISTICAS = ['count', 'sum', 'avg'];
const GRANULARIDADES = ['dia', 'semana', 'mes', 'trimestre', 'ano'];
const NUMERICOS = /^(smallint|integer|bigint|numeric|real|double precision|int|int4|int8|float|float8|decimal)/i;
const DATAS = /^(date|timestamp)/i;
const MAX_LINHAS_TABELA = 2000;

function paraDom(arvore) {
  if (typeof arvore === 'string') return document.createTextNode(arvore);
  const el = document.createElementNS(NS, arvore.tag);
  for (const [k, v] of Object.entries(arvore.atrs || {})) el.setAttribute(k, String(v));
  for (const f of arvore.filhos || []) el.append(paraDom(f));
  return el;
}

/* texto SQL-92 (gramática do app.consulta.where_ast) que seleciona o que uma barra representa */
export function filtroDaBarra(campo, el) {
  if (el.dataset.outros === '1') return null;
  if (el.dataset.nulo === '1') return { texto: `${campo} IS NULL`, maplibre: ['!', ['has', campo]], rotulo: 'sem valor' };
  if (el.dataset.de !== undefined) {
    const de = Number(el.dataset.de);
    const ate = Number(el.dataset.ate);
    const fecha = el.dataset.ultima === '1';
    return {
      texto: `${campo} >= ${de} AND ${campo} ${fecha ? '<=' : '<'} ${ate}`,
      maplibre: ['all', ['>=', ['to-number', ['get', campo]], de], [fecha ? '<=' : '<', ['to-number', ['get', campo]], ate]],
      rotulo: `${de} – ${ate}`,
    };
  }
  const chave = el.dataset.chave;
  if (el.dataset.ate !== undefined && el.classList.contains('ponto')) {
    // faixa de data: da chave até a próxima faixa (texto ISO comparável como texto no tile e no SQL)
    const ate = el.dataset.ate;
    const texto = ate ? `${campo} >= '${chave.replace(/'/g, "''")}' AND ${campo} < '${ate.replace(/'/g, "''")}'` : `${campo} >= '${chave.replace(/'/g, "''")}'`;
    const ml = ate ? ['all', ['>=', ['get', campo], chave], ['<', ['get', campo], ate]] : ['>=', ['get', campo], chave];
    return { texto, maplibre: ml, rotulo: chave };
  }
  const numero = chave !== '' && !Number.isNaN(Number(chave)) && String(Number(chave)) === chave;
  return {
    texto: numero ? `${campo} = ${chave}` : `${campo} = '${chave.replace(/'/g, "''")}'`,
    maplibre: ['==', ['get', campo], numero ? Number(chave) : chave],
    rotulo: chave,
  };
}

function juntar(a, b) {
  if (a && b) return `(${a}) AND (${b})`;
  return a || b || '';
}

export class PainelGraficos {
  constructor(map, catalogo, raiz, { aoSelecionar = () => {}, aoErro = () => {} } = {}) {
    this.map = map;
    this.catalogo = catalogo;
    this.raiz = raiz;
    this.aoSelecionar = aoSelecionar;
    this.aoErro = aoErro;
    this.camadaId = null;
    this.dados = null;
    this.selecao = null;      // {camada, filtro, maplibre, n, rotulo}
    this.filtrosExternos = new Map();  // camadaId → filtro vindo de plat:filtro-camada
    this._montar();
    catalogo.aoMudar(() => this._sincronizarCamadas());
    map.on('moveend', () => { if (this.campos.extensao.checked && this.dados) this.gerar(); });
    document.addEventListener('plat:filtro-camada', (ev) => {
      const d = ev.detail || {};
      if (!d.camada) return;
      this.filtrosExternos.set(d.camada, d.filtro || '');
      if (d.camada === this.camadaId) { this.campos.filtro.value = d.filtro || ''; if (this.dados) this.gerar(); }
    });
    this._sincronizarCamadas();
  }

  /* ---------------------------------------------------------------- formulário */
  _montar() {
    const sel = (id, opcoes, rotulo) => {
      const s = h('select', { id, 'aria-label': rotulo });
      for (const [v, r] of opcoes) s.append(h('option', { value: v }, r));
      return s;
    };
    this.campos = {
      camada: sel('grafico-camada', [], t('mapa.grafico_camada')),
      tipo: sel('grafico-tipo', TIPOS.map((x) => [x, t(`mapa.grafico_tipo_${x}`)]), t('mapa.grafico_tipo')),
      campo: sel('grafico-campo', [], t('mapa.grafico_campo')),
      estatistica: sel('grafico-estatistica', ESTATISTICAS.map((x) => [x, t(`mapa.grafico_estat_${x}`)]), t('mapa.grafico_estatistica')),
      campoY: sel('grafico-campo-y', [], t('mapa.grafico_campo_y')),
      granularidade: sel('grafico-granularidade', GRANULARIDADES.map((x) => [x, t(`mapa.grafico_gran_${x}`)]), t('mapa.grafico_granularidade')),
      faixas: h('input', { id: 'grafico-faixas', type: 'number', min: '1', max: '200', value: '10', 'aria-label': t('mapa.grafico_faixas') }),
      filtro: h('input', { id: 'grafico-filtro', type: 'text', autocomplete: 'off', 'aria-label': t('mapa.grafico_filtro'), title: "categoria = 'norte' AND valor > 10" }),
      extensao: h('input', { id: 'grafico-extensao', type: 'checkbox' }),
    };
    this.campos.granularidade.value = 'mes';
    const linha = (...els) => h('div', { class: 'linha grafico-linha' }, ...els);
    const rot = (chave, el) => h('label', { class: 'grafico-rotulo' }, t(chave), el);
    this.botoes = {
      gerar: h('button', { type: 'button', id: 'grafico-gerar', class: 'botao', onclick: () => this.gerar() }, t('mapa.grafico_gerar')),
      salvar: h('button', { type: 'button', id: 'grafico-salvar', class: 'botao secundario', onclick: () => this.salvar() }, t('mapa.grafico_salvar')),
      png: h('button', { type: 'button', id: 'grafico-png', class: 'botao secundario', disabled: true, onclick: () => this.exportarPng() }, 'PNG'),
      csv: h('button', { type: 'button', id: 'grafico-csv', class: 'botao secundario', disabled: true, onclick: () => this.exportarCsv() }, 'CSV'),
      limpar: h('button', { type: 'button', id: 'grafico-limpar-selecao', class: 'botao secundario', disabled: true, onclick: () => this.limparSelecao() }, t('mapa.grafico_limpar_selecao')),
    };
    this.area = h('div', { id: 'grafico-area', class: 'grafico-area' });
    this.saida = h('p', { id: 'grafico-saida', class: 'saida', 'aria-live': 'polite' });
    this.tabelaEl = h('table', { id: 'grafico-tabela', class: 'sr-only' });
    this.salvos = h('ul', { id: 'grafico-salvos', class: 'sugestoes grafico-salvos' });
    limpar(this.raiz);
    this.raiz.append(
      linha(rot('mapa.grafico_camada', this.campos.camada)),
      linha(rot('mapa.grafico_tipo', this.campos.tipo), rot('mapa.grafico_campo', this.campos.campo)),
      linha(rot('mapa.grafico_estatistica', this.campos.estatistica), rot('mapa.grafico_campo_y', this.campos.campoY)),
      linha(rot('mapa.grafico_granularidade', this.campos.granularidade), rot('mapa.grafico_faixas', this.campos.faixas)),
      linha(rot('mapa.grafico_filtro', this.campos.filtro)),
      linha(h('label', { class: 'grafico-rotulo grafico-caixa' }, this.campos.extensao, t('mapa.grafico_extensao'))),
      linha(this.botoes.gerar, this.botoes.salvar, this.botoes.png, this.botoes.csv, this.botoes.limpar),
      this.area, this.saida, this.tabelaEl, this.salvos,
    );
    this.campos.camada.addEventListener('change', () => this.abrir(this.campos.camada.value, false));
    this.campos.tipo.addEventListener('change', () => this._ajustarCampos());
    this.campos.estatistica.addEventListener('change', () => this._ajustarCampos());
    this.campos.filtro.addEventListener('change', () => { if (this.dados) this.gerar(); });
    this._ajustarCampos();
  }

  _sincronizarCamadas() {
    const s = this.campos.camada;
    const atual = s.value;
    limpar(s);
    for (const id of this.catalogo.ativas) {
      const f = this.catalogo.ficha(id);
      if (f) s.append(h('option', { value: id }, f.titulo));
    }
    if (this.catalogo.ativas.includes(atual)) s.value = atual;
    else if (this.catalogo.ativas.length) { s.value = this.catalogo.ativas[0]; this.abrir(s.value, false); }
    if (this.selecao && !this.catalogo.ativas.includes(this.selecao.camada)) this.limparSelecao();
  }

  _camposDaCamada() {
    const f = this.catalogo.ficha(this.camadaId);
    return (f && f.campos) || [];
  }

  _ajustarCampos() {
    const tipo = this.campos.tipo.value;
    const estat = this.campos.estatistica.value;
    const campos = this._camposDaCamada();
    const encher = (sel, lista) => {
      const antes = sel.value;
      limpar(sel);
      for (const c of lista) sel.append(h('option', { value: c.nome }, `${c.nome} (${c.tipo || 'text'})`));
      if (lista.some((c) => c.nome === antes)) sel.value = antes;
    };
    const numericos = campos.filter((c) => NUMERICOS.test(c.tipo || ''));
    if (tipo === 'histograma' || tipo === 'dispersao') encher(this.campos.campo, numericos);
    else if (tipo === 'linha') encher(this.campos.campo, campos.filter((c) => DATAS.test(c.tipo || '')));
    else encher(this.campos.campo, campos);
    encher(this.campos.campoY, numericos);
    const mostrar = (el, sim) => { el.closest('.grafico-rotulo').hidden = !sim; };
    mostrar(this.campos.estatistica, tipo === 'barras' || tipo === 'pizza' || tipo === 'linha');
    mostrar(this.campos.campoY, tipo === 'dispersao' || ((tipo === 'barras' || tipo === 'pizza' || tipo === 'linha') && estat !== 'count'));
    mostrar(this.campos.granularidade, tipo === 'linha');
    mostrar(this.campos.faixas, tipo === 'histograma');
  }

  /* ---------------------------------------------------------------- abrir uma camada (botão da árvore) */
  abrir(camadaId, focar = true) {
    if (!this.catalogo.ficha(camadaId)) return false;
    this.camadaId = camadaId;
    if (this.campos.camada.value !== camadaId) this.campos.camada.value = camadaId;
    this.campos.filtro.value = this.filtrosExternos.get(camadaId) || '';
    this._ajustarCampos();
    this._desenharSalvos();
    const salvos = this.lerSalvos()[camadaId] || [];
    if (salvos.length) this.aplicarConfiguracao(salvos[0]);
    else { this.dados = null; limpar(this.area); limpar(this.tabelaEl); }
    if (focar) { this.raiz.scrollIntoView({ block: 'nearest' }); this.campos.tipo.focus(); }
    return true;
  }

  configuracao() {
    const c = {
      tipo: this.campos.tipo.value, campo: this.campos.campo.value, estatistica: this.campos.estatistica.value,
      campo_y: this.campos.campoY.value || null, granularidade: this.campos.granularidade.value,
      faixas: Number(this.campos.faixas.value) || 10, filtro: this.campos.filtro.value.trim(), extensao: this.campos.extensao.checked,
    };
    if (c.tipo === 'histograma' || (c.estatistica === 'count' && c.tipo !== 'dispersao')) c.campo_y = null;
    return c;
  }

  aplicarConfiguracao(c) {
    this.campos.tipo.value = c.tipo;
    this.campos.estatistica.value = c.estatistica || 'count';
    this._ajustarCampos();
    if (c.campo) this.campos.campo.value = c.campo;
    if (c.campo_y) this.campos.campoY.value = c.campo_y;
    if (c.granularidade) this.campos.granularidade.value = c.granularidade;
    if (c.faixas) this.campos.faixas.value = String(c.faixas);
    this.campos.filtro.value = c.filtro || '';
    this.campos.extensao.checked = !!c.extensao;
    return this.gerar();
  }

  /* ---------------------------------------------------------------- pedido ao servidor e desenho */
  pedido() {
    const c = this.configuracao();
    const corpo = { tipo: c.tipo, campo: c.campo, estatistica: c.tipo === 'dispersao' ? 'count' : c.estatistica };
    if (c.campo_y) corpo.campo_y = c.campo_y;
    if (c.tipo === 'linha') corpo.granularidade = c.granularidade;
    if (c.tipo === 'histograma') corpo.faixas = c.faixas;
    if (c.filtro) corpo.filtro = c.filtro;
    if (c.extensao) {
      const b = this.map.getBounds();
      corpo.extensao = { xmin: b.getWest(), ymin: b.getSouth(), xmax: b.getEast(), ymax: b.getNorth() };
    }
    return corpo;
  }

  async gerar() {
    if (!this.camadaId) return null;
    const corpo = this.pedido();
    if (!corpo.campo) { this.saida.textContent = t('mapa.grafico_sem_campo'); return null; }
    // pedidos em voo fora de ordem (filtro digitado + extensão marcada em seguida): só a resposta do ÚLTIMO
    // pedido conta; uma anterior que chegue depois é descartada em vez de sobrescrever o gráfico
    this._sequencia = (this._sequencia || 0) + 1;
    const meu = this._sequencia;
    this.raiz.dataset.ocupado = '1';
    const r = await enviar(`/api/camadas/${this.camadaId}/grafico`, corpo);
    if (meu !== this._sequencia) return null;
    delete this.raiz.dataset.ocupado;
    if (r.status !== 200) {
      this.saida.textContent = mensagemDe(r);
      this.dados = null;
      limpar(this.area);
      limpar(this.tabelaEl);
      this.botoes.png.disabled = this.botoes.csv.disabled = true;
      return null;
    }
    this.dados = r.json;
    this.desenhar();
    return this.dados;
  }

  desenhar() {
    const d = this.dados;
    const selecionado = (e) => this.selecao && this.selecao.camada === this.camadaId && this.selecao.chave !== undefined
      && String(e.chave ?? '') === String(this.selecao.chave ?? '');
    const arvore = desenhar(d, { titulo: t('mapa.grafico_titulo', { tipo: t(`mapa.grafico_tipo_${d.tipo}`), campo: d.campo }),
      mensagemVazio: t('mapa.grafico_vazio'), selecionado });
    this.svgTexto = paraTexto(arvore);
    limpar(this.area);
    const svg = paraDom(arvore);
    this.area.append(svg);
    svg.querySelectorAll('.barra').forEach((el) => {
      el.addEventListener('click', () => this.selecionar(el));
      el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); this.selecionar(el); } });
    });
    this._tabela();
    const partes = [t('mapa.grafico_resumo', { total: (d.total ?? 0).toLocaleString('pt-BR'), nulos: (d.nulos ?? 0).toLocaleString('pt-BR'), ms: d.tempo_ms })];
    if (d.truncado && d.outros) partes.push(t('mapa.grafico_outros', { n: d.outros.categorias.toLocaleString('pt-BR') }));
    if (d.tipo === 'dispersao' && d.amostra) partes.push(t('mapa.grafico_amostra', { n: d.series.length.toLocaleString('pt-BR') }));
    if (d.tipo === 'dispersao' && d.regressao) partes.push(`r² = ${d.regressao.r2 === null ? '—' : d.regressao.r2.toFixed(4)}`);
    this.saida.textContent = partes.join(' · ');
    this.botoes.png.disabled = this.botoes.csv.disabled = false;
  }

  _tabela() {
    const tb = tabela(this.dados);
    limpar(this.tabelaEl);
    this.tabelaEl.append(h('caption', {}, `${this.dados.tipo} · ${this.dados.campo}`));
    this.tabelaEl.append(h('thead', {}, h('tr', {}, ...tb.cabecalho.map((c) => h('th', { scope: 'col' }, c)))));
    const corpo = h('tbody', {});
    tb.linhas.slice(0, MAX_LINHAS_TABELA).forEach((l) => corpo.append(h('tr', {}, ...l.map((v) => h('td', {}, v === null || v === undefined ? '' : String(v))))));
    if (tb.linhas.length > MAX_LINHAS_TABELA) corpo.append(h('tr', {}, h('td', { colspan: String(tb.cabecalho.length) }, `… ${tb.linhas.length - MAX_LINHAS_TABELA} linhas no CSV`)));
    this.tabelaEl.append(corpo);
    this.tabelaEl.append(h('tfoot', {}, ...tb.rodape.map(([k, v]) => h('tr', {}, h('th', { scope: 'row' }, k), h('td', { colspan: String(Math.max(1, tb.cabecalho.length - 1)) }, v === null ? '' : String(v))))));
    this.tabelaEl.dataset.linhas = String(tb.linhas.length);
  }

  /* ---------------------------------------------------------------- seleção no mapa a partir do clique */
  async selecionar(el) {
    const d = this.dados;
    if (!d || d.tipo === 'dispersao') return null;
    const f = filtroDaBarra(d.campo, el);
    if (!f) { this.saida.textContent = t('mapa.grafico_outros_sem_selecao'); return null; }
    const c = this.configuracao();
    const corpo = { tipo: 'contagem', filtro: juntar(c.filtro, f.texto) };
    if (c.extensao) corpo.extensao = this.pedido().extensao;
    const r = await enviar(`/api/camadas/${this.camadaId}/grafico`, corpo);
    if (r.status !== 200) { this.saida.textContent = mensagemDe(r); return null; }
    this.selecao = { camada: this.camadaId, campo: d.campo, filtro: corpo.filtro, maplibre: f.maplibre, n: r.json.total, rotulo: f.rotulo,
      chave: el.dataset.nulo === '1' ? null : (el.dataset.chave ?? el.dataset.de) };
    this._destacarNoMapa();
    this.desenhar();
    this.saida.textContent = t('mapa.grafico_selecionadas', { n: this.selecao.n.toLocaleString('pt-BR'), rotulo: f.rotulo });
    this.botoes.limpar.disabled = false;
    this.aoSelecionar(this.selecao);
    document.dispatchEvent(new CustomEvent('plat:selecao-camada', { detail: { ...this.selecao } }));
    return this.selecao;
  }

  _idsDestaque() {
    return this.map.getStyle().layers.map((l) => l.id).filter((id) => id.startsWith('plat-sel-'));
  }

  _destacarNoMapa() {
    for (const id of this._idsDestaque()) this.map.removeLayer(id);
    if (!this.selecao) return;
    const f = this.catalogo.ficha(this.selecao.camada);
    if (!f) return;
    for (const camada of f.estilo) {
      if (!this.map.getLayer(camada.id)) continue;
      const clone = JSON.parse(JSON.stringify(camada));
      clone.id = `plat-sel-${camada.id}`;
      clone.filter = camada.filter ? ['all', camada.filter, this.selecao.maplibre] : this.selecao.maplibre;
      clone.paint = clone.paint || {};
      if (clone.type === 'circle') Object.assign(clone.paint, { 'circle-color': '#ffd54a', 'circle-stroke-color': '#1a1002', 'circle-stroke-width': 1.2, 'circle-opacity': 1 });
      else if (clone.type === 'line') Object.assign(clone.paint, { 'line-color': '#ffd54a', 'line-width': 3, 'line-opacity': 1 });
      else if (clone.type === 'fill') Object.assign(clone.paint, { 'fill-color': '#ffd54a', 'fill-opacity': 0.75, 'fill-outline-color': '#1a1002' });
      else if (clone.type === 'symbol') { clone.paint = { ...clone.paint, 'icon-color': '#ffd54a', 'text-color': '#ffd54a' }; }
      else continue;
      this.map.addLayer(clone);
    }
  }

  limparSelecao() {
    this.selecao = null;
    for (const id of this._idsDestaque()) this.map.removeLayer(id);
    this.botoes.limpar.disabled = true;
    if (this.dados) this.desenhar();
    this.saida.textContent = t('mapa.grafico_selecao_limpa');
    this.aoSelecionar(null);
    document.dispatchEvent(new CustomEvent('plat:selecao-camada', { detail: null }));
  }

  /* ---------------------------------------------------------------- exportação */
  async exportarPng() {
    if (!this.svgTexto) return null;
    const escala = 3;
    const canvas = document.createElement('canvas');
    canvas.width = LARGURA * escala;
    canvas.height = ALTURA * escala;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#12181a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const svgComTamanho = this.svgTexto.replace('width="100%"', `width="${LARGURA}" height="${ALTURA}"`);
    const url = URL.createObjectURL(new Blob([svgComTamanho], { type: 'image/svg+xml;charset=utf-8' }));
    try {
      const img = new Image();
      await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error('svg')); img.src = url; });
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    } finally { URL.revokeObjectURL(url); }
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/png'));
    baixar(blob, `grafico-${this.dados.tipo}-${this.dados.campo}.png`);
    this.saida.textContent = t('mapa.impressao_pronta', { formato: 'PNG', kb: Math.round(blob.size / 1024) });
    return blob;
  }

  exportarCsv() {
    if (!this.dados) return null;
    const texto = csv(this.dados);
    const blob = new Blob([texto], { type: 'text/csv;charset=utf-8' });
    baixar(blob, `grafico-${this.dados.tipo}-${this.dados.campo}.csv`);
    this.saida.textContent = t('mapa.impressao_pronta', { formato: 'CSV', kb: Math.max(1, Math.round(blob.size / 1024)) });
    return texto;
  }

  /* ---------------------------------------------------------------- gráficos guardados por camada */
  lerSalvos() {
    try { const b = localStorage.getItem(CHAVE); return b ? JSON.parse(b) : {}; } catch { return {}; }
  }

  _gravar(todos) {
    try { localStorage.setItem(CHAVE, JSON.stringify(todos)); return true; } catch { return false; }
  }

  salvar() {
    if (!this.camadaId) return null;
    const c = this.configuracao();
    const todos = this.lerSalvos();
    const lista = (todos[this.camadaId] || []).filter((x) => JSON.stringify(x) !== JSON.stringify(c));
    lista.unshift(c);
    todos[this.camadaId] = lista.slice(0, 12);
    this._gravar(todos);
    this._desenharSalvos();
    this.saida.textContent = t('mapa.grafico_salvo');
    return c;
  }

  remover(indice) {
    const todos = this.lerSalvos();
    const lista = todos[this.camadaId] || [];
    lista.splice(indice, 1);
    todos[this.camadaId] = lista;
    this._gravar(todos);
    this._desenharSalvos();
  }

  _desenharSalvos() {
    limpar(this.salvos);
    const lista = this.lerSalvos()[this.camadaId] || [];
    lista.forEach((c, i) => {
      const rotulo = `${t(`mapa.grafico_tipo_${c.tipo}`)} · ${c.campo}${c.campo_y ? ` × ${c.campo_y}` : ''}${c.filtro ? ' · filtro' : ''}`;
      this.salvos.append(h('li', { dataset: { salvo: String(i) } },
        h('button', { type: 'button', class: 'sugestao', onclick: () => this.aplicarConfiguracao(c) }, rotulo),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': `remover ${rotulo}`, onclick: () => this.remover(i) }, '✕')));
    });
  }
}

function baixar(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
