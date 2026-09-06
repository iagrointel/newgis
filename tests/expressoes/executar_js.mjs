// Runner do avaliador JavaScript para o teste de equivalência (tests/unit/test_expressao_equivalencia.py
// chama este script via subprocess): lê tests/expressoes/vetores.json, avalia cada expressão com
// web/js/expressao/avaliador.js e imprime em stdout um array JSON de {entrada, resultado, erro}
// — o Python compara com o resultado do avaliador Python para o MESMO vetor.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { avaliarTexto, ErroExpressao, TABELA_FUNCOES } from '../../web/js/expressao/avaliador.js';

const aqui = path.dirname(fileURLToPath(import.meta.url));

if (process.argv.includes('--nomes-funcoes')) {
  process.stdout.write(JSON.stringify(Object.keys(TABELA_FUNCOES)));
  process.exit(0);
}

const vetores = JSON.parse(readFileSync(path.join(aqui, 'vetores.json'), 'utf8'));
const saida = vetores.map((vetor) => {
  try {
    const resultado = avaliarTexto(vetor.entrada, vetor.contexto || {});
    return { entrada: vetor.entrada, resultado, erro: null };
  } catch (e) {
    if (e instanceof ErroExpressao) return { entrada: vetor.entrada, resultado: null, erro: e.codigo };
    return { entrada: vetor.entrada, resultado: null, erro: `EXCECAO_NAO_TRATADA:${e.message}` };
  }
});
process.stdout.write(JSON.stringify(saida));
