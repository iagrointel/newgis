/* plat — tela pública /aceitar-convite (item L0-07-d-smtp-convites): GET /api/convites/resolver (mostra
   inquilino/e-mail/perfil sem exigir nada) e POST /api/convites/aceitar. O e-mail exibido vem SEMPRE do que
   o servidor resolveu a partir do token — a URL só carrega o token, nunca o e-mail (fecha por construção a
   refutação "altera o e-mail no link"). Sem sessão: página acessível a qualquer um com o link. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import '../base/componentes.js';
import { carregar, t } from '../base/i18n.js';

await carregar();

const params = new URLSearchParams(location.search);
const token = params.get('token') || '';
const aviso = document.getElementById('aviso');
const info = document.getElementById('convite-info');
const form = document.getElementById('form-aceitar');
const concluido = document.getElementById('concluido');

function mensagemMotivo(json) {
  const motivo = json?.detalhe?.motivo;
  return t({
    usado: 'aceitar_convite.usado',
    cancelado: 'aceitar_convite.usado',
    expirado: 'aceitar_convite.expirado',
    invalido: 'aceitar_convite.invalido',
    inquilino_suspenso: 'aceitar_convite.invalido',
  }[motivo] || 'aceitar_convite.invalido');
}

async function iniciar() {
  if (!token) { aviso.erro(t('aceitar_convite.sem_token')); return; }
  const r = await obter(`/api/convites/resolver?token=${encodeURIComponent(token)}`);
  if (r.status !== 200) { aviso.erro(mensagemMotivo(r.json)); return; }
  document.getElementById('convite-tenant').textContent = r.json.tenant_nome;
  document.getElementById('convite-email').textContent = r.json.email;
  info.hidden = false;
  form.hidden = false;
  document.getElementById('login').value = (r.json.email.split('@')[0] || '').toLowerCase().replace(/[^a-z0-9._-]/g, '');
  document.getElementById('login').focus();
}

document.getElementById('mostrar-senha').addEventListener('click', (e) => {
  const senha = document.getElementById('senha');
  const ver = senha.type === 'password';
  senha.type = ver ? 'text' : 'password';
  e.currentTarget.setAttribute('aria-pressed', String(ver));
  e.currentTarget.textContent = ver ? t('form.ocultar') : t('form.mostrar');
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  const login = document.getElementById('login').value.trim();
  const nome = document.getElementById('nome').value.trim();
  const senha = document.getElementById('senha').value;
  if (!login || !nome || !senha) { aviso.erro(t('login.preencha')); return; }
  const bt = document.getElementById('aceitar');
  bt.disabled = true;
  const r = await enviar('/api/convites/aceitar', { token, login, nome, senha });
  bt.disabled = false;
  if (r.status !== 200 || !r.json.ok) {
    if (r.status === 410) { aviso.erro(mensagemMotivo(r.json)); form.hidden = true; info.hidden = true; return; }
    aviso.erro(mensagemDe(r));
    return;
  }
  form.hidden = true;
  info.hidden = true;
  concluido.hidden = false;
  document.getElementById('link-entrar').href = `/entrar?inquilino=${encodeURIComponent(r.json.tenant_slug)}&proximo=%2Fconta`;
});

await iniciar();
document.body.dataset.pronto = '1';
