/* plat — núcleo compartilhado pelas telas: leitura de JSON da API e utilidades de DOM. Toda leitura fica
   registrada para a RÉGUA (web/js/base/api.js registrarChamada; item L0-14). */
import { registrarChamada } from './base/api.js';

export async function obterJSON(url, opcoes = {}) {
  const t0 = performance.now();
  const resp = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...opcoes });
  registrarChamada((opcoes.method || 'GET').toUpperCase(), url, resp.status, performance.now() - t0, resp.headers.get('Date'));
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
