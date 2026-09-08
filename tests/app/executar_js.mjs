// Runner do modelo de dado do app (item L5-07) em Node: os módulos de web/js/app/*.js não usam DOM, então as
// regras (CQL2, validação do modelo, barramento com corte de ciclo, estado na URL) e a LATÊNCIA
// gatilho->ação com 10 mil feições em memória são medidas aqui, sem navegador. tests/unit/test_app_modelo.py
// chama `node tests/app/executar_js.mjs <comando>` e lê JSON do stdout.
//   validar   : lê {corpo} do stdin, imprime {erros, avisos} de validarModelo (comparado com o Python)
//   cql2      : lê {filtros:[texto|json], feicoes:[...]} do stdin, imprime [{json, ids}] (ids que passam)
//   latencia  : gera 10 mil feições, 3 widgets e 2 vistas, dispara 200 seleções no mapa; imprime {p95_ms, ...}
//   ciclo     : A filtra B e B filtra A; imprime {avisos, voltas, filtroA, filtroB}
//   url       : ida e volta do estado de vistas pelos parâmetros de URL
import { webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
if (!globalThis.performance) globalThis.performance = performance;
if (!globalThis.btoa) globalThis.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
if (!globalThis.atob) globalThis.atob = (s) => Buffer.from(s, 'base64').toString('binary');

const modelo = await import('../../web/js/app/modelo.js');
const cql2 = await import('../../web/js/app/cql2.js');
const { Fonte, normalizarLista } = await import('../../web/js/app/fontes.js');
const { criarVistas } = await import('../../web/js/app/vistas.js');
const { Barramento } = await import('../../web/js/app/barramento.js');
const url = await import('../../web/js/app/estado_url.js');
const { REGISTRO } = await import('../../web/js/widgets/registro.js');

const comando = process.argv[2];
const entrada = () => JSON.parse(readFileSync(0, 'utf8'));
const sair = (obj) => { process.stdout.write(JSON.stringify(obj)); process.exit(0); };

function ulid(n) { return '01K5' + String(n).padStart(22, '0').replace(/[^0-9A-HJKMNP-TV-Z]/g, '0'); }

function fonteEmbutida(id, feicoes, campos) {
  const f = new Fonte({ id, nome: id, origem: { tipo: 'embutida', feicoes }, campos });
  f.definirFeicoes(normalizarLista(feicoes));
  return f;
}

function widgetFalso(id, vista) {
  return { noId: id, configuracao: { vista: vista.id }, acoes: [], executar(acao, det) { this.acoes.push({ acao, n: (det.registros || []).length }); } };
}

if (comando === 'validar') {
  const { corpo } = entrada();
  sair(modelo.validarModelo(corpo));
}

if (comando === 'cql2') {
  const { filtros, feicoes } = entrada();
  const lista = normalizarLista(feicoes);
  sair(filtros.map((f) => {
    try {
      const json = cql2.normalizar(f);
      const pred = cql2.predicado(json);
      return { json, ids: lista.filter(pred).map((x) => x.id), erro: null };
    } catch (e) { return { json: null, ids: [], erro: e.codigo || 'erro' }; }
  }));
}

if (comando === 'latencia') {
  const N = Number(process.argv[3] || 10000);
  const feicoes = [];
  for (let i = 0; i < N; i += 1) {
    feicoes.push({ type: 'Feature', id: i, properties: { nome: `f${i}`, uf: ['SP', 'RJ', 'MG', 'BA', 'PR'][i % 5], valor: i % 100 },
      geometry: { type: 'Point', coordinates: [-50 + (i % 100) * 0.1, -20 + Math.floor(i / 100) * 0.1] } });
  }
  const fontes = new Map();
  const F = ulid(1);
  fontes.set(F, fonteEmbutida(F, feicoes, [{ nome: 'nome', tipo: 'texto' }, { nome: 'uf', tipo: 'texto' }, { nome: 'valor', tipo: 'inteiro' }, { nome: 'geometria', tipo: 'geometria' }]));
  const V1 = ulid(2); const V2 = ulid(3);
  const corpo = {
    nos: [{ id: ulid(10), tipo: 'mapa', configuracao: { vista: V1 } }, { id: ulid(11), tipo: 'tabela', configuracao: { vista: V2 } }, { id: ulid(12), tipo: 'grafico', configuracao: { vista: V2 } }],
    fontes: [{ id: F, nome: 'f', origem: { tipo: 'embutida', feicoes: [] }, campos: fontes.get(F).campos }],
    vistas: [{ id: V1, nome: 'mapa', fonte: F }, { id: V2, nome: 'tabela', fonte: F }],
    mensagens: [{ id: ulid(20), gatilho: { origem: ulid(10), evento: 'selecao_mudou' }, acoes: [{ alvo: V2, acao: 'filtrar', relacao: { tipo: 'mesma_fonte' } }, { alvo: ulid(12), acao: 'piscar' }] }],
  };
  const vistas = criarVistas(corpo, fontes);
  const widgets = new Map([[ulid(10), widgetFalso(ulid(10), vistas.get(V1))], [ulid(11), widgetFalso(ulid(11), vistas.get(V2))], [ulid(12), widgetFalso(ulid(12), vistas.get(V2))]]);
  const bus = new Barramento(corpo, { vistas, widgets });
  const tempos = [];
  for (let k = 0; k < 200; k += 1) {
    const ids = [k * 7 % N, (k * 13 + 1) % N, (k * 29 + 2) % N];
    const t0 = performance.now();
    bus.disparar(ulid(10), 'selecao_mudou', { ids });
    const regs = vistas.get(V2).registros();  // o alvo já foi refiltrado dentro da mesma volta
    tempos.push(performance.now() - t0);
    if (regs.length !== 3) sair({ erro: `esperava 3 registros filtrados, veio ${regs.length}` });
  }
  const ord = [...tempos].sort((a, b) => a - b);
  const p = (q) => ord[Math.min(ord.length - 1, Math.ceil(ord.length * q) - 1)];
  sair({ feicoes: N, disparos: tempos.length, p50_ms: +p(0.5).toFixed(3), p95_ms: +p(0.95).toFixed(3), max_ms: +ord[ord.length - 1].toFixed(3),
    p95_barramento_ms: +bus.p95().toFixed(3), acoes_grafico: widgets.get(ulid(12)).acoes.length });
}

if (comando === 'ciclo') {
  // A (municípios) filtra B (escolas) por atributo e B filtra A de volta: cada passagem produz um filtro
  // DIFERENTE (in cod_mun [...] / in cod [...]), então sem o corte a recursão não pararia
  const F1 = ulid(1); const F2 = ulid(4); const A = ulid(2); const B = ulid(3);
  const mun = [1, 2, 3, 4].map((i) => ({ type: 'Feature', id: i, properties: { cod: i } }));
  const esc = [[1, 1], [2, 1], [3, 2], [4, 3]].map(([id, cod]) => ({ type: 'Feature', id, properties: { cod_mun: cod } }));
  const fontes = new Map([[F1, fonteEmbutida(F1, mun, [{ nome: 'cod', tipo: 'inteiro' }])], [F2, fonteEmbutida(F2, esc, [{ nome: 'cod_mun', tipo: 'inteiro' }])]]);
  const corpo = {
    nos: [],
    fontes: [{ id: F1, nome: 'municipios', origem: { tipo: 'embutida', feicoes: [] }, campos: [{ nome: 'cod', tipo: 'inteiro' }] },
      { id: F2, nome: 'escolas', origem: { tipo: 'embutida', feicoes: [] }, campos: [{ nome: 'cod_mun', tipo: 'inteiro' }] }],
    vistas: [{ id: A, nome: 'A', fonte: F1 }, { id: B, nome: 'B', fonte: F2 }],
    mensagens: [
      { id: ulid(20), gatilho: { origem: A, evento: 'filtro_mudou' }, acoes: [{ alvo: B, acao: 'filtrar', relacao: { tipo: 'atributo', campo_origem: 'cod', campo_alvo: 'cod_mun', operador: 'in' } }] },
      { id: ulid(21), gatilho: { origem: B, evento: 'filtro_mudou' }, acoes: [{ alvo: A, acao: 'filtrar', relacao: { tipo: 'atributo', campo_origem: 'cod_mun', campo_alvo: 'cod', operador: 'in' } }] },
    ],
  };
  const validacao = modelo.validarModelo(corpo);
  const vistas = criarVistas(corpo, fontes);
  const bus = new Barramento(corpo, { vistas });
  let cortes = 0;
  bus.addEventListener('aviso', (e) => { if (e.detail.tipo === 'ciclo_cortado') cortes += 1; });
  vistas.get(A).definirFiltro({ op: '=', args: [{ property: 'cod' }, 1] }, 'teste');
  sair({ avisos_validacao: validacao.avisos.map((a) => a.regra), erros_validacao: validacao.erros, avisos: bus.avisos.map((a) => a.tipo), cortes,
    filtroA: vistas.get(A).filtro, filtroB: vistas.get(B).filtro, registrosA: vistas.get(A).registros().length, registrosB: vistas.get(B).registros().length });
}

if (comando === 'url') {
  const F = ulid(1); const A = ulid(2);
  const feicoes = [1, 2, 3].map((i) => ({ type: 'Feature', id: i, properties: { k: i } }));
  const fontes = new Map([[F, fonteEmbutida(F, feicoes, [{ nome: 'k', tipo: 'inteiro' }])]]);
  const corpo = { nos: [], fontes: [], vistas: [{ id: A, nome: 'A', fonte: F }], mensagens: [] };
  const vistas = criarVistas(corpo, fontes);
  vistas.get(A).definirFiltro('k >= 2');
  vistas.get(A).definirSelecao([3]);
  const params = url.paramsDoEstado(url.estadoDasVistas(vistas), new URLSearchParams('item=x'));
  const vistas2 = criarVistas(corpo, fontes);
  const aplicados = url.aplicarEstado(vistas2, url.estadoDosParams(params));
  sair({ query: params.toString(), aplicados, filtro: vistas2.get(A).filtro, selecao: [...vistas2.get(A).selecao], registros: vistas2.get(A).registros().map((f) => f.id) });
}


/* item L5-01-e: contrato por tipo de widget (o teste compara com app/app_modelo/contratos.py) */
if (comando === 'contratos') {
  sair(Object.fromEntries([...REGISTRO.values()].map((m) => [m.nome, { eventos: [...m.eventos], acoes: [...m.acoes] }])));
}

/* item L5-01-e, refutação: N ações em cadeia (mapa -> vista 1 -> vista 2 -> ... -> vista N, cada uma filtrando a
   próxima por mesma_fonte no evento filtro_mudou), 100 voltas de seleção no mapa; mede p95/máximo por volta, a
   profundidade da pilha de disparo e conta cortes de recursão. Com "ciclo", a última vista filtra a primeira. */
if (comando === 'cadeia') {
  const N = Number(process.argv[3] || 30); const NF = Number(process.argv[4] || 5000); const fecharCiclo = process.argv[5] === 'ciclo';
  const feicoes = [];
  for (let i = 0; i < NF; i += 1) feicoes.push({ type: 'Feature', id: i, properties: { k: i, uf: ['SP', 'RJ', 'MG'][i % 3] }, geometry: { type: 'Point', coordinates: [-50 + (i % 100) * 0.1, -20 + Math.floor(i / 100) * 0.1] } });
  const F = ulid(1);
  const fontes = new Map([[F, fonteEmbutida(F, feicoes, [{ nome: 'k', tipo: 'inteiro' }, { nome: 'uf', tipo: 'texto' }, { nome: 'geometria', tipo: 'geometria' }])]]);
  const V = (i) => ulid(100 + i); const W = ulid(50);
  const vistasDef = []; const mensagens = [];
  for (let i = 0; i <= N; i += 1) vistasDef.push({ id: V(i), nome: `v${i}`, fonte: F });
  mensagens.push({ id: ulid(200), gatilho: { origem: W, evento: 'selecao_mudou' }, acoes: [{ alvo: V(1), acao: 'filtrar', parametros: {}, relacao: { tipo: 'mesma_fonte' } }] });
  for (let i = 1; i < N; i += 1) mensagens.push({ id: ulid(200 + i), gatilho: { origem: V(i), evento: 'filtro_mudou' }, acoes: [{ alvo: V(i + 1), acao: 'filtrar', parametros: {}, relacao: { tipo: 'mesma_fonte' } }] });
  if (fecharCiclo) mensagens.push({ id: ulid(299), gatilho: { origem: V(N), evento: 'filtro_mudou' }, acoes: [{ alvo: V(1), acao: 'filtrar', parametros: {}, relacao: { tipo: 'mesma_fonte' } }] });
  const corpo = { nos: [{ id: W, tipo: 'mapa', configuracao: { vista: V(0) } }], fontes: [{ id: F, nome: 'f', origem: { tipo: 'embutida', feicoes: [] }, campos: fontes.get(F).campos }], vistas: vistasDef, mensagens };
  const validacao = modelo.validarModelo(corpo);
  if (validacao.erros.length) sair({ erro: 'modelo inválido', erros: validacao.erros });
  const vistas = criarVistas(corpo, fontes);
  const widgets = new Map([[W, widgetFalso(W, vistas.get(V(0)))]]);
  const bus = new Barramento(corpo, { vistas, widgets });
  let cortes = 0; let profundidade = 0; let atual = 0;
  bus.addEventListener('aviso', (e) => { if (e.detail.tipo === 'ciclo_cortado') cortes += 1; });
  const original = bus.disparar.bind(bus);
  bus.disparar = (...args) => { atual += 1; profundidade = Math.max(profundidade, atual); try { return original(...args); } finally { atual -= 1; } };
  const tempos = []; let disparosPorVolta = 0;
  for (let k = 0; k < 100; k += 1) {
    const ids = [k % NF, (k * 7 + 1) % NF, (k * 13 + 2) % NF];
    const antes = bus.medidas.length;
    const t0 = performance.now();
    bus.disparar(W, 'selecao_mudou', { ids });
    tempos.push(performance.now() - t0);
    disparosPorVolta = bus.medidas.slice(antes).reduce((s, m) => s + m.mensagens, 0);
  }
  const ord = [...tempos].sort((a, b) => a - b);
  const p = (q) => ord[Math.min(ord.length - 1, Math.ceil(ord.length * q) - 1)];
  sair({ vistas: vistasDef.length, mensagens: mensagens.length, feicoes: NF, voltas: tempos.length, disparos_por_volta: disparosPorVolta,
    p50_ms: +p(0.5).toFixed(3), p95_ms: +p(0.95).toFixed(3), max_ms: +ord[ord.length - 1].toFixed(3), profundidade_max: profundidade, cortes,
    avisos: [...new Set(bus.avisos.map((a) => a.tipo))], registros_primeira: vistas.get(V(1)).registros().length, registros_ultima: vistas.get(V(N)).registros().length,
    avisos_validacao: validacao.avisos.map((a) => a.regra) });
}

process.stderr.write(`comando desconhecido: ${comando}\n`);
process.exit(2);
