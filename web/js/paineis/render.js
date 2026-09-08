/* plat · painel — motor de renderização do documento de painel (item L2-06-a-modelo-painel-fontes). Módulo ES
   puro (sem framework), usado pela tela autenticada (/paineis/{id}, painel.js) E pela página anônima de link
   (/c/{token}, catalogo/compartilhado.js) — as duas só diferem em QUEM busca o dado (`buscarDados`).

   Regra do portão que decide a forma deste módulo: um ciclo de atualização faz UMA requisição POR FONTE, nunca
   uma por elemento — `agruparPorFonte()` monta, para cada fonte referenciada por ao menos um elemento, um único
   objeto `pedidos` (chave = id do elemento) e chama `buscarDados(fonteId, pedidos, filtroExecucao)` uma vez; a
   agregação (contagem/soma/categorias/linhas) roda inteira no servidor (`app.paineis.dados`), nunca aqui — este
   módulo só formata o `resultado` que volta pronto.

   Responsivo: a posição de cada elemento vem de `--gx/--gy/--gw/--gh` (custom properties, `painel.css` os lê no
   grid); em viewport estreito o `painel.css` zera esses quatro para `auto`, e a ordem visual passa a ser a
   ORDEM DO DOCUMENTO (a mesma ordem de `corpo.elementos`) — nenhum JS decide o empilhamento, é puro CSS. */

import { h, limpar } from '../base/dom.js';
import { TIPOS_COM_FONTE, pedidoDoElemento, renderElemento } from './elementos.js';

/* item L2-06-b-elementos-basicos: os tipos de elemento, o pedido de cada um e o desenho vivem em
   `elementos.js`; este módulo continua responsável só pela GRADE, pelo ciclo de atualização (uma requisição
   por fonte) e pelo estado de execução (filtros globais, ordenação de tabela, paginação de lista, extensão do
   mapa como filtro). */

function agruparPorFonte(elementos, ajustes = {}) {
  const porFonte = new Map();
  for (const el of elementos) {
    if (!TIPOS_COM_FONTE.has(el.tipo) || !el.fonte) continue;
    const pedido = pedidoDoElemento(el);
    if (!pedido) continue;
    const ajuste = ajustes[el.id];
    if (ajuste) Object.assign(pedido, ajuste);
    if (!porFonte.has(el.fonte)) porFonte.set(el.fonte, {});
    porFonte.get(el.fonte)[el.id] = pedido;
  }
  return porFonte;
}

function renderElementoVazio(elemento) {
  const div = h('div', {
    class: `painel-el painel-el-${elemento.tipo}`,
    'data-id': elemento.id,
    'data-tipo': elemento.tipo,
    style: `--gx:${elemento.x};--gy:${elemento.y};--gw:${elemento.largura};--gh:${elemento.altura}`,
  });
  if (elemento.titulo) div.append(h('h3', { class: 'painel-el-titulo' }, elemento.titulo));
  const corpo = h('div', { class: 'painel-el-corpo', 'data-papel': 'corpo' });
  if (elemento.tipo === 'texto') {
    corpo.textContent = (elemento.opcoes || {}).texto || '';
  } else if (!TIPOS_COM_FONTE.has(elemento.tipo)) {
    corpo.dataset.semFonte = '1';   // legenda, cabeçalho e texto rico sem campos: desenham na montagem
  } else {
    corpo.textContent = '…';
    corpo.setAttribute('aria-busy', 'true');
  }
  div.append(corpo);
  return div;
}

function corpoDoElemento(container, elemento) {
  return container.querySelector(`.painel-el[data-id="${CSS.escape(elemento.id)}"] [data-papel="corpo"]`);
}

function pintarResultado(container, elemento, resultado, ctx) {
  const corpo = corpoDoElemento(container, elemento);
  if (!corpo) return;
  corpo.removeAttribute('aria-busy');
  const caixa = corpo.closest('.painel-el');
  const marcarVazio = (vazio) => { if (caixa) caixa.dataset.vazio = vazio ? '1' : '0'; };
  const r = renderElemento(corpo, elemento, resultado, ctx);
  if (r && typeof r.then === 'function') { r.then((vazio) => marcarVazio(vazio)); return; }
  marcarVazio(r);
}

/**
 * Monta o painel dentro de `container` a partir de `corpo` (o `dados.corpo` do documento, já migrado para a
 * versão vigente). `buscarDados(fonteId, pedidos, filtroExecucao)` devolve `{resultados}`.
 * `parametrosUrlIniciais` (opcional) é `{campo: valor}` já lido de `location.search` pelo chamador (a tela
 * decide se os nomes de parâmetro vêm de query string ou de outro lugar — este módulo só recebe valores).
 * Devolve `{atualizarFiltro(campo, valor), destruir(), aguardarPrimeiraCarga}`.
 */
export function montarPainel(container, corpo, buscarDados, parametrosUrlIniciais = {}) {
  const grade = corpo.grade || { colunas: 12, linha_px: 36 };
  const elementos = corpo.elementos || [];
  const fontesPorId = new Map((corpo.fontes || []).map((f) => [f.id, f]));

  limpar(container);
  container.classList.add('painel-grade');
  container.style.setProperty('--painel-colunas', grade.colunas || 12);
  container.style.setProperty('--painel-linha-px', `${grade.linha_px || 36}px`);
  if ((corpo.tema || {}).modo === 'escuro') container.classList.add('painel-escuro');

  for (const el of elementos) container.append(renderElementoVazio(el));

  const filtroExecucao = { ...parametrosUrlIniciais };
  const temporizadores = [];
  const ajustes = {};              // por elemento: paginação da lista (deslocamento)
  const estados = new Map();       // por elemento: ordenação da tabela (só no cliente, sobre a página lida)
  const ultimos = new Map();       // último resultado por elemento (repintar sem nova requisição)
  const geracoes = new Map();      // número de ordem do último pedido de cada fonte (descarta resposta atrasada)
  let atualizadoEm = null;

  const ctx = {
    estado(id, inicial) {
      if (!estados.has(id)) estados.set(id, { ...inicial });
      return estados.get(id);
    },
    repintar(id) {
      const el = elementos.find((e) => e.id === id);
      if (el) pintarResultado(container, el, ultimos.get(id), ctx);
    },
    paginar(id, deslocamento) {
      ajustes[id] = { ...(ajustes[id] || {}), deslocamento: Math.max(0, deslocamento) };
      const el = elementos.find((e) => e.id === id);
      if (el) return atualizarFonte(el.fonte);
      return Promise.resolve();
    },
    /* extensão do mapa como filtro dos OUTROS elementos: entra no filtro de execução como caixa em
       EPSG:4326 (`__extensao`), que o servidor transforma em condição espacial na coluna de geometria */
    filtrarExtensao(caixa) {
      if (!caixa) delete filtroExecucao.__extensao;
      else filtroExecucao.__extensao = caixa.map((v) => Number(v).toFixed(6)).join(',');
      container.dataset.extensao = filtroExecucao.__extensao || '';
      return atualizarTudo();
    },
    textoAtualizacao() {
      if (!atualizadoEm) return 'atualizando…';
      return `atualizado às ${atualizadoEm.toLocaleTimeString('pt-BR')}`;
    },
  };

  function porFonteAtual() { return agruparPorFonte(elementos, ajustes); }

  async function atualizarFonte(fonteId) {
    const pedidos = porFonteAtual().get(fonteId);
    if (!pedidos || !Object.keys(pedidos).length) return;
    // uma requisição por fonte, mas quem usa troca de filtro mais depressa do que o servidor responde:
    // cada pedido leva um número de ordem e a resposta que chega atrasada é DESCARTADA (senão o painel volta
    // a mostrar o resultado do filtro anterior — a tela mentiria sobre o filtro que está na barra)
    const ordem = (geracoes.get(fonteId) || 0) + 1;
    geracoes.set(fonteId, ordem);
    let resposta;
    try {
      resposta = await buscarDados(fonteId, pedidos, filtroExecucao);
      if (geracoes.get(fonteId) !== ordem) return;
    } catch {
      if (geracoes.get(fonteId) !== ordem) return;
      for (const elId of Object.keys(pedidos)) {
        const el = elementos.find((e) => e.id === elId);
        if (el) { ultimos.set(elId, null); pintarResultado(container, el, null, ctx); }
      }
      return;
    }
    const resultados = (resposta && resposta.resultados) || {};
    for (const elId of Object.keys(pedidos)) {
      const el = elementos.find((e) => e.id === elId);
      if (el) { ultimos.set(elId, resultados[elId]); pintarResultado(container, el, resultados[elId], ctx); }
    }
  }

  function pintarSemFonte() {
    for (const el of elementos) {
      if (TIPOS_COM_FONTE.has(el.tipo) || el.tipo === 'texto') continue;
      pintarResultado(container, el, null, ctx);
    }
  }

  function marcarAtualizacao() {
    atualizadoEm = new Date();
    for (const alvo of container.querySelectorAll('[data-papel="atualizado"]')) {
      alvo.textContent = ctx.textoAtualizacao();
    }
  }

  async function atualizarTudo() {
    await Promise.all([...porFonteAtual().keys()].map((fid) => atualizarFonte(fid)));
    marcarAtualizacao();
  }

  pintarSemFonte();

  for (const fonteId of porFonteAtual().keys()) {
    const fonte = fontesPorId.get(fonteId);
    const intervaloS = fonte && fonte.atualizacao_s;
    if (intervaloS && intervaloS > 0) {
      temporizadores.push(setInterval(() => atualizarFonte(fonteId).then(marcarAtualizacao), intervaloS * 1000));
    }
  }

  const aguardarPrimeiraCarga = atualizarTudo();

  function atualizarFiltro(campo, valor) {
    if (valor === undefined || valor === null || valor === '') delete filtroExecucao[campo];
    else filtroExecucao[campo] = valor;
    for (const id of Object.keys(ajustes)) delete ajustes[id].deslocamento;  // filtro novo volta à 1ª página
    return atualizarTudo();
  }

  function destruir() {
    for (const t of temporizadores) clearInterval(t);
  }

  return { atualizarFiltro, destruir, aguardarPrimeiraCarga, filtroExecucao, filtrarExtensao: ctx.filtrarExtensao };
}

/** Constrói a barra de filtros globais (`corpo.filtros`) — um controle por filtro, chamando
 * `onMudar(campo, valor)` a cada alteração (debounce simples em texto/número). */
export function montarBarraFiltros(container, filtros, valoresIniciais, onMudar) {
  limpar(container);
  if (!filtros || !filtros.length) { container.hidden = true; return; }
  container.hidden = false;
  for (const f of filtros) {
    const campoId = `painel-filtro-${f.id}`;
    const label = h('label', { class: 'painel-filtro', for: campoId }, f.titulo || f.campo);
    const inputTipo = f.tipo === 'numero' ? 'number' : f.tipo === 'data' ? 'date' : 'text';
    const input = h('input', { type: inputTipo, id: campoId, 'data-campo': f.campo });
    if (valoresIniciais[f.campo] !== undefined) input.value = valoresIniciais[f.campo];
    let temporizador = null;
    input.addEventListener('input', () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(() => onMudar(f.campo, input.value), 250);
    });
    label.append(input);
    container.append(label);
  }
}

/** Lê `corpo.parametros_url` da query string atual: `{nome, campo}` -> `{campo: valor}`. */
export function parametrosUrlDaLocalizacao(parametrosUrl, buscaLocation = location.search) {
  const params = new URLSearchParams(buscaLocation);
  const saida = {};
  for (const p of parametrosUrl || []) {
    const v = params.get(p.nome);
    if (v !== null && v !== '') saida[p.campo] = v;
  }
  return saida;
}
