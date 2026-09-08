/* plat — tela pública /redefinir-senha (item L0-07-d-smtp-convites): sem ?token=, formulário de SOLICITAR
   (inquilino + e-mail; resposta sempre genérica, nunca revela se o e-mail existe); com ?token=, formulário de
   TROCAR a senha (GET /api/senha/redefinir/resolver valida antes de mostrar o campo; POST .../aplicar troca). */
import { enviar, mensagemDe, obter } from '../base/api.js';
import '../base/componentes.js';
import { carregar, t } from '../base/i18n.js';

await carregar();

const params = new URLSearchParams(location.search);
const token = params.get('token') || '';
const aviso = document.getElementById('aviso');
const formSolicitar = document.getElementById('form-solicitar');
const solicitado = document.getElementById('solicitado');
const formAplicar = document.getElementById('form-aplicar');
const concluido = document.getElementById('concluido');

function mensagemMotivo(json) {
  const motivo = json?.detalhe?.motivo;
  return t(motivo === 'expirado' ? 'redefinir_senha.expirado' : 'redefinir_senha.invalido');
}

async function iniciar() {
  if (!token) { formSolicitar.hidden = false; document.getElementById('inquilino').focus(); return; }
  const r = await obter(`/api/senha/redefinir/resolver?token=${encodeURIComponent(token)}`);
  if (r.status !== 200) { aviso.erro(mensagemMotivo(r.json)); return; }
  formAplicar.hidden = false;
  document.getElementById('senha').focus();
}

document.getElementById('mostrar-senha').addEventListener('click', (e) => {
  const senha = document.getElementById('senha');
  const ver = senha.type === 'password';
  senha.type = ver ? 'text' : 'password';
  e.currentTarget.setAttribute('aria-pressed', String(ver));
  e.currentTarget.textContent = ver ? t('form.ocultar') : t('form.mostrar');
});

formSolicitar.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  const inquilino = document.getElementById('inquilino').value.trim();
  const email = document.getElementById('email').value.trim();
  if (!inquilino || !email) { aviso.erro(t('login.preencha')); return; }
  const bt = document.getElementById('solicitar');
  bt.disabled = true;
  const r = await enviar('/api/senha/redefinir/solicitar', { inquilino, email });
  bt.disabled = false;
  if (r.status === 429) { aviso.erro(mensagemDe(r)); return; }
  if (r.status !== 202 || !r.json.ok) { aviso.erro(mensagemDe(r)); return; }
  formSolicitar.hidden = true;
  solicitado.hidden = false;
});

formAplicar.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  const senha = document.getElementById('senha').value;
  if (!senha) return;
  const bt = document.getElementById('aplicar');
  bt.disabled = true;
  const r = await enviar('/api/senha/redefinir/aplicar', { token, senha });
  bt.disabled = false;
  if (r.status !== 200 || !r.json.ok) {
    if (r.status === 410) { aviso.erro(mensagemMotivo(r.json)); formAplicar.hidden = true; return; }
    aviso.erro(mensagemDe(r));
    return;
  }
  formAplicar.hidden = true;
  concluido.hidden = false;
});

await iniciar();
document.body.dataset.pronto = '1';
