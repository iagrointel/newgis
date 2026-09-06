// Runner do avaliador JavaScript para os testes de equivalência (tests/unit/test_expressao_*.py chamam
// este script via subprocess): lê tests/expressoes/vetores.json (ou um JSON pelo stdin com `--stdin`),
// avalia cada expressão com web/js/expressao/avaliador.js e imprime em stdout um array JSON de
// {entrada, resultado, erro, ast, resultado_ida_e_volta} — o Python compara com o resultado do
// avaliador Python para o MESMO vetor. `ast` é astParaJson(analisar(entrada)) e `resultado_ida_e_volta`
// é o valor da AST exportada → JSON.stringify → JSON.parse → astDeJson → avaliar (portão: "AST exportado
// e reimportado avalia igual"). Com `--ast`, cada item do stdin traz uma `ast` (exportada pelo PYTHON) e o
// runner só a reimporta e avalia — prova cruzada: AST gravada por um avaliador, lida pelo outro.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import {
  analisar, astDeJson, astParaJson, avaliar, avaliarTexto, ErroExpressao, TABELA_FUNCOES,
} from '../../web/js/expressao/avaliador.js';

const aqui = path.dirname(fileURLToPath(import.meta.url));

if (process.argv.includes('--nomes-funcoes')) {
  process.stdout.write(JSON.stringify(Object.keys(TABELA_FUNCOES)));
  process.exit(0);
}

const modoAst = process.argv.includes('--ast');
const vetores = JSON.parse(readFileSync(process.argv.includes('--stdin') ? 0 : path.join(aqui, 'vetores.json'), 'utf8'));

function guardado(fn) {
  try {
    return { resultado: fn(), erro: null };
  } catch (e) {
    if (e instanceof ErroExpressao) return { resultado: null, erro: e.codigo };
    return { resultado: null, erro: `EXCECAO_NAO_TRATADA:${e.message}` };
  }
}

const saida = vetores.map((vetor) => {
  const contexto = vetor.contexto || {};
  if (modoAst) {
    const r = guardado(() => avaliar(astDeJson(vetor.ast), contexto));
    return { entrada: vetor.entrada, resultado: r.resultado, erro: r.erro };
  }
  const direto = guardado(() => avaliarTexto(vetor.entrada, contexto));
  let ast = null;
  let idaEVolta = { resultado: null, erro: direto.erro };
  if (direto.erro === null) {
    ast = astParaJson(analisar(vetor.entrada));
    idaEVolta = guardado(() => avaliar(astDeJson(JSON.parse(JSON.stringify(ast))), contexto));
  }
  return {
    entrada: vetor.entrada, resultado: direto.resultado, erro: direto.erro,
    ast, resultado_ida_e_volta: idaEVolta.resultado, erro_ida_e_volta: idaEVolta.erro,
  };
});
process.stdout.write(JSON.stringify(saida));
