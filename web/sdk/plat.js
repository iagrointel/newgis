/* SDK JavaScript `plat` da plataforma SIG (item L7-08-c-sdk-js). Módulo ES sem dependência: só `fetch`.
   Mesmo modelo do SDK Python (sdk/python/src/plat/cliente.py): `new Plataforma(url, token)` ->
   `.itens` / `.camadas` / `.mapas` / `.jobs.esperar()` / `.tokens`, paginação por cursor e retentativa
   embutidas, erros como Problem Details (RFC 9457) traduzidos do contrato real da API
   (`{"erro","mensagem","detalhe","req_id"}`), e os ajudantes MapLibre em `.maplibre`
   (`fonte(item)`, `camada(item)`, `estilo(mapa)`, `transformRequest`, `enquadrar`).

   O que a API não tem, o SDK não finge: não existe rota de feições por camada nem de tiles dinâmicos hoje
   (FeatureServer real é o L2-04, parcial) — `fonte(item)` devolve o que EXISTE: a extensão do item como
   GeoJSON, o PMTiles quando o item aponta para um, e o catálogo OGC API Records como GeoJSON autenticado.

   Serve tanto no navegador (same-origin: a API não emite CORS; o exemplo roda em /static/sdk/exemplos/)
   quanto em Node >= 18 (os testes de unidade em tests/sdk_js/ rodam com `fetch` falso). Sem avaliação de
   texto como código, sem escrita de HTML por texto, sem script inline: os exemplos abrem com CSP estrita
   (refutação do item). */

const TENTATIVAS_PADRAO = 3;
const ESPERA_BASE_MS = 500;
// 429/502/503/504: taxa e indisponibilidade transitória — nunca 4xx de validação/permissão, que repetir não conserta
const STATUS_RETENTAVEIS = new Set([429, 502, 503, 504]);
const ESTADOS_TERMINAIS_JOB = new Set(['concluido', 'falhou', 'cancelado']);
const PREFIXO_TIPO_CAMADA = 'camada_';
export const VERSAO = '0.1.0';

export class ErroPlataforma extends Error {
  /** Uma resposta de erro da plataforma no vocabulário RFC 9457: status, tipo ("type"), titulo ("title"),
      detalhe ("detail"), instancia ("instance" = req_id, o mesmo de plat.log_acesso). */
  constructor({ status, tipo, titulo, detalhe = null, instancia = null, corpoBruto = null }) {
    super(`${status} ${tipo}: ${titulo}`);
    this.name = 'ErroPlataforma';
    this.status = status;
    this.tipo = tipo;
    this.titulo = titulo;
    this.detalhe = detalhe;
    this.instancia = instancia;
    this.corpoBruto = corpoBruto;
  }

  toProblemDetails() {
    const d = { status: this.status, type: this.tipo, title: this.titulo };
    if (this.detalhe != null) d.detail = this.detalhe;
    if (this.instancia != null) d.instance = this.instancia;
    return d;
  }
}

export function erroDeCorpo(status, corpo) {
  /* Corpo de erro da API (`app.erros.corpo_erro`) -> ErroPlataforma. Corpo fora do contrato (proxy, 5xx sem
     JSON) ainda vira ErroPlataforma com tipo "erro_desconhecido" e o bruto em detalhe. */
  if (corpo && typeof corpo === 'object' && 'erro' in corpo) {
    return new ErroPlataforma({
      status,
      tipo: String(corpo.erro),
      titulo: String(corpo.mensagem ?? corpo.erro),
      detalhe: corpo.detalhe ?? null,
      instancia: corpo.req_id ?? null,
      corpoBruto: corpo,
    });
  }
  return new ErroPlataforma({
    status,
    tipo: 'erro_desconhecido',
    titulo: `resposta ${status} fora do contrato da API`,
    detalhe: corpo,
    corpoBruto: corpo && typeof corpo === 'object' ? corpo : { bruto: corpo },
  });
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

function montarConsulta(params) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : '';
}

async function lerCorpo(resp) {
  const texto = await resp.text();
  if (!texto) return null;
  try { return JSON.parse(texto); } catch { return texto; }
}

class Http {
  /* Transporte: Bearer (ou cookie de sessão), JSON, retentativa com espera exponencial, tempo-limite. */
  constructor(url, { token = null, cookie = null, fetch: f = globalThis.fetch, tempoLimiteMs = 30000, tentativas = TENTATIVAS_PADRAO } = {}) {
    if (typeof f !== 'function') throw new Error('sem fetch: passe { fetch } (Node < 18) ou rode no navegador');
    this.url = url.replace(/\/+$/, '');
    this.token = token;
    this.cookie = cookie;
    this.fetch = (...args) => f(...args); // nunca `this.fetch(...)` cru: no navegador fetch exige `this` = window
    this.tempoLimiteMs = tempoLimiteMs;
    this.tentativas = tentativas;
  }

  cabecalhos(extra = {}) {
    const h = { Accept: 'application/json', ...extra };
    if (this.token) h.Authorization = `Bearer ${this.token}`;
    if (this.cookie) h.Cookie = this.cookie; // só em Node; o navegador cuida do cookie sozinho (same-origin)
    return h;
  }

  async pedir(metodo, caminho, { corpo, params } = {}) {
    const url = `${this.url}${caminho}${montarConsulta(params)}`;
    // Bearer NUNCA junto com o cookie de sessão (a API responde 400 autenticacao_ambigua): pedido por token vai sem
    // credenciais do navegador; pedido de sessão (tokens, login) leva o cookie same-origin
    const opcoes = { method: metodo, headers: this.cabecalhos(), credentials: this.token ? 'omit' : 'same-origin', cache: 'no-store' };
    if (corpo !== undefined) {
      opcoes.headers['Content-Type'] = 'application/json';
      opcoes.body = JSON.stringify(corpo);
    } else if (metodo === 'POST' || metodo === 'PUT') {
      // a checagem CSRF sob cookie exige application/json em todo corpo; um POST sem corpo manda {}
      opcoes.headers['Content-Type'] = 'application/json';
      opcoes.body = '{}';
    }
    let ultimoErro = null;
    for (let tentativa = 0; tentativa < this.tentativas; tentativa++) {
      if (tentativa) await dormir(ESPERA_BASE_MS * 2 ** (tentativa - 1));
      let resp;
      try {
        const ctl = typeof AbortController === 'function' ? new AbortController() : null;
        const t = ctl ? setTimeout(() => ctl.abort(), this.tempoLimiteMs) : null;
        try {
          resp = await this.fetch(url, ctl ? { ...opcoes, signal: ctl.signal } : opcoes);
        } finally { if (t) clearTimeout(t); }
      } catch (e) {
        ultimoErro = e; // erro de rede/tempo-limite: repete
        continue;
      }
      if (STATUS_RETENTAVEIS.has(resp.status) && tentativa < this.tentativas - 1) continue;
      const dados = await lerCorpo(resp);
      if (resp.status >= 200 && resp.status < 300) return { status: resp.status, dados, resp };
      throw erroDeCorpo(resp.status, dados);
    }
    throw new ErroPlataforma({
      status: 0, tipo: 'rede_indisponivel',
      titulo: `falha de rede após ${this.tentativas} tentativa(s): ${ultimoErro}`, detalhe: String(ultimoErro),
    });
  }

  get(c, params) { return this.pedir('GET', c, { params }).then((r) => r.dados); }
  post(c, corpo, params) { return this.pedir('POST', c, { corpo, params }).then((r) => r.dados); }
  put(c, corpo) { return this.pedir('PUT', c, { corpo }).then((r) => r.dados); }
  patch(c, corpo) { return this.pedir('PATCH', c, { corpo }).then((r) => r.dados); }
  delete(c, params) { return this.pedir('DELETE', c, { params }).then((r) => r.dados); }
}

export class Itens {
  /** `/api/itens`: o catálogo (mapas, camadas, conexões e todo `tipo_item` cadastrado). */
  constructor(http) { this._http = http; }

  listar({ tipo, limite, cursor, ...filtros } = {}) {
    // uma página: {total, itens, proximo_cursor, aproximado}; filtros = qualquer parâmetro da rota (q, tags, bbox, ...)
    return this._http.get('/api/itens', { tipo, limite, cursor, ...filtros });
  }

  async *todos({ tipo, ...filtros } = {}) {
    // itera todos os itens virando página pelo proximo_cursor — quem chama nunca lê o cursor na mão
    let cursor = null;
    for (;;) {
      const pagina = await this.listar({ tipo, cursor: cursor ?? undefined, ...filtros });
      for (const it of pagina.itens || []) yield it;
      cursor = pagina.proximo_cursor;
      if (!cursor) return;
    }
  }

  obter(id) { return this._http.get(`/api/itens/${encodeURIComponent(id)}`); }

  criar(tipo, titulo, { resumo, descricao, tags, pasta_id, extent, categorias, url, origem = 'hospedado', dados } = {}) {
    const corpo = { tipo, titulo, origem };
    for (const [k, v] of Object.entries({ resumo, descricao, tags, pasta_id, extent, categorias, url, dados })) {
      if (v !== undefined) corpo[k] = v;
    }
    return this._http.post('/api/itens', corpo);
  }

  atualizar(id, campos) { return this._http.patch(`/api/itens/${encodeURIComponent(id)}`, campos); }
  apagar(id, { cascata = false } = {}) { return this._http.delete(`/api/itens/${encodeURIComponent(id)}`, cascata ? { cascata: 'true' } : undefined); }
  mover(id, pastaId) { return this._http.post(`/api/itens/${encodeURIComponent(id)}/mover`, { pasta_id: pastaId ?? null }); }
  facetas() { return this._http.get('/api/itens/facetas'); }
  compartilhamento(id) { return this._http.get(`/api/itens/${encodeURIComponent(id)}/compartilhamento`); }
  compartilhar(id, { acesso, grupos } = {}) {
    const corpo = { acesso };
    if (grupos !== undefined) corpo.grupos = grupos;
    return this._http.put(`/api/itens/${encodeURIComponent(id)}/compartilhamento`, corpo);
  }
}

class VisaoPorTipo extends Itens {
  /* `.camadas` e `.mapas` são VISÕES por `tipo` sobre /api/itens — /api/camadas e /api/mapas não existem. */
  constructor(http, tipoPadrao, filtroTipo) { super(http); this._tipoPadrao = tipoPadrao; this._filtroTipo = filtroTipo; }
  listar({ tipo, ...filtros } = {}) { return super.listar({ tipo: tipo ?? this._filtroTipo, ...filtros }); }
  todos({ tipo, ...filtros } = {}) { return super.todos({ tipo: tipo ?? this._filtroTipo, ...filtros }); }
  criar(titulo, { tipo = this._tipoPadrao, ...campos } = {}) { return super.criar(tipo, titulo, campos); }
}

export class Jobs {
  constructor(http) { this._http = http; }
  listar(filtros) { return this._http.get('/api/jobs', filtros); }
  obter(id) { return this._http.get(`/api/jobs/${encodeURIComponent(id)}`); }
  tipos() { return this._http.get('/api/jobs/tipos'); }
  criar(tipo, parametros = {}) { return this._http.post('/api/jobs', { tipo, parametros }); }

  async esperar(id, { tempoLimiteMs = 60000, intervaloMs = 1000 } = {}) {
    // até estado terminal (concluido/falhou/cancelado) ou ErroPlataforma tempo_esgotado; nunca espera para sempre
    const inicio = Date.now();
    for (;;) {
      const job = await this.obter(id);
      if (ESTADOS_TERMINAIS_JOB.has(job.estado)) return job;
      if (Date.now() - inicio >= tempoLimiteMs) {
        throw new ErroPlataforma({
          status: 0, tipo: 'tempo_esgotado',
          titulo: `job ${id} não chegou a estado terminal em ${tempoLimiteMs} ms (estado atual: ${job.estado})`,
          detalhe: job,
        });
      }
      await dormir(intervaloMs);
    }
  }
}

export class Tokens {
  /* Toda rota de /api/tokens exige SESSÃO (cookie) — nunca outro token. No navegador a sessão vem do login da
     página (same-origin); em Node, de `Plataforma.entrar()`, que guarda o cookie. */
  constructor(httpSessao) { this._http = httpSessao; }
  _ou_erro() {
    if (!this._http) {
      throw new ErroPlataforma({
        status: 0, tipo: 'exige_sessao',
        titulo: 'as rotas de /api/tokens exigem sessão de login: use Plataforma.entrar(...) ou a página autenticada',
      });
    }
    return this._http;
  }
  async listar() { return this._ou_erro().get('/api/tokens'); }
  async criar(nome, escopos, { validadeDias, restricao } = {}) {
    const corpo = { nome, escopos };
    if (validadeDias !== undefined) corpo.validade_dias = validadeDias;
    if (restricao !== undefined) corpo.restricao = restricao;
    return this._ou_erro().post('/api/tokens', corpo);
  }
  async revogar(id) { return this._ou_erro().delete(`/api/tokens/${encodeURIComponent(id)}`); }
  async renovar(id) { return this._ou_erro().post(`/api/tokens/${encodeURIComponent(id)}/renovar`); }
  async log(id) { return this._ou_erro().get(`/api/tokens/${encodeURIComponent(id)}/log`); }
}

export class MapLibre {
  /* Ajudantes para MapLibre GL JS (vendorizado em /static/vendor/maplibre-gl-*.js; o SDK não o importa —
     recebe o objeto `maplibregl` ou o mapa já criado). Nada aqui chama a rede. */
  constructor(plataforma) { this._p = plataforma; }

  transformRequest = (url) => {
    // opção `transformRequest` do `new maplibregl.Map({...})`: põe o Bearer só em pedidos à própria plataforma
    // (/api e /ogc); tile de terceiro ou PMTiles estático passam intactos
    const base = this._p.url;
    if (this._p.token && (url.startsWith(`${base}/api/`) || url.startsWith(`${base}/ogc/`))) {
      return { url, headers: { Authorization: `Bearer ${this._p.token}` }, credentials: 'omit' }; // nunca Bearer + cookie
    }
    return { url };
  };

  extensaoComoGeoJSON(item) {
    const e = item && item.extent;
    if (!Array.isArray(e) || e.length !== 4 || e.some((v) => typeof v !== 'number' || Number.isNaN(v))) return null;
    const [xmin, ymin, xmax, ymax] = e;
    return {
      type: 'Feature',
      id: item.id,
      properties: { id: item.id, titulo: item.titulo, tipo: item.tipo },
      geometry: { type: 'Polygon', coordinates: [[[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]] },
    };
  }

  fonte(item) {
    /* `source` do MapLibre pronta para `mapa.addSource(id, fonte)`:
       - item que aponta para um PMTiles (url .pmtiles, ou procedência protocolo pmtiles) -> vector pmtiles://
       - item com extensão (`extent` [xmin,ymin,xmax,ymax] em 4326) -> geojson com o polígono da extensão
       - senão -> ErroPlataforma item_sem_geometria (nunca uma fonte vazia silenciosa) */
    if (!item || typeof item !== 'object') throw new ErroPlataforma({ status: 0, tipo: 'item_invalido', titulo: 'fonte(item) exige o item do catálogo (objeto de GET /api/itens/{id})' });
    const url = item.url || (item.dados && item.dados.procedencia && item.dados.procedencia.url) || null;
    const protocolo = item.dados && item.dados.procedencia && item.dados.procedencia.protocolo;
    if (url && (String(url).toLowerCase().endsWith('.pmtiles') || protocolo === 'pmtiles')) {
      return { type: 'vector', url: `pmtiles://${url}`, attribution: item.creditos || '' };
    }
    const feicao = this.extensaoComoGeoJSON(item);
    if (feicao) return { type: 'geojson', data: { type: 'FeatureCollection', features: [feicao] } };
    throw new ErroPlataforma({
      status: 0, tipo: 'item_sem_geometria',
      titulo: `o item ${item.id || '?'} (${item.tipo || '?'}) não tem extensão nem endereço de tiles; nada para desenhar`,
    });
  }

  camada(item, { id, cor = '#d98a2b', opacidade = 0.25 } = {}) {
    // `layer` para o `fonte(item)` correspondente: preenchimento da extensão (geojson) ou linhas do tileset (vector)
    const fonte = id || `plat-${item.id}`;
    const f = this.fonte(item);
    if (f.type === 'vector') {
      return { id: `${fonte}-linhas`, type: 'line', source: fonte, 'source-layer': (item.dados && item.dados.camada_tiles) || 'estradas', paint: { 'line-color': cor, 'line-width': 1 } };
    }
    return { id: `${fonte}-extensao`, type: 'fill', source: fonte, paint: { 'fill-color': cor, 'fill-opacity': opacidade, 'fill-outline-color': cor } };
  }

  catalogo({ bbox, tipo, q, limit = 100 } = {}) {
    /* Catálogo OGC API Records como GeoJSON (extensão de cada item legível): source geojson por URL — exige o
       `transformRequest` deste objeto no mapa, porque a rota pede token com escopo catalogo:ler. */
    const params = { limit };
    if (bbox) params.bbox = Array.isArray(bbox) ? bbox.join(',') : bbox;
    if (tipo) params.tipo = tipo;
    if (q) params.q = q;
    return { type: 'geojson', data: `${this._p.url}/ogc/records/collections/catalogo/items${montarConsulta(params)}` };
  }

  enquadrar(mapa, item, opcoes = { padding: 24 }) {
    const e = item && item.extent;
    if (!Array.isArray(e) || e.length !== 4) throw new ErroPlataforma({ status: 0, tipo: 'item_sem_geometria', titulo: 'enquadrar exige item com extent' });
    mapa.fitBounds([[e[0], e[1]], [e[2], e[3]]], opcoes);
    return mapa;
  }

  estilo(mapaItem, { basemapUrl = null, itens = [], fundo = '#0b0f10', cor = '#d98a2b' } = {}) {
    /* Estilo MapLibre (versão 8) de um item `mapa`: se `dados.corpo.estilo` já é um estilo MapLibre completo, é
       ele (com as fontes dos `itens` acrescentadas); senão, monta um: fundo + mapa-base PMTiles (se dado) +
       uma camada de extensão por item de `itens` (os itens que o corpo do mapa referencia, já carregados por
       `itens.obter`). Os ids de camada seguem `plat-<id do item>`. */
    const corpo = (mapaItem && mapaItem.dados && mapaItem.dados.corpo) || {};
    const base = corpo.estilo && corpo.estilo.version === 8
      ? { ...corpo.estilo, sources: { ...(corpo.estilo.sources || {}) }, layers: [...(corpo.estilo.layers || [])] }
      : { version: 8, name: `plat-${(mapaItem && mapaItem.id) || 'mapa'}`, sources: {}, layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': fundo } }] };
    if (basemapUrl && !base.sources.base) {
      base.sources.base = { type: 'vector', url: `pmtiles://${basemapUrl}`, attribution: '© colaboradores do OpenStreetMap — ODbL 1.0' };
      base.layers.push({ id: 'base-vias', type: 'line', source: 'base', 'source-layer': 'estradas', paint: { 'line-color': '#4d5b57', 'line-width': 0.8 } });
    }
    for (const item of itens) {
      const id = `plat-${item.id}`;
      base.sources[id] = this.fonte(item);
      base.layers.push(this.camada(item, { id, cor }));
    }
    return base;
  }
}

export class Plataforma {
  /** Ponto de entrada: `new Plataforma(url, token)`. `url` = URL pública do inquilino; `token` = token de serviço
      (`plat_...`, Minha conta -> Tokens, ou `await Plataforma.entrar(...)`). No navegador, `token` pode ser
      omitido para usar a sessão de cookie da página (same-origin); `.tokens` funciona nesse modo. */
  constructor(url, token = null, { fetch: f, tempoLimiteMs, tentativas, _cookie = null, _sessao = false, _tokenId = null } = {}) {
    this.url = String(url).replace(/\/+$/, '');
    this.token = token || null;
    this.tokenId = _tokenId;
    const opcoes = { fetch: f, tempoLimiteMs, tentativas };
    this._http = new Http(this.url, { token: this.token, ...opcoes });
    // sessão: cookie explícito (Node, vindo de entrar()), o jarro do navegador depois de entrar() (o cookie é
    // HttpOnly, invisível ao script, mas vai sozinho em pedidos same-origin), ou a sessão da página quando não há token
    this._httpSessao = (_cookie || _sessao) ? new Http(this.url, { cookie: _cookie, ...opcoes }) : (this.token ? null : this._http);
    this.itens = new Itens(this._http);
    this.camadas = new VisaoPorTipo(this._http, 'camada_vetorial', undefined);
    this.mapas = new VisaoPorTipo(this._http, 'mapa', 'mapa');
    this.jobs = new Jobs(this._http);
    this.tokens = new Tokens(this._httpSessao);
    this.maplibre = new MapLibre(this);
  }

  toString() { return `Plataforma(url=${this.url})`; } // nunca imprime o token

  eu() { return this._http.get('/api/eu'); }

  static async entrar(url, inquilino, login, senha, { nomeToken = 'sdk-js', escopos = ['admin:inquilino'], validadeDias, fetch: f, tempoLimiteMs, tentativas } = {}) {
    /* Login por usuário e senha (POST /api/login), depois cria um token de serviço com a sessão (POST /api/tokens,
       que só aceita sessão) e devolve uma Plataforma já autenticada por esse token. 2FA obrigatório vira
       ErroPlataforma exige_2fa (o SDK não implementa TOTP; use um token já existente). */
    const sessao = new Http(String(url).replace(/\/+$/, ''), { fetch: f, tempoLimiteMs, tentativas: 1 });
    const r = await sessao.pedir('POST', '/api/login', { corpo: { inquilino, login, senha } });
    const corpo = r.dados;
    if (!corpo || corpo.ok !== true) {
      if (corpo && corpo.exige_2fa) throw new ErroPlataforma({ status: r.status, tipo: 'exige_2fa', titulo: 'conta com 2FA obrigatório (o SDK não implementa TOTP; use um token já existente)', detalhe: corpo });
      throw erroDeCorpo(r.status, corpo);
    }
    // Node: o cookie de sessão vem em Set-Cookie e tem de ser reenviado à mão; navegador: já está no jarro
    const setCookie = r.resp && r.resp.headers && typeof r.resp.headers.get === 'function' ? r.resp.headers.get('set-cookie') : null;
    const cookie = setCookie ? setCookie.split(';')[0] : null;
    if (cookie) sessao.cookie = cookie;
    const corpoToken = { nome: nomeToken, escopos };
    if (validadeDias !== undefined) corpoToken.validade_dias = validadeDias;
    const tk = await sessao.post('/api/tokens', corpoToken);
    return new Plataforma(sessao.url, tk.token, { fetch: f, tempoLimiteMs, tentativas, _cookie: cookie, _sessao: true, _tokenId: tk.id });
  }

  async sair() {
    // revoga o token que entrar() criou (o limite de tokens ativos por usuário é real) e encerra a sessão
    if (this.tokenId != null && this._httpSessao) {
      try { await this.tokens.revogar(this.tokenId); } catch (e) { if (!(e instanceof ErroPlataforma)) throw e; }
    }
    if (this._httpSessao) {
      try { await this._httpSessao.post('/api/logout'); } catch (e) { if (!(e instanceof ErroPlataforma)) throw e; }
    }
  }
}

export default Plataforma;
