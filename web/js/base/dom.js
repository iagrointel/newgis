/* plat — utilidades de DOM. h() cria elementos sem HTML em string (texto sempre por textContent);
   htmlSeguro() é a ÚNICA porta para HTML vindo de fora e passa pelo DOMPurify (L5_CONCEITO D23, obrigatório). */

export function h(tag, atributos = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(atributos || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k in el && typeof v !== 'string' && k !== 'style') el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  anexar(el, filhos);
  return el;
}

export function anexar(el, filhos) {
  for (const f of filhos.flat(Infinity)) {
    if (f === undefined || f === null || f === false) continue;
    el.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return el;
}

export function limpar(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

/* HTML de fora (SVG do QR, texto de documento) só entra por aqui. Sem DOMPurify na página = erro, nunca inserção crua. */
export function htmlSeguro(html, { svg = false, proibir = [] } = {}) {
  if (!window.DOMPurify) throw new Error('DOMPurify ausente: inclua /static/vendor/dompurify-3.4.14.js antes do módulo');
  const perfil = svg ? { USE_PROFILES: { svg: true, svgFilters: true } } : { USE_PROFILES: { html: true } };
  // `proibir`: tags a cortar além do perfil (o widget de texto tira <style>, que o perfil html deixa passar e
  // cujo @import ainda dispara um pedido de rede — item L5-01-d)
  const limpo = window.DOMPurify.sanitize(String(html), { ...perfil, FORBID_TAGS: proibir, RETURN_DOM_FRAGMENT: true });
  return limpo;
}

/* copia texto; devolve true se o navegador aceitou. Sem área de transferência (contexto sem permissão), seleciona o alvo. */
export async function copiar(texto, alvo) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    if (alvo) {
      const faixa = document.createRange();
      faixa.selectNodeContents(alvo);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(faixa);
    }
    return false;
  }
}

/* botão "Copiar" com confirmação acessível (aria-live no próprio botão) */
export function botaoCopiar(obterTexto, alvo, rotulos = { copiar: 'Copiar', copiado: 'Copiado', selecionado: 'Selecionado; use Ctrl+C' }) {
  const b = h('button', { type: 'button', class: 'pequeno', 'aria-live': 'polite' }, rotulos.copiar);
  b.addEventListener('click', async () => {
    const ok = await copiar(typeof obterTexto === 'function' ? obterTexto() : obterTexto, alvo);
    b.textContent = ok ? rotulos.copiado : rotulos.selecionado;
    setTimeout(() => { b.textContent = rotulos.copiar; }, 2500);
  });
  return b;
}

export function marcador(texto, tipo) {
  return h('span', { class: `marcador ${tipo || ''}`.trim() }, texto);
}

/* caminho de retorno seguro: só relativo, começa por / e não por // (ADR 0002 seção 15.1) */
export function caminhoSeguro(valor, padrao = '/') {
  if (typeof valor !== 'string' || !valor.startsWith('/') || valor.startsWith('//') || valor.includes('\\')) return padrao;
  return valor;
}
