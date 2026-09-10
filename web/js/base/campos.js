/* plat — campos de formulário escrito à mão (entrar, aceitar convite, redefinir senha; UX-02). O mesmo contrato do
   <plat-formulario>: erro por campo com aria-invalid + <span class="erro-campo" role="alert"> ligado por
   aria-describedby, para um campo inválido nunca sumir sem mensagem (refutação do item). Também: validação de
   obrigatórios com foco no primeiro inválido, botão ocupado (disabled + aria-busy + rótulo), aviso de Caps Lock em
   campo de senha e o botão mostrar/ocultar senha. */
import { h } from './dom.js';
import { t } from './i18n.js';

export function erroCampo(input, texto) {
  const wrap = input.closest('.campo') || input.parentElement;
  const id = `${input.id || input.name}-erro`;
  let el = wrap.querySelector('.erro-campo');
  if (!el) { el = h('span', { class: 'erro-campo', id, role: 'alert' }); wrap.append(el); }
  el.textContent = texto;
  input.setAttribute('aria-invalid', 'true');
  const desc = (input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
  if (!desc.includes(id)) desc.push(id);
  input.setAttribute('aria-describedby', desc.join(' '));
}

export function limparErros(raiz) {
  raiz.querySelectorAll('.erro-campo').forEach((el) => {
    const input = raiz.querySelector(`[aria-describedby~="${el.id}"]`);
    if (input) {
      const desc = (input.getAttribute('aria-describedby') || '').split(' ').filter((d) => d && d !== el.id);
      if (desc.length) input.setAttribute('aria-describedby', desc.join(' ')); else input.removeAttribute('aria-describedby');
    }
    el.remove();
  });
  raiz.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
}

/* pares [[input, mensagem, (valor) => ok?]]: marca cada inválido, foca o primeiro; devolve true se tudo passou */
export function validar(pares) {
  let primeiro = null;
  for (const [input, mensagem, teste] of pares) {
    const v = input.type === 'password' ? input.value : input.value.trim();
    const ok = teste ? teste(v) : v !== '';
    if (ok) continue;
    erroCampo(input, mensagem);
    primeiro = primeiro || input;
  }
  if (primeiro) primeiro.focus();
  return !primeiro;
}

/* botão de envio ocupado: disabled + aria-busy + rótulo alternativo; ocupado(bt, false) restaura o rótulo original */
export function ocupado(botao, sim, rotulo) {
  if (sim) {
    botao.dataset.rotulo = botao.dataset.rotulo || botao.textContent;
    botao.disabled = true;
    botao.setAttribute('aria-busy', 'true');
    if (rotulo) botao.textContent = rotulo;
  } else {
    botao.disabled = false;
    botao.removeAttribute('aria-busy');
    if (botao.dataset.rotulo) botao.textContent = botao.dataset.rotulo;
  }
}

/* aviso de Caps Lock: aparece enquanto a tecla estiver ligada e o campo com foco (não é erro, é atenção) */
export function avisarCapsLock(input) {
  const wrap = input.closest('.campo') || input.parentElement;
  const aviso = h('span', { class: 'aviso-caps', role: 'status', hidden: true }, t('login.caps_lock'));
  wrap.append(aviso);
  const conferir = (e) => { aviso.hidden = !(e.getModifierState && e.getModifierState('CapsLock')); };
  input.addEventListener('keydown', conferir);
  input.addEventListener('keyup', conferir);
  input.addEventListener('blur', () => { aviso.hidden = true; });
}

/* botão mostrar/ocultar senha (aria-pressed + aria-controls); o rótulo segue o idioma */
export function ligarMostrarSenha(botao, input) {
  botao.addEventListener('click', () => {
    const ver = input.type === 'password';
    input.type = ver ? 'text' : 'password';
    botao.setAttribute('aria-pressed', String(ver));
    botao.textContent = ver ? t('form.ocultar') : t('form.mostrar');
    input.focus();
  });
}

/* 422 do servidor com detalhe do pydantic ([{loc, msg}]): põe cada mensagem no campo certo; devolve o que sobrou */
export function errosDoServidor(resp, campos) {
  const det = resp && resp.json && resp.json.detalhe;
  const sobra = [];
  if (!Array.isArray(det)) return null;
  for (const d of det) {
    const nome = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : '';
    if (campos[nome]) erroCampo(campos[nome], d.msg || t('form.obrigatorio')); else sobra.push(d.msg);
  }
  return sobra;
}
