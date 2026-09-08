// Runner Node dos testes de unidade do módulo de desfazer/refazer do editor (item L5-09-desfazer-refazer-
// rascunho): tests/unit/test_desfazer_refazer.py chama este script por subprocess (mesmo padrão de
// tests/expressoes/executar_js.mjs). Lê um comando pelo stdin como JSON {acao, ...} e imprime o resultado
// como JSON em stdout — sem framework de teste em JS no repositório, então quem afirma é o Python.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { criarHistorico, diferencaJson, aplicarPatch, jsonCanonico } from '../../web/js/editor/desfazer.js';
import * as doc from '../../web/js/editor/documento.js';
import { PALETA_LAYOUT } from '../../web/js/editor/paleta.js';
import { criarAutosave } from '../../web/js/editor/rascunho.js';
import { compararDocumentos } from '../../web/js/editor/diferenca.js';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const entrada = JSON.parse(readFileSync(process.argv.includes('--stdin') ? 0 : path.join(aqui, 'entrada.json'), 'utf8'));

/* gerador determinístico (sem depender de Math.random para o teste ser reproduzível): LCG simples */
function criarSorteio(semente) {
  let s = semente >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

function operacaoAleatoria(documento, sorteio) {
  const tipos = ['grupo', 'texto', 'imagem', 'mapa', 'tabela'];
  const nos = doc.nos(documento);
  const escolhas = ['inserir'];
  if (nos.length) escolhas.push('redimensionar', 'definirPropriedade');
  if (nos.length > 1) escolhas.push('mover');
  if (nos.length > 3) escolhas.push('remover');
  const acao = escolhas[Math.floor(sorteio() * escolhas.length)];
  const alvo = nos.length ? nos[Math.floor(sorteio() * nos.length)] : null;
  if (acao === 'inserir') {
    const tipo = tipos[Math.floor(sorteio() * tipos.length)];
    const containers = nos.filter((n) => PALETA_LAYOUT.tipos[n.tipo]?.aceita_filhos);
    const pai = containers.length && sorteio() < 0.4 ? containers[Math.floor(sorteio() * containers.length)].id : null;
    return doc.inserir(documento, PALETA_LAYOUT, { tipo, pai }).documento;
  }
  if (acao === 'redimensionar') return doc.redimensionar(documento, alvo.id, 1 + Math.floor(sorteio() * 12));
  if (acao === 'definirPropriedade') return doc.definirPropriedade(documento, alvo.id, 'rotulo', `r${Math.floor(sorteio() * 1000)}`);
  if (acao === 'remover') return doc.remover(documento, alvo.id);
  if (acao === 'mover') {
    const containers = nos.filter((n) => PALETA_LAYOUT.tipos[n.tipo]?.aceita_filhos && n.id !== alvo.id && !doc.ehDescendente(documento, n.id, alvo.id));
    const paiNovo = containers.length && sorteio() < 0.5 ? containers[Math.floor(sorteio() * containers.length)].id : null;
    try { return doc.mover(documento, PALETA_LAYOUT, alvo.id, { pai: paiNovo }); } catch { return documento; }
  }
  return documento;
}

function testeCicloDesfazerRefazer({ n, semente }) {
  const sorteio = criarSorteio(semente);
  const historico = criarHistorico();
  let atual = doc.novoDocumento('app');
  const inicial = atual;
  const passos = [];
  for (let i = 0; i < n; i += 1) {
    let novo;
    try { novo = operacaoAleatoria(atual, sorteio); } catch { continue; }
    historico.registrar(atual, novo);
    passos.push(novo);
    atual = novo;
  }
  const final = atual;
  // desfaz tudo
  let doc1 = atual;
  let voltas = 0;
  while (historico.podeDesfazer()) { doc1 = historico.desfazer(doc1); voltas += 1; }
  const bateuInicial = jsonCanonico(doc1) === jsonCanonico(inicial);
  // refaz tudo
  let doc2 = doc1;
  let idas = 0;
  while (historico.podeRefazer()) { doc2 = historico.refazer(doc2); idas += 1; }
  const bateuFinal = jsonCanonico(doc2) === jsonCanonico(final);
  return { operacoes_aplicadas: passos.length, voltas, idas, bateuInicial, bateuFinal };
}

function testeAgrupamento() {
  const historico = criarHistorico();
  let d0 = doc.novoDocumento('app');
  const r = doc.inserir(d0, PALETA_LAYOUT, { tipo: 'grupo' });
  const id = r.id;
  let atual = r.documento;
  historico.registrar(d0, atual);
  const antesDoGrupo = atual;
  // simula um "arrasto contínuo": 5 mudanças de largura, mesmo grupo -> deve virar 1 passo de histórico
  for (let largura = 11; largura >= 7; largura -= 1) {
    const novo = doc.redimensionar(atual, id, largura);
    historico.registrar(atual, novo, { grupo: `redimensionar:${id}` });
    atual = novo;
  }
  const tamanhoAntes = historico.tamanho().desfazer;
  const desfeito = historico.desfazer(atual);
  const bateuAntesDoGrupo = jsonCanonico(desfeito) === jsonCanonico(antesDoGrupo);
  return { passos_apos_grupo: tamanhoAntes, bateu_um_passo_so: bateuAntesDoGrupo };
}

function testeDiferencaPatch() {
  const antes = { a: 1, l: [1, 2, 3] };
  const depois = { a: 2, l: [1, 9], b: 'novo' };
  const p = diferencaJson(antes, depois);
  const aplicado = aplicarPatch(antes, p);
  return { ida_e_volta_ok: JSON.stringify(aplicado) === JSON.stringify(depois), patch: p };
}

function testeAutosaveLocal() {
  const armazenamento = new Map();
  const fake = {
    setItem: (k, v) => armazenamento.set(k, v),
    getItem: (k) => (armazenamento.has(k) ? armazenamento.get(k) : null),
    removeItem: (k) => armazenamento.delete(k),
  };
  let documentoAtual = doc.novoDocumento('app');
  const autosave = criarAutosave({
    idItem: 'item-teste',
    obterDocumento: () => documentoAtual,
    obterVersaoBase: () => 1,
    armazenamento: fake,
    intervaloMs: 999999,
  });
  documentoAtual = doc.inserir(documentoAtual, PALETA_LAYOUT, { tipo: 'texto' }).documento;
  autosave.registrarLocal(documentoAtual);
  const recuperadoAntes = autosave.recuperar();
  const tinhaPendente = !!recuperadoAntes && recuperadoAntes.pendente === true;
  autosave.confirmarServidor(documentoAtual);
  const recuperadoDepois = autosave.recuperar();
  return { tinha_pendente_antes: tinhaPendente, limpou_apos_confirmar: recuperadoDepois === null };
}

function testeDiferencaVisual() {
  let d0 = doc.novoDocumento('app');
  const a = doc.inserir(d0, PALETA_LAYOUT, { tipo: 'grupo' });
  const b = doc.inserir(a.documento, PALETA_LAYOUT, { tipo: 'texto', pai: a.id });
  const v3 = b.documento; // dois nós
  const v7a = doc.remover(v3, b.id); // remove o texto
  const v7 = doc.definirPropriedade(v7a, a.id, 'rotulo', 'Mudou'); // altera o grupo
  const c = doc.inserir(v7, PALETA_LAYOUT, { tipo: 'imagem' }); // adiciona imagem
  const comparacao = compararDocumentos(v3, c.documento);
  return {
    estados: comparacao.map((x) => x.estado).sort(),
    tem_removido_certo: comparacao.some((x) => x.estado === 'removido' && x.id === b.id),
    tem_alterado_certo: comparacao.some((x) => x.estado === 'alterado' && x.id === a.id),
    tem_adicionado_certo: comparacao.some((x) => x.estado === 'adicionado' && x.id === c.id),
  };
}

const ACOES = {
  ciclo_desfazer_refazer: testeCicloDesfazerRefazer,
  agrupamento: testeAgrupamento,
  diferenca_patch: testeDiferencaPatch,
  autosave_local: testeAutosaveLocal,
  diferenca_visual: testeDiferencaVisual,
};

const fn = ACOES[entrada.acao];
if (!fn) { process.stderr.write(`ação desconhecida: ${entrada.acao}\n`); process.exit(1); }
process.stdout.write(JSON.stringify(fn(entrada)));
