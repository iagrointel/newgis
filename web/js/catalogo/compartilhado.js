/* plat · catálogo — página anônima /c/<token> (ADR 0004 seção 15.4): GET /api/compartilhado/<token> devolve o item e os
   itens incluídos em contexto só de leitura; 404 (revogado/inexistente) e 410 (expirado) viram mensagem com o código.
   Sem sessão, sem barra lateral; a descrição saneada do servidor passa de novo pelo DOMPurify. */
import '../base/componentes.js';
import { anexar, h, limpar, htmlSeguro } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { pronto } from '../base/layout.js';
import * as api from './api.js';
import { bytes, dataHora, elipse } from './formato.js';

const el = (id) => document.getElementById(id);
const token = decodeURIComponent((/^\/c\/([^/]+)/.exec(location.pathname) || [])[1] || '');

await carregarIdioma();
await principal();
pronto();

async function principal() {
  const aviso = el('aviso');
  if (!token) { aviso.erro(t('catalogo.link_invalido', { codigo: 404 })); return; }
  let r;
  try {
    r = await api.compartilhado(token);
  } catch (e) {
    aviso.erro(e.status === 410 ? t('catalogo.link_expirado', { codigo: 410 }) : e.status === 404 ? t('catalogo.link_invalido', { codigo: 404 }) : e.status === 429 ? t('login.muitas_tentativas') : e.message);
    return;
  }
  const it = r.item || r;
  const sec = el('item');
  limpar(sec);
  document.title = `${elipse(it.titulo, 60)} · ${t('app.nome')}`;
  const mini = h('img', { class: 'mini', src: api.compartilhadoMiniaturaUrl(token, it.id), alt: '', width: 600, height: 400 });
  mini.addEventListener('error', () => mini.remove(), { once: true });
  // anexar() (não o append nativo, que escreve o texto "null" para um filho nulo — defeito visto na captura do L0-03-e)
  anexar(sec, [h('h2', {}, it.titulo), it.miniatura ? mini : null, h('p', { class: 'fraco' }, `${it.tipo || ''} · ${dataHora(it.modificado_em)} · ${bytes(it.tamanho_bytes)}`), it.resumo ? h('p', {}, it.resumo) : null]);
  if (it.descricao_html) { const d = h('div', { class: 'descricao-html' }); d.append(htmlSeguro(it.descricao_html)); sec.append(d); }
  if ((it.tags || []).length) sec.append(h('div', { class: 'chips' }, ...it.tags.map((tg) => h('span', { class: 'chip' }, h('span', { class: 'nome' }, tg)))));
  if (it.creditos) sec.append(h('p', { class: 'fraco' }, `${t('catalogo.creditos')}: ${it.creditos}`));
  if (r.permite_download && r.download_url) sec.append(h('p', {}, h('a', { class: 'botao', href: r.download_url }, t('catalogo.baixar'))));
  sec.hidden = false;
  const incluidos = Array.isArray(r.itens_incluidos) ? r.itens_incluidos : [];
  if (incluidos.length) {
    const tab = el('incluidos-tabela');
    tab.setAttribute('legenda', t('catalogo.link_incluidos'));
    tab.colunas = [{ chave: 'titulo', titulo: t('catalogo.col_titulo') }, { chave: 'tipo', titulo: t('catalogo.col_tipo') }, { chave: 'modificado_em', titulo: t('catalogo.col_modificado'), formatar: (v) => dataHora(v) }];
    tab.linhas = incluidos;
    el('incluidos').hidden = false;
  }
}
