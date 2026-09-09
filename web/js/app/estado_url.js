/* plat — estado de seleção e filtros na URL (item L5-07; padrão do SIG de teste interno): cada vista com filtro
   dinâmico ou seleção vira um parâmetro `v.<id>` = base64url de {f: <CQL2-JSON>, s: [ids]}. Copiar a URL e abrir
   noutro navegador reabre com o mesmo filtro e a mesma seleção (`aplicarDaUrl` antes de montar os widgets).
   Sem DOM além de `history`/`location`; funções puras testáveis em node. */

function codificar(obj) {
  const texto = JSON.stringify(obj);
  const bytes = new TextEncoder().encode(texto);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decodificar(texto) {
  const b64 = texto.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (texto.length % 4)) % 4);
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

export const PREFIXO = 'v.';
export const LIMITE_PARAMETRO = 8000;

export function estadoDasVistas(vistas) {
  const estado = {};
  for (const v of vistas.values()) {
    const f = v.filtroDinamico; const s = [...v.selecao];
    if (!f && !s.length) continue;
    estado[v.id] = { ...(f ? { f } : {}), ...(s.length ? { s } : {}) };
  }
  return estado;
}

export function paramsDoEstado(estado, base = new URLSearchParams()) {
  const p = new URLSearchParams(base);
  for (const k of [...p.keys()]) if (k.startsWith(PREFIXO)) p.delete(k);
  for (const [id, e] of Object.entries(estado)) {
    const valor = codificar(e);
    if (valor.length > LIMITE_PARAMETRO) continue; // seleção enorme não cabe na URL: fica só em memória
    p.set(PREFIXO + id, valor);
  }
  return p;
}

export function estadoDosParams(params) {
  const estado = {};
  for (const [k, v] of new URLSearchParams(params)) {
    if (!k.startsWith(PREFIXO)) continue;
    try { estado[k.slice(PREFIXO.length)] = decodificar(v); } catch { /* parâmetro corrompido: ignora */ }
  }
  return estado;
}

export function aplicarEstado(vistas, estado) {
  let aplicados = 0;
  for (const [id, e] of Object.entries(estado)) {
    const v = vistas.get(id);
    if (!v) continue;
    try {
      if (e.f) v.definirFiltro(e.f, 'url');
      if (Array.isArray(e.s)) v.definirSelecao(e.s, 'url');
      aplicados += 1;
    } catch { /* filtro inválido na URL: ignora, a vista fica como o documento manda */ }
  }
  return aplicados;
}

/* ---------------------------------------------------------------- navegador */
export function aplicarDaUrl(vistas, url = location.href) {
  return aplicarEstado(vistas, estadoDosParams(new URL(url).search));
}

export function sincronizarUrl(vistas, { substituir = true } = {}) {
  const u = new URL(location.href);
  u.search = paramsDoEstado(estadoDasVistas(vistas), u.searchParams).toString();
  if (u.href === location.href) return u.href;
  if (substituir) history.replaceState(history.state, '', u); else history.pushState(history.state, '', u);
  return u.href;
}

/* liga a sincronização: qualquer mudança de vista reescreve a URL (replaceState: sem poluir o histórico) */
export function ligarUrl(vistas) {
  let agendado = false;
  const agendar = () => {
    if (agendado) return;
    agendado = true;
    queueMicrotask(() => { agendado = false; sincronizarUrl(vistas); });
  };
  for (const v of vistas.values()) v.addEventListener('vista_mudou', agendar);
  return agendar;
}
