/* plat · mapa — painel "Seleção" (item UX-23; backend L2-01-h em app/mapa/selecao.py). Três maneiras de
   escolher feições de UMA camada hospedada, todas efêmeras até o usuário mandar guardar:

     por atributo      condições campo · operador · valor combinadas com E/OU, traduzidas para CQL2-JSON
                       (o vocabulário que a lista branca da camada aceita) e enviadas a
                       POST /api/mapa/camadas/{id}/filtrar → contagem, ids (amostra) e o SQL equivalente;
     por geometria     uma feição do painel Desenho (polígono, retângulo, linha, ponto) com a relação
                       "intersecta" ou "a até X m", combinada com a seleção atual (nova, somar, subtrair,
                       interseccionar) → POST /api/mapa/camadas/{id}/selecionar;
     entre camadas     feições desta camada que intersectam / estão a X m das feições de OUTRA camada →
                       POST /api/mapa/selecao-espacial.

   O resultado vai para a tabela de atributos (que realça no mapa), pode virar filtro da camada no mapa
   (só as feições escolhidas ficam visíveis — filtro de ids, declarado "amostra" quando o servidor truncou)
   e pode ser guardado como item `selecao` do catálogo (POST /api/itens, sem rota nova). Erro do servidor
   (campo fora da lista branca, operador não permitido, camada sem tabela, relação inválida) aparece
   nomeado no painel com a referência; nunca 422 cru. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

const OPERADORES = ['=', '<>', '<', '<=', '>', '>=', 'like', 'in', 'isNull'];
const OP_CHAVE = { '=': 'igual', '<>': 'diferente', '<': 'menor', '<=': 'menor_igual', '>': 'maior', '>=': 'maior_igual', like: 'like', in: 'in', isNull: 'nulo' };
const SEM_VALOR = new Set(['isNull']);
const RE_NUMERO = /int|double|numeric|real|serial|decimal|float|money/i;
const RE_BOOL = /bool/i;
const LIMITE_CONDICOES = 8;

export class PainelSelecao {
  constructor(map, catalogo, desenho, tabela, raiz) {
    this.map = map;
    this.catalogo = catalogo;
    this.desenho = desenho;
    this.tabela = tabela;
    this.raiz = raiz;
    this.modo = 'atributo';
    this.condicoes = [];            // [{campo, op, valor}] — só o modelo; o DOM é redesenhado dele
    this.resultado = null;          // {camadaId, n, ids, truncado, criterio, sql}
    this.filtrosOriginais = new Map(); // id de camada de estilo -> filtro antes do nosso
    this.filtroAplicadoEm = null;   // id da camada do catálogo com filtro nosso no mapa
    this._valores = new Map();      // `${camada}:${campo}` -> valores únicos (datalist)
    this._montar();
    this.catalogo.aoMudar(() => this._camadas());
    this.desenho.aoMudar(() => this._desenhos());
  }

  /* ---------------------------------------------------------------- montagem */
  _montar() {
    const r = this.raiz;
    limpar(r);
    this.estado = h('plat-estado', { id: 'sel-estado' });
    this.estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') this.executar(); });
    this.selCamada = h('select', { id: 'sel-camada', class: 'controle' });
    this.selCamada.addEventListener('change', () => { this._valores.clear(); this._condicoes(); this._camadasB(); });
    r.append(h('div', { class: 'campo' }, h('label', { for: 'sel-camada' }, t('selecao.camada')), this.selCamada, h('span', { class: 'ajuda' }, t('selecao.camada_ajuda'))));
    // modos
    const modos = h('div', { class: 'rotas-modos', role: 'radiogroup', 'aria-label': t('selecao.modo') });
    for (const m of ['atributo', 'geometria', 'camadas']) {
      const b = h('button', { type: 'button', class: 'pequeno', role: 'radio', 'aria-checked': String(m === this.modo), dataset: { modo: m } }, t(`selecao.modo_${m}`));
      b.addEventListener('click', () => this._trocarModo(m));
      modos.append(b);
    }
    r.append(modos);
    // bloco atributo
    this.listaCondicoes = h('ol', { class: 'sel-condicoes', id: 'sel-condicoes', 'aria-label': t('selecao.condicoes') });
    this.selCombinador = h('select', { id: 'sel-combinador', class: 'controle' }, h('option', { value: 'and' }, t('selecao.e')), h('option', { value: 'or' }, t('selecao.ou')));
    const btMais = h('button', { type: 'button', class: 'pequeno', id: 'sel-mais' }, t('selecao.mais_condicao'));
    btMais.addEventListener('click', () => this._acrescentarCondicao());
    this.blocoAtributo = h('div', { class: 'rotas-bloco', id: 'sel-bloco-atributo' },
      this.listaCondicoes,
      h('div', { class: 'linha' }, btMais, h('label', { for: 'sel-combinador' }, t('selecao.combinar')), this.selCombinador));
    // bloco geometria
    this.selDesenho = h('select', { id: 'sel-desenho', class: 'controle' });
    this.selRelacao = h('select', { id: 'sel-relacao', class: 'controle' }, h('option', { value: 'intersects' }, t('selecao.intersecta')), h('option', { value: 'dwithin' }, t('selecao.a_ate')));
    this.selRelacao.addEventListener('change', () => this._distancia());
    this.inDistancia = h('input', { type: 'number', id: 'sel-distancia', class: 'controle', min: '0', step: 'any', value: '100' });
    this.selModoComb = h('select', { id: 'sel-modo-combinacao', class: 'controle' },
      ...['novo', 'somar', 'subtrair', 'interseccionar'].map((m) => h('option', { value: m }, t(`selecao.comb_${m}`))));
    this.blocoGeometria = h('div', { class: 'rotas-bloco', id: 'sel-bloco-geometria', hidden: true },
      h('div', { class: 'campo' }, h('label', { for: 'sel-desenho' }, t('selecao.desenho')), this.selDesenho, h('span', { class: 'ajuda' }, t('selecao.desenho_ajuda'))),
      h('div', { class: 'linha' },
        h('div', { class: 'campo' }, h('label', { for: 'sel-relacao' }, t('selecao.relacao')), this.selRelacao),
        h('div', { class: 'campo', id: 'sel-campo-distancia' }, h('label', { for: 'sel-distancia' }, t('selecao.distancia')), this.inDistancia)),
      h('div', { class: 'campo' }, h('label', { for: 'sel-modo-combinacao' }, t('selecao.combinacao')), this.selModoComb));
    // bloco entre camadas
    this.selCamadaB = h('select', { id: 'sel-camada-b', class: 'controle' });
    this.selRelacaoB = h('select', { id: 'sel-relacao-b', class: 'controle' }, h('option', { value: 'intersects' }, t('selecao.intersecta')), h('option', { value: 'dwithin' }, t('selecao.a_ate')));
    this.selRelacaoB.addEventListener('change', () => this._distancia());
    this.inDistanciaB = h('input', { type: 'number', id: 'sel-distancia-b', class: 'controle', min: '0', step: 'any', value: '100' });
    this.blocoCamadas = h('div', { class: 'rotas-bloco', id: 'sel-bloco-camadas', hidden: true },
      h('div', { class: 'campo' }, h('label', { for: 'sel-camada-b' }, t('selecao.camada_b')), this.selCamadaB),
      h('div', { class: 'linha' },
        h('div', { class: 'campo' }, h('label', { for: 'sel-relacao-b' }, t('selecao.relacao')), this.selRelacaoB),
        h('div', { class: 'campo', id: 'sel-campo-distancia-b' }, h('label', { for: 'sel-distancia-b' }, t('selecao.distancia')), this.inDistanciaB)));
    r.append(this.blocoAtributo, this.blocoGeometria, this.blocoCamadas);
    // ação e resultado
    this.btExecutar = h('button', { type: 'button', class: 'primario', id: 'sel-executar' }, t('selecao.executar'));
    this.btExecutar.addEventListener('click', () => this.executar());
    r.append(h('div', { class: 'botoes' }, this.btExecutar), this.estado);
    this.saida = h('div', { class: 'sel-resultado', id: 'sel-resultado', 'aria-live': 'polite', hidden: true });
    r.append(this.saida);
    r.append(h('p', { class: 'ajuda' }, t('selecao.nota')));
    this._camadas();
    if (!this.condicoes.length) this._acrescentarCondicao();
    this._desenhos();
    this._distancia();
  }

  _trocarModo(m) {
    this.modo = m;
    this.raiz.querySelectorAll('[data-modo]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.modo === m)));
    this.blocoAtributo.hidden = m !== 'atributo';
    this.blocoGeometria.hidden = m !== 'geometria';
    this.blocoCamadas.hidden = m !== 'camadas';
    this.estado.limpar();
  }

  _distancia() {
    this.raiz.querySelector('#sel-campo-distancia').hidden = this.selRelacao.value !== 'dwithin';
    this.raiz.querySelector('#sel-campo-distancia-b').hidden = this.selRelacaoB.value !== 'dwithin';
  }

  _hospedadas() { return this.catalogo.disponiveis.filter((f) => f.servivel); }
  _camadaAtual() { return this.catalogo.ficha(this.selCamada.value) || null; }

  _camadas() {
    const anterior = this.selCamada.value;
    limpar(this.selCamada);
    const ativas = this.catalogo.ativas.map((id) => this.catalogo.ficha(id)).filter((f) => f && f.servivel);
    for (const f of ativas) this.selCamada.append(h('option', { value: f.id }, f.titulo));
    if (anterior && ativas.some((f) => f.id === anterior)) this.selCamada.value = anterior;
    this.selCamada.disabled = !ativas.length;
    this.btExecutar.disabled = !ativas.length;
    if (!ativas.length) this.estado.vazio(t('selecao.sem_camada'));
    else if (this.estado.getAttribute('tipo') === 'vazio') this.estado.limpar();
    this._condicoes();
    this._camadasB();
  }

  _camadasB() {
    const anterior = this.selCamadaB.value;
    limpar(this.selCamadaB);
    for (const f of this._hospedadas().filter((f) => f.id !== this.selCamada.value)) this.selCamadaB.append(h('option', { value: f.id }, f.titulo));
    if (anterior) this.selCamadaB.value = anterior;
  }

  _desenhos() {
    const anterior = this.selDesenho.value;
    limpar(this.selDesenho);
    const lista = this.desenho.lista();
    lista.forEach((f, i) => this.selDesenho.append(h('option', { value: f.id }, `${i + 1} · ${f.properties.tipo_desenho}`)));
    if (anterior && lista.some((f) => f.id === anterior)) this.selDesenho.value = anterior;
    this.selDesenho.disabled = !lista.length;
  }

  /* ---------------------------------------------------------------- condições por atributo */
  _campos() {
    const f = this._camadaAtual();
    const campos = [{ nome: 'fid', tipo: 'bigint' }];
    for (const c of (f && f.campos) || []) if (c && c.nome && c.nome !== 'fid' && c.nome !== 'geom') campos.push({ nome: c.nome, tipo: c.tipo || 'text' });
    return campos;
  }

  _acrescentarCondicao() {
    if (this.condicoes.length >= LIMITE_CONDICOES) { this.estado.erro(t('selecao.condicoes_demais', { n: LIMITE_CONDICOES }), []); return; }
    const campos = this._campos();
    this.condicoes.push({ campo: campos[0].nome, op: '=', valor: '' });
    this._condicoes();
    const ultimo = this.listaCondicoes.lastElementChild;
    ultimo?.querySelector('select')?.focus();
  }

  _condicoes() {
    limpar(this.listaCondicoes);
    const campos = this._campos();
    const nomes = new Set(campos.map((c) => c.nome));
    this.condicoes.forEach((c, i) => {
      if (!nomes.has(c.campo)) c.campo = campos[0].nome;
      const selCampo = h('select', { class: 'controle', 'aria-label': t('selecao.campo_n', { n: i + 1 }), dataset: { condicao: String(i), parte: 'campo' } },
        ...campos.map((cc) => h('option', { value: cc.nome }, `${cc.nome} (${cc.tipo})`)));
      selCampo.value = c.campo;
      selCampo.addEventListener('change', () => { c.campo = selCampo.value; this._condicoes(); });
      const selOp = h('select', { class: 'controle', 'aria-label': t('selecao.operador_n', { n: i + 1 }), dataset: { condicao: String(i), parte: 'op' } },
        ...OPERADORES.map((op) => h('option', { value: op }, t(`selecao.op_${OP_CHAVE[op]}`))));
      selOp.value = c.op;
      selOp.addEventListener('change', () => { c.op = selOp.value; this._condicoes(); });
      const listaId = `sel-valores-${i}`;
      const inValor = h('input', { type: 'text', class: 'controle', autocomplete: 'off', list: listaId, value: c.valor, 'aria-label': t('selecao.valor_n', { n: i + 1 }), dataset: { condicao: String(i), parte: 'valor' } });
      inValor.hidden = SEM_VALOR.has(c.op);
      inValor.addEventListener('input', () => { c.valor = inValor.value; });
      inValor.addEventListener('focus', () => this._sugerirValores(c.campo, listaId));
      const datalist = h('datalist', { id: listaId });
      const btMenos = h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('selecao.remover_condicao', { n: i + 1 }), dataset: { remover: String(i) } }, '×');
      btMenos.addEventListener('click', () => { this.condicoes.splice(i, 1); this._condicoes(); });
      const ajuda = c.op === 'in' ? t('selecao.ajuda_in') : c.op === 'like' ? t('selecao.ajuda_like') : '';
      this.listaCondicoes.append(h('li', { class: 'sel-condicao', dataset: { condicao: String(i) } },
        h('div', { class: 'linha' }, selCampo, selOp, inValor, datalist, btMenos),
        ajuda ? h('span', { class: 'ajuda' }, ajuda) : null));
    });
  }

  async _sugerirValores(campo, listaId) {
    const cid = this.selCamada.value;
    if (!cid || campo === 'fid') return;
    const chave = `${cid}:${campo}`;
    if (!this._valores.has(chave)) {
      const r = await obter(`/api/mapa/camadas/${encodeURIComponent(cid)}/valores?campo=${encodeURIComponent(campo)}&limite=100`);
      this._valores.set(chave, r.status === 200 ? (r.json.valores || []) : []);
    }
    const dl = this.raiz.querySelector(`#${listaId}`);
    if (!dl) return;
    limpar(dl);
    for (const v of this._valores.get(chave)) dl.append(h('option', { value: String(v) }));
  }

  _tipoDoCampo(nome) { return (this._campos().find((c) => c.nome === nome) || {}).tipo || 'text'; }

  _literal(campo, texto) {
    const tipo = this._tipoDoCampo(campo);
    const s = String(texto).trim();
    if (RE_NUMERO.test(tipo)) { const n = Number(s); if (s === '' || Number.isNaN(n)) throw new Error(t('selecao.valor_numerico', { campo })); return n; }
    if (RE_BOOL.test(tipo)) { if (['true', 'sim', '1', 'verdadeiro'].includes(s.toLowerCase())) return true; if (['false', 'nao', 'não', '0', 'falso'].includes(s.toLowerCase())) return false; throw new Error(t('selecao.valor_booleano', { campo })); }
    return s;
  }

  /* condições → CQL2-JSON (validação local nomeada por condição; o servidor valida de novo pela lista branca) */
  criterioAtributo() {
    if (!this.condicoes.length) throw new Error(t('selecao.sem_condicao'));
    const nos = this.condicoes.map((c, i) => {
      const prop = { property: c.campo };
      if (c.op === 'isNull') return { op: 'isNull', args: [prop] };
      const bruto = String(c.valor ?? '').trim();
      if (!bruto) throw new Error(t('selecao.valor_vazio', { n: i + 1 }));
      if (c.op === 'in') return { op: 'in', args: [prop, bruto.split(',').map((v) => this._literal(c.campo, v))] };
      if (c.op === 'like') return { op: 'like', args: [prop, bruto.includes('%') || bruto.includes('_') ? bruto : `%${bruto}%`] };
      return { op: c.op, args: [prop, this._literal(c.campo, bruto)] };
    });
    return nos.length === 1 ? nos[0] : { op: this.selCombinador.value, args: nos };
  }

  /* ---------------------------------------------------------------- execução */
  async executar() {
    const f = this._camadaAtual();
    this.estado.limpar();
    if (!f) { this.estado.erro(t('selecao.sem_camada'), []); return; }
    // cada chamada com o seu caminho na mesma linha: é assim que docs/gerar_cobertura_ui.py liga rota → tela
    let chamada; let criterio;
    const cid = encodeURIComponent(f.id);
    try {
      if (this.modo === 'atributo') {
        const filtro = this.criterioAtributo();
        chamada = () => enviar(`/api/mapa/camadas/${cid}/filtrar`, { filtro });
        criterio = { tipo: 'atributo', modo: 'filtro', filtro };
      } else if (this.modo === 'geometria') {
        const feicao = this.desenho.lista().find((x) => x.id === this.selDesenho.value);
        if (!feicao) throw new Error(t('selecao.sem_desenho'));
        const relacao = this.selRelacao.value;
        const distancia = Number(this.inDistancia.value);
        if (relacao === 'dwithin' && !(distancia > 0)) throw new Error(t('selecao.distancia_invalida'));
        const modo = this.selModoComb.value;
        const atuais = modo === 'novo' ? [] : this._idsAtuais(f.id);
        const corpo = { geometria: feicao.geometry, relacao, modo, ids_atuais: atuais };
        if (relacao === 'dwithin') corpo.distancia_m = distancia;
        chamada = () => enviar(`/api/mapa/camadas/${cid}/selecionar`, corpo);
        // `modo` do critério segue o esquema do tipo `selecao` (retangulo/poligono/laco...); a combinação vai à parte
        const modoDesenho = { retangulo: 'retangulo', poligono: 'poligono', laco: 'laco' }[feicao.properties.tipo_desenho] || 'poligono';
        criterio = { tipo: 'geometria', modo: modoDesenho, combinacao: modo, relacao, distancia_m: corpo.distancia_m ?? null, geometria: feicao.geometry };
      } else {
        const b = this.selCamadaB.value;
        if (!b) throw new Error(t('selecao.sem_camada_b'));
        const relacao = this.selRelacaoB.value;
        const distancia = Number(this.inDistanciaB.value);
        if (relacao === 'dwithin' && !(distancia > 0)) throw new Error(t('selecao.distancia_invalida'));
        const corpo = { camada_a: f.id, camada_b: b, relacao };
        if (relacao === 'dwithin') corpo.distancia_m = distancia;
        chamada = () => enviar('/api/mapa/selecao-espacial', corpo);
        criterio = { tipo: 'camadas', modo: 'espacial', camada_b: b, relacao, distancia_m: corpo.distancia_m ?? null };
      }
    } catch (e) {
      this.estado.erro(e.message, []);
      return;
    }
    this.estado.carregando(t('selecao.calculando'));
    this.btExecutar.disabled = true;
    const r = await chamada();
    this.btExecutar.disabled = false;
    if (r.status !== 200) {
      this.saida.hidden = true;
      this.estado.mostrar({ tipo: r.status === 403 ? 'negado' : 'erro', texto: this._textoErro(r), acoes: r.status >= 500 || r.status === 0 ? [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] : [], ref: r.json?.req_id });
      return;
    }
    this.estado.limpar();
    this.resultado = { camadaId: f.id, titulo: f.titulo, n: r.json.n, ids: r.json.ids || [], truncado: !!r.json.truncado, criterio, sql: r.json.sql_equivalente || null };
    this._mostrarResultado();
  }

  _textoErro(r) {
    const j = r.json || {};
    const base = mensagemDe(r);
    if (j.erro === 'campo_nao_permitido' && j.detalhe?.campo) return t('selecao.erro_campo', { campo: j.detalhe.campo });
    if (j.erro === 'camada_sem_tabela') return t('selecao.erro_sem_tabela');
    if (j.erro === 'operador_nao_permitido') return t('selecao.erro_operador', { op: j.detalhe?.op ?? '' });
    return base;
  }

  _idsAtuais(camadaId) {
    if (this.resultado && this.resultado.camadaId === camadaId) return this.resultado.ids;
    if (this.tabela && this.tabela.estado.camadaId === camadaId) return [...this.tabela.estado.selecionados];
    return [];
  }

  _mostrarResultado() {
    const s = this.resultado;
    limpar(this.saida);
    this.saida.hidden = false;
    this.saida.append(h('p', { class: 'rotas-resumo sel-n' }, t('selecao.resultado', { n: s.n.toLocaleString('pt-BR'), camada: s.titulo })));
    if (s.truncado) this.saida.append(h('p', { class: 'ajuda sel-truncado' }, t('selecao.truncado', { amostra: s.ids.length.toLocaleString('pt-BR') })));
    if (s.sql) this.saida.append(h('details', {}, h('summary', {}, t('selecao.sql')), h('code', { class: 'sel-sql' }, s.sql)));
    const btTabela = h('button', { type: 'button', class: 'pequeno primario', id: 'sel-ver-tabela', disabled: !s.ids.length }, t('selecao.ver_tabela'));
    btTabela.addEventListener('click', () => this.verNaTabela());
    const btFiltrar = h('button', { type: 'button', class: 'pequeno', id: 'sel-filtrar-mapa', disabled: !s.ids.length }, t('selecao.filtrar_mapa'));
    btFiltrar.addEventListener('click', () => this.filtrarNoMapa());
    const btLimpar = h('button', { type: 'button', class: 'pequeno', id: 'sel-limpar-mapa', hidden: !this.filtroAplicadoEm }, t('selecao.limpar_filtro'));
    btLimpar.addEventListener('click', () => this.limparFiltroDoMapa());
    const btSalvar = h('button', { type: 'button', class: 'pequeno', id: 'sel-salvar', disabled: !s.ids.length }, t('selecao.salvar'));
    btSalvar.addEventListener('click', () => this.salvar());
    this.saida.append(h('div', { class: 'botoes' }, btTabela, btFiltrar, btLimpar, btSalvar));
    this.saida.append(h('p', { class: 'saida', id: 'sel-saida', 'aria-live': 'polite' }));
  }

  async verNaTabela() {
    const s = this.resultado;
    if (!s || !this.tabela) return;
    await this.tabela.selecionar(s.camadaId, s.ids);
  }

  /* filtro de ids nas camadas de estilo da camada (o tile traz o fid como id da feição e como propriedade) */
  filtrarNoMapa() {
    const s = this.resultado;
    if (!s) return;
    this.limparFiltroDoMapa();
    const ids = s.ids.map((v) => (typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : v));
    const meu = ['any', ['in', ['id'], ['literal', ids]], ['in', ['get', 'fid'], ['literal', ids]]];
    for (const idc of this.catalogo.idsDeEstilo(s.camadaId)) {
      if (!this.map.getLayer(idc)) continue;
      const original = this.map.getFilter(idc) || null;
      this.filtrosOriginais.set(idc, original);
      this.map.setFilter(idc, original ? ['all', original, meu] : meu);
    }
    this.filtroAplicadoEm = s.camadaId;
    const bt = this.saida.querySelector('#sel-limpar-mapa');
    if (bt) bt.hidden = false;
    this._saida(s.truncado ? t('selecao.filtro_aplicado_amostra', { n: ids.length.toLocaleString('pt-BR') }) : t('selecao.filtro_aplicado', { n: ids.length.toLocaleString('pt-BR') }));
  }

  limparFiltroDoMapa() {
    for (const [idc, original] of this.filtrosOriginais) if (this.map.getLayer(idc)) this.map.setFilter(idc, original);
    this.filtrosOriginais.clear();
    if (this.filtroAplicadoEm) this._saida(t('selecao.filtro_removido'));
    this.filtroAplicadoEm = null;
    const bt = this.saida.querySelector('#sel-limpar-mapa');
    if (bt) bt.hidden = true;
  }

  async salvar() {
    const s = this.resultado;
    if (!s) return;
    const titulo = `${t('selecao.titulo_item', { camada: s.titulo })} ${new Date().toLocaleString('pt-BR')}`;
    const r = await enviar('/api/itens', { tipo: 'selecao', titulo, dados: { camada_id: s.camadaId, ids: s.ids, criterio: s.criterio, contagem: s.n } });
    if (r.status !== 201) { this.estado.erro(r, []); return; }
    const p = this.saida.querySelector('#sel-saida');
    if (p) { limpar(p).append(t('selecao.salva'), ' ', h('a', { href: `/conteudo/${encodeURIComponent(r.json.id)}` }, r.json.titulo || titulo)); }
  }

  _saida(texto) {
    const p = this.saida.querySelector('#sel-saida');
    if (p) p.textContent = texto;
  }
}
