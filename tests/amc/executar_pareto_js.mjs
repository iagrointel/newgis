// Runner da parte pura da tela de Pareto (web/js/amc/pareto.js) para o teste de equivalência
// (tests/unit/test_amc_pareto_escova.py chama este script por subprocesso). Lê do stdin
// {unidades, ix, iy, caixa_px, largura, altura} e imprime o que a tela calcularia:
// os pontos desenháveis, a caixa em coordenadas de dado, os identificadores escovados e o filtro
// MapLibre de realce.
import { readFileSync } from 'node:fs';
import { caixaDeDado, corDaOrdem, escovar, faixa, filtroDeRealce, pontos, projetar } from '../../web/js/amc/pareto.js';

const e = JSON.parse(readFileSync(0, 'utf8'));
const desenhados = pontos(e.unidades, e.ix, e.iy);
const fx = faixa(e.unidades, e.ix);
const fy = faixa(e.unidades, e.iy);
const caixa = e.caixa_px ? caixaDeDado(e.caixa_px, fx, fy, e.largura, e.altura) : e.caixa;
const ids = escovar(desenhados, caixa);
process.stdout.write(JSON.stringify({
  desenhados,
  faixa_x: fx,
  faixa_y: fy,
  caixa,
  ids,
  filtro: filtroDeRealce(ids),
  cores: [corDaOrdem(1), corDaOrdem(2), corDaOrdem(3), corDaOrdem(0)],
  pixels: desenhados.map((p) => [projetar(p.x, fx, e.largura), projetar(p.y, fy, e.altura, true)]),
}));
