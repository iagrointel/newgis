/* plat — tela /executar (item L5-01-a-layout-paginas): abre um item `app` e roda de verdade o documento de
   páginas com `web/js/executor/executor.js` — SEM a barra lateral do instrumento (a página, sobretudo a de
   tela cheia, é dona do viewport inteiro; ver web/estilo/executor.css). Tela fina de propósito, no mesmo
   espírito de `web/js/editor/tela.js`: quem sabe renderizar página/layout é o executor, não esta tela. */
import { obter } from '../base/api.js';
import { carregar, t } from '../base/i18n.js';
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
  const estado = document.getElementById('estado');
  const id = new URLSearchParams(location.search).get('item');
  // estados explícitos (UX-07): sem item, carregando, item inexistente/sem acesso, erro — nunca tela em branco
  estado.addEventListener('acao', (ev) => {
    if (ev.detail.id === 'construtor') location.href = '/construtor';
    if (ev.detail.id === 'tentar') location.reload();
  });
  if (!id) {
    estado.mostrar({ tipo: 'vazio', titulo: t('executor.sem_item_titulo'), texto: t('executor.sem_item_texto'), acoes: [{ id: 'construtor', rotulo: t('executor.ir_construtor') }] });
    return;
  }
  estado.carregando(t('executor.carregando'));
  const r = await obter(`/api/itens/${encodeURIComponent(id)}`);
  if (r.status === 404) {
    estado.mostrar({ tipo: 'vazio', titulo: t('executor.inexistente_titulo'), texto: t('executor.inexistente_texto'), acoes: [{ id: 'construtor', rotulo: t('executor.ir_construtor') }] });
    return;
  }
  if (r.status !== 200) { estado.erro(r); return; }
  estado.limpar();
  const item = r.json;
  if (item.tipo !== 'app' && item.tipo !== 'painel') {
    estado.mostrar({ tipo: 'vazio', titulo: t('executor.nao_e_app_titulo'), texto: t('executor.nao_e_app_texto', { tipo: item.tipo }), acoes: [{ id: 'construtor', rotulo: t('executor.ir_construtor') }] });
    return;
  }
  document.title = `${item.titulo} · ${t('app.nome')}`;
  const dados = item.dados || {};
  const documento = dados.corpo
    ? { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } }
    : novoDocumento(item.tipo);

  const falhas = await prepararWidgets(documento);
  montarExecucao({ raiz, documento, paleta: PALETA_PAGINAS, falhas });
}
