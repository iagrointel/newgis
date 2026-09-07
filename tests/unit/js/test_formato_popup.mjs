// Formatação do popup em tempo de execução (item L2-01-d-popup-runtime), lado do NAVEGADOR.
// `node --test` puro (stdlib), sem framework novo — o repositório não tem jest/vitest instalado e o
// PONYTAIL.md manda subir a escada até a biblioteca padrão antes de escrever/instalar qualquer coisa.
//
// Uso:  node --test tests/unit/js/test_formato_popup.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  formatarNumero, formatarMoeda, formatarData, urlSegura, valorExibicao, SEM_VALOR,
} from '../../../web/js/mapa/formato.js';

test('número grande com duas casas e separador pt-BR (cláusula literal do portão)', () => {
  assert.equal(formatarNumero(1234567.891, 2), '1.234.567,89');
});

test('número nulo/indefinido vira SEM_VALOR, nunca "null"/"undefined"', () => {
  assert.equal(formatarNumero(null, 2), SEM_VALOR);
  assert.equal(formatarNumero(undefined, 2), SEM_VALOR);
  assert.notEqual(formatarNumero(null, 2), 'null');
});

test('moeda em reais', () => {
  assert.equal(formatarMoeda(1234.5), 'R$\xa01.234,50');
});

test('data no fuso pedido: o mesmo instante, dois textos diferentes', () => {
  const ms = 1772614800000; // convenção do L2-10-c: ms desde a época, sempre UTC
  const utc = formatarData(ms, 'UTC');
  const sp = formatarData(ms, 'America/Sao_Paulo');
  assert.notEqual(utc, sp);
  assert.match(utc, /^\d{2}\/\d{2}\/\d{4},? \d{2}:\d{2}$/);
});

test('fuso desconhecido cai no padrão sem lançar', () => {
  assert.doesNotThrow(() => formatarData(1772614800000, 'Nao/Existe'));
});

test('url segura aceita http(s) e recusa javascript:', () => {
  assert.equal(urlSegura('https://exemplo.iagrointel.com/x'), 'https://exemplo.iagrointel.com/x');
  assert.equal(urlSegura('javascript:alert(1)'), null);
  assert.equal(urlSegura('data:text/html,<script>1</script>'), null);
  assert.equal(urlSegura(''), null);
  assert.equal(urlSegura(null), null);
});

test('valorExibicao: campo nulo vira SEM_VALOR sempre, qualquer tipo', () => {
  assert.equal(valorExibicao(null, { tipo: 'numero' }), SEM_VALOR);
  assert.equal(valorExibicao(undefined, { tipo: 'texto' }), SEM_VALOR);
  assert.equal(valorExibicao('', { tipo: 'texto' }), SEM_VALOR);
});

test('valorExibicao: texto bruto com HTML/script nunca é interpretado aqui (é string, quem insere no DOM decide)', () => {
  const bruto = '<script>alert(1)</script>';
  assert.equal(valorExibicao(bruto, { tipo: 'texto' }), bruto);
});
