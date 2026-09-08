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

const TIPOS_COM_FONTE = new Set(['indicador', 'grafico', 'tabela']);

function formatarNumero(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
}

function pedidoDoElemento(elemento) {
  const op = elemento.opcoes || {};
  if (elemento.tipo === 'indicador') {
    return { agregacao: op.agregacao || 'contagem', campo: op.campo };
  }
  if (elemento.tipo === 'grafico') {
    return {
      agregacao: 'categorias',
      campo: op.campo_rotulo,
      agregacao_valor: op.agregacao || 'contagem',
      campo_valor: op.campo,
      max_categorias: op.max_categorias || 8,
    };
  }
  if (elemento.tipo === 'tabela') {
    return { agregacao: 'linhas', campos: op.campos, limite: op.max_linhas || 50 };
  }
  return null;
}

function agruparPorFonte(elementos) {
  const porFonte = new Map();
  for (const el of elementos) {
    if (!TIPOS_COM_FONTE.has(el.tipo) || !el.fonte) continue;
    const pedido = pedidoDoElemento(el);
    if (!pedido) continue;
    if (!porFonte.has(el.fonte)) porFonte.set(el.fonte, {});
    porFonte.get(el.fonte)[el.id] = pedido;
  }
  return porFonte;
}

function renderElementoVazio(elemento) {
  const div = h('div', {
    class: `painel-el painel-el-${elemento.tipo}`,
    'data-id': elemento.id,
    style: `--gx:${elemento.x};--gy:${elemento.y};--gw:${elemento.largura};--gh:${elemento.altura}`,
  });
  if (elemento.titulo) div.append(h('h3', { class: 'painel-el-titulo' }, elemento.titulo));
  const corpo = h('div', { class: 'painel-el-corpo', 'data-papel': 'corpo' });
  if (elemento.tipo === 'texto') {
    corpo.textContent = (elemento.opcoes || {}).texto || '';
  } else {
    corpo.textContent = '…';
    corpo.setAttribute('aria-busy', 'true');
  }
  div.append(corpo);
  return div;
}

function pintarResultado(container, elemento, resultado) {
  const corpo = container.querySelector(`.painel-el[data-id="${CSS.escape(elemento.id)}"] [data-papel="corpo"]`);
  if (!corpo) return;
  corpo.removeAttribute('aria-busy');
  limpar(corpo);
  if (!resultado) { corpo.textContent = '—'; return; }
  if (resultado.tipo === 'numero') {
    corpo.append(h('span', { class: 'painel-indicador-valor' }, formatarNumero(resultado.valor)));
    return;
  }
  if (resultado.tipo === 'categorias') {
    const linhas = resultado.linhas || [];
    const max = Math.max(1, ...linhas.map((l) => Number(l.valor) || 0));
    const lista = h('ul', { class: 'painel-grafico-barras' });
    for (const linha of linhas) {
      const pct = Math.max(2, Math.round(((Number(linha.valor) || 0) / max) * 100));
      lista.append(
        h(
          'li',
          {},
          h('span', { class: 'painel-grafico-rotulo' }, String(linha.categoria ?? '')),
          h('span', { class: 'painel-grafico-barra-fundo' }, h('span', { class: 'painel-grafico-barra', style: `width:${pct}%` })),
          h('span', { class: 'painel-grafico-valor' }, formatarNumero(linha.valor)),
        ),
      );
    }
    corpo.append(lista);
    return;
  }
  if (resultado.tipo === 'linhas') {
    const colunas = resultado.colunas || [];
    const tabela = h('table', { class: 'painel-tabela' });
    tabela.append(h('thead', {}, h('tr', {}, ...colunas.map((c) => h('th', {}, c)))));
    const tbody = h('tbody');
    for (const linha of resultado.linhas || []) {
      tbody.append(h('tr', {}, ...colunas.map((c) => h('td', {}, linha[c] === null || linha[c] === undefined ? '' : String(linha[c])))));
    }
    tabela.append(tbody);
    corpo.append(tabela);
    return;
  }
  corpo.textContent = '—';
}

/**
 * Monta o painel dentro de `container` a partir de `corpo` (o `dados.corpo` do documento, já migrado para a
 * versão vigente). `buscarDados(fonteId, pedidos, filtroExecucao)` devolve `{resultados}`.
 * `parametrosUrlIniciais` (opcional) é `{campo: valor}` já lido de `location.search` pelo chamador (a tela
 * decide se os nomes de parâmetro vêm de query string ou de outro lugar — este módulo só recebe valores).
 *
 * `opcoes.assinar(camadas, aoMudar, {aoIndisponivel})` (item L2-06-d) liga a atualização viva: quando o dado
 * muda no banco, o servidor empurra o evento e só as fontes daquela camada refazem a consulta — sem
 * recarregar a página. É OPCIONAL: a tela anônima do link compartilhado não assina (o fluxo é autenticado) e
 * continua no intervalo. Quando a assinatura existe, o intervalo de atualização de cada fonte fica DESLIGADO
 * e só entra em cena se o fluxo se declarar indisponível — é o fallback por polling que o portão pede, e é
 * assim que não se paga a consulta duas vezes.
 * `opcoes.aoAtualizar(data)` é chamado a cada carga concluída, para o "atualizado às hh:mm:ss" do cabeçalho.
 *
 * Devolve `{atualizarFiltro(campo, valor), destruir(), aguardarPrimeiraCarga}`.
 */
export function montarPainel(container, corpo, buscarDados, parametrosUrlIniciais = {}, opcoes = {}) {
  const grade = corpo.grade || { colunas: 12, linha_px: 36 };
  const elementos = corpo.elementos || [];
  const fontesPorId = new Map((corpo.fontes || []).map((f) => [f.id, f]));
  const porFonte = agruparPorFonte(elementos);

  limpar(container);
  container.classList.add('painel-grade');
  container.style.setProperty('--painel-colunas', grade.colunas || 12);
  container.style.setProperty('--painel-linha-px', `${grade.linha_px || 36}px`);
  if ((corpo.tema || {}).modo === 'escuro') container.classList.add('painel-escuro');

  for (const el of elementos) container.append(renderElementoVazio(el));

  const filtroExecucao = { ...parametrosUrlIniciais };
  const temporizadores = [];
  let assinatura = null;

  // camada -> fontes que a usam: o evento vivo chega por CAMADA e precisa virar refetch por FONTE
  const fontesPorCamada = new Map();
  for (const fonteId of porFonte.keys()) {
    const fonte = fontesPorId.get(fonteId);
    const ref = fonte && fonte.camada && fonte.camada.ref;
    if (!ref) continue;
    if (!fontesPorCamada.has(ref)) fontesPorCamada.set(ref, []);
    fontesPorCamada.get(ref).push(fonteId);
  }

  async function atualizarFonte(fonteId) {
    const pedidos = porFonte.get(fonteId);
    if (!pedidos || !Object.keys(pedidos).length) return;
    let resposta;
    try {
      resposta = await buscarDados(fonteId, pedidos, filtroExecucao);
    } catch {
      for (const elId of Object.keys(pedidos)) {
        const el = elementos.find((e) => e.id === elId);
        if (el) pintarResultado(container, el, null);
      }
      return;
    }
    const resultados = (resposta && resposta.resultados) || {};
    for (const elId of Object.keys(pedidos)) {
      const el = elementos.find((e) => e.id === elId);
      if (el) pintarResultado(container, el, resultados[elId]);
    }
    if (opcoes.aoAtualizar) opcoes.aoAtualizar(new Date());
  }

  async function atualizarTudo() {
    await Promise.all([...porFonte.keys()].map((fid) => atualizarFonte(fid)));
  }

  function ligarIntervalos() {
    if (temporizadores.length) return;
    for (const fonteId of porFonte.keys()) {
      const fonte = fontesPorId.get(fonteId);
      const intervaloS = fonte && fonte.atualizacao_s;
      if (intervaloS && intervaloS > 0) {
        temporizadores.push(setInterval(() => atualizarFonte(fonteId), intervaloS * 1000));
      }
    }
  }

  if (typeof opcoes.assinar === 'function' && fontesPorCamada.size) {
    assinatura = opcoes.assinar(
      [...fontesPorCamada.keys()],
      (camadasMudadas) => {
        const alvos = new Set();
        for (const camada of camadasMudadas) {
          for (const fonteId of fontesPorCamada.get(camada) || []) alvos.add(fonteId);
        }
        for (const fonteId of alvos) atualizarFonte(fonteId);
      },
      { aoIndisponivel: ligarIntervalos },
    );
  } else {
    ligarIntervalos();
  }

  const aguardarPrimeiraCarga = atualizarTudo();

  function atualizarFiltro(campo, valor) {
    if (valor === undefined || valor === null || valor === '') delete filtroExecucao[campo];
    else filtroExecucao[campo] = valor;
    return atualizarTudo();
  }

  function destruir() {
    for (const t of temporizadores) clearInterval(t);
    temporizadores.length = 0;
    if (assinatura) assinatura.fechar();
  }

  return { atualizarFiltro, destruir, aguardarPrimeiraCarga, filtroExecucao };
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
