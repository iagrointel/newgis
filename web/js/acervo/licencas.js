/* plat · acervo — vocabulário fechado de licença (item L6-01-g, tabela plat.acervo_licenca, migração 043) e a
   regra de atribuição obrigatória (item L6-01-c). Módulo próprio porque DUAS telas dependem da mesma resposta:
   /acervo (cartão e ficha) e /mapa (legenda das camadas do acervo). Uma cópia em cada tela seria duas verdades.

   O rótulo acentuado existe só para a tela; o valor gravado no banco segue sem acento de propósito (evita duas
   grafias da mesma coisa por encoding). Nada aqui infere licença de texto livre: `licenca_curada_tipo` só chega
   preenchido quando a curadoria por HTTP do L6-01-g confirmou a licença na página do órgão. */

export const ROTULO_LICENCA = {
  CC0: 'CC0 (domínio público)',
  'CC-BY': 'CC-BY (atribuição)',
  'CC-BY-SA': 'CC-BY-SA (atribuição + compartilhamento pelas mesmas regras)',
  ODbL: 'ODbL (atribuição obrigatória)',
  'dado-aberto-com-termo-do-orgao': 'dado aberto — termo próprio do órgão',
  Copernicus: 'Copernicus (atribuição obrigatória)',
  'licenca-propria': 'licença própria da fonte',
  'nao-declarada': 'não declarada',
};

// as licenças que EXIGEM crédito visível de quem usa o dado (hipótese literal do portão do item L6-01-c:
// "aviso de atribuição obrigatória para ODbL e CC BY-SA"); as demais do vocabulário não exigem o aviso.
export const EXIGE_ATRIBUICAO = new Set(['ODbL', 'CC-BY-SA']);

export function exigeAtribuicao(tipo) {
  return Boolean(tipo) && EXIGE_ATRIBUICAO.has(tipo);
}

export function rotuloLicenca(tipo) {
  return tipo ? (ROTULO_LICENCA[tipo] || tipo) : null;
}
