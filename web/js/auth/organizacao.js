/* plat — tela /admin/organizacao (item L0-07-a-configuracoes-org): GET/PUT /api/org sobre `plat.tenant` — nome,
   identidade visual (cor + logotipo, reaproveitando POST/DELETE /api/org/logo do L0-11), mapa padrão, idioma
   padrão, cotas de armazenamento/usuários e a MESMA política de senha/2FA que /conta já lê (tenant.config.auth,
   L0-02): esta tela só a expõe para edição, nunca recria um esquema novo. Cinco `plat-formulario` (uma por
   assunto) escrevem no MESMO objeto: cada envio parte do último `GET /api/org` conhecido, sobrepõe só os campos
   da própria seção e manda o corpo INTEIRO (a API substitui `tenant.config` por merge, mas o corpo de entrada é
   sempre completo — mesmo contrato do PUT /api/org/ldap). Só admin do inquilino chega aqui (privilégio
   `org.configurar`); quem não tem cai em "sem permissão" pelo próprio `exigirSessao`. */
import { obter, enviar, alterar, apagar, mensagemDe } from '../base/api.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';

const IDIOMAS = [{ valor: 'pt-BR', rotulo: 'Português (Brasil)' }];
let atual = null;

/* declarado antes de qualquer await de topo: iniciar() chega em carregarSmtp() antes de a linha do `let` executar
   (zona morta temporal, achado pelo e2e do L0-14 em /admin/organizacao) */
let smtpAtual = null;

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
  const r = await obter('/api/org');
  if (r.status !== 200) { document.getElementById('aviso').erro(`${t('org.erro_carregar')}: ${mensagemDe(r)}`); return; }
  atual = r.json;
  montarLogo();
  montarIdentidade();
  montarMapa();
  montarArmazenamento();
  montarUsuarios();
  montarSeguranca();
  await carregarSmtp();
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

document.getElementById('logo-arquivo').addEventListener('change', async (e) => {
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
});

document.getElementById('logo-remover').addEventListener('click', async () => {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const r = await apagar('/api/org/logo');
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  atual.logo = null;
  montarLogo();
  aviso.ok(t('org.logo_removido'));
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
  });
}

document.getElementById('smtp-testar').addEventListener('click', async () => {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const bt = document.getElementById('smtp-testar');
  bt.disabled = true;
  const r = await enviar('/api/org/smtp/testar', {});
  bt.disabled = false;
  if (r.status !== 200) { aviso.erro(`${t('smtp.testar_falhou')}: ${mensagemDe(r)}`); return; }
  aviso.ok(t('smtp.testar_ok', { destinatario: r.json.destinatario }));
});
