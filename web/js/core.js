/* plat — núcleo compartilhado pelas telas: leitura de JSON da API e utilidades de DOM. */

export async function obterJSON(url, opcoes = {}) {
  const resp = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...opcoes });
  let json = null;
  try { json = await resp.json(); } catch { json = null; }
  return { status: resp.status, json: json ?? {} };
}

export function formatarJSON(obj) {
  return JSON.stringify(obj, null, 2);
}

export function texto(id, valor) {
  const el = document.getElementById(id);
  if (el) el.textContent = valor == null ? '' : String(valor);
}
