/* plat — leitura de PÁGINAS de um documento `app` (item L5-01-a-layout-paginas).

   Convenção da linha L5-01: um nó de tipo `pagina` só existe na RAIZ do documento (pai=null); tudo o mais
   mora dentro de uma página. Este módulo só LÊ o documento (nenhuma mutação) — quem grava é o mesmo editor
   genérico de L5-08 (`doc.inserir`/`doc.mover`), com a paleta de `paleta_paginas.js`. */
import * as doc from '../editor/documento.js';

export function paginas(documento) {
  return doc.filhos(documento, null).filter((n) => n.tipo === 'pagina');
}

/* páginas na ordem do MENU: por `ordem` crescente, empate por título; `oculta` fica de fora do menu mas
   continua ROTEÁVEL por link direto (a Esri também deixa a página oculta acessível por URL — ela só some da
   navegação, "Hide page" não é "Disable page"). */
export function paginasNoMenu(documento) {
  return paginas(documento)
    .filter((n) => !(n.propriedades || {}).oculta)
    .sort((a, b) => {
      const oa = (a.propriedades || {}).ordem ?? 0;
      const ob = (b.propriedades || {}).ordem ?? 0;
      if (oa !== ob) return oa - ob;
      return String((a.propriedades || {}).titulo || '').localeCompare(String((b.propriedades || {}).titulo || ''));
    });
}

export function paginaPorCaminho(documento, caminho) {
  return paginas(documento).find((n) => (n.propriedades || {}).caminho === caminho) || null;
}

/* página que abre quando a URL não nomeia nenhuma: a marcada `inicial`, senão a 1ª do menu, senão a 1ª
   página que exista (mesmo oculta), senão null (documento sem página nenhuma). */
export function paginaInicial(documento) {
  const marcada = paginas(documento).find((n) => (n.propriedades || {}).inicial);
  if (marcada) return marcada;
  const noMenu = paginasNoMenu(documento);
  if (noMenu.length) return noMenu[0];
  const todas = paginas(documento);
  return todas.length ? todas[0] : null;
}
