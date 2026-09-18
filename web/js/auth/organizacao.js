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
import { h, limpar } from '../base/dom.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';

/* item UX-17: estado da seção Diretório declarado ANTES de `iniciar()` rodar (o módulo executa de cima para
   baixo e `carregarLdap` é chamado durante a carga — declarar depois seria TDZ, o mesmo susto do smtpAtual). */
let ldapAtual = null;
let ldapOuvintesLigados = false; // os dois formulários são remontados a cada gravação; o ouvinte liga uma vez
const PERFIS_LDAP = ['admin', 'editor', 'visualizador', 'campo'];

const IDIOMAS = [
  { valor: 'pt-BR', rotulo: 'Português (Brasil)' },
  { valor: 'en', rotulo: 'English' },
  { valor: 'es', rotulo: 'Español' },
];
let atual = null;
// declarado ANTES do await de nível de módulo abaixo: carregarSmtp() o atribui durante iniciar(), e um `let` que
// só aparecesse depois estaria na zona morta temporal (achado UX-01: a página nunca marcava body[data-pronto])
let smtpAtual = null;

/* declaradas ANTES dos awaits de nível de módulo: carregarOrg() as usa durante iniciar(), e uma const que
   só aparecesse depois estaria na zona morta temporal (o mesmo achado UX-01 do smtpAtual, duas linhas acima). */
const UNIDADES = ['metrico', 'imperial'];
const FORMATOS_DATA = ['dd/mm/aaaa', 'mm/dd/aaaa', 'aaaa-mm-dd'];
const FORMATOS_NUMERO_DATA = ['idioma', 'navegador'];
const BLOCOS_MAX = 15;
const BLOCO_LINKS_MAX = 8;
let blocosOuvintesLigados = false; // os ouvintes do editor de blocos ligam uma vez; a lista remonta a cada gravação

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
  montarContatos();
  montarRegional();
  montarMapa();
  montarPaginaInicial();
  montarAvisos();
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
    resumo: atual.resumo,
    contato: atual.contato,
    contatos_admin: [...atual.contatos_admin],
    idioma_padrao: atual.idioma_padrao,
    unidades: atual.regional.unidades,
    formato_data: atual.regional.formato_data,
    formato_numero_data: atual.regional.formato_numero_data,
    centro: atual.mapa.centro,
    zoom: atual.mapa.zoom,
    basemap: atual.mapa.basemap,
    extent: atual.mapa.extent,
    srid_padrao: atual.mapa.srid_padrao,
    pagina_inicial: atual.pagina_inicial.map((b) => ({ ...b })),
    galeria_destaque: atual.galeria_destaque,
    banner_aviso: atual.banner_aviso,
    termo_acesso: atual.termo_acesso,
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
    { nome: 'resumo', rotulo: t('org.resumo'), tipo: 'area', padrao: atual.resumo || '', atributos: { rows: 3, maxlength: 310 } },
    { nome: 'contato', rotulo: t('org.contato'), tipo: 'texto', padrao: atual.contato || '', ajuda: t('org.contato_ajuda'), atributos: { maxlength: 254, type: 'email' } },
    { nome: 'idioma_padrao', rotulo: t('org.idioma'), tipo: 'select', padrao: atual.idioma_padrao, opcoes: IDIOMAS },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    if (!/^#[0-9a-fA-F]{6}$/.test(v.cor)) { f.erro('cor', t('org.cor_ajuda')); return; }
    const ok = await salvar(f, { nome: v.nome, cor: v.cor, resumo: v.resumo || null, contato: v.contato || null, idioma_padrao: v.idioma_padrao });
    if (ok) montarLayout({ usuario: { ...usuario, inquilino: { ...usuario.inquilino, nome: v.nome } }, ativo: '/admin/organizacao' });
  });
}

function montarContatos() {
  const f = document.getElementById('form-contatos');
  f.campos = [
    { nome: 'contatos_admin', rotulo: t('org.contatos_lista'), tipo: 'lista', obrigatorio: true, padrao: atual.contatos_admin, linhas: 3, ajuda: t('org.contatos_lista_ajuda') },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    const lista = (e.detail.valores.contatos_admin || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean);
    if (!lista.length) { f.erro('contatos_admin', t('org.contatos_vazio')); return; }
    await salvar(f, { contatos_admin: [...new Set(lista)] });
  });
}

function montarRegional() {
  const f = document.getElementById('form-regional');
  const rotulos = (valores) => valores.map((v) => ({ valor: v, rotulo: t(`org.regional_${v.replace(/\//g, '_')}`) }));
  f.campos = [
    { nome: 'unidades', rotulo: t('org.unidades'), tipo: 'select', padrao: atual.regional.unidades, opcoes: rotulos(UNIDADES) },
    { nome: 'formato_data', rotulo: t('org.formato_data'), tipo: 'select', padrao: atual.regional.formato_data, opcoes: rotulos(FORMATOS_DATA) },
    { nome: 'formato_numero_data', rotulo: t('org.formato_numero_data'), tipo: 'select', padrao: atual.regional.formato_numero_data, opcoes: rotulos(FORMATOS_NUMERO_DATA) },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const v = e.detail.valores;
    salvar(f, { unidades: v.unidades, formato_data: v.formato_data, formato_numero_data: v.formato_numero_data });
  });
}

function montarMapa() {
  const f = document.getElementById('form-mapa');
  const c = atual.mapa.centro || [null, null];
  const ex = atual.mapa.extent || [null, null, null, null];
  f.campos = [
    { nome: 'centro_lon', rotulo: t('org.centro_lon'), tipo: 'numero', padrao: c[0], atributos: { step: 'any', min: -180, max: 180 } },
    { nome: 'centro_lat', rotulo: t('org.centro_lat'), tipo: 'numero', padrao: c[1], atributos: { step: 'any', min: -90, max: 90 } },
    { nome: 'zoom', rotulo: t('org.zoom'), tipo: 'numero', padrao: atual.mapa.zoom, atributos: { min: 0, max: 24, step: 1 } },
    { nome: 'basemap', rotulo: t('org.basemap'), tipo: 'texto', padrao: atual.mapa.basemap || '', atributos: { maxlength: 100 } },
    { nome: 'extent_o', rotulo: t('org.extent_o'), tipo: 'numero', padrao: ex[0], atributos: { step: 'any', min: -180, max: 180 } },
    { nome: 'extent_s', rotulo: t('org.extent_s'), tipo: 'numero', padrao: ex[1], atributos: { step: 'any', min: -90, max: 90 } },
    { nome: 'extent_l', rotulo: t('org.extent_l'), tipo: 'numero', padrao: ex[2], atributos: { step: 'any', min: -180, max: 180 } },
    { nome: 'extent_n', rotulo: t('org.extent_n'), tipo: 'numero', padrao: ex[3], atributos: { step: 'any', min: -90, max: 90 } },
    { nome: 'srid_padrao', rotulo: t('org.srid'), tipo: 'numero', padrao: atual.mapa.srid_padrao, atributos: { min: 1024, max: 999999, step: 1 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const v = e.detail.valores;
    const centro = v.centro_lon === null || v.centro_lat === null ? null : [v.centro_lon, v.centro_lat];
    const exVals = [v.extent_o, v.extent_s, v.extent_l, v.extent_n];
    const extent = exVals.some((x) => x === null) ? null : exVals;
    if (extent && !(extent[0] < extent[2] && extent[1] < extent[3])) { f.erro('extent_o', t('org.extent_invalido')); return; }
    salvar(f, { centro, zoom: v.zoom, basemap: v.basemap || null, extent, srid_padrao: v.srid_padrao });
  });
}

/* ---------------- página inicial (item L0-07-a): editor de blocos fora do plat-formulario — o componente
   declarativo não tem "lista de sub-formulários por tipo". Cada bloco é um fieldset com os campos do seu tipo;
   links entram como linhas "rótulo | URL" (o mesmo formato do mapa grupo→perfil do LDAP, que o admin já
   conhece). Validado no cliente antes do PUT e de novo no servidor (422 com caminho). */
function blocoParaFieldset(bloco, i) {
  const fs = h('fieldset', { class: 'bloco-edit', dataset: { tipo: bloco.tipo } });
  fs.append(h('legend', {}, `${t(`org.bloco_${bloco.tipo}`)} ${i + 1}`));
  const titulo = h('input', { class: 'bloco-titulo', type: 'text', value: bloco.titulo || '', maxlength: 80 });
  fs.append(h('label', { class: 'fraco' }, t('org.bloco_titulo'), titulo));
  if (bloco.tipo === 'texto') {
    fs.append(h('textarea', { class: 'bloco-texto', rows: 3, maxlength: 4000 }, bloco.texto || ''));
  } else if (bloco.tipo === 'links') {
    const linhas = (bloco.links || []).map((l) => `${l.rotulo} | ${l.url}`).join('\n');
    fs.append(h('textarea', { class: 'bloco-links', rows: 4, placeholder: t('org.bloco_links_formato') }, linhas));
  } else {
    fs.append(h('p', { class: 'fraco' }, t('org.bloco_galeria_info')));
  }
  const subir = h('button', { type: 'button', class: 'pequeno bloco-subir', 'aria-label': t('org.bloco_subir') }, '↑');
  const remover = h('button', { type: 'button', class: 'pequeno perigo bloco-remover' }, t('org.bloco_remover'));
  fs.append(h('div', { class: 'botoes' }, subir, remover));
  return fs;
}

function montarPaginaInicial() {
  const lista = document.getElementById('blocos-lista');
  limpar(lista);
  atual.pagina_inicial.forEach((bloco, i) => lista.append(blocoParaFieldset(bloco, i)));
  montarGaleriaDestaque();
  if (blocosOuvintesLigados) return;
  blocosOuvintesLigados = true;
  document.getElementById('bloco-adicionar').addEventListener('click', () => {
    if (lista.children.length >= BLOCOS_MAX) { document.getElementById('aviso').erro(t('org.blocos_max', { n: BLOCOS_MAX })); return; }
    const tipo = document.getElementById('bloco-add-tipo').value;
    const bloco = tipo === 'texto' ? { tipo, titulo: '', texto: '' } : tipo === 'links' ? { tipo, titulo: '', links: [] } : { tipo, titulo: '' };
    lista.append(blocoParaFieldset(bloco, lista.children.length));
    renumerarBlocos();
  });
  lista.addEventListener('click', (e) => {
    const fs = e.target.closest('fieldset.bloco-edit');
    if (!fs) return;
    if (e.target.closest('.bloco-remover')) { fs.remove(); renumerarBlocos(); }
    else if (e.target.closest('.bloco-subir') && fs.previousElementSibling) { fs.previousElementSibling.before(fs); renumerarBlocos(); }
  });
  document.getElementById('blocos-salvar').addEventListener('click', salvarBlocos);
}

function renumerarBlocos() {
  document.querySelectorAll('#blocos-lista fieldset.bloco-edit legend').forEach((leg, i) => {
    leg.textContent = leg.textContent.replace(/\d+$/, `${i + 1}`);
  });
}

async function montarGaleriaDestaque() {
  const sel = document.getElementById('galeria-destaque');
  limpar(sel);
  sel.append(h('option', { value: '' }, t('org.galeria_nenhuma')));
  const r = await obter('/api/grupos?limite=100');
  if (r.status === 200 && r.json && Array.isArray(r.json.itens)) {
    for (const g of r.json.itens) sel.append(h('option', { value: g.id }, g.nome));
  }
  sel.value = atual.galeria_destaque || '';
  if (atual.galeria_destaque && sel.value !== atual.galeria_destaque) {
    sel.append(h('option', { value: atual.galeria_destaque }, atual.galeria_destaque));
    sel.value = atual.galeria_destaque;
  }
}

function coletarBlocos() {
  const blocos = [];
  for (const fs of document.querySelectorAll('#blocos-lista fieldset.bloco-edit')) {
    const tipo = fs.dataset.tipo;
    const titulo = fs.querySelector('.bloco-titulo').value.trim();
    if (tipo === 'texto') {
      const texto = fs.querySelector('.bloco-texto').value.trim();
      if (!texto) return { erro: t('org.bloco_texto_vazio') };
      blocos.push({ tipo, titulo, texto });
    } else if (tipo === 'links') {
      const links = [];
      for (const linha of fs.querySelector('.bloco-links').value.split('\n')) {
        const li = linha.trim();
        if (!li) continue;
        const corte = li.indexOf('|');
        const rotulo = (corte >= 0 ? li.slice(0, corte) : li).trim();
        const url = (corte >= 0 ? li.slice(corte + 1) : '').trim();
        if (!rotulo || !url || !(url.startsWith('https://') || (url.startsWith('/') && !url.startsWith('//')))) {
          return { erro: t('org.bloco_link_invalido', { linha: li }) };
        }
        links.push({ rotulo, url });
      }
      if (!links.length || links.length > BLOCO_LINKS_MAX) return { erro: t('org.bloco_links_max', { n: BLOCO_LINKS_MAX }) };
      blocos.push({ tipo, titulo, links });
    } else {
      blocos.push({ tipo, titulo });
    }
  }
  if (blocos.length > BLOCOS_MAX) return { erro: t('org.blocos_max', { n: BLOCOS_MAX }) };
  return { blocos };
}

async function salvarBlocos() {
  const aviso = document.getElementById('aviso');
  aviso.limpar();
  const { blocos, erro } = coletarBlocos();
  if (erro) { aviso.erro(erro); return; }
  const bt = document.getElementById('blocos-salvar');
  bt.disabled = true;
  const r = await alterar('/api/org', corpoBase({ pagina_inicial: blocos, galeria_destaque: document.getElementById('galeria-destaque').value || null }));
  bt.disabled = false;
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  atual = r.json;
  montarPaginaInicial();
  aviso.ok(t('org.salvo'));
}

function montarAvisos() {
  const f = document.getElementById('form-avisos');
  f.campos = [
    { nome: 'banner_aviso', rotulo: t('org.banner'), tipo: 'area', padrao: atual.banner_aviso || '', atributos: { rows: 2, maxlength: 500 } },
    { nome: 'termo_acesso', rotulo: t('org.termo'), tipo: 'area', padrao: atual.termo_acesso || '', atributos: { rows: 6, maxlength: 4000 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  f.addEventListener('enviar', (e) => {
    const v = e.detail.valores;
    salvar(f, { banner_aviso: v.banner_aviso || null, termo_acesso: v.termo_acesso || null });
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
  carregarLdap();  // item UX-17: seção do diretório carrega em paralelo (privilégio próprio: org.integracoes)
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


/* ---------------------------------------------------------------- Diretório LDAP (item UX-17-login-sem-controle):
   controles em tela para PUT /api/org/ldap (configuração, corpo sempre completo) e POST /api/org/ldap/importar
   (grupo → usuários desabilitados). Estados do sistema de design: carregando, erro (com "tentar de novo" e
   referência), negado (403: privilégio org.integracoes é separado do org.configurar desta tela), vazio (nenhum
   provedor ainda) e conteúdo. A senha da conta de serviço nunca volta na resposta (só tem_bind_senha). */

function opcoesPerfilLdap(comNenhum) {
  const base = PERFIS_LDAP.map((p) => ({ valor: p, rotulo: t(`perfil.${p}`) }));
  return comNenhum ? [{ valor: '', rotulo: t('ldap.perfil_nenhum') }, ...base] : base;
}

function mapaParaTexto(mapa) {
  return Object.entries(mapa || {}).map(([g, p]) => `${g} = ${p}`).join('\n');
}

function textoParaMapa(texto) {
  const mapa = {};
  const linhas = String(texto || '').split('\n');
  for (let i = 0; i < linhas.length; i++) {
    const li = linhas[i].trim();
    if (!li) continue;
    const m = li.match(/^(.+?)\s*=\s*([a-z]+)$/);
    if (!m || !PERFIS_LDAP.includes(m[2])) return { erro: i + 1 };
    mapa[m[1].trim()] = m[2];
  }
  return { mapa };
}

async function carregarLdap() {
  const estado = document.getElementById('ldap-estado');
  const form = document.getElementById('form-ldap');
  const resumo = document.getElementById('ldap-resumo');
  estado.hidden = false;
  form.hidden = true;
  resumo.hidden = true;
  estado.carregando();
  const r = await obter('/api/org/ldap');
  if (r.status === 403) { estado.negado(t('ldap.negado')); mostrarImportar(false); return; }
  if (r.status !== 200) {
    estado.mostrar({ tipo: 'erro', titulo: t('ldap.erro_carregar'), texto: mensagemDe(r), ref: r.json?.req_id,
                     acoes: [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }] });
    estado.addEventListener('acao', (e) => { if (e.detail?.id === 'tentar') carregarLdap(); }, { once: true });
    mostrarImportar(false);
    return;
  }
  ldapAtual = r.json; // null = nenhum provedor ainda (estado vazio, com o formulário para preencher)
  estado.hidden = true;
  estado.limpar();
  montarLdap();
}

function mostrarImportar(visivel) {
  for (const id of ['t-ldap-importar', 'ldap-importar-ajuda', 'form-ldap-importar']) document.getElementById(id).hidden = !visivel;
}

function montarLdap() {
  const s = ldapAtual;
  const resumo = document.getElementById('ldap-resumo');
  resumo.hidden = false;
  resumo.id = 'ldap-resumo';
  if (!s) {
    resumo.textContent = t('ldap.nao_configurado');
    resumo.dataset.estado = 'vazio';
  } else {
    resumo.textContent = t('ldap.configurado', { url: s.url || '—', base_dn: s.base_dn || '—', estado: t(s.habilitado ? 'ldap.habilitado' : 'ldap.desabilitado') });
    resumo.dataset.estado = s.habilitado ? 'habilitado' : 'desabilitado';
  }
  const f = document.getElementById('form-ldap');
  f.hidden = false;
  f.campos = [
    { nome: 'habilitado', rotulo: t('ldap.campo_habilitado'), tipo: 'caixa', padrao: s ? s.habilitado : false },
    { nome: 'url', rotulo: t('ldap.url'), tipo: 'texto', padrao: s?.url || '', ajuda: t('ldap.url_ajuda'), atributos: { maxlength: 250 } },
    { nome: 'base_dn', rotulo: t('ldap.base_dn'), tipo: 'texto', padrao: s?.base_dn || '', ajuda: t('ldap.base_dn_ajuda'), atributos: { maxlength: 250 } },
    { nome: 'start_tls', rotulo: t('ldap.start_tls'), tipo: 'caixa', padrao: s ? s.start_tls : true },
    { nome: 'bind_dn', rotulo: t('ldap.bind_dn'), tipo: 'texto', padrao: s?.bind_dn || '', ajuda: t('ldap.bind_dn_ajuda'), atributos: { maxlength: 250, autocomplete: 'off' } },
    { nome: 'bind_senha', rotulo: t(s?.tem_bind_senha ? 'ldap.bind_senha_trocar' : 'ldap.bind_senha'), tipo: 'senha', padrao: '', ajuda: s?.tem_bind_senha ? t('ldap.bind_senha_ajuda') : '', atributos: { maxlength: 250, autocomplete: 'new-password' } },
    { nome: 'filtro_usuario', rotulo: t('ldap.filtro_usuario'), tipo: 'texto', obrigatorio: true, padrao: s?.filtro_usuario || '(uid={login})', ajuda: t('ldap.filtro_ajuda'), atributos: { maxlength: 250 } },
    { nome: 'atributo_grupos', rotulo: t('ldap.atributo_grupos'), tipo: 'texto', obrigatorio: true, padrao: s?.atributo_grupos || 'memberOf', atributos: { maxlength: 64 } },
    { nome: 'perfil_padrao', rotulo: t('ldap.perfil_padrao'), tipo: 'select', padrao: s?.perfil_padrao || '', opcoes: opcoesPerfilLdap(true) },
    { nome: 'mapa', rotulo: t('ldap.mapa'), tipo: 'area', padrao: mapaParaTexto(s?.mapa_grupo_perfil), ajuda: t('ldap.mapa_ajuda'), atributos: { rows: 4, maxlength: 4000 } },
  ];
  f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
  montarImportar();
  if (ldapOuvintesLigados) return;
  ldapOuvintesLigados = true;
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    f.limparErros();
    const mapa = textoParaMapa(v.mapa);
    if (mapa.erro) { f.erro('mapa', t('ldap.mapa_invalido', { n: mapa.erro })); return; }
    f.ocupado = true;
    const corpo = {
      habilitado: !!v.habilitado, url: v.url || null, base_dn: v.base_dn || null, start_tls: !!v.start_tls,
      bind_dn: v.bind_dn || null, filtro_usuario: v.filtro_usuario, atributo_grupos: v.atributo_grupos,
      perfil_padrao: v.perfil_padrao || null, mapa_grupo_perfil: mapa.mapa,
    };
    if (v.bind_senha) corpo.bind_senha = v.bind_senha; // vazio: preserva a cifra guardada
    const r = await alterar('/api/org/ldap', corpo);
    f.ocupado = false;
    if (r.status === 403) { f.mensagem(t('ldap.negado'), 'erro'); return; }
    if (r.status === 422 && r.json?.detalhe?.campo) {
      const campo = r.json.detalhe.campo === 'mapa_grupo_perfil' ? 'mapa' : r.json.detalhe.campo;
      f.erro(campo, r.json.mensagem);
      return;
    }
    if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return; }
    ldapAtual = r.json;
    document.getElementById('aviso').ok(t('ldap.salvo'));
    montarLdap();
  });
  ligarImportar();
}

function montarImportar() {
  mostrarImportar(true);
  const f = document.getElementById('form-ldap-importar');
  f.campos = [
    { nome: 'grupo_dn', rotulo: t('ldap.grupo_dn'), tipo: 'texto', obrigatorio: true, padrao: '', ajuda: t('ldap.grupo_dn_ajuda'), atributos: { maxlength: 250 } },
    { nome: 'atributo_membro', rotulo: t('ldap.atributo_membro'), tipo: 'texto', obrigatorio: true, padrao: 'member', atributos: { maxlength: 64 } },
    { nome: 'atributo_login', rotulo: t('ldap.atributo_login'), tipo: 'texto', obrigatorio: true, padrao: 'uid', atributos: { maxlength: 64 } },
    { nome: 'perfil', rotulo: t('ldap.perfil'), tipo: 'select', padrao: 'visualizador', opcoes: opcoesPerfilLdap(false) },
  ];
  f.botoes = [{ id: 'importar', rotulo: t('ldap.importar'), tipo: 'submit' }];
}

function ligarImportar() {
  const f = document.getElementById('form-ldap-importar');
  f.addEventListener('enviar', async (e) => {
    const v = e.detail.valores;
    f.limparErros();
    f.ocupado = true;
    const r = await enviar('/api/org/ldap/importar', { grupo_dn: v.grupo_dn, atributo_membro: v.atributo_membro, atributo_login: v.atributo_login, perfil: v.perfil });
    f.ocupado = false;
    if (r.status === 403) { f.mensagem(t('ldap.importar_negado'), 'erro'); return; }
    if (r.status === 409) { f.mensagem(t('ldap.importar_sem_configuracao'), 'erro'); return; }
    if (r.status === 503) { f.mensagem(`${t('ldap.importar_indisponivel')} (${mensagemDe(r)})`, 'erro'); return; }
    if (r.status === 422 && r.json?.detalhe?.campo) { f.erro(r.json.detalhe.campo, r.json.mensagem); return; }
    if (r.status !== 200) { f.mensagem(mensagemDe(r), 'erro'); return; }
    const j = r.json;
    f.mensagem(t('ldap.importar_ok', { encontrados: j.encontrados, criados: j.criados, ja_existentes: j.ja_existentes, recusados: j.recusados }), 'ok');
    document.getElementById('aviso').ok(t('ldap.importar_ok', { encontrados: j.encontrados, criados: j.criados, ja_existentes: j.ja_existentes, recusados: j.recusados }));
  });
}
