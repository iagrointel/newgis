/* plat — base dos widgets (L5-06), com a ligação a VISTA do L5-07: `widget.vista` (objeto Vista do
   app/vistas.js) chega pelo motor quando `configuracao.vista` aponta para uma vista do documento; o widget
   ouve `vista_mudou` e repinta. `emitir(nome, detalhe)` publica no barramento de widgets do L5-06 (ligações
   simples) E no barramento de mensagens do L5-07 (`barramentoApp.disparar`), quando houver. As ações de dado
   (filtrar/selecionar/limpar_*) chegam ao widget já resolvidas na vista pelo barramento; aqui ficam as ações de
   widget (piscar, abrir, fechar, definir_parametro) com comportamento padrão. */
export class PlatWidget extends HTMLElement {
  #configuracao = {};
  #vista = null;
  #aoMudarVista = null;
  barramento = null;
  barramentoApp = null;
  noId = '';

  set configuracao(valor) {
    this.#configuracao = Object.freeze({ ...(valor || {}) });
    if (this.isConnected) this.renderizar();
  }

  get configuracao() { return this.#configuracao; }

  set vista(v) {
    if (this.#vista && this.#aoMudarVista) this.#vista.removeEventListener('vista_mudou', this.#aoMudarVista);
    this.#vista = v || null;
    if (this.#vista) {
      this.#aoMudarVista = () => { if (this.isConnected) this.renderizar(); };
      this.#vista.addEventListener('vista_mudou', this.#aoMudarVista);
    }
    if (this.isConnected) this.renderizar();
  }

  get vista() { return this.#vista; }

  emitir(nome, detalhe = {}) {
    const evento = { nome, origem: this.noId, detalhe };
    this.barramento?.publicar(evento);
    this.barramentoApp?.disparar(this.noId, nome, detalhe);
    this.dispatchEvent(new CustomEvent(nome, { detail: detalhe, bubbles: true, composed: true }));
  }

  executar(acao, detalhe = {}) {
    const metodo = this[`acao_${acao.replaceAll('.', '_')}`];
    if (typeof metodo !== 'function') throw new Error(`ação desconhecida em ${this.localName}: ${acao}`);
    metodo.call(this, detalhe);
  }

  /* ações de widget com comportamento padrão (o widget pode sobrescrever) */
  acao_piscar() {
    this.setAttribute('data-piscando', '1');
    clearTimeout(this._piscar);
    this._piscar = setTimeout(() => this.removeAttribute('data-piscando'), 1200);
  }

  acao_abrir() { this.hidden = false; this.setAttribute('data-aberto', '1'); }

  acao_fechar() { this.hidden = true; this.removeAttribute('data-aberto'); }

  acao_definir_parametro(detalhe) {
    if (!detalhe || typeof detalhe.nome !== 'string') return;
    this.dataset[`parametro${detalhe.nome.replace(/[^a-z0-9]/gi, '')}`] = String(detalhe.valor ?? '');
    this.configuracao = { ...this.configuracao, [detalhe.nome]: detalhe.valor };
  }

  /* item L5-01-e: botão "Ações" do usuário nos widgets de dado (o "Actions" do EXB): exportar as feições FILTRADAS
     da vista (CSV ou GeoJSON), ver na tabela (as tabelas da mesma fonte passam a mostrar só a seleção), zoom à
     seleção (os mapas da mesma fonte enquadram) e criar item no catálogo com a seleção (`POST /api/itens`, tipo
     `selecao` quando a instalação o tem — a resposta da API aparece nomeada, nunca um número cru). Não passa pelo
     barramento de mensagens: é ação de quem usa o app, não do documento. */
  montarAcoesUsuario() {
    if (!this.vista || this.configuracao?.acoes_usuario === false) return null;
    const menu = document.createElement('details');
    menu.className = 'widget-acoes';
    const resumo = document.createElement('summary'); resumo.textContent = 'Ações'; menu.append(resumo);
    const saida = document.createElement('p'); saida.className = 'widget-acoes-saida'; saida.setAttribute('aria-live', 'polite');
    const item = (rotulo, id, fn) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'pequeno'; b.dataset.acaoUsuario = id; b.textContent = rotulo;
      b.addEventListener('click', async () => {
        try { const msg = await fn(); if (msg) saida.textContent = msg; }
        catch (e) { saida.textContent = `${id}: ${e.message}`; saida.dataset.tipo = 'erro'; }
      });
      return b;
    };
    menu.append(
      item('Exportar CSV (filtradas)', 'exportar_csv', () => this.exportarRegistros('csv')),
      item('Exportar GeoJSON (filtradas)', 'exportar_geojson', () => this.exportarRegistros('geojson')),
      item('Ver na tabela', 'ver_na_tabela', () => this.verNaTabela()),
      item('Zoom à seleção', 'zoom_selecao', () => this.zoomSelecao()),
      item('Criar item com a seleção', 'criar_item', () => this.criarItemSelecao()),
      saida,
    );
    return menu;
  }

  #widgetsIrmaos(tipo) {
    const raiz = this.closest('.plat-widgets') || document;
    return [...raiz.querySelectorAll(`[data-tipo="${tipo}"]`)].filter((w) => w !== this && w.vista && w.vista.fonte === this.vista.fonte);
  }

  exportarRegistros(formato) {
    const regs = this.vista.registros();
    const campos = (this.vista.fonte.campos || []).filter((c) => c.tipo !== 'geometria').map((c) => c.nome);
    let conteudo; let tipo; let ext;
    if (formato === 'csv') {
      const esc = (v) => { const s = v === null || v === undefined ? '' : String(v); return /[";\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s; };
      conteudo = [campos.join(';'), ...regs.map((f) => campos.map((c) => esc(f.propriedades?.[c])).join(';'))].join('\n');
      tipo = 'text/csv;charset=utf-8'; ext = 'csv';
    } else {
      conteudo = JSON.stringify({ type: 'FeatureCollection', features: regs.map((f) => ({ type: 'Feature', id: f.id, properties: f.propriedades || {}, geometry: f.geometria || null })) });
      tipo = 'application/geo+json'; ext = 'geojson';
    }
    const nome = `${(this.vista.nome || 'vista').replace(/[^\w.-]+/g, '_')}.${ext}`;
    const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
    const a = document.createElement('a'); a.href = url; a.download = nome; a.hidden = true;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    this.dataset.exportadas = String(regs.length);
    return `${regs.length} registro(s) exportado(s) em ${nome}`;
  }

  verNaTabela() {
    const ids = [...this.vista.selecao];
    if (!ids.length) return 'nada selecionado';
    let n = 0;
    for (const t of this.#widgetsIrmaos('tabela')) { t.vista.definirFiltro({ op: 'in', args: [{ property: '__id' }, ids] }, this.noId); n += 1; }
    return n ? `${ids.length} registro(s) na(s) ${n} tabela(s)` : 'nenhuma tabela desta fonte no aplicativo';
  }

  zoomSelecao() {
    if (!this.vista.selecao.size) return 'nada selecionado';
    const regs = this.vista.selecionados();
    let n = 0;
    for (const m of [this, ...this.#widgetsIrmaos('mapa')].filter((w) => w.dataset.tipo === 'mapa')) { m.executar('zoom', { registros: regs, origem: this.noId }); n += 1; }
    return n ? `zoom em ${n} mapa(s)` : 'nenhum mapa desta fonte no aplicativo';
  }

  async criarItemSelecao() {
    const ids = [...this.vista.selecao];
    if (!ids.length) return 'nada selecionado';
    const fonte = this.vista.fonte;
    const corpo = { tipo: 'selecao', titulo: `Seleção de ${this.vista.nome || fonte.nome} (${ids.length})`,
      dados: { esquema_versao: 1, fonte: fonte.origem || {}, ids, filtro: this.vista.filtro || null, total: ids.length } };
    const r = await fetch('/api/itens', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    let json = null; try { json = await r.json(); } catch { json = null; }
    if (r.status !== 201) throw new Error(json?.erro ? `${json.erro}: ${json.mensagem || ''}` : `HTTP ${r.status}`);
    this.dataset.itemCriado = json.id;
    return `item criado: ${json.titulo || json.id}`;
  }

  connectedCallback() { this.renderizar(); }

  disconnectedCallback() { if (this.#vista && this.#aoMudarVista) this.#vista.removeEventListener('vista_mudou', this.#aoMudarVista); }

  renderizar() {}
}

export function definir(nome, classe) {
  if (!customElements.get(nome)) customElements.define(nome, classe);
}
