/* plat · mapa — formatação de valor no popup em tempo de execução (item L2-01-d-popup-runtime).

   Puro (sem DOM, sem rede): dá para testar com `node --test` (tests/unit/js/test_formato_popup.mjs),
   e é exatamente por isso que o formato NUNCA volta ao servidor para um campo que já veio no tile —
   `Intl` é recurso NATIVO da linguagem (navegador e Node), sem dependência nova (escada do
   PONYTAIL.md: biblioteca padrão antes de escrever código).

   Convenção de data: milissegundos desde a época Unix, sempre UTC (a mesma do núcleo de expressão do
   item L2-10-c, `app/expressao/avaliador_py.py`) — por isso `formatarData` recebe um NÚMERO, nunca
   uma string de data solta. */

export const SEM_VALOR = '—';

const ESQUEMAS_SEGUROS = new Set(['http:', 'https:']);

export function formatarNumero(valor, decimais = 2) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return SEM_VALOR;
  return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: decimais, maximumFractionDigits: decimais })
    .format(Number(valor));
}

export function formatarMoeda(valor) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return SEM_VALOR;
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(valor));
}

export function formatarData(valorMs, fuso = 'America/Sao_Paulo') {
  if (valorMs === null || valorMs === undefined || Number.isNaN(Number(valorMs))) return SEM_VALOR;
  const d = new Date(Number(valorMs));
  if (Number.isNaN(d.getTime())) return SEM_VALOR;
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      timeZone: fuso, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(d);
  } catch {
    // fuso IANA desconhecido no navegador: cai no padrão do produto, nunca lança (mesma regra do servidor)
    return new Intl.DateTimeFormat('pt-BR', {
      timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(d);
  }
}

/* só http(s): nunca javascript:/data:/vbscript: num href — a mesma fronteira de confiança de um link
   clicável que vem de dado do usuário. Devolve null quando a URL não é segura (o chamador então mostra
   o valor como texto simples, nunca como link). */
export function urlSegura(valor) {
  if (typeof valor !== 'string' || !valor) return null;
  try {
    const base = typeof window !== 'undefined' && window.location ? window.location.href : undefined;
    const u = new URL(valor, base);
    return ESQUEMAS_SEGUROS.has(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}

/* dispatcher único: campo (config normalizada do servidor) + valor bruto -> texto para exibição.
   'url' e 'imagem' não formatam texto aqui (o chamador monta <a>/<img>; ver popup.js). */
export function valorExibicao(valor, campo, fuso) {
  if (valor === null || valor === undefined || valor === '') return SEM_VALOR;
  switch (campo && campo.tipo) {
    case 'numero': return formatarNumero(valor, campo.decimais ?? 2);
    case 'moeda': return formatarMoeda(valor);
    case 'data': return formatarData(valor, fuso);
    default: return String(valor);
  }
}
