/* plat — fonte de CAMADA consultada no servidor (item L5-01-c). O documento do app fala em vista (fonte +
   filtro CQL2-JSON + seleção + ordenação); quando a fonte é uma camada vetorial do catálogo, o navegador NÃO
   carrega a camada inteira: pagina, ordena, conta, agrega e exporta pelo FeatureServer do L2-04
   (`/rest/services/{item}/FeatureServer/0/query`: where, orderByFields, resultOffset/resultRecordCount,
   outStatistics + groupByFieldsForStatistics, returnDistinctValues, returnCountOnly, returnIdsOnly, geometry).
   O filtro CQL2-JSON da vista é traduzido aqui para a cláusula `where` do FeatureServer (subconjunto que o
   analisador seguro do L2-04-b aceita: comparação, LIKE, IN, BETWEEN, IS [NOT] NULL, AND/OR/NOT, parênteses) e
   o predicado espacial `s_intersects` vira o parâmetro `geometry` (só no nível de AND: o protocolo não tem
   "OR espacial"). Valores entram sempre entre aspas simples dobradas ou como número — nunca texto cru — e o
   nome de campo só passa se for identificador simples; o servidor ainda valida tudo de novo (lista branca de
   colunas). Sessão do usuário (cookie) ou token de serviço, sempre mesmo domínio. */

export const LIMITE_PAGINA = 5000;      // MAX_RECORD_COUNT_TETO do motor de consulta
export const LIMITE_JANELA = 2000;      // feições com geometria carregadas de saída (mapa) por fonte de servidor
export const LIMITE_EXPORTACAO = 200000;
export const LIMITE_IDS_IN = 10000;

const IDENT = /^[a-z_][a-z0-9_]*$/i;

export class ErroWhere extends Error {
  constructor(codigo, mensagem) { super(mensagem); this.codigo = codigo; }
}

/* CQL2-JSON -> { where, geometria } ; `oid` é o nome do campo de id no servidor (fid) */
export function cql2ParaWhere(filtro, { oid = 'fid' } = {}) {
  if (!filtro) return { where: '1=1', geometria: null };
  const espaciais = [];
  const where = traduzir(filtro, oid, espaciais, true);
  if (espaciais.length > 1) throw new ErroWhere('espacial_multiplo', 'só um predicado espacial por consulta');
  return { where: where || '1=1', geometria: espaciais[0] || null };
}

function traduzir(no, oid, espaciais, topo) {
  if (!no || typeof no !== 'object' || typeof no.op !== 'string') throw new ErroWhere('filtro_invalido', 'nó CQL2 inválido');
  const op = no.op.toLowerCase();
  const args = no.args || [];
  if (op === 'and' || op === 'or') {
    const partes = args.map((a) => traduzir(a, oid, espaciais, topo && op === 'and')).filter(Boolean);
    if (!partes.length) return '';
    return partes.length === 1 ? partes[0] : `(${partes.join(op === 'and' ? ' AND ' : ' OR ')})`;
  }
  if (op === 'not') {
    const interno = traduzir(args[0], oid, espaciais, false);
    return interno ? `(NOT ${interno})` : '';
  }
  if (op === 's_intersects' || op === 's_within' || op === 's_contains') {
    if (!topo) throw new ErroWhere('espacial_fora_de_and', 'predicado espacial só pode entrar combinado por AND');
    const geom = args.find((a) => a && typeof a === 'object' && a.type);
    if (!geom) throw new ErroWhere('espacial_sem_geometria', 'predicado espacial sem geometria literal');
    espaciais.push({ geometria: geom, relacao: op });
    return '';
  }
  if (op === 'isnull') return `${campo(args[0], oid)} IS NULL`;
  if (op === 'like' || op === 'not like') return `${campo(args[0], oid)} ${op.toUpperCase()} ${literal(args[1])}`;
  if (op === 'in') {
    const lista = Array.isArray(args[1]) ? args[1] : [];
    if (!lista.length) return '1=0';
    if (lista.length > LIMITE_IDS_IN) throw new ErroWhere('in_grande_demais', `lista IN com ${lista.length} valores (teto ${LIMITE_IDS_IN})`);
    return `${campo(args[0], oid)} IN (${lista.map(literal).join(', ')})`;
  }
  if (op === 'between') return `${campo(args[0], oid)} BETWEEN ${literal(args[1])} AND ${literal(args[2])}`;
  if (['=', '<>', '!=', '<', '>', '<=', '>='].includes(op)) {
    const esq = args[0]; const dir = args[1];
    if (dir === null || dir === undefined) return op === '=' ? `${campo(esq, oid)} IS NULL` : `${campo(esq, oid)} IS NOT NULL`;
    return `${campo(esq, oid)} ${op === '!=' ? '<>' : op} ${literal(dir)}`;
  }
  throw new ErroWhere('operador_fora', `operador CQL2 sem tradução para where: ${no.op}`);
}

function campo(a, oid) {
  const nome = a && typeof a === 'object' ? a.property : a;
  if (typeof nome !== 'string') throw new ErroWhere('campo_invalido', 'comparação sem nome de campo');
  const real = nome === '__id' ? oid : nome;
  if (!IDENT.test(real) || real.length > 63) throw new ErroWhere('campo_invalido', `nome de campo inválido: ${nome}`);
  return real;
}

export function literal(v) {
  if (v === null || v === undefined) return 'NULL';
  if (typeof v === 'number') { if (!Number.isFinite(v)) throw new ErroWhere('valor_invalido', 'número não finito'); return String(v); }
  if (typeof v === 'boolean') return v ? '1' : '0';
  if (typeof v === 'object') {
    if (v.timestamp) return `'${String(v.timestamp).replaceAll("'", "''")}'`;
    if (v.date) return `'${String(v.date).replaceAll("'", "''")}'`;
    if (v.property !== undefined) throw new ErroWhere('valor_invalido', 'comparação entre dois campos não é aceita');
    throw new ErroWhere('valor_invalido', 'valor literal inválido');
  }
  return `'${String(v).replaceAll("'", "''")}'`;
}

/* GeoJSON -> geometria Esri + geometryType para o parâmetro `geometry` */
export function geometriaEsri(g) {
  const sr = { spatialReference: { wkid: 4326 } };
  if (!g) return null;
  if (g.type === 'Polygon') return { tipo: 'esriGeometryPolygon', geometria: { rings: g.coordinates, ...sr } };
  if (g.type === 'MultiPolygon') return { tipo: 'esriGeometryPolygon', geometria: { rings: g.coordinates.flat(), ...sr } };
  if (g.type === 'Point') return { tipo: 'esriGeometryPoint', geometria: { x: g.coordinates[0], y: g.coordinates[1], ...sr } };
  if (g.type === 'LineString') return { tipo: 'esriGeometryPolyline', geometria: { paths: [g.coordinates], ...sr } };
  if (g.type === 'Envelope' || (Array.isArray(g.bbox) && !g.coordinates)) {
    const b = g.bbox; return { tipo: 'esriGeometryEnvelope', geometria: { xmin: b[0], ymin: b[1], xmax: b[2], ymax: b[3], ...sr } };
  }
  throw new ErroWhere('geometria_fora', `geometria de filtro sem tradução: ${g.type}`);
}

const RELACAO_ESRI = { s_intersects: 'esriSpatialRelIntersects', s_within: 'esriSpatialRelWithin', s_contains: 'esriSpatialRelContains' };

const TIPO_DE_ESRI = {
  esriFieldTypeString: 'texto', esriFieldTypeGUID: 'texto', esriFieldTypeGlobalID: 'texto',
  esriFieldTypeInteger: 'inteiro', esriFieldTypeSmallInteger: 'inteiro', esriFieldTypeBigInteger: 'inteiro', esriFieldTypeOID: 'inteiro',
  esriFieldTypeDouble: 'decimal', esriFieldTypeSingle: 'decimal',
  esriFieldTypeDate: 'data_hora', esriFieldTypeDateOnly: 'data', esriFieldTypeTimeOnly: 'texto',
};

/* transporte padrão: fetch no mesmo domínio; POST de formulário (where longo não cabe na URL) */
export const transporteFetch = {
  async get(caminho) {
    const r = await fetch(caminho, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    return lerResposta(r, caminho);
  },
  async post(caminho, params) {
    const corpo = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) corpo.set(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
    const r = await fetch(caminho, { method: 'POST', credentials: 'same-origin', body: corpo,
      headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' } });
    return lerResposta(r, caminho);
  },
};

async function lerResposta(r, caminho) {
  let corpo = null;
  try { corpo = await r.json(); } catch { corpo = null; }
  if (!r.ok) {
    const msg = corpo?.mensagem || corpo?.error?.message || corpo?.erro || `HTTP ${r.status}`;
    const e = new Error(`${caminho}: ${msg}`); e.status = r.status; e.codigo = corpo?.erro || corpo?.error?.code; throw e;
  }
  if (corpo && corpo.error) { const e = new Error(corpo.error.message || 'erro do serviço'); e.codigo = corpo.error.code; throw e; }
  return corpo;
}

export class FonteServidor {
  constructor(itemId, { transporte = transporteFetch, camadaId = '0' } = {}) {
    this.itemId = itemId;
    this.base = `/rest/services/${encodeURIComponent(itemId)}/FeatureServer/${camadaId}`;
    this.transporte = transporte;
    this.oid = 'fid';
    this.campos = [];
    this.geometria = null;
    this.descritor = null;
    this.chamadas = [];
  }

  async descrever() {
    const d = await this.transporte.get(`${this.base}?f=json`);
    this.descritor = d;
    this.oid = d.objectIdField || 'fid';
    this.geometria = d.geometryType || null;
    this.campos = (d.fields || []).filter((f) => f.type !== 'esriFieldTypeGeometry' && f.name !== this.oid && f.name !== 'globalid')
      .map((f) => ({ nome: f.name, tipo: TIPO_DE_ESRI[f.type] || 'texto' }));
    if (this.geometria) this.campos.push({ nome: 'geometria', tipo: 'geometria' });
    return this.campos;
  }

  #camposData() { return new Set(this.campos.filter((c) => c.tipo === 'data' || c.tipo === 'data_hora').map((c) => c.nome)); }

  async #query(params) {
    const t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());
    const r = await this.transporte.post(`${this.base}/query`, { f: 'json', ...params });
    this.chamadas.push({ ms: (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0, params: Object.keys(params) });
    return r;
  }

  #base(filtro) {
    const p = { where: filtro?.where || '1=1' };
    if (filtro?.geometria) {
      const g = geometriaEsri(filtro.geometria.geometria);
      p.geometry = g.geometria; p.geometryType = g.tipo; p.inSR = 4326;
      p.spatialRel = RELACAO_ESRI[filtro.geometria.relacao] || 'esriSpatialRelIntersects';
    }
    return p;
  }

  /* página de feições no formato interno {id, propriedades, geometria} */
  async consultar(filtro, { ordenacao = [], deslocamento = 0, limite = 50, campos = null, comGeometria = false } = {}) {
    const p = { ...this.#base(filtro), outFields: campos && campos.length ? campos.join(',') : '*',
      returnGeometry: comGeometria ? 'true' : 'false', outSR: 4326,
      resultOffset: deslocamento, resultRecordCount: Math.min(limite, LIMITE_PAGINA), f: 'geojson' };
    if (ordenacao && ordenacao.length) p.orderByFields = ordenacao.map((o) => `${campoSeguro(o.campo, this.oid)} ${o.direcao === 'desc' ? 'DESC' : 'ASC'}`).join(',');
    const r = await this.#query(p);
    const datas = this.#camposData();
    const feicoes = (r.features || []).map((f) => {
      const props = { ...(f.properties || {}) };
      for (const k of datas) if (typeof props[k] === 'number') props[k] = new Date(props[k]).toISOString();
      const id = f.id ?? props[this.oid];
      delete props[this.oid];
      return { id, propriedades: { ...props, __id: id }, geometria: f.geometry || null };
    });
    return { feicoes, excedeu: feicoes.length >= Math.min(limite, LIMITE_PAGINA) };
  }

  async contar(filtro) { return Number((await this.#query({ ...this.#base(filtro), returnCountOnly: 'true' })).count || 0); }

  async ids(filtro) { return (await this.#query({ ...this.#base(filtro), returnIdsOnly: 'true' })).objectIds || []; }

  /* agregação no servidor: [{valor, n, medida, soma, minimo, maximo}] ordenado por medida desc */
  async estatisticas(filtro, { campo, agregacao = 'contagem', campo_valor = null, maximo = 20 }) {
    const specs = [{ statisticType: 'count', onStatisticField: '*', outStatisticFieldName: 'n' }];
    if (campo_valor) {
      for (const [tipo, nome] of [['sum', 'soma'], ['avg', 'media'], ['min', 'minimo'], ['max', 'maximo']]) specs.push({ statisticType: tipo, onStatisticField: campoSeguro(campo_valor, this.oid), outStatisticFieldName: nome });
    }
    const p = { ...this.#base(filtro), outStatistics: specs };
    if (campo) p.groupByFieldsForStatistics = campoSeguro(campo, this.oid);
    const r = await this.#query(p);
    const linhas = (r.features || []).map((f) => {
      const a = f.attributes || {};
      const g = { valor: campo ? (a[campo] ?? null) : null, n: Number(a.n || 0), soma: a.soma ?? null, media: a.media ?? null, minimo: a.minimo ?? null, maximo: a.maximo ?? null, ids: [] };
      g.medida = agregacao === 'soma' ? g.soma : agregacao === 'media' ? g.media : agregacao === 'minimo' ? g.minimo : agregacao === 'maximo' ? g.maximo : g.n;
      return g;
    });
    linhas.sort((x, y) => (y.medida ?? -Infinity) - (x.medida ?? -Infinity));
    return maximo ? linhas.slice(0, maximo) : linhas;
  }

  async minMax(filtro, campo) {
    const r = await this.#query({ ...this.#base(filtro), outStatistics: [
      { statisticType: 'min', onStatisticField: campoSeguro(campo, this.oid), outStatisticFieldName: 'minimo' },
      { statisticType: 'max', onStatisticField: campoSeguro(campo, this.oid), outStatisticFieldName: 'maximo' }] });
    const a = r.features?.[0]?.attributes || {};
    return { minimo: a.minimo ?? null, maximo: a.maximo ?? null };
  }

  /* contagem por faixa, cada faixa = uma contagem no servidor (agregação nunca no navegador) */
  async histograma(filtro, { campo, faixas = 10 }) {
    const { minimo, maximo } = await this.minMax(filtro, campo);
    if (minimo === null || maximo === null) return [];
    const largura = (maximo - minimo) / faixas || 1;
    const c = campoSeguro(campo, this.oid);
    const base = filtro?.where && filtro.where !== '1=1' ? `(${filtro.where}) AND ` : '';
    const lista = [];
    for (let i = 0; i < faixas; i += 1) {
      const de = minimo + i * largura; const ate = i === faixas - 1 ? maximo : minimo + (i + 1) * largura;
      const cond = i === faixas - 1 ? `${c} >= ${de} AND ${c} <= ${ate}` : `${c} >= ${de} AND ${c} < ${ate}`;
      lista.push({ de, ate, where: `${base}(${cond})` });
    }
    const ns = await Promise.all(lista.map((fx) => this.contar({ where: fx.where, geometria: filtro?.geometria || null })));
    return lista.map((fx, i) => ({ de: fx.de, ate: fx.ate, n: ns[i] }));
  }

  async distintos(filtro, campo, limite = 200) {
    const c = campoSeguro(campo, this.oid);
    // o servidor não ordena valores distintos (orderByFields é ignorado nesse modo): ordena aqui, lista curta
    const r = await this.#query({ ...this.#base(filtro), returnDistinctValues: 'true', outFields: c, returnGeometry: 'false', resultRecordCount: limite });
    return (r.features || []).map((f) => f.attributes?.[campo]).filter((v) => v !== null && v !== undefined).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  }

  /* todas as feições do filtro, em páginas de LIMITE_PAGINA, até LIMITE_EXPORTACAO */
  async todas(filtro, { ordenacao = [], campos = null, comGeometria = false, limite = LIMITE_EXPORTACAO } = {}) {
    const saida = [];
    for (let desloc = 0; desloc < limite; desloc += LIMITE_PAGINA) {
      const { feicoes, excedeu } = await this.consultar(filtro, { ordenacao, deslocamento: desloc, limite: Math.min(LIMITE_PAGINA, limite - desloc), campos, comGeometria });
      saida.push(...feicoes);
      if (!excedeu) break;
    }
    return saida;
  }

  p95() {
    const xs = this.chamadas.map((c) => c.ms).sort((a, b) => a - b);
    return xs.length ? xs[Math.min(xs.length - 1, Math.ceil(xs.length * 0.95) - 1)] : null;
  }
}

function campoSeguro(nome, oid) {
  const real = nome === '__id' ? oid : nome;
  if (typeof real !== 'string' || !IDENT.test(real)) throw new ErroWhere('campo_invalido', `nome de campo inválido: ${nome}`);
  return real;
}
