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

function guardado(fn) {
  try {
    return { resultado: fn(), erro: null };
  } catch (e) {
    if (e instanceof ErroExpressao) return { resultado: null, erro: e.codigo };
    return { resultado: null, erro: `EXCECAO_NAO_TRATADA:${e.message}` };
  }
}

// `--perfis` roda tests/expressoes/vetores_perfis.json pelo avaliador de PERFIL do navegador
// (web/js/expressao/perfis.js): cada vetor traz perfil, expressão e feição, e o Python compara o
// resultado com o do avaliador de perfil do servidor (app/expressao/perfis.py). `--perfis-pares`
// avalia CADA vetor nos dois perfis nomeados em `pares` e devolve os dois valores — é a prova de
// que a mesma expressão no popup e no cálculo de formulário dá o mesmo valor, no navegador.
if (process.argv.includes('--perfis') || process.argv.includes('--perfis-pares')) {
  const { avaliarPerfil, PERFIS } = await import('../../web/js/expressao/perfis.js');
  if (process.argv.includes('--nomes-perfis')) {
    process.stdout.write(JSON.stringify(Object.keys(PERFIS)));
    process.exit(0);
  }
  const arquivo = process.argv.includes('--stdin') ? 0 : path.join(aqui, 'vetores_perfis.json');
  const casos = JSON.parse(readFileSync(arquivo, 'utf8'));
  const pares = process.argv.includes('--perfis-pares');
  const saida = casos.map((caso) => {
    const alvos = pares ? caso.pares : [caso.perfil];
    const valores = alvos.map((perfil) => guardado(() => avaliarPerfil(perfil, caso.entrada, caso.feicao ?? null)));
    return {
      entrada: caso.entrada,
      resultados: valores.map((v) => v.resultado),
      erros: valores.map((v) => v.erro),
    };
  });
  process.stdout.write(JSON.stringify(saida));
  process.exit(0);
}

const modoAst = process.argv.includes('--ast');
const vetores = JSON.parse(readFileSync(process.argv.includes('--stdin') ? 0 : path.join(aqui, 'vetores.json'), 'utf8'));


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
