/* plat — tela /admin/categorias (item UX-12-categorias-sem-controle): as duas rotas de escrita do grupo
   `categorias` ganham controle na tela — `PUT /api/categorias` (a árvore inteira, 3 níveis, ids preservados) pelo
   editor de árvore com "Salvar", e `POST /api/categorias/importar` pelo botão "Importar modelo" (ISO 19115 ou
   INSPIRE, idempotente). Estados do sistema de design (UX-01): <plat-estado> da lista (carregando com esqueleto,
   vazio com a ação de importar, erro com "tentar de novo", negado) e <plat-estado> do salvar/importar, onde o erro
   da API aparece NOMEADO — 409 categoria_em_uso lista os caminhos com itens, 409 nome_existente, 422
   limite_categorias/nivel_maximo com os números, 403 negado — nunca "422" cru (refutação do item).
   Só quem tem `conteudo.categorias` chega aqui (exigirSessao); a API exige o mesmo privilégio. */
import { obter, enviar, alterar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { notificar, confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
const NIVEIS = 3;
let arvore = [];        // [{id, nome, codigo, origem, itens, filhas: [...]}] — cópia editável do último GET
let maximo = 0;
let sujo = false;

await carregar();
const usuario = await exigirSessao({ privilegio: 'conteudo.categorias' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/categorias' });
  cabecalho(t('categorias.titulo'));
  el('categorias-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'tentar') carregarArvore();
    if (e.detail.id === 'importar') el('modelo').focus();
  });
  el('nova-raiz').addEventListener('click', () => { arvore.push(no()); marcarSujo(); desenhar(); });
  el('salvar').addEventListener('click', salvar);
  el('importar').addEventListener('click', importar);
  el('recarregar').addEventListener('click', async () => {
    if (sujo && !(await confirmar(t('categorias.descartar_titulo'), t('categorias.descartar_texto'), { perigo: true }))) return;
    await carregarArvore();
  });
  await carregarArvore();
}

function no(nome = '') { return { id: null, nome, codigo: null, origem: 'local', itens: 0, filhas: [] }; }
function clonar(nos) { return (nos || []).map((n) => ({ ...n, filhas: clonar(n.filhas) })); }
function contar(nos) { return nos.reduce((s, n) => s + 1 + contar(n.filhas), 0); }
function marcarSujo() { sujo = true; el('salvar').disabled = false; el('estado-edicao').textContent = t('categorias.nao_gravado'); }

/* ------------------------------------------------------------------ leitura */
async function carregarArvore() {
  const estado = el('categorias-estado');
  const lista = el('arvore');
  limpar(lista);
  estado.carregando(t('categorias.carregando'));
  const r = await obter('/api/categorias');
  if (r.status === 401) { location.href = '/entrar?proximo=/admin/categorias'; return; }
  if (r.status >= 400 || r.status === 0) {
    // 403 vira negado e 0 vira "sem rede" dentro do componente; o resto é erro com referência e "tentar de novo"
    estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]);
    return;
  }
  arvore = clonar(r.json.arvore);
  maximo = r.json.maximo;
  sujo = false;
  el('salvar').disabled = true;
  el('estado-edicao').textContent = '';
  desenhar();
}

/* ------------------------------------------------------------------ editor da árvore */
function desenhar() {
  const estado = el('categorias-estado');
  const lista = el('arvore');
  limpar(lista);
  el('contagem').textContent = t('categorias.contagem', { n: contar(arvore), max: maximo });
  if (!arvore.length) {
    estado.mostrar({ tipo: 'vazio', titulo: t('categorias.vazio_titulo'), texto: t('categorias.vazio'),
      acoes: [{ id: 'importar', rotulo: t('categorias.importar_modelo'), classe: 'primario' }] });
    return;
  }
  estado.limpar();
  for (const n of arvore) lista.append(linha(n, arvore, 1));
}

function linha(n, irmaos, nivel) {
  const campo = h('input', { type: 'text', class: 'controle categoria-nome', value: n.nome, maxlength: '120',
    'aria-label': t('categorias.nome_nivel', { nivel }), dataset: { categoria: n.id || '' } });
  campo.addEventListener('input', () => { n.nome = campo.value; marcarSujo(); });
  const meta = h('span', { class: 'categoria-meta' },
    n.codigo ? h('code', {}, n.codigo) : null,
    n.itens ? h('span', { class: 'marcador' }, t('categorias.itens', { n: n.itens })) : null);
  const i = irmaos.indexOf(n);
  const bt = (rotulo, aria, fn, extra = {}) => h('button', { type: 'button', class: 'pequeno texto', 'aria-label': aria, title: aria, onclick: fn, ...extra }, rotulo);
  const acoes = h('div', { class: 'categoria-acoes' },
    nivel < NIVEIS ? bt('+', t('categorias.nova_filha'), () => { n.filhas.push(no()); marcarSujo(); desenhar(); }, { dataset: { novaFilha: n.id || n.nome } }) : null,
    bt('↑', t('categorias.subir'), () => { if (i > 0) { irmaos.splice(i, 1); irmaos.splice(i - 1, 0, n); marcarSujo(); desenhar(); } }, { disabled: i === 0 }),
    bt('↓', t('categorias.descer'), () => { if (i < irmaos.length - 1) { irmaos.splice(i, 1); irmaos.splice(i + 1, 0, n); marcarSujo(); desenhar(); } }, { disabled: i === irmaos.length - 1 }),
    bt('✕', n.itens ? t('categorias.remover_em_uso', { n: n.itens }) : t('categorias.remover'),
      () => { irmaos.splice(i, 1); marcarSujo(); desenhar(); }, { disabled: !!n.itens, dataset: { remover: n.id || n.nome } }));
  const li = h('li', { class: `categoria nivel-${nivel}`, dataset: { nivel: String(nivel) } },
    h('div', { class: 'categoria-linha' }, campo, meta, acoes));
  if (n.filhas.length) {
    const sub = h('ul', { class: 'categorias-sub' });
    for (const f of n.filhas) sub.append(linha(f, n.filhas, nivel + 1));
    li.append(sub);
  }
  return li;
}

function corpoDaArvore(nos) {
  return nos.map((n) => ({ id: n.id || undefined, nome: n.nome.trim(), codigo: n.codigo || undefined, filhas: corpoDaArvore(n.filhas) }));
}

/* ------------------------------------------------------------------ escrita: PUT da árvore inteira */
function erroNomeado(r) {
  // a mensagem da API já é nomeada; aqui só entra o detalhe que a mensagem sozinha não mostra
  const j = r.json || {};
  if (j.erro === 'categoria_em_uso' && Array.isArray(j.detalhe)) {
    return `${j.mensagem}: ${j.detalhe.map((d) => `${d.caminho} (${t('categorias.itens', { n: d.itens })})`).join('; ')}`;
  }
  if (j.erro === 'limite_categorias' && j.detalhe) return `${j.mensagem} — ${t('categorias.contagem', { n: j.detalhe.total, max: j.detalhe.maximo })}`;
  if (j.erro === 'nivel_maximo' && j.detalhe) return `${j.mensagem} (${j.detalhe.nome})`;
  return mensagemDe(r);
}

async function salvar() {
  const estado = el('salvar-estado');
  const vazias = [];
  const conferir = (nos) => nos.forEach((n) => { if (!n.nome.trim()) vazias.push(n); conferir(n.filhas); });
  conferir(arvore);
  if (vazias.length) { estado.erro(t('categorias.nome_vazio'), []); return; }
  el('salvar').disabled = true;
  el('salvar').setAttribute('aria-busy', 'true');
  estado.carregando(t('categorias.salvando'));
  const r = await alterar('/api/categorias', { arvore: corpoDaArvore(arvore) });
  el('salvar').removeAttribute('aria-busy');
  if (r.status === 401) { location.href = '/entrar?proximo=/admin/categorias'; return; }
  if (r.status >= 400 || r.status === 0) {
    el('salvar').disabled = false;
    if (r.status === 403) estado.negado(r.json?.mensagem);
    else estado.mostrar({ tipo: 'erro', titulo: t('categorias.erro_salvar'), texto: erroNomeado(r), ref: r.json?.req_id,
      acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
    return;
  }
  estado.limpar();
  arvore = clonar(r.json.arvore);
  maximo = r.json.maximo;
  sujo = false;
  el('estado-edicao').textContent = t('categorias.salvo');
  notificar(t('categorias.salvo'), { tipo: 'ok' });
  desenhar();
}

/* ------------------------------------------------------------------ escrita: POST importar modelo */
async function importar() {
  const estado = el('salvar-estado');
  const modelo = el('modelo').value;
  el('importar').disabled = true;
  el('importar').setAttribute('aria-busy', 'true');
  estado.carregando(t('categorias.importando', { modelo }));
  const r = await enviar('/api/categorias/importar', { modelo });
  el('importar').disabled = false;
  el('importar').removeAttribute('aria-busy');
  if (r.status === 401) { location.href = '/entrar?proximo=/admin/categorias'; return; }
  if (r.status >= 400 || r.status === 0) {
    if (r.status === 403) estado.negado(r.json?.mensagem);
    else estado.mostrar({ tipo: 'erro', titulo: t('categorias.erro_importar'), texto: erroNomeado(r), ref: r.json?.req_id, acoes: [] });
    return;
  }
  estado.limpar();
  notificar(t('categorias.importado', { modelo, criadas: r.json.criadas, existentes: r.json.existentes }), { tipo: 'ok' });
  el('importado').textContent = t('categorias.importado', { modelo, criadas: r.json.criadas, existentes: r.json.existentes });
  await carregarArvore();
}

el('salvar-estado').addEventListener('acao', (e) => { if (e.detail.id === 'tentar') salvar(); });
