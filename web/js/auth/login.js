/* plat — tela /entrar (ADR 0002 seção 15.1; polimento UX-02). Lê ?inquilino= e ?proximo=; GET /api/login/provedores;
   POST /api/login; troca para o formulário de código quando exige_2fa (POST /api/login/2fa); contador de 5 min do
   desafio; redireciona só para caminho relativo seguro. Sem "lembrar-me".
   Estados explícitos: erro por campo (nunca só o aviso geral), botão ocupado durante a chamada, aviso de Caps Lock,
   estado de rede fora com "tentar de novo", sucesso antes do redirecionamento. Idioma pelo <plat-idioma> do cartão. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar, caminhoSeguro } from '../base/dom.js';
import { carregar, t, formatarData, aoTraduzir } from '../base/i18n.js';
import '../base/componentes.js';
import { avisarCapsLock, erroCampo, errosDoServidor, ligarMostrarSenha, limparErros, ocupado, validar } from '../base/campos.js';
import { lembrarInquilino, marcarSessao, inquilinoLembrado } from './sessao.js';

await carregar();

const params = new URLSearchParams(location.search);
const proximo = caminhoSeguro(params.get('proximo'), '/');
const el = (id) => document.getElementById(id);
const aviso = el('aviso');
const estado = el('estado-entrada');
const formSenha = el('form-senha');
const form2fa = el('form-2fa');
const campoInquilino = el('campo-inquilino');
const inputInquilino = el('inquilino');
const inputLogin = el('login');
const inputSenha = el('senha');
const inputCodigo = el('codigo');
const rotuloCodigo = el('codigo-rotulo');
const ajudaCodigo = el('codigo-ajuda');
const contador = el('contador');
const provedores = el('provedores');
const btEntrar = el('entrar');
const btConfirmar = el('confirmar');
const btAlternar = el('alternar-recuperacao');

let slug = (params.get('inquilino') || inquilinoLembrado() || '').trim();
let desafio = null;
let recuperacao = false;
let relogio = null;
let listaProvedores = [];
let modoLdap = false; // UX-17: entrar pelo diretório (POST /api/login/ldap) com os mesmos campos usuário/senha

function mostrarInquilino(nome) {
  el('inquilino-rotulo').textContent = nome;
  el('inquilino-nome').hidden = false;
  campoInquilino.classList.add('oculto');
  inputInquilino.required = false;
  inputInquilino.value = slug;
}

function pedirInquilino(msg) {
  el('inquilino-nome').hidden = true;
  campoInquilino.classList.remove('oculto');
  inputInquilino.required = true;
  inputInquilino.value = slug;
  if (msg) erroCampo(inputInquilino, msg);
}

function mostrarProvedores(lista) {
  listaProvedores = lista || [];
  limpar(provedores);
  for (const p of listaProvedores) {
    if (p && p.tipo === 'ldap') {
      // diretório LDAP/AD do inquilino: mesmo formulário, outra rota; o botão alterna e diz o que muda
      const b = h('button', { type: 'button', class: 'botao', id: 'entrar-ldap', 'aria-pressed': String(modoLdap) },
        t(modoLdap ? 'login.ldap_usar_local' : 'login.entrar_com', { nome: p.nome || 'LDAP' }));
      b.addEventListener('click', () => alternarLdap(!modoLdap));
      provedores.append(b);
      continue;
    }
    if (!p || typeof p.url !== 'string' || !p.url.startsWith('/')) continue;
    provedores.append(h('a', { class: 'botao', href: p.url }, t('login.entrar_com', { nome: p.nome || p.tipo || '' })));
  }
  const dica = el('ldap-dica');
  dica.hidden = !modoLdap;
  dica.textContent = modoLdap ? t('login.ldap_dica') : '';
}

function alternarLdap(ligar) {
  modoLdap = !!ligar && listaProvedores.some((p) => p && p.tipo === 'ldap');
  mostrarProvedores(listaProvedores);
  aviso.limpar();
  inputLogin.focus();
}

async function carregarInquilino() {
  estado.limpar();
  formSenha.hidden = false;
  if (!slug) { pedirInquilino(); return; }
  formSenha.setAttribute('aria-busy', 'true');
  const r = await obter(`/api/login/provedores?inquilino=${encodeURIComponent(slug)}`);
  formSenha.removeAttribute('aria-busy');
  if (r.status === 200) {
    mostrarInquilino(r.json.inquilino?.nome || slug);
    mostrarProvedores(r.json.provedores);
    if (r.json.login_local === false) { formSenha.hidden = true; aviso.mostrar(t('login.so_externo'), 'info'); }
    return;
  }
  if (r.status === 0 || r.status >= 500) {
    // sem servidor: estado de erro com nova tentativa, em vez de um formulário que falharia em silêncio
    formSenha.hidden = true;
    estado.erro(r, [{ id: 'tentar', rotulo: t('login.tentar_de_novo'), classe: 'primario' }]);
    return;
  }
  pedirInquilino(r.status === 404 ? t('login.inquilino_inexistente', { slug }) : mensagemDe(r));
}
estado.addEventListener('acao', () => carregarInquilino());

function concluir(json) {
  lembrarInquilino(slug);
  marcarSessao(true);
  const pend = json.usuario?.pendencias || [];
  const destino = pend.includes('trocar_senha') ? '/conta#senha' : (pend.length ? '/conta#2fa' : proximo);
  aviso.ok(t('login.redirecionando'));
  location.replace(destino);
}

function mensagemLogin(r) {
  const j = r.json || {};
  if (j.erro === 'ldap_indisponivel' || j.erro === 'ldap_sem_configuracao') return t('login.ldap_indisponivel');
  if (j.erro === 'sem_grupo_mapeado') return t('login.ldap_sem_grupo');
  if (j.erro === 'login_em_uso_local') return t('login.ldap_login_local');
  if (r.status === 423 && j.detalhe?.bloqueado_ate) return t('login.bloqueado_ate', { quando: formatarData(j.detalhe.bloqueado_ate) });
  if (r.status === 429) return t('login.muitas_tentativas');
  if (r.status === 0) return t('login.sem_servidor');
  return mensagemDe(r);
}

function pararRelogio() { if (relogio) { clearInterval(relogio); relogio = null; } contador.textContent = ''; }

function iniciarRelogio(segundos) {
  pararRelogio();
  const fim = Date.now() + segundos * 1000;
  const tique = () => {
    const resta = Math.max(0, Math.round((fim - Date.now()) / 1000));
    contador.textContent = t('login.desafio_expira', { min: Math.floor(resta / 60), seg: String(resta % 60).padStart(2, '0') });
    if (resta <= 0) { pararRelogio(); voltarParaSenha(t('login.desafio_expirado')); }
  };
  tique();
  relogio = setInterval(tique, 1000);
}

function mostrar2fa(json) {
  desafio = json.desafio;
  recuperacao = false;
  aplicarModoCodigo();
  formSenha.hidden = true;
  provedores.hidden = true;
  form2fa.hidden = false;
  btAlternar.hidden = json.recuperacao_disponivel === false;
  aviso.limpar();
  iniciarRelogio(5 * 60);
  inputCodigo.value = '';
  inputCodigo.focus();
}

function aplicarModoCodigo() {
  rotuloCodigo.textContent = recuperacao ? t('login.codigo_recuperacao') : t('login.codigo');
  ajudaCodigo.textContent = recuperacao ? t('login.codigo_recuperacao_ajuda') : t('login.codigo_ajuda');
  inputCodigo.setAttribute('inputmode', recuperacao ? 'text' : 'numeric');
  inputCodigo.setAttribute('autocomplete', recuperacao ? 'off' : 'one-time-code');
  inputCodigo.setAttribute('maxlength', recuperacao ? '20' : '6');
  btAlternar.textContent = recuperacao ? t('login.usar_autenticador') : t('login.usar_recuperacao');
}

function voltarParaSenha(msg) {
  pararRelogio();
  desafio = null;
  form2fa.hidden = true;
  formSenha.hidden = false;
  provedores.hidden = false;
  inputSenha.value = '';
  limparErros(document);
  if (msg) aviso.mostrar(msg, 'atencao'); else aviso.limpar();
  inputSenha.focus();
}

ligarMostrarSenha(el('mostrar-senha'), inputSenha);
avisarCapsLock(inputSenha);
inputCodigo.addEventListener('input', () => { if (!recuperacao) inputCodigo.value = inputCodigo.value.replace(/\D/g, '').slice(0, 6); });

formSenha.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  limparErros(formSenha);
  if (!campoInquilino.classList.contains('oculto')) slug = inputInquilino.value.trim();
  const pares = [[inputLogin, t('login.usuario_obrigatorio')], [inputSenha, t('login.senha_obrigatoria')]];
  if (!campoInquilino.classList.contains('oculto')) pares.unshift([inputInquilino, t('login.inquilino_obrigatorio')]);
  if (!validar(pares)) return;
  ocupado(btEntrar, true, t('login.entrando'));
  formSenha.setAttribute('aria-busy', 'true');
  const credenciais = { inquilino: slug, login: inputLogin.value.trim(), senha: inputSenha.value };
  const r = modoLdap ? await enviar('/api/login/ldap', credenciais) : await enviar('/api/login', credenciais);
  formSenha.removeAttribute('aria-busy');
  ocupado(btEntrar, false);
  if (r.status === 200 && r.json.ok === true) { concluir(r.json); return; }
  if (modoLdap && r.status === 403 && r.json?.erro === 'login_ldap_desabilitado') { alternarLdap(false); aviso.erro(t('login.ldap_desabilitado')); return; }
  if (r.status === 200 && r.json.exige_2fa) { mostrar2fa(r.json); return; }
  if (r.status === 404) { pedirInquilino(t('login.inquilino_inexistente', { slug })); inputInquilino.focus(); return; }
  if (r.status === 422 && errosDoServidor(r, { inquilino: inputInquilino, login: inputLogin, senha: inputSenha })) { return; }
  aviso.erro(mensagemLogin(r));
  if (r.status === 401) { erroCampo(inputSenha, mensagemLogin(r)); inputSenha.select(); } else inputSenha.focus();
});

btAlternar.addEventListener('click', () => {
  recuperacao = !recuperacao;
  aplicarModoCodigo();
  limparErros(form2fa);
  inputCodigo.value = '';
  inputCodigo.focus();
});
el('voltar').addEventListener('click', () => voltarParaSenha());

form2fa.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  limparErros(form2fa);
  const codigo = inputCodigo.value.trim();
  if (!desafio) { voltarParaSenha(t('login.desafio_expirado')); return; }
  const formato = recuperacao ? /^[a-z0-9-]{8,20}$/i : /^\d{6}$/;
  if (!validar([[inputCodigo, codigo ? t(recuperacao ? 'login.codigo_recuperacao_formato' : 'login.codigo_formato') : t('login.codigo_obrigatorio'), (v) => formato.test(v)]])) return;
  ocupado(btConfirmar, true, t('login.entrando'));
  form2fa.setAttribute('aria-busy', 'true');
  const corpo = recuperacao ? { desafio, codigo_recuperacao: codigo } : { desafio, codigo };
  const r = await enviar('/api/login/2fa', corpo);
  form2fa.removeAttribute('aria-busy');
  ocupado(btConfirmar, false);
  if (r.status === 200 && r.json.ok === true) { pararRelogio(); concluir(r.json); return; }
  if (r.status === 410) { voltarParaSenha(t('login.desafio_expirado')); return; }
  aviso.erro(mensagemLogin(r));
  erroCampo(inputCodigo, mensagemLogin(r));
  inputCodigo.select();
});

/* troca de idioma pelo seletor: o que foi montado por código re-traduz aqui (o resto é data-i18n) */
aoTraduzir(() => {
  if (!form2fa.hidden) aplicarModoCodigo();
  if (listaProvedores.length) mostrarProvedores(listaProvedores);
  if (!el('inquilino-nome').hidden) document.title = `${t('login.entrar')} · ${t('app.nome')}`;
});

await carregarInquilino();
(slug && campoInquilino.classList.contains('oculto') ? inputLogin : inputInquilino).focus();
document.body.dataset.pronto = '1';
