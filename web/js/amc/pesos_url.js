/* plat · AMC — item L3-01-g-tela-motor: os pesos que viajam na URL.

   O link da tela do motor carrega os pesos escolhidos pelo usuário (`?execucao=<id>&w=fator:peso,...`) para
   que a mesma leitura possa ser reaberta e passada adiante. Isso faz da barra de endereço uma FRONTEIRA DE
   CONFIANÇA: quem abre o link pode ter mexido nele. Por isso a leitura é validada aqui, uma regra por vez, e
   devolve a lista de recusas em português — a tela mostra as recusas e NÃO calcula nada enquanto houver uma.
   Nunca cair para um peso padrão em silêncio: um mapa recolorido com peso diferente do que está escrito na
   barra de endereço seria a pior falha possível desta tela.

   As regras são as mesmas que `app/amc/esquema.py:validar_pesos` aplica no servidor (fator tem de existir no
   modelo, peso >= 0 e finito, soma > 0, combinador 'percentual' fecha 100), mais o teto de escala PESO_MAX,
   que é do controle deslizante e não existe no servidor. Módulo puro: sem DOM, sem rede — é o que permite
   prová-lo fora do navegador (tests/amc/executar_pesos_url.mjs). */

export const PESO_MAX = 100;
export const TOLERANCIA_PERCENTUAL = 1e-6;

/** Lê `w=fator:peso,fator:peso` contra as fichas de fator do modelo. Devolve {pesos, erros}. */
export function lerPesos(texto, fatores, combinador = 'soma_ponderada_normalizada') {
  const conhecidos = new Map(fatores.map((f) => [f.id, f]));
  const pesos = {};
  const erros = [];
  for (const f of fatores) pesos[f.id] = Number(f.peso_modelo);

  if (texto !== null && texto !== undefined && String(texto).trim() !== '') {
    const vistos = new Set();
    for (const parte of String(texto).split(',')) {
      const cru = parte.trim();
      if (cru === '') continue;
      const corte = cru.indexOf(':');
      if (corte < 1) {
        erros.push(`peso mal escrito no link: ${JSON.stringify(cru)}; a forma é fator:peso`);
        continue;
      }
      const id = cru.slice(0, corte).trim();
      const bruto = cru.slice(corte + 1).trim();
      if (!conhecidos.has(id)) {
        erros.push(`o link traz o fator ${JSON.stringify(id)}, que não existe neste modelo`);
        continue;
      }
      if (vistos.has(id)) {
        erros.push(`o fator ${JSON.stringify(id)} aparece mais de uma vez no link`);
        continue;
      }
      vistos.add(id);
      if (!/^[+]?\d*\.?\d+$/.test(bruto)) {
        erros.push(`o peso do fator ${JSON.stringify(id)} não é um número não negativo: ${JSON.stringify(bruto)}`);
        continue;
      }
      const w = Number(bruto);
      if (!Number.isFinite(w)) {
        erros.push(`o peso do fator ${JSON.stringify(id)} não é um número finito: ${JSON.stringify(bruto)}`);
        continue;
      }
      if (w > PESO_MAX) {
        erros.push(`o peso do fator ${JSON.stringify(id)} é ${w}, acima do máximo ${PESO_MAX} da escala desta tela`);
        continue;
      }
      pesos[id] = w;
    }
  }

  const soma = Object.values(pesos).reduce((a, b) => a + b, 0);
  if (!(soma > 0)) {
    erros.push('a soma dos pesos é zero: nenhum fator pesa, não há como normalizar');
  }
  if (combinador === 'percentual' && Math.abs(soma - 100) > TOLERANCIA_PERCENTUAL) {
    erros.push(`no combinador percentual os pesos fecham 100; os do link somam ${soma}`);
  }
  return { pesos, erros, soma };
}

/** Escreve os pesos na forma que `lerPesos` lê de volta, em ordem estável. */
export function escreverPesos(pesos) {
  return Object.keys(pesos).sort()
    .map((id) => `${id}:${Number(pesos[id])}`)
    .join(',');
}

/** Link completo desta leitura: mesma origem/caminho, execução e pesos. */
export function montarLink(origem, execucaoId, pesos) {
  const u = new URL('/amc/motor', origem);
  u.searchParams.set('execucao', execucaoId);
  u.searchParams.set('w', escreverPesos(pesos));
  return u.toString();
}
