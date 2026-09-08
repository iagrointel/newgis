/* plat — tela pública /redefinir-senha (item L0-07-d-smtp-convites; polimento UX-02): sem ?token=, formulário de
   SOLICITAR (inquilino + e-mail; resposta sempre genérica, nunca revela se o e-mail existe); com ?token=, formulário de
   TROCAR a senha (GET /api/senha/redefinir/resolver valida antes de mostrar o campo; POST .../aplicar troca).
   Estados: link inválido/expirado como <plat-estado> com ação "pedir um novo link"; erro por campo (e-mail inválido,
   senha recusada pela política vai para o campo com a mensagem do servidor); botão ocupado; sucesso nomeado. */
import { enviar, mensagemDe, obter } from '../base/api.js';
import '../base/componentes.js';
import { avisarCapsLock, erroCampo, errosDoServidor, ligarMostrarSenha, limparErros, ocupado, validar } from '../base/campos.js';
import { carregar, t } from '../base/i18n.js';

await carregar();

const params = new URLSearchParams(location.search);
const token = params.get('token') || '';
const el = (id) => document.getElementById(id);
const aviso = el('aviso');
const estado = el('estado');
const formSolicitar = el('form-solicitar');
const solicitado = el('solicitado');
const formAplicar = el('form-aplicar');
const concluido = el('concluido');
const inputInquilino = el('inquilino');
const inputEmail = el('email');
const inputSenha = el('senha');
const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function linkInvalido(json) {
  formAplicar.hidden = true;
  const chave = json?.detalhe?.motivo === 'expirado' ? 'redefinir_senha.expirado' : 'redefinir_senha.invalido';
  estado.mostrar({ tipo: 'erro', titulo: t(chave), acoes: [{ id: 'novo', rotulo: t('redefinir_senha.pedir_novo'), classe: 'primario' }], ref: json?.req_id });
}
estado.addEventListener('acao', (e) => {
  if (e.detail.id === 'novo') { location.href = '/redefinir-senha'; return; }
  iniciar();
});

async function iniciar() {
  if (!token) { formSolicitar.hidden = false; inputInquilino.focus(); return; }
  estado.carregando();
  const r = await obter(`/api/senha/redefinir/resolver?token=${encodeURIComponent(token)}`);
  if (r.status === 0 || r.status >= 500) { estado.erro(r, [{ id: 'tentar', rotulo: t('login.tentar_de_novo'), classe: 'primario' }]); return; }
  if (r.status !== 200) { linkInvalido(r.json); return; }
  estado.limpar();
  formAplicar.hidden = false;
  inputSenha.focus();
}

ligarMostrarSenha(el('mostrar-senha'), inputSenha);
avisarCapsLock(inputSenha);

formSolicitar.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  limparErros(formSolicitar);
  const ok = validar([
    [inputInquilino, t('redefinir_senha.inquilino_obrigatorio')],
    [inputEmail, inputEmail.value.trim() ? t('campo.email_invalido') : t('redefinir_senha.email_obrigatorio'), (v) => RE_EMAIL.test(v)],
  ]);
  if (!ok) return;
  const bt = el('solicitar');
  ocupado(bt, true, t('redefinir_senha.enviando'));
  formSolicitar.setAttribute('aria-busy', 'true');
  const r = await enviar('/api/senha/redefinir/solicitar', { inquilino: inputInquilino.value.trim(), email: inputEmail.value.trim() });
  formSolicitar.removeAttribute('aria-busy');
  ocupado(bt, false);
  if (r.status === 202 && r.json.ok) { formSolicitar.hidden = true; solicitado.hidden = false; solicitado.querySelector('plat-aviso').focus?.(); return; }
  if (r.status === 422 && errosDoServidor(r, { inquilino: inputInquilino, email: inputEmail })) { formSolicitar.querySelector('[aria-invalid]')?.focus(); return; }
  aviso.erro(r.status === 0 ? t('login.sem_servidor') : mensagemDe(r));
});

formAplicar.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  limparErros(formAplicar);
  if (!validar([[inputSenha, inputSenha.value ? t('senha.curta', { n: 8 }) : t('senha.obrigatoria'), (v) => v.length >= 8]])) return;
  const bt = el('aplicar');
  ocupado(bt, true, t('redefinir_senha.trocando'));
  formAplicar.setAttribute('aria-busy', 'true');
  const r = await enviar('/api/senha/redefinir/aplicar', { token, senha: inputSenha.value });
  formAplicar.removeAttribute('aria-busy');
  ocupado(bt, false);
  if (r.status === 200 && r.json.ok) { formAplicar.hidden = true; concluido.hidden = false; concluido.querySelector('a').focus(); return; }
  if (r.status === 410) { linkInvalido(r.json); return; }
  if (r.json?.erro === 'senha_fraca') { erroCampo(inputSenha, mensagemDe(r)); inputSenha.focus(); return; }
  if (r.status === 422 && errosDoServidor(r, { senha: inputSenha })) { inputSenha.focus(); return; }
  aviso.erro(r.status === 0 ? t('login.sem_servidor') : mensagemDe(r));
});

await iniciar();
document.body.dataset.pronto = '1';
