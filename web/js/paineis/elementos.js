/* plat · painel — os ELEMENTOS BÁSICOS do painel (item L2-06-b-elementos-basicos): indicador, gráfico serial,
   pizza/rosca, tabela (com agrupamento e subtotal), lista paginada, mapa, detalhes, texto rico, legenda e
   cabeçalho. Um módulo por responsabilidade: aqui ficam o PEDIDO de cada elemento (o que o servidor precisa
   agregar) e o DESENHO do resultado; `render.js` só monta a grade e faz uma requisição por fonte.

   Regras do item, valendo para todos:
   - nenhum número é calculado aqui: contagem, soma, média, subtotal e total vêm do motor do L2-06-e pelo
     `app/paineis/dados.py`; este módulo só formata;
   - todo elemento tem estado "sem dado" EXPLÍCITO (`data-vazio="1"` + mensagem visível), nunca um quadro em
     branco nem um zero inventado;
   - todo elemento gráfico (indicador, serial, pizza, mapa) publica a TABELA EQUIVALENTE do mesmo dado, ligada
     por `aria-describedby` — quem usa leitor de tela lê os números, não "gráfico". */
import { h, limpar } from '../base/dom.js';
import { paraDom } from '../mapa/grafico_svg.js';
import { desenharSerie, tabelaDaSerie, rotuloDeChave } from './serie_svg.js';

let seq = 0;
const proximoId = (prefixo) => `${prefixo}-${(seq += 1)}`;

export const TIPOS_COM_FONTE = new Set([
  'indicador', 'grafico', 'serial', 'pizza', 'tabela', 'lista', 'mapa', 'detalhes', 'texto_rico',
]);

/* ------------------------------------------------------------------ formatação */
export function formatarNumero(v, op = {}) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const casas = op.casas === undefined || op.casas === null ? 2 : Math.max(0, Math.min(6, op.casas));
  let texto = n.toLocaleString('pt-BR', { minimumFractionDigits: op.casas === undefined ? 0 : casas,
    maximumFractionDigits: casas });
  if (op.percentual) texto += ' %';
  return `${op.prefixo || ''}${texto}${op.sufixo ? ` ${op.sufixo}` : ''}`;
}

export function valorDeCelula(v) {
  if (v === null || v === undefined) return '';
  return String(v);
}

/** cor da faixa a que o valor pertence: `faixas: [{de, ate, cor}]` (de/ate opcionais, ate exclusivo) */
export function corDaFaixa(valor, faixas) {
  if (valor === null || valor === undefined || !Array.isArray(faixas)) return null;
  const n = Number(valor);
  if (!Number.isFinite(n)) return null;
  for (const f of faixas) {
    const de = f.de === undefined || f.de === null ? -Infinity : Number(f.de);
    const ate = f.ate === undefined || f.ate === null ? Infinity : Number(f.ate);
    if (n >= de && n < ate) return f.cor || null;
  }
  return null;
}

/** substitui {campo} pelo valor da linha — texto puro, nunca marcação (o valor vem do dado do inquilino) */
export function preencherModelo(modelo, linha) {
  return String(modelo || '').replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, campo) => {
    const v = (linha || {})[campo];
    return v === null || v === undefined ? '' : String(v);
  });
}

/* ------------------------------------------------------------------ pedidos por tipo */
export function pedidoDoElemento(elemento) {
  const op = elemento.opcoes || {};
  const tipo = elemento.tipo;
  if (tipo === 'indicador') {
    if (op.modo === 'uma_feicao') {
      return { agregacao: 'uma_feicao', campos: op.campos, ordenacao: op.ordenacao };
    }
    return { agregacao: 'indicador', estatistica: op.estatistica || op.agregacao || 'contagem',
      campo: op.campo, percentil: op.percentil };
  }
  if (tipo === 'grafico') {  // compatibilidade com o L2-06-a (barras de uma série por categoria)
    return { agregacao: 'categorias', campo: op.campo_rotulo, agregacao_valor: op.agregacao || 'contagem',
      campo_valor: op.campo, max_categorias: op.max_categorias || 8 };
  }
  if (tipo === 'serial' || tipo === 'pizza') {
    const pedido = { agregacao: 'serie', limite: op.max_categorias || (op.faixa_data ? 60 : 20) };
    if (op.faixa_data) pedido.faixa_data = op.faixa_data;
    else pedido.grupo = op.grupo || op.campo_rotulo;
    pedido.series = op.series || [{ estatistica: op.estatistica || op.agregacao || 'contagem', campo: op.campo,
      rotulo: op.rotulo }];
    if (tipo === 'pizza') pedido.series = pedido.series.slice(0, 1);
    return pedido;
  }
  if (tipo === 'tabela') {
    if (op.grupos && op.grupos.length) {
      return { agregacao: 'grupos', grupos: op.grupos, series: op.series
        || [{ estatistica: op.estatistica || 'contagem', campo: op.campo }], limite: op.max_linhas || 100,
      ordenacao: op.ordenacao_grupos };
    }
    return { agregacao: 'linhas', campos: op.campos, limite: op.max_linhas || 50, ordenacao: op.ordenacao,
      total: true };
  }
  if (tipo === 'lista') {
    return { agregacao: 'linhas', campos: op.campos, limite: op.por_pagina || 25, ordenacao: op.ordenacao,
      total: true, deslocamento: 0 };
  }
  if (tipo === 'mapa') {
    return { agregacao: 'linhas', campos: op.campos, limite: op.max_pontos || 500, geometria: true };
  }
  if (tipo === 'detalhes') {
    return { agregacao: 'uma_feicao', campos: op.campos, ordenacao: op.ordenacao };
  }
  if (tipo === 'texto_rico') {
    return op.campos && op.campos.length
      ? { agregacao: 'uma_feicao', campos: op.campos, ordenacao: op.ordenacao }
      : null;
  }
  return null;
}

/* ------------------------------------------------------------------ peças comuns */
export function semDado(mensagem = 'sem dado para este filtro') {
  return h('p', { class: 'painel-sem-dado', role: 'status' }, mensagem);
}

/** tabela equivalente (oculta ou em <details>), devolvida junto com o id para o `aria-describedby` */
export function tabelaEquivalente(cabecalho, linhas, { visivel = false, rotulo = 'tabela do gráfico' } = {}) {
  const id = proximoId('painel-tab');
  const tabela = h('table', { class: 'painel-tabela painel-tabela-equivalente', id },
    h('caption', { class: 'sr-only' }, rotulo),
    h('thead', {}, h('tr', {}, ...cabecalho.map((c) => h('th', { scope: 'col' }, String(c))))),
    h('tbody', {}, ...linhas.map((l) => h('tr', {}, ...l.map((v) => h('td', {}, valorDeCelula(v)))))));
  if (visivel) return { id, no: tabela };
  return { id, no: h('details', { class: 'painel-equivalente' },
    h('summary', {}, 'ver como tabela'), tabela) };
}

/* ------------------------------------------------------------------ um render por tipo */
function renderIndicador(corpo, el, resultado) {
  const op = el.opcoes || {};
  let valor = null;
  if (resultado && resultado.tipo === 'numero') valor = resultado.valor;
  else if (resultado && resultado.tipo === 'feicao') valor = (resultado.valores || {})[op.campo];
  if (valor === null || valor === undefined) { corpo.append(semDado(op.texto_sem_dado || 'sem valor')); return true; }
  const cor = corDaFaixa(valor, op.faixas);
  const caixa = h('p', { class: 'painel-indicador' });
  if (op.icone) caixa.append(h('span', { class: 'painel-indicador-icone', 'aria-hidden': 'true' }, op.icone));
  const numero = h('span', { class: 'painel-indicador-valor' }, formatarNumero(valor, op));
  if (cor) numero.style.color = cor;
  caixa.append(numero);
  if (op.rotulo) caixa.append(h('span', { class: 'painel-indicador-rotulo' }, op.rotulo));
  corpo.append(caixa);
  if (resultado.tipo === 'feicao' && op.campos_detalhe) {
    const linhas = op.campos_detalhe.map((c) => [c, (resultado.valores || {})[c]]);
    corpo.append(tabelaEquivalente(['campo', 'valor'], linhas, { rotulo: 'feição do indicador' }).no);
  }
  return false;
}

function renderSerial(corpo, el, resultado) {
  const op = el.opcoes || {};
  if (!resultado || resultado.tipo !== 'serie' || !(resultado.chaves || []).length) {
    corpo.append(semDado(op.texto_sem_dado)); return true;
  }
  const t = tabelaDaSerie(resultado);
  const eq = tabelaEquivalente(t.cabecalho, t.linhas, { rotulo: el.titulo || 'dados do gráfico' });
  const svg = paraDom(desenharSerie(resultado, {
    tipo: op.forma || 'barras', empilhado: !!op.empilhado, titulo: el.titulo || 'gráfico',
    mensagemVazio: op.texto_sem_dado || 'sem dado',
  }));
  svg.setAttribute('aria-describedby', eq.id);
  corpo.append(svg, eq.no);
  return false;
}

function renderPizza(corpo, el, resultado) {
  const op = el.opcoes || {};
  const serie = resultado && resultado.tipo === 'serie' ? (resultado.series || [])[0] : null;
  const chaves = (resultado && resultado.chaves) || [];
  if (!serie || !chaves.length) { corpo.append(semDado(op.texto_sem_dado)); return true; }
  const dados = {
    tipo: 'pizza', campo: resultado.chave, estatistica: 'valor',
    series: chaves.map((chave, i) => ({ chave: rotuloDeChave(chave, resultado.granularidade),
      n: serie.valores[i], valor: serie.valores[i] })),
    total: null, nulos: 0,
  };
  const eq = tabelaEquivalente([resultado.chave || 'categoria', serie.rotulo],
    chaves.map((c, i) => [rotuloDeChave(c, resultado.granularidade), serie.valores[i]]),
    { rotulo: el.titulo || 'dados do gráfico' });
  // importação tardia evita carregar o desenho de pizza em painel que não tem pizza
  return import('../mapa/grafico_svg.js').then(({ desenhar }) => {
    const svg = paraDom(desenhar(dados, { rosca: op.rosca !== false, titulo: el.titulo || 'gráfico de pizza',
      mensagemVazio: op.texto_sem_dado || 'sem dado' }));
    svg.setAttribute('aria-describedby', eq.id);
    corpo.append(svg, eq.no);
    return false;
  });
}

function ordenarLinhas(linhas, campo, direcao) {
  if (!campo) return linhas;
  const sinal = direcao === 'desc' ? -1 : 1;
  return [...linhas].sort((a, b) => {
    const va = a[campo]; const vb = b[campo];
    if (va === vb) return 0;
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    const na = Number(va); const nb = Number(vb);
    if (Number.isFinite(na) && Number.isFinite(nb)) return (na - nb) * sinal;
    return String(va).localeCompare(String(vb), 'pt-BR') * sinal;
  });
}

function renderTabela(corpo, el, resultado, ctx) {
  const op = el.opcoes || {};
  if (resultado && resultado.tipo === 'grupos') {
    const linhas = resultado.linhas || [];
    if (!linhas.length) { corpo.append(semDado(op.texto_sem_dado)); return true; }
    const grupos = resultado.grupos || [];
    const series = resultado.series || [];
    const tabela = h('table', { class: 'painel-tabela painel-tabela-agrupada' },
      h('thead', {}, h('tr', {}, ...grupos.map((g) => h('th', { scope: 'col' }, g)),
        ...series.map((s) => h('th', { scope: 'col', class: 'num' }, s.rotulo)))),
      h('tbody', {}, ...linhas.map((linha) => h('tr', {},
        ...grupos.map((g) => h('td', {}, valorDeCelula(linha[g]))),
        ...series.map((s) => h('td', { class: 'num' }, formatarNumero(linha[s.alias], op)))))),
      h('tfoot', {}, h('tr', { class: 'painel-total' },
        h('th', { scope: 'row', colspan: String(Math.max(1, grupos.length)) }, op.rotulo_total || 'total'),
        ...series.map((s) => h('td', { class: 'num' }, formatarNumero((resultado.total || {})[s.alias], op))))));
    corpo.append(tabela);
    return false;
  }
  const colunas = (resultado && resultado.colunas) || [];
  const linhasBrutas = (resultado && resultado.linhas) || [];
  if (!linhasBrutas.length) { corpo.append(semDado(op.texto_sem_dado)); return true; }
  const estado = ctx.estado(el.id, { campo: (op.ordenacao || {}).campo, direcao: (op.ordenacao || {}).direcao });
  const linhas = ordenarLinhas(linhasBrutas, estado.campo, estado.direcao);
  const tabela = h('table', { class: 'painel-tabela' });
  const cabecalho = h('tr', {});
  for (const c of colunas) {
    const th = h('th', { scope: 'col', 'aria-sort': estado.campo === c ? (estado.direcao === 'desc' ? 'descending' : 'ascending') : 'none' });
    const bt = h('button', { type: 'button', class: 'painel-ordenar', 'data-campo': c }, c);
    bt.addEventListener('click', () => {
      estado.direcao = estado.campo === c && estado.direcao === 'asc' ? 'desc' : 'asc';
      estado.campo = c;
      ctx.repintar(el.id);
    });
    th.append(bt);
    cabecalho.append(th);
  }
  tabela.append(h('thead', {}, cabecalho));
  tabela.append(h('tbody', {}, ...linhas.map((linha) => h('tr', {},
    ...colunas.map((c) => h('td', {}, valorDeCelula(linha[c])))))));
  corpo.append(tabela);
  if (resultado.total !== undefined && resultado.total !== null) {
    corpo.append(h('p', { class: 'painel-rodape-tabela' },
      `${formatarNumero(linhas.length)} de ${formatarNumero(resultado.total)} registro(s)`));
  }
  return false;
}

function renderLista(corpo, el, resultado, ctx) {
  const op = el.opcoes || {};
  const linhas = (resultado && resultado.linhas) || [];
  if (!linhas.length) { corpo.append(semDado(op.texto_sem_dado)); return true; }
  const lista = h('ul', { class: 'painel-lista' });
  for (const linha of linhas) {
    const item = h('li', { class: 'painel-lista-item' });
    if (op.icone) item.append(h('span', { class: 'painel-lista-icone', 'aria-hidden': 'true' }, op.icone));
    const texto = h('div', { class: 'painel-lista-texto' },
      h('span', { class: 'painel-lista-titulo' }, preencherModelo(op.modelo_titulo || `{${(resultado.colunas || [])[0] || ''}}`, linha)));
    if (op.modelo_detalhe) texto.append(h('span', { class: 'painel-lista-detalhe' }, preencherModelo(op.modelo_detalhe, linha)));
    item.append(texto);
    lista.append(item);
  }
  corpo.append(lista);
  const total = resultado.total;
  if (total !== undefined && total !== null && total > (resultado.limite || 0)) {
    const desloc = resultado.deslocamento || 0;
    const pagina = Math.floor(desloc / (resultado.limite || 1)) + 1;
    const paginas = Math.max(1, Math.ceil(total / (resultado.limite || 1)));
    const barra = h('div', { class: 'painel-paginacao' });
    const btAnterior = h('button', { type: 'button', class: 'pequeno', disabled: desloc <= 0,
      'data-acao': 'anterior' }, 'anterior');
    const btProxima = h('button', { type: 'button', class: 'pequeno', disabled: pagina >= paginas,
      'data-acao': 'proxima' }, 'próxima');
    btAnterior.addEventListener('click', () => ctx.paginar(el.id, Math.max(0, desloc - (resultado.limite || 0))));
    btProxima.addEventListener('click', () => ctx.paginar(el.id, desloc + (resultado.limite || 0)));
    barra.append(btAnterior,
      h('span', { class: 'painel-paginacao-texto', 'aria-live': 'polite' },
        `página ${formatarNumero(pagina)} de ${formatarNumero(paginas)} · ${formatarNumero(total)} registro(s)`),
      btProxima);
    corpo.append(barra);
  }
  return false;
}

const PROJ = { LARGURA: 420, ALTURA: 240, MARGEM: 10 };

function renderMapa(corpo, el, resultado, ctx) {
  const op = el.opcoes || {};
  const linhas = (resultado && resultado.linhas) || [];
  const pontos = linhas.filter((l) => Number.isFinite(Number(l.__lon)) && Number.isFinite(Number(l.__lat)))
    .map((l) => ({ lon: Number(l.__lon), lat: Number(l.__lat), linha: l }));
  if (!pontos.length) { corpo.append(semDado(op.texto_sem_dado || 'sem feição com geometria neste filtro')); return true; }
  const lons = pontos.map((p) => p.lon); const lats = pontos.map((p) => p.lat);
  const env = [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
  const dx = (env[2] - env[0]) || 0.01; const dy = (env[3] - env[1]) || 0.01;
  const caixa = [env[0] - dx * 0.06, env[1] - dy * 0.06, env[2] + dx * 0.06, env[3] + dy * 0.06];
  const px = (lon) => PROJ.MARGEM + ((lon - caixa[0]) / (caixa[2] - caixa[0])) * (PROJ.LARGURA - 2 * PROJ.MARGEM);
  const py = (lat) => PROJ.ALTURA - PROJ.MARGEM - ((lat - caixa[1]) / (caixa[3] - caixa[1])) * (PROJ.ALTURA - 2 * PROJ.MARGEM);
  const filhos = pontos.map((p) => ({
    tag: 'circle',
    atrs: { cx: Math.round(px(p.lon) * 100) / 100, cy: Math.round(py(p.lat) * 100) / 100, r: 4,
      class: 'painel-mapa-ponto' },
    filhos: [{ tag: 'title', atrs: {}, filhos: [preencherModelo(op.modelo_titulo || '', p.linha) || `${p.lon}, ${p.lat}`] }],
  }));
  const svg = paraDom({ tag: 'svg', atrs: { viewBox: `0 0 ${PROJ.LARGURA} ${PROJ.ALTURA}`, class: 'painel-mapa',
    role: 'img', 'aria-label': el.titulo || 'mapa', 'data-extensao': caixa.map((v) => v.toFixed(5)).join(',') },
  filhos });
  const eq = tabelaEquivalente(['longitude', 'latitude'], pontos.slice(0, 200).map((p) => [p.lon, p.lat]),
    { rotulo: el.titulo || 'pontos do mapa' });
  svg.setAttribute('aria-describedby', eq.id);
  corpo.append(svg);
  // "extensão como filtro": a extensão visível vira condição espacial nas OUTRAS fontes do painel
  const barra = h('div', { class: 'painel-mapa-acoes' });
  const btFiltrar = h('button', { type: 'button', class: 'pequeno', 'data-acao': 'filtrar-extensao' },
    op.rotulo_filtrar || 'filtrar pela extensão');
  const btLimpar = h('button', { type: 'button', class: 'pequeno texto', 'data-acao': 'limpar-extensao' },
    op.rotulo_limpar || 'limpar extensão');
  btFiltrar.addEventListener('click', () => ctx.filtrarExtensao(caixa));
  btLimpar.addEventListener('click', () => ctx.filtrarExtensao(null));
  barra.append(btFiltrar, btLimpar);
  corpo.append(barra, eq.no);
  return false;
}

function renderDetalhes(corpo, el, resultado) {
  const op = el.opcoes || {};
  const valores = resultado && resultado.tipo === 'feicao' ? resultado.valores : null;
  if (!valores) { corpo.append(semDado(op.texto_sem_dado || 'nenhuma feição selecionada')); return true; }
  const campos = op.campos || (resultado.campos || []);
  corpo.append(h('dl', { class: 'painel-detalhes' },
    ...campos.flatMap((c) => [h('dt', {}, c), h('dd', {}, valorDeCelula(valores[c]))])));
  return false;
}

/* markdown mínimo e SEGURO: só **negrito**, *itálico*, `código`, listas e parágrafos — nunca HTML do dado */
export function markdownSeguro(texto) {
  const linhas = String(texto || '').split(/\r?\n/);
  const nos = [];
  let lista = null;
  const inline = (s) => {
    const partes = [];
    const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
    let ultimo = 0; let m;
    while ((m = re.exec(s)) !== null) {
      if (m.index > ultimo) partes.push(s.slice(ultimo, m.index));
      const t = m[0];
      if (t.startsWith('**')) partes.push(h('strong', {}, t.slice(2, -2)));
      else if (t.startsWith('`')) partes.push(h('code', {}, t.slice(1, -1)));
      else partes.push(h('em', {}, t.slice(1, -1)));
      ultimo = m.index + t.length;
    }
    if (ultimo < s.length) partes.push(s.slice(ultimo));
    return partes;
  };
  for (const linha of linhas) {
    const item = /^\s*[-*]\s+(.*)$/.exec(linha);
    if (item) {
      if (!lista) { lista = h('ul', {}); nos.push(lista); }
      lista.append(h('li', {}, ...inline(item[1])));
      continue;
    }
    lista = null;
    const titulo = /^(#{1,3})\s+(.*)$/.exec(linha);
    if (titulo) { nos.push(h(`h${titulo[1].length + 2}`, {}, ...inline(titulo[2]))); continue; }
    if (linha.trim()) nos.push(h('p', {}, ...inline(linha)));
  }
  return nos;
}

function renderTextoRico(corpo, el, resultado) {
  const op = el.opcoes || {};
  const valores = resultado && resultado.tipo === 'feicao' ? (resultado.valores || {}) : {};
  const texto = preencherModelo(op.texto || '', valores);
  if (!texto.trim()) { corpo.append(semDado(op.texto_sem_dado || 'sem texto')); return true; }
  corpo.append(...markdownSeguro(texto));
  return false;
}

function renderLegenda(corpo, el) {
  const op = el.opcoes || {};
  const itens = op.itens || [];
  if (!itens.length) { corpo.append(semDado(op.texto_sem_dado || 'sem itens de legenda')); return true; }
  corpo.append(h('ul', { class: 'painel-legenda' }, ...itens.map((i) => h('li', {},
    h('span', { class: 'painel-legenda-cor', style: `background:${i.cor || 'transparent'}`, 'aria-hidden': 'true' }),
    h('span', {}, i.rotulo || '')))));
  return false;
}

function renderCabecalho(corpo, el, _resultado, ctx) {
  const op = el.opcoes || {};
  const caixa = h('div', { class: 'painel-cabecalho' });
  if (op.logo) caixa.append(h('img', { class: 'painel-logo', src: op.logo, alt: op.logo_alt || '' }));
  const textos = h('div', {});
  if (op.titulo) textos.append(h('h2', { class: 'painel-cabecalho-titulo' }, op.titulo));
  if (op.subtitulo) textos.append(h('p', { class: 'painel-cabecalho-sub' }, op.subtitulo));
  if (op.mostrar_atualizacao !== false) {
    textos.append(h('p', { class: 'painel-atualizado', 'data-papel': 'atualizado', 'aria-live': 'polite' },
      ctx.textoAtualizacao()));
  }
  caixa.append(textos);
  corpo.append(caixa);
  return false;
}

const RENDER = {
  indicador: renderIndicador,
  grafico: renderSerial,        // o `grafico` do L2-06-a passa a desenhar em SVG, com tabela equivalente
  serial: renderSerial,
  pizza: renderPizza,
  tabela: renderTabela,
  lista: renderLista,
  mapa: renderMapa,
  detalhes: renderDetalhes,
  texto_rico: renderTextoRico,
  legenda: renderLegenda,
  cabecalho: renderCabecalho,
};

/** Desenha um elemento no seu `corpo`; devolve true quando ficou no estado "sem dado". */
export function renderElemento(corpo, elemento, resultado, ctx) {
  limpar(corpo);
  const f = RENDER[elemento.tipo];
  if (!f) { corpo.textContent = '—'; return false; }
  // o `grafico` do L2-06-a devolve `{tipo:'categorias'}`: converte para a forma de série antes de desenhar
  let dado = resultado;
  if (resultado && resultado.tipo === 'categorias') {
    dado = { tipo: 'serie', chave: (elemento.opcoes || {}).campo_rotulo || 'categoria', granularidade: null,
      chaves: (resultado.linhas || []).map((l) => l.categoria),
      series: [{ alias: 's0', rotulo: 'valor', valores: (resultado.linhas || []).map((l) => l.valor) }] };
  }
  return f(corpo, elemento, dado, ctx);
}
