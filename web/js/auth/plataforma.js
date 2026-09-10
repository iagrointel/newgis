/* plat · plataforma — console do operador (superadmin, ADR 0002 seção 10; tela por UX-18). Só o inquilino
   `plataforma` tem superadmin; para qualquer outra sessão a API responde 404 (a rota não se confirma) e esta tela
   mostra o estado "sem permissão" com o caminho de volta. Rotas: GET/POST /api/plataforma/inquilinos,
   POST .../{id}/suspender, POST .../{id}/reativar, DELETE .../{id}. A senha temporária do primeiro administrador
   aparece UMA vez, com botão de copiar; 409 slug_existente e 422 validacao voltam ao campo. */
import { apagar, enviar, mensagemDe, obter } from '../base/api.js';
import { confirmar } from '../base/componentes.js';
import { copiar, h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, formatarData, t } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { estadoDeLista, eventoRegistrado } from './comum.js';
import { exigirSessao } from './sessao.js';

function el(id) { return document.getElementById(id); }
const s = { inquilinos: [], q: '' };

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/plataforma' });
  cabecalho(t('plataforma.titulo'));
  if (!usuario.superadmin) {
    el('estado').mostrar({ tipo: 'negado', titulo: t('plataforma.negado_titulo'), texto: t('plataforma.negado'), acoes: [{ id: 'inicio', rotulo: t('nav.inicio'), classe: 'primario' }] });
    el('estado').addEventListener('acao', () => { location.href = '/'; });
    return;
  }
  el('corpo').hidden = false;
  const busca = el('inquilinos-busca');
  busca.querySelector('label').textContent = t('plataforma.filtrar');
  busca.querySelector('input').setAttribute('aria-label', t('plataforma.filtrar'));
  busca.addEventListener('buscar', (ev) => { s.q = ev.detail.q; desenhar(); });
  el('inquilinos-recarregar').addEventListener('click', () => carregarInquilinos());
  el('inquilinos-estado').addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') carregarInquilinos(); });
  const tabela = el('inquilinos-tabela');
  tabela.colunas = [
    { chave: 'slug', titulo: t('plataforma.slug'), formatar: (v) => h('code', { class: 'mono' }, v) },
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'ativo', titulo: t('plataforma.estado'), formatar: (v) => h('span', { class: `marcador ${v ? 'ok' : 'atencao'}` }, t(v ? 'plataforma.ativo' : 'plataforma.suspenso')) },
    { chave: 'usuarios', titulo: t('plataforma.usuarios') },
    { chave: 'criado_em', titulo: t('plataforma.criado_em'), formatar: (v) => (v ? formatarData(v, true) : '—') },
    { chave: 'ultimo_acesso', titulo: t('plataforma.ultimo_acesso'), formatar: (v) => (v ? formatarData(v) : '—') },
  ];
  tabela.vazio = t('plataforma.vazio');
  tabela.acoes = (l) => (l.slug === 'plataforma' ? [] : [
    l.ativo ? { id: 'suspender', rotulo: t('plataforma.suspender'), classe: 'perigo' } : { id: 'reativar', rotulo: t('plataforma.reativar') },
    { id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' },
  ]);
  tabela.addEventListener('acao', (ev) => acao(ev.detail.id, ev.detail.linha));
  montarFormulario();
  await carregarInquilinos();
}

async function carregarInquilinos() {
  const estado = el('inquilinos-estado'); const tabela = el('inquilinos-tabela');
  estadoDeLista(estado, tabela, null);
  const r = await obter('/api/plataforma/inquilinos');
  if (r.status !== 200) {
    // 404 aqui é "não é superadmin" (a rota não se confirma): vira negado, nunca "inexistente"
    if (r.status === 404) { estado.negado(t('plataforma.negado')); tabela.hidden = true; return; }
    estadoDeLista(estado, tabela, r, { acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
    return;
  }
  s.inquilinos = Array.isArray(r.json) ? r.json : [];
  desenhar();
}

function desenhar() {
  const estado = el('inquilinos-estado'); const tabela = el('inquilinos-tabela');
  const q = s.q.toLocaleLowerCase();
  const linhas = s.inquilinos.filter((i) => !q || `${i.slug} ${i.nome}`.toLocaleLowerCase().includes(q));
  el('inquilinos-total').textContent = `(${linhas.length}/${s.inquilinos.length})`;
  estadoDeLista(estado, tabela, { status: 200, json: { itens: linhas } }, { vazio: s.q ? t('plataforma.vazio_filtro') : t('plataforma.vazio') });
  tabela.linhas = linhas;
}

async function acao(id, linha) {
  const aviso = el('aviso');
  aviso.limpar();
  if (id === 'apagar') {
    if (!(await confirmar(t('plataforma.apagar_titulo'), t('plataforma.apagar_texto', { slug: linha.slug, n: linha.usuarios }), { ok: t('acao.apagar'), perigo: true }))) return;
    const r = await apagar(`/api/plataforma/inquilinos/${encodeURIComponent(linha.id)}`);
    if (r.status !== 204) { aviso.erro(erroTexto(r)); return; }
    aviso.ok(t('plataforma.apagado', { slug: linha.slug }));
  } else if (id === 'suspender') {
    if (!(await confirmar(t('plataforma.suspender_titulo'), t('plataforma.suspender_texto', { slug: linha.slug }), { ok: t('plataforma.suspender'), perigo: true }))) return;
    const r = await enviar(`/api/plataforma/inquilinos/${encodeURIComponent(linha.id)}/suspender`);
    if (r.status !== 204) { aviso.erro(erroTexto(r)); return; }
    aviso.ok(t('plataforma.suspenso_ok', { slug: linha.slug }));
  } else if (id === 'reativar') {
    const r = await enviar(`/api/plataforma/inquilinos/${encodeURIComponent(linha.id)}/reativar`);
    if (r.status !== 204) { aviso.erro(erroTexto(r)); return; }
    aviso.ok(t('plataforma.reativado_ok', { slug: linha.slug }));
  } else return;
  await carregarInquilinos();
  eventoRegistrado();
}

function erroTexto(r) {
  const j = r.json || {};
  if (r.status === 409) return t('plataforma.erro_plataforma_propria');
  if (r.status === 404) return t('plataforma.inexistente');
  return `${mensagemDe(r)}${j.req_id ? ` (${t('estado.ref', { ref: j.req_id })})` : ''}`;
}

function montarFormulario() {
  const f = el('form-novo');
  f.campos = [
    { nome: 'slug', rotulo: t('plataforma.slug'), tipo: 'texto', obrigatorio: true, ajuda: t('plataforma.slug_ajuda'), atributos: { maxlength: '39', autocomplete: 'off', spellcheck: 'false', autocapitalize: 'none' } },
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200' } },
    { nome: 'admin_login', rotulo: t('plataforma.admin_login'), tipo: 'texto', obrigatorio: true, ajuda: t('plataforma.admin_login_ajuda'), atributos: { maxlength: '128', autocomplete: 'off', autocapitalize: 'none' } },
    { nome: 'admin_nome', rotulo: t('plataforma.admin_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200' } },
  ];
  f.botoes = [{ id: 'criar', rotulo: t('plataforma.criar'), tipo: 'submit' }];
  f.addEventListener('enviar', (ev) => criar(f, ev.detail.valores));
  el('criado-copiar').addEventListener('click', () => copiar(el('criado-senha').textContent, el('criado-copiar')));
}

async function criar(f, v) {
  f.limparErros();
  el('criado').hidden = true;
  const slug = String(v.slug || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9-]{1,38}$/.test(slug)) { f.erro('slug', t('plataforma.slug_invalido')); f.campo('slug').focus(); return; }
  if (!/^[a-z0-9][a-z0-9._@-]*$/.test(String(v.admin_login || '').trim().toLowerCase())) { f.erro('admin_login', t('plataforma.admin_login_invalido')); f.campo('admin_login').focus(); return; }
  f.ocupado = true;
  const r = await enviar('/api/plataforma/inquilinos', { slug, nome: v.nome.trim(), admin_login: v.admin_login.trim().toLowerCase(), admin_nome: v.admin_nome.trim() });
  f.ocupado = false;
  if (r.status === 409) { f.erro('slug', t('plataforma.slug_existente')); f.campo('slug').focus(); return; }
  if (r.status === 422) {
    const campo = r.json?.detalhe?.campo;
    if (campo && f.campo(campo)) { f.erro(campo, mensagemDe(r)); f.campo(campo).focus(); } else f.mensagem(mensagemDe(r), 'erro');
    return;
  }
  if (r.status !== 201) { f.mensagem(erroTexto(r), 'erro'); return; }
  f.definir({ slug: '', nome: '', admin_login: '', admin_nome: '' });
  const c = r.json;
  el('criado-resumo').textContent = t('plataforma.criado_resumo', { slug: c.slug, login: c.admin?.login || '' });
  el('criado-senha').textContent = c.senha_temporaria || '';
  el('criado-entrar').href = `/entrar?inquilino=${encodeURIComponent(c.slug)}`;
  el('criado').hidden = false;
  limpar(el('aviso'));
  await carregarInquilinos();
  eventoRegistrado();
}
