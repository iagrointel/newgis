// Runner do leitor de pesos da URL (web/js/amc/pesos_url.js) para tests/unit/test_amc_pesos_url.py.
// Lê do stdin um array de casos {texto, fatores, combinador} e imprime um array de {pesos, erros, soma}.
// O mesmo módulo que a tela do motor carrega: nenhuma cópia da regra vive no teste.
import { readFileSync } from 'node:fs';
import { lerPesos, escreverPesos, montarLink, PESO_MAX } from '../../web/js/amc/pesos_url.js';

const entrada = JSON.parse(readFileSync(0, 'utf8'));
const saida = entrada.map((caso) => {
  try {
    const r = lerPesos(caso.texto, caso.fatores, caso.combinador || 'soma_ponderada_normalizada');
    return {
      pesos: r.pesos,
      erros: r.erros,
      soma: r.soma,
      texto_de_volta: escreverPesos(r.pesos),
      link: montarLink('http://exemplo.invalido', caso.execucao_id || 'e1', r.pesos),
      peso_max: PESO_MAX,
    };
  } catch (e) {
    return { excecao: `${e.message}` };
  }
});
process.stdout.write(JSON.stringify(saida));
