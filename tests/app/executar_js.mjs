// Runner do modelo de dado do app (item L5-07) em Node: os módulos de web/js/app/*.js não usam DOM, então as
// regras (CQL2, validação do modelo, barramento com corte de ciclo, estado na URL) e a LATÊNCIA
// gatilho->ação com 10 mil feições em memória são medidas aqui, sem navegador. tests/unit/test_app_modelo.py
// chama `node tests/app/executar_js.mjs <comando>` e lê JSON do stdout.
//   validar   : lê {corpo} do stdin, imprime {erros, avisos} de validarModelo (comparado com o Python)
//   cql2      : lê {filtros:[texto|json], feicoes:[...]} do stdin, imprime [{json, ids}] (ids que passam)
//   latencia  : gera 10 mil feições, 3 widgets e 2 vistas, dispara 200 seleções no mapa; imprime {p95_ms, ...}
//   ciclo     : A filtra B e B filtra A; imprime {avisos, voltas, filtroA, filtroB}
//   url       : ida e volta do estado de vistas pelos parâmetros de URL
//   where     : (L5-01-c) lê {filtros:[cql2 json|texto]} do stdin, imprime [{where, geometria, erro}]
//   agregar   : (L5-01-c) lê {feicoes, opcoes} do stdin, imprime {grupos, histograma, csv}
//   vista_memoria : (L5-01-c) a API assíncrona da vista em fonte de memória: página, total, agregação, exportação
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
const consulta = await import('../../web/js/app/consulta.js');
const agregacao = await import('../../web/js/app/agregacao.js');

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

if (comando === 'where') {
  const { filtros, oid } = entrada();
  sair(filtros.map((f) => {
    try { const r = consulta.cql2ParaWhere(cql2.normalizar(f), { oid: oid || 'fid' }); return { where: r.where, geometria: r.geometria ? r.geometria.relacao : null, erro: null }; }
    catch (e) { return { where: null, geometria: null, erro: e.codigo || 'erro' }; }
  }));
}

if (comando === 'agregar') {
  const { feicoes, opcoes } = entrada();
  const lista = normalizarLista(feicoes);
  sair({
    grupos: agregacao.agregarEmMemoria(lista, opcoes),
    histograma: opcoes.campo_valor ? agregacao.histogramaEmMemoria(lista, { campo: opcoes.campo_valor, faixas: opcoes.faixas || 4 }) : [],
    csv: agregacao.paraCsv(lista.map((f) => ({ __id: f.id, ...f.propriedades })), opcoes.colunas || null),
    modelo: agregacao.preencherModelo(opcoes.modelo || '', lista[0]?.propriedades || {}),
  });
}

if (comando === 'vista_memoria') {
  const { feicoes, filtro, ordenacao, limite } = entrada();
  const F = ulid(1); const A = ulid(2);
  const lista = normalizarLista(feicoes);
  const fontes = new Map([[F, fonteEmbutida(F, feicoes, [])]]);
  const corpo = { nos: [], fontes: [], vistas: [{ id: A, nome: 'A', fonte: F, ordenacao: ordenacao || [] }], mensagens: [] };
  const vistas = criarVistas(corpo, fontes);
  const v = vistas.get(A);
  if (filtro) v.definirFiltro(filtro);
  const p1 = await v.pagina({ deslocamento: 0, limite: limite || 2 });
  const p2 = await v.pagina({ deslocamento: limite || 2, limite: limite || 2 });
  const csv = await v.exportar('csv');
  const gj = await v.exportar('geojson');
  const ids = await v.idsDoFiltro({ op: '>', args: [{ property: 'n' }, 2] });
  sair({ total: await v.total(), p1: p1.registros.map((f) => f.id), p2: p2.registros.map((f) => f.id), linhasCsv: csv.trim().split('\n').length - 1, feicoesGeoJson: gj.features.length,
    distintos: await v.distintos('uf'), ids, lista: lista.length });
}

process.stderr.write(`comando desconhecido: ${comando}\n`);
process.exit(2);
