// Runner do combinador JavaScript para os testes de equivalência e de desempenho no navegador
// (tests/unit/test_amc_combinacao*.py chamam este script por subprocesso).
//
//   --stdin        lê do stdin um array de casos {fatores, pesos, opcoes} e imprime um array JSON de
//                  {fav, vetado, cobertura, motivo, observacoes, aviso_pesos, erro}
//   --desempenho   lê do stdin {fatores, pesos, opcoes, repeticoes} e imprime {ms_mediano, ms_min,
//                  unidades, fatores, repeticoes} — o mesmo relógio (performance.now) que o navegador usa
import { readFileSync } from 'node:fs';
import { combinar, ErroCombinacao } from '../../web/js/amc/combinacao.js';

const entrada = JSON.parse(readFileSync(0, 'utf8'));

if (process.argv.includes('--desempenho')) {
  const { fatores, pesos, opcoes = {}, repeticoes = 20 } = entrada;
  const tempos = [];
  for (let k = 0; k < repeticoes; k += 1) {
    const t0 = performance.now();
    combinar(fatores, pesos, opcoes);
    tempos.push(performance.now() - t0);
  }
  tempos.sort((a, b) => a - b);
  process.stdout.write(JSON.stringify({
    ms_mediano: tempos[Math.floor(tempos.length / 2)],
    ms_min: tempos[0],
    unidades: fatores.length,
    fatores: fatores[0].length,
    repeticoes,
  }));
  process.exit(0);
}

// JSON não tem Infinity nem NaN: o Python manda esses valores como as cadeias "inf", "-inf" e "nan"
// (só os testes de ataque usam isso) e aqui viram o número correspondente.
const ESPECIAIS = { inf: Infinity, '-inf': -Infinity, nan: NaN };
function numero(v) { return typeof v === 'string' && v in ESPECIAIS ? ESPECIAIS[v] : v; }

const saida = entrada.map((caso) => {
  try {
    const fatores = caso.fatores.map((linha) => linha.map(numero));
    const pesos = caso.pesos.map(numero);
    const r = combinar(fatores, pesos, caso.opcoes || {});
    return {
      fav: r.fav, vetado: r.vetado, cobertura: r.cobertura, motivo: r.motivo,
      observacoes: r.observacoes, aviso_pesos: r.avisoPesos, erro: null,
    };
  } catch (e) {
    if (e instanceof ErroCombinacao) return { erro: e.codigo };
    return { erro: `EXCECAO_NAO_TRATADA:${e.message}` };
  }
});
process.stdout.write(JSON.stringify(saida));
