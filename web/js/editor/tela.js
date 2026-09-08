/* plat — tela /construtor (item L5-08-editor-arrasto): abre um item de tipo `app` ou `painel` do catálogo,
   monta o editor de arrasto sobre o documento do item (L5-05) e grava com PATCH /api/itens/{id}.

   A tela é fina de propósito: tudo o que edita documento está em web/js/editor/{documento,editor,arrasto,
   esquema,paleta}.js, que é o que os outros doze construtores da linha vão reusar. Aqui só há: sessão,
   carregar, salvar e o aviso de conflito de versão (409, D12: versão otimista).
   Idioma: textos em português literal nesta tela; a passagem para o dicionário é o item
   L5-12-acessibilidade-i18n-construtores, que cobre os construtores todos de uma vez. */
import { obter, chamar, mensagemDe } from '../base/api.js';
import { h, limpar as limparFilhos } from '../base/dom.js';
import { carregar } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from './editor.js';
import { PALETA_LAYOUT } from './paleta.js';
import { PALETA_PAGINAS } from './paleta_paginas.js';
import { PALETA_NARRATIVA } from './paleta_narrativa.js';
import { novoDocumento } from './documento.js';

/* item `app` ganha a paleta de PÁGINAS E LAYOUT (L5-01-a: página, cabeçalho, menu, janela, ...); os demais
   tipos de construtor continuam com a paleta de layout comum do L5-08, sem página nenhuma dentro deles. */
function paletaDoTipo(tipo) {
  if (tipo === 'app') return PALETA_PAGINAS;
  if (tipo === 'narrativa') return PALETA_NARRATIVA; // item L5-04-a: blocos de narrativa, lista sem aninhamento
  return PALETA_LAYOUT;
}

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/construtor' });
  const principal = document.getElementById('principal');
  const id = new URLSearchParams(location.search).get('item');
  const aviso = document.getElementById('aviso');
  const h1 = document.querySelector('main > h1');

  let item = null;
  let documento = novoDocumento('app');
  if (id) {
    const r = await obter(`/api/itens/${id}`);
    if (r.status !== 200) { aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    const dados = item.dados || {};
    if (dados.corpo) documento = { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } };
    else documento = novoDocumento(item.tipo);
    h1.textContent = item.titulo;
    document.title = `${item.titulo} · construtor · plat`;
  }

  const alvo = h('div', { id: 'editor-raiz' });
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !id }, 'Salvar');
  const estado = h('span', { id: 'estado-salvo', class: 'estado' }, id ? 'sem alterações' : 'sem item: passe ?item=<id>');
  const executavel = documento.tipo === 'app' || documento.tipo === 'narrativa';
  const linkExecutar = executavel && id
    ? h('a', { id: 'executar', class: 'pequeno', href: `/executar?item=${id}`, target: '_blank', rel: 'noopener' }, documento.tipo === 'narrativa' ? 'Ler' : 'Executar')
    : null;
  /* publicar por link (L5-14): o servidor recusa narrativa com imagem sem texto alternativo — a mensagem dele
     aparece aqui, bloco a bloco, e a publicação não acontece (portão do L5-04-a) */
  const btPublicar = documento.tipo === 'narrativa' && id
    ? h('button', { type: 'button', id: 'publicar', class: 'pequeno' }, 'Publicar')
    : null;
  const linkPublicado = h('span', { id: 'publicado-em', class: 'estado' }, '');
  principal.append(h('div', { class: 'linha-ferramentas' }, btSalvar, estado, linkExecutar, btPublicar, linkPublicado), alvo);

  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: paletaDoTipo(documento.tipo),
    aoMudar: () => { estado.textContent = 'alterações não gravadas'; },
  });

  btPublicar?.addEventListener('click', async () => {
    if (!item) return;
    const slugPadrao = (item.titulo || 'narrativa').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'narrativa';
    const slug = window.prompt('endereço da publicação (/p/<inquilino>/<slug>)', slugPadrao);
    if (slug === null) return;
    btPublicar.disabled = true;
    const r = await chamar('POST', `/api/itens/${item.id}/publicacao`, { slug });
    btPublicar.disabled = false;
    if (r.status !== 201 && r.status !== 200) {
      const detalhe = Array.isArray(r.json?.detalhe) ? r.json.detalhe : [];
      const linhas = detalhe.filter((d) => d && d.erro).map((d) => `${d.tipo || 'bloco'}: ${d.erro}`);
      aviso.mostrar(linhas.length ? `${r.json.mensagem} — ${linhas.join(' · ')}` : mensagemDe(r), 'erro');
      linkPublicado.textContent = 'não publicado';
      linkPublicado.dataset.estado = 'recusado';
      return;
    }
    aviso.limpar?.();
    limparFilhos(linkPublicado);
    linkPublicado.dataset.estado = 'publicado';
    linkPublicado.append('publicado em ', h('a', { href: r.json.url, target: '_blank', rel: 'noopener', id: 'link-publicado' }, r.json.url));
  });

  btSalvar.addEventListener('click', async () => {
    if (!item) return;
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status !== 200) { estado.textContent = 'não gravado'; aviso.mostrar(mensagemDe(r), 'erro'); return; }
    item = r.json;
    aviso.limpar?.();
    estado.textContent = `gravado (versão ${item.versao_atual})`;
  });
}
