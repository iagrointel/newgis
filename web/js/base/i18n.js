/* plat — i18n mínimo: chaves em web/js/i18n/<idioma>.json; pt-BR é o padrão; o L7-10 acrescenta idiomas.
   t(chave, params) substitui {nome}; chave ausente devolve a própria chave (visível no e2e, sem ruído no console).
   aplicar(raiz) troca o texto de todo [data-i18n] e o aria-label de [data-i18n-aria]. */

let dicionario = {};
let idioma = 'pt-BR';

export async function carregar(id) {
  idioma = id || document.documentElement.lang || 'pt-BR';
  const resp = await fetch(`/static/js/i18n/${idioma}.json`, { cache: 'no-store', credentials: 'same-origin' });
  dicionario = resp.ok ? await resp.json() : {};
  aplicar(document);
  return dicionario;
}

export function t(chave, params = {}) {
  const s = dicionario[chave];
  if (s === undefined) return chave;
  return s.replace(/\{(\w+)\}/g, (_, k) => (params[k] === undefined ? `{${k}}` : String(params[k])));
}

export function aplicar(raiz) {
  raiz.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  raiz.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  raiz.querySelectorAll('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}

export function idiomaAtual() { return idioma; }

const fmtDataHora = () => new Intl.DateTimeFormat(idioma, { dateStyle: 'short', timeStyle: 'short' });
const fmtData = () => new Intl.DateTimeFormat(idioma, { dateStyle: 'short' });

export function formatarData(iso, soData = false) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return (soData ? fmtData() : fmtDataHora()).format(d);
}

export function formatarNumero(n) {
  if (n === null || n === undefined || n === '') return '';
  return new Intl.NumberFormat(idioma).format(n);
}

/* dias inteiros até a data (negativo = passado) */
export function diasAte(iso) {
  if (!iso) return null;
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);
}
