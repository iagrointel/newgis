/* plat · AMC — item L3-01-g-tela-motor: a tela /amc/motor.

   O que ela faz, na ordem em que o usuário faz: parte de um CONJUNTO DE UNIDADES já pronto, monta um modelo
   (adicionar fator = camada do catálogo ou do acervo + extrator + transformação, com pré-visualização do
   histograma; marcar veto = restrição separada do peso), escolhe o peso de cada fator por controle deslizante
   (multiplicador) ou por percentual com trava, manda RODAR (a extração é um job do servidor) e, com a
   execução em mãos, recombina NA HORA ao mover um peso — sem novo job, sem nova extração.

   Por que dá para recombinar sem servidor: `GET /api/amc/execucoes/{id}/matriz` entrega a favorabilidade de
   cada fator em cada unidade (a parte cara, que depende da extração) e `web/js/amc/combinacao.js` faz a parte
   barata (a soma ponderada), provada equivalente ao `app/amc/combinacao.py` em
   tests/unit/test_amc_combinacao_equivalencia.py. Mover um peso não muda nenhum valor extraído — só a conta.

   Fronteira de confiança: os pesos viajam na URL e por isso passam por `web/js/amc/pesos_url.js` antes de
   qualquer conta. Link adulterado é recusado com a razão escrita na tela; nada é recolorido em silêncio.

   Módulo ES sem build; cache resolvido por no-store no nginx: NUNCA `?v=` nos imports. MapLibre GL e o
   protocolo pmtiles vêm de <script> clássico carregado antes deste módulo (window.maplibregl/window.pmtiles),
   como em web/js/mapa/mapa.js. */
import { obter, enviar, alterar, mensagemDe } from '../base/api.js';
import '../base/componentes.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { irParaLogin, marcarSessao } from '../auth/sessao.js';
import { h, limpar, copiar } from '../base/dom.js';
import { combinar, ErroCombinacao, MAPA_COMBINADOR, MAPA_POLITICA, SEM_PESO } from './combinacao.js';
import { lerPesos, escreverPesos, montarLink, PESO_MAX } from './pesos_url.js';
import { corDe, itensDaLegenda } from './rampa.js';
import { CAMPOS, TIPOS, EXTRATORES, lerCampo } from './parametros.js';
import { construirEstilo } from '../mapa/estilo.js';

const el = (id) => document.getElementById(id);
const UNIDADES_PAGINA = 2000;
const ESTADOS_EM_CURSO = new Set(['registrada', 'na_fila', 'executando']);

const estado = {
  execucao: null,      // ficha de GET /api/amc/execucoes/{id}
  definicao: null,     // documento do modelo (amc_modelo.v1)
  modeloId: null,
  conjuntoId: null,
  matriz: null,        // GET /api/amc/execucoes/{id}/matriz
  geo: new Map(),      // unidade_id -> geometria (GeoJSON)
  pesos: {},           // {fator_id: peso} em uso agora
  travados: new Set(), // fatores com o peso travado no modo percentual
  modoPeso: 'multiplicador',
  resultado: null,     // saída de combinar()
  mapa: null,
  recusas: [],
};

/* ---------------------------------------------------------------- utilidades de leitura */
function parametros() {
  return new URLSearchParams(location.search);
}

function numero(v, casas = 1) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(casas) : '—';
}

function fatores() {
  return (estado.matriz && estado.matriz.fatores) || (estado.definicao ? fichasDaDefinicao() : []);
}

function fichasDaDefinicao() {
  return (estado.definicao.fatores || []).map((f) => ({
    id: f.id, nome: f.nome, criterio: f.criterio, fonte: f.fonte, unidade: f.unidade,
    direcao: f.direcao, base: f.base, peso_modelo: Number(f.peso), camada: f.camada || {},
    extrator_tipo: (f.extrator || {}).tipo, transformacao: f.transformacao || {},
    proxy_descricao: (f.proxy || {}).descricao, proxy_teto_peso: (f.proxy || {}).teto_peso,
    nao_sustenta: f.nao_sustenta,
  }));
}

function combinadorDoModelo() {
  const tipo = ((estado.definicao || {}).combinador || {}).tipo || 'soma_ponderada_normalizada';
  return { tipo, js: MAPA_COMBINADOR[tipo] || 'soma_ponderada', gama: ((estado.definicao || {}).combinador || {}).gama };
}

/* ---------------------------------------------------------------- recombinação (a parte barata) */
function recombinar() {
  const aviso = el('aviso');
  if (estado.recusas.length || !estado.matriz || !estado.matriz.unidades.length) {
    estado.resultado = null;
    desenharMelhores();
    pintarMapa();
    return;
  }
  const fichas = estado.matriz.fatores;
  const ids = fichas.map((f) => f.id);
  const pesos = ids.map((id) => Number(estado.pesos[id]));
  const matriz = estado.matriz.unidades.map((u) => u.favorabilidades);
  const fracaoVetada = estado.matriz.unidades.map((u) => (u.vetado ? 1 : 0));
  const motivoVeto = estado.matriz.unidades.map((u) => u.motivo);
  const comb = combinadorDoModelo();
  try {
    estado.resultado = combinar(matriz, pesos, {
      combinador: comb.js,
      politicaAusente: MAPA_POLITICA[estado.matriz.dado_ausente] || 'excluir',
      gama: typeof comb.gama === 'number' ? comb.gama : 0.5,
      fracaoVetada, motivoVeto, idsFatores: ids,
    });
    aviso.limpar();
  } catch (e) {
    estado.resultado = null;
    aviso.erro(e instanceof ErroCombinacao ? `a conta foi recusada: ${e.mensagem}` : String(e.message || e));
  }
  desenharMelhores();
  desenharResumoNotas();
  pintarMapa();
  atualizarUrl();
}

function atualizarUrl() {
  if (!estado.execucao) return;
  const u = new URL(location.href);
  u.searchParams.set('execucao', estado.execucao.id);
  u.searchParams.set('w', escreverPesos(estado.pesos));
  history.replaceState(null, '', u.toString());
}

/* ---------------------------------------------------------------- painéis */
function desenharContexto() {
  const dl = el('contexto-lista');
  limpar(dl);
  const linha = (rotulo, valor) => dl.append(h('dt', {}, rotulo), h('dd', {}, valor));
  // identificador é dado de auditoria, longo por natureza: entra em fonte de dado e quebra onde couber, para
  // não empurrar o resto do painel para fora da primeira tela
  const id = (v) => h('code', { class: 'motor-id', title: v || '' }, v || '—');
  linha('modelo', (estado.definicao && estado.definicao.nome) || '—');
  linha('conjunto de unidades', id(estado.conjuntoId));
  if (estado.execucao) {
    linha('execução', id(estado.execucao.id));
    linha('versão do modelo', id(estado.execucao.versao_hash));
    linha('versão do motor', id(estado.execucao.motor_versao));
  }
  linha('combinador', combinadorDoModelo().tipo);
  linha('pesos', 'escolhidos pelo usuário, não medidos');
}

function desenharRecusas() {
  const bloco = el('bloco-recusas');
  const lista = el('recusas-lista');
  limpar(lista);
  bloco.hidden = estado.recusas.length === 0;
  for (const r of estado.recusas) lista.append(h('li', {}, r));
}

function somaPesos() {
  return Object.values(estado.pesos).reduce((a, b) => a + Number(b), 0);
}

function desenharSomaPesos() {
  const comb = combinadorDoModelo();
  const soma = somaPesos();
  const alvo = estado.modoPeso === 'percentual' || comb.tipo === 'percentual';
  const texto = alvo ? `soma ${numero(soma, 2)} de 100` : `soma ${numero(soma, 2)}`;
  const cabe = !alvo || Math.abs(soma - 100) < 1e-6;
  const caixa = el('soma-pesos');
  caixa.textContent = cabe ? texto : `${texto} — fora de 100, a conta não roda`;
  caixa.classList.toggle('erro-campo', !cabe);
  if (SEM_PESO.includes(comb.js)) {
    caixa.textContent = `${texto} · o combinador ${comb.tipo} não usa peso por definição matemática`;
  }
}

/** No modo percentual, mexer num peso redistribui a diferença entre os NÃO travados — é o que "trava" quer
    dizer. Nenhum peso vira negativo: se os livres não têm folga, a mudança é recusada e a tela diz por quê. */
function aplicarPercentual(idMexido, novo) {
  const ids = fatores().map((f) => f.id);
  const livres = ids.filter((i) => i !== idMexido && !estado.travados.has(i));
  const fixos = ids.filter((i) => i !== idMexido && estado.travados.has(i));
  const somaFixos = fixos.reduce((a, i) => a + Number(estado.pesos[i]), 0);
  const folga = 100 - somaFixos - novo;
  if (!livres.length || folga < -1e-9) {
    el('aviso').erro('não há folga nos pesos livres para fechar 100: destrave um fator ou baixe outro peso.');
    return false;
  }
  const somaLivres = livres.reduce((a, i) => a + Number(estado.pesos[i]), 0);
  for (const i of livres) {
    estado.pesos[i] = somaLivres > 0 ? (Number(estado.pesos[i]) / somaLivres) * folga : folga / livres.length;
  }
  estado.pesos[idMexido] = novo;
  el('aviso').limpar();
  return true;
}

function definirPeso(id, novo) {
  const w = Math.min(Math.max(Number(novo), 0), PESO_MAX);
  if (!Number.isFinite(w)) return;
  // ACHADO no e2e: o campo de número dispara `change` OUTRA VEZ ao perder o foco, com o MESMO valor. Sem esta
  // saída, a lista era redesenhada entre o apertar e o soltar do botão em que o usuário acabara de clicar, o
  // nó era trocado e o clique se perdia no ar — a explicação simplesmente não abria. Peso que não mudou não
  // redesenha nada.
  if (Number(estado.pesos[id]) === w) return;
  if (estado.modoPeso === 'percentual') {
    if (!aplicarPercentual(id, w)) return;
    desenharFatores();
  } else {
    estado.pesos[id] = w;
  }
  desenharSomaPesos();
  recombinar();
}

function desenharFatores() {
  const ul = el('fatores-lista');
  limpar(ul);
  const fichas = fatores();
  if (!fichas.length) {
    ul.append(h('li', { class: 'fraco' }, 'nenhum fator ainda; use "adicionar fator".'));
    return;
  }
  for (const f of fichas) {
    const valor = Number(estado.pesos[f.id] ?? f.peso_modelo);
    const faixa = h('input', {
      type: 'range', min: 0, max: PESO_MAX, step: 0.1, value: String(valor),
      id: `faixa-${f.id}`, 'aria-label': `peso de ${f.nome}`,
      disabled: estado.modoPeso === 'percentual' && estado.travados.has(f.id),
    });
    const caixa = h('input', {
      type: 'number', min: 0, max: PESO_MAX, step: 0.1, value: String(valor),
      id: `peso-${f.id}`, 'aria-label': `peso de ${f.nome} em número`,
    });
    faixa.addEventListener('input', () => { caixa.value = faixa.value; definirPeso(f.id, faixa.value); });
    caixa.addEventListener('change', () => { faixa.value = caixa.value; definirPeso(f.id, caixa.value); });
    const trava = h('input', {
      type: 'checkbox', id: `trava-${f.id}`, checked: estado.travados.has(f.id),
      'aria-label': `travar o peso de ${f.nome}`,
    });
    trava.addEventListener('change', () => {
      if (trava.checked) estado.travados.add(f.id); else estado.travados.delete(f.id);
      desenharFatores();
    });
    const bPrevisao = h('button', { type: 'button', class: 'pequeno', id: `previsao-${f.id}` }, 'pré-visualizar');
    bPrevisao.addEventListener('click', () => abrirPrevisao(f));
    const bTransf = h('button', { type: 'button', class: 'pequeno', id: `transformar-${f.id}` }, 'transformação');
    bTransf.addEventListener('click', () => abrirTransformacao(f));
    const bRemover = h('button', { type: 'button', class: 'pequeno', id: `remover-${f.id}` }, 'remover');
    bRemover.addEventListener('click', () => removerFator(f.id));

    ul.append(h('li', { class: 'motor-fator', dataset: { fator: f.id } },
      h('div', { class: 'motor-fator-topo' }, h('strong', {}, f.nome), h('code', {}, f.id)),
      h('div', { class: 'fraco' }, f.criterio || `${f.direcao === 'menor_melhor' ? 'menor é melhor' : 'maior é melhor'} · ${f.unidade}`),
      h('div', { class: 'fraco' }, `fonte: ${f.fonte} · base: ${f.base} · transformação: ${(f.transformacao || {}).tipo || '—'}`),
      f.proxy_descricao ? h('div', { class: 'fraco' }, `proxy declarado: ${f.proxy_descricao}`) : null,
      f.nao_sustenta ? h('div', { class: 'fraco' }, `não sustenta: ${f.nao_sustenta}`) : null,
      h('div', { class: `motor-peso${estado.travados.has(f.id) ? ' travado' : ''}` },
        faixa, caixa,
        h('label', { for: `trava-${f.id}`, class: 'fraco' }, trava, ' travar')),
      h('div', { class: 'motor-fator-acoes' }, bPrevisao, bTransf, bRemover)));
  }
  desenharSomaPesos();
}

function desenharVetos() {
  const ul = el('vetos-lista');
  limpar(ul);
  const rest = (estado.definicao && estado.definicao.restricoes) || [];
  if (!rest.length) {
    ul.append(h('li', { class: 'fraco' }, 'nenhum veto declarado neste modelo.'));
    return;
  }
  for (const r of rest) {
    const bRemover = h('button', { type: 'button', class: 'pequeno', id: `remover-veto-${r.id}` }, 'remover');
    bRemover.addEventListener('click', () => removerVeto(r.id));
    ul.append(h('li', { class: 'motor-veto', dataset: { veto: r.id } },
      h('strong', {}, r.nome),
      h('span', { class: 'fraco' }, `base: ${r.base === 'norma' ? 'a norma veda' : 'precaução da equipe'}${r.base_legal ? ` (${r.base_legal})` : ''}`),
      h('span', { class: 'fraco' }, `regra: ${r.regra.tipo}${r.buffer_m ? ` · faixa de ${r.buffer_m} m` : ''}`),
      h('span', { class: 'fraco' }, r.motivo || 'sem motivo escrito'),
      bRemover));
  }
}

function desenharLegenda() {
  const ul = el('legenda-rampa');
  limpar(ul);
  for (const item of itensDaLegenda()) {
    ul.append(h('li', {},
      h('span', { class: 'motor-amostra', style: `background:${item.cor};${item.contorno ? `border-color:${item.contorno}` : ''}` }),
      item.rotulo));
  }
}

function desenharResumoNotas() {
  const caixa = el('resumo-notas');
  if (!estado.resultado) { caixa.textContent = ''; return; }
  const notas = estado.resultado.fav.filter((v) => v !== null && !Number.isNaN(v));
  const vetadas = estado.resultado.vetado.filter(Boolean).length;
  const semNota = estado.resultado.fav.length - notas.length;
  caixa.textContent = `${estado.resultado.fav.length} unidades · ${vetadas} vetadas · ${semNota} sem nota`;
}

function linhasOrdenadas() {
  if (!estado.resultado) return [];
  const linhas = estado.matriz.unidades.map((u, i) => ({
    id: u.unidade_id,
    favorabilidade: estado.resultado.fav[i],
    cobertura: estado.resultado.cobertura[i],
    vetado: estado.resultado.vetado[i],
    motivo: estado.resultado.motivo[i],
    indice: i,
  }));
  linhas.sort((a, b) => {
    const va = a.favorabilidade === null || Number.isNaN(a.favorabilidade) ? -1 : a.favorabilidade;
    const vb = b.favorabilidade === null || Number.isNaN(b.favorabilidade) ? -1 : b.favorabilidade;
    return vb - va;
  });
  return linhas;
}

function desenharMelhores() {
  const tabela = el('tabela-melhores');
  const quantas = Math.max(1, Number(el('quantas').value) || 20);
  // ACHADO no e2e: numa coluna de 320 px, uma coluna de ações no extremo direito fica FORA da parte visível
  // da tabela (a rolagem horizontal a esconde) e o "clique = explicação" da hipótese vira inalcançável no
  // painel estreito. Por isso o próprio identificador da unidade é o botão: fica na primeira coluna, sempre
  // à vista, e é também o alvo mais óbvio para quem lê a lista.
  tabela.colunas = [
    { chave: 'id',
      titulo: 'unidade',
      formatar: (v) => {
        const b = h('button', { type: 'button', class: 'pequeno', dataset: { unidade: v } }, v);
        b.addEventListener('click', () => abrirExplicacao(v));
        return b;
      } },
    { chave: 'favorabilidade', titulo: 'favorabilidade', formatar: (v) => numero(v) },
    { chave: 'cobertura', titulo: 'cobertura', formatar: (v) => (typeof v === 'number' ? `${numero(v * 100)}%` : '—') },
    { chave: 'vetado', titulo: 'veto', formatar: (v, l) => (v ? (l.motivo || 'vetado') : '—') },
  ];
  tabela.chave = 'id';
  tabela.vazio = estado.execucao ? 'nenhuma unidade com fator extraído nesta execução ainda.' : 'ainda sem execução.';
  tabela.linhas = linhasOrdenadas().slice(0, quantas);
}

/* ---------------------------------------------------------------- explicação de uma unidade */
function abrirExplicacao(unidadeId) {
  const i = estado.matriz.unidades.findIndex((u) => u.unidade_id === unidadeId);
  if (i < 0 || !estado.resultado) return;
  const u = estado.matriz.unidades[i];
  const fichas = estado.matriz.fatores;
  const somaPesosPresentes = fichas.reduce((a, f, j) => (u.favorabilidades[j] === null ? a : a + Number(estado.pesos[f.id])), 0);
  const corpo = h('div', {},
    h('p', { class: 'fraco' }, 'os pesos abaixo são os que você escolheu agora nesta tela, não uma medida.'),
    h('dl', { class: 'motor-dl' },
      h('dt', {}, 'unidade'), h('dd', {}, unidadeId),
      h('dt', {}, 'favorabilidade'), h('dd', { id: 'exp-favorabilidade' }, numero(estado.resultado.fav[i], 2)),
      h('dt', {}, 'cobertura'), h('dd', {}, `${numero(estado.resultado.cobertura[i] * 100)}%`),
      h('dt', {}, 'vetado'), h('dd', {}, estado.resultado.vetado[i] ? (estado.resultado.motivo[i] || 'sim') : 'não')),
    h('div', { class: 'tabela-rolagem' },
      h('table', { class: 'tabela', id: 'exp-tabela' },
        h('thead', {}, h('tr', {},
          h('th', {}, 'fator'), h('th', {}, 'valor bruto'), h('th', {}, 'unidade'),
          h('th', {}, 'favorabilidade'), h('th', {}, 'peso'), h('th', {}, 'contribuição'))),
        h('tbody', {}, fichas.map((f, j) => {
          const fav = u.favorabilidades[j];
          const w = Number(estado.pesos[f.id]);
          const contrib = fav === null || somaPesosPresentes <= 0 ? null : (w / somaPesosPresentes) * fav;
          return h('tr', {},
            h('td', {}, `${f.nome} (${f.id})`),
            h('td', {}, u.brutos[j] === null || u.brutos[j] === undefined ? 'sem dado' : numero(u.brutos[j], 3)),
            h('td', {}, f.unidade),
            h('td', {}, fav === null ? 'sem nota' : numero(fav, 2)),
            h('td', {}, numero(w, 2)),
            h('td', {}, contrib === null ? '—' : numero(contrib, 2)));
        })))),
    h('p', {}, h('a', { href: `/amc/explicacao/${encodeURIComponent(estado.execucao.id)}/${encodeURIComponent(unidadeId)}`,
                        id: 'exp-link-servidor' },
      'ver a explicação recalculada pelo servidor sobre os pesos gravados na execução')));
  el('dialogo').abrir({ titulo: 'por que esta unidade tem esta nota', corpo, botoes: [{ id: 'ok', rotulo: 'fechar' }] });
}

/* ---------------------------------------------------------------- pré-visualização da transformação */
function desenharHistograma(hist, curva) {
  const largura = 320;
  const altura = 140;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
  svg.setAttribute('role', 'img');
  const contagens = hist.contagens || [];
  const maxC = Math.max(1, ...contagens);
  const larguraBarra = contagens.length ? largura / contagens.length : largura;
  contagens.forEach((c, i) => {
    const alt = (c / maxC) * (altura - 8);
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r.setAttribute('class', 'barra');
    r.setAttribute('x', String(i * larguraBarra));
    r.setAttribute('y', String(altura - alt));
    r.setAttribute('width', String(Math.max(1, larguraBarra - 1)));
    r.setAttribute('height', String(alt));
    svg.append(r);
  });
  const pares = (curva && curva.pares) || [];
  if (pares.length > 1) {
    const xs = pares.map((p) => p[0]);
    const x0 = Math.min(...xs); const x1 = Math.max(...xs);
    const d = pares.filter((p) => p[1] !== null).map((p, i) => {
      const x = x1 > x0 ? ((p[0] - x0) / (x1 - x0)) * largura : 0;
      const y = altura - (p[1] / 100) * (altura - 8);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    const caminho = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    caminho.setAttribute('class', 'curva');
    caminho.setAttribute('d', d);
    svg.append(caminho);
  }
  return svg;
}

function valoresBrutosDe(fatorId) {
  if (!estado.matriz) return [];
  const j = estado.matriz.fatores.findIndex((f) => f.id === fatorId);
  if (j < 0) return [];
  return estado.matriz.unidades.map((u) => u.brutos[j]);
}

async function abrirPrevisao(ficha, transformacaoCandidata = null) {
  const valores = valoresBrutosDe(ficha.id);
  const transformacao = transformacaoCandidata || ficha.transformacao;
  const corpo = h('div', { class: 'motor-previsao', id: 'previsao-corpo' });
  if (!valores.length) {
    corpo.append(h('p', { class: 'fraco' },
      'este fator ainda não foi extraído nesta execução: o histograma aparece depois de rodar. '
      + 'A tela não desenha histograma sobre valor inventado.'));
    el('dialogo').abrir({ titulo: `transformação de ${ficha.nome}`, corpo, botoes: [{ id: 'ok', rotulo: 'fechar' }] });
    return;
  }
  corpo.append(h('p', { class: 'fraco' }, 'calculando…'));
  el('dialogo').abrir({ titulo: `transformação de ${ficha.nome}`, corpo, botoes: [{ id: 'ok', rotulo: 'fechar' }] });
  const r = await enviar('/api/amc/transformacoes/previsao', { transformacao, valores });
  limpar(corpo);
  if (r.status !== 200) {
    corpo.append(h('p', { class: 'erro' }, mensagemDe(r)));
    return;
  }
  corpo.append(
    h('p', { class: 'fraco' }, `${r.json.n} valores · ${r.json.n_nulo} sem nota · transformação ${r.json.tipo}`),
    h('h3', {}, 'valor bruto'), desenharHistograma(r.json.entrada_histograma, r.json.curva),
    h('h3', {}, 'favorabilidade 0-100'), desenharHistograma(r.json.saida_histograma, null));
}

/* ---------------------------------------------------------------- edição do modelo */
function campoTexto(id, rotulo, valor = '', tipo = 'text') {
  return h('label', { class: 'campo' }, rotulo,
    h('input', { type: tipo, id, value: valor }));
}

function campoEscolha(id, rotulo, opcoes, valor) {
  const sel = h('select', { id }, opcoes.map((o) => h('option', { value: o, selected: o === valor }, o)));
  return h('label', { class: 'campo' }, rotulo, sel);
}

function camposDaTransformacao(tipo, atual = {}) {
  const area = h('div', { id: 'campos-transformacao' });
  for (const campo of CAMPOS[tipo] || []) {
    const idc = `t-${campo.nome}`;
    let valor = atual[campo.nome];
    if (campo.tipo === 'lista' && Array.isArray(valor)) valor = valor.join(',');
    else if (campo.tipo === 'bandas' && Array.isArray(valor)) valor = valor.map((b) => `${b.ate}:${b.nota}`).join('\n');
    else if (campo.tipo === 'pares' && valor && typeof valor === 'object') {
      valor = Object.entries(valor).map(([k, v]) => `${k}:${v}`).join('\n');
    }
    if (campo.tipo === 'escolha') area.append(campoEscolha(idc, campo.rotulo, campo.opcoes, valor));
    else if (campo.tipo === 'bandas' || campo.tipo === 'pares') {
      area.append(h('label', { class: 'campo' }, campo.rotulo,
        h('textarea', { id: idc, rows: 4 }, valor === undefined ? '' : String(valor))));
    } else area.append(campoTexto(idc, campo.rotulo, valor === undefined ? '' : String(valor)));
  }
  return area;
}

function lerTransformacao(tipo) {
  const t = { tipo };
  for (const campo of CAMPOS[tipo] || []) {
    const v = lerCampo(campo, (el(`t-${campo.nome}`) || {}).value);
    if (v !== undefined) t[campo.nome] = v;
  }
  return t;
}

async function camadasDisponiveis() {
  const [itens, acervo] = await Promise.all([
    obter('/api/itens?limite=200'),
    obter('/api/acervo/camadas'),
  ]);
  const lista = [];
  if (itens.status === 200) {
    for (const it of itens.json.itens || itens.json.resultados || []) {
      lista.push({ rotulo: `catálogo · ${it.titulo}`, tipo: 'item', id: it.id });
    }
  }
  if (acervo.status === 200) {
    for (const c of acervo.json.camadas || []) {
      lista.push({ rotulo: `acervo · ${c.view_nome}${c.assinada ? '' : ' (não assinada)'}`,
                   tipo: 'acervo', id: `${c.fonte_id}/${c.schema_origem}.${c.tabela_origem}` });
    }
  }
  return lista;
}

async function abrirTransformacao(ficha) {
  const tipoAtual = (ficha.transformacao || {}).tipo || 'linear';
  const sel = h('select', { id: 'transformacao-tipo' }, TIPOS.map((t) => h('option', { value: t, selected: t === tipoAtual }, t)));
  const area = h('div', { class: 'campo' }, camposDaTransformacao(tipoAtual, ficha.transformacao || {}));
  const corpo = h('div', { class: 'form' }, h('label', { class: 'campo' }, 'tipo', sel), area);
  sel.addEventListener('change', () => {
    limpar(area).append(camposDaTransformacao(sel.value, {}));
  });
  const bPrever = h('button', { type: 'button', class: 'pequeno', id: 'prever-agora' }, 'pré-visualizar histograma');
  bPrever.addEventListener('click', () => {
    try {
      abrirPrevisao(ficha, lerTransformacao(el('transformacao-tipo').value));
    } catch (e) { el('aviso').erro(String(e.message || e)); }
  });
  corpo.append(bPrever);
  const escolha = await el('dialogo').abrir({
    titulo: `transformação de ${ficha.nome}`, corpo,
    botoes: [{ id: 'salvar', rotulo: 'salvar no modelo', classe: 'botao' }, { id: 'cancelar', rotulo: 'cancelar' }],
  });
  if (escolha !== 'salvar') return;
  try {
    const nova = lerTransformacao(el('transformacao-tipo') ? el('transformacao-tipo').value : tipoAtual);
    const f = estado.definicao.fatores.find((x) => x.id === ficha.id);
    f.transformacao = nova;
    await salvarModelo('transformação alterada; rode de novo para a extração usar a nova curva');
  } catch (e) {
    el('aviso').erro(String(e.message || e));
  }
}

async function abrirAdicionarFator() {
  const camadas = await camadasDisponiveis();
  const selCamada = h('select', { id: 'f-camada' },
    camadas.map((c, i) => h('option', { value: String(i) }, c.rotulo)));
  const gruposExtrator = h('select', { id: 'f-extrator' },
    Object.entries(EXTRATORES).flatMap(([grupo, lista]) => lista.map((x) => h('option', { value: x }, `${grupo} · ${x}`))));
  const selTipo = h('select', { id: 'transformacao-tipo' }, TIPOS.map((t) => h('option', { value: t, selected: t === 'linear' }, t)));
  const area = h('div', { class: 'campo' }, camposDaTransformacao('linear', {}));
  selTipo.addEventListener('change', () => limpar(area).append(camposDaTransformacao(selTipo.value, {})));
  const corpo = h('div', { class: 'form' },
    campoTexto('f-id', 'identificador (letras minúsculas, dígitos e _)'),
    campoTexto('f-nome', 'nome'),
    campoTexto('f-criterio', 'critério (o que se quer, uma linha)'),
    campoTexto('f-fonte', 'fonte (quem publica e quando)'),
    campoTexto('f-unidade', 'unidade de medida do valor bruto'),
    campoEscolha('f-direcao', 'direção', ['maior_melhor', 'menor_melhor'], 'maior_melhor'),
    campoEscolha('f-base', 'base do peso', ['norma', 'engenharia', 'preferencia'], 'engenharia'),
    h('label', { class: 'campo' }, 'camada', selCamada),
    campoTexto('f-banda', 'banda do raster (vazio se não for raster)'),
    campoTexto('f-atributo', 'atributo da camada vetorial (vazio se não usar)'),
    h('label', { class: 'campo' }, 'extrator', gruposExtrator),
    h('label', { class: 'campo' }, 'transformação', selTipo),
    area,
    campoTexto('f-peso', 'peso inicial', '1'));
  const escolha = await el('dialogo').abrir({
    titulo: 'adicionar fator', corpo,
    botoes: [{ id: 'adicionar', rotulo: 'adicionar', classe: 'botao' }, { id: 'cancelar', rotulo: 'cancelar' }],
  });
  if (escolha !== 'adicionar') return;
  try {
    const camada = camadas[Number(el('f-camada').value)];
    if (!camada) throw new Error('escolha uma camada: sem camada não há valor bruto para extrair.');
    const ref = { tipo: camada.tipo, id: camada.id };
    const banda = (el('f-banda').value || '').trim();
    const atributo = (el('f-atributo').value || '').trim();
    if (banda) ref.banda = Number(banda);
    if (atributo) ref.atributo = atributo;
    const novo = {
      id: (el('f-id').value || '').trim(),
      nome: (el('f-nome').value || '').trim(),
      criterio: (el('f-criterio').value || '').trim() || undefined,
      fonte: (el('f-fonte').value || '').trim(),
      unidade: (el('f-unidade').value || '').trim(),
      direcao: el('f-direcao').value,
      base: el('f-base').value,
      camada: ref,
      extrator: { tipo: el('f-extrator').value },
      transformacao: lerTransformacao(el('transformacao-tipo').value),
      peso: Number(el('f-peso').value),
    };
    if (!/^[a-z][a-z0-9_]{0,31}$/.test(novo.id)) {
      throw new Error('o identificador do fator tem de começar por letra minúscula e usar só letras, dígitos e _');
    }
    estado.definicao.fatores.push(novo);
    estado.pesos[novo.id] = novo.peso;
    await salvarModelo('fator acrescentado; rode para extrair o valor bruto dele');
  } catch (e) {
    el('aviso').erro(String(e.message || e));
  }
}

async function abrirAdicionarVeto() {
  const camadas = await camadasDisponiveis();
  const selCamada = h('select', { id: 'v-camada' }, camadas.map((c, i) => h('option', { value: String(i) }, c.rotulo)));
  const corpo = h('div', { class: 'form' },
    campoTexto('v-id', 'identificador'),
    campoTexto('v-nome', 'nome'),
    campoEscolha('v-base', 'base', ['norma', 'precaucao'], 'precaucao'),
    campoTexto('v-base-legal', 'base legal (só quando a base é norma)'),
    campoTexto('v-fonte', 'fonte'),
    h('label', { class: 'campo' }, 'camada', selCamada),
    campoTexto('v-buffer', 'faixa em metros', '0'),
    campoEscolha('v-regra', 'regra', ['intersecta', 'fracao_area_minima', 'valor_raster', 'atributo_igual'], 'intersecta'),
    campoTexto('v-fracao', 'fração mínima (só para fracao_area_minima)'),
    campoTexto('v-motivo', 'motivo que a unidade vetada carrega'));
  const escolha = await el('dialogo').abrir({
    titulo: 'marcar veto', corpo,
    botoes: [{ id: 'adicionar', rotulo: 'marcar', classe: 'botao' }, { id: 'cancelar', rotulo: 'cancelar' }],
  });
  if (escolha !== 'adicionar') return;
  try {
    const camada = camadas[Number(el('v-camada').value)];
    if (!camada) throw new Error('escolha a camada que define o veto.');
    const regra = { tipo: el('v-regra').value };
    if (regra.tipo === 'fracao_area_minima') regra.fracao_minima = Number(el('v-fracao').value);
    const base = el('v-base').value;
    const novo = {
      id: (el('v-id').value || '').trim(),
      nome: (el('v-nome').value || '').trim(),
      base,
      base_legal: base === 'norma' ? ((el('v-base-legal').value || '').trim() || undefined) : undefined,
      fonte: (el('v-fonte').value || '').trim(),
      camada: { tipo: camada.tipo, id: camada.id },
      buffer_m: Number(el('v-buffer').value) || undefined,
      regra,
      motivo: (el('v-motivo').value || '').trim() || undefined,
    };
    estado.definicao.restricoes = estado.definicao.restricoes || [];
    estado.definicao.restricoes.push(novo);
    await salvarModelo('veto marcado; rode para aplicá-lo às unidades');
  } catch (e) {
    el('aviso').erro(String(e.message || e));
  }
}

async function removerFator(id) {
  estado.definicao.fatores = estado.definicao.fatores.filter((f) => f.id !== id);
  delete estado.pesos[id];
  estado.travados.delete(id);
  await salvarModelo('fator removido');
}

async function removerVeto(id) {
  estado.definicao.restricoes = (estado.definicao.restricoes || []).filter((r) => r.id !== id);
  await salvarModelo('veto removido');
}

/** Toda edição do modelo cria uma VERSÃO nova no servidor (o hash muda); a execução em mãos continua
    apontando a versão antiga — por isso a tela diz que é preciso rodar de novo, em vez de fingir que o
    mapa na tela já reflete a mudança. */
async function salvarModelo(nota) {
  const r = await alterar(`/api/amc/modelos/${encodeURIComponent(estado.modeloId)}`, { definicao: estado.definicao });
  if (r.status !== 200) {
    el('aviso').erro(mensagemDe(r));
    return false;
  }
  el('aviso').mostrar(`${nota}.`, 'info');
  desenharFatores();
  desenharVetos();
  desenharContexto();
  return true;
}

/* ---------------------------------------------------------------- rodar (extração como job) */
async function rodar() {
  if (!estado.modeloId || !estado.conjuntoId) {
    el('aviso').erro('sem modelo ou sem conjunto de unidades não há o que rodar.');
    return;
  }
  el('rodar').disabled = true;
  const r = await enviar('/api/amc/execucoes', {
    modelo_id: estado.modeloId, conjunto_id: estado.conjuntoId, pesos: estado.pesos,
  });
  el('rodar').disabled = false;
  if (r.status !== 201) {
    el('aviso').erro(mensagemDe(r));
    return;
  }
  estado.execucao = r.json;
  el('estado-execucao').textContent = `execução ${r.json.id} · ${r.json.estado}`;
  await carregarMatriz();
  acompanhar();
}

let relogio = null;
function acompanhar() {
  clearInterval(relogio);
  // sem job não há o que acompanhar: uma execução 'registrada' cujo modelo não tem fator do acervo fica
  // nesse estado até alguém rodar a extração, e um relógio batendo no servidor a cada 3 s não a muda.
  if (!estado.execucao || !estado.execucao.job_id || !ESTADOS_EM_CURSO.has(estado.execucao.estado)) return;
  relogio = setInterval(async () => {
    const r = await obter(`/api/amc/execucoes/${encodeURIComponent(estado.execucao.id)}`);
    if (r.status !== 200) { clearInterval(relogio); return; }
    estado.execucao = { ...estado.execucao, ...r.json };
    el('estado-execucao').textContent = `execução ${r.json.id} · ${r.json.estado}`
      + (r.json.erro ? ` · ${r.json.erro}` : '');
    if (!ESTADOS_EM_CURSO.has(r.json.estado)) {
      clearInterval(relogio);
      await carregarMatriz();
    }
  }, 3000);
}

/* ---------------------------------------------------------------- mapa */
function iniciarMapa() {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro('biblioteca de mapa ausente nesta instalação; a lista continua funcionando.');
    return null;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);
  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(`${location.origin}/static/dados/basemap/guarulhos.pmtiles`),
    center: [-46.53, -23.45],
    zoom: 9,
    attributionControl: { compact: true },
  });
  map.addControl(new window.maplibregl.NavigationControl({ visualizePitch: false }), 'top-right');
  map.addControl(new window.maplibregl.ScaleControl({ unit: 'metric' }));
  map.on('mousemove', (ev) => {
    el('coordenadas').textContent = `${ev.lngLat.lat.toFixed(5)}, ${ev.lngLat.lng.toFixed(5)} · z${map.getZoom().toFixed(1)}`;
  });
  map.on('load', () => {
    map.addSource('unidades', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: 'unidades-preenchimento', type: 'fill', source: 'unidades',
      paint: { 'fill-color': ['get', 'cor'], 'fill-opacity': 0.72 },
    });
    map.addLayer({
      id: 'unidades-contorno', type: 'line', source: 'unidades',
      paint: { 'line-color': ['get', 'contorno'], 'line-width': 0.6 },
    });
    map.on('click', 'unidades-preenchimento', (ev) => {
      const f = ev.features && ev.features[0];
      if (f) abrirExplicacao(f.properties.unidade_id);
    });
    map.on('mouseenter', 'unidades-preenchimento', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'unidades-preenchimento', () => { map.getCanvas().style.cursor = ''; });
    estado.mapaPronto = true;
    pintarMapa();
  });
  return map;
}

function pintarMapa() {
  if (!estado.mapa || !estado.mapaPronto) return;
  const fonte = estado.mapa.getSource('unidades');
  if (!fonte) return;
  if (estado.recusas.length || !estado.matriz) {
    // link recusado: o mapa fica VAZIO, não colorido com os pesos do modelo. Mostrar um mapa recolorido
    // enquanto a barra de endereço diz outra coisa é exatamente a falha que a recusa existe para evitar.
    fonte.setData({ type: 'FeatureCollection', features: [] });
    document.body.dataset.mapaPintado = '0';
    return;
  }
  const features = [];
  estado.matriz.unidades.forEach((u, i) => {
    const g = estado.geo.get(u.unidade_id);
    if (!g) return;
    const fav = estado.resultado ? estado.resultado.fav[i] : null;
    const vetado = estado.resultado ? estado.resultado.vetado[i] : u.vetado;
    features.push({
      type: 'Feature', geometry: g,
      properties: {
        unidade_id: u.unidade_id,
        favorabilidade: fav === null || Number.isNaN(fav) ? null : fav,
        cor: corDe(fav, vetado),
        contorno: '#8fa19c',
      },
    });
  });
  fonte.setData({ type: 'FeatureCollection', features });
  document.body.dataset.mapaPintado = String(features.length);
  if (features.length && !estado.enquadrou) {
    const limites = new window.maplibregl.LngLatBounds();
    for (const f of features) {
      for (const anel of (f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat())) {
        for (const c of anel) limites.extend(c);
      }
    }
    estado.mapa.fitBounds(limites, { padding: 24, duration: 0 });
    estado.enquadrou = true;
    // marca lida pelo e2e: prova que a câmera foi para as unidades, e não ficou no enquadramento inicial
    document.body.dataset.mapaEnquadrado = `${estado.mapa.getCenter().lng.toFixed(4)},`
      + `${estado.mapa.getCenter().lat.toFixed(4)},z${estado.mapa.getZoom().toFixed(1)}`;
  }
}

/* ---------------------------------------------------------------- carga */
async function carregarGeometria(conjuntoId) {
  estado.geo.clear();
  let deslocamento = 0;
  for (;;) {
    const r = await obter(`/api/amc/conjuntos/${encodeURIComponent(conjuntoId)}/unidades?limite=${UNIDADES_PAGINA}&deslocamento=${deslocamento}`);
    if (r.status !== 200) { el('aviso').erro(mensagemDe(r)); return; }
    for (const f of r.json.features) estado.geo.set(f.properties.unidade_id, f.geometry);
    deslocamento += r.json.features.length;
    if (!r.json.features.length || deslocamento >= r.json.total) break;
  }
}

async function carregarMatriz() {
  const r = await obter(`/api/amc/execucoes/${encodeURIComponent(estado.execucao.id)}/matriz?limite=${UNIDADES_PAGINA}`);
  if (r.status !== 200) { el('aviso').erro(mensagemDe(r)); return; }
  estado.matriz = r.json;
  aplicarPesosDaUrl();
  desenharFatores();
  recombinar();
}

function aplicarPesosDaUrl() {
  const fichas = fatores();
  const comb = combinadorDoModelo();
  const { pesos, erros } = lerPesos(parametros().get('w'), fichas, comb.tipo);
  estado.recusas = erros;
  desenharRecusas();
  if (!erros.length) estado.pesos = pesos;
  else estado.pesos = Object.fromEntries(fichas.map((f) => [f.id, f.peso_modelo]));
}

/* ---------------------------------------------------------------- abas de celular */
function ligarAbas() {
  const abaLista = el('aba-lista');
  const abaMapa = el('aba-mapa');
  const painel = el('painel-motor');
  const area = el('area-mapa');
  const trocar = (paraMapa) => {
    abaLista.setAttribute('aria-selected', String(!paraMapa));
    abaMapa.setAttribute('aria-selected', String(paraMapa));
    painel.hidden = paraMapa;
    area.hidden = !paraMapa;
    if (paraMapa && estado.mapa) estado.mapa.resize();
  };
  abaLista.addEventListener('click', () => trocar(false));
  abaMapa.addEventListener('click', () => trocar(true));
  const estreita = window.matchMedia('(max-width: 900px)');
  const ajustar = () => {
    el('abas').hidden = !estreita.matches;
    if (!estreita.matches) { painel.hidden = false; area.hidden = false; }
    else trocar(abaMapa.getAttribute('aria-selected') === 'true');
  };
  estreita.addEventListener('change', ajustar);
  ajustar();
}

/* ---------------------------------------------------------------- entrada */
async function principal() {
  const aviso = el('aviso');
  // o dicionário tem de chegar ANTES de montarLayout: a barra lateral é montada com t() e, sem ele, a tela
  // mostra as chaves cruas (nav.inicio, app.nome) — foi o que a primeira captura deste item flagrou
  await carregarIdioma();
  const r = await obter('/api/eu');
  if (r.status === 401) { irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  marcarSessao(!!usuario);
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/amc/motor' });
  desenharLegenda();
  ligarAbas();

  const p = parametros();
  const execucaoId = p.get('execucao');
  try {
    if (execucaoId) {
      const re = await obter(`/api/amc/execucoes/${encodeURIComponent(execucaoId)}`);
      if (re.status !== 200) { aviso.erro(mensagemDe(re)); pronto(); return; }
      estado.execucao = re.json;
      estado.definicao = re.json.definicao;
      estado.modeloId = re.json.modelo_id;
      estado.conjuntoId = re.json.conjunto_id;
      el('estado-execucao').textContent = `execução ${re.json.id} · ${re.json.estado}`;
    } else {
      estado.modeloId = p.get('modelo');
      estado.conjuntoId = p.get('conjunto');
      if (!estado.modeloId || !estado.conjuntoId) {
        aviso.erro('abra a tela a partir de um conjunto de unidades: /amc/motor?modelo=<id>&conjunto=<id> '
          + 'ou /amc/motor?execucao=<id>.');
        pronto();
        return;
      }
      const rm = await obter(`/api/amc/modelos/${encodeURIComponent(estado.modeloId)}`);
      if (rm.status !== 200) { aviso.erro(mensagemDe(rm)); pronto(); return; }
      estado.definicao = rm.json.definicao;
    }
    desenharContexto();
    aplicarPesosDaUrl();
    desenharFatores();
    desenharVetos();
    estado.mapa = iniciarMapa();
    await carregarGeometria(estado.conjuntoId);
    if (estado.execucao) { await carregarMatriz(); acompanhar(); }
  } catch (e) {
    aviso.erro(`não foi possível montar a tela: ${e.message || e}`);
  }

  el('rodar').addEventListener('click', () => rodar());
  el('adicionar-fator').addEventListener('click', () => abrirAdicionarFator());
  el('adicionar-veto').addEventListener('click', () => abrirAdicionarVeto());
  el('quantas').addEventListener('change', () => desenharMelhores());
  el('modo-peso').addEventListener('change', () => {
    estado.modoPeso = el('modo-peso').value;
    if (estado.modoPeso === 'percentual') {
      const soma = somaPesos();
      if (soma > 0) for (const k of Object.keys(estado.pesos)) estado.pesos[k] = (estado.pesos[k] / soma) * 100;
    }
    desenharFatores();
    recombinar();
  });
  el('usar-pesos-do-modelo').addEventListener('click', () => {
    estado.recusas = [];
    estado.pesos = Object.fromEntries(fatores().map((f) => [f.id, f.peso_modelo]));
    desenharRecusas();
    desenharFatores();
    recombinar();
  });
  el('copiar-link').addEventListener('click', async () => {
    if (!estado.execucao) { el('aviso').erro('o link só carrega pesos depois de rodar.'); return; }
    const link = montarLink(location.origin, estado.execucao.id, estado.pesos);
    const ok = await copiar(link, el('contexto-lista'));
    el('aviso').mostrar(ok ? 'link copiado com os pesos desta leitura.' : `copie o link: ${link}`, 'ok');
  });
  pronto();
}

principal();
