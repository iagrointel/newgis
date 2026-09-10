/* plat — tela /executar (item L5-01-a-layout-paginas; tema do L5-10-temas-marca): abre um item `app` e roda
   de verdade o documento de páginas com `web/js/executor/executor.js` — SEM a barra lateral do instrumento
   (a página, sobretudo a de tela cheia, é dona do viewport inteiro; ver web/estilo/executor.css). Tela fina
   de propósito, no mesmo espírito de `web/js/editor/tela.js`: quem sabe renderizar página/layout é o
   executor, não esta tela.
   Tema (L5-10): a cadeia documento.corpo.tema -> inquilino -> padrão é resolvida com os dados de
   GET /api/temas e aplicada como CSS custom properties na raiz — trocar de tema no seletor flutuante
   re-aplica tokens (style.setProperty), NUNCA recarrega a página (cláusula 1 do portão). */
import { obter, mensagemDe } from '../base/api.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { montarExecucao } from './executor.js';
import { PALETA_PAGINAS } from '../editor/paleta_paginas.js';
import { novoDocumento } from '../editor/documento.js';
import { carregar as carregarTemas, montarSeletor, resolver as resolverTema, aplicar as aplicarTema } from '../temas/temas.js';

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

  // tema ANTES da primeira pintura das páginas: a cadeia documento -> inquilino -> padrão (o documento
  // sem tema nenhum renderiza com o padrão da plataforma — cláusula 5 do portão)
  let dadosTemas = null;
  try {
    dadosTemas = await carregarTemas();
  } catch {
    // sem /api/temas o app segue com os tokens da plataforma (falha de tema não derruba a execução)
  }
  const selecaoTema = documento.corpo.tema || null;
  if (dadosTemas) {
    const resolvido = resolverTema(selecaoTema, dadosTemas);
    aplicarTema(raiz, resolvido.definicao);
    raiz.dataset.temaOrigem = resolvido.origem;
    raiz.after(montarSeletor({
      raiz,
      dados: dadosTemas,
      selecaoDocumento: selecaoTema,
    }));
  }

  montarExecucao({ raiz, documento, paleta: PALETA_PAGINAS });
}
