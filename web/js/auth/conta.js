/* plat — tela /conta (ADR 0002 seção 15.2): dados, senha (regra ao vivo da política do inquilino), 2FA (QR do servidor
   por DOMPurify, segredo em texto, códigos de recuperação uma vez), sessões, convites. Âncoras #senha e #2fa abrem a
   seção e mostram o aviso de pendência.
   Item L0-02-g-perfil-usuario (auto-atendimento): idioma/unidades/formato de data/visibilidade viajam dentro do
   MESMO `form-dados` (mesmo PUT /api/eu, campos novos na whitelist do servidor); foto é fora do plat-formulario
   (não há campo "arquivo" no componente declarativo) — mesmo padrão de web/js/auth/organizacao.js::montarLogo,
   só que POST/DELETE /api/eu/foto em vez de /api/org/logo. */
import { obter, enviar, alterar, apagar, mensagemDe } from '../base/api.js';
import { icone } from '../base/icones.js';
import { h, limpar, htmlSeguro, botaoCopiar, marcador } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import { loja } from '../base/estado.js';
import '../base/componentes.js';
import { pedir } from '../base/componentes.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao, caminhoPendencia } from './sessao.js';

const IDIOMAS = [
  { valor: 'pt-BR', rotulo: 'Português (Brasil)' },
  { valor: 'en', rotulo: 'English' },
  { valor: 'es', rotulo: 'Español' },
];
const FORMATOS_DATA = [
  { valor: 'dd/mm/aaaa', rotulo: 'dd/mm/aaaa' },
  { valor: 'mm/dd/aaaa', rotulo: 'mm/dd/aaaa' },
  { valor: 'aaaa-mm-dd', rotulo: 'aaaa-mm-dd' },
];
/* rótulos vêm de t() — precisam do dicionário já carregado, por isso são função (chamada depois de carregar()),
   nunca constante de módulo (o dicionário chega de um fetch assíncrono, ver base/i18n.js::carregar) */
function unidadesOpcoes() {
  return [
    { valor: 'metrico', rotulo: t('conta.unidades_metrico') },
    { valor: 'imperial', rotulo: t('conta.unidades_imperial') },
  ];
}
function visibilidadesOpcoes() {
  return [
    { valor: 'inquilino', rotulo: t('conta.visibilidade_inquilino') },
    { valor: 'privado', rotulo: t('conta.visibilidade_privado') },
  ];
}

await carregar();
let usuario = await exigirSessao({ permitirPendencia: true });
if (usuario) {
  montarLayout({ usuario, ativo: '/conta' });
  await iniciar();
}
pronto();

function politica() {
  const a = usuario.inquilino?.config_publica?.auth || {};
  return {
    min: Number(a.senha_min) >= 8 ? Number(a.senha_min) : 8,
    maiuscula: !!a.senha_maiuscula, minuscula: !!a.senha_minuscula, simbolo: !!a.senha_simbolo,
    exigir2fa: !!a.exigir_2fa, dominios: Array.isArray(a.dominios_email) ? a.dominios_email : [],
  };
}

function regraSenha() {
  const p = politica();
  const partes = [t('senha.regra_base', { n: p.min })];
  if (p.maiuscula) partes.push(t('senha.regra_maiuscula'));
  if (p.minuscula) partes.push(t('senha.regra_minuscula'));
  if (p.simbolo) partes.push(t('senha.regra_simbolo'));
  return partes.join('; ');
}

/* repetição da regra no cliente só como ajuda; quem decide é o servidor (ADR 0002 seção 6.1) */
function senhaAtende(s) {
  const p = politica();
  if (s.length < p.min || !/[A-Za-zÀ-ÿ]/.test(s) || !/\d/.test(s)) return false;
  if (p.maiuscula && !/[A-ZÀ-Þ]/.test(s)) return false;
  if (p.minuscula && !/[a-zß-ÿ]/.test(s)) return false;
  if (p.simbolo && !/[^A-Za-z0-9À-ÿ\s]/.test(s)) return false;
  return true;
}

function mostrarPendencia() {
  const alvo = document.getElementById('pendencia');
  limpar(alvo);
  const pend = usuario.pendencias || [];
  if (!pend.length) return;
  const texto = pend.includes('trocar_senha') ? t('conta.pendencia_senha') : t('conta.pendencia_2fa');
  alvo.append(h('div', { class: 'aviso-pendencia', role: 'alert' }, h('strong', {}, t('conta.pendencia_titulo')), ' ', texto));
  const destino = caminhoPendencia(pend);
  if (destino && location.hash !== destino.slice(destino.indexOf('#'))) location.hash = destino.slice(destino.indexOf('#'));
}

async function recarregarUsuario() {
  const r = await obter('/api/eu');
  if (r.status === 200) { usuario = r.json; loja.definir({ usuario }); }
  return r;
}

function comPendencia() { return (usuario.pendencias || []).length > 0; }

/* com pendência a API recusa tudo fora de /api/eu, /api/eu/senha e /api/eu/2fa/* (ADR 0002 seção 5.4): as seções que
   dependem de outras rotas ficam com o texto da pendência e carregam assim que ela é resolvida. */
async function carregarResto() {
  if (comPendencia()) {
    for (const id of ['aviso-sessoes', 'aviso-convites']) document.getElementById(id).mostrar(t('conta.apos_pendencia'), 'atencao');
    document.getElementById('tabela-sessoes').linhas = [];
    document.getElementById('tabela-convites').linhas = [];
    document.getElementById('encerrar-outras').disabled = true;
    listarPrivilegios([]);
    return;
  }
  document.getElementById('encerrar-outras').disabled = false;
  await Promise.all([carregarSessoes(), carregarConvites(), carregarPrivilegios()]);
}

async function iniciar() {
  mostrarPendencia();
  montarFoto();
  montarDados();
  montarSenha();
  montar2fa();
  await carregarResto();
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

function montarDados() {
  const f = document.getElementById('form-dados');
  const p = politica();
  f.campos = [
    { nome: 'login', rotulo: t('campo.login'), tipo: 'info', padrao: usuario.login },
    { nome: 'perfil', rotulo: t('campo.perfil'), tipo: 'info', padrao: t(`perfil.${usuario.perfil}`) + (usuario.papel ? ` · ${t('campo.papel')}: ${usuario.papel.nome}` : '') },
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: usuario.nome || '', atributos: { maxlength: 128, autocomplete: 'name' } },
    { nome: 'email', rotulo: t('campo.email'), tipo: 'email', padrao: usuario.email || '', atributos: { maxlength: 254, autocomplete: 'email' },
      ajuda: p.dominios.length ? t('campo.email_dominios', { lista: p.dominios.join(', ') }) : undefined },
    { nome: 'idioma_preferido', rotulo: t('conta.idioma'), tipo: 'select', padrao: usuario.idioma_preferido, opcoes: IDIOMAS,
      ajuda: t('conta.idioma_ajuda') },
    { nome: 'unidades', rotulo: t('conta.unidades'), tipo: 'select', padrao: usuario.unidades, opcoes: unidadesOpcoes() },
    { nome: 'formato_data', rotulo: t('conta.formato_data'), tipo: 'select', padrao: usuario.formato_data, opcoes: FORMATOS_DATA },
    { nome: 'visibilidade_perfil', rotulo: t('conta.visibilidade'), tipo: 'select', padrao: usuario.visibilidade_perfil, opcoes: visibilidadesOpcoes() },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const v = e.detail.valores;
    const r = await alterar('/api/eu', {
      nome: v.nome, email: v.email, idioma_preferido: v.idioma_preferido, unidades: v.unidades,
      formato_data: v.formato_data, visibilidade_perfil: v.visibilidade_perfil,
    });
    f.ocupado = false;
    if (r.status === 200) { usuario = r.json; loja.definir({ usuario }); montarLayout({ usuario, ativo: '/conta' }); f.mensagem(t('conta.dados_salvos'), 'ok'); return; }
    if (r.json.erro === 'email_dominio') f.erro('email', mensagemDe(r)); else f.mensagem(mensagemDe(r), 'erro');
  });
}

/* ---------------------------------------------------------------- foto de perfil (POST/DELETE /api/eu/foto,
   fora do plat-formulario: mesmo padrão de web/js/auth/organizacao.js::montarLogo) */
function montarFoto() {
  const img = document.getElementById('foto-preview');
  const vazio = document.getElementById('foto-vazio');
  if (usuario.foto_url) {
    img.src = usuario.foto_url;
    img.hidden = false;
    vazio.hidden = true;
  } else {
    img.hidden = true;
    vazio.hidden = false;
  }
}

function lerComoBase64(arquivo) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(',', 2)[1] || '');
    leitor.onerror = () => reject(leitor.error);
    leitor.readAsDataURL(arquivo);
  });
}

document.getElementById('foto-arquivo').addEventListener('change', async (e) => {
  const arquivo = e.target.files?.[0];
  e.target.value = '';
  if (!arquivo) return;
  const f = document.getElementById('form-dados');
  const conteudo = await lerComoBase64(arquivo);
  const r = await enviar('/api/eu/foto', { conteudo });
  if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return; }
  usuario = { ...usuario, foto_url: r.json.foto_url };
  loja.definir({ usuario });
  montarLayout({ usuario, ativo: '/conta' });
  montarFoto();
  f.mensagem(t('conta.foto_enviada'), 'ok');
});

document.getElementById('foto-remover').addEventListener('click', async () => {
  const f = document.getElementById('form-dados');
  const r = await apagar('/api/eu/foto');
  if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return; }
  usuario = { ...usuario, foto_url: null };
  loja.definir({ usuario });
  montarLayout({ usuario, ativo: '/conta' });
  montarFoto();
  f.mensagem(t('conta.foto_removida'), 'ok');
});

function montarSenha() {
  const f = document.getElementById('form-senha');
  const externo = usuario.origem && usuario.origem !== 'local';
  if (externo) { f.campos = [{ nome: 'info', rotulo: t('campo.senha'), tipo: 'info', padrao: t('conta.login_externo') }]; return; }
  f.campos = [
    { nome: 'atual', rotulo: t('senha.atual'), tipo: 'senha', obrigatorio: true, atributos: { autocomplete: 'current-password', maxlength: 128 } },
    { nome: 'nova', rotulo: t('senha.nova'), tipo: 'senha', obrigatorio: true, ajuda: regraSenha(), atributos: { autocomplete: 'new-password', maxlength: 128 } },
  ];
  f.botoes = [{ id: 'trocar', rotulo: t('senha.trocar'), tipo: 'submit' }];
  const nova = f.campo('nova');
  const ajuda = nova.parentElement.parentElement.querySelector('.ajuda');
  nova.addEventListener('input', () => {
    const ok = senhaAtende(nova.value);
    ajuda.textContent = nova.value ? `${regraSenha()} — ${ok ? t('senha.atende') : t('senha.nao_atende')}` : regraSenha();
  });
  f.addEventListener('enviar', async (e) => {
    const { atual, nova: n } = e.detail.valores;
    if (!senhaAtende(n)) { f.erro('nova', t('senha.nao_atende_regra', { regra: regraSenha() })); return; }
    f.ocupado = true;
    const r = await alterar('/api/eu/senha', { atual, nova: n });
    f.ocupado = false;
    if (r.status === 204) {
      f.definir({ atual: '', nova: '' });
      await recarregarUsuario();
      mostrarPendencia();
      f.mensagem(t('senha.trocada'), 'ok');
      await carregarResto();
      return;
    }
    if (r.status === 401) f.erro('atual', mensagemDe(r));
    else if (r.status === 422) f.erro('nova', mensagemDe(r));
    else f.mensagem(mensagemDe(r), 'erro');
  });
}

function montar2fa() {
  const estado = document.getElementById('estado-2fa');
  const texto = document.getElementById('texto-2fa');
  const area = document.getElementById('area-2fa');
  const botoes = document.getElementById('botoes-2fa');
  limpar(area); limpar(botoes);
  const p = politica();
  const externo = usuario.origem && usuario.origem !== 'local';
  const ativo = !!usuario.totp_ativo;
  estado.textContent = ativo ? t('2fa.ligado') : t('2fa.desligado');
  estado.className = `estado ${ativo ? 'ok' : ''}`;
  if (externo) { texto.textContent = t('conta.login_externo'); return; }
  if (!ativo) {
    texto.textContent = p.exigir2fa ? t('2fa.exigido_texto') : t('2fa.desligado_texto');
    const bt = h('button', { type: 'button', class: 'primario', id: 'ligar-2fa' }, t('2fa.ligar'));
    bt.addEventListener('click', iniciar2fa);
    botoes.append(bt);
    return;
  }
  const restantes = usuario.codigos_recuperacao_restantes;
  texto.textContent = t('2fa.ligado_texto') + (typeof restantes === 'number' ? ` ${t('2fa.restantes', { n: restantes })}` : '');
  if (restantes === 0) area.append(h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('2fa.sem_codigos')));
  const btCodigos = h('button', { type: 'button', id: 'codigos-2fa' }, t('2fa.gerar_codigos'));
  btCodigos.addEventListener('click', gerarCodigos);
  botoes.append(btCodigos);
  if (p.exigir2fa) botoes.append(h('span', { class: 'fraco' }, t('2fa.obrigatorio_inquilino')));
  else {
    const btDesligar = h('button', { type: 'button', class: 'perigo', id: 'desligar-2fa' }, t('2fa.desligar'));
    btDesligar.addEventListener('click', desligar2fa);
    botoes.append(btDesligar);
  }
}

function listaCodigos(codigos) {
  const ul = h('ul', { class: 'lista-codigos', id: 'codigos-recuperacao' }, ...codigos.map((c) => h('li', {}, c)));
  return h('div', {},
    h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('2fa.codigos_uma_vez')),
    ul,
    botaoCopiar(() => codigos.join('\n'), ul, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') }));
}

async function iniciar2fa() {
  const area = document.getElementById('area-2fa');
  const botoes = document.getElementById('botoes-2fa');
  limpar(area);
  const r = await enviar('/api/eu/2fa/iniciar');
  if (r.status !== 200) { area.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, mensagemDe(r))); return; }
  limpar(botoes);
  const { segredo, uri, qr_svg: qrSvg } = r.json;
  const qr = h('div', { class: 'svg-qr', role: 'img', 'aria-label': t('2fa.qr_rotulo') });
  if (qrSvg) qr.append(htmlSeguro(qrSvg, { svg: true }));
  const seg = h('code', { class: 'codigo grande', id: 'segredo-2fa' }, segredo);
  const f = h('plat-formulario');
  f.campos = [{ nome: 'codigo', rotulo: t('login.codigo'), tipo: 'texto', obrigatorio: true, atributos: { inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 6 } }];
  f.botoes = [{ id: 'confirmar', rotulo: t('2fa.confirmar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') montar2fa(); });
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const c = await enviar('/api/eu/2fa/confirmar', { codigo: e.detail.valores.codigo });
    f.ocupado = false;
    if (c.status !== 200) { f.erro('codigo', mensagemDe(c)); return; }
    await recarregarUsuario();
    montar2fa();
    document.getElementById('area-2fa').append(listaCodigos(c.json.codigos_recuperacao || []));
    mostrarPendencia();
    await carregarResto();
  });
  area.append(h('div', { class: 'par-qr' }, qr,
    h('div', {}, h('p', {}, t('2fa.instrucao')), h('span', { class: 'campo-rotulo' }, t('2fa.segredo')), seg,
      botaoCopiar(segredo, seg, { copiar: t('acao.copiar'), copiado: t('acao.copiado'), selecionado: t('acao.selecionado') }),
      uri ? h('details', {}, h('summary', {}, t('2fa.uri')), h('code', { class: 'codigo' }, uri)) : null, f)));
  f.focarPrimeiro();
}

function formSenhaCodigo(comCodigo) {
  const f = h('plat-formulario');
  const campos = [{ nome: 'senha', rotulo: t('campo.senha'), tipo: 'senha', obrigatorio: true, atributos: { autocomplete: 'current-password' } }];
  if (comCodigo) campos.push({ nome: 'codigo', rotulo: t('login.codigo'), tipo: 'texto', obrigatorio: true, atributos: { inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 6 } });
  f.campos = campos;
  f.botoes = [{ id: 'ok', rotulo: t('acao.confirmar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  return f;
}

async function desligar2fa() {
  const f = formSenhaCodigo(true);
  const v = await pedir(t('2fa.desligar'), f);
  if (!v) return;
  const area = document.getElementById('area-2fa');
  const r = await enviar('/api/eu/2fa/desativar', { senha: v.senha, codigo: v.codigo });
  limpar(area);
  if (r.status !== 204) { area.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, mensagemDe(r))); return; }
  await recarregarUsuario();
  montar2fa();
  document.getElementById('area-2fa').append(h('plat-aviso', { 'data-tipo': 'ok' }, t('2fa.desligado_ok')));
}

async function gerarCodigos() {
  const f = formSenhaCodigo(false);
  const v = await pedir(t('2fa.gerar_codigos'), f);
  if (!v) return;
  const area = document.getElementById('area-2fa');
  limpar(area);
  const r = await enviar('/api/eu/2fa/codigos', { senha: v.senha });
  if (r.status !== 200) { area.append(h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, mensagemDe(r))); return; }
  await recarregarUsuario();
  montar2fa();
  document.getElementById('area-2fa').append(listaCodigos(r.json.codigos_recuperacao || []));
}

async function carregarSessoes() {
  const tab = document.getElementById('tabela-sessoes');
  const aviso = document.getElementById('aviso-sessoes');
  tab.colunas = [
    { chave: 'criado_em', titulo: t('sessao.criada'), formatar: (v) => formatarData(v) },
    { chave: 'ultimo_uso', titulo: t('sessao.ultimo_uso'), formatar: (v) => formatarData(v) },
    { chave: 'expira_em', titulo: t('sessao.expira'), formatar: (v) => formatarData(v) },
    { chave: 'ip', titulo: t('sessao.ip'), classe: 'mono' },
    { chave: 'agente', titulo: t('sessao.navegador'), formatar: (v) => (v || '').slice(0, 60) },
    { chave: 'atual', titulo: '', formatar: (v) => (v ? marcador(t('sessao.atual'), 'ok') : '') },
  ];
  tab.acoes = (l) => (l.atual ? [] : [{ id: 'encerrar', rotulo: t('sessao.encerrar'), classe: 'perigo' }]);
  tab.addEventListener('acao', async (e) => {
    const r = await apagar(`/api/eu/sessoes/${e.detail.linha.id}`);
    if (r.status === 204) { await carregarSessoes(); aviso.ok(t('sessao.encerrada')); } else aviso.erro(mensagemDe(r));
  });
  const r = await obter('/api/eu/sessoes');
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); tab.linhas = []; return; }
  tab.linhas = Array.isArray(r.json) ? r.json : (r.json.itens || []);
}
document.getElementById('encerrar-outras').addEventListener('click', async () => {
  const aviso = document.getElementById('aviso-sessoes');
  const r = await apagar('/api/eu/sessoes?outras=1');
  if (r.status === 204) { await carregarSessoes(); aviso.ok(t('sessao.outras_encerradas')); } else aviso.erro(mensagemDe(r));
});

async function carregarConvites() {
  const tab = document.getElementById('tabela-convites');
  const aviso = document.getElementById('aviso-convites');
  tab.chave = 'chave';
  tab.colunas = [
    { chave: 'grupo', titulo: t('grupo.grupo'), formatar: (g) => g?.nome || '' },
    { chave: 'papel', titulo: t('grupo.papel'), formatar: (v) => (v ? t(`grupo.papel_${v}`) : '') },
    { chave: 'convidado_por', titulo: t('grupo.convidado_por'), formatar: (v) => (v && typeof v === 'object' ? (v.nome || v.login) : (v ?? '')) },
    { chave: 'criado_em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
  ];
  tab.acoes = [{ id: 'aceitar', rotulo: t('grupo.aceitar'), classe: 'primario' }, { id: 'recusar', rotulo: t('grupo.recusar') }];
  tab.addEventListener('acao', async (e) => {
    const gid = e.detail.linha.grupo?.id;
    const r = await enviar(`/api/grupos/${gid}/${e.detail.id}`);
    if (r.status === 200 || r.status === 204) { await carregarConvites(); aviso.ok(e.detail.id === 'aceitar' ? t('grupo.aceito') : t('grupo.recusado')); } else aviso.erro(mensagemDe(r));
  });
  const r = await obter('/api/eu/convites');
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); tab.linhas = []; return; }
  const itens = Array.isArray(r.json) ? r.json : (r.json.itens || []);
  tab.linhas = itens.map((c, i) => ({ ...c, chave: c.grupo?.id || i }));
  tab.vazio = t('grupo.sem_convites');
}

function listarPrivilegios(todos) {
  const ul = document.getElementById('lista-privilegios');
  limpar(ul);
  const meus = new Set(usuario.privilegios || []);
  const lista = todos.length ? todos : [...meus].map((nome) => ({ nome }));
  for (const p of lista) {
    const temEste = meus.has(p.nome);
    ul.append(h('li', { class: temEste ? '' : 'sem', title: p.descricao }, icone(temEste ? 'ok' : 'menos', { tamanho: 12 }), p.nome));
  }
  if (!lista.length) ul.append(h('li', {}, t('conta.sem_privilegios')));
}

async function carregarPrivilegios() {
  const r = await obter('/api/privilegios');
  listarPrivilegios(r.status === 200 && Array.isArray(r.json) ? r.json : []);
}
