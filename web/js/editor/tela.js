/* plat — tela /construtor (itens L5-08-editor-arrasto e UX-07): abre um item de tipo `app` ou `painel` do
   catálogo, monta o editor de arrasto sobre o documento do item (L5-05) e grava com PATCH /api/itens/{id}.

   A tela é fina de propósito: tudo o que edita documento está em web/js/editor/{documento,editor,arrasto,
   esquema,paleta}.js, que é o que os outros doze construtores da linha vão reusar. Aqui só há: sessão, a
   escolha do item (sem ?item= a tela lista os aplicativos e painéis que a conta pode editar e cria um novo),
   carregar, salvar, publicar (POST /api/itens/{id}/versoes/{n}/publicar) e o aviso de conflito de versão
   (409, D12: versão otimista). Estados explícitos por <plat-estado>; textos do chrome pelo dicionário
   (construtor.*); os rótulos da PALETA continuam dados do documento (item L5-12 os leva ao dicionário). */
import { obter, chamar, enviar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, formatarData, t } from '../base/i18n.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { tem } from '../base/estado.js';
import { exigirSessao } from '../auth/sessao.js';
import { criarEditor } from './editor.js';
import { PALETA_LAYOUT } from './paleta.js';
import { PALETA_PAGINAS } from './paleta_paginas.js';
import { novoDocumento } from './documento.js';

/* item `app` ganha a paleta de PÁGINAS E LAYOUT (L5-01-a: página, cabeçalho, menu, janela, ...); os demais
   tipos de construtor continuam com a paleta de layout comum do L5-08, sem página nenhuma dentro deles. */
function paletaDoTipo(tipo) { return tipo === 'app' ? PALETA_PAGINAS : PALETA_LAYOUT; }
/* `app` roda no executor de páginas; `painel` (grade de widgets, sem página) roda em /aplicativo pelo motor */
function urlExecucao(item) { return `${item.tipo === 'app' ? '/executar' : '/aplicativo'}?item=${encodeURIComponent(item.id)}`; }
const el = (id) => document.getElementById(id);

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/construtor' });
  const id = new URLSearchParams(location.search).get('item');
  if (!id) { await escolherItem(); return; }
  await abrirItem(id);
}

/* ---------------------------------------------------------------- escolha do item (sem ?item=) */
async function escolherItem() {
  const sec = el('escolha');
  const estado = el('escolha-estado');
  const tab = el('escolha-tabela');
  sec.hidden = false;
  el('novo-app').hidden = !tem('conteudo.criar');
  tab.colunas = [
    { chave: 'titulo', titulo: t('catalogo.col_titulo') },
    { chave: 'tipo', titulo: t('catalogo.col_tipo'), formatar: (v) => t(`construtor.tipo_${v}`) },
    { chave: 'modificado_em', titulo: t('catalogo.col_modificado'), formatar: (v) => (v ? formatarData(v) : '—') },
    { chave: 'versao_publicada', titulo: t('construtor.col_publicada'), formatar: (v) => (v ? t('construtor.versao_n', { n: v }) : t('construtor.nao_publicado')) },
  ];
  tab.acoes = () => [{ id: 'abrir', rotulo: t('construtor.abrir_no_construtor'), classe: 'primario' }, { id: 'executar', rotulo: t('construtor.executar') }];
  tab.addEventListener('acao', (ev) => {
    if (ev.detail.id === 'abrir') location.href = `/construtor?item=${encodeURIComponent(ev.detail.linha.id)}`;
    else window.open(urlExecucao(ev.detail.linha), '_blank', 'noopener');
  });
  let q = '';
  async function listar() {
    estado.carregando(t('construtor.carregando_lista'));
    tab.hidden = true;
    const r = await obter(`/api/itens?tipo=app&tipo=painel&limite=50&ordenar=modificado_em&direcao=desc${q ? `&q=${encodeURIComponent(q)}` : ''}`);
    if (r.status !== 200) { estado.erro(r); return; }
    const itens = r.json.itens || [];
    if (!itens.length) {
      estado.vazio(q ? t('construtor.lista_vazia_busca', { q }) : t('construtor.lista_vazia'), tem('conteudo.criar') && !q ? [{ id: 'novo', rotulo: t('construtor.novo_app'), classe: 'primario' }] : []);
      return;
    }
    estado.limpar();
    tab.hidden = false;
    tab.linhas = itens;
  }
  estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') listar(); if (ev.detail.id === 'novo') abrirNovo(); });
  el('escolha-busca').addEventListener('buscar', (ev) => { q = ev.detail.q; listar(); });
  el('escolha-busca').querySelector('label').textContent = t('construtor.buscar');
  el('escolha-busca').querySelector('input').setAttribute('aria-label', t('construtor.buscar'));

  const form = el('novo-app-form');
  form.campos = [
    { nome: 'titulo', rotulo: t('construtor.campo_titulo'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200', autocomplete: 'off' } },
    { nome: 'tipo', rotulo: t('construtor.campo_tipo'), tipo: 'select', padrao: 'app', opcoes: [{ valor: 'app', rotulo: t('construtor.tipo_app') }, { valor: 'painel', rotulo: t('construtor.tipo_painel') }] },
  ];
  form.botoes = [{ id: 'criar', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar'), tipo: 'button' }];
  form.addEventListener('botao', (ev) => { if (ev.detail.id === 'cancelar') el('novo-app-caixa').hidden = true; });
  form.addEventListener('enviar', async (ev) => {
    const v = ev.detail.valores;
    form.ocupado = true;
    const d = novoDocumento(v.tipo);
    const r = await enviar('/api/itens', { tipo: v.tipo, titulo: v.titulo, dados: { tipo: v.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo } });
    form.ocupado = false;
    if (r.status !== 201) {
      if (r.json.erro === 'titulo_existente' || r.status === 409) form.erro('titulo', mensagemDe(r));
      else form.mensagem(mensagemDe(r), 'erro');
      return;
    }
    location.href = `/construtor?item=${encodeURIComponent(r.json.id)}`;
  });
  function abrirNovo() { el('novo-app-caixa').hidden = false; form.focarPrimeiro(); }
  el('novo-app').addEventListener('click', abrirNovo);
  await listar();
}

/* ---------------------------------------------------------------- edição de um item */
async function abrirItem(id) {
  const principal = el('principal');
  const aviso = el('aviso');
  const estado = el('estado');
  const h1 = document.querySelector('main > h1');
  estado.addEventListener('acao', (ev) => {
    if (ev.detail.id === 'escolher') location.href = '/construtor';
    if (ev.detail.id === 'tentar') location.reload();
  });
  estado.carregando(t('construtor.carregando_item'));
  const r = await obter(`/api/itens/${encodeURIComponent(id)}`);
  if (r.status === 404) {
    estado.mostrar({ tipo: 'vazio', titulo: t('executor.inexistente_titulo'), texto: t('executor.inexistente_texto'), acoes: [{ id: 'escolher', rotulo: t('construtor.escolher_outro') }] });
    return;
  }
  if (r.status !== 200) { estado.erro(r); return; }
  let item = r.json;
  if (item.tipo !== 'app' && item.tipo !== 'painel') {
    estado.mostrar({ tipo: 'vazio', titulo: t('executor.nao_e_app_titulo'), texto: t('executor.nao_e_app_texto', { tipo: item.tipo }), acoes: [{ id: 'escolher', rotulo: t('construtor.escolher_outro') }] });
    return;
  }
  estado.limpar();
  const dados = item.dados || {};
  let documento;
  if (dados.corpo) documento = { tipo: item.tipo, esquema_versao: dados.esquema_versao || 2, corpo: { nos: [], ligacoes: [], ...dados.corpo } };
  else documento = novoDocumento(item.tipo);
  h1.textContent = item.titulo;
  document.title = `${item.titulo} · ${t('construtor.titulo')} · ${t('app.nome')}`;
  const podeEditar = item.pode_editar !== false;

  const alvo = h('div', { id: 'editor-raiz' });
  const btSalvar = h('button', { type: 'button', id: 'salvar', class: 'primario', disabled: !podeEditar }, t('acao.salvar'));
  const btPublicar = h('button', { type: 'button', id: 'publicar', disabled: !podeEditar }, t('construtor.publicar'));
  const estadoSalvo = h('span', { id: 'estado-salvo', class: 'estado', 'aria-live': 'polite' }, podeEditar ? t('construtor.sem_alteracoes') : t('construtor.so_leitura'));
  const publicado = h('span', { id: 'estado-publicado', class: 'marcador' });
  const linkExecutar = h('a', { id: 'executar', class: 'botao pequeno', href: urlExecucao(item), target: '_blank', rel: 'noopener' }, t('construtor.executar'));
  const linkEscolher = h('a', { id: 'escolher-outro', class: 'botao pequeno texto', href: '/construtor' }, t('construtor.escolher_outro'));
  const barra = el('ferramentas');
  limpar(barra).append(h('div', { class: 'botoes' }, btSalvar, btPublicar, linkExecutar, linkEscolher), h('div', { class: 'direita' }, estadoSalvo, publicado));
  principal.append(alvo);
  let sujo = false;

  function pintarPublicado() {
    const n = item.versao_publicada;
    publicado.className = `marcador ${n ? (n === item.versao_atual ? 'ok' : 'atencao') : 'info'}`;
    publicado.textContent = n
      ? (n === item.versao_atual ? t('construtor.publicado_atual', { n }) : t('construtor.publicado_antigo', { n, atual: item.versao_atual }))
      : t('construtor.nao_publicado');
    btPublicar.disabled = !podeEditar || sujo || (n === item.versao_atual);
  }

  const editor = criarEditor({
    raiz: alvo,
    documento,
    paleta: paletaDoTipo(documento.tipo),
    aoMudar: () => { sujo = true; estadoSalvo.textContent = t('construtor.nao_gravado'); btPublicar.disabled = true; },
  });
  window.plat = { ...(window.plat || {}), construtor: { editor, item: () => item } };

  async function salvar() {
    btSalvar.disabled = true;
    const d = editor.documento();
    const r = await chamar('PATCH', `/api/itens/${item.id}`, {
      dados: { tipo: item.tipo, esquema_versao: d.esquema_versao, corpo: d.corpo },
      versao_atual: item.versao_atual,
    });
    btSalvar.disabled = false;
    if (r.status === 409) {
      estadoSalvo.textContent = t('construtor.nao_gravado');
      aviso.limpar();
      aviso.mostrar(t('construtor.conflito_versao'), 'erro');
      const bt = h('button', { type: 'button', class: 'pequeno', id: 'recarregar' }, t('construtor.recarregar'));
      bt.addEventListener('click', () => location.reload());
      aviso.append(' ', bt);
      return false;
    }
    if (r.status !== 200) { estadoSalvo.textContent = t('construtor.nao_gravado'); aviso.mostrar(mensagemDe(r), 'erro'); return false; }
    item = r.json;
    sujo = false;
    aviso.limpar?.();
    estadoSalvo.textContent = t('construtor.gravado', { n: item.versao_atual });
    pintarPublicado();
    return true;
  }

  async function publicar() {
    if (sujo && !(await salvar())) return;
    if (!(await confirmar(t('construtor.publicar'), t('construtor.publicar_confirma', { n: item.versao_atual, titulo: item.titulo }), { ok: t('construtor.publicar') }))) return;
    btPublicar.disabled = true;
    const r = await enviar(`/api/itens/${item.id}/versoes/${item.versao_atual}/publicar`, {});
    if (r.status !== 200) { btPublicar.disabled = false; aviso.mostrar(`${t('construtor.publicar_falhou')}: ${mensagemDe(r)}`, 'erro'); return; }
    item = r.json;
    pintarPublicado();
    aviso.mostrar(t('construtor.publicado', { n: item.versao_publicada }), 'ok');
    aviso.append(' ', h('a', { href: urlExecucao(item), target: '_blank', rel: 'noopener' }, t('construtor.abrir_publicado')));
  }

  btSalvar.addEventListener('click', salvar);
  btPublicar.addEventListener('click', publicar);
  document.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') { ev.preventDefault(); if (podeEditar) salvar(); }
  });
  pintarPublicado();
}
