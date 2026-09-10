/* plat — modelo do documento de construtor no navegador (item L5-08-editor-arrasto; L5_CONCEITO D2/D12).

   Primitiva COMPARTILHADA pelos doze construtores da linha L5: nenhuma função aqui sabe o que é um mapa, um
   passo de fluxo ou uma pergunta de formulário. Sabe só o que o envelope do L5-05 já grava:
   `{tipo, esquema_versao, corpo:{nos:[...], ligacoes:[...]}}`, com `nos` numa LISTA PLANA e o aninhamento
   escrito em `pai` (id do nó contêiner, ou null para a raiz). Lista plana porque:

   - o esquema `app-v2`/`painel-v2` do servidor já valida `corpo.nos` como lista de `{id ULID, tipo}` e recusa
     id repetido/ligação órfã (`app/catalogo/documento.py`) — árvore aninhada exigiria migração de esquema;
   - o desfazer do L5-09 é JSON Patch (D12): `replace /corpo/nos/<i>/largura_colunas` é uma operação estável;
   - reordenar é mover um bloco contíguo na lista, e a ORDEM DA LISTA é a ordem da tela — logo dois caminhos de
     edição (arrasto e teclado) que produzem a mesma lista produzem o mesmo documento, byte a byte.

   Toda função devolve um documento NOVO (cópia rasa dos nós alterados); nada muta o documento recebido. */

export const COLUNAS = 12;

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
export const ULID_RE = /^[0-7][0-9A-HJKMNP-TV-Z]{25}$/;

/* ULID: 48 bits de tempo em ms + 80 bits aleatórios, Crockford base32 — mesmo FORMATO do servidor
   (`app/catalogo/documento.py::gerar_ulid`); as duas implementações não se compartilham, só concordam. */
export function gerarUlid(agora = Date.now(), aleatorio = crypto.getRandomValues(new Uint8Array(10))) {
  let saida = '';
  let ts = BigInt(agora) & ((1n << 48n) - 1n);
  let valor = ts << 80n;
  for (const b of aleatorio) valor = (valor << 8n) | BigInt(b);
  for (let i = 0; i < 26; i += 1) { saida = CROCKFORD[Number(valor & 31n)] + saida; valor >>= 5n; }
  return saida;
}

export function novoDocumento(tipo = 'app') {
  return { tipo, esquema_versao: 2, corpo: { nos: [], ligacoes: [] } };
}

export function nos(doc) { return doc?.corpo?.nos ?? []; }
export function acharNo(doc, id) { return nos(doc).find((n) => n.id === id) || null; }
export function indiceDe(doc, id) { return nos(doc).findIndex((n) => n.id === id); }
export function filhos(doc, paiId = null) { return nos(doc).filter((n) => (n.pai ?? null) === (paiId ?? null)); }

export function ehDescendente(doc, id, possivelAncestral) {
  let atual = acharNo(doc, id);
  let voltas = 0;
  while (atual && atual.pai && voltas < 1000) {
    if (atual.pai === possivelAncestral) return true;
    atual = acharNo(doc, atual.pai);
    voltas += 1;
  }
  return false;
}

export function descendentes(doc, id) {
  return nos(doc).filter((n) => ehDescendente(doc, n.id, id));
}

function comNos(doc, lista) {
  return { ...doc, corpo: { ...doc.corpo, nos: lista } };
}

/* posição na lista onde entra um nó novo/movido: antes do irmão `antes`, ou depois do último nó do
   sub-arbusto do pai (para o filho novo nascer no fim do contêiner, não no fim do documento). */
function posicaoDeInsercao(lista, doc, pai, antes) {
  if (antes) {
    const i = lista.findIndex((n) => n.id === antes);
    if (i >= 0) return i;
  }
  if (!pai) return lista.length;
  const docTmp = comNos(doc, lista);
  let ultimo = lista.findIndex((n) => n.id === pai);
  if (ultimo < 0) return lista.length;
  for (let i = ultimo + 1; i < lista.length; i += 1) {
    if (ehDescendente(docTmp, lista[i].id, pai)) ultimo = i;
  }
  return ultimo + 1;
}

export class ErroEdicao extends Error {
  constructor(regra, mensagem) { super(mensagem); this.regra = regra; }
}

/* insere um nó novo. `paleta` é o catálogo de tipos (web/js/editor/paleta.js ou o manifesto do L5-06):
   quem diz se um tipo aceita filhos e qual a largura padrão é a paleta, nunca este módulo. */
export function inserir(doc, paleta, { tipo, pai = null, antes = null, id = null, propriedades = null, largura_colunas = null }) {
  const def = paleta.tipos[tipo];
  if (!def) throw new ErroEdicao('tipo_desconhecido', `tipo de nó fora da paleta: ${tipo}`);
  if (pai) {
    const noPai = acharNo(doc, pai);
    if (!noPai) throw new ErroEdicao('pai_inexistente', 'contêiner de destino não existe');
    if (!paleta.tipos[noPai.tipo]?.aceita_filhos) throw new ErroEdicao('pai_nao_container', 'este nó não aceita filhos');
  }
  const no = {
    id: id || gerarUlid(),
    tipo,
    pai: pai ?? null,
    largura_colunas: Math.min(COLUNAS, Math.max(1, largura_colunas ?? def.largura_padrao ?? COLUNAS)),
    propriedades: { ...(def.propriedades_padrao || {}), ...(propriedades || {}) },
  };
  const lista = nos(doc).slice();
  lista.splice(posicaoDeInsercao(lista, doc, pai, antes), 0, no);
  return { documento: comNos(doc, lista), id: no.id };
}

/* move um nó (com todo o sub-arbusto, na ordem em que está) para outro pai e/ou outra posição. */
export function mover(doc, paleta, id, { pai = null, antes = null } = {}) {
  const no = acharNo(doc, id);
  if (!no) throw new ErroEdicao('no_inexistente', 'nó inexistente');
  if (pai === id) throw new ErroEdicao('ciclo', 'um nó não pode ser filho de si mesmo');
  if (pai && ehDescendente(doc, pai, id)) throw new ErroEdicao('ciclo', 'um nó não pode entrar dentro de si mesmo');
  if (pai) {
    const noPai = acharNo(doc, pai);
    if (!noPai) throw new ErroEdicao('pai_inexistente', 'contêiner de destino não existe');
    if (!paleta.tipos[noPai.tipo]?.aceita_filhos) throw new ErroEdicao('pai_nao_container', 'este nó não aceita filhos');
  }
  if (antes && (antes === id || ehDescendente(doc, antes, id))) {
    throw new ErroEdicao('ciclo', 'destino dentro do próprio nó');
  }
  const bloco = [no, ...descendentes(doc, id)];
  const idsBloco = new Set(bloco.map((n) => n.id));
  const resto = nos(doc).filter((n) => !idsBloco.has(n.id));
  const docResto = comNos(doc, resto);
  const pos = posicaoDeInsercao(resto, docResto, pai, antes);
  const blocoNovo = bloco.map((n) => (n.id === id ? { ...n, pai: pai ?? null } : n));
  const lista = resto.slice(0, pos).concat(blocoNovo, resto.slice(pos));
  return comNos(doc, lista);
}

/* largura em COLUNAS da grade (1..12) — nunca pixel. O editor converte o arrasto em colunas antes de chamar. */
export function redimensionar(doc, id, colunas) {
  const c = Math.min(COLUNAS, Math.max(1, Math.round(Number(colunas))));
  if (!Number.isFinite(c)) throw new ErroEdicao('largura_invalida', 'largura precisa ser um número de colunas');
  return comNos(doc, nos(doc).map((n) => (n.id === id ? { ...n, largura_colunas: c } : n)));
}

export function definirPropriedade(doc, id, campo, valor) {
  return comNos(doc, nos(doc).map((n) => (n.id === id ? { ...n, propriedades: { ...n.propriedades, [campo]: valor } } : n)));
}

export function remover(doc, id) {
  const fora = new Set([id, ...descendentes(doc, id).map((n) => n.id)]);
  const lista = nos(doc).filter((n) => !fora.has(n.id));
  const ligacoes = (doc.corpo.ligacoes || []).filter((l) => !fora.has(l.origem) && !fora.has(l.alvo));
  return { ...doc, corpo: { ...doc.corpo, nos: lista, ligacoes } };
}

/* ordem de exibição: pré-ordem da árvore, que é a própria ordem da lista quando o documento é bem formado. */
export function emProfundidade(doc, paiId = null, nivel = 0, saida = []) {
  for (const n of filhos(doc, paiId)) {
    saida.push({ no: n, nivel });
    emProfundidade(doc, n.id, nivel + 1, saida);
  }
  return saida;
}

/* ------------------------------------------------------------------------------------------------------------
   vista móvel (item L5-15-vista-movel-responsivo; `db/migracoes/20260907T1505_vista_movel.sql`, esquema v3):
   `corpo.vista_movel = {manual, nos}`, onde `nos` é um mapa id-de-nó-de-RAIZ -> {oculto, ordem, largura_colunas}.
   `manual: true` faz esta lista PREVALECER sobre o reflow automático (portão do item); `manual: false`/ausente
   deixa o visualizador (web/js/visualizador/visualizador.js) empilhar tudo numa coluna só, na ordem em que já
   está. D1 do item: só nó de RAIZ tem override — um contêiner aninhado herda o reflow do próprio pai, para não
   precisar de uma segunda árvore de aninhamento só para celular. */

export function vistaMovel(doc) {
  const vm = doc?.corpo?.vista_movel;
  return { manual: !!vm?.manual, nos: (vm && typeof vm.nos === 'object' && vm.nos) || {} };
}

export function definirVistaMovelManual(doc, manual) {
  const vm = vistaMovel(doc);
  return { ...doc, corpo: { ...doc.corpo, vista_movel: { ...vm, manual: !!manual } } };
}

export function definirOverrideMovel(doc, id, patch) {
  const no = acharNo(doc, id);
  if (!no) throw new ErroEdicao('no_inexistente', 'nó inexistente');
  if (no.pai) throw new ErroEdicao('vista_movel_fora_da_raiz', 'vista móvel só configura nó de raiz');
  const vm = vistaMovel(doc);
  const atual = { ...(vm.nos[id] || {}), ...patch };
  for (const k of Object.keys(atual)) if (atual[k] === undefined) delete atual[k];
  return { ...doc, corpo: { ...doc.corpo, vista_movel: { ...vm, nos: { ...vm.nos, [id]: atual } } } };
}

export function removerOverrideMovel(doc, id) {
  const vm = vistaMovel(doc);
  if (!(id in vm.nos)) return doc;
  const nos2 = { ...vm.nos };
  delete nos2[id];
  return { ...doc, corpo: { ...doc.corpo, vista_movel: { ...vm, nos: nos2 } } };
}

/* nós de raiz visíveis na vista móvel MANUAL, na ordem em que devem aparecer: quem tem `ordem` explícita
   nunca perde para quem não tem (por isso o padrão de quem não tem override é `indice + 1000`, não o
   `indice` puro — um `ordem: 0` explícito tem de furar a fila na frente de TUDO que não foi configurado,
   mesmo que o nó não configurado já estivesse na posição 0 do documento). Entre dois nós sem override
   nenhum, o desempate é a ordem original da lista. */
export function nosVistaMovelManual(doc) {
  const vm = vistaMovel(doc);
  return filhos(doc, null)
    .map((no, i) => ({ no, ov: vm.nos[no.id] || {}, indice: i }))
    .filter((x) => !x.ov.oculto)
    .sort((a, b) => (a.ov.ordem ?? a.indice + 1000) - (b.ov.ordem ?? b.indice + 1000) || a.indice - b.indice)
    .map((x) => ({ no: x.no, largura_colunas_movel: x.ov.largura_colunas ?? null }));
}

/* Forma canônica para COMPARAR dois documentos construídos por caminhos diferentes: o ULID é aleatório por
   construção (D2: gerado na criação, nunca derivado de posição), então dois documentos iguais em estrutura
   têm ids diferentes. Aqui cada id vira `n1..nN` na ordem de profundidade; tudo o mais (tipo, aninhamento,
   ordem, largura em colunas, propriedades, ligações) é comparado como está. Se a diferença for vazia depois
   disto, os dois caminhos produziram o MESMO documento. */
export function canonico(doc) {
  const mapa = new Map();
  emProfundidade(doc).forEach(({ no }, i) => mapa.set(no.id, `n${i + 1}`));
  const traduz = (id) => (id === null || id === undefined ? null : (mapa.get(id) || id));
  return {
    tipo: doc.tipo,
    esquema_versao: doc.esquema_versao,
    corpo: {
      nos: emProfundidade(doc).map(({ no }) => ({
        id: traduz(no.id),
        tipo: no.tipo,
        pai: traduz(no.pai ?? null),
        largura_colunas: no.largura_colunas,
        propriedades: no.propriedades || {},
      })),
      ligacoes: (doc.corpo.ligacoes || []).map((l) => ({ ...l, origem: traduz(l.origem), alvo: traduz(l.alvo) })),
    },
  };
}
