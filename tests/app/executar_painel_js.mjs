/* plat · runner node das INTERAÇÕES do painel (item L2-06-c-acoes-seletores-filtros-cruzados).
 * Executa com o BARRAMENTO REAL do L5-07 (`web/js/app/barramento.js`) e o adaptador REAL
 * (`web/js/paineis/interacoes.js`) — nenhum dublê. Comandos (todos rodam, JSON no stdout):
 *
 *   latencia    — cláusula 6 do portão: p95 gatilho→ação com 10.000 feições carregadas nas vistas alvo,
 *                 200 disparos do gatilho do seletor (o mesmo formato da mensagem m1 da semente: filtrar
 *                 na mesma fonte e filtrar por atributo em fonte diferente) + o pior caso adversarial
 *                 (relação por atributo onde a ORIGEM tem as 10.000 feições e o filtro é avaliado em
 *                 memória feição a feição).
 *   ciclo       — refutação: A filtra B e B filtra A; cada mensagem roda no máximo uma vez por volta
 *                 (corte em uma volta, aviso `ciclo_cortado`), 200 disparos alternados sem laço.
 *   selecao5000 — refutação: selecionar 5.000 feições de uma vista com 10.000 e disparar o gatilho de
 *                 seleção com ação por atributo (a lista do `in` é deduplicada).
 *   url         — cláusula 5 (funções puras): filtro/seleção das vistas → URL → vistas novas reabrem
 *                 com o mesmo estado.
 *   embrulhar   — a forma de feição que cada tipo de resultado do servidor produz (linhas, serie,
 *                 categorias, feicao, numero) — é o que as relações das mensagens leem.
 */
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const { Barramento } = await import(join(raiz, 'web/js/app/barramento.js'));
const { VistaElemento, embrulharResultado } = await import(join(raiz, 'web/js/paineis/interacoes.js'));
import * as estadoUrl from '../../web/js/app/estado_url.js';

const CAMPOS = ['agua', 'energia', 'via', 'limpeza'];
const feicoes10k = () => Array.from({ length: 10000 }, (_, i) => ({
  id: String(i),
  propriedades: { categoria: CAMPOS[i % 4], valor: i },
  geometria: { type: 'Point', coordinates: [-46.53 - (i % 11) * 0.01, -23.45 - (i % 7) * 0.01] },
}));

/* o barramento resolve TANTO gatilho QUANTO alvo pelo mapa de widgets (`configuracao.vista`) quando a
 * chave não é de vista — igual faz `ligarInteracoes` no painel de verdade: TODO elemento com fonte tem
 * widget. Sem isso a ação cai fora (`alvo_sem_vista`) e a medida mede nada. */
const widgetsDe = (ids, vistas) => new Map(ids.map((id) => [id,
  { configuracao: { vista: vistas.has(`v:${id}`) ? `v:${id}` : null }, executar: () => {} }]));

const agora = () => performance.now();
const p95de = (xs) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil(s.length * 0.95) - 1)];
};

/* ------------------------------------------------------------------ latência */
function latencia() {
  // painel realista: o seletor (widget, 4 feições de categorias) dispara m1 — filtrar 3 alvos da mesma
  // fonte e 1 por atributo — e os alvos são vistas com 10.000 feições carregadas (o mapa cheio)
  const alvos = ['a', 'b', 'c'].map((id) => {
    const v = new VistaElemento({ id }, { id: 'f1', campos: ['categoria', 'valor'] });
    v.carregar({ tipo: 'linhas', linhas: feicoes10k().map((f) => f.propriedades) });
    return [`v:${id}`, v];
  });
  const d = new VistaElemento({ id: 'd' }, { id: 'f2', campos: ['categoria', 'valor'] });
  d.carregar({ tipo: 'linhas', linhas: feicoes10k().map((f) => f.propriedades) });
  const sel = new VistaElemento({ id: 'sel' }, { id: 'f1', campos: ['categoria', 'valor'] });
  sel.carregar({ tipo: 'categorias', linhas: CAMPOS.map((c) => ({ categoria: c, valor: 30 })) });

  const vistas = new Map([['v:sel', sel], ['v:d', d], ...alvos]);
  const widgets = widgetsDe(['sel', 'a', 'b', 'c', 'd'], vistas);
  const mensagens = [{
    id: '01JPA1NEKEXEMPK0EKEM000LA1',
    gatilho: { origem: 'sel', evento: 'filtro_mudou' },
    acoes: [
      { alvo: 'a', acao: 'filtrar' },
      { alvo: 'b', acao: 'filtrar' },
      { alvo: 'c', acao: 'filtrar' },
      { alvo: 'd', acao: 'filtrar', relacao: { tipo: 'atributo', campo_origem: 'categoria', campo_alvo: 'categoria', operador: 'in' } },
    ],
  }];
  const barramento = new Barramento({ mensagens }, { vistas, widgets });

  const filtro = { op: '=', args: [{ property: 'categoria' }, 'agua'] };
  for (let i = 0; i < 200; i += 1) barramento.disparar('sel', 'filtro_mudou', { filtro });

  // pior caso adversarial: a ORIGEM é quem tem 10.000 feições e o filtro é avaliado em memória
  const origem10k = new VistaElemento({ id: 'o10k' }, { id: 'f3', campos: ['categoria', 'valor'] });
  origem10k.carregar({ tipo: 'linhas', linhas: feicoes10k().map((f) => f.propriedades) });
  const alvoF3 = new VistaElemento({ id: 'af3' }, { id: 'f4', campos: ['valor'] });
  const vistas2 = new Map([['v:o10k', origem10k], ['v:af3', alvoF3]]);
  const barramento2 = new Barramento({
    mensagens: [{
      id: '01JPA1NEKEXEMPK0EKEM000LA2',
      gatilho: { origem: 'o10k', evento: 'filtro_mudou' },
      acoes: [{ alvo: 'af3', acao: 'filtrar', relacao: { tipo: 'atributo', campo_origem: 'categoria', campo_alvo: 'valor', operador: 'in' } }],
    }],
  }, { vistas: vistas2, widgets: widgetsDe(['o10k', 'af3'], vistas2) });
  // 50 disparos bastam para o pior caso: cada um compila predicado CQL2 e avalia feição a feição sobre
  // as 10.000 da ORIGEM (o caminho em memória de fonte diferente) — é custo quadratico de demonstração,
  // não o caminho do painel real (que filtra em SQL no servidor)
  for (let i = 0; i < 50; i += 1) {
    barramento2.disparar('o10k', 'filtro_mudou', { filtro: { op: '=', args: [{ property: 'categoria' }, CAMPOS[i % 4]] } });
  }

  return {
    disparos: 200,
    feicoes_por_alvo: 10000,
    p95_ms: p95de(barramento.medidas.map((m) => m.ms)),
    max_ms: Math.max(...barramento.medidas.map((m) => m.ms)),
    disparos_medidos: barramento.medidas.length,
    pior_caso_atributo_10k_p95_ms: p95de(barramento2.medidas.map((m) => m.ms)),
    filtro_no_alvo_aplicado: vistas.get('v:a').filtroDinamico,
    alvo_d_recebeu_in: vistas.get('v:d').filtroDinamico?.op === 'in'
      && JSON.stringify(vistas.get('v:d').filtroDinamico.args[1]) === JSON.stringify(['agua']),
  };
}

/* ------------------------------------------------------------------ ciclo (refutação) */
function ciclo() {
  const va = new VistaElemento({ id: 'ea' }, { id: 'f1', campos: ['categoria'] });
  const vb = new VistaElemento({ id: 'eb' }, { id: 'f1', campos: ['categoria'] });
  va.carregar({ tipo: 'linhas', linhas: [{ categoria: 'agua' }] });
  vb.carregar({ tipo: 'linhas', linhas: [{ categoria: 'agua' }] });
  const vistas = new Map([['v:ea', va], ['v:eb', vb]]);
  const rel = { tipo: 'atributo', campo_origem: 'categoria', campo_alvo: 'categoria', operador: 'in' };
  const barramento = new Barramento({
    mensagens: [
      { id: '01JPA1NEKEXEMPK0EKEM000CI1', gatilho: { origem: 'ea', evento: 'filtro_mudou' },
        acoes: [{ alvo: 'eb', acao: 'filtrar', relacao: rel }] },
      { id: '01JPA1NEKEXEMPK0EKEM000CI2', gatilho: { origem: 'eb', evento: 'filtro_mudou' },
        acoes: [{ alvo: 'ea', acao: 'filtrar', relacao: rel }] },
    ],
  }, { vistas, widgets: widgetsDe(['ea', 'eb'], vistas) });

  const filtro = { op: '=', args: [{ property: 'categoria' }, 'agua'] };
  const inicio = agora();
  let disparos = 0;
  for (let i = 0; i < 200; i += 1) {
    barramento.disparar(i % 2 ? 'eb' : 'ea', 'filtro_mudou', { filtro });
    disparos += 1;
  }
  const cortes = barramento.avisos.filter((a) => a.tipo === 'ciclo_cortado').length;
  const voltasComMaisDeUmaMensagem = barramento.medidas.filter((m) => m.mensagens > 1).length;
  return {
    disparos,
    duracao_ms: Math.round((agora() - inicio) * 100) / 100,
    mensagens_executadas: barramento.medidas.reduce((s, m) => s + m.mensagens, 0),
    cortes_ciclo_cortado: cortes,
    voltas_com_mais_de_uma_mensagem: voltasComMaisDeUmaMensagem,
    limite_declarado: 'corte em uma volta: cada mensagem roda no máximo uma vez por volta do barramento '
      + '(conjunto por volta em Barramento#disparar); A->B->A recursa no máximo uma vez',
    terminou_sem_laco: disparos === 200 && barramento.medidas.length === 200,
  };
}

/* ------------------------------------------------------------------ seleção de 5.000 (refutação) */
function selecao5000() {
  const vista = new VistaElemento({ id: 'big' }, { id: 'f1', campos: ['categoria', 'valor'] });
  vista.carregar({ tipo: 'linhas', linhas: feicoes10k().map((f) => f.propriedades) });
  const alvo = new VistaElemento({ id: 'outro' }, { id: 'f2', campos: ['categoria'] });
  alvo.carregar({ tipo: 'linhas', linhas: feicoes10k().map((f) => f.propriedades) });
  const vistas = new Map([['v:big', vista], ['v:outro', alvo]]);
  const barramento = new Barramento({
    mensagens: [{
      id: '01JPA1NEKEXEMPK0EKEM000SE1',
      gatilho: { origem: 'big', evento: 'selecao_mudou' },
      acoes: [{ alvo: 'outro', acao: 'filtrar', relacao: { tipo: 'atributo', campo_origem: 'categoria', campo_alvo: 'categoria', operador: 'in' } }],
    }],
  }, { vistas, widgets: widgetsDe(['big', 'outro'], vistas) });

  const ids5000 = Array.from({ length: 5000 }, (_, i) => String(i * 2));
  const esperados = [...new Set(ids5000.map((id) => CAMPOS[Number(id) % 4]))].sort();
  const t0 = agora();
  vista.definirSelecao(ids5000, 'big');
  const ms_selecao = agora() - t0;
  const t1 = agora();
  barramento.disparar('big', 'selecao_mudou', { ids: ids5000 });
  const ms_gatilho = agora() - t1;
  const inlist = alvo.filtroDinamico?.args?.[1] || [];
  return {
    selecionadas: vista.selecao.size,
    ms_definir_selecao: Math.round(ms_selecao * 100) / 100,
    ms_gatilho_para_acao: Math.round(ms_gatilho * 100) / 100,
    valores_distintos_no_in: [...new Set(inlist)].sort(),
    in_deduplicado: JSON.stringify([...new Set(inlist)].sort()) === JSON.stringify(esperados),
    selecao_5000_aceita: vista.selecao.size === 5000,
  };
}

/* ------------------------------------------------------------------ URL (cláusula 5, funções puras) */
function url() {
  const vista = new VistaElemento({ id: 'el1' }, { id: 'f1', campos: ['categoria', 'valor'] });
  const outro = new VistaElemento({ id: 'el2' }, { id: 'f1', campos: ['categoria', 'valor'] });
  const vistas = new Map([['v:el1', vista], ['v:el2', outro]]);
  const filtro = { op: '=', args: [{ property: 'categoria' }, 'agua'] };
  vista.definirFiltro(filtro, 'el1');
  outro.definirSelecao(['3', '7'], 'el2');

  const busca = estadoUrl.paramsDoEstado(estadoUrl.estadoDasVistas(vistas)).toString();
  const restauradas = new Map([['v:el1', new VistaElemento({ id: 'el1' }, { id: 'f1' })],
    ['v:el2', new VistaElemento({ id: 'el2' }, { id: 'f1' })]]);
  const aplicados = estadoUrl.aplicarEstado(restauradas, estadoUrl.estadoDosParams(busca));
  return {
    nome_do_parametro: [...new URLSearchParams(busca).keys()],
    vistas_aplicadas: aplicados,
    filtro_restaurado_igual: JSON.stringify(restauradas.get('v:el1').filtroDinamico) === JSON.stringify(filtro),
    selecao_restaurada_igual: JSON.stringify([...restauradas.get('v:el2').selecao]) === JSON.stringify(['3', '7']),
    url_cabe_no_limite: busca.length <= 8000,
  };
}

/* ------------------------------------------------------------------ embrulharResultado */
function embrulhar() {
  const linhas = embrulharResultado({ tipo: 'linhas', linhas: [{ categoria: 'agua', valor: 1, __lon: -46.5, __lat: -23.4 }] });
  const serie = embrulharResultado({ tipo: 'serie', chave: 'categoria', chaves: ['agua', 'via'] });
  const categorias = embrulharResultado({ tipo: 'categorias', linhas: [{ categoria: 'agua', valor: 30 }] });
  const feicao = embrulharResultado({ tipo: 'feicao', valores: { valor: 10, __lon: -46.5, __lat: -23.4 } });
  const numero = embrulharResultado({ tipo: 'numero', valor: 120 });
  return {
    linhas_com_geometria: linhas.length === 1 && linhas[0].geometria?.type === 'Point' && linhas[0].id === '0',
    serie_id_e_a_chave: serie.length === 2 && serie[0].id === 'agua' && serie[1].propriedades.categoria === 'via',
    categorias_id_e_a_categoria: categorias[0].id === 'agua' && categorias[0].propriedades.valor === 30,
    feicao_unica: feicao.length === 1 && feicao[0].propriedades.valor === 10,
    numero_nao_carrega_feicao: numero.length === 0,
  };
}

const saida = {
  latencia: latencia(),
  ciclo: ciclo(),
  selecao5000: selecao5000(),
  url: url(),
  embrulhar: embrulhar(),
};
process.stdout.write(JSON.stringify(saida));
