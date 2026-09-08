/* plat — tela /admin/usuarios (ADR 0002 seção 15.3): lista paginada com filtros e busca, painel lateral de criar/editar,
   senha temporária mostrada uma vez, ações por linha, seleção em massa até 100 (POST /api/usuarios/lote). Botões só com
   o privilégio correspondente; mensagens exatas da API (409 ultimo_admin etc.). */
import { obter, enviar, alterar, apagar, mensagemDe, consulta } from '../base/api.js';
import { h, limpar, botaoCopiar } from '../base/dom.js';
import { carregar, t } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { filtro, seletor, opcoesPerfil, opcoesPapel, estadoUsuario, simNao, dataOuTraco, textoErro, estadoDeLista, eventoRegistrado } from './comum.js';
import { formatarData } from '../base/i18n.js';

const LIMITE = 50;
const filtros = { perfil: '', ativo: '1', q: '', ordenar: 'login', limite: LIMITE, deslocamento: 0 };
let papeis = [];
let total = 0;

let seqLista = 0;

await carregar();
const usuario = await exigirSessao({ privilegio: 'membros.ver' });
if (usuario) await iniciar();
pronto();
function podeGerir() { return tem('membros.gerir'); }
function podePapel() { return tem('membros.papel'); }
function podeApagar() { return tem('membros.apagar'); }
function veTudo() { return tem('membros.ver_tudo'); }

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/usuarios' });
  papeis = await opcoesPapel();
  montarFiltros();
  montarTabela();
  const botoes = [];
  if (podeGerir()) {
    const bt = h('button', { type: 'button', class: 'primario', id: 'novo' }, t('usuarios.novo'));
    bt.addEventListener('click', () => abrirPainel(null));
    botoes.push(bt);
  }
  cabecalho(t('usuarios.titulo'), { contagem: 0, botoes });
  document.getElementById('estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'tentar') carregarLista();
    if (ev.detail.id === 'novo') abrirPainel(null);
    if (ev.detail.id === 'limpar') {
      filtros.perfil = ''; filtros.ativo = ''; filtros.q = ''; filtros.deslocamento = 0;
      document.querySelector('#filtros select[name=perfil]').value = '';
      document.querySelector('#filtros select[name=ativo]').value = '';
      document.querySelector('#filtros plat-busca').valor = '';
      carregarLista();
    }
  });
  await carregarLista();
}

function montarFiltros() {
  const area = document.getElementById('filtros');
  const perfil = seletor('perfil', [{ valor: '', rotulo: t('geral.todos') }, ...opcoesPerfil()], '');
  const ativo = seletor('ativo', [{ valor: '1', rotulo: t('usuario.ativos') }, { valor: '0', rotulo: t('usuario.desabilitados') }, { valor: '', rotulo: t('geral.todos') }], '1');
  const busca = h('plat-busca', { rotulo: t('usuarios.buscar') });
  perfil.addEventListener('change', () => { filtros.perfil = perfil.value; filtros.deslocamento = 0; carregarLista(); });
  ativo.addEventListener('change', () => { filtros.ativo = ativo.value; filtros.deslocamento = 0; carregarLista(); });
  busca.addEventListener('buscar', (e) => { filtros.q = e.detail.q; filtros.deslocamento = 0; carregarLista(); });
  area.append(filtro(t('campo.perfil'), perfil).el, filtro(t('campo.estado'), ativo).el, busca);
  document.getElementById('paginacao').addEventListener('mudar', (e) => { filtros.deslocamento = e.detail.deslocamento; carregarLista(); });
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  const colunas = [
    { chave: 'login', titulo: t('campo.login'), classe: 'mono' },
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'perfil', titulo: t('campo.perfil'), formatar: (v) => t(`perfil.${v}`) },
    { chave: 'papel', titulo: t('campo.papel'), formatar: (v) => (v ? v.nome : '') },
  ];
  if (veTudo()) colunas.push({ chave: 'totp_ativo', titulo: t('usuario.2fa'), formatar: simNao });
  colunas.push({ chave: 'ultimo_login', titulo: t('usuario.ultimo_acesso'), formatar: dataOuTraco });
  if (veTudo()) colunas.push({ chave: 'ultimo_ip', titulo: t('sessao.ip'), classe: 'mono', formatar: (v) => v || '' });
  colunas.push({ chave: 'ativo', titulo: t('campo.estado'), formatar: (_, l) => estadoUsuario(l) });
  tab.colunas = colunas;
  tab.selecionavel = podeGerir() || podePapel();
  tab.limiteSelecao = 100;
  tab.acoes = (u) => {
    const a = [];
    if (podeGerir() || podePapel()) a.push({ id: 'editar', rotulo: t('acao.editar') });
    a.push({ id: 'detalhes', rotulo: t('usuarios.detalhes') });
    if (podeGerir()) {
      if (u.origem === 'local' || !u.origem) a.push({ id: 'senha', rotulo: t('usuarios.redefinir_senha') });
      if (u.totp_ativo) a.push({ id: '2fa', rotulo: t('usuarios.desligar_2fa') });
      if (u.bloqueado_ate && new Date(u.bloqueado_ate) > new Date()) a.push({ id: 'desbloquear', rotulo: t('usuarios.desbloquear') });
      a.push(u.ativo === false ? { id: 'reabilitar', rotulo: t('usuarios.reabilitar') } : { id: 'desabilitar', rotulo: t('usuarios.desabilitar'), classe: 'perigo' });
    }
    if (podeApagar()) a.push({ id: 'apagar', rotulo: t('acao.apagar'), classe: 'perigo' });
    return a;
  };
  tab.addEventListener('acao', (e) => acaoLinha(e.detail.id, e.detail.linha));
  tab.addEventListener('selecao', (e) => montarLote(e.detail.ids));
}

async function carregarLista() {
  const estado = document.getElementById('estado');
  const tab = document.getElementById('tabela');
  const seq = ++seqLista;
  if (!tab.linhas.length) estadoDeLista(estado, tab, null);
  const r = await obter(`/api/usuarios${consulta(filtros)}`);
  if (seq !== seqLista) return; // chegou depois de um pedido mais novo: descarta (a lista nunca volta no tempo)
  const filtrado = Boolean(filtros.perfil || filtros.q || filtros.ativo !== '');
  estadoDeLista(estado, tab, r, {
    vazio: filtrado ? t('usuarios.vazio_filtros') : t('usuarios.vazio'),
    acoes: filtrado ? [{ id: 'limpar', rotulo: t('usuarios.limpar_filtros') }] : (podeGerir() ? [{ id: 'novo', rotulo: t('usuarios.novo'), classe: 'primario' }] : []),
  });
  if (r.status !== 200) { tab.linhas = []; return; }
  total = r.json.total ?? (r.json.itens || []).length;
  tab.linhas = r.json.itens || [];
  document.getElementById('paginacao').atualizar({ total, limite: LIMITE, deslocamento: filtros.deslocamento });
  cabecalho(t('usuarios.titulo'), { contagem: total });
}

function montarLote(ids) {
  const area = document.getElementById('lote');
  limpar(area);
  if (!ids.length) { area.hidden = true; return; }
  area.hidden = false;
  area.append(h('span', {}, t('usuarios.selecionados', { n: ids.length })));
  if (podePapel()) {
    const sel = seletor('perfil_lote', [{ valor: '', rotulo: t('usuarios.mudar_perfil') }, ...opcoesPerfil()], '');
    sel.setAttribute('aria-label', t('usuarios.mudar_perfil'));
    sel.addEventListener('change', () => { if (sel.value) lote({ ids, acao: 'perfil', perfil: sel.value }); });
    area.append(sel);
  }
  if (podeGerir()) {
    const bd = h('button', { type: 'button', class: 'perigo' }, t('usuarios.desabilitar'));
    bd.addEventListener('click', () => lote({ ids, acao: 'desabilitar' }));
    const br = h('button', { type: 'button' }, t('usuarios.reabilitar'));
    br.addEventListener('click', () => lote({ ids, acao: 'reabilitar' }));
    area.append(bd, br);
  }
  area.append(h('span', { class: 'resultado-lote', id: 'resultado-lote', 'aria-live': 'polite' }));
}

async function lote(corpo) {
  const aviso = document.getElementById('aviso');
  const r = await enviar('/api/usuarios/lote', corpo);
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  const rec = r.json.recusados || [];
  const partes = [t('usuarios.lote_alterados', { n: r.json.alterados ?? 0 })];
  if (rec.length) partes.push(t('usuarios.lote_recusados', { n: rec.length, motivos: rec.map((x) => `${x.id}: ${textoErro(x.erro)}`).join('; ') }));
  await carregarLista();
  aviso.mostrar(partes.join(' · '), rec.length ? 'atencao' : 'ok');
  eventoRegistrado();
}

async function acaoLinha(id, u) {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  if (id === 'editar') { abrirPainel(u); return; }
  if (id === 'detalhes') { await abrirDetalhes(u); return; }
  if (id === 'senha') {
    if (!(await confirmar(t('usuarios.redefinir_senha'), t('usuarios.redefinir_confirma', { login: u.login })))) return;
    const r = await enviar(`/api/usuarios/${u.id}/senha`);
    if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
    mostrarSenhaTemporaria(u.login, r.json.senha_temporaria);
    eventoRegistrado();
    return;
  }
  if (id === '2fa') {
    if (!(await confirmar(t('usuarios.desligar_2fa'), t('usuarios.desligar_2fa_confirma', { login: u.login }), { perigo: true }))) return;
    const r = await enviar(`/api/usuarios/${u.id}/2fa/desativar`);
    if (r.status === 204) { await carregarLista(); aviso.ok(t('usuarios.2fa_desligado', { login: u.login })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
    return;
  }
  if (id === 'desbloquear') {
    const r = await enviar(`/api/usuarios/${u.id}/desbloquear`);
    if (r.status === 204) { await carregarLista(); aviso.ok(t('usuarios.desbloqueado', { login: u.login })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
    return;
  }
  if (id === 'desabilitar' || id === 'reabilitar') {
    const r = await alterar(`/api/usuarios/${u.id}`, { ativo: id === 'reabilitar' });
    if (r.status === 200) { await carregarLista(); aviso.ok(t(id === 'reabilitar' ? 'usuarios.reabilitado' : 'usuarios.desabilitado', { login: u.login })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
    return;
  }
  if (id === 'apagar') {
    if (!(await confirmar(t('acao.apagar'), t('usuarios.apagar_confirma', { login: u.login }), { perigo: true, ok: t('acao.apagar') }))) return;
    const r = await apagar(`/api/usuarios/${u.id}`);
    if (r.status === 204) { await carregarLista(); aviso.ok(t('usuarios.apagado', { login: u.login })); eventoRegistrado(); return; }
    let m = mensagemDe(r);
    if (r.json.erro === 'possui_grupos' && Array.isArray(r.json.detalhe)) m += ` — ${t('usuarios.possui_grupos')}: ${r.json.detalhe.map((g) => g.nome).join(', ')}`;
    if (r.json.erro === 'possui_itens' && Array.isArray(r.json.detalhe)) m += ` — ${t('usuarios.possui_itens')}: ${r.json.detalhe.map((i) => i.titulo).join(', ')}`;
    aviso.erro(m);
  }
}

function mostrarSenhaTemporaria(login, senha) {
  const painel = document.getElementById('painel');
  const cod = h('code', { class: 'codigo grande', id: 'senha-temporaria' }, senha);
  painel.abrir({
    titulo: t('usuarios.senha_temporaria'),
    corpo: h('div', {}, h('p', {}, t('usuarios.senha_temporaria_texto', { login })), cod,
      h('div', { class: 'botoes espaco' }, botaoCopiar(senha, cod, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') })),
      h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('usuarios.senha_uma_vez'))),
    botoes: [{ id: 'ok', rotulo: t('acao.fechar'), classe: 'primario' }],
  });
}

/* GET /api/usuarios/{id} (rota que estava sem tela): a ficha completa de um membro, com o que a lista resume —
   origem, criação, último acesso e IP, 2FA, bloqueio, códigos de recuperação restantes, pendência de senha */
async function abrirDetalhes(u) {
  const painel = document.getElementById('painel');
  const estado = h('plat-estado');
  const corpo = h('div', {}, estado);
  painel.abrir({ titulo: t('usuarios.detalhes_de', { login: u.login }), corpo, botoes: [{ id: 'ok', rotulo: t('acao.fechar') }] }).then(() => {});
  estado.carregando();
  const r = await obter(`/api/usuarios/${u.id}`);
  if (r.status !== 200) { estado.erro(r, []); return; }
  const d = r.json;
  estado.limpar();
  const linha = (rot, val) => [h('dt', {}, rot), h('dd', {}, val === null || val === undefined || val === '' ? '—' : val)];
  corpo.append(h('dl', { class: 'espaco ficha-acervo' },
    ...linha(t('campo.login'), h('span', { class: 'mono' }, d.login)),
    ...linha(t('campo.nome'), d.nome),
    ...linha(t('campo.email'), d.email),
    ...linha(t('campo.perfil'), t(`perfil.${d.perfil}`)),
    ...linha(t('campo.papel'), d.papel?.nome || t('papel.perfil_inteiro')),
    ...linha(t('campo.estado'), estadoUsuario(d)),
    ...linha(t('usuarios.origem'), d.origem ? t(`usuarios.origem_${d.origem}`) === `usuarios.origem_${d.origem}` ? d.origem : t(`usuarios.origem_${d.origem}`) : null),
    ...linha(t('campo.criado_em'), d.criado_em ? formatarData(d.criado_em) : null),
    ...linha(t('usuario.ultimo_acesso'), d.ultimo_login ? formatarData(d.ultimo_login) : null),
    ...(veTudo() ? linha(t('sessao.ip'), d.ultimo_ip ? h('span', { class: 'mono' }, d.ultimo_ip) : null) : []),
    ...(veTudo() ? linha(t('usuario.2fa'), simNao(d.totp_ativo)) : []),
    ...(veTudo() ? linha(t('usuarios.codigos_recuperacao'), d.codigos_recuperacao_restantes ?? null) : []),
    ...(veTudo() ? linha(t('usuarios.trocar_senha'), simNao(d.trocar_senha)) : []),
    ...(d.bloqueado_ate && new Date(d.bloqueado_ate) > new Date() ? linha(t('usuario.bloqueado'), formatarData(d.bloqueado_ate)) : []),
  ));
  if (tem('org.log_ver')) corpo.append(h('p', {}, h('a', { class: 'botao pequeno', href: `/admin/log?usuario_id=${encodeURIComponent(d.id)}` }, t('usuarios.ver_acessos'))));
}

function dominiosAjuda() {
  const d = usuario.inquilino?.config_publica?.auth?.dominios_email;
  return Array.isArray(d) && d.length ? t('campo.email_dominios', { lista: d.join(', ') }) : undefined;
}

function abrirPainel(u) {
  const painel = document.getElementById('painel');
  document.getElementById('aviso').limpar();
  const novo = !u;
  const f = h('plat-formulario', { autocompletar: 'off' });
  const campos = [];
  if (novo) campos.push({ nome: 'login', rotulo: t('campo.login'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: 64, autocapitalize: 'none', spellcheck: 'false' }, ajuda: t('campo.login_ajuda') });
  else campos.push({ nome: 'login', rotulo: t('campo.login'), tipo: 'info', padrao: u.login });
  campos.push({ nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: u?.nome || '', atributos: { maxlength: 128 }, desabilitado: !podeGerir() });
  campos.push({ nome: 'email', rotulo: t('campo.email'), tipo: 'email', padrao: u?.email || '', ajuda: dominiosAjuda(), atributos: { maxlength: 254 }, desabilitado: !podeGerir() });
  campos.push({ nome: 'perfil', rotulo: t('campo.perfil'), tipo: 'select', opcoes: opcoesPerfil(), padrao: u?.perfil || 'visualizador', desabilitado: !podePapel(), ajuda: t('campo.perfil_ajuda') });
  campos.push({ nome: 'papel_id', rotulo: t('campo.papel'), tipo: 'select', opcoes: papeis, padrao: u?.papel?.id ? String(u.papel.id) : '', desabilitado: !podePapel() });
  if (!novo) campos.push({ nome: 'ativo', rotulo: t('usuario.ativo'), tipo: 'caixa', padrao: u.ativo !== false, desabilitado: !podeGerir() });
  f.campos = campos;
  f.botoes = [{ id: 'salvar', rotulo: novo ? t('acao.criar') : t('acao.salvar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    const corpo = {};
    if (novo) corpo.login = v.login;
    if (podeGerir()) { corpo.nome = v.nome; corpo.email = v.email || null; if (!novo) corpo.ativo = !!v.ativo; }
    if (podePapel()) { corpo.perfil = v.perfil; corpo.papel_id = v.papel_id ? Number(v.papel_id) : null; }
    if (novo && corpo.email === null) delete corpo.email;
    if (novo && !podePapel()) { corpo.perfil = v.perfil; }
    f.ocupado = true;
    const r = novo ? await enviar('/api/usuarios', corpo) : await alterar(`/api/usuarios/${u.id}`, corpo);
    f.ocupado = false;
    if (r.status === 201) {
      painel.fechar('ok');
      await carregarLista();
      mostrarSenhaTemporaria(r.json.usuario?.login || v.login, r.json.senha_temporaria);
      eventoRegistrado();
      return;
    }
    if (r.status === 200) { painel.fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t('usuarios.salvo', { login: r.json.login })); eventoRegistrado(); return; }
    const campoPorErro = { login_existente: 'login', email_dominio: 'email', papel_incompativel: 'papel_id', ultimo_admin: 'perfil', so_admin_cria_admin: 'perfil', so_admin_altera_admin: 'perfil', possui_grupos: 'perfil', possui_itens: 'perfil' };
    const campo = campoPorErro[r.json.erro];
    let m = mensagemDe(r);
    if (r.json.erro === 'possui_grupos' && Array.isArray(r.json.detalhe)) m += ` (${r.json.detalhe.map((g) => g.nome).join(', ')})`;
    if (r.json.erro === 'possui_itens' && Array.isArray(r.json.detalhe)) m += ` (${r.json.detalhe.map((i) => i.titulo).join(', ')})`;
    if (campo) f.erro(campo, m); else f.mensagem(m, 'erro');
  });
  painel.abrir({ titulo: novo ? t('usuarios.novo') : t('usuarios.editar', { login: u.login }), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

