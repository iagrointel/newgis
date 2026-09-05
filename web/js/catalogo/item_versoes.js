/* plat · catálogo — aba Versões (ADR 0004 seção 4): lista paginada, diff JSON Patch entre a versão e a anterior,
   restaurar (cria versão nova) e publicar. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { confirmar } from '../base/componentes.js';
import * as api from './api.js';
import { dataHora } from './formato.js';

const LIMITE = 20;

export function montar(item, { aoMudar }) {
  const raiz = h('div', { class: 'versoes' });
  const aviso = h('plat-aviso');
  const tab = h('plat-tabela', { id: 'versoes-tabela', legenda: t('catalogo.versoes') });
  const pag = h('plat-paginacao', { id: 'versoes-paginacao' });
  const diffArea = h('div', { id: 'versoes-diff', hidden: true });
  let deslocamento = 0;
  const podeEditar = !!item.pode_editar;

  tab.colunas = [
    { chave: 'versao', titulo: t('catalogo.versao'), classe: 'num', formatar: (v) => (v === item.versao_atual ? `${v} (${t('catalogo.versao_atual')})` : String(v)) },
    { chave: 'autor', titulo: t('catalogo.autor'), formatar: (a) => (a ? (a.login || a.nome || String(a.id ?? a)) : '—') },
    { chave: 'criado_em', titulo: t('campo.quando'), formatar: (v) => dataHora(v) },
    { chave: 'rotulo', titulo: t('catalogo.rotulo'), formatar: (v, l) => `${v || ''}${l.compactou ? ` (${t('catalogo.compactou', { n: l.compactou })})` : ''}${item.versao_publicada === l.versao ? ` · ${t('catalogo.publicada')}` : ''}` },
    { chave: 'comentario', titulo: t('catalogo.comentario'), formatar: (v) => v || '' },
  ];
  tab.acoes = (l) => {
    const a = [{ id: 'diff', rotulo: t('catalogo.ver_diff') }];
    if (podeEditar && l.versao !== item.versao_atual) a.push({ id: 'restaurar', rotulo: t('catalogo.restaurar') });
    if (podeEditar && item.versao_publicada !== l.versao) a.push({ id: 'publicar', rotulo: t('catalogo.publicar') });
    return a;
  };
  tab.addEventListener('acao', async (e) => {
    const l = e.detail.linha;
    aviso.limpar();
    try {
      if (e.detail.id === 'diff') { await mostrarDiff(l.versao); return; }
      if (e.detail.id === 'restaurar') {
        if (!(await confirmar(t('catalogo.restaurar'), t('catalogo.restaurar_versao_confirma', { n: l.versao })))) return;
        const novo = await api.versaoRestaurar(item.id, l.versao);
        aviso.ok(t('catalogo.versao_restaurada', { n: l.versao, nova: novo.versao_atual }));
        aoMudar(novo);
        item.versao_atual = novo.versao_atual;
        await carregar();
        return;
      }
      if (e.detail.id === 'publicar') {
        const novo = await api.versaoPublicar(item.id, l.versao);
        item.versao_publicada = novo.versao_publicada;
        aviso.ok(t('catalogo.versao_publicada', { n: l.versao }));
        aoMudar(novo);
        await carregar();
      }
    } catch (err) { aviso.erro(err.message); }
  });
  pag.addEventListener('mudar', (e) => { deslocamento = e.detail.deslocamento; carregar(); });

  async function mostrarDiff(n) {
    limpar(diffArea);
    diffArea.hidden = false;
    diffArea.append(h('p', { class: 'fraco' }, t('catalogo.carregando')));
    try {
      const v = await api.versao(item.id, n, n > 1 ? n - 1 : undefined);
      limpar(diffArea);
      const fechar = h('button', { type: 'button', class: 'pequeno texto' }, t('acao.fechar'));
      fechar.addEventListener('click', () => { diffArea.hidden = true; });
      diffArea.append(h('div', { class: 'linha-ferramentas' }, h('strong', {}, t('catalogo.diff_titulo', { n, de: n > 1 ? n - 1 : '—' })), h('code', { class: 'fraco' }, `sha256 ${String(v.sha256 || '').slice(0, 16)}…`), h('div', { class: 'direita' }, fechar)));
      const patch = Array.isArray(v.diff) ? v.diff : null;
      if (patch && !patch.length) diffArea.append(h('p', { class: 'fraco' }, t('catalogo.diff_vazio')));
      else if (patch) {
        const ul = h('ul', { class: 'lista-relacoes' });
        for (const op of patch) ul.append(h('li', {}, h('span', { class: `marcador ${op.op === 'remove' ? 'falha' : op.op === 'add' ? 'ok' : 'info'}` }, op.op), h('code', {}, op.path), op.value === undefined ? null : h('span', { class: 'diff' }, JSON.stringify(op.value).slice(0, 300))));
        diffArea.append(ul);
      } else diffArea.append(h('pre', { class: 'diff' }, JSON.stringify(v.corpo, null, 2)));
    } catch (err) { limpar(diffArea); diffArea.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, err.message)); }
  }

  async function carregar() {
    try {
      const r = await api.versoes(item.id, { limite: LIMITE, deslocamento });
      tab.linhas = r.itens || [];
      tab.vazio = t('catalogo.sem_versoes');
      pag.atualizar({ total: r.total ?? (r.itens || []).length, limite: LIMITE, deslocamento });
    } catch (err) { aviso.erro(err.message); tab.linhas = []; }
  }
  raiz.append(aviso, h('p', { class: 'fraco' }, t('catalogo.versoes_texto')), tab, pag, diffArea);
  carregar();
  return raiz;
}
