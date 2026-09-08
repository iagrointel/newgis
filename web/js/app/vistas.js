/* plat — vistas (item L5-07; D4): uma Vista é fonte + filtro CQL2-JSON + seleção + ordenação + campos.
   `registros()` aplica o filtro sobre as feições carregadas da fonte (todas em memória: o portão mede 10 mil),
   com cache invalidado só quando filtro/dado mudam; seleção é um Set de ids. Cada mudança emite `vista_mudou`,
   `filtro_mudou` ou `selecao_mudou` no EventTarget da vista — o barramento (barramento.js) reencaminha.
   Item L5-01-c: a mesma Vista atende os widgets de dado por uma API assíncrona única — `pagina()`, `total()`,
   `agregar()`, `histograma()`, `distintos()`, `exportar()`, `idsDoFiltro()` — que em fonte de memória roda
   aqui e em fonte de SERVIDOR (camada) delega ao FeatureServer com o filtro traduzido para `where`; o que volta
   do servidor entra no cache da fonte, e `registros()`/`selecionados()` continuam a valer sobre esse cache. */
import * as cql2 from './cql2.js';
import { cql2ParaWhere } from './consulta.js';
import { agregarEmMemoria, histogramaEmMemoria, paraCsv, paraGeoJson } from './agregacao.js';

export class Vista extends EventTarget {
  constructor(definicao, fonte) {
    super();
    this.id = definicao.id;
    this.nome = definicao.nome || definicao.id;
    this.fonte = fonte;
    this.campos = definicao.campos || null;
    this.ordenacao = definicao.ordenacao || [];
    this.#filtroBase = cql2.normalizar(definicao.filtro || null);
    this.#filtro = new Map();
    this.selecao = new Set(definicao.selecao || []);
    this.#cache = null;
    fonte.addEventListener('dado_adicionado', () => { this.#cache = null; this.#emitir('dado_adicionado', {}); });
    fonte.addEventListener('registros_carregados', () => { this.#cache = null; this.#emitir('registros_carregados', { total: fonte.feicoes.length }); });
  }

  #filtroBase; #filtro; #cache;

  /* filtro efetivo = filtro fixo da definição AND os filtros dinâmicos das ações, um por ORIGEM (item L5-01-c:
     o filtro de um widget de filtro e a seleção do mapa levada por mensagem se COMBINAM em vez de um apagar o
     outro — regra dos Dashboards; a mesma origem substitui o próprio filtro anterior) */
  get filtro() {
    const partes = [this.#filtroBase, ...this.#filtro.values()].filter(Boolean);
    if (!partes.length) return null;
    return partes.length === 1 ? partes[0] : { op: 'and', args: partes };
  }

  get filtroDinamico() {
    const partes = [...this.#filtro.values()].filter(Boolean);
    if (!partes.length) return null;
    return partes.length === 1 ? partes[0] : { op: 'and', args: partes };
  }

  definirFiltro(filtro, origem = null) {
    const chave = origem || '';
    const novo = cql2.normalizar(filtro);
    const atual = this.#filtro.get(chave) || null;
    if (JSON.stringify(novo) === JSON.stringify(atual)) return false;
    if (novo) this.#filtro.set(chave, novo); else this.#filtro.delete(chave);
    this.#cache = null;
    this.#emitir('filtro_mudou', { filtro: this.filtro, origem });
    return true;
  }

  /* sem origem limpa cada filtro dinâmico; com origem, só o daquela origem */
  limparFiltro(origem = null) {
    if (origem === null || origem === undefined) {
      if (!this.#filtro.size) return false;
      this.#filtro.clear(); this.#cache = null;
      this.#emitir('filtro_mudou', { filtro: this.filtro, origem: null });
      return true;
    }
    return this.definirFiltro(null, origem);
  }

  definirSelecao(ids, origem = null) {
    const nova = new Set(ids || []);
    if (nova.size === this.selecao.size && [...nova].every((i) => this.selecao.has(i))) return false;
    this.selecao = nova;
    this.#emitir('selecao_mudou', { ids: [...nova], origem });
    return true;
  }

  limparSelecao(origem = null) { return this.definirSelecao([], origem); }

  registros() {
    if (this.#cache) return this.#cache;
    const pred = cql2.predicado(this.filtro);
    let saida = this.fonte.feicoes.filter(pred);
    if (this.ordenacao.length) {
      const ord = this.ordenacao;
      saida = [...saida].sort((a, b) => {
        for (const o of ord) {
          const va = a.propriedades?.[o.campo]; const vb = b.propriedades?.[o.campo];
          if (va === vb) continue;
          if (va === null || va === undefined) return 1;
          if (vb === null || vb === undefined) return -1;
          const c = va < vb ? -1 : 1;
          return o.direcao === 'desc' ? -c : c;
        }
        return 0;
      });
    }
    this.#cache = saida;
    return saida;
  }

  selecionados() { return this.registros().filter((f) => this.selecao.has(f.id)); }

  valoresDe(campo, soSelecionados = false) {
    const base = soSelecionados ? this.selecionados() : this.registros();
    const vistos = new Set();
    for (const f of base) { const v = f.propriedades?.[campo]; if (v !== null && v !== undefined) vistos.add(v); }
    return [...vistos];
  }

  envelopeSelecao() {
    let env = null;
    for (const f of this.selecionados()) {
      const e = cql2.envelope(f.geometria);
      if (!e) continue;
      env = env ? [Math.min(env[0], e[0]), Math.min(env[1], e[1]), Math.max(env[2], e[2]), Math.max(env[3], e[3])] : e;
    }
    return env;
  }

  get servidor() { return this.fonte.modo === 'servidor'; }

  /* filtro efetivo traduzido para o FeatureServer ({where, geometria}); só faz sentido em fonte de servidor */
  filtroServidor(extra = null) {
    const f = extra ? (this.filtro ? { op: 'and', args: [this.filtro, extra] } : extra) : this.filtro;
    return cql2ParaWhere(f, { oid: this.fonte.oid });
  }

  #ordenar(lista, ordenacao) {
    if (!ordenacao || !ordenacao.length) return lista;
    return [...lista].sort((a, b) => {
      for (const o of ordenacao) {
        const va = a.propriedades?.[o.campo]; const vb = b.propriedades?.[o.campo];
        if (va === vb) continue;
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        const c = va < vb ? -1 : 1;
        return o.direcao === 'desc' ? -c : c;
      }
      return 0;
    });
  }

  /* página de registros: {registros, total, deslocamento, limite} */
  async pagina({ deslocamento = 0, limite = 50, ordenacao = null, campos = null } = {}) {
    const ord = ordenacao || this.ordenacao;
    if (!this.servidor) {
      const todos = this.#ordenar(this.registros(), ordenacao);
      return { registros: todos.slice(deslocamento, deslocamento + limite), total: todos.length, deslocamento, limite };
    }
    const filtro = this.filtroServidor();
    const [r, total] = await Promise.all([
      this.fonte.servidor.consultar(filtro, { ordenacao: ord, deslocamento, limite, campos: campos || this.campos, comGeometria: false }),
      this.total(),
    ]);
    this.fonte.lembrar(r.feicoes);
    return { registros: r.feicoes, total, deslocamento, limite };
  }

  async total() {
    if (!this.servidor) return this.registros().length;
    const chave = JSON.stringify(this.filtroServidor());
    if (this.#totalCache && this.#totalCache.chave === chave) return this.#totalCache.valor;
    const valor = await this.fonte.servidor.contar(this.filtroServidor());
    this.#totalCache = { chave, valor };
    return valor;
  }

  async agregar(opcoes) {
    if (!this.servidor) return agregarEmMemoria(this.registros(), opcoes);
    return this.fonte.servidor.estatisticas(this.filtroServidor(), opcoes);
  }

  async histograma(opcoes) {
    if (!this.servidor) return histogramaEmMemoria(this.registros(), opcoes);
    return this.fonte.servidor.histograma(this.filtroServidor(), opcoes);
  }

  /* valores únicos do campo SEM o filtro dinâmico (a lista de um filtro mostra todas as opções da fonte) */
  async distintos(campo, limite = 200) {
    if (!this.servidor) {
      const vistos = new Set();
      const pred = cql2.predicado(this.#filtroBase);
      for (const f of this.fonte.feicoes) { if (!pred(f)) continue; const v = f.propriedades?.[campo]; if (v !== null && v !== undefined) vistos.add(v); }
      return [...vistos].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)).slice(0, limite);
    }
    return this.fonte.servidor.distintos(cql2ParaWhere(this.#filtroBase, { oid: this.fonte.oid }), campo, limite);
  }

  /* ids que casam com um filtro CQL2 (seleção por atributo), respeitando o filtro da vista */
  async idsDoFiltro(filtro) {
    if (!this.servidor) { const pred = cql2.predicado(filtro); return this.registros().filter(pred).map((f) => f.id); }
    return this.fonte.servidor.ids(this.filtroServidor(filtro));
  }

  /* exportação com o filtro ativo: 'csv' -> texto; 'geojson' -> objeto */
  async exportar(formato = 'csv', colunas = null, { limite = undefined } = {}) {
    let feicoes;
    if (!this.servidor) feicoes = this.#ordenar(this.registros(), this.ordenacao);
    else feicoes = await this.fonte.servidor.todas(this.filtroServidor(), { ordenacao: this.ordenacao, comGeometria: formato === 'geojson', limite });
    if (formato === 'geojson') return paraGeoJson(feicoes);
    return paraCsv(feicoes.map((f) => ({ __id: f.id, ...f.propriedades })), colunas);
  }

  #totalCache = null;

  #emitir(nome, detalhe) {
    if (nome === 'filtro_mudou' || nome === 'dado_adicionado' || nome === 'registros_carregados') this.#totalCache = null;
    this.dispatchEvent(new CustomEvent(nome, { detail: { origem: this.id, ...detalhe } }));
    this.dispatchEvent(new CustomEvent('vista_mudou', { detail: { origem: this.id, causa: nome } }));
  }
}

export function criarVistas(corpo, fontes) {
  const vistas = new Map();
  for (const def of corpo.vistas || []) {
    const fonte = fontes.get(def.fonte);
    if (!fonte) continue;
    vistas.set(def.id, new Vista(def, fonte));
  }
  return vistas;
}
