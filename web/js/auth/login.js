/* plat — tela /entrar (ADR 0002 seção 15.1). Lê ?inquilino= e ?proximo=; GET /api/login/provedores; POST /api/login;
   troca para o formulário de código quando exige_2fa (POST /api/login/2fa); contador de 5 min do desafio;
   redireciona só para caminho relativo seguro. Sem "lembrar-me". */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { h, limpar, caminhoSeguro } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import { aplicarFaixaModo } from '../base/modo.js';
import '../base/componentes.js';
import { lembrarInquilino, marcarSessao, inquilinoLembrado } from './sessao.js';

await carregar();
aplicarFaixaModo();  // L7-33: quem ainda não entrou também vê a faixa de manutenção (modo global)

const params = new URLSearchParams(location.search);
const proximo = caminhoSeguro(params.get('proximo'), '/');
const aviso = document.getElementById('aviso');
const formSenha = document.getElementById('form-senha');
const form2fa = document.getElementById('form-2fa');
const campoInquilino = document.getElementById('campo-inquilino');
const inputInquilino = document.getElementById('inquilino');
const inputLogin = document.getElementById('login');
const inputSenha = document.getElementById('senha');
const inputCodigo = document.getElementById('codigo');
const rotuloCodigo = document.getElementById('codigo-rotulo');
const contador = document.getElementById('contador');
const provedores = document.getElementById('provedores');
const btEntrar = document.getElementById('entrar');
const btConfirmar = document.getElementById('confirmar');

let slug = (params.get('inquilino') || inquilinoLembrado() || '').trim();
let desafio = null;
let recuperacao = false;
let relogio = null;

function mostrarInquilino(nome) {
  document.getElementById('inquilino-rotulo').textContent = nome;
  document.getElementById('inquilino-nome').hidden = false;
  campoInquilino.classList.add('oculto');
  inputInquilino.required = false;
  inputInquilino.value = slug;
}

function pedirInquilino(msg) {
  document.getElementById('inquilino-nome').hidden = true;
  campoInquilino.classList.remove('oculto');
  inputInquilino.required = true;
  inputInquilino.value = slug;
  if (msg) aviso.erro(msg);
}

function mostrarProvedores(lista) {
  limpar(provedores);
  for (const p of lista || []) {
    if (!p || typeof p.url !== 'string' || !p.url.startsWith('/')) continue;
    provedores.append(h('a', { class: 'botao', href: p.url }, t('login.entrar_com', { nome: p.nome || p.tipo || '' })));
  }
}

async function carregarInquilino() {
  if (!slug) { pedirInquilino(); return; }
  const r = await obter(`/api/login/provedores?inquilino=${encodeURIComponent(slug)}`);
  if (r.status === 200) {
    mostrarInquilino(r.json.inquilino?.nome || slug);
    mostrarProvedores(r.json.provedores);
    if (r.json.login_local === false) { formSenha.hidden = true; aviso.mostrar(t('login.so_externo'), 'info'); }
    return;
  }
  pedirInquilino(r.status === 404 ? t('login.inquilino_inexistente', { slug }) : mensagemDe(r));
}

function concluir(json) {
  lembrarInquilino(slug);
  marcarSessao(true);
  const pend = json.usuario?.pendencias || [];
  const destino = pend.includes('trocar_senha') ? '/conta#senha' : (pend.length ? '/conta#2fa' : proximo);
  location.replace(destino);
}

function mensagemLogin(r) {
  const j = r.json || {};
  if (r.status === 423 && j.detalhe?.bloqueado_ate) return t('login.bloqueado_ate', { quando: formatarData(j.detalhe.bloqueado_ate) });
  if (r.status === 429) return t('login.muitas_tentativas');
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
  form2fa.hidden = false;
  document.getElementById('alternar-recuperacao').hidden = json.recuperacao_disponivel === false;
  aviso.limpar();
  iniciarRelogio(5 * 60);
  inputCodigo.value = '';
  inputCodigo.focus();
}

function aplicarModoCodigo() {
  rotuloCodigo.textContent = recuperacao ? t('login.codigo_recuperacao') : t('login.codigo');
  inputCodigo.setAttribute('inputmode', recuperacao ? 'text' : 'numeric');
  inputCodigo.setAttribute('autocomplete', recuperacao ? 'off' : 'one-time-code');
  document.getElementById('alternar-recuperacao').textContent = recuperacao ? t('login.usar_autenticador') : t('login.usar_recuperacao');
}

function voltarParaSenha(msg) {
  pararRelogio();
  desafio = null;
  form2fa.hidden = true;
  formSenha.hidden = false;
  inputSenha.value = '';
  if (msg) aviso.mostrar(msg, 'atencao'); else aviso.limpar();
  inputSenha.focus();
}

document.getElementById('mostrar-senha').addEventListener('click', (e) => {
  const ver = inputSenha.type === 'password';
  inputSenha.type = ver ? 'text' : 'password';
  e.currentTarget.setAttribute('aria-pressed', String(ver));
  e.currentTarget.textContent = ver ? t('form.ocultar') : t('form.mostrar');
});

formSenha.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  if (!campoInquilino.classList.contains('oculto')) slug = inputInquilino.value.trim();
  if (!slug || !inputLogin.value.trim() || !inputSenha.value) { aviso.erro(t('login.preencha')); return; }
  btEntrar.disabled = true;
  const r = await enviar('/api/login', { inquilino: slug, login: inputLogin.value.trim(), senha: inputSenha.value });
  btEntrar.disabled = false;
  if (r.status === 200 && r.json.ok === true) { concluir(r.json); return; }
  if (r.status === 200 && r.json.exige_2fa) { mostrar2fa(r.json); return; }
  aviso.erro(mensagemLogin(r));
  inputSenha.focus();
});

document.getElementById('alternar-recuperacao').addEventListener('click', () => {
  recuperacao = !recuperacao;
  aplicarModoCodigo();
  inputCodigo.value = '';
  inputCodigo.focus();
});
document.getElementById('voltar').addEventListener('click', () => voltarParaSenha());

form2fa.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  const codigo = inputCodigo.value.trim();
  if (!codigo || !desafio) { aviso.erro(t('login.preencha_codigo')); return; }
  btConfirmar.disabled = true;
  const corpo = recuperacao ? { desafio, codigo_recuperacao: codigo } : { desafio, codigo };
  const r = await enviar('/api/login/2fa', corpo);
  btConfirmar.disabled = false;
  if (r.status === 200 && r.json.ok === true) { pararRelogio(); concluir(r.json); return; }
  if (r.status === 410) { voltarParaSenha(t('login.desafio_expirado')); return; }
  aviso.erro(mensagemLogin(r));
  inputCodigo.select();
});

await carregarInquilino();
(slug && campoInquilino.classList.contains('oculto') ? inputLogin : inputInquilino).focus();
document.body.dataset.pronto = '1';
