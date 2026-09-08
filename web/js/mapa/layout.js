/* plat · mapa — painel "Layout" (item L2-12-b-layouts-elementos-exportacao): o diálogo de impressão do visualizador.
   Modelo (padrão ou do inquilino) → documento de layout editável por FORMULÁRIO (coordenadas em mm; o editor por
   arrasto é o L5-08) → pré-visualização PNG (POST /api/layouts/previa) → exportação por job (POST
   /api/layouts/exportar → layout.exportar; progresso pelo canal de eventos da tela Tarefas) → link do arquivo.
   O mapa do quadro é o que está na tela: camadas ligadas do catálogo (com opacidade), mapa-base e vista atual.
   Grava o layout como item do catálogo (tipo `layout`; `modelo: true` = modelo do inquilino).
   Erro do servidor volta nomeado: 422 `layout_invalido` aponta o elemento e o campo. */
import { alterar, enviar, mensagemDe, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { assinar, cancelarAssinatura } from '../jobs/eventos.js';
import { FINAIS } from '../jobs/formato.js';

const TIPOS = ['mapa', 'legenda', 'escala', 'norte', 'grade', 'titulo', 'texto', 'imagem', 'tabela', 'data', 'atribuicao'];
const CAMPOS_GEOMETRIA = ['x', 'y', 'w', 'h'];

export class PainelLayout {
  constructor(map, catalogo, raiz, { baseAtual = () => 'osm-guarulhos', mapaId = () => null } = {}) {
    this.map = map;
    this.catalogo = catalogo;
    this.raiz = raiz;
    this.baseAtual = baseAtual;
    this.mapaId = mapaId;
    this.doc = null;          // documento de layout em edição
    this.itemId = null;       // id do item `layout` quando veio do catálogo
    this.modelos = null;
    this.job = null;
    this._ouvinte = (ev) => this._evento(ev);
    this._montar();
  }

  /* ---------------------------------------------------------------- montagem */
  _montar() {
    const r = this.raiz;
    limpar(r);
    this.estado = h('plat-estado', { id: 'lay-estado' });
    this.estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.carregarModelos(); });
    this.selModelo = h('select', { id: 'lay-modelo', class: 'controle' });
    this.selModelo.addEventListener('change', () => this.aplicarModelo(this.selModelo.value));
    this.selExistente = h('select', { id: 'lay-existente', class: 'controle' });
    this.selExistente.addEventListener('change', () => { if (this.selExistente.value) this.abrirItem(this.selExistente.value); });
    r.append(h('div', { class: 'campo' }, h('label', { for: 'lay-modelo' }, t('layout.modelo')), this.selModelo, h('span', { class: 'ajuda' }, t('layout.modelo_ajuda'))));
    r.append(h('div', { class: 'campo' }, h('label', { for: 'lay-existente' }, t('layout.existente')), this.selExistente));
    r.append(this.estado);
    // papel
    this.inNome = h('input', { type: 'text', id: 'lay-nome', class: 'controle', maxlength: '200', autocomplete: 'off' });
    this.selPapel = h('select', { id: 'lay-papel', class: 'controle' }, ...['A4', 'A3', 'A2', 'A1', 'A0', 'carta'].map((p) => h('option', { value: p }, p)));
    this.selOrientacao = h('select', { id: 'lay-orientacao', class: 'controle' }, h('option', { value: 'retrato' }, t('layout.retrato')), h('option', { value: 'paisagem' }, t('layout.paisagem')));
    for (const el of [this.inNome, this.selPapel, this.selOrientacao]) el.addEventListener('change', () => this._lerCabecalho());
    r.append(h('div', { class: 'campo' }, h('label', { for: 'lay-nome' }, t('layout.nome')), this.inNome));
    r.append(h('div', { class: 'linha' },
      h('div', { class: 'campo' }, h('label', { for: 'lay-papel' }, t('layout.papel')), this.selPapel),
      h('div', { class: 'campo' }, h('label', { for: 'lay-orientacao' }, t('layout.orientacao')), this.selOrientacao)));
    // elementos
    this.listaElementos = h('ol', { class: 'lay-elementos', id: 'lay-elementos', 'aria-label': t('layout.elementos') });
    this.selNovo = h('select', { id: 'lay-novo-tipo', class: 'controle', 'aria-label': t('layout.novo_tipo') }, ...TIPOS.map((tp) => h('option', { value: tp }, t(`layout.tipo_${tp}`))));
    const btNovo = h('button', { type: 'button', class: 'pequeno', id: 'lay-novo' }, t('layout.acrescentar'));
    btNovo.addEventListener('click', () => this.acrescentarElemento(this.selNovo.value));
    r.append(h('div', { class: 'lay-bloco' }, h('h3', {}, t('layout.elementos')), this.listaElementos, h('div', { class: 'linha' }, this.selNovo, btNovo)));
    this.estadoDoc = h('plat-estado', { id: 'lay-doc-estado' });
    r.append(this.estadoDoc);
    // saída
    this.selFormato = h('select', { id: 'lay-formato', class: 'controle' }, ...['pdf', 'png', 'jpg', 'svg'].map((f) => h('option', { value: f }, f.toUpperCase())));
    this.inDpi = h('input', { type: 'number', id: 'lay-dpi', class: 'controle', min: '72', max: '300', step: '1', value: '150' });
    this.chkQuadros = h('input', { type: 'checkbox', id: 'lay-previa-quadros' });
    const btPrevia = h('button', { type: 'button', class: 'pequeno', id: 'lay-previa' }, t('layout.previa'));
    btPrevia.addEventListener('click', () => this.previa());
    const btExportar = h('button', { type: 'button', class: 'primario', id: 'lay-exportar' }, t('layout.exportar'));
    btExportar.addEventListener('click', () => this.exportar());
    const btSalvar = h('button', { type: 'button', class: 'pequeno', id: 'lay-salvar' }, t('layout.salvar'));
    btSalvar.addEventListener('click', () => this.salvar(false));
    const btModelo = h('button', { type: 'button', class: 'pequeno', id: 'lay-salvar-modelo' }, t('layout.salvar_modelo'));
    btModelo.addEventListener('click', () => this.salvar(true));
    r.append(h('div', { class: 'lay-bloco' }, h('h3', {}, t('layout.saida')),
      h('div', { class: 'linha' },
        h('div', { class: 'campo' }, h('label', { for: 'lay-formato' }, t('layout.formato')), this.selFormato),
        h('div', { class: 'campo' }, h('label', { for: 'lay-dpi' }, t('layout.dpi')), this.inDpi)),
      h('label', { class: 'caixa' }, this.chkQuadros, ' ', t('layout.previa_quadros')),
      h('div', { class: 'botoes' }, btPrevia, btExportar),
      h('div', { class: 'botoes' }, btSalvar, btModelo)));
    this.estadoSaida = h('plat-estado', { id: 'lay-saida-estado' });
    this.estadoSaida.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.exportar(); });
    this.imgPrevia = h('img', { id: 'lay-previa-img', class: 'lay-previa', alt: t('layout.previa_alt'), hidden: true });
    this.saida = h('div', { id: 'lay-saida', class: 'lay-saida', 'aria-live': 'polite' });
    r.append(this.estadoSaida, this.imgPrevia, this.saida);
    r.append(h('p', { class: 'ajuda' }, t('layout.nota')));
    this.carregarModelos();
  }

  /* ---------------------------------------------------------------- modelos e itens */
  async carregarModelos() {
    this.estado.carregando(t('layout.carregando'));
    const [rm, ri] = await Promise.all([obter('/api/layouts/modelos'), obter('/api/itens?tipo=layout&limite=100')]);
    if (rm.status !== 200) { this.estado.erro(rm, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]); return; }
    this.estado.limpar();
    this.modelos = rm.json;
    limpar(this.selModelo);
    this.selModelo.append(h('option', { value: '' }, t('layout.escolha_modelo')));
    for (const m of rm.json.padrao) this.selModelo.append(h('option', { value: m.id }, `${m.nome} (${t('layout.padrao')})`));
    for (const m of rm.json.inquilino) this.selModelo.append(h('option', { value: m.id }, `${m.nome} (${t('layout.do_inquilino')})`));
    limpar(this.selExistente);
    this.selExistente.append(h('option', { value: '' }, t('layout.escolha_existente')));
    const itens = ri.status === 200 ? (ri.json.itens || []) : [];
    for (const it of itens) this.selExistente.append(h('option', { value: it.id }, it.titulo));
    this.selExistente.disabled = !itens.length;
    if (!this.doc) this.estadoDoc.vazio(t('layout.sem_documento'));
  }

  async aplicarModelo(id) {
    if (!id) return;
    const r = await obter(`/api/layouts/modelos/${encodeURIComponent(id)}`);
    if (r.status !== 200) { this.estado.erro(r, []); return; }
    const doc = r.json;
    doc.modelo = false;
    doc.nome = doc.nome || id;
    this.itemId = null;
    this._definirDoc(doc);
  }

  async abrirItem(id) {
    const r = await obter(`/api/itens/${encodeURIComponent(id)}`);
    if (r.status !== 200) { this.estado.erro(r, []); return; }
    if (r.json.tipo !== 'layout') { this.estado.erro(t('layout.nao_e_layout'), []); return; }
    const doc = { ...(r.json.dados || {}), nome: r.json.titulo };
    this.itemId = id;
    this.selModelo.value = '';
    this._definirDoc(doc);
  }

  _definirDoc(doc) {
    this.doc = doc;
    this.inNome.value = doc.nome || '';
    this.selPapel.value = doc.papel || 'A4';
    this.selOrientacao.value = doc.orientacao || 'retrato';
    this.estadoDoc.limpar();
    this._desenharElementos();
    this.imgPrevia.hidden = true;
    limpar(this.saida);
  }

  _lerCabecalho() {
    if (!this.doc) return;
    this.doc.nome = this.inNome.value.trim();
    this.doc.papel = this.selPapel.value;
    this.doc.orientacao = this.selOrientacao.value;
  }

  /* ---------------------------------------------------------------- elementos por formulário */
  _desenharElementos() {
    limpar(this.listaElementos);
    if (!this.doc) return;
    const els = this.doc.elementos || [];
    if (!els.length) this.estadoDoc.vazio(t('layout.sem_elementos'));
    els.forEach((el, i) => {
      const li = h('li', { class: 'lay-elemento', dataset: { elemento: String(i), tipo: el.tipo } });
      const btRemover = h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('layout.remover_elemento', { n: i + 1 }), dataset: { remover: String(i) } }, '×');
      btRemover.addEventListener('click', () => { this.doc.elementos.splice(i, 1); this._desenharElementos(); });
      li.append(h('div', { class: 'lay-elemento-topo' }, h('strong', {}, t(`layout.tipo_${el.tipo}`)), h('code', { class: 'mono' }, el.id || `${el.tipo}-${i + 1}`), btRemover));
      const linha = h('div', { class: 'linha' });
      if (el.tipo !== 'grade') {
        for (const c of CAMPOS_GEOMETRIA) {
          const inp = h('input', { type: 'number', class: 'controle curto', step: 'any', min: '0', value: String(el[c] ?? 0), 'aria-label': `${t(`layout.campo_${c}`)} ${i + 1}`, dataset: { campo: c } });
          inp.addEventListener('input', () => { el[c] = Number(inp.value); });
          linha.append(h('label', { class: 'lay-mini' }, t(`layout.campo_${c}`), inp));
        }
      }
      li.append(linha);
      li.append(this._propriedades(el, i));
      this.listaElementos.append(li);
    });
  }

  _propriedades(el, i) {
    const caixa = h('div', { class: 'linha lay-props' });
    const texto = (chave, rotulo, attrs = {}) => {
      const inp = h('input', { type: attrs.tipo || 'text', class: 'controle', value: el[chave] ?? '', 'aria-label': `${rotulo} ${i + 1}`, ...attrs.extra });
      inp.addEventListener('input', () => { el[chave] = attrs.tipo === 'number' ? Number(inp.value) : inp.value; });
      return h('label', { class: 'lay-mini' }, rotulo, inp);
    };
    const escolha = (chave, rotulo, opcoes, padrao) => {
      const sel = h('select', { class: 'controle', 'aria-label': `${rotulo} ${i + 1}` }, ...opcoes.map(([v, rot]) => h('option', { value: v }, rot)));
      sel.value = el[chave] ?? padrao;
      sel.addEventListener('change', () => { el[chave] = sel.value; this._desenharElementos(); });
      return h('label', { class: 'lay-mini' }, rotulo, sel);
    };
    switch (el.tipo) {
      case 'mapa':
        caixa.append(escolha('modo', t('layout.modo'), [['extensao', t('layout.modo_extensao')], ['escala', t('layout.modo_escala')]], 'extensao'));
        if (el.modo === 'escala') {
          if (!el.centro) { const c = this.map.getCenter(); el.centro = [c.lng, c.lat]; }
          caixa.append(texto('escala', t('layout.escala_1n'), { tipo: 'number', extra: { min: '100', step: '1' } }));
        } else {
          caixa.append(h('span', { class: 'ajuda' }, t('layout.extensao_da_vista')));
        }
        caixa.append(texto('rotacao', t('layout.rotacao'), { tipo: 'number', extra: { min: '-180', max: '180', step: '1' } }));
        break;
      case 'legenda':
        caixa.append(texto('titulo', t('layout.titulo_legenda')));
        caixa.append(texto('colunas', t('layout.colunas'), { tipo: 'number', extra: { min: '1', max: '6', step: '1' } }));
        break;
      case 'escala':
        caixa.append(texto('divisoes', t('layout.divisoes'), { tipo: 'number', extra: { min: '1', max: '10', step: '1' } }));
        caixa.append(escolha('unidade', t('layout.unidade'), [['auto', t('layout.unidade_auto')], ['m', 'm'], ['km', 'km']], 'auto'));
        break;
      case 'norte':
        caixa.append(escolha('referencia', t('layout.referencia'), [['verdadeiro', t('layout.norte_verdadeiro')], ['grade', t('layout.norte_grade')]], 'verdadeiro'));
        break;
      case 'grade':
        caixa.append(escolha('crs', t('layout.crs'), [['utm', 'UTM (m)'], ['4326', t('layout.crs_geografica')]], 'utm'));
        caixa.append(texto('intervalo', t('layout.intervalo'), { tipo: 'number', extra: { min: '0', step: 'any' } }));
        break;
      case 'titulo': case 'texto':
        caixa.append(texto('texto', t('layout.texto'), { extra: { maxlength: '4000' } }));
        caixa.append(texto('tamanho_pt', t('layout.tamanho_pt'), { tipo: 'number', extra: { min: '4', max: '120', step: '1' } }));
        caixa.append(h('span', { class: 'ajuda' }, t('layout.expressoes')));
        break;
      case 'imagem':
        caixa.append(escolha('origem', t('layout.origem'), [['logo', t('layout.origem_logo')], ['sha256', 'sha256']], 'logo'));
        if (el.origem === 'sha256') caixa.append(texto('sha256', 'sha256'));
        break;
      case 'tabela':
        caixa.append(texto('selecao_id', t('layout.selecao_id')));
        caixa.append(texto('linhas_max', t('layout.linhas_max'), { tipo: 'number', extra: { min: '1', max: '200', step: '1' } }));
        break;
      case 'data':
        caixa.append(escolha('formato', t('layout.formato_data'), [['longa', t('layout.data_longa')], ['curta', t('layout.data_curta')]], 'longa'));
        break;
      default:
        break;
    }
    return caixa;
  }

  acrescentarElemento(tipo) {
    if (!this.doc) { this.estadoDoc.erro(t('layout.escolha_primeiro'), []); return; }
    const n = (this.doc.elementos || []).length + 1;
    const base = { tipo, id: `${tipo}-${n}`, x: 10, y: 10, w: 60, h: 20 };
    if (tipo === 'mapa') Object.assign(base, { modo: 'extensao', w: 150, h: 120 });
    if (tipo === 'grade') { delete base.x; delete base.y; delete base.w; delete base.h; base.crs = 'utm'; }
    if (tipo === 'titulo') Object.assign(base, { texto: '{titulo_mapa}', tamanho_pt: 18, h: 12 });
    if (tipo === 'texto') Object.assign(base, { texto: '{inquilino} · {data}', tamanho_pt: 10, h: 8 });
    if (tipo === 'norte') Object.assign(base, { w: 15, h: 20, referencia: 'verdadeiro' });
    if (tipo === 'escala') Object.assign(base, { w: 70, h: 12, divisoes: 4, unidade: 'auto' });
    if (tipo === 'legenda') Object.assign(base, { w: 60, h: 80, colunas: 1, titulo: t('layout.titulo_legenda_padrao') });
    if (tipo === 'atribuicao') Object.assign(base, { h: 5 });
    if (tipo === 'data') Object.assign(base, { h: 6, formato: 'longa' });
    if (tipo === 'tabela') Object.assign(base, { w: 120, h: 60, linhas_max: 20 });
    if (tipo === 'imagem') Object.assign(base, { w: 40, h: 15, origem: 'logo' });
    (this.doc.elementos ||= []).push(base);
    this._desenharElementos();
    this.listaElementos.lastElementChild?.querySelector('input, select')?.focus();
  }

  /* ---------------------------------------------------------------- mapa da tela */
  mapaAtual() {
    const b = this.map.getBounds();
    const c = this.map.getCenter();
    return {
      titulo: (this.doc && this.doc.nome) || t('layout.mapa_padrao'),
      camadas: this.catalogo.ativas.map((id) => ({ camada_id: id, opacidade: this.catalogo.opacidade.get(id) ?? 1, visivel: true })),
      base: this.baseAtual(),
      extensao: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
      centro: [c.lng, c.lat],
      zoom: this.map.getZoom(),
    };
  }

  _erroDoc(r) {
    const j = r.json || {};
    const campo = j.detalhe && j.detalhe.campo;
    this.raiz.querySelectorAll('.lay-elemento').forEach((li) => li.classList.remove('invalido'));
    if (campo) {
      const m = /^elementos\[(\d+)\]/.exec(campo);
      if (m) this.raiz.querySelector(`.lay-elemento[data-elemento='${m[1]}']`)?.classList.add('invalido');
    }
    this.estadoDoc.erro(campo ? t('layout.erro_campo', { campo, mensagem: mensagemDe(r) }) : mensagemDe(r), []);
  }

  async previa() {
    if (!this.doc) { this.estadoDoc.erro(t('layout.escolha_primeiro'), []); return; }
    this._lerCabecalho();
    this.estadoSaida.carregando(t('layout.gerando_previa'));
    this.imgPrevia.hidden = true;
    const corpo = { layout: this.doc, mapa: this.mapaAtual(), dpi: 48, quadros: this.chkQuadros.checked };
    let resp;
    try {
      resp = await fetch('/api/layouts/previa', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', Accept: 'image/png' }, body: JSON.stringify(corpo) });
    } catch (e) {
      this.estadoSaida.erro({ status: 0, json: { mensagem: (e && e.message) || String(e) } }, []);
      return;
    }
    if (!resp.ok) {
      let json = null;
      try { json = await resp.json(); } catch { json = null; }
      const r = { status: resp.status, json: json || {} };
      if (resp.status === 422 && json && json.erro === 'layout_invalido') { this.estadoSaida.limpar(); this._erroDoc(r); return; }
      this.estadoSaida.erro(r, []);
      return;
    }
    const blob = await resp.blob();
    this.estadoSaida.limpar();
    this.estadoDoc.limpar();
    if (this.imgPrevia.src) URL.revokeObjectURL(this.imgPrevia.src);
    this.imgPrevia.src = URL.createObjectURL(blob);
    this.imgPrevia.hidden = false;
    const relatorio = resp.headers.get('X-Layout-Relatorio');
    if (relatorio) this._mostrarRelatorio(JSON.parse(relatorio));
  }

  _mostrarRelatorio(rel) {
    limpar(this.saida);
    const principal = rel.escala && Object.values(rel.escala)[0];
    if (principal) this.saida.append(h('p', { class: 'rotas-resumo' }, t('layout.escala_resultante', { escala: Math.round(principal.escala).toLocaleString('pt-BR') })));
    if (rel.resolucao_efetiva_dpi && rel.resolucao_efetiva_dpi < rel.dpi) this.saida.append(h('p', { class: 'ajuda' }, t('layout.resolucao_efetiva', { dpi: rel.resolucao_efetiva_dpi })));
    for (const a of rel.avisos || []) this.saida.append(h('p', { class: 'ajuda lay-aviso' }, a));
    const fora = (rel.elementos || []).filter((e) => e.estado === 'fora');
    for (const e of fora) this.saida.append(h('p', { class: 'ajuda lay-aviso' }, `${e.id}: ${e.nota}`));
  }

  async exportar() {
    if (!this.doc) { this.estadoDoc.erro(t('layout.escolha_primeiro'), []); return; }
    this._lerCabecalho();
    const dpi = Number(this.inDpi.value) || 150;
    if (dpi < 72 || dpi > 300) { this.estadoSaida.erro(t('layout.dpi_invalido'), []); this.inDpi.focus(); return; }
    this.estadoSaida.carregando(t('layout.enviando'));
    limpar(this.saida);
    const r = await enviar('/api/layouts/exportar', { layout: this.doc, mapa: this.mapaAtual(), formato: this.selFormato.value, dpi });
    if (r.status === 422 && r.json?.erro === 'layout_invalido') { this.estadoSaida.limpar(); this._erroDoc(r); return; }
    if (r.status !== 201) { this.estadoSaida.mostrar({ tipo: r.status === 403 ? 'negado' : 'erro', texto: mensagemDe(r), acoes: r.status >= 500 || r.status === 0 ? [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] : [], ref: r.json?.req_id }); return; }
    if (this.job && !FINAIS.has(this.job.estado)) cancelarAssinatura(this.job.id, this._ouvinte);
    this.job = r.json.job;
    this.estadoSaida.carregando(t('layout.na_fila', { formato: this.selFormato.value.toUpperCase() }));
    this.saida.append(h('p', { class: 'ajuda' }, h('a', { href: `/tarefas/${encodeURIComponent(this.job.id)}`, id: 'lay-tarefa' }, t('layout.ver_tarefa'))));
    assinar(this.job.id, this._ouvinte);
  }

  _evento(ev) {
    if (!this.job || ev.id !== this.job.id) return;
    if ((ev.tipo === 'estado' || ev.tipo === 'fim') && ev.dados) {
      this.job = ev.dados;
      const j = this.job;
      if (j.estado === 'rodando' || j.estado === 'pendente') this.estadoSaida.carregando(t('layout.progresso', { pct: j.progresso ?? 0, msg: j.mensagem || '' }));
      if (j.estado === 'concluido') {
        this.estadoSaida.limpar();
        const res = j.resultado || {};
        limpar(this.saida);
        this.saida.append(h('p', { class: 'rotas-resumo' },
          h('a', { href: res.url || '#', id: 'lay-link', download: res.nome_arquivo || '' }, t('layout.baixar', { nome: res.nome_arquivo || '', kb: Math.round((res.bytes || 0) / 1024) }))));
        if (res.relatorio) this._mostrarRelatorio({ ...res.relatorio, dpi: res.relatorio.dpi });
      } else if (j.estado === 'falhou' || j.estado === 'cancelado') {
        this.estadoSaida.erro(t('layout.falhou', { erro: j.erro || j.estado }), [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]);
      }
    }
  }

  async salvar(comoModelo) {
    if (!this.doc) { this.estadoDoc.erro(t('layout.escolha_primeiro'), []); return; }
    this._lerCabecalho();
    const dados = { ...this.doc, esquema_versao: 1, modelo: !!comoModelo, mapa_id: this.mapaId() || null };
    delete dados.nome;
    const titulo = this.doc.nome || t('layout.mapa_padrao');
    const r = this.itemId && !comoModelo
      ? await alterar(`/api/itens/${encodeURIComponent(this.itemId)}`, { titulo, dados })
      : await enviar('/api/itens', { tipo: 'layout', titulo: comoModelo ? `${titulo} (${t('layout.modelo_sufixo')})` : titulo, dados });
    if (r.status !== 200 && r.status !== 201) { this.estadoDoc.erro(r, []); return; }
    if (!comoModelo) this.itemId = r.json.id;
    this.estadoDoc.mostrar({ tipo: 'vazio', titulo: t(comoModelo ? 'layout.modelo_gravado' : 'layout.gravado'), texto: r.json.titulo || titulo });
    await this.carregarModelos();
    if (!comoModelo) this.selExistente.value = this.itemId;
  }
}
