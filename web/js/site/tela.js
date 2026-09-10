/* plat — tela /sites (item L5-20-sites-paginas-publicas): construtor do site do inquilino por arrasto e a
   publicação dele em /s/<inquilino>/.

   A tela é fina, como a do /construtor (L5-08): tudo o que edita documento está em web/js/editor/*, e o que
   esta tela acrescenta é (1) a paleta de site, (2) o gravar com versão otimista e (3) a caixa de publicação,
   com a opção de indexação e o aviso que a acompanha — `noindex` é o padrão da casa e ligar a indexação é uma
   decisão consciente do dono do site, nunca um valor herdado em silêncio.

   O que a página PUBLICADA mostra não é montado aqui: ela sai pronta do servidor (L5_CONCEITO D24). Esta tela
   monta o DOCUMENTO; a prova de que o servidor a desenha igual é o e2e do item. */
import { obter, chamar, mensagemDe } from '../base/api.js';
import { h } from '../base/dom.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from '../editor/editor.js';
import { PALETA_SITE } from '../editor/paleta_site.js';
import { novoDocumento } from '../editor/documento.js';

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/sites' });
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  const h1 = document.querySelector('main > h1');
  const id = new URLSearchParams(location.search).get('item');

  let item = null;
  let documento = novoDocumento('site');
  documento.esquema_versao = 1;
  if (id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    const dados = item.dados || {};
    documento = { tipo: 'site', esquema_versao: dados.esquema_versao || 1, corpo: { nos: [], ligacoes: [], ...(dados.corpo || {}) } };
    h1.textContent = item.titulo;
    document.title = `${item.titulo} · sites · plat`;
  }

  const alvo = h('div', { id: 'editor-raiz' });
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !id }, 'Salvar');
  const estado = h('span', { id: 'estado-salvo', class: 'estado' }, id ? 'sem alterações' : 'sem item: passe ?item=<id de site>');
  principal.append(h('div', { class: 'linha-ferramentas' }, btSalvar, estado), caixaPublicacao(), alvo);

  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: PALETA_SITE,
    aoMudar: () => { estado.textContent = 'alterações não gravadas'; },
  });

  btSalvar.addEventListener('click', async () => {
    if (!item) return;
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: 'site', esquema_versao: d.esquema_versao || 1, corpo: d.corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status !== 200) { estado.textContent = 'não gravado'; aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    aviso.limpar?.();
    estado.textContent = `gravado (versão ${item.versao_atual})`;
  });

  function caixaPublicacao() {
    const indexar = h('input', { type: 'checkbox', id: 'site-indexavel' });
    const avisoIndexar = h('p', { class: 'ajuda', id: 'site-aviso-indexar' },
      'Com a indexação ligada, buscadores podem listar as páginas deste site. O padrão é não indexar.');
    const btPublicar = h('button', { type: 'button', id: 'publicar', class: 'primario', disabled: !id }, 'Publicar site');
    const btRetirar = h('button', { type: 'button', id: 'despublicar', class: 'perigo', disabled: true }, 'Retirar do ar');
    const linha = h('p', { id: 'site-estado', class: 'estado' }, 'site não publicado');
    const link = h('a', { id: 'site-url', href: '#', hidden: true, rel: 'noopener', target: '_blank' }, 'abrir site');

    function mostrar(s) {
      if (!s) {
        linha.textContent = 'site não publicado';
        link.hidden = true;
        btRetirar.disabled = true;
        return;
      }
      linha.textContent = `publicado (versão ${s.versao_publicada}) · ${s.indexavel ? 'indexável' : 'não indexável'}`;
      link.href = `/s/${s.tenant_slug}/`;
      link.hidden = false;
      indexar.checked = !!s.indexavel;
      btRetirar.disabled = false;
    }

    if (id) obter(`/api/itens/${id}/site`).then((r) => { if (r.status === 200) mostrar(r.json); });

    btPublicar.addEventListener('click', async () => {
      if (!item) return;
      btPublicar.disabled = true;
      const r = await chamar('PUT', `/api/itens/${item.id}/site`, { indexavel: indexar.checked });
      btPublicar.disabled = false;
      if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
      aviso.limpar?.();
      mostrar(r.json);
    });
    btRetirar.addEventListener('click', async () => {
      if (!item) return;
      const r = await chamar('DELETE', `/api/itens/${item.id}/site`, null);
      if (r.status !== 204) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
      mostrar(null);
    });

    return h('section', { class: 'caixa', id: 'caixa-publicacao', 'aria-label': 'Publicação do site' },
      h('h2', {}, 'Publicação'),
      linha,
      h('p', {}, h('label', { for: 'site-indexavel' }, indexar, ' permitir indexação por buscadores')),
      avisoIndexar,
      h('p', { class: 'linha-ferramentas' }, btPublicar, btRetirar, link));
  }
}
