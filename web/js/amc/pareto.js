/* plat · motor multicritério — parte PURA da tela de fronteira de Pareto (item L3-08-pareto).
   Sem DOM, sem MapLibre, sem fetch: só a conta que liga o gráfico de dispersão ao mapa. É esta parte
   que tests/unit/test_amc_pareto_escova.py executa em node, do mesmo jeito que o combinador
   (web/js/amc/combinacao.js) é executado pelos testes de equivalência.

   A ligação gráfico -> mapa é uma seleção de identificadores: escovar um retângulo no gráfico devolve
   os `unidade_id` cujos dois valores caem dentro, e o mapa realça exatamente esses identificadores com
   um filtro MapLibre. Nenhum lado guarda uma cópia da seleção do outro. */

// cor por ordem de fronteira; a 1ª ordem é a única em cor de destaque (tokens escuros de estilo/tokens.css)
export const CORES_ORDEM = ['#d98a2b', '#8fa19c', '#4d5b57'];
export const COR_SEM_ORDEM = '#263133';

export function corDaOrdem(ordem) {
  if (!Number.isInteger(ordem) || ordem < 1) return COR_SEM_ORDEM;
  return CORES_ORDEM[Math.min(ordem, CORES_ORDEM.length) - 1];
}

function numero(v) { return typeof v === 'number' && Number.isFinite(v) ? v : null; }

/** Menor e maior valor do objetivo `indice` entre as unidades, ignorando ausência (null/NaN).
    Devolve null quando nenhuma unidade tem dado — quem chama decide o que desenhar nesse caso. */
export function faixa(unidades, indice) {
  let min = Infinity;
  let max = -Infinity;
  for (const u of unidades) {
    const v = numero(u.valores?.[indice]);
    if (v === null) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min === Infinity) return null;
  return { min, max };
}

/** Posição em pixels de um valor dentro de uma faixa. `inverter` é para o eixo vertical do SVG, que
    cresce para baixo. Faixa de largura zero (todo mundo igual) cai no meio, nunca divide por zero. */
export function projetar(valor, faixaValor, tamanho, inverter = false) {
  if (!faixaValor) return null;
  const v = numero(valor);
  if (v === null) return null;
  const largura = faixaValor.max - faixaValor.min;
  const fracao = largura === 0 ? 0.5 : (v - faixaValor.min) / largura;
  return (inverter ? 1 - fracao : fracao) * tamanho;
}

/** Unidades desenháveis no gráfico: as que têm dado nos DOIS objetivos escolhidos. Unidade sem dado
    não vira ponto (não existe posição honesta para ela), e é por isso que ela também não é escovável. */
export function pontos(unidades, ix, iy) {
  const saida = [];
  for (const u of unidades) {
    const x = numero(u.valores?.[ix]);
    const y = numero(u.valores?.[iy]);
    if (x === null || y === null) continue;
    saida.push({ unidade_id: u.unidade_id, ordem: u.ordem, x, y });
  }
  return saida;
}

/** Identificadores das unidades dentro do retângulo escovado, em COORDENADAS DE DADO (não em pixels):
    {x0,x1,y0,y1} em qualquer ordem. Retângulo degenerado (área zero) devolve lista vazia — um clique
    seco não é uma escova, e tratá-lo como tal apagaria a seleção anterior sem o usuário querer. */
export function escovar(pontosDesenhados, caixa) {
  if (!caixa) return [];
  const x0 = Math.min(caixa.x0, caixa.x1);
  const x1 = Math.max(caixa.x0, caixa.x1);
  const y0 = Math.min(caixa.y0, caixa.y1);
  const y1 = Math.max(caixa.y0, caixa.y1);
  if (!(x1 > x0) || !(y1 > y0)) return [];
  return pontosDesenhados
    .filter((p) => p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1)
    .map((p) => p.unidade_id);
}

/** Filtro MapLibre que realça exatamente os identificadores escovados. Lista vazia = filtro que não
    casa com nada (o realce some), nunca um filtro ausente (que realçaria tudo). */
export function filtroDeRealce(ids) {
  return ['in', ['get', 'unidade_id'], ['literal', Array.isArray(ids) ? ids : []]];
}

/** Caixa em coordenadas de dado a partir de uma caixa em pixels do gráfico (o inverso de `projetar`). */
export function caixaDeDado(caixaPx, faixaX, faixaY, largura, altura) {
  if (!faixaX || !faixaY) return null;
  const desfazer = (px, f, tamanho, inverter) => {
    const fracao = tamanho === 0 ? 0 : px / tamanho;
    const t = inverter ? 1 - fracao : fracao;
    return f.min + t * (f.max - f.min);
  };
  return {
    x0: desfazer(caixaPx.x0, faixaX, largura, false),
    x1: desfazer(caixaPx.x1, faixaX, largura, false),
    y0: desfazer(caixaPx.y0, faixaY, altura, true),
    y1: desfazer(caixaPx.y1, faixaY, altura, true),
  };
}
