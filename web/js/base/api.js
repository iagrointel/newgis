/* plat — cliente da API para todas as telas. Contrato de erro (ADR 0002 seção 14):
   {erro, mensagem, detalhe?, req_id}. Nunca guarda token; sempre credentials same-origin e no-store.
   Toda chamada devolve {status, json}; erro de rede vira status 0 com o mesmo formato. */

const MENSAGEM_PADRAO = {
  0: 'não foi possível falar com o servidor',
  400: 'pedido inválido',
  401: 'sessão ausente ou expirada',
  403: 'sem permissão',
  404: 'não encontrado',
  409: 'conflito com o estado atual',
  410: 'expirado',
  415: 'formato do pedido não aceito',
  422: 'dados inválidos',
  423: 'bloqueado',
  429: 'muitas tentativas; aguarde',
  500: 'erro no servidor',
  502: 'servidor indisponível',
  503: 'serviço indisponível',
};

export function normalizarErro(status, json, reqId) {
  const j = json && typeof json === 'object' ? json : {};
  return {
    erro: typeof j.erro === 'string' ? j.erro : `http_${status}`,
    mensagem: typeof j.mensagem === 'string' && j.mensagem ? j.mensagem : (MENSAGEM_PADRAO[status] || `erro ${status}`),
    detalhe: j.detalhe,
    req_id: j.req_id || reqId || null,
    status,
  };
}

export async function chamar(metodo, url, corpo, opcoes = {}) {
  const init = { method: metodo, credentials: 'same-origin', cache: 'no-store', headers: { ...(opcoes.headers || {}) } };
  // item L2-01-d-popup-runtime: cancelar a chamada anterior em cliques rápidos (AbortController do chamador)
  if (opcoes.signal) init.signal = opcoes.signal;
  if (metodo !== 'GET' && metodo !== 'HEAD') {
    // escrita sob cookie exige Content-Type application/json (ADR 0002 seção 5.3); DELETE vai sem corpo
    init.headers['Content-Type'] = 'application/json';
    if (corpo !== undefined && corpo !== null) init.body = JSON.stringify(corpo);
    else if (metodo !== 'DELETE') init.body = '{}';
  }
  let resp;
  try {
    resp = await fetch(url, init);
  } catch {
    return { status: 0, json: normalizarErro(0, null, null) };
  }
  let json = null;
  const tipo = resp.headers.get('content-type') || '';
  if (resp.status !== 204 && tipo.includes('json')) {
    try { json = await resp.json(); } catch { json = null; }
  }
  if (resp.status >= 400) return { status: resp.status, json: normalizarErro(resp.status, json, resp.headers.get('X-Req-Id')) };
  return { status: resp.status, json: json ?? {} };
}

export const obter = (url, opcoes) => chamar('GET', url, undefined, opcoes);
export const enviar = (url, corpo) => chamar('POST', url, corpo ?? {});
export const alterar = (url, corpo) => chamar('PUT', url, corpo ?? {});
export const apagar = (url) => chamar('DELETE', url);

/* texto de tela para uma resposta de erro: a mensagem já vem em português da API; o front só mostra.
   Em 5xx acrescenta o req_id para o usuário citar ao suporte. */
export function mensagemDe(resp) {
  const j = resp.json || {};
  let m = j.mensagem || MENSAGEM_PADRAO[resp.status] || `erro ${resp.status}`;
  if (Array.isArray(j.detalhe) && j.detalhe.length && j.detalhe.every((d) => d && typeof d === 'object' && d.msg)) {
    m += ': ' + j.detalhe.map((d) => `${(d.loc || []).slice(-1)[0] ?? ''} ${d.msg}`.trim()).join('; ');
  }
  if (resp.status >= 500 && j.req_id) m += ` (ref. ${j.req_id})`;
  return m;
}

/* monta ?a=1&b=2 ignorando vazios, null e undefined */
export function consulta(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '') continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}
