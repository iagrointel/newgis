/* plat — tela pública /aceitar-convite (item L0-07-d-smtp-convites; polimento UX-02): GET /api/convites/resolver
   (mostra inquilino/e-mail/perfil/validade sem exigir nada) e POST /api/convites/aceitar. O e-mail exibido vem SEMPRE
   do que o servidor resolveu a partir do token — a URL só carrega o token, nunca o e-mail. Sem sessão.
   Estados: convite inválido/usado/expirado como <plat-estado> (título nomeado, sem formulário); erro por campo (login
   fora do padrão, nome vazio, senha recusada pela política vai para o campo senha com a mensagem do servidor); botão
   ocupado; sucesso com o link de entrada já apontando para o inquilino. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import '../base/componentes.js';
import { avisarCapsLock, erroCampo, errosDoServidor, ligarMostrarSenha, limparErros, ocupado, validar } from '../base/campos.js';
import { carregar, formatarData, t } from '../base/i18n.js';

await carregar();

const params = new URLSearchParams(location.search);
const token = params.get('token') || '';
const el = (id) => document.getElementById(id);
const aviso = el('aviso');
const estado = el('estado');
const info = el('convite-info');
const form = el('form-aceitar');
const concluido = el('concluido');
const inputLogin = el('login');
const inputNome = el('nome');
const inputSenha = el('senha');
const RE_LOGIN = /^[a-z0-9][a-z0-9._@-]*$/;
let resolvido = null;

function chaveMotivo(json) {
  const motivo = json?.detalhe?.motivo;
  return {
    usado: 'aceitar_convite.usado',
    cancelado: 'aceitar_convite.usado',
    expirado: 'aceitar_convite.expirado',
  }[motivo] || 'aceitar_convite.invalido';
}

function conviteInvalido(json) {
  form.hidden = true;
  info.hidden = true;
  estado.mostrar({ tipo: 'erro', titulo: t(chaveMotivo(json)), texto: t('aceitar_convite.pedir_novo'), ref: json?.req_id });
}

function mostrarInfo() {
  el('convite-tenant').textContent = resolvido.tenant_nome;
  el('convite-email').textContent = resolvido.email;
  el('convite-perfil').textContent = resolvido.perfil ? t('aceitar_convite.perfil', { perfil: t(`perfil.${resolvido.perfil}`) }) : '';
  el('convite-expira').textContent = resolvido.expira_em ? t('aceitar_convite.expira', { quando: formatarData(resolvido.expira_em) }) : '';
  info.hidden = false;
}

async function iniciar() {
  if (!token) { estado.mostrar({ tipo: 'erro', titulo: t('aceitar_convite.sem_token'), texto: t('aceitar_convite.pedir_novo') }); return; }
  estado.carregando();
  const r = await obter(`/api/convites/resolver?token=${encodeURIComponent(token)}`);
  if (r.status === 0 || r.status >= 500) { estado.erro(r, [{ id: 'tentar', rotulo: t('login.tentar_de_novo'), classe: 'primario' }]); return; }
  if (r.status !== 200) { conviteInvalido(r.json); return; }
  estado.limpar();
  resolvido = r.json;
  mostrarInfo();
  form.hidden = false;
  inputLogin.value = (resolvido.email.split('@')[0] || '').toLowerCase().replace(/[^a-z0-9._-]/g, '');
  inputLogin.focus();
}
estado.addEventListener('acao', () => iniciar());

ligarMostrarSenha(el('mostrar-senha'), inputSenha);
avisarCapsLock(inputSenha);

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  limparErros(form);
  const ok = validar([
    [inputLogin, inputLogin.value.trim() ? t('aceitar_convite.login_invalido') : t('login.usuario_obrigatorio'), (v) => RE_LOGIN.test(v)],
    [inputNome, t('aceitar_convite.nome_obrigatorio')],
    [inputSenha, inputSenha.value ? t('senha.curta', { n: 8 }) : t('senha.obrigatoria'), (v) => v.length >= 8],
  ]);
  if (!ok) return;
  const bt = el('aceitar');
  ocupado(bt, true, t('aceitar_convite.criando'));
  form.setAttribute('aria-busy', 'true');
  const r = await enviar('/api/convites/aceitar', { token, login: inputLogin.value.trim(), nome: inputNome.value.trim(), senha: inputSenha.value });
  form.removeAttribute('aria-busy');
  ocupado(bt, false);
  if (r.status === 200 && r.json.ok) {
    form.hidden = true;
    info.hidden = true;
    concluido.hidden = false;
    el('link-entrar').href = `/entrar?inquilino=${encodeURIComponent(r.json.tenant_slug)}&proximo=%2Fconta`;
    el('link-entrar').focus();
    return;
  }
  if (r.status === 410) { conviteInvalido(r.json); return; }
  const codigo = r.json?.erro;
  if (codigo === 'senha_fraca') { erroCampo(inputSenha, mensagemDe(r)); inputSenha.focus(); return; }
  if (codigo === 'login_em_uso' || codigo === 'login_invalido') { erroCampo(inputLogin, mensagemDe(r)); inputLogin.focus(); return; }
  if (r.status === 422 && errosDoServidor(r, { login: inputLogin, nome: inputNome, senha: inputSenha })) { form.querySelector('[aria-invalid]')?.focus(); return; }
  aviso.erro(mensagemDe(r));
});

document.addEventListener('plat:i18n', () => { if (resolvido) mostrarInfo(); });

await iniciar();
document.body.dataset.pronto = '1';
