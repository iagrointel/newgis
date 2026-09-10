/* plat — vistas em memória (item L5-07; D4): uma Vista é fonte + filtro CQL2-JSON + seleção + ordenação + campos.
   `registros()` aplica o filtro sobre as feições carregadas da fonte (todas em memória: o portão mede 10 mil),
   com cache invalidado só quando filtro/dado mudam; seleção é um Set de ids. Cada mudança emite `vista_mudou`,
   `filtro_mudou` ou `selecao_mudou` no EventTarget da vista — o barramento (barramento.js) reencaminha. */
import * as cql2 from './cql2.js';

export class Vista extends EventTarget {
  constructor(definicao, fonte) {
    super();
    this.id = definicao.id;
    this.nome = definicao.nome || definicao.id;
    this.fonte = fonte;
    this.campos = definicao.campos || null;
    this.ordenacao = definicao.ordenacao || [];
    this.#filtroBase = cql2.normalizar(definicao.filtro || null);
    this.#filtro = null;
    this.selecao = new Set(definicao.selecao || []);
    this.#cache = null;
    fonte.addEventListener('dado_adicionado', () => { this.#cache = null; this.#emitir('dado_adicionado', {}); });
    fonte.addEventListener('registros_carregados', () => { this.#cache = null; this.#emitir('registros_carregados', { total: fonte.feicoes.length }); });
  }

  #filtroBase; #filtro; #cache;

  /* filtro efetivo = filtro fixo da definição AND filtro dinâmico (das ações) */
  get filtro() {
    if (this.#filtroBase && this.#filtro) return { op: 'and', args: [this.#filtroBase, this.#filtro] };
    return this.#filtro || this.#filtroBase || null;
  }

  get filtroDinamico() { return this.#filtro; }

  definirFiltro(filtro, origem = null) {
    const novo = cql2.normalizar(filtro);
    if (JSON.stringify(novo) === JSON.stringify(this.#filtro)) return false;
    this.#filtro = novo;
    this.#cache = null;
    this.#emitir('filtro_mudou', { filtro: this.filtro, origem });
    return true;
  }

  limparFiltro(origem = null) { return this.definirFiltro(null, origem); }

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

  #emitir(nome, detalhe) {
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
