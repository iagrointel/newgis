/* plat — fontes do app (item L5-07; D4): uma Fonte é um item do catálogo (camada, tabela, arquivo GeoJSON,
   acervo) ou um caminho do próprio servidor, com os campos declarados no documento. `carregar()` traz as feições
   para a memória no formato interno {id, propriedades, geometria} (GeoJSON de entrada; a chave `__id` das
   propriedades é o id). Origem `item`: lê o item (`GET /api/itens/{id}`) e escolhe o caminho pelo tipo — arquivo
   GeoJSON (`dados.chave` -> `GET /api/arquivos/{sha256}?classe=...`) fica em memória; camada vetorial vira fonte
   de SERVIDOR (item L5-01-c, consulta.js): descreve a camada pelo FeatureServer, carrega só uma JANELA de
   feições com geometria (mapa) e deixa tabela, gráfico, filtro e exportação paginarem/agregarem no servidor;
   `feicoes` passa a ser o cache do que já foi visto (seleção e relações do barramento leem dali). Sempre no
   mesmo domínio, nunca endereço de fora (regra do L0-11). Origem `embutida`: feições dentro do documento (dado
   pequeno digitado pelo autor, como o "static data" dos Dashboards). Eventos: `registros_carregados`,
   `dado_adicionado`. */
import { FonteServidor, LIMITE_JANELA } from './consulta.js';

export const LIMITE_FEICOES = 100000;

export class Fonte extends EventTarget {
  constructor(definicao) {
    super();
    this.id = definicao.id;
    this.nome = definicao.nome || definicao.id;
    this.origem = definicao.origem || {};
    this.campos = definicao.campos || [];
    this.feicoes = [];
    this.carregada = false;
    this.erro = null;
    this.modo = 'memoria';      // 'memoria' | 'servidor'
    this.servidor = null;       // FonteServidor quando modo = servidor
    this.oid = '__id';
    this.total = null;          // total no servidor (sem filtro), quando conhecido
    this.#porId = new Map();
  }

  #porId;

  get camposDeclarados() { return this.campos.filter((c) => c.nome !== 'geometria'); }

  campo(nome) { return this.campos.find((c) => c.nome === nome) || null; }

  temGeometria() { return this.campos.some((c) => c.tipo === 'geometria'); }

  definirFeicoes(lista) {
    this.feicoes = lista.slice(0, LIMITE_FEICOES);
    this.#porId = new Map(this.feicoes.map((f) => [f.id, f]));
    this.carregada = true;
    this.dispatchEvent(new CustomEvent('registros_carregados', { detail: { origem: this.id, total: this.feicoes.length } }));
  }

  adicionar(lista) {
    if (!lista.length) return;
    this.feicoes = this.feicoes.concat(lista).slice(0, LIMITE_FEICOES);
    for (const f of lista) this.#porId.set(f.id, f);
    this.dispatchEvent(new CustomEvent('dado_adicionado', { detail: { origem: this.id, novos: lista.length } }));
  }

  porId(id) { return this.#porId.get(id) || null; }

  /* fonte de servidor: guarda no cache o que uma página/agregação trouxe (sem emitir evento de dado) */
  lembrar(lista) {
    if (this.modo !== 'servidor') return;
    let novos = 0;
    for (const f of lista) {
      const atual = this.#porId.get(f.id);
      if (atual) { if (f.geometria && !atual.geometria) atual.geometria = f.geometria; Object.assign(atual.propriedades, f.propriedades); continue; }
      if (this.feicoes.length >= LIMITE_FEICOES) break;
      this.#porId.set(f.id, f); this.feicoes.push(f); novos += 1;
    }
    return novos;
  }

  async carregar(buscar = fetchLocal, transporte = undefined) {
    try {
      if (this.origem.tipo === 'embutida') { this.definirFeicoes(normalizarLista(this.origem.feicoes || [])); return this.feicoes; }
      if (this.origem.tipo === 'url') { this.definirFeicoes(normalizarLista(await buscar(this.origem.url))); return this.feicoes; }
      if (this.origem.tipo === 'item') {
        const item = await buscar(`/api/itens/${encodeURIComponent(this.origem.item_id)}`);
        if (item.tipo === 'camada_vetorial' || item.tipo === 'camada') return this.#carregarServidor(item, transporte);
        const dados = await lerDadosDoItem(item, buscar);
        this.definirFeicoes(normalizarLista(dados));
        return this.feicoes;
      }
      throw new Error(`origem de fonte desconhecida: ${this.origem.tipo}`);
    } catch (e) {
      this.erro = e.message;
      this.dispatchEvent(new CustomEvent('erro', { detail: { origem: this.id, mensagem: e.message } }));
      throw e;
    }
  }

  async #carregarServidor(item, transporte) {
    this.modo = 'servidor';
    this.servidor = new FonteServidor(item.id, transporte ? { transporte } : {});
    const campos = await this.servidor.descrever();
    this.oid = this.servidor.oid;
    if (!this.camposDeclarados.length) this.campos = campos;
    else if (this.servidor.geometria && !this.campos.some((c) => c.nome === 'geometria')) this.campos.push({ nome: 'geometria', tipo: 'geometria' });
    const [janela, total] = await Promise.all([
      this.servidor.consultar({ where: '1=1' }, { limite: LIMITE_JANELA, comGeometria: !!this.servidor.geometria }),
      this.servidor.contar({ where: '1=1' }),
    ]);
    this.total = total;
    this.feicoes = janela.feicoes;
    this.#porId = new Map(this.feicoes.map((f) => [f.id, f]));
    this.carregada = true;
    this.dispatchEvent(new CustomEvent('registros_carregados', { detail: { origem: this.id, total, janela: this.feicoes.length, servidor: true } }));
    return this.feicoes;
  }
}

async function fetchLocal(caminho) {
  if (!caminho.startsWith('/')) throw new Error('fonte só lê caminho do próprio servidor');
  const r = await fetch(caminho, { credentials: 'same-origin', headers: { Accept: 'application/geo+json, application/json' } });
  if (!r.ok) throw new Error(`${caminho}: HTTP ${r.status}`);
  return r.json();
}

async function lerDadosDoItem(item, buscar) {
  const tipo = item.tipo;
  if (tipo === 'arquivo') {
    const chave = item.dados?.chave || '';
    const partes = chave.split('/');
    const classe = partes.length >= 3 ? partes[1] : 'objeto';
    return buscar(`/api/arquivos/${item.dados.sha256}?classe=${encodeURIComponent(classe)}`);
  }
  throw new Error(`item do tipo ${tipo} não serve como fonte de feições`);
}

/* GeoJSON (FeatureCollection ou lista de Feature) ou lista de objetos planos -> formato interno */
export function normalizarLista(bruto) {
  const lista = Array.isArray(bruto) ? bruto : (bruto?.type === 'FeatureCollection' ? bruto.features : (bruto?.itens || bruto?.features || []));
  return lista.map((f, i) => {
    if (f && f.type === 'Feature') {
      const id = f.id ?? f.properties?.id ?? f.properties?.__id ?? i;
      return { id, propriedades: { ...(f.properties || {}), __id: id }, geometria: f.geometry || null };
    }
    if (f && typeof f === 'object' && 'propriedades' in f) return { id: f.id ?? i, propriedades: { ...(f.propriedades || {}), __id: f.id ?? i }, geometria: f.geometria || null };
    const id = f?.id ?? i;
    return { id, propriedades: { ...(f || {}), __id: id }, geometria: null };
  });
}

export function criarFontes(corpo) {
  const fontes = new Map();
  for (const def of corpo.fontes || []) fontes.set(def.id, new Fonte(def));
  return fontes;
}

/* campos deduzidos de uma amostra (o construtor usa para preencher `campos` ao ligar uma fonte) */
export function deduzirCampos(feicoes) {
  const tipos = new Map();
  const tipoDe = (v) => {
    if (typeof v === 'boolean') return 'booleano';
    if (typeof v === 'number') return Number.isInteger(v) ? 'inteiro' : 'decimal';
    if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) return 'data';
    if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(v)) return 'data_hora';
    return 'texto';
  };
  for (const f of feicoes.slice(0, 500)) {
    for (const [k, v] of Object.entries(f.propriedades || {})) {
      if (k === '__id' || v === null || v === undefined) continue;
      const t = tipoDe(v);
      const atual = tipos.get(k);
      if (!atual) tipos.set(k, t);
      else if (atual !== t) tipos.set(k, (atual === 'inteiro' && t === 'decimal') || (atual === 'decimal' && t === 'inteiro') ? 'decimal' : 'texto');
    }
  }
  const campos = [...tipos].map(([nome, tipo]) => ({ nome, tipo }));
  if (feicoes.some((f) => f.geometria)) campos.push({ nome: 'geometria', tipo: 'geometria' });
  return campos;
}
