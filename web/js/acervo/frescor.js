/* plat · acervo — o selo de frescor, num módulo só (item L6-01-h-frescor-verificacao).
   Duas telas usam exatamente este selo, com o mesmo texto e o mesmo motivo: a ficha (/acervo) e o mapa
   (/mapa, painel das camadas do acervo). O texto do aviso está escrito UMA vez, aqui — se ele mudar, muda
   nos dois lugares ao mesmo tempo, e o e2e que procura por ele não passa a medir duas coisas diferentes. */

export const AVISO_VENCIDA = 'verificação vencida';

const MOTIVOS = {
  endpoint_morto: 'um endereço da fonte parou de responder no último teste HTTP',
  prazo_da_fonte_vencido: 'a data de próxima verificação declarada pela fonte já passou',
  nunca_verificada: 'esta camada nunca passou pela verificação de frescor',
  verificacao_antiga: 'a última verificação tem mais de 14 dias (dois ciclos semanais)',
};

export function motivoTexto(motivo) {
  return MOTIVOS[motivo] || 'motivo não registrado';
}

/* `h` entra por parâmetro para este módulo não amarrar o painel do mapa (que monta nó a nó) ao helper de dom
   da tela de acervo — os dois passam o mesmo `h` de web/js/base/dom.js. */
export function selo(c, h) {
  if (!c.verificacao_vencida) {
    return h('span', { class: 'marcador ok', title: 'verificação de frescor em dia' }, 'em dia');
  }
  return h('span', { class: 'marcador falha', title: motivoTexto(c.motivo_vencida) }, AVISO_VENCIDA);
}
