// Runner do motor JavaScript do formulário (item L2-07-b), chamado por subprocesso em
// tests/unit/test_coleta_motor_equivalencia.py: lê pelo stdin [{documento, valores, repeticoes}], roda o mesmo
// que o servidor faz (recalcular + validar) e devolve [{valores, repeticoes, erros, ordem}] para o teste comparar
// com app/coleta/motor.py. Nunca toca DOM.
import { readFileSync } from 'node:fs';
import { Motor } from '../../web/js/coleta/motor.js';

const casos = JSON.parse(readFileSync(0, 'utf8'));
const saida = casos.map((c) => {
  try {
    const m = new Motor(c.documento);
    m.valores = { ...m.valores, ...(c.valores || {}) };
    for (const [r, linhas] of Object.entries(c.repeticoes || {})) m.repeticoes[r] = linhas.map((l) => ({ ...l }));
    m.recalcular();
    const erros = m.validar();
    return { ordem: m.ordem, valores: m.valores, repeticoes: m.repeticoes, erros };
  } catch (e) {
    return { erro: e.codigo || String(e), campos: e.campos || null };
  }
});
process.stdout.write(JSON.stringify(saida));
