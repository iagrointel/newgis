/* plat · catálogo — página pública /p/<inquilino>/<slug> (item L5-14-publicacao-links-embed): busca
   GET /api/p/<inquilino>/<slug>[?link=<token>] e renderiza o documento publicado (título, grafo de nós,
   camadas citadas). Página vanilla de propósito: serve dentro de <iframe> em domínio externo (a lista de
   domínios do app decide, via cabeçalho Content-Security-Policy: frame-ancestors, se o navegador deixa
   carregar) e não depende da casca autenticada do produto (sem sessão, sem barra lateral, sem i18n). */

function texto(v) {
  return String(v == null ? '' : v);
}

function el(tag, attrs, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null) continue;
    if (k === 'texto') n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const f of filhos) if (f != null) n.append(f);
  return n;
}

function caminho() {
  const m = /^\/p\/([^/]+)\/([^/]+)\/?$/.exec(location.pathname);
  return m ? { inquilino: decodeURIComponent(m[1]), slug: decodeURIComponent(m[2]) } : null;
}

async function principal() {
  const raiz = document.getElementById('conteudo');
  const p = caminho();
  if (!p) {
    raiz.append(el('div', { class: 'erro' }, el('p', { texto: 'endereço de publicação inválido' })));
    return;
  }
  const params = new URLSearchParams(location.search);
  const link = params.get('link');
  const url = `/api/p/${encodeURIComponent(p.inquilino)}/${encodeURIComponent(p.slug)}${link ? `?link=${encodeURIComponent(link)}` : ''}`;
  let r;
  let resp;
  try {
    resp = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch {
    raiz.append(el('div', { class: 'erro' }, el('p', { texto: 'não foi possível carregar o aplicativo publicado' })));
    return;
  }
  if (!resp.ok) {
    let corpo = {};
    try { corpo = await resp.json(); } catch { /* corpo sem json: mantém {} */ }
    raiz.append(
      el(
        'div',
        { class: 'erro' },
        el('p', { texto: `${resp.status} · ${texto(corpo.mensagem || corpo.erro || 'aplicativo inexistente ou sem acesso')}` })
      )
    );
    return;
  }
  r = await resp.json();
  document.title = `${texto(r.titulo)} · plat`;
  const nos = (r.corpo && r.corpo.corpo && Array.isArray(r.corpo.corpo.nos)) ? r.corpo.corpo.nos : [];
  raiz.append(
    el('h1', { texto: r.titulo || '(sem título)' }),
    r.resumo ? el('p', { texto: r.resumo }) : null,
    el('p', { texto: `versão publicada: ${r.versao_publicada}` }),
    el(
      'section',
      {},
      el('h2', { texto: `nós do aplicativo (${nos.length})` }),
      el(
        'ul',
        {},
        ...(nos.length
          ? nos.map((n) => el('li', {}, el('code', { texto: texto(n.tipo) }), document.createTextNode(` · ${texto(n.id)}`)))
          : [el('li', { texto: '(nenhum)' })])
      )
    )
  );
  raiz.dataset.carregado = '1'; // marcador para o e2e: conteúdo real chegou (não é o esqueleto inicial)
}

principal();
