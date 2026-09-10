/* plat — modelo de dado do app (item L5-07-fontes-vistas-mensagens; L5_CONCEITO D4 e D5), sem DOM:

   corpo.fontes[]    { id: ULID, nome, origem: {tipo: 'item', item_id} | {tipo: 'url', url} | {tipo: 'embutida', feicoes},
                       campos: [{nome, tipo: 'texto|inteiro|decimal|booleano|data|data_hora|geometria'}] }
   corpo.vistas[]    { id: ULID, nome, fonte: <id de fonte>, filtro: <CQL2-JSON|null>, selecao: [ids],
                       ordenacao: [{campo, direcao}], campos: [nomes] | null }
   corpo.mensagens[] { id: ULID, gatilho: {origem: <id de widget|vista>, evento: <um dos 8>},
                       acoes: [{alvo: <id de widget|vista>, acao: <uma das 11>, parametros: {},
                                relacao: {tipo: 'mesma_fonte'|'atributo'|'espacial', campo_origem, campo_alvo, operador}}] }

   `validarModelo(corpo)` devolve {erros, avisos}: erro = o construtor recusa e o servidor recusa (422); aviso =
   o construtor mostra e deixa salvar (ciclo A->B->A: o barramento corta a recursão em 1 volta). A regra de
   relação é a dos Dashboards: entre fontes DIFERENTES a ação de dado exige relação declarada — por atributo
   (tipos casam; inteiro/decimal e data/data_hora são as duas exceções) ou espacial (as duas fontes têm
   geometria). O mesmo arquivo de regras existe em Python (app/app_modelo/validar.py): a API recusa o que o
   construtor recusaria. */
import * as cql2 from './cql2.js';
import { REGISTRO } from '../widgets/registro.js';

export const EVENTOS = Object.freeze(['clique', 'dado_adicionado', 'filtro_mudou', 'extensao_mudou', 'localizacao', 'registros_carregados', 'selecao_mudou', 'vista_mudou']);
export const ACOES_DADO = Object.freeze(['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao']);
export const ACOES_WIDGET = Object.freeze(['zoom', 'pan', 'piscar', 'popup', 'abrir', 'fechar', 'definir_parametro']);
export const ACOES = Object.freeze([...ACOES_DADO, ...ACOES_WIDGET]);
export const RELACOES = Object.freeze(['mesma_fonte', 'atributo', 'espacial']);
export const TIPOS_CAMPO = Object.freeze(['texto', 'inteiro', 'decimal', 'booleano', 'data', 'data_hora', 'geometria']);
export const OPERADORES_RELACAO = Object.freeze(['=', 'in']);
/* item L5-01-e-acoes-configuraveis: contrato por TIPO de widget (eventos que emite, ações que aceita), lido do
   registro dos widgets — o painel "Ações" só oferece o que casa, e a validação recusa o resto nos dois lados
   (`app/app_modelo/contratos.py` é o espelho em Python; `tests/unit/test_app_acoes.py` compara os dois). Uma
   vista emite só os cinco eventos de dado e aceita só as ações de dado. */
export const EVENTOS_VISTA = Object.freeze(['filtro_mudou', 'selecao_mudou', 'vista_mudou', 'dado_adicionado', 'registros_carregados']);
export const CONTRATOS = Object.freeze(Object.fromEntries([...REGISTRO.values()].map((m) => [m.nome, Object.freeze({ eventos: [...m.eventos], acoes: [...m.acoes] })])));
export function eventosDe(corpo, id, idx = indices(corpo)) {
  if (idx.vistas.has(id)) return EVENTOS_VISTA.filter((e) => EVENTOS.includes(e));
  const no = idx.nos.get(id);
  const c = no && CONTRATOS[no.tipo];
  return c ? c.eventos.filter((e) => EVENTOS.includes(e)) : [];
}
export function acoesDe(corpo, id, idx = indices(corpo)) {
  if (idx.vistas.has(id)) return [...ACOES_DADO];
  const no = idx.nos.get(id);
  const c = no && CONTRATOS[no.tipo];
  return c ? c.acoes.filter((a) => ACOES.includes(a)) : [];
}
export const ULID_RE = /^[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
export const LIMITES = Object.freeze({ fontes: 50, vistas: 200, mensagens: 500, acoes_por_mensagem: 20, campos: 500 });

const FAMILIA_TIPO = { inteiro: 'numero', decimal: 'numero', data: 'instante', data_hora: 'instante' };
export function tiposCasam(a, b) {
  if (a === b) return true;
  return !!FAMILIA_TIPO[a] && FAMILIA_TIPO[a] === FAMILIA_TIPO[b];
}

function erro(lista, caminho, mensagem, regra) { lista.push({ campo: caminho, erro: mensagem, regra }); }

export function indices(corpo) {
  const fontes = new Map((corpo.fontes || []).map((f) => [f.id, f]));
  const vistas = new Map((corpo.vistas || []).map((v) => [v.id, v]));
  const nos = new Map((corpo.nos || []).map((n) => [n.id, n]));
  return { fontes, vistas, nos };
}

export function fonteDaVista(corpo, vistaId, idx = indices(corpo)) {
  const v = idx.vistas.get(vistaId);
  return v ? idx.fontes.get(v.fonte) || null : null;
}

/* vista que um nó (widget) usa: configuracao.vista */
export function vistaDoNo(corpo, noId, idx = indices(corpo)) {
  const n = idx.nos.get(noId);
  const vid = n?.configuracao?.vista;
  return vid ? idx.vistas.get(vid) || null : null;
}

/* fonte por trás de um id que pode ser vista ou widget (nó ligado a uma vista) */
export function fonteDe(corpo, id, idx = indices(corpo)) {
  if (idx.vistas.has(id)) return fonteDaVista(corpo, id, idx);
  const v = vistaDoNo(corpo, id, idx);
  return v ? idx.fontes.get(v.fonte) || null : null;
}

function nomeNo(corpo, id, idx = indices(corpo)) {
  const v = idx.vistas.get(id); if (v) return `vista ${v.nome || id}`;
  const n = idx.nos.get(id); if (n) return `${n.tipo} ${String(id).slice(-4)}`;
  return String(id);
}
function campoDe(fonte, nome) { return (fonte?.campos || []).find((c) => c.nome === nome) || null; }
function temGeometria(fonte) { return (fonte?.campos || []).some((c) => c.tipo === 'geometria'); }

export function validarRelacao(corpo, origemId, alvoId, relacao, caminho, erros, idx = indices(corpo)) {
  const fo = fonteDe(corpo, origemId, idx);
  const fa = fonteDe(corpo, alvoId, idx);
  if (!fo || !fa) { erro(erros, caminho, 'origem e alvo de uma ação de dado precisam estar ligados a uma vista com fonte', 'sem_fonte'); return; }
  if (fo.id === fa.id) {
    if (relacao && relacao.tipo && relacao.tipo !== 'mesma_fonte') erro(erros, `${caminho}.relacao.tipo`, 'origem e alvo têm a mesma fonte: a relação é mesma_fonte', 'relacao_redundante');
    return;
  }
  if (!relacao || !relacao.tipo) { erro(erros, `${caminho}.relacao`, `fontes diferentes (${fo.nome || fo.id} e ${fa.nome || fa.id}) exigem relação declarada por atributo ou espacial`, 'relacao_ausente'); return; }
  if (!RELACOES.includes(relacao.tipo)) { erro(erros, `${caminho}.relacao.tipo`, `tipo de relação desconhecido: ${relacao.tipo}`, 'relacao_tipo'); return; }
  if (relacao.tipo === 'mesma_fonte') { erro(erros, `${caminho}.relacao.tipo`, 'fontes diferentes não são mesma_fonte', 'relacao_tipo'); return; }
  if (relacao.tipo === 'espacial') {
    if (!temGeometria(fo) || !temGeometria(fa)) erro(erros, `${caminho}.relacao`, 'relação espacial exige geometria nas duas fontes', 'relacao_espacial_sem_geometria');
    return;
  }
  const co = campoDe(fo, relacao.campo_origem);
  const ca = campoDe(fa, relacao.campo_alvo);
  if (!co) { erro(erros, `${caminho}.relacao.campo_origem`, `campo ${relacao.campo_origem} não existe na fonte de origem`, 'campo_inexistente'); return; }
  if (!ca) { erro(erros, `${caminho}.relacao.campo_alvo`, `campo ${relacao.campo_alvo} não existe na fonte de destino`, 'campo_inexistente'); return; }
  if (!tiposCasam(co.tipo, ca.tipo)) erro(erros, `${caminho}.relacao`, `tipos não casam: ${co.nome} é ${co.tipo} e ${ca.nome} é ${ca.tipo} (só inteiro/decimal e data/data_hora se equivalem)`, 'relacao_tipos');
  if (relacao.operador && !OPERADORES_RELACAO.includes(relacao.operador)) erro(erros, `${caminho}.relacao.operador`, `operador de relação inválido: ${relacao.operador}`, 'relacao_operador');
}

/* ciclos: A -> B -> A (por origem/alvo das ações de dado) viram AVISO; o barramento corta em 1 volta */
export function ciclos(corpo) {
  const grafo = new Map();
  for (const m of corpo.mensagens || []) {
    for (const a of m.acoes || []) {
      if (!ACOES_DADO.includes(a.acao)) continue;
      const de = m.gatilho?.origem; const para = a.alvo;
      if (!de || !para) continue;
      if (!grafo.has(de)) grafo.set(de, new Set());
      grafo.get(de).add(para);
    }
  }
  const achados = [];
  const visita = (inicio, atual, trilha, vistos) => {
    for (const prox of grafo.get(atual) || []) {
      if (prox === inicio) { achados.push([...trilha, prox]); continue; }
      if (vistos.has(prox)) continue;
      vistos.add(prox);
      visita(inicio, prox, [...trilha, prox], vistos);
    }
  };
  for (const inicio of grafo.keys()) visita(inicio, inicio, [inicio], new Set([inicio]));
  const unicos = new Map();
  for (const c of achados) { const chave = [...new Set(c)].sort().join('>'); if (!unicos.has(chave)) unicos.set(chave, c); }
  return [...unicos.values()];
}

export function validarModelo(corpo) {
  const erros = []; const avisos = [];
  const fontes = corpo.fontes || []; const vistas = corpo.vistas || []; const mensagens = corpo.mensagens || [];
  if (fontes.length > LIMITES.fontes) erro(erros, 'corpo.fontes', `mais de ${LIMITES.fontes} fontes`, 'limite');
  if (vistas.length > LIMITES.vistas) erro(erros, 'corpo.vistas', `mais de ${LIMITES.vistas} vistas`, 'limite');
  if (mensagens.length > LIMITES.mensagens) erro(erros, 'corpo.mensagens', `mais de ${LIMITES.mensagens} mensagens`, 'limite');
  const ids = new Set((corpo.nos || []).map((n) => n.id));
  fontes.forEach((f, i) => {
    const c = `corpo.fontes.${i}`;
    if (!ULID_RE.test(f.id || '')) erro(erros, `${c}.id`, 'id de fonte precisa ser um ULID', 'ulid');
    if (ids.has(f.id)) erro(erros, `${c}.id`, `id repetido: ${f.id}`, 'id_duplicado'); ids.add(f.id);
    if (!f.origem || !['item', 'url', 'embutida'].includes(f.origem.tipo)) erro(erros, `${c}.origem.tipo`, 'origem precisa ser item, url ou embutida', 'origem');
    if (f.origem?.tipo === 'url' && !/^\/[^\s]*$/.test(f.origem.url || '')) erro(erros, `${c}.origem.url`, 'url de fonte precisa ser caminho do próprio servidor (começa com /)', 'origem_url');
    if (!Array.isArray(f.campos) || f.campos.length > LIMITES.campos) erro(erros, `${c}.campos`, `campos precisa ser lista de até ${LIMITES.campos}`, 'campos');
    const nomes = new Set();
    for (const [j, campo] of (Array.isArray(f.campos) ? f.campos : []).entries()) {
      if (!campo || typeof campo.nome !== 'string' || !campo.nome) erro(erros, `${c}.campos.${j}.nome`, 'campo sem nome', 'campo');
      else if (nomes.has(campo.nome)) erro(erros, `${c}.campos.${j}.nome`, `campo repetido: ${campo.nome}`, 'campo_duplicado');
      nomes.add(campo?.nome);
      if (!TIPOS_CAMPO.includes(campo?.tipo)) erro(erros, `${c}.campos.${j}.tipo`, `tipo de campo desconhecido: ${campo?.tipo}`, 'campo_tipo');
    }
  });
  const idx = indices(corpo);
  vistas.forEach((v, i) => {
    const c = `corpo.vistas.${i}`;
    if (!ULID_RE.test(v.id || '')) erro(erros, `${c}.id`, 'id de vista precisa ser um ULID', 'ulid');
    if (ids.has(v.id)) erro(erros, `${c}.id`, `id repetido: ${v.id}`, 'id_duplicado'); ids.add(v.id);
    const f = idx.fontes.get(v.fonte);
    if (!f) { erro(erros, `${c}.fonte`, `vista aponta para fonte inexistente: ${v.fonte}`, 'referencia_pendente'); return; }
    if (v.filtro) {
      try { cql2.validar(v.filtro); } catch (e) { erro(erros, `${c}.filtro`, e.message, 'cql2'); }
      for (const p of cql2.propriedades(v.filtro)) if (!campoDe(f, p)) erro(erros, `${c}.filtro`, `filtro cita campo inexistente na fonte: ${p}`, 'campo_inexistente');
    }
    for (const [j, o] of (v.ordenacao || []).entries()) {
      if (!campoDe(f, o?.campo)) erro(erros, `${c}.ordenacao.${j}.campo`, `campo de ordenação inexistente: ${o?.campo}`, 'campo_inexistente');
      if (o?.direcao && !['asc', 'desc'].includes(o.direcao)) erro(erros, `${c}.ordenacao.${j}.direcao`, 'direção precisa ser asc ou desc', 'ordenacao');
    }
    for (const nome of v.campos || []) if (!campoDe(f, nome)) erro(erros, `${c}.campos`, `campo inexistente na fonte: ${nome}`, 'campo_inexistente');
    if (v.selecao && (!Array.isArray(v.selecao) || v.selecao.length > 10000)) erro(erros, `${c}.selecao`, 'seleção precisa ser lista de até 10000 ids', 'selecao');
  });
  const alvosValidos = (id) => idx.nos.has(id) || idx.vistas.has(id);
  const vistos = new Map(); // item L5-01-e: gatilho + alvo + ação repetidos = erro `gatilho_repetido`
  mensagens.forEach((m, i) => {
    const c = `corpo.mensagens.${i}`;
    if (!ULID_RE.test(m.id || '')) erro(erros, `${c}.id`, 'id de mensagem precisa ser um ULID', 'ulid');
    if (!m.gatilho || !alvosValidos(m.gatilho.origem)) erro(erros, `${c}.gatilho.origem`, `origem do gatilho não é widget nem vista do documento: ${m.gatilho?.origem}`, 'referencia_pendente');
    if (!EVENTOS.includes(m.gatilho?.evento)) erro(erros, `${c}.gatilho.evento`, `evento desconhecido: ${m.gatilho?.evento} (aceitos: ${EVENTOS.join(', ')})`, 'evento');
    else if (m.gatilho && alvosValidos(m.gatilho.origem)) {
      const emitidos = eventosDe(corpo, m.gatilho.origem, idx);
      if (!emitidos.includes(m.gatilho.evento)) erro(erros, `${c}.gatilho.evento`, `a origem ${nomeNo(corpo, m.gatilho.origem, idx)} não emite ${m.gatilho.evento} (emite: ${emitidos.join(', ') || 'nada'})`, 'evento_incompativel');
    }
    if (!Array.isArray(m.acoes) || !m.acoes.length) { erro(erros, `${c}.acoes`, 'mensagem sem ações', 'acoes'); return; }
    if (m.acoes.length > LIMITES.acoes_por_mensagem) erro(erros, `${c}.acoes`, `mais de ${LIMITES.acoes_por_mensagem} ações`, 'limite');
    m.acoes.forEach((a, j) => {
      const ca = `${c}.acoes.${j}`;
      if (!alvosValidos(a.alvo)) { erro(erros, `${ca}.alvo`, `alvo não é widget nem vista do documento: ${a.alvo}`, 'referencia_pendente'); return; }
      if (!ACOES.includes(a.acao)) { erro(erros, `${ca}.acao`, `ação desconhecida: ${a.acao} (aceitas: ${ACOES.join(', ')})`, 'acao'); return; }
      const aceitas = acoesDe(corpo, a.alvo, idx);
      if (!aceitas.includes(a.acao)) { erro(erros, `${ca}.acao`, `o alvo ${nomeNo(corpo, a.alvo, idx)} não aceita ${a.acao} (aceita: ${aceitas.join(', ') || 'nada'})`, 'alvo_incompativel'); return; }
      const chave = `${m.gatilho?.origem}|${m.gatilho?.evento}|${a.alvo}|${a.acao}`;
      if (vistos.has(chave)) erro(erros, `${ca}`, `gatilho já usado: ${m.gatilho?.evento} de ${nomeNo(corpo, m.gatilho?.origem, idx)} já dispara ${a.acao} em ${nomeNo(corpo, a.alvo, idx)} (mensagem ${vistos.get(chave)})`, 'gatilho_repetido');
      else vistos.set(chave, i);
      if (ACOES_DADO.includes(a.acao) && m.gatilho?.origem) validarRelacao(corpo, m.gatilho.origem, a.alvo, a.relacao, ca, erros, idx);
      const cond = a.parametros?.condicao;
      if (cond !== undefined && cond !== null) {
        try { cql2.validar(cond); } catch (e) { erro(erros, `${ca}.parametros.condicao`, `condição inválida: ${e.message}`, 'cql2'); }
        const fo = m.gatilho?.origem ? fonteDe(corpo, m.gatilho.origem, idx) : null;
        if (fo) for (const p of cql2.propriedades(cond)) if (!campoDe(fo, p)) erro(erros, `${ca}.parametros.condicao`, `condição cita campo inexistente na fonte de origem: ${p}`, 'campo_inexistente');
      }
      if (a.acao === 'definir_parametro' && (!a.parametros || typeof a.parametros.nome !== 'string')) erro(erros, `${ca}.parametros.nome`, 'definir_parametro exige parametros.nome', 'parametros');
    });
  });
  for (const c of ciclos(corpo)) avisos.push({ campo: 'corpo.mensagens', aviso: `ciclo de mensagens ${c.join(' -> ')}: o barramento corta a recursão em uma volta`, regra: 'ciclo' });
  return { erros, avisos };
}

/* ---------------------------------------------------------------- utilidades de documento */
const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
export function gerarUlid(agora = Date.now(), aleatorio = null) {
  let t = agora; let saida = '';
  for (let i = 0; i < 10; i += 1) { saida = CROCKFORD[t % 32] + saida; t = Math.floor(t / 32); }
  const bytes = aleatorio || (typeof crypto !== 'undefined' && crypto.getRandomValues ? crypto.getRandomValues(new Uint8Array(16)) : Array.from({ length: 16 }, () => Math.floor(Math.random() * 32)));
  for (let i = 0; i < 16; i += 1) saida += CROCKFORD[bytes[i] % 32];
  return saida;
}

export function garantirColecoes(corpo) {
  corpo.fontes ||= []; corpo.vistas ||= []; corpo.mensagens ||= [];
  return corpo;
}
