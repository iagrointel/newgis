/* plat · coleção — página interna /colecao?item=<id> (L5-04-c). Leitora da coleção + publicar por link: a
   resposta do POST traz `avisos` com os itens citados que ficaram fora, e o botão "corrigir" revoga e recria
   o link incluindo-os. O tema declarado no corpo fica no dado; aplicar a cadeia de temas é do L5-10
   (cláusula pendente enquanto a dependência não chega ao master). */
import '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import * as api from '../catalogo/api.js';
import { montar, separar } from './leitor.js';

const el = (id) => document.getElementById(id);
const ACHOU = /[?&]item=([0-9a-f-]{36})/i.exec(location.search);

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/conteudo' });
  await principal();
}
pronto();

async function principal() {
  const aviso = el('aviso');
  if (!ACHOU) {
    aviso.erro(t('colecao.sem_item'));
    return;
  }
  let it;
  try {
    it = await api.chamar('GET', `/api/itens/${ACHOU[1]}`);
  } catch (e) {
    aviso.erro(e.message || t('erro.carregar'));
    return;
  }
  const corpo = (it.dados && it.dados.corpo) || {};
  const refs = corpo.itens || [];
  const carregados = new Map();
  await Promise.all(
    refs.map(async (ref) => {
      try {
        carregados.set(ref.item_id, await api.chamar('GET', `/api/itens/${ref.item_id}`));
      } catch {
        /* sem acesso ao item citado: entra como ausente na leitora */
      }
    }),
  );
  const { presentes, ausentes } = separar(refs, carregados);
  document.title = `${(corpo.capa || {}).titulo || it.titulo} · ${t('app.nome')}`;
  const avisos = ausentes.map((a) => t('colecao.sem_acesso', { titulo: a.rotulo || a.item_id }));
  montar(el('leitor'), corpo.capa || {}, presentes, avisos, { aoAbrir: (x) => `/conteudo/${x.id}` });
  publicar(it);
}

/* seção "publicar por link": cria, lista avisos e oferece recriar incluindo o que ficou de fora */
function publicar(it) {
  const secao = el('compartilhar');
  const avisoLink = el('aviso-link');
  const saida = el('links');

  const mostrar = (link) => {
    limpar(saida);
    avisoLink.limpar();
    saida.append(h('p', {}, h('a', { href: link.url, id: 'link-publico' }, link.url)));
    const fora = link.avisos || [];
    if (fora.length) {
      avisoLink.erro(t('colecao.avisos_texto', { n: fora.length }));
      for (const a of fora) saida.append(h('p', { class: 'fraco' }, t('colecao.fora_do_link', { titulo: a.titulo || a.id })));
      const bt = h('button', { type: 'button', class: 'botao', id: 'botao-corrigir' }, t('colecao.corrigir'));
      bt.addEventListener('click', async () => {
        try {
          await api.chamar('DELETE', `/api/itens/${it.id}/links/${link.id}`);
          const refeito = await api.chamar('POST', `/api/itens/${it.id}/links`, {
            nome: t('colecao.link_nome'),
            itens_incluidos: fora.map((a) => a.id),
          });
          mostrar(refeito);
        } catch (e) {
          avisoLink.erro(e.message || t('erro.carregar'));
        }
      });
      saida.append(h('p', {}, bt));
    } else {
      avisoLink.ok(t('colecao.link_completo'));
    }
  };

  el('botao-link').addEventListener('click', async () => {
    try {
      mostrar(await api.chamar('POST', `/api/itens/${it.id}/links`, { nome: t('colecao.link_nome') }));
    } catch (e) {
      avisoLink.erro(e.message || t('erro.carregar'));
    }
  });
  secao.hidden = false;
}
