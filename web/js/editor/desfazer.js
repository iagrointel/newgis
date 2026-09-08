/* plat — desfazer/refazer do documento de construtor (item L5-09-desfazer-refazer-rascunho).

   Pilha de JSON Patch (RFC 6902) por SESSÃO de edição (vive só na aba, nunca é gravada): cada mutação do
   documento (web/js/editor/documento.js) entra como {antes, depois, direto, inverso, grupo} — o PATCH de
   "antes" para "depois" e o de "depois" para "antes" — em vez de guardar a cópia inteira de cada passo. Uma
   operação CONTÍNUA (arrastar a alça de largura até soltar, digitar um campo até confirmar) grava um só passo
   porque `editor.js` só chama `aoMudar` UMA vez por gesto (a pré-visualização do arrasto mexe em CSS, nunca no
   documento — ver `ligarRedimensionar`/`aoPrever` em arrasto.js); o parâmetro `grupo` aqui existe para o caso
   em que uma chamada futura precise emitir vários `aoMudar` para o MESMO gesto (ex.: um controle que grava a
   cada tecla): registros consecutivos com o mesmo `grupo` substituem o topo da pilha em vez de empilhar.

   `diferencaJson`/`aplicarPatch` são uma reimplementação em JavaScript de `app/catalogo/diff.py`, de propósito
   SEM compartilhar código com o Python: os dois lados são exercitados por `tests/unit/test_diff_versoes.py`
   (Python) e `tests/unit/test_desfazer_refazer.py` (Node, via tests/unit/apoio_editor_js.mjs) separadamente —
   um defeito num não passaria despercebido só porque o outro concorda consigo mesmo. */

function escaparPonteiro(parte) {
  return String(parte).replace(/~/g, '~0').replace(/\//g, '~1');
}

function caminhoDe(partes) {
  return partes.length ? `/${partes.map(escaparPonteiro).join('/')}` : '';
}

function ehObjetoLiso(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/* diferença entre dois documentos JSON no formato JSON Patch (add/replace/remove), recursiva sobre
   dicionários e listas — mesma forma de app/catalogo/diff.py::patch. */
export function diferencaJson(antes, depois, partes = []) {
  if (ehObjetoLiso(antes) && ehObjetoLiso(depois)) {
    const ops = [];
    const chaves = Array.from(new Set([...Object.keys(antes), ...Object.keys(depois)])).sort();
    for (const chave of chaves) {
      const temAntes = Object.prototype.hasOwnProperty.call(antes, chave);
      const temDepois = Object.prototype.hasOwnProperty.call(depois, chave);
      if (!temAntes) ops.push({ op: 'add', path: caminhoDe([...partes, chave]), value: depois[chave] });
      else if (!temDepois) ops.push({ op: 'remove', path: caminhoDe([...partes, chave]) });
      else ops.push(...diferencaJson(antes[chave], depois[chave], [...partes, chave]));
    }
    return ops;
  }
  if (Array.isArray(antes) && Array.isArray(depois)) {
    const ops = [];
    const comum = Math.min(antes.length, depois.length);
    for (let i = 0; i < comum; i += 1) ops.push(...diferencaJson(antes[i], depois[i], [...partes, i]));
    for (let i = comum; i < depois.length; i += 1) ops.push({ op: 'add', path: caminhoDe([...partes, i]), value: depois[i] });
    // remoções do fim para o início, para os índices continuarem válidos ao aplicar (idem ao lado Python)
    for (let i = antes.length - 1; i >= comum; i -= 1) ops.push({ op: 'remove', path: caminhoDe([...partes, i]) });
    return ops;
  }
  if (antes === depois) return [];
  return [{ op: 'replace', path: caminhoDe(partes), value: depois }];
}

function partesDoCaminho(path) {
  if (!path) return [];
  return path
    .slice(1)
    .split('/')
    .map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'));
}

/* aplica uma lista de operações RFC 6902 sobre um documento e devolve um documento NOVO (cópia profunda por
   JSON, suficiente aqui: o documento do construtor só tem tipos que sobrevivem a JSON.stringify/parse). */
export function aplicarPatch(documento, operacoes) {
  let doc = JSON.parse(JSON.stringify(documento));
  for (const op of operacoes) {
    const partes = partesDoCaminho(op.path);
    if (!partes.length) {
      doc = JSON.parse(JSON.stringify(op.value));
      continue;
    }
    let alvo = doc;
    for (let i = 0; i < partes.length - 1; i += 1) {
      alvo = Array.isArray(alvo) ? alvo[Number(partes[i])] : alvo[partes[i]];
    }
    const ultimo = partes[partes.length - 1];
    if (Array.isArray(alvo)) {
      const i = Number(ultimo);
      if (op.op === 'add') alvo.splice(i, 0, op.value);
      else if (op.op === 'remove') alvo.splice(i, 1);
      else alvo[i] = op.value;
    } else if (op.op === 'remove') {
      delete alvo[ultimo];
    } else {
      alvo[ultimo] = op.value;
    }
  }
  return doc;
}

/* forma canônica para hash: chaves de objeto em ordem alfabética (recursivo), ordem de lista preservada.
   JSON.stringify sozinho já preserva a ordem de inserção das chaves do V8, mas dois caminhos de construção
   diferentes (arrasto x teclado, ou depois de desfazer/refazer) podem inserir as mesmas chaves em ordem
   diferente sem que o DOCUMENTO seja diferente — por isso o hash do portão de pronto usa esta forma, nunca
   JSON.stringify cru. */
export function canonicoParaHash(valor) {
  if (Array.isArray(valor)) return valor.map(canonicoParaHash);
  if (ehObjetoLiso(valor)) {
    const saida = {};
    for (const chave of Object.keys(valor).sort()) saida[chave] = canonicoParaHash(valor[chave]);
    return saida;
  }
  return valor;
}

export function jsonCanonico(valor) {
  return JSON.stringify(canonicoParaHash(valor));
}

/* pilha de desfazer/refazer de UMA sessão de edição. `documentoInicial` só marca o fundo da pilha (não é
   guardado à parte: desfazer tudo devolve o documento atual encadeado pelos inversos, que por construção bate
   com ele). */
export function criarHistorico() {
  let pilha = []; // {antes, depois, direto, inverso, grupo}
  let ponteiro = 0; // pilha[0..ponteiro) já aplicado ao documento atual

  function registrar(antes, depois, { grupo = null } = {}) {
    if (jsonCanonico(antes) === jsonCanonico(depois)) return; // nada mudou: não é passo de histórico
    const podeAgrupar = grupo !== null && ponteiro > 0 && ponteiro === pilha.length && pilha[ponteiro - 1].grupo === grupo;
    if (podeAgrupar) {
      const entrada = pilha[ponteiro - 1];
      entrada.depois = depois;
      entrada.direto = diferencaJson(entrada.antes, depois);
      entrada.inverso = diferencaJson(depois, entrada.antes);
      return;
    }
    pilha = pilha.slice(0, ponteiro); // edição nova depois de desfazer corta o "refazer" pendente
    pilha.push({ antes, depois, direto: diferencaJson(antes, depois), inverso: diferencaJson(depois, antes), grupo });
    ponteiro = pilha.length;
  }

  function podeDesfazer() { return ponteiro > 0; }
  function podeRefazer() { return ponteiro < pilha.length; }

  function desfazer(documentoAtual) {
    if (!podeDesfazer()) return documentoAtual;
    ponteiro -= 1;
    return aplicarPatch(documentoAtual, pilha[ponteiro].inverso);
  }

  function refazer(documentoAtual) {
    if (!podeRefazer()) return documentoAtual;
    const entrada = pilha[ponteiro];
    ponteiro += 1;
    return aplicarPatch(documentoAtual, entrada.direto);
  }

  function limpar() { pilha = []; ponteiro = 0; }

  function tamanho() { return { desfazer: ponteiro, refazer: pilha.length - ponteiro }; }

  return { registrar, desfazer, refazer, podeDesfazer, podeRefazer, limpar, tamanho };
}
