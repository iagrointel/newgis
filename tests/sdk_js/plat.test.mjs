// Testes de unidade do SDK JavaScript (item L7-08-c-sdk-js) com `node --test` e `fetch` falso: retentativa,
// paginação por cursor, erros como Problem Details, login+token (cookie em Node), tokens exigem sessão,
// jobs.esperar com tempo-limite, e os ajudantes MapLibre (funções puras: nunca chamam a rede).
// Corridos pelo pytest em tests/unit/test_sdk_js.py (fazem parte do `make check`).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ErroPlataforma, Plataforma, VERSAO, erroDeCorpo } from '../../sdk/js/plat.js';

const URL_BASE = 'https://plat.exemplo';

function resposta(status, corpo, cabecalhos = {}) {
  const texto = corpo === null ? '' : (typeof corpo === 'string' ? corpo : JSON.stringify(corpo));
  return {
    status,
    headers: { get: (k) => cabecalhos[k.toLowerCase()] ?? null },
    text: async () => texto,
  };
}

function fetchFalso(roteiro) {
  // roteiro: função (url, opcoes, n) -> resposta; guarda as chamadas para inspeção
  const chamadas = [];
  const f = async (url, opcoes) => {
    chamadas.push({ url, opcoes });
    return roteiro(url, opcoes, chamadas.length);
  };
  f.chamadas = chamadas;
  return f;
}

test('versão e toString nunca expõem o token', () => {
  const p = new Plataforma(`${URL_BASE}/`, 'plat_segredo', { fetch: fetchFalso(() => resposta(200, {})) });
  assert.equal(VERSAO, '0.1.0');
  assert.equal(p.url, URL_BASE);
  assert.equal(String(p).includes('segredo'), false);
});

test('Bearer no cabeçalho, JSON no corpo, e 2xx devolve o corpo decodificado', async () => {
  const f = fetchFalso(() => resposta(200, { login: 'ana' }));
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  const eu = await p.eu();
  assert.deepEqual(eu, { login: 'ana' });
  assert.equal(f.chamadas[0].url, `${URL_BASE}/api/eu`);
  assert.equal(f.chamadas[0].opcoes.headers.Authorization, 'Bearer plat_t');
  assert.equal(f.chamadas[0].opcoes.credentials, 'omit', 'Bearer nunca junto com o cookie de sessão');
  const item = await p.mapas.criar('m', { dados: { esquema_versao: 1, corpo: {} }, tags: ['a'] });
  assert.deepEqual(item, { login: 'ana' });
  const corpo = JSON.parse(f.chamadas[1].opcoes.body);
  assert.deepEqual(corpo, { tipo: 'mapa', titulo: 'm', origem: 'hospedado', dados: { esquema_versao: 1, corpo: {} }, tags: ['a'] });
  assert.equal(f.chamadas[1].opcoes.headers['Content-Type'], 'application/json');
});

test('erro da API vira ErroPlataforma (RFC 9457) com instancia = req_id; 4xx nunca é repetido', async () => {
  const f = fetchFalso(() => resposta(403, { erro: 'escopo_insuficiente', mensagem: 'sem escopo', detalhe: { exigido: 'admin:inquilino' }, req_id: 'abc' }));
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  await assert.rejects(p.itens.obter('x'), (e) => {
    assert.ok(e instanceof ErroPlataforma);
    assert.equal(e.status, 403);
    assert.equal(e.tipo, 'escopo_insuficiente');
    assert.equal(e.titulo, 'sem escopo');
    assert.equal(e.instancia, 'abc');
    assert.deepEqual(e.toProblemDetails(), { status: 403, type: 'escopo_insuficiente', title: 'sem escopo', detail: { exigido: 'admin:inquilino' }, instance: 'abc' });
    return true;
  });
  assert.equal(f.chamadas.length, 1);
  const e = erroDeCorpo(502, '<html>ruim</html>');
  assert.equal(e.tipo, 'erro_desconhecido');
  assert.equal(e.status, 502);
});

test('retentativa: 503 e erro de rede repetem com espera; 3ª tentativa passa', async () => {
  const f = fetchFalso((url, o, n) => {
    if (n === 1) return resposta(503, { erro: 'indisponivel', mensagem: 'x' });
    if (n === 2) throw new TypeError('rede caiu');
    return resposta(200, { ok: true });
  });
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  const inicio = Date.now();
  assert.deepEqual(await p.eu(), { ok: true });
  assert.equal(f.chamadas.length, 3);
  assert.ok(Date.now() - inicio >= 1400, 'espera exponencial 500 ms + 1000 ms');
});

test('retentativa esgotada por rede vira ErroPlataforma rede_indisponivel (status 0)', async () => {
  const f = fetchFalso(() => { throw new TypeError('sem rota'); });
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f, tentativas: 2 });
  await assert.rejects(p.eu(), (e) => e instanceof ErroPlataforma && e.tipo === 'rede_indisponivel' && e.status === 0);
  assert.equal(f.chamadas.length, 2);
});

test('paginação: todos() vira página pelo proximo_cursor e para no fim', async () => {
  const paginas = {
    '': { total: 5, itens: [{ id: 1 }, { id: 2 }], proximo_cursor: 'c2' },
    c2: { total: 5, itens: [{ id: 3 }, { id: 4 }], proximo_cursor: 'c3' },
    c3: { total: 5, itens: [{ id: 5 }], proximo_cursor: null },
  };
  const f = fetchFalso((url) => resposta(200, paginas[new URL(url).searchParams.get('cursor') || '']));
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  const ids = [];
  for await (const it of p.itens.todos({ tipo: 'mapa', limite: 2 })) ids.push(it.id);
  assert.deepEqual(ids, [1, 2, 3, 4, 5]);
  assert.equal(f.chamadas.length, 3);
  const u = new URL(f.chamadas[0].url);
  assert.equal(u.searchParams.get('tipo'), 'mapa');
  assert.equal(u.searchParams.get('limite'), '2');
  assert.equal(u.searchParams.has('cursor'), false);
});

test('entrar(): login por cookie, POST /api/tokens com o cookie, Plataforma por Bearer; sair() revoga', async () => {
  const f = fetchFalso((url, o) => {
    if (url.endsWith('/api/login')) return resposta(200, { ok: true }, { 'set-cookie': 'plat_sessao=abc; Path=/; HttpOnly' });
    if (url.endsWith('/api/tokens') && o.method === 'POST') return resposta(201, { id: 7, token: 'plat_novo', escopos: ['admin:inquilino'] });
    if (url.endsWith('/api/tokens/7') && o.method === 'DELETE') return resposta(204, null);
    if (url.endsWith('/api/logout')) return resposta(200, { ok: true });
    return resposta(200, { login: 'ana' });
  });
  const p = await Plataforma.entrar(URL_BASE, 'demo', 'ana', 's3nha', { fetch: f, nomeToken: 'teste' });
  assert.equal(p.token, 'plat_novo');
  assert.equal(p.tokenId, 7);
  assert.equal(f.chamadas[1].opcoes.headers.Cookie, 'plat_sessao=abc');
  assert.deepEqual(JSON.parse(f.chamadas[1].opcoes.body), { nome: 'teste', escopos: ['admin:inquilino'] });
  assert.equal(f.chamadas[1].opcoes.headers.Authorization, undefined);
  assert.equal(f.chamadas[1].opcoes.credentials, 'same-origin');
  await p.eu();
  assert.equal(f.chamadas[2].opcoes.headers.Authorization, 'Bearer plat_novo');
  await p.sair();
  assert.equal(f.chamadas[3].opcoes.method, 'DELETE');
  assert.equal(f.chamadas[3].opcoes.headers.Cookie, 'plat_sessao=abc');
  assert.ok(f.chamadas[4].url.endsWith('/api/logout'));
});

test('entrar() com 2FA obrigatório ou senha errada vira ErroPlataforma, sem criar token', async () => {
  const f2 = fetchFalso(() => resposta(200, { ok: false, exige_2fa: true }));
  await assert.rejects(Plataforma.entrar(URL_BASE, 'demo', 'a', 'b', { fetch: f2 }), (e) => e.tipo === 'exige_2fa');
  assert.equal(f2.chamadas.length, 1);
  const f401 = fetchFalso(() => resposta(401, { erro: 'credenciais_invalidas', mensagem: 'login ou senha inválidos' }));
  await assert.rejects(Plataforma.entrar(URL_BASE, 'demo', 'a', 'b', { fetch: f401 }), (e) => e.status === 401 && e.tipo === 'credenciais_invalidas');
});

test('tokens exigem sessão: Plataforma só por token recusa antes da rede', async () => {
  const f = fetchFalso(() => resposta(200, []));
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  await assert.rejects(p.tokens.listar(), (e) => e instanceof ErroPlataforma && e.tipo === 'exige_sessao');
  assert.equal(f.chamadas.length, 0);
  // no navegador, sem token = sessão de cookie da página: .tokens funciona pelo mesmo transporte
  const pc = new Plataforma(URL_BASE, null, { fetch: f });
  assert.deepEqual(await pc.tokens.listar(), []);
  assert.equal(f.chamadas[0].opcoes.headers.Authorization, undefined);
});

test('jobs.esperar(): devolve no estado terminal; tempo-limite vira tempo_esgotado', async () => {
  let n = 0;
  const f = fetchFalso(() => resposta(200, { id: 'j', estado: ++n >= 3 ? 'concluido' : 'executando' }));
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: f });
  const job = await p.jobs.esperar('j', { tempoLimiteMs: 5000, intervaloMs: 5 });
  assert.equal(job.estado, 'concluido');
  assert.equal(f.chamadas.length, 3);
  const fLento = fetchFalso(() => resposta(200, { id: 'j', estado: 'pendente' }));
  const p2 = new Plataforma(URL_BASE, 'plat_t', { fetch: fLento });
  await assert.rejects(p2.jobs.esperar('j', { tempoLimiteMs: 30, intervaloMs: 5 }), (e) => e.tipo === 'tempo_esgotado');
  const criado = fetchFalso(() => resposta(201, { id: 'novo' }));
  const p3 = new Plataforma(URL_BASE, 'plat_t', { fetch: criado });
  await p3.jobs.criar('prova.progresso', { passos: 2 });
  assert.deepEqual(JSON.parse(criado.chamadas[0].opcoes.body), { tipo: 'prova.progresso', parametros: { passos: 2 } });
});

test('maplibre.transformRequest: Bearer só na própria plataforma (/api, /ogc); resto intacto', () => {
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: fetchFalso(() => resposta(200, {})) });
  assert.deepEqual(p.maplibre.transformRequest(`${URL_BASE}/api/itens`), { url: `${URL_BASE}/api/itens`, headers: { Authorization: 'Bearer plat_t' }, credentials: 'omit' });
  assert.deepEqual(p.maplibre.transformRequest(`${URL_BASE}/ogc/records/collections/catalogo/items`).headers, { Authorization: 'Bearer plat_t' });
  assert.deepEqual(p.maplibre.transformRequest(`${URL_BASE}/static/dados/basemap/g.pmtiles`), { url: `${URL_BASE}/static/dados/basemap/g.pmtiles` });
  assert.deepEqual(p.maplibre.transformRequest('https://outro.exemplo/api/x'), { url: 'https://outro.exemplo/api/x' });
});

test('maplibre.fonte/camada/enquadrar: extensão vira GeoJSON; PMTiles vira vector; sem geometria recusa', () => {
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: fetchFalso(() => resposta(200, {})) });
  const item = { id: 'i1', tipo: 'mapa', titulo: 't', extent: [-46.6, -23.5, -46.4, -23.4] };
  const f = p.maplibre.fonte(item);
  assert.equal(f.type, 'geojson');
  assert.equal(f.data.features.length, 1);
  assert.deepEqual(f.data.features[0].geometry.coordinates[0][0], [-46.6, -23.5]);
  assert.equal(f.data.features[0].properties.titulo, 't');
  const c = p.maplibre.camada(item);
  assert.equal(c.type, 'fill');
  assert.equal(c.source, 'plat-i1');
  const pm = p.maplibre.fonte({ id: 'i2', tipo: 'camada_vetorial', url: `${URL_BASE}/static/dados/basemap/g.pmtiles` });
  assert.equal(pm.type, 'vector');
  assert.equal(pm.url, `pmtiles://${URL_BASE}/static/dados/basemap/g.pmtiles`);
  assert.equal(p.maplibre.camada({ id: 'i2', url: 'x.pmtiles' }).type, 'line');
  assert.throws(() => p.maplibre.fonte({ id: 'i3', tipo: 'mapa', extent: null }), (e) => e.tipo === 'item_sem_geometria');
  assert.throws(() => p.maplibre.fonte(null), (e) => e.tipo === 'item_invalido');
  const chamadas = [];
  p.maplibre.enquadrar({ fitBounds: (b, o) => chamadas.push([b, o]) }, item);
  assert.deepEqual(chamadas[0][0], [[-46.6, -23.5], [-46.4, -23.4]]);
  assert.throws(() => p.maplibre.enquadrar({ fitBounds() {} }, { id: 'x' }), (e) => e.tipo === 'item_sem_geometria');
});

test('maplibre.catalogo e estilo: fonte GeoJSON por URL autenticada; estilo versão 8 com fundo, base e itens', () => {
  const p = new Plataforma(URL_BASE, 'plat_t', { fetch: fetchFalso(() => resposta(200, {})) });
  const cat = p.maplibre.catalogo({ bbox: [-47, -24, -46, -23], tipo: 'mapa', limit: 10 });
  assert.equal(cat.type, 'geojson');
  const u = new URL(cat.data);
  assert.equal(u.pathname, '/ogc/records/collections/catalogo/items');
  assert.equal(u.searchParams.get('bbox'), '-47,-24,-46,-23');
  assert.equal(u.searchParams.get('limit'), '10');
  const itens = [{ id: 'a', tipo: 'mapa', titulo: 'a', extent: [0, 0, 1, 1] }, { id: 'b', tipo: 'mapa', titulo: 'b', extent: [1, 1, 2, 2] }];
  const est = p.maplibre.estilo({ id: 'm', dados: { corpo: { camadas: ['a', 'b'] } } }, { basemapUrl: `${URL_BASE}/x.pmtiles`, itens });
  assert.equal(est.version, 8);
  assert.deepEqual(Object.keys(est.sources), ['base', 'plat-a', 'plat-b']);
  assert.deepEqual(est.layers.map((l) => l.id), ['fundo', 'base-vias', 'plat-a-extensao', 'plat-b-extensao']);
  // corpo.estilo completo é respeitado (e as fontes dos itens acrescentadas)
  const proprio = { version: 8, sources: { s: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } }, layers: [{ id: 'x', type: 'background' }] };
  const est2 = p.maplibre.estilo({ id: 'm2', dados: { corpo: { estilo: proprio } } }, { itens: [itens[0]] });
  assert.deepEqual(Object.keys(est2.sources), ['s', 'plat-a']);
  assert.equal(est2.layers[0].id, 'x');
  assert.equal(proprio.layers.length, 1, 'o estilo do corpo não é mutado');
  const vazio = p.maplibre.estilo(null);
  assert.deepEqual(vazio.layers.map((l) => l.id), ['fundo']);
});
