/* plat · legenda — item L2-01-c-lista-camadas-legenda.

   Módulo REUTILIZÁVEL (o próprio item pede: "web/js/legenda.js reutilizável pelo widget do L5-01-b").
   Não recebe uma lista de cores pronta do servidor: lê o ESTILO MapLibre AO VIVO da camada
   (`map.getPaintProperty`/`map.getLayer`) e deriva a legenda dele. É por isso que a legenda muda quando
   o estilo muda sem recarregar a página — basta chamar `Legenda.atualizar()` (ou deixar o `map.on(
   'styledata', ...)` interno fazer isso sozinho: MapLibre dispara 'styledata' em QUALQUER mutação de
   estilo, inclusive `setPaintProperty`/`setLayoutProperty`, medido nesta suíte).

   Reconhece os 6 tipos de estilo do item L2-02-c-editor-simbologia-vetor pela FORMA da expressão da
   Style Spec — não por um campo "tipo" que o servidor mande à parte (o servidor de hoje, L2-01-mapa-web,
   já manda; um estilo escrito por outra ferramenta, ou pelo próprio L2-02-c quando existir, também tem
   de funcionar, porque a legenda lê o que o MAPA está desenhando, não um metadado de conveniência):

     símbolo único   cor/raio CONSTANTE (string ou número) no paint
     categorias      ["case", ["==", ["get", campo], v1], cor1, ..., corResto]
     classes         ["case", ["<", [...], corte1], cor1, ..., corResto]  (teste "<" em vez de "==")
     proporcional    circle-radius é ["interpolate", ..., ["to-number", ["get", campo]] | ["get", campo], ...]
                      (raio varia por VALOR da feição, não por zoom)
     calor           camada type "heatmap"; rampa vem de heatmap-color (interpolate sobre heatmap-density)
     raster c/ rampa camada type "raster"; rampa vem de raster-color (interpolate sobre raster-value),
                      mín/máx de raster-color-range OU do metadata plat:minimo/plat:maximo

   `metadata` na camada de estilo (campo livre da Style Spec, `layer.metadata`) carrega só o que a Style
   Spec não expressa: unidade, título amigável e — no proporcional/raster — o par mínimo/máximo, para a
   legenda não ter de adivinhar a partir da própria expressão (ela AINDA confere a expressão: o número
   mostrado sai da expressão real, o metadata só rotula). */

import { h, limpar } from './base/dom.js';

const EPS = 1e-9;

function ehCor(v) {
  return typeof v === 'string' && /^#|^rgba?\(|^hsla?\(/.test(v);
}

function coresDoCase(expr) {
  // ["case", teste1, cor1, teste2, cor2, ..., corResto]
  const cores = [];
  for (let i = 1; i < expr.length; i += 1) {
    if (i === expr.length - 1 || i % 2 === 0) { if (ehCor(expr[i])) cores.push(expr[i]); }
  }
  return cores;
}

/* devolve {tipo:'categorias'|'classes', entradas:[{rotulo,cor}]} a partir de um "case" com os TESTES
   originais — não dá para recuperar o rótulo textual perfeito de "10 a 20" sem o servidor, então a
   legenda dinâmica mostra o valor numérico/literal do teste; quando a ficha do servidor já trouxe
   `legenda` pronta (mesma lista de classes que gerou o estilo, app/mapa/simbologia.py), ela é preferida
   e este caminho só é o de RESERVA para estilo que não veio com ficha (o que a cláusula "muda sem
   recarregar" exige: funcionar só com o estilo, sem outra chamada ao servidor). */
function entradasDoCase(expr) {
  const partes = expr.slice(1);
  const resto = partes[partes.length - 1];
  const pares = partes.slice(0, -1);
  const entradas = [];
  let tipo = 'categorias';
  for (let i = 0; i < pares.length; i += 2) {
    const teste = pares[i];
    const cor = pares[i + 1];
    if (Array.isArray(teste) && teste[0] === '==') {
      entradas.push({ rotulo: String(teste[2]), cor });
    } else if (Array.isArray(teste) && (teste[0] === '<' || teste[0] === '<=')) {
      tipo = 'classes';
      const corte = teste[teste.length - 1];
      const anterior = entradas.length ? entradas[entradas.length - 1]._corteAnterior : undefined;
      entradas.push({ rotulo: anterior === undefined ? `< ${corte}` : `${anterior} a ${corte}`, cor,
        _corteAnterior: corte });
    } else {
      entradas.push({ rotulo: String(i / 2), cor });
    }
  }
  entradas.push({ rotulo: tipo === 'classes' ? `≥ ${entradas.length ? entradas[entradas.length - 1]._corteAnterior : ''}` : 'outros', cor: resto });
  for (const e of entradas) delete e._corteAnterior;
  return { tipo, entradas };
}

function eIntepolatePorPropriedade(expr) {
  // ["interpolate", ["linear"|...], ATRIBUTO, v0, out0, v1, out1, ...] com ATRIBUTO != ["zoom"]
  if (!Array.isArray(expr) || expr[0] !== 'interpolate') return null;
  const atributo = expr[2];
  const ehZoom = Array.isArray(atributo) && atributo[0] === 'zoom';
  if (ehZoom) return null;
  const paradas = expr.slice(3);
  const pontos = [];
  for (let i = 0; i < paradas.length; i += 2) pontos.push({ valor: paradas[i], saida: paradas[i + 1] });
  return pontos;
}

/* Lê o paint de UMA camada de estilo do MapLibre (já aplicada ao mapa) e devolve um descritor de
   legenda genérico. `map` precisa ter a camada (getLayer(layerId) não nulo). Nunca lança: camada sem
   forma reconhecida devolve null (o chamador decide o que fazer — normalmente nada, não um erro). */
export function analisarCamada(map, layerId) {
  const camada = map.getLayer(layerId);
  if (!camada) return null;
  const tipo = camada.type;
  const meta = (map.getLayoutProperty(layerId, 'visibility'), camada.metadata) || {};
  const titulo = meta['plat:titulo'] || null;
  const unidade = meta['plat:unidade'] || null;

  if (tipo === 'heatmap') {
    const expr = map.getPaintProperty(layerId, 'heatmap-color');
    const cores = Array.isArray(expr) ? expr.filter((v) => ehCor(v)) : [];
    if (!cores.length) return null;
    return { tipo: 'calor', titulo, unidade, entradas: [
      { rotulo: 'baixo', cor: cores[0] }, { rotulo: 'alto', cor: cores[cores.length - 1] }],
      rampa: cores };
  }

  if (tipo === 'raster') {
    const expr = map.getPaintProperty(layerId, 'raster-color');
    const faixa = map.getPaintProperty(layerId, 'raster-color-range');
    const cores = Array.isArray(expr) ? expr.filter((v) => ehCor(v)) : [];
    if (!cores.length) return null;
    const minimo = (faixa && faixa[0]) ?? meta['plat:minimo'] ?? 0;
    const maximo = (faixa && faixa[1]) ?? meta['plat:maximo'] ?? 1;
    return { tipo: 'raster', titulo, unidade, minimo, maximo, rampa: cores,
      entradas: [{ rotulo: String(minimo), cor: cores[0] }, { rotulo: String(maximo), cor: cores[cores.length - 1] }] };
  }

  const chaveCor = tipo === 'circle' ? 'circle-color' : tipo === 'line' ? 'line-color' : 'fill-color';
  const chaveRaio = tipo === 'circle' ? 'circle-radius' : null;
  const cor = map.getPaintProperty(layerId, chaveCor);
  const raio = chaveRaio ? map.getPaintProperty(layerId, chaveRaio) : null;

  if (chaveRaio) {
    const pontosRaio = eIntepolatePorPropriedade(raio);
    if (pontosRaio && pontosRaio.length >= 2 && ehCor(cor)) {
      return { tipo: 'proporcional', titulo, unidade, cor,
        entradas: pontosRaio.map((p) => ({ rotulo: String(p.valor), cor, raio: p.saida })) };
    }
  }

  if (ehCor(cor)) {
    return { tipo: 'simples', titulo, unidade, forma: tipo,
      entradas: [{ rotulo: meta['plat:rotulo'] || 'todas as feições', cor }] };
  }
  if (Array.isArray(cor) && cor[0] === 'case') {
    const { tipo: subtipo, entradas } = entradasDoCase(cor);
    return { tipo: subtipo, titulo, unidade, forma: tipo, entradas };
  }
  return null;
}

const NS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}

/* amostra SVG desenhada da PRÓPRIA cor/forma lida do estilo — nunca um <img> ou sprite estático. */
function amostraSvg(entrada, forma) {
  const raiz = svg('svg', { width: 22, height: 16, viewBox: '0 0 22 16', class: 'legenda-svg', 'aria-hidden': 'true' });
  if (forma === 'circle' || forma === 'proporcional') {
    const raioMax = 7;
    const r = Math.max(1.5, Math.min(raioMax, (entrada.raio ?? 4) / 2 + 1.5));
    raiz.append(svg('circle', { cx: 11, cy: 8, r, fill: entrada.cor, stroke: '#10161a', 'stroke-width': 0.6 }));
  } else if (forma === 'line') {
    raiz.append(svg('line', { x1: 1, y1: 8, x2: 21, y2: 8, stroke: entrada.cor, 'stroke-width': 2.4, 'stroke-linecap': 'round' }));
  } else if (forma === 'calor' || forma === 'raster') {
    const grad = svg('linearGradient', { id: `g-${Math.random().toString(36).slice(2)}` });
    const rampa = entrada._rampa || [entrada.cor];
    rampa.forEach((c, i) => grad.append(svg('stop', { offset: `${(i / Math.max(1, rampa.length - 1)) * 100}%`, 'stop-color': c })));
    const defs = svg('defs', {});
    defs.append(grad);
    raiz.append(defs);
    raiz.append(svg('rect', { x: 1, y: 3, width: 20, height: 10, fill: `url(#${grad.getAttribute('id')})`, stroke: '#10161a', 'stroke-width': 0.5 }));
  } else {
    raiz.append(svg('rect', { x: 2, y: 2, width: 18, height: 12, fill: entrada.cor, stroke: '#10161a', 'stroke-width': 0.6 }));
  }
  return raiz;
}

export class Legenda {
  /* map: instância MapLibre. obterCamadas(): () => [{ id, tituloExibido, idsDeEstilo: [layerId,...],
     minzoom, maxzoom, foraDeEscala }] na ordem de desenho (do topo para baixo) — normalmente vem do
     mesmo objeto que desenha a árvore de camadas (camadas.js), para a legenda respeitar visibilidade e
     escala igual à árvore, sem calcular duas vezes. */
  constructor(map, raiz, obterCamadas) {
    this.map = map;
    this.raiz = raiz;
    this.obterCamadas = obterCamadas;
    this._pendente = null;
    map.on('styledata', () => this._agendar());
  }

  _agendar() {
    if (this._pendente) return;
    this._pendente = requestAnimationFrame(() => { this._pendente = null; this.desenhar(); });
  }

  desenhar() {
    limpar(this.raiz);
    const lista = this.obterCamadas();
    if (!lista.length) {
      this.raiz.append(h('p', { class: 'vazio' }, 'nenhuma camada visível'));
      return;
    }
    for (const cam of lista) {
      if (cam.foraDeEscala) continue; // legenda respeita escala: fora da faixa, não aparece
      // camadas auxiliares do editor de simbologia (sombra, brilho; item L2-02-c) não representam a camada
      const auxiliar = (id) => !!((this.map.getLayer(id) || {}).metadata || {})['plat:auxiliar'];
      const primeiraCamadaComForma = cam.idsDeEstilo.find((id) => this.map.getLayer(id) && !auxiliar(id) && analisarCamada(this.map, id));
      if (!primeiraCamadaComForma) continue;
      const desc = analisarCamada(this.map, primeiraCamadaComForma);
      if (!desc) continue;
      const bloco = h('div', { class: 'legenda-bloco', dataset: { camada: cam.id, tipoEstilo: desc.tipo } },
        h('h3', {}, cam.tituloExibido));
      if (desc.unidade) bloco.append(h('p', { class: 'legenda-unidade' }, desc.unidade));
      const ul = h('ul', { class: 'legenda-lista' });
      for (const entrada of desc.entradas) {
        entrada._rampa = desc.rampa;
        // envelope `.legenda-amostra` com a var CSS `--cor`: compatibilidade com o seletor do item-pai
        // (L2-01-mapa-web, tests/e2e/test_mapa_web.py) — a prova em si é o SVG dentro, desenhado da cor
        // lida do estilo agora mesmo (nunca uma cópia estática); a var serve a quem quer 1 seletor sem
        // abrir o SVG.
        const svgAmostra = amostraSvg(entrada, desc.forma || desc.tipo);
        const amostra = h('span', { class: 'legenda-amostra' }, svgAmostra);
        if (typeof entrada.cor === 'string') amostra.style.setProperty('--cor', entrada.cor);
        ul.append(h('li', {}, amostra, h('span', {}, entrada.rotulo)));
      }
      bloco.append(ul);
      if (desc.tipo === 'raster' && (desc.minimo !== undefined)) {
        bloco.append(h('p', { class: 'legenda-faixa' }, `mín. ${desc.minimo} · máx. ${desc.maximo}`));
      }
      this.raiz.append(bloco);
    }
  }
}
