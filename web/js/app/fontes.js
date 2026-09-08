/* plat — fontes do app (item L5-07; D4): uma Fonte é um item do catálogo (camada, tabela, arquivo GeoJSON,
   acervo) ou um caminho do próprio servidor, com os campos declarados no documento. `carregar()` traz as feições
   para a memória no formato interno {id, propriedades, geometria} (GeoJSON de entrada; a chave `__id` das
   propriedades é o id). Origem `item`: lê o item (`GET /api/itens/{id}`) e escolhe o caminho pelo tipo — arquivo
   GeoJSON (`dados.chave` -> `GET /api/arquivos/{sha256}?classe=...`), camada vetorial (OGC API Features
   `/ogc/collections/{id}/items`, quando o serviço existir nesta instalação) — sempre no mesmo domínio, nunca
   endereço de fora (regra do L0-11). Origem `embutida`: feições dentro do documento (dado pequeno digitado
   pelo autor, como o "static data" dos Dashboards). Eventos: `registros_carregados`, `dado_adicionado`. */

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
  }

  campo(nome) { return this.campos.find((c) => c.nome === nome) || null; }

  temGeometria() { return this.campos.some((c) => c.tipo === 'geometria'); }

  definirFeicoes(lista) {
    this.feicoes = lista.slice(0, LIMITE_FEICOES);
    this.carregada = true;
    this.dispatchEvent(new CustomEvent('registros_carregados', { detail: { origem: this.id, total: this.feicoes.length } }));
  }

  adicionar(lista) {
    if (!lista.length) return;
    this.feicoes = this.feicoes.concat(lista).slice(0, LIMITE_FEICOES);
    this.dispatchEvent(new CustomEvent('dado_adicionado', { detail: { origem: this.id, novos: lista.length } }));
  }

  async carregar(buscar = fetchLocal) {
    try {
      if (this.origem.tipo === 'embutida') { this.definirFeicoes(normalizarLista(this.origem.feicoes || [])); return this.feicoes; }
      if (this.origem.tipo === 'url') { this.definirFeicoes(normalizarLista(await buscar(this.origem.url))); return this.feicoes; }
      if (this.origem.tipo === 'item') {
        const item = await buscar(`/api/itens/${encodeURIComponent(this.origem.item_id)}`);
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
  if (tipo === 'camada_vetorial' || tipo === 'camada') {
    return buscar(`/ogc/collections/${encodeURIComponent(item.id)}/items?f=json&limit=${LIMITE_FEICOES}`);
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
