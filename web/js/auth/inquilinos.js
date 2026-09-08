/* plat — tela /admin/inquilinos (item UX-18-plataforma-sem-tela): console do superadmin sobre as quatro rotas de
   escrita do grupo `plataforma` — `POST /api/plataforma/inquilinos` (formulário: slug, nome, login e nome do admin;
   a senha temporária aparece UMA vez), `POST .../{id}/suspender` e `POST .../{id}/reativar` (ações da lista, com
   confirmação) e `DELETE .../{id}` (apagar tudo, com confirmação em dois passos). Estados do sistema de design
   (UX-01): <plat-estado> da lista (carregando, vazio, erro com "tentar de novo" + referência, negado — quem não é
   superadmin recebe 404 da API e vê o estado negado nomeado) e das ações; erro da API NOMEADO no campo
   (422 validacao no slug; 409 slug_existente / slug_reservado no slug; 409 plataforma_nao_suspende e 404
   inquilino_inexistente no controle) — nunca "422" cru (refutação do item). */
import { obter, enviar, apagar, mensagemDe } from '../base/api.js';
import { h, limpar, marcador, botaoCopiar } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { confirmar, notificar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
let itens = [];

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/inquilinos' });
  cabecalho(t('inquilinos.titulo'));
  montarTabela();
  el('novo').addEventListener('click', abrirNovo);
  el('recarregar').addEventListener('click', () => carregarLista());
  el('lista-estado').addEventListener('acao', (e) => { if (e.detail.id === 'tentar') carregarLista(); if (e.detail.id === 'novo') abrirNovo(); });
  el('acao-estado').addEventListener('acao', (e) => { if (e.detail.id === 'fechar') el('acao-estado').limpar(); });
  if (!usuario.superadmin) el('novo').hidden = true;
  await carregarLista();
}

function montarTabela() {
  const tab = el('tabela');
  tab.colunas = [
    { chave: 'slug', titulo: t('inquilinos.col_slug'), classe: 'mono' },
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'ativo', titulo: t('campo.estado'), formatar: (v) => marcador(v ? t('inquilinos.ativo') : t('inquilinos.suspenso'), v ? 'ok' : 'falha') },
    { chave: 'usuarios', titulo: t('inquilinos.col_usuarios'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'criado_em', titulo: t('inquilinos.col_criado'), formatar: (v) => (v ? formatarData(v) : '—') },
    { chave: 'ultimo_acesso', titulo: t('inquilinos.col_ultimo_acesso'), formatar: (v) => (v ? formatarData(v) : '—') },
  ];
  tab.acoes = (inq) => {
    if (inq.slug === 'plataforma') return [];
    return [
      inq.ativo ? { id: 'suspender', rotulo: t('inquilinos.suspender'), classe: 'perigo' } : { id: 'reativar', rotulo: t('inquilinos.reativar') },
      { id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' },
    ];
  };
  tab.vazio = t('inquilinos.vazio');
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
}

async function carregarLista() {
  const estado = el('lista-estado');
  const tab = el('tabela');
  tab.hidden = true;
  estado.carregando(t('inquilinos.carregando'));
  const r = await obter('/api/plataforma/inquilinos');
  if (r.status === 401) { location.href = '/entrar?proximo=/admin/inquilinos'; return; }
  if (r.status === 404 || r.status === 403) {
    // a API responde 404 a quem não é superadmin (a rota não se confirma): é o estado negado, nomeado
    estado.negado(t('inquilinos.negado'));
    el('contagem').textContent = '';
    return;
  }
  if (r.status >= 400 || r.status === 0) {
    estado.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]);
    return;
  }
  itens = r.json || [];
  el('contagem').textContent = t('inquilinos.contagem', { n: itens.length, suspensos: itens.filter((i) => !i.ativo).length });
  if (!itens.length) {
    estado.mostrar({ tipo: 'vazio', titulo: t('inquilinos.vazio_titulo'), texto: t('inquilinos.vazio'),
      acoes: [{ id: 'novo', rotulo: t('inquilinos.novo'), classe: 'primario' }] });
    return;
  }
  estado.limpar();
  tab.linhas = itens;
  tab.hidden = false;
}

/* ------------------------------------------------------------------ ações da lista */
function erroNomeado(r) {
  const j = r.json || {};
  return j.erro ? `${j.erro}: ${j.mensagem || ''}` : mensagemDe(r);
}

async function acao(id, inq) {
  const estado = el('acao-estado');
  estado.limpar();
  if (id === 'suspender' || id === 'reativar') {
    const ok = await confirmar(t(`inquilinos.${id}_titulo`), t(`inquilinos.${id}_texto`, { nome: inq.nome, slug: inq.slug }),
      { ok: t(`inquilinos.${id}`), perigo: id === 'suspender' });
    if (!ok) return;
    const r = await enviar(`/api/plataforma/inquilinos/${encodeURIComponent(inq.id)}/${id}`, {});
    if (r.status === 204) { notificar(t(`inquilinos.${id}_ok`, { slug: inq.slug }), { tipo: 'ok' }); await carregarLista(); return; }
    mostrarErroAcao(r, id, inq);
    return;
  }
  if (id === 'apagar') {
    const ok = await confirmar(t('inquilinos.apagar_titulo'), t('inquilinos.apagar_texto', { nome: inq.nome, slug: inq.slug, usuarios: inq.usuarios }),
      { ok: t('acao.apagar'), perigo: true });
    if (!ok) return;
    const ok2 = await confirmar(t('inquilinos.apagar_titulo'), t('inquilinos.apagar_confirma2', { slug: inq.slug }), { ok: t('inquilinos.apagar_definitivo'), perigo: true });
    if (!ok2) return;
    const r = await apagar(`/api/plataforma/inquilinos/${encodeURIComponent(inq.id)}`);
    if (r.status === 204) { notificar(t('inquilinos.apagado', { slug: inq.slug }), { tipo: 'ok' }); await carregarLista(); return; }
    mostrarErroAcao(r, 'apagar', inq);
  }
}

function mostrarErroAcao(r, id, inq) {
  const estado = el('acao-estado');
  if (r.status === 401) { location.href = '/entrar?proximo=/admin/inquilinos'; return; }
  if (r.status === 403) { estado.negado(erroNomeado(r)); return; }
  if (r.status === 404 || r.status === 409) {
    estado.mostrar({ tipo: 'erro', titulo: t(`inquilinos.erro_${id}`, { slug: inq.slug }), texto: erroNomeado(r), ref: r.json?.req_id,
      acoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
    return;
  }
  estado.erro(r, [{ id: 'fechar', rotulo: t('acao.fechar') }]);
}

/* ------------------------------------------------------------------ novo inquilino */
function abrirNovo() {
  const painel = el('painel');
  const form = h('plat-formulario', { id: 'form-inquilino' });
  form.campos = [
    { nome: 'slug', rotulo: t('inquilinos.campo_slug'), tipo: 'texto', obrigatorio: true, ajuda: t('inquilinos.campo_slug_ajuda'),
      atributos: { maxlength: '39', autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'nome', rotulo: t('inquilinos.campo_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200' } },
    { nome: 'admin_login', rotulo: t('inquilinos.campo_admin_login'), tipo: 'texto', obrigatorio: true, ajuda: t('inquilinos.campo_admin_login_ajuda'),
      atributos: { maxlength: '128', autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'admin_nome', rotulo: t('inquilinos.campo_admin_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200' } },
  ];
  form.botoes = [
    { id: 'criar', rotulo: t('acao.criar'), tipo: 'submit' },
    { id: 'cancelar', rotulo: t('acao.cancelar'), tipo: 'button' },
  ];
  form.addEventListener('botao', (ev) => { if (ev.detail.id === 'cancelar') painel.fechar(null); });
  form.addEventListener('enviar', async (ev) => {
    const v = ev.detail.valores;
    const corpo = { slug: String(v.slug || '').trim().toLowerCase(), nome: String(v.nome || '').trim(),
      admin_login: String(v.admin_login || '').trim().toLowerCase(), admin_nome: String(v.admin_nome || '').trim() };
    form.limparErros();
    form.ocupado = true;
    const r = await enviar('/api/plataforma/inquilinos', corpo);
    form.ocupado = false;
    if (r.status === 201) { painel.fechar('ok'); mostrarCriado(r.json); await carregarLista(); return; }
    const j = r.json || {};
    if (r.status === 401) { location.href = '/entrar?proximo=/admin/inquilinos'; return; }
    if (r.status === 403 || r.status === 404) { form.mensagem(t('inquilinos.negado'), 'erro'); return; }
    // 409 slug_existente / slug_reservado (RaiseException do banco) e 422 validacao caem no slug; lista do pydantic
    // por campo; o resto na mensagem do formulário — sempre com o código nomeado
    if (r.status === 409 && /slug/.test(j.erro || '')) { form.erro('slug', `${j.erro}: ${j.mensagem}`); return; }
    if (r.status === 422 && j.detalhe && j.detalhe.campo) { form.erro(j.detalhe.campo, `${j.erro}: ${j.mensagem}`); return; }
    if (r.status === 422 && Array.isArray(j.detalhe)) {
      let algum = false;
      for (const d of j.detalhe) {
        const campo = (d.loc || []).filter((x) => typeof x === 'string' && x !== 'body')[0];
        if (campo && ['slug', 'nome', 'admin_login', 'admin_nome'].includes(campo)) { form.erro(campo, d.msg || 'inválido'); algum = true; }
      }
      if (algum) return;
    }
    form.mensagem(erroNomeado(r), 'erro');
  });
  painel.abrir({ titulo: t('inquilinos.novo'), corpo: form, botoes: [] });
  form.focarPrimeiro();
}

function mostrarCriado(novo) {
  const painel = el('painel');
  const cod = h('code', { id: 'senha-temporaria' }, novo.senha_temporaria);
  const corpo = h('div', { class: 'inquilino-criado', id: 'inquilino-criado' },
    h('p', {}, t('inquilinos.criado', { slug: novo.slug })),
    h('p', {}, h('strong', {}, t('inquilinos.criado_admin')), ' ', h('code', {}, novo.admin.login)),
    h('p', {}, h('strong', {}, t('inquilinos.criado_senha')), ' ', cod, ' ',
      botaoCopiar(novo.senha_temporaria, cod, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })),
    h('p', { class: 'aviso-senha' }, t('inquilinos.criado_aviso')),
    h('p', {}, h('a', { href: `/entrar?inquilino=${encodeURIComponent(novo.slug)}` }, t('inquilinos.criado_entrar', { slug: novo.slug }))));
  painel.abrir({ titulo: t('inquilinos.criado_titulo'), corpo, botoes: [{ id: 'fechar', rotulo: t('acao.fechar') }] });
  notificar(t('inquilinos.criado', { slug: novo.slug }), { tipo: 'ok' });
}
