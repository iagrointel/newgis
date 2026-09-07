#!/usr/bin/env node
/* Validador da MapLibre Style Spec (item L2-02-a-modelo-estilo): lê UM estilo JSON completo (version 8,
   sources incluídas — a fonte simbólica `camada` já vem injetada pelo chamador, app/estilos/validador.py)
   de stdin e escreve em stdout `{"ok": bool, "erros": [{"mensagem": str}]}` com os erros do pacote oficial
   @maplibre/maplibre-gl-style-spec (versão fixada em package.json). Sem rede, sem escrita em disco.

   Código de saída: 0 = validação executada (o resultado está no JSON, ok true/false);
   2 = entrada ausente ou JSON inválido (o chamador trata como falha do validador, nunca como estilo válido). */

import { validateStyleMin as validate } from '@maplibre/maplibre-gl-style-spec';

const PEDACOS_MAX = 64 * 1024 * 1024; // teto de stdin: o corpo da API já limita o documento bem abaixo disto

let entrada = '';
let total = 0;
process.stdin.setEncoding('utf8');
process.stdin.on('data', (pedaco) => {
  total += pedaco.length;
  if (total > PEDACOS_MAX) {
    process.stderr.write('entrada acima do teto\n');
    process.exit(2);
  }
  entrada += pedaco;
});
process.stdin.on('end', () => {
  let estilo;
  try {
    estilo = JSON.parse(entrada);
  } catch (e) {
    process.stderr.write(`JSON inválido: ${e.message}\n`);
    process.exit(2);
  }
  const erros = validate(estilo).map((e) => ({ mensagem: e.message }));
  process.stdout.write(JSON.stringify({ ok: erros.length === 0, erros }) + '\n');
});
