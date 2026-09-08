/* plat — tela /admin/organizacao (item L0-07-a-configuracoes-org): GET/PUT /api/org sobre `plat.tenant` — nome,
   identidade visual (cor + logotipo, reaproveitando POST/DELETE /api/org/logo do L0-11), mapa padrão, idioma
   padrão, cotas de armazenamento/usuários e a MESMA política de senha/2FA que /conta já lê (tenant.config.auth,
   L0-02): esta tela só a expõe para edição, nunca recria um esquema novo. Cinco `plat-formulario` (uma por
   assunto) escrevem no MESMO objeto: cada envio parte do último `GET /api/org` conhecido, sobrepõe só os campos
   da própria seção e manda o corpo INTEIRO (a API substitui `tenant.config` por merge, mas o corpo de entrada é
   sempre completo — mesmo contrato do PUT /api/org/ldap). Só admin do inquilino chega aqui (privilégio
   `org.configurar`); quem não tem cai em "sem permissão" pelo próprio `exigirSessao`. */
import { obter, enviar, alterar, apagar, mensagemDe } from '../base/api.js';
import { tem } from '../base/estado.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { eventoRegistrado, PERFIS } from './comum.js';

const IDIOMAS = [
  { valor: 'pt-BR', rotulo: 'Português (Brasil)' },
  { valor: 'en', rotulo: 'English' },
  { valor: 'es', rotulo: 'Español' },
];
let atual = null;
// declarado ANTES do await de nível de módulo abaixo: carregarSmtp() o atribui durante iniciar(), e um `let` que
// só aparecesse depois estaria na zona morta temporal (achado UX-01: a página nunca marcava body[data-pronto])
let smtpAtual = null;
let ldapAtual = null;

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.configurar' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/organizacao' });
  cabecalho(t('org.titulo'));
  await carregarOrg();
}

async function carregarOrg() {
  const estado = document.getElementById('estado');
  estado.carregando(t('org.carregando'));
  const r = await obter('/api/org');
  if (r.status !== 200) {
    estado.erro(r);
    estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') carregarOrg(); }, { once: true });
    return;
  }
  estado.limpar();
  atual = r.json;
  montarLogo();
  montarIdentidade();
  montarMapa();
  montarArmazenamento();
  montarUsuarios();
  montarSeguranca();
  await carregarSmtp();
  if (tem('org.integracoes')) await carregarLdap();
  if (location.hash) document.querySelector(location.hash)?.scrollIntoView({ block: 'start' });
}

/* corpo completo de PUT /api/org a partir do último GET conhecido; `sobre` sobrepõe só o que a seção que
   enviou o formulário edita — as demais seções viajam intactas */
function corpoBase(sobre) {
  return {
    nome: atual.nome,
    cor: atual.cor,
    idioma_padrao: atual.idioma_padrao,
    centro: atual.mapa.centro,
    zoom: atual.mapa.zoom,
    basemap: atual.mapa.basemap,
    srid_padrao: atual.mapa.srid_padrao,
    cota_bytes: atual.armazenamento.cota_bytes,
    cota_usuarios: atual.usuarios.cota,
    auth: { ...atual.auth },
    ...sobre,
  };
}

async function salvar(f, sobre) {
  f.ocupado = true;
  const r = await alterar('/api/org', corpoBase(sobre));
  f.ocupado = false;
  if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return false; }
  atual = r.json;
  document.getElementById('aviso').ok(t('org.salvo'));
  montarLogo();
  montarArmazenamento();
  montarUsuarios();
  eventoRegistrado();
  return true;
}

function montarIdentidade() {
  const f = document.getElementById('form-identidade');
  f.campos = [
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: atual.nome, atributos: { maxlength: 55 } },
    { nome: 'cor', rotulo: t('org.cor'), tipo: 'texto', obrigatorio: true, padrao: atual.cor, ajuda: t('org.cor_ajuda'), atributos: { maxlength: 7, pattern: '^#[0-9a-fA-F]{6}$' } },
    { nome: 'idioma_padrao', rotulo: t('org.idioma'), tipo: 'select', padrao: atual.idioma_padrao, opcoes: IDIOMAS },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (!/^#[0-9a-fA-F]{6}$/.test(v.cor)) { f.erro('cor', t('org.cor_ajuda')); return; }
    const ok = await salvar(f, { nome: v.nome, cor: v.cor, idioma_padrao: v.idioma_padrao });
    if (ok) montarLayout({ usuario: { ...usuario, inquilino: { ...usuario.inquilino, nome: v.nome } }, ativo: '/admin/organizacao' });
  });
}

function montarMapa() {
  const f = document.getElementById('form-mapa');
  const c = atual.mapa.centro || [null, null];
  f.campos = [
    { nome: 'centro_lon', rotulo: t('org.centro_lon'), tipo: 'numero', padrao: c[0], atributos: { step: 'any', min: -180, max: 180 } },
    { nome: 'centro_lat', rotulo: t('org.centro_lat'), tipo: 'numero', padrao: c[1], atributos: { step: 'any', min: -90, max: 90 } },
    { nome: 'zoom', rotulo: t('org.zoom'), tipo: 'numero', padrao: atual.mapa.zoom, atributos: { min: 0, max: 24, step: 1 } },
    { nome: 'basemap', rotulo: t('org.basemap'), tipo: 'texto', padrao: atual.mapa.basemap || '', atributos: { maxlength: 100 } },
    { nome: 'srid_padrao', rotulo: t('org.srid'), tipo: 'numero', padrao: atual.mapa.srid_padrao, atributos: { min: 1024, max: 999999, step: 1 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const v = e.detail.valores;
    const centro = v.centro_lon === null || v.centro_lat === null ? null : [v.centro_lon, v.centro_lat];
    salvar(f, { centro, zoom: v.zoom, basemap: v.basemap || null, srid_padrao: v.srid_padrao });
  });
}

function montarArmazenamento() {
  const f = document.getElementById('form-armazenamento');
  const mb = Math.round(atual.armazenamento.cota_bytes / (1024 * 1024));
  const usoMb = (atual.armazenamento.bytes_usados / (1024 * 1024)).toFixed(1);
  f.campos = [
    { nome: 'uso', rotulo: t('org.uso_armazenamento', { mb: usoMb, cota: mb }), tipo: 'info', padrao: '' },
    { nome: 'cota_mb', rotulo: t('org.cota_armazenamento_mb'), tipo: 'numero', obrigatorio: true, padrao: mb, atributos: { min: 100, step: 1 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const bytes = Math.round(e.detail.valores.cota_mb * 1024 * 1024);
    salvar(f, { cota_bytes: bytes });
  });
}

function montarUsuarios() {
  const f = document.getElementById('form-usuarios');
  f.campos = [
    { nome: 'ativos', rotulo: t('org.usuarios_ativos', { n: atual.usuarios.ativos, cota: atual.usuarios.cota }), tipo: 'info', padrao: '' },
    { nome: 'cota_usuarios', rotulo: t('org.cota_usuarios'), tipo: 'numero', obrigatorio: true, padrao: atual.usuarios.cota, atributos: { min: 1, step: 1 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => salvar(f, { cota_usuarios: e.detail.valores.cota_usuarios }));
}

function montarSeguranca() {
  const f = document.getElementById('form-seguranca');
  const a = atual.auth;
  f.campos = [
    { nome: 'senha_min', rotulo: t('org.senha_min'), tipo: 'numero', padrao: a.senha_min, atributos: { min: 8, max: 64, step: 1 } },
    { nome: 'senha_maiuscula', rotulo: t('org.senha_maiuscula'), tipo: 'caixa', padrao: a.senha_maiuscula },
    { nome: 'senha_minuscula', rotulo: t('org.senha_minuscula'), tipo: 'caixa', padrao: a.senha_minuscula },
    { nome: 'senha_simbolo', rotulo: t('org.senha_simbolo'), tipo: 'caixa', padrao: a.senha_simbolo },
    { nome: 'senha_historico', rotulo: t('org.senha_historico'), tipo: 'numero', padrao: a.senha_historico, atributos: { min: 0, max: 24, step: 1 } },
    { nome: 'senha_expira_dias', rotulo: t('org.senha_expira_dias'), tipo: 'numero', padrao: a.senha_expira_dias, atributos: { min: 0, max: 365, step: 1 } },
    { nome: 'bloqueio_tentativas', rotulo: t('org.bloqueio_tentativas'), tipo: 'numero', padrao: a.bloqueio_tentativas, atributos: { min: 3, max: 10, step: 1 } },
    { nome: 'bloqueio_minutos', rotulo: t('org.bloqueio_minutos'), tipo: 'numero', padrao: a.bloqueio_minutos, atributos: { min: 5, max: 60, step: 1 } },
    { nome: 'sessao_ociosa_horas', rotulo: t('org.sessao_ociosa_horas'), tipo: 'numero', padrao: a.sessao_ociosa_horas, atributos: { min: 1, max: 24, step: 1 } },
    { nome: 'sessao_max_dias', rotulo: t('org.sessao_max_dias'), tipo: 'numero', padrao: a.sessao_max_dias, atributos: { min: 1, max: 30, step: 1 } },
    { nome: 'exigir_2fa', rotulo: t('org.exigir_2fa'), tipo: 'caixa', padrao: a.exigir_2fa, desabilitado: usuario.inquilino?.slug === 'plataforma' },
    { nome: 'token_max_dias', rotulo: t('org.token_max_dias'), tipo: 'numero', padrao: a.token_max_dias, atributos: { min: 1, max: 365, step: 1 } },
    { nome: 'token_padrao_dias', rotulo: t('org.token_padrao_dias'), tipo: 'numero', padrao: a.token_padrao_dias, atributos: { min: 1, max: 365, step: 1 } },
    { nome: 'dominios_email', rotulo: t('org.dominios_email'), tipo: 'lista', padrao: a.dominios_email, linhas: 3 },
    { nome: 'compartilhar_publico', rotulo: t('org.compartilhar_publico'), tipo: 'caixa', padrao: a.compartilhar_publico },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const v = e.detail.valores;
    salvar(f, { auth: { ...atual.auth, ...v } });
  });
}

/* ---------------------------------------------------------------- logotipo (POST/DELETE /api/org/logo,
   fora do plat-formulario: não há campo "arquivo" no componente declarativo, e a leitura em base64 é local) */
function montarLogo() {
  const img = document.getElementById('logo-preview');
  const vazio = document.getElementById('logo-vazio');
  if (atual.logo) {
    img.src = `/api/arquivos/${atual.logo}?classe=org_logo`;
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

// `?.`: sem org.configurar o exigirSessao troca o <main> pela página "sem permissão" e estes elementos não existem
document.getElementById('logo-arquivo')?.addEventListener('change', async (e) => {
  const arquivo = e.target.files?.[0];
  e.target.value = '';
  if (!arquivo) return;
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const conteudo = await lerComoBase64(arquivo);
  const r = await enviar('/api/org/logo', { conteudo });
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  atual.logo = r.json.logo;
  montarLogo();
  aviso.ok(t('org.logo_enviado'));
  eventoRegistrado();
});

document.getElementById('logo-remover')?.addEventListener('click', async () => {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const r = await apagar('/api/org/logo');
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  atual.logo = null;
  montarLogo();
  aviso.ok(t('org.logo_removido'));
  eventoRegistrado();
});

/* ---------------------------------------------------------------- SMTP (item L0-07-d-smtp-convites):
   endpoint PRÓPRIO (/api/org/smtp), fora de /api/org — a senha nunca volta na resposta (só
   senha_configurada: bool); "host" vazio apaga o override do inquilino (volta à instalação/caminho manual). */

async function carregarSmtp() {
  const r = await obter('/api/org/smtp');
  if (r.status !== 200) { document.getElementById('aviso').erro(`${t('smtp.erro_carregar')}: ${mensagemDe(r)}`); return; }
  smtpAtual = r.json;
  montarSmtp();
}

function montarSmtp() {
  const s = smtpAtual;
  const rotulo = document.getElementById('smtp-origem');
  rotulo.textContent = s.configurado
    ? t(s.origem === 'inquilino' ? 'smtp.origem_inquilino' : 'smtp.origem_instalacao', { host: s.host })
    : t('smtp.origem_nenhum');
  const f = document.getElementById('form-smtp');
  f.campos = [
    { nome: 'host', rotulo: t('smtp.host'), tipo: 'texto', padrao: s.origem === 'inquilino' ? (s.host || '') : '', ajuda: t('smtp.host_ajuda'), atributos: { maxlength: 255 } },
    { nome: 'porta', rotulo: t('smtp.porta'), tipo: 'numero', padrao: s.origem === 'inquilino' ? (s.porta ?? 587) : 587, atributos: { min: 1, max: 65535, step: 1 } },
    { nome: 'tls', rotulo: t('smtp.tls'), tipo: 'caixa', padrao: s.origem === 'inquilino' ? (s.tls ?? true) : true },
    { nome: 'usuario', rotulo: t('smtp.usuario'), tipo: 'texto', padrao: s.origem === 'inquilino' ? (s.usuario || '') : '', atributos: { maxlength: 255, autocomplete: 'off' } },
    { nome: 'senha', rotulo: t(s.senha_configurada && s.origem === 'inquilino' ? 'smtp.senha_trocar' : 'smtp.senha'), tipo: 'senha', padrao: '', ajuda: s.senha_configurada && s.origem === 'inquilino' ? t('smtp.senha_ajuda') : '', atributos: { maxlength: 1024, autocomplete: 'new-password' } },
    { nome: 'remetente', rotulo: t('smtp.remetente'), tipo: 'texto', padrao: s.origem === 'inquilino' ? (s.remetente || '') : '', atributos: { maxlength: 255 } },
    { nome: 'rotulo', rotulo: t('smtp.rotulo'), tipo: 'texto', padrao: s.origem === 'inquilino' ? (s.rotulo || '') : '', atributos: { maxlength: 100 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    f.ocupado = true;
    const corpo = { host: v.host, porta: v.porta, tls: v.tls, usuario: v.usuario, remetente: v.remetente, rotulo: v.rotulo };
    if (v.senha) corpo.senha = v.senha; // vazio: preserva a cifra atual (nunca reenviamos a senha existente)
    const r = await alterar('/api/org/smtp', corpo);
    f.ocupado = false;
    if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return; }
    smtpAtual = r.json;
    document.getElementById('aviso').ok(t('smtp.salvo'));
    montarSmtp();
    eventoRegistrado();
  });
}

/* ---------------------------------------------------------------- LDAP (UX-06; rotas do L0-08 que estavam sem
   tela: GET/PUT /api/org/ldap e POST /api/org/ldap/importar). Privilégio org.integracoes; a senha de bind só
   vai quando preenchida (vazio preserva a cifra atual) e nunca volta — a API devolve só tem_bind_senha. */
async function carregarLdap() {
  const sec = document.getElementById('ldap');
  const estado = document.getElementById('ldap-estado');
  sec.hidden = false;
  estado.carregando();
  const r = await obter('/api/org/ldap');
  if (r.status !== 200) {
    estado.erro(r);
    estado.addEventListener('acao', (ev) => { if (ev.detail.id === 'tentar') carregarLdap(); }, { once: true });
    return;
  }
  estado.limpar();
  ldapAtual = r.json; // null = nunca configurado
  montarLdap();
  montarLdapImportar();
}

function mapaParaTexto(m) { return Object.entries(m || {}).map(([g, p]) => `${g} = ${p}`); }
function textoParaMapa(linhas, erros) {
  const m = {};
  for (const l of linhas || []) {
    const i = l.lastIndexOf('=');
    if (i < 1) { erros.mapa_grupo_perfil = t('ldap.erro_mapa_linha', { linha: l }); continue; }
    const grupo = l.slice(0, i).trim(); const perfil = l.slice(i + 1).trim();
    if (!PERFIS.includes(perfil)) { erros.mapa_grupo_perfil = t('ldap.erro_mapa_perfil', { perfil }); continue; }
    m[grupo] = perfil;
  }
  return m;
}

function montarLdap() {
  const f = document.getElementById('form-ldap');
  const l = ldapAtual;
  document.getElementById('ldap-estado-texto').textContent = l
    ? (l.habilitado ? t('ldap.estado_habilitado', { url: l.url || t('ldap.sem_url') }) : t('ldap.estado_desabilitado'))
    : t('ldap.estado_nunca');
  const opcoesPerfil = [{ valor: '', rotulo: t('ldap.perfil_padrao_nenhum') }, ...PERFIS.map((p) => ({ valor: p, rotulo: t(`perfil.${p}`) }))];
  f.campos = [
    { nome: 'habilitado', rotulo: t('ldap.habilitado_campo'), tipo: 'caixa', padrao: l ? l.habilitado : false, ajuda: t('ldap.habilitado_ajuda') },
    { nome: 'url', rotulo: t('ldap.url'), tipo: 'texto', padrao: l?.url || '', ajuda: t('ldap.url_ajuda'), atributos: { maxlength: 250, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'base_dn', rotulo: t('ldap.base_dn'), tipo: 'texto', padrao: l?.base_dn || '', atributos: { maxlength: 250, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'start_tls', rotulo: t('ldap.start_tls'), tipo: 'caixa', padrao: l ? l.start_tls : true, ajuda: t('ldap.start_tls_ajuda') },
    { nome: 'bind_dn', rotulo: t('ldap.bind_dn'), tipo: 'texto', padrao: l?.bind_dn || '', ajuda: t('ldap.bind_dn_ajuda'), atributos: { maxlength: 250, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'bind_senha', rotulo: t(l?.tem_bind_senha ? 'ldap.bind_senha_trocar' : 'ldap.bind_senha'), tipo: 'senha', padrao: '', ajuda: l?.tem_bind_senha ? t('ldap.bind_senha_ajuda') : '', atributos: { maxlength: 250, autocomplete: 'new-password' } },
    { nome: 'filtro_usuario', rotulo: t('ldap.filtro_usuario'), tipo: 'texto', padrao: l?.filtro_usuario || '(uid={login})', ajuda: t('ldap.filtro_usuario_ajuda'), atributos: { maxlength: 250, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'atributo_grupos', rotulo: t('ldap.atributo_grupos'), tipo: 'texto', padrao: l?.atributo_grupos || 'memberOf', atributos: { maxlength: 64, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'perfil_padrao', rotulo: t('ldap.perfil_padrao'), tipo: 'select', padrao: l?.perfil_padrao || '', opcoes: opcoesPerfil, ajuda: t('ldap.perfil_padrao_ajuda') },
    { nome: 'mapa_grupo_perfil', rotulo: t('ldap.mapa'), tipo: 'lista', padrao: mapaParaTexto(l?.mapa_grupo_perfil), linhas: 4, ajuda: t('ldap.mapa_ajuda') },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    const erros = {};
    const mapa = textoParaMapa(v.mapa_grupo_perfil, erros);
    if (v.habilitado && !v.url) erros.url = t('ldap.erro_url_obrigatoria');
    if (v.url && !/^ldaps?:\/\//i.test(v.url)) erros.url = t('ldap.erro_url_esquema');
    if (Object.keys(erros).length) { f.limparErros(); for (const [c, m] of Object.entries(erros)) f.erro(c, m); return; }
    const corpo = {
      habilitado: !!v.habilitado, url: v.url || null, base_dn: v.base_dn || null, start_tls: !!v.start_tls, bind_dn: v.bind_dn || null,
      filtro_usuario: v.filtro_usuario || '(uid={login})', atributo_grupos: v.atributo_grupos || 'memberOf',
      perfil_padrao: v.perfil_padrao || null, mapa_grupo_perfil: mapa,
    };
    if (v.bind_senha) corpo.bind_senha = v.bind_senha;
    f.ocupado = true;
    const r = await alterar('/api/org/ldap', corpo);
    f.ocupado = false;
    if (r.status !== 200) {
      const campo = r.json.detalhe && typeof r.json.detalhe === 'object' && !Array.isArray(r.json.detalhe) ? r.json.detalhe.campo : null;
      if (campo && f.campo(campo)) f.erro(campo, mensagemDe(r)); else f.mensagem(mensagemDe(r), 'erro');
      return;
    }
    ldapAtual = r.json;
    document.getElementById('aviso').ok(t('ldap.salvo'));
    montarLdap();
    montarLdapImportar();
    eventoRegistrado();
  });
}

function montarLdapImportar() {
  const f = document.getElementById('form-ldap-importar');
  const habilitado = !!(ldapAtual && ldapAtual.habilitado);
  f.campos = [
    { nome: 'grupo_dn', rotulo: t('ldap.grupo_dn'), tipo: 'texto', obrigatorio: true, padrao: '', ajuda: t('ldap.grupo_dn_ajuda'), atributos: { maxlength: 250, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'atributo_membro', rotulo: t('ldap.atributo_membro'), tipo: 'texto', padrao: 'member', atributos: { maxlength: 64, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'atributo_login', rotulo: t('ldap.atributo_login'), tipo: 'texto', padrao: 'uid', atributos: { maxlength: 64, autocomplete: 'off', spellcheck: 'false' } },
    { nome: 'perfil', rotulo: t('ldap.perfil_importado'), tipo: 'select', padrao: 'visualizador', opcoes: PERFIS.map((p) => ({ valor: p, rotulo: t(`perfil.${p}`) })) },
  ];
  f.botoes = [{ id: 'importar', rotulo: t('ldap.importar'), tipo: 'submit' }];
  if (!habilitado) f.mensagem(t('ldap.importar_exige_habilitado'), 'info');
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    f.ocupado = true;
    const r = await enviar('/api/org/ldap/importar', { grupo_dn: v.grupo_dn, atributo_membro: v.atributo_membro || 'member', atributo_login: v.atributo_login || 'uid', perfil: v.perfil });
    f.ocupado = false;
    if (r.status !== 200) {
      if (r.json.erro === 'ldap_sem_configuracao') f.mensagem(t('ldap.erro_sem_configuracao'), 'erro');
      else if (r.status === 503 || r.status === 502) f.mensagem(t('ldap.erro_servidor', { erro: mensagemDe(r) }), 'erro');
      else f.mensagem(mensagemDe(r), 'erro');
      return;
    }
    // resposta: {grupo_dn, encontrados, criados, ja_existentes, recusados} (plat.ldap_importar_lote)
    const j = r.json || {};
    f.mensagem(t('ldap.importados', { encontrados: j.encontrados ?? 0, criados: j.criados ?? 0, existentes: j.ja_existentes ?? 0, recusados: j.recusados ?? 0 }), 'ok');
    eventoRegistrado();
  });
}

document.getElementById('smtp-testar')?.addEventListener('click', async () => {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const bt = document.getElementById('smtp-testar');
  bt.disabled = true;
  const r = await enviar('/api/org/smtp/testar', {});
  bt.disabled = false;
  if (r.status !== 200) { aviso.erro(`${t('smtp.testar_falhou')}: ${mensagemDe(r)}`); return; }
  aviso.ok(t('smtp.testar_ok', { destinatario: r.json.destinatario }));
});


/* ---------------------------------------------------------------- arquivos e objetos (UX-11; L0-11, ADR 0006)
   GET /api/arquivos (uso × cota), GET /api/arquivos/_varredura (órfãos), POST /api/arquivos?classe= (corpo cru,
   SÓ com token de serviço: sob cookie a escrita tem de ser JSON, proteção contra CSRF) e DELETE
   /api/arquivos/{sha256}. O envio cunha um token `admin:inquilino` de 1 dia por POST /api/tokens, envia com
   Authorization: Bearer e credentials 'omit' (cookie + Authorization juntos dão 400 autenticacao_ambigua) e
   REVOGA o token no fim, dando certo ou errado. O servidor não lista objetos: a tabela mostra os enviados nesta
   sessão, cada um com baixar (GET) e apagar (DELETE). */
import { confirmar } from '../base/componentes.js';
import { h, limpar } from '../base/dom.js';

const arquivosEnviados = [];

function enviarBruto(metodo, url, corpo, cabecalhos) {
  return fetch(url, { method: metodo, body: corpo, credentials: 'omit', cache: 'no-store', headers: cabecalhos });
}

function mbTexto(bytes) { return `${(bytes / (1024 * 1024)).toFixed(1)} MB`; }

async function carregarUsoArquivos() {
  const r = await obter('/api/arquivos');
  const texto = document.getElementById('arquivos-uso-texto');
  const barra = document.getElementById('arquivos-uso-barra');
  const prog = document.getElementById('arquivos-uso');
  if (!texto) return;
  if (r.status !== 200) { texto.textContent = mensagemDe(r); return; }
  const pct = r.json.cota_bytes ? Math.min(100, Math.round((r.json.bytes_usados / r.json.cota_bytes) * 100)) : 0;
  barra.style.width = `${pct}%`;
  prog.setAttribute('aria-valuenow', String(pct));
  texto.textContent = t('org.arquivos_uso', { usado: mbTexto(r.json.bytes_usados), cota: mbTexto(r.json.cota_bytes), pct });
}

async function varrerOrfaos() {
  const estado = document.getElementById('arquivos-estado');
  const saida = document.getElementById('arquivos-varredura');
  estado.carregando(t('org.arquivos_varrendo'));
  const r = await obter('/api/arquivos/_varredura');
  if (r.status !== 200) { estado.erro(r, [{ id: 'varrer', rotulo: t('estado.tentar_de_novo') }]); return; }
  estado.limpar();
  const j = r.json || {};
  saida.textContent = t('org.arquivos_varredura', { objetos: j.objetos_no_garage ?? 0, linhas: j.linhas_no_banco ?? 0, sem_linha: (j.sem_linha || []).length, sem_objeto: (j.sem_objeto || []).length });
}

function desenharArquivos() {
  const tabela = document.getElementById('arquivos-lista');
  const corpo = limpar(document.getElementById('arquivos-corpo'));
  tabela.hidden = !arquivosEnviados.length;
  for (const a of arquivosEnviados) {
    const url = `/api/arquivos/${encodeURIComponent(a.sha256)}?classe=${encodeURIComponent(a.classe)}`;
    const btApagar = h('button', { type: 'button', class: 'pequeno perigo', dataset: { apagar: a.sha256 } }, t('acao.apagar'));
    btApagar.addEventListener('click', () => apagarArquivo(a));
    corpo.append(h('tr', { dataset: { sha256: a.sha256 } },
      h('td', {}, a.classe), h('td', {}, h('code', { class: 'mono' }, `${a.sha256.slice(0, 12)}…`)), h('td', {}, mbTexto(a.bytes)), h('td', {}, a.content_type || ''),
      h('td', { class: 'acoes' }, h('a', { class: 'botao pequeno', href: url, download: '' }, t('org.arquivo_baixar')), ' ', btApagar)));
  }
}

async function apagarArquivo(a) {
  const estado = document.getElementById('arquivos-estado');
  if (!(await confirmar(t('acao.apagar'), t('org.arquivo_apagar_confirma', { sha: a.sha256.slice(0, 12) }), { perigo: true, ok: t('acao.apagar') }))) return;
  const r = await apagar(`/api/arquivos/${encodeURIComponent(a.sha256)}?classe=${encodeURIComponent(a.classe)}`);
  if (r.status !== 204) { estado.erro(r, []); return; }
  estado.limpar();
  arquivosEnviados.splice(arquivosEnviados.indexOf(a), 1);
  desenharArquivos();
  document.getElementById('aviso').ok(t('org.arquivo_apagado'));
  carregarUsoArquivos();
}

function textoErroArquivo(r, j) {
  if (r.status === 413) return t('org.arquivo_cota', { mensagem: (j && j.mensagem) || '' });
  if (r.status === 415) return t('org.arquivo_recusado', { tipo: (j && j.detalhe && j.detalhe.tipo_detectado) || '?' });
  if (r.status === 0) return t('login.sem_servidor');
  return (j && j.mensagem) ? j.mensagem : `${t('erro.carregar')} (${r.status})`;
}

async function enviarArquivo() {
  const estado = document.getElementById('arquivos-estado');
  const entrada = document.getElementById('arquivo-envio');
  const classe = (document.getElementById('arquivo-classe').value || '').trim();
  const botao = document.getElementById('arquivo-enviar');
  const arquivo = entrada.files && entrada.files[0];
  if (!arquivo) { estado.erro(t('org.arquivo_sem_arquivo'), []); return; }
  if (!/^[a-z0-9_]{1,40}$/.test(classe)) { estado.erro(t('org.arquivo_classe_invalida'), []); document.getElementById('arquivo-classe').focus(); return; }
  if (!tem('tokens.gerar')) { estado.negado(t('org.arquivo_sem_token')); return; }
  botao.disabled = true;
  estado.carregando(t('org.arquivo_enviando', { nome: arquivo.name, mb: mbTexto(arquivo.size) }));
  const tk = await enviar('/api/tokens', { nome: t('org.arquivo_token_nome'), escopos: ['admin:inquilino'], validade_dias: 1 });
  if (tk.status !== 201) { botao.disabled = false; estado.mostrar({ tipo: tk.status === 403 ? 'negado' : 'erro', texto: mensagemDe(tk), ref: tk.json?.req_id }); return; }
  let resp; let json = null;
  try {
    // cada chamada com o caminho na própria linha: é assim que docs/gerar_cobertura_ui.py liga rota → tela
    resp = await enviarBruto('POST', `/api/arquivos?classe=${encodeURIComponent(classe)}`, arquivo,
      { Authorization: `Bearer ${tk.json.token}`, 'Content-Type': arquivo.type || 'application/octet-stream', Accept: 'application/json' });
    try { json = await resp.json(); } catch { json = null; }
  } catch (e) {
    resp = { status: 0 }; json = { mensagem: (e && e.message) || String(e) };
  } finally {
    await apagar(`/api/tokens/${encodeURIComponent(tk.json.id)}`); // o token vive só o tempo do envio
  }
  botao.disabled = false;
  if (resp.status !== 201) { estado.mostrar({ tipo: resp.status === 403 ? 'negado' : 'erro', texto: textoErroArquivo(resp, json), ref: json && json.req_id }); return; }
  estado.limpar();
  entrada.value = '';
  botao.disabled = true;
  arquivosEnviados.unshift({ classe, sha256: json.sha256, bytes: json.bytes ?? arquivo.size, content_type: json.content_type || arquivo.type });
  desenharArquivos();
  document.getElementById('aviso').ok(t('org.arquivo_enviado', { sha: String(json.sha256).slice(0, 12) }));
  carregarUsoArquivos();
}

if (document.getElementById('arquivos')) {
  document.getElementById('arquivo-envio').addEventListener('change', (e) => { document.getElementById('arquivo-enviar').disabled = !(e.target.files && e.target.files.length); });
  document.getElementById('arquivo-enviar').addEventListener('click', enviarArquivo);
  document.getElementById('arquivos-varrer').addEventListener('click', varrerOrfaos);
  document.getElementById('arquivos-estado').addEventListener('acao', (ev) => { if (ev.detail.id === 'varrer') varrerOrfaos(); });
  carregarUsoArquivos();
}
