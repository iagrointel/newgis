/* plat — o que o domínio faz com um VALOR na tela (item L2-10-a).

   Uma função só, usada em todo lugar onde um valor de campo aparece: no formulário (a lista de escolha), no
   popup e na tabela. É isto que faz a tela mostrar "São Paulo" onde o banco guarda "SP" — em nenhuma tela o
   usuário vê o código quando existe descrição, e em nenhuma tela o código deixa de ser o que se grava.

   `ligacoes` é a resposta de GET /api/camadas/{id}/dominios: cada linha tem campo, subtipo_codigo (nulo = o
   domínio padrão da camada) e valores. A escolha do domínio de um campo depende do subtipo ATUAL da feição,
   por isso toda função recebe o subtipo junto. */

export function dominioDoCampo(ligacoes, campo, subtipo) {
  const doSubtipo = ligacoes.find((l) => l.campo === campo && l.subtipo_codigo !== null
    && String(l.subtipo_codigo) === String(subtipo));
  return doSubtipo || ligacoes.find((l) => l.campo === campo && l.subtipo_codigo === null) || null;
}

/* o que a tela MOSTRA para um valor gravado. Sem domínio, o próprio valor; com domínio codificado, a
   descrição; código fora da lista (dado antigo, domínio editado depois) volta como o código entre parênteses,
   nunca some da tela e nunca é confundido com um valor válido. */
export function rotulo(ligacoes, campo, valor, subtipo) {
  if (valor === null || valor === undefined || valor === '') return '';
  const d = dominioDoCampo(ligacoes, campo, subtipo);
  if (!d || d.tipo !== 'codificado') return String(valor);
  const achado = (d.valores || []).find((v) => String(v.codigo) === String(valor));
  return achado ? achado.descricao : `${valor} (fora do domínio)`;
}

/* as opções de uma lista de escolha, já ordenadas e sem os valores inativos (um valor inativo continua
   válido no banco para o dado que já o usa; o que ele não é mais é OFERECIDO) */
export function opcoes(dominio) {
  return (dominio.valores || [])
    .filter((v) => v.ativo !== false)
    .slice()
    .sort((a, b) => (a.ordem ?? 0) - (b.ordem ?? 0))
    .map((v) => ({ codigo: v.codigo, descricao: v.descricao }));
}

/* o campo de subtipo também é código na tabela e nome na tela: 2 vira "Rural" */
export function rotuloSubtipo(subtipo, valor) {
  if (valor === null || valor === undefined || valor === '') return '';
  const achado = ((subtipo && subtipo.valores) || []).find((v) => String(v.codigo) === String(valor));
  return achado ? achado.nome : `${valor} (fora da lista de subtipos)`;
}

export function faixa(dominio) {
  return dominio && dominio.tipo === 'intervalo' ? dominio.valores : null;
}
