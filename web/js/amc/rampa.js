/* plat · AMC — item L3-01-g-tela-motor: a rampa de favorabilidade, DECLARADA num lugar só.

   O mapa e a legenda leem esta mesma lista: legenda que discorda do mapa é o defeito clássico desta tela.
   A rampa é sequencial (uma única direção: menos favorável -> mais favorável), não divergente — a
   favorabilidade 0-100 não tem ponto neutro no meio, então uma paleta de duas pontas mentiria sobre o dado.
   As cores são as do instrumento (web/estilo/tokens.css, âmbar) escritas em hexadecimal porque o MapLibre lê
   JSON puro e não resolve var() de CSS — a mesma razão documentada em web/js/mapa/estilo.js.

   Duas cores fora da rampa, e por quê:
   - VETADO: cinza. Unidade vetada não é "pouco favorável", é EXCLUÍDA por restrição declarada; pintá-la no
     extremo frio da rampa a faria parecer comparável com as demais.
   - SEM NOTA: vazado (só contorno). Falta de dado não é nota baixa (regra A3: NULL nunca vira 0). */

export const FAIXAS = [
  { ate: 20, cor: '#2b2f33', rotulo: '0 a 20' },
  { ate: 40, cor: '#5a4a2a', rotulo: '20 a 40' },
  { ate: 60, cor: '#8a6a24', rotulo: '40 a 60' },
  { ate: 80, cor: '#c08a2a', rotulo: '60 a 80' },
  { ate: 100, cor: '#f0b755', rotulo: '80 a 100' },
];
export const COR_VETADO = '#6b7280';
export const COR_SEM_NOTA = 'rgba(0,0,0,0)';
export const CONTORNO_SEM_NOTA = '#8fa19c';

/** cor de uma unidade já avaliada; `vetado` vence a nota, `null` (sem dado) nunca cai na rampa. */
export function corDe(favorabilidade, vetado) {
  if (vetado) return COR_VETADO;
  if (favorabilidade === null || favorabilidade === undefined || Number.isNaN(favorabilidade)) return COR_SEM_NOTA;
  for (const f of FAIXAS) if (favorabilidade <= f.ate) return f.cor;
  return FAIXAS[FAIXAS.length - 1].cor;
}

/** o que a legenda mostra, na mesma ordem em que se lê a rampa. */
export function itensDaLegenda() {
  return [
    ...FAIXAS.map((f) => ({ cor: f.cor, rotulo: `favorabilidade ${f.rotulo}` })),
    { cor: COR_VETADO, rotulo: 'vetado por restrição declarada' },
    { cor: COR_SEM_NOTA, contorno: CONTORNO_SEM_NOTA, rotulo: 'sem nota (falta dado; nunca 0)' },
  ];
}
