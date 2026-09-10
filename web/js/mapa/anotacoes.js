/* plat · mapa — painel de anotações de feição (item L2-01-k-desenho-anotacoes; controles e estados por UX-23).
   Clique numa feição (modo "anotar" ligado) abre a lista de comentários dessa (camada, fid) e o formulário para
   acrescentar um novo, sempre em texto puro (h()/textContent — nunca innerHTML, a regra de web/js/base/dom.js).
   Backend: app/mapa/anotacoes.py — GET/POST /api/anotacoes, PATCH /api/anotacoes/{id} (texto só pelo autor;
   resolvido por quem vê), DELETE /api/anotacoes/{id} (só o autor). Visibilidade por grupo (RLS).
   Estados no próprio painel (<plat-estado>): sem alvo, carregando, vazio, erro com referência, sem grupo. */
import { apagar, enviar, mensagemDe, obter, remendar } from '../base/api.js';
import { confirmar } from '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { loja } from '../base/estado.js';
import { t } from '../base/i18n.js';

export class PainelAnotacoes {
  constructor(map, catalogo, els) {
    this.map = map;
    this.catalogo = catalogo;
    this.els = els; // {btnModo, corpo, alvo, lista, selGrupo, campoTexto, btnEnviar, estado, aviso}
    this.modo = false;
    this.alvo = null; // {camadaId, fid}
    this.anotacoes = [];
    this.editando = null; // id da anotação em edição de texto
    this._grupos = null;

    els.btnModo.addEventListener('click', () => this.alternarModo());
    els.btnEnviar.addEventListener('click', () => this._enviar());
    els.campoTexto.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) this._enviar(); });
    els.estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this._recarregar(); });
    this._clique = (ev) => this._aoClicar(ev);
    els.estado.vazio(t('mapa.anotacao_sem_alvo'));
  }

  alternarModo(forcar) {
    this.modo = forcar !== undefined ? forcar : !this.modo;
    this.els.btnModo.setAttribute('aria-pressed', this.modo ? 'true' : 'false');
    if (this.modo) this.map.on('click', this._clique);
    else this.map.off('click', this._clique);
  }

  async _garantirGrupos() {
    if (this._grupos) return this._grupos;
    const r = await obter('/api/grupos?limite=200');
    this._grupos = r.status === 200 ? (r.json.itens || []) : [];
    limpar(this.els.selGrupo);
    for (const g of this._grupos) this.els.selGrupo.append(h('option', { value: g.id }, g.nome));
    this.els.selGrupo.disabled = !this._grupos.length;
    this.els.btnEnviar.disabled = !this._grupos.length;
    return this._grupos;
  }

  async _aoClicar(ev) {
    const camadas = this.catalogo.ativas.flatMap((id) => this.catalogo.idsDeEstilo(id)).filter((idc) => this.map.getLayer(idc));
    if (!camadas.length) return;
    const feicoes = this.map.queryRenderedFeatures(ev.point, { layers: camadas });
    if (!feicoes.length) return;
    const f = feicoes[0];
    const camadaId = (f.layer && f.layer.source || '').replace(/^plat-/, '');
    const fid = String(f.id ?? (f.properties && f.properties.fid) ?? '');
    if (!camadaId || !fid) return;
    await this.abrir(camadaId, fid);
  }

  async abrir(camadaId, fid) {
    this.alvo = { camadaId, fid };
    this.editando = null;
    this.els.corpo.hidden = false;
    const ficha = this.catalogo.ficha(camadaId);
    this.els.alvo.textContent = t('mapa.anotacao_alvo', { camada: (ficha && ficha.titulo) || camadaId, fid });
    await this._garantirGrupos();
    if (!this._grupos.length) this.els.aviso.mostrar(t('mapa.anotacao_sem_grupo'), 'atencao');
    else this.els.aviso.limpar();
    await this._recarregar();
  }

  async _recarregar() {
    if (!this.alvo) return;
    this.els.estado.carregando(t('mapa.anotacao_carregando'));
    this.els.lista.hidden = true;
    const r = await obter(`/api/anotacoes?camada_id=${encodeURIComponent(this.alvo.camadaId)}&fid=${encodeURIComponent(this.alvo.fid)}`);
    limpar(this.els.lista);
    if (r.status !== 200) { this.els.estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]); return; }
    this.anotacoes = r.json.anotacoes || [];
    if (!this.anotacoes.length) { this.els.estado.vazio(t('mapa.anotacao_vazio')); return; }
    this.els.estado.limpar();
    this.els.lista.hidden = false;
    const eu = (loja.ler('usuario') || {}).id;
    for (const a of this.anotacoes) this.els.lista.append(this._linha(a, a.autor_id === eu));
  }

  _linha(a, minha) {
    const editando = this.editando === a.id;
    const cabecalho = h('div', { class: 'anotacao-cabecalho' },
      h('strong', {}, a.autor_nome), ' · ',
      h('time', { datetime: a.criado_em }, new Date(a.criado_em).toLocaleString('pt-BR')),
      a.editado_em ? h('span', { class: 'ajuda' }, ` · ${t('mapa.anotacao_editada')}`) : null,
      a.resolvido ? h('span', { class: 'marcador ok' }, t('mapa.anotacao_resolvida')) : null);
    const corpo = editando
      ? h('textarea', { class: 'anotacao-editor', maxlength: '4000', rows: '3', 'aria-label': t('mapa.anotacao_editar_texto'), value: a.texto })
      : h('p', {}, a.texto); // textContent — nunca HTML do usuário
    if (editando) corpo.value = a.texto;
    const botoes = h('div', { class: 'botoes anotacao-acoes' });
    const btResolver = h('button', { type: 'button', class: 'botao-mini', dataset: { acao: 'resolver' } }, t(a.resolvido ? 'mapa.anotacao_reabrir' : 'mapa.anotacao_resolver'));
    btResolver.addEventListener('click', () => this._alterar(a, { resolvido: !a.resolvido }));
    botoes.append(btResolver);
    if (minha && !editando) {
      const btEditar = h('button', { type: 'button', class: 'botao-mini', dataset: { acao: 'editar' } }, t('acao.editar'));
      btEditar.addEventListener('click', () => { this.editando = a.id; this._redesenhar(); this.els.lista.querySelector('textarea')?.focus(); });
      const btApagar = h('button', { type: 'button', class: 'botao-mini perigo', dataset: { acao: 'apagar' } }, t('acao.apagar'));
      btApagar.addEventListener('click', () => this._apagar(a));
      botoes.append(btEditar, btApagar);
    }
    if (editando) {
      const btGravar = h('button', { type: 'button', class: 'botao-mini primario', dataset: { acao: 'gravar' } }, t('acao.salvar'));
      btGravar.addEventListener('click', () => this._alterar(a, { texto: corpo.value.trim() }));
      const btCancelar = h('button', { type: 'button', class: 'botao-mini', dataset: { acao: 'cancelar' } }, t('acao.cancelar'));
      btCancelar.addEventListener('click', () => { this.editando = null; this._redesenhar(); });
      botoes.append(btGravar, btCancelar);
    }
    return h('li', { class: 'anotacao-item', dataset: { anotacao: a.id, resolvido: a.resolvido ? '1' : '0', minha: minha ? '1' : '0' } }, cabecalho, corpo, botoes);
  }

  _redesenhar() {
    limpar(this.els.lista);
    const eu = (loja.ler('usuario') || {}).id;
    for (const a of this.anotacoes) this.els.lista.append(this._linha(a, a.autor_id === eu));
  }

  async _alterar(a, mudanca) {
    if (mudanca.texto !== undefined && !mudanca.texto) { this.els.aviso.mostrar(t('mapa.anotacao_texto_vazio'), 'erro'); return; }
    this.els.aviso.limpar();
    const r = await remendar(`/api/anotacoes/${encodeURIComponent(a.id)}`, mudanca);
    if (r.status !== 200) { this.els.aviso.mostrar(this._erro(r), 'erro'); return; }
    this.editando = null;
    await this._recarregar();
  }

  async _apagar(a) {
    if (!(await confirmar(t('acao.apagar'), t('mapa.anotacao_apagar_confirma'), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/anotacoes/${encodeURIComponent(a.id)}`);
    if (r.status !== 204) { this.els.aviso.mostrar(this._erro(r), 'erro'); return; }
    await this._recarregar();
  }

  async _enviar() {
    const texto = this.els.campoTexto.value.trim();
    const grupoId = this.els.selGrupo.value;
    if (!this.alvo) { this.els.aviso.mostrar(t('mapa.anotacao_sem_alvo'), 'atencao'); return; }
    if (!grupoId) { this.els.aviso.mostrar(t('mapa.anotacao_sem_grupo'), 'atencao'); return; }
    if (!texto) { this.els.aviso.mostrar(t('mapa.anotacao_texto_vazio'), 'erro'); this.els.campoTexto.focus(); return; }
    this.els.aviso.limpar();
    this.els.btnEnviar.disabled = true;
    const r = await enviar('/api/anotacoes', { camada_id: this.alvo.camadaId, fid: this.alvo.fid, grupo_id: grupoId, texto });
    this.els.btnEnviar.disabled = false;
    if (r.status !== 201) { this.els.aviso.mostrar(this._erro(r), 'erro'); return; }
    this.els.campoTexto.value = '';
    await this._recarregar();
  }

  _erro(r) {
    const j = r.json || {};
    if (r.status === 403) return t('mapa.anotacao_so_autor');
    if (r.status === 404) return t('mapa.anotacao_inexistente');
    return `${mensagemDe(r)}${j.req_id ? ` (${t('estado.ref', { ref: j.req_id })})` : ''}`;
  }
}
