/* plat — i18n: chaves em web/js/i18n/<idioma>.json (pt-BR, en, es; paridade de chaves provada por
   tests/unit/test_i18n_paridade.py). t(chave, params) substitui {nome}; chave ausente no idioma cai para o pt-BR e,
   ausente nos dois, devolve a própria chave (visível no e2e, sem ruído no console). aplicar(raiz) troca o texto de
   todo [data-i18n], o aria-label de [data-i18n-aria] e o title de [data-i18n-title].

   Resolução do idioma (UX-02), do mais ao menos específico: ?idioma= na URL > localStorage plat_idioma (o seletor
   <plat-idioma> das telas públicas e a preferência da conta gravam aqui) > <html lang> quando não for o padrão >
   navigator.languages > pt-BR. A preferência gravada na conta (usuario.idioma_preferido) é aplicada por
   exigirSessao (auth/sessao.js) assim que a sessão é conhecida, e passa a valer também nas telas públicas. */

export const IDIOMAS = ['pt-BR', 'en', 'es'];
export const PADRAO = 'pt-BR';
export const CHAVE_IDIOMA = 'plat_idioma';
export const EVENTO = 'plat:i18n';

let dicionario = {};
let reserva = {};
let idioma = PADRAO;
let carregado = false;

export function normalizarIdioma(v) {
  if (!v) return null;
  const s = String(v).toLowerCase();
  if (s.startsWith('pt')) return 'pt-BR';
  if (s.startsWith('en')) return 'en';
  if (s.startsWith('es')) return 'es';
  return null;
}

function lembrado() { try { return normalizarIdioma(localStorage.getItem(CHAVE_IDIOMA)); } catch { return null; } }

export function idiomaPreferido() {
  const daUrl = normalizarIdioma(new URLSearchParams(location.search).get('idioma'));
  if (daUrl) return daUrl;
  const doArmazenamento = lembrado();
  if (doArmazenamento) return doArmazenamento;
  const doHtml = normalizarIdioma(document.documentElement.getAttribute('lang'));
  if (doHtml && doHtml !== PADRAO) return doHtml;
  for (const l of navigator.languages || [navigator.language]) {
    const n = normalizarIdioma(l);
    if (n) return n;
  }
  return PADRAO;
}

async function buscar(id) {
  const resp = await fetch(`/static/js/i18n/${id}.json`, { cache: 'no-store', credentials: 'same-origin' });
  return resp.ok ? resp.json() : {};
}

export async function carregar(id) {
  idioma = normalizarIdioma(id) || idiomaPreferido();
  const [d, r] = await Promise.all([buscar(idioma), idioma === PADRAO ? Promise.resolve(null) : buscar(PADRAO)]);
  dicionario = d;
  reserva = r || d;
  carregado = true;
  document.documentElement.lang = idioma;
  aplicar(document);
  // componentes que traduziram antes do dicionário chegar (renderizam no connectedCallback) re-traduzem por este evento
  document.dispatchEvent(new CustomEvent(EVENTO, { detail: { idioma } }));
  return dicionario;
}

/* escolha explícita (seletor ou preferência da conta): grava e recarrega; devolve o idioma efetivo */
export async function definirIdioma(id, { lembrar = true } = {}) {
  const n = normalizarIdioma(id);
  if (!n) return idioma;
  if (lembrar) { try { localStorage.setItem(CHAVE_IDIOMA, n); } catch { /* sem armazenamento: vale só nesta página */ } }
  if (n !== idioma || !carregado) await carregar(n);
  return idioma;
}

export function pronto() { return carregado; }

/* fn roda agora se o dicionário já chegou e de novo a cada carga (troca de idioma); devolve a função que cancela */
export function aoTraduzir(fn) {
  const h = () => fn();
  document.addEventListener(EVENTO, h);
  if (carregado) fn();
  return () => document.removeEventListener(EVENTO, h);
}

export function t(chave, params = {}) {
  let s = dicionario[chave];
  if (s === undefined) s = reserva[chave];
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
