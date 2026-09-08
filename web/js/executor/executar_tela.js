/* plat — tela /executar (item L5-01-a-layout-paginas): abre um item `app` e roda de verdade o documento de
   páginas com `web/js/executor/executor.js` — SEM a barra lateral do instrumento (a página, sobretudo a de
   tela cheia, é dona do viewport inteiro; ver web/estilo/executor.css). Tela fina de propósito, no mesmo
   espírito de `web/js/editor/tela.js`: quem sabe renderizar página/layout é o executor, não esta tela. */
import { obter, mensagemDe } from '../base/api.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { montarExecucao, prepararWidgets } from './executor.js';
import { PALETA_PAGINAS } from '../editor/paleta_paginas.js';
import { novoDocumento } from '../editor/documento.js';

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  const raiz = document.getElementById('raiz-execucao');
  const aviso = document.getElementById('aviso');
  const id = new URLSearchParams(location.search).get('item');
  if (!id) { aviso.mostrar('passe ?item=<id> na URL', 'erro'); return; }

  const r = await obter(`/api/itens/${id}`);
  if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
  const item = r.json;
  const dados = item.dados || {};
  const documento = dados.corpo
    ? { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } }
    : novoDocumento(item.tipo);

  const falhas = await prepararWidgets(documento);
  montarExecucao({ raiz, documento, paleta: PALETA_PAGINAS, falhas });
}
