/* plat — tela /admin/logins (item L0-08-e-mapeamento-provisionamento): provedores de login externo do inquilino
   (GET /api/org/logins) com rótulo/ordem/habilitação dos botões e as regras de provisionamento por provedor
   (PUT /api/org/logins/{tipo}/{id}): criação automática ou só por convite, padrões para membro novo (papel, grupos,
   pasta), mapa valor exato do grupo do IdP -> perfil/papel/grupos, atualizar a cada login, desligar sem grupo
   mapeado. Privilégio org.integracoes. O editor de regras é uma tabela simples: uma linha por valor do IdP. */
import { obter, alterar, mensagemDe } from '../base/api.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { opcoesPapel, opcoesPerfil } from './comum.js';

let provedores = [];
let criacoes = [];
let papeis = [];
let grupos = [];

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.integracoes' });
if (usuario) await iniciar();
pronto();

function aviso() { return document.getElementById('aviso'); }

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/logins' });
  cabecalho(t('logins.titulo'));
  papeis = await opcoesPapel();
  const rg = await obter('/api/grupos?limite=200');
  grupos = rg.status === 200 ? (rg.json.itens || []).map((g) => ({ valor: g.id, rotulo: g.nome })) : [];
  montarTabela();
  await carregarLista();
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  tab.colunas = [
    { chave: 'tipo', titulo: t('logins.col_tipo'), classe: 'mono', formatar: (v) => v.toUpperCase() },
    { chave: 'rotulo', titulo: t('logins.col_rotulo'), formatar: (v, l) => (l.tipo === 'ldap' ? t('logins.ldap_sem_botao') : v) },
    { chave: 'ordem', titulo: t('logins.col_ordem'), formatar: (v) => (v === null || v === undefined ? '—' : String(v)) },
    { chave: 'identificador', titulo: t('logins.col_identificador'), classe: 'mono', formatar: (v) => v || '—' },
    { chave: 'habilitado', titulo: t('campo.estado'), formatar: (v) => marcador(v ? t('logins.habilitado') : t('logins.desabilitado'), v ? 'ok' : 'falha') },
    { chave: 'provisionamento', titulo: t('logins.col_criacao'), formatar: (v) => t(`logins.criacao_${v.criacao}`) },
    { chave: 'provisionamento', titulo: t('logins.col_regras'), formatar: (v) => String(Object.keys(v.mapa || {}).length) },
    { chave: 'atualizado_em', titulo: t('logins.col_atualizado'), formatar: (v) => (v ? formatarData(v) : '—') },
  ];
  tab.chave = 'chave';
  tab.acoes = (p) => {
    const a = [{ id: 'regras', rotulo: t('logins.regras') }];
    a.push(p.habilitado ? { id: 'desabilitar', rotulo: t('logins.desabilitar'), classe: 'perigo' } : { id: 'habilitar', rotulo: t('logins.habilitar') });
    return a;
  };
  tab.vazio = t('logins.vazio');
  tab.addEventListener('acao', (e) => acao(e.detail.id, e.detail.linha));
}

async function carregarLista() {
  const r = await obter('/api/org/logins');
  if (r.status !== 200) { aviso().erro(`${t('erro.carregar')}: ${mensagemDe(r)}`); return; }
  criacoes = r.json.criacoes;
  provedores = r.json.provedores.map((p) => ({ ...p, chave: `${p.tipo}:${p.id}` }));
  document.getElementById('tabela').linhas = provedores;
  cabecalho(t('logins.titulo'), { contagem: provedores.length });
}

async function acao(id, p) {
  aviso().limpar();
  if (id === 'regras') return abrirRegras(p);
  const r = await alterar(`/api/org/logins/${p.tipo}/${p.id}`, { habilitado: id === 'habilitar' });
  if (r.status === 200) { await carregarLista(); aviso().ok(t('logins.salvo', { tipo: p.tipo.toUpperCase() })); } else aviso().erro(mensagemDe(r));
}

/* ---------- editor de regras ---------- */
function seletorGrupos(nome, marcados) {
  const caixa = h('div', { class: 'grupos', 'data-nome': nome });
  if (!grupos.length) caixa.append(h('span', { class: 'fraco' }, t('logins.sem_grupos')));
  for (const g of grupos) {
    const input = h('input', { type: 'checkbox', value: g.valor });
    input.checked = (marcados || []).includes(g.valor);
    caixa.append(h('label', {}, input, ' ', g.rotulo));
  }
  return caixa;
}

function gruposMarcados(caixa) {
  return [...caixa.querySelectorAll('input:checked')].map((i) => i.value);
}

function selecao(nome, opcoes, valor, vazio) {
  const s = h('select', { name: nome });
  if (vazio !== undefined) s.append(h('option', { value: '' }, vazio));
  for (const o of opcoes) s.append(h('option', { value: String(o.valor) }, o.rotulo));
  s.value = valor === null || valor === undefined ? '' : String(valor);
  return s;
}

function linhaRegra(valor, regra) {
  const tr = h('tr', { class: 'regra' });
  const inValor = h('input', { type: 'text', name: 'valor', value: valor || '', maxlength: 200, placeholder: t('logins.valor_exemplo'), spellcheck: 'false' });
  const perfil = selecao('perfil', opcoesPerfil(), regra?.perfil ?? '', t('logins.perfil_sem'));
  const papel = selecao('papel_id', papeis, regra?.papel_id ?? '', t('logins.papel_nenhum'));
  const caixa = seletorGrupos('grupos', regra?.grupos || []);
  const remover = h('button', { type: 'button', class: 'pequeno perigo' }, t('acao.apagar'));
  remover.addEventListener('click', () => tr.remove());
  tr.append(h('td', {}, inValor), h('td', {}, perfil), h('td', {}, papel), h('td', {}, caixa), h('td', {}, remover));
  return tr;
}

function abrirRegras(p) {
  const painel = document.getElementById('painel');
  const pr = p.provisionamento;
  const form = h('form', { class: 'form', id: 'form-regras', novalidate: true });
  const campos = [];
  if (p.tipo !== 'ldap') {
    campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-rotulo' }, t('logins.col_rotulo')),
      h('input', { type: 'text', id: 'r-rotulo', name: 'rotulo', value: p.rotulo || '', maxlength: 120, required: true })));
    campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-ordem' }, t('logins.col_ordem')),
      h('input', { type: 'number', id: 'r-ordem', name: 'ordem', value: p.ordem ?? 0, min: 0, max: 99, style: 'width:6rem' })));
  }
  const criacao = selecao('criacao', criacoes.map((c) => ({ valor: c, rotulo: t(`logins.criacao_${c}`) })), pr.criacao);
  criacao.id = 'r-criacao';
  campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-criacao' }, t('logins.col_criacao')), criacao,
    h('small', { class: 'fraco' }, t('logins.criacao_ajuda'))));
  const perfilPadrao = selecao('perfil_padrao', opcoesPerfil(), p.perfil_padrao ?? '', t('logins.perfil_sem'));
  perfilPadrao.id = 'r-perfil-padrao';
  perfilPadrao.disabled = true;
  campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-perfil-padrao' }, t('logins.perfil_padrao')), perfilPadrao,
    h('small', { class: 'fraco' }, t('logins.perfil_padrao_ajuda'))));
  const papelPadrao = selecao('papel_padrao', papeis, pr.padrao?.papel_id ?? '', t('logins.papel_nenhum'));
  papelPadrao.id = 'r-papel-padrao';
  campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-papel-padrao' }, t('logins.papel_padrao')), papelPadrao));
  const gruposPadrao = seletorGrupos('grupos_padrao', pr.padrao?.grupos || []);
  gruposPadrao.id = 'r-grupos-padrao';
  campos.push(h('div', { class: 'campo' }, h('span', { class: 'rotulo' }, t('logins.grupos_padrao')), gruposPadrao));
  const pasta = h('input', { type: 'text', id: 'r-pasta', name: 'pasta', value: pr.pasta || '', maxlength: 128, placeholder: 'Pessoal de {login}' });
  campos.push(h('div', { class: 'campo' }, h('label', { for: 'r-pasta' }, t('logins.pasta')), pasta, h('small', { class: 'fraco' }, t('logins.pasta_ajuda'))));
  const atualizar = h('input', { type: 'checkbox', id: 'r-atualizar' });
  atualizar.checked = pr.atualizar_a_cada_login !== false;
  const desligar = h('input', { type: 'checkbox', id: 'r-desligar' });
  desligar.checked = pr.desligar_sem_grupo === true;
  campos.push(h('label', { class: 'caixa' }, atualizar, ' ', t('logins.atualizar')));
  campos.push(h('label', { class: 'caixa' }, desligar, ' ', t('logins.desligar')));
  const tabela = h('table', { class: 'regras', id: 'regras' },
    h('thead', {}, h('tr', {}, h('th', {}, t('logins.valor_idp')), h('th', {}, t('campo.perfil')), h('th', {}, t('campo.papel')), h('th', {}, t('logins.grupos_internos')), h('th', {}, ''))),
    h('tbody'));
  const tbody = tabela.querySelector('tbody');
  for (const [valor, regra] of Object.entries(pr.mapa || {})) tbody.append(linhaRegra(valor, regra));
  const btNova = h('button', { type: 'button', class: 'pequeno', id: 'regra-nova' }, t('logins.regra_nova'));
  btNova.addEventListener('click', () => { tbody.append(linhaRegra('', null)); tbody.lastChild.querySelector('input[name=valor]').focus(); });
  const avisoForm = h('plat-aviso', { id: 'regras-aviso' });
  const btSalvar = h('button', { type: 'submit', class: 'primario', id: 'regras-salvar' }, t('acao.salvar'));
  const btCancelar = h('button', { type: 'button' }, t('acao.cancelar'));
  btCancelar.addEventListener('click', () => painel.fechar(null));
  form.append(...campos, h('h3', {}, t('logins.mapa')), h('p', { class: 'fraco' }, t('logins.mapa_ajuda')), tabela, h('div', { class: 'botoes' }, btNova), avisoForm, h('div', { class: 'botoes' }, btSalvar, btCancelar));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const mapa = {};
    for (const tr of tbody.querySelectorAll('tr.regra')) {
      const valor = tr.querySelector('input[name=valor]').value.trim();
      if (!valor) continue;
      const perfil = tr.querySelector('select[name=perfil]').value || null;
      const papelId = tr.querySelector('select[name=papel_id]').value;
      mapa[valor] = { perfil, papel_id: papelId ? Number(papelId) : null, grupos: gruposMarcados(tr.querySelector('.grupos')) };
    }
    const corpo = {
      provisionamento: {
        criacao: criacao.value,
        atualizar_a_cada_login: atualizar.checked,
        desligar_sem_grupo: desligar.checked,
        padrao: { papel_id: papelPadrao.value ? Number(papelPadrao.value) : null, grupos: gruposMarcados(gruposPadrao) },
        pasta: pasta.value.trim() || null,
        mapa,
      },
    };
    if (p.tipo !== 'ldap') {
      corpo.rotulo = form.querySelector('input[name=rotulo]').value.trim();
      corpo.ordem = Number(form.querySelector('input[name=ordem]').value) || 0;
    }
    btSalvar.disabled = true;
    const r = await alterar(`/api/org/logins/${p.tipo}/${p.id}`, corpo);
    btSalvar.disabled = false;
    if (r.status !== 200) { avisoForm.erro(mensagemDe(r)); return; }
    painel.fechar('ok');
    await carregarLista();
    aviso().ok(t('logins.salvo', { tipo: p.tipo.toUpperCase() }));
  });
  painel.abrir({ titulo: t('logins.regras_de', { tipo: p.tipo.toUpperCase(), id: p.identificador || p.id }), corpo: form });
}
