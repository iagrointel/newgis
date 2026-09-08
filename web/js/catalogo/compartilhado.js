/* plat · catálogo — página anônima /c/<token> (ADR 0004 seção 15.4; UX-05): GET /api/compartilhado/<token> devolve o
   item e os itens incluídos em contexto só de leitura; 404 (revogado/inexistente), 410 (expirado) e 429 viram um
   <plat-estado> nomeado com o código. Sem sessão e sem o chrome interno (nada de barra lateral nem menu): só a marca,
   idioma e tema. Clicar num item incluído lê GET /api/compartilhado/<token>/itens/<id> e mostra a ficha dele aqui
   mesmo. A descrição saneada do servidor passa de novo pelo DOMPurify. */
import '../base/componentes.js';
import { h, limpar, htmlSeguro } from '../base/dom.js';
import { aoTraduzir, aplicar, carregar as carregarIdioma, t } from '../base/i18n.js';
import { pronto } from '../base/layout.js';
import * as api from './api.js';
import { bytes, dataHora, elipse } from './formato.js';

const el = (id) => document.getElementById(id);
const token = decodeURIComponent((/^\/c\/([^/]+)/.exec(location.pathname) || [])[1] || '');
const s = { resposta: null, incluidoAberto: null };

await carregarIdioma();
aplicar(document);
el('estado').addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') principal(); });
aoTraduzir(() => { aplicar(document); if (s.resposta) renderizar(s.resposta); });
await principal();
pronto();

function mostrarErro(e) {
  const estado = el('estado');
  const status = e && e.status;
  if (status === 410) estado.mostrar({ tipo: 'vazio', titulo: t('catalogo.link_expirado_titulo'), texto: t('catalogo.link_expirado', { codigo: 410 }) });
  else if (status === 404 || !token) estado.mostrar({ tipo: 'vazio', titulo: t('catalogo.link_invalido_titulo'), texto: t('catalogo.link_invalido', { codigo: 404 }) });
  else if (status === 429) estado.mostrar({ tipo: 'erro', titulo: t('login.muitas_tentativas'), texto: t('catalogo.link_429'), acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
  else estado.erro({ status: status || 0, json: { mensagem: e && e.message, req_id: e && e.reqId } });
  document.title = `${t('catalogo.compartilhado_titulo')} · ${t('app.nome')}`;
}

async function principal() {
  const estado = el('estado');
  el('item').hidden = true;
  el('incluidos').hidden = true;
  el('incluido').hidden = true;
  if (!token) { mostrarErro({ status: 404 }); return; }
  estado.carregando(t('catalogo.link_carregando'));
  let r;
  try {
    r = await api.compartilhado(token);
  } catch (e) {
    mostrarErro(e);
    return;
  }
  estado.limpar();
  s.resposta = r;
  renderizar(r);
}

function fichaItem(it, { podeBaixar = false, downloadUrl = null, miniaturaUrl = null } = {}) {
  const sec = h('div', { class: 'ficha-item' });
  const mini = miniaturaUrl ? h('img', { class: 'mini', src: miniaturaUrl, alt: '', width: 600, height: 400 }) : null;
  if (mini) mini.addEventListener('error', () => mini.remove(), { once: true });
  sec.append(
    h('h2', {}, it.titulo),
    it.miniatura && mini ? mini : null,
    h('p', { class: 'fraco' }, `${it.tipo || ''} · ${dataHora(it.modificado_em)} · ${bytes(it.tamanho_bytes)}`),
    it.resumo ? h('p', {}, it.resumo) : null,
  );
  if (it.descricao_html) { const d = h('div', { class: 'descricao-html' }); d.append(htmlSeguro(it.descricao_html)); sec.append(d); }
  if ((it.tags || []).length) sec.append(h('div', { class: 'chips' }, ...it.tags.map((tg) => h('span', { class: 'chip' }, h('span', { class: 'nome' }, tg)))));
  if (it.creditos) sec.append(h('p', { class: 'fraco' }, `${t('catalogo.creditos')}: ${it.creditos}`));
  if (podeBaixar && downloadUrl) sec.append(h('p', {}, h('a', { class: 'botao', href: downloadUrl }, t('catalogo.baixar'))));
  return sec;
}

function renderizar(r) {
  const it = r.item || r;
  const sec = el('item');
  limpar(sec);
  document.title = `${elipse(it.titulo, 60)} · ${t('app.nome')}`;
  sec.append(fichaItem(it, { podeBaixar: r.permite_download, downloadUrl: r.download_url, miniaturaUrl: api.compartilhadoMiniaturaUrl(token, it.id) }));
  sec.hidden = false;
  const incluidos = Array.isArray(r.itens_incluidos) ? r.itens_incluidos : [];
  const secInc = el('incluidos');
  if (incluidos.length) {
    const tab = el('incluidos-tabela');
    tab.setAttribute('legenda', t('catalogo.link_incluidos'));
    tab.querySelector('table')?.setAttribute('aria-label', t('catalogo.link_incluidos'));
    tab.colunas = [
      { chave: 'titulo', titulo: t('catalogo.col_titulo') },
      { chave: 'tipo', titulo: t('catalogo.col_tipo') },
      { chave: 'modificado_em', titulo: t('catalogo.col_modificado'), formatar: (v) => dataHora(v) },
    ];
    tab.acoes = () => [{ id: 'ver', rotulo: t('acao.ver'), classe: 'acao-ver' }];
    tab.linhas = incluidos;
    if (!tab.dataset.ligado) {
      tab.dataset.ligado = '1';
      tab.addEventListener('acao', (ev) => { if (ev.detail.id === 'ver') abrirIncluido(ev.detail.linha); });
    }
    secInc.hidden = false;
  } else {
    secInc.hidden = true;
  }
  if (s.incluidoAberto) abrirIncluido(s.incluidoAberto);
}

/* GET /api/compartilhado/{token}/itens/{id}: a ficha completa de um item incluído, no mesmo contexto do link */
async function abrirIncluido(linha) {
  const sec = el('incluido');
  limpar(sec);
  sec.hidden = false;
  const estado = h('plat-estado');
  sec.append(estado);
  estado.carregando(t('catalogo.link_carregando'));
  s.incluidoAberto = linha;
  // api.chamar devolve o JSON no sucesso e lança ErroApi ({status, message, reqId}) em qualquer falha
  const r = await api.chamar('GET', `/api/compartilhado/${encodeURIComponent(token)}/itens/${encodeURIComponent(linha.id)}`).catch((e) => e);
  limpar(sec);
  if (r instanceof Error) {
    const e2 = h('plat-estado');
    sec.append(e2);
    e2.erro({ status: r.status || 0, json: { mensagem: r.message, req_id: r.reqId } });
    return;
  }
  const it = r;
  const fechar = h('button', { type: 'button', class: 'pequeno texto fechar-incluido' }, t('acao.fechar'));
  fechar.addEventListener('click', () => { s.incluidoAberto = null; sec.hidden = true; limpar(sec); el('incluidos-tabela').querySelector('button')?.focus(); });
  sec.append(h('div', { class: 'linha-ferramentas' }, h('h2', {}, t('catalogo.link_incluido_titulo')), h('div', { class: 'direita' }, fechar)));
  sec.append(fichaItem(it, { podeBaixar: false, miniaturaUrl: api.compartilhadoMiniaturaUrl(token, it.id) }));
  sec.scrollIntoView({ block: 'nearest' });
  sec.querySelector('h2')?.focus?.();
}
