/* plat · narrativa — LEITOR de uma narrativa por blocos (item L5-04-a-blocos-de-conteudo): desenha, na ordem
   da lista, cada bloco do documento `narrativa` como conteúdo de verdade. Mesmo documento e mesma paleta que o
   editor de arrasto usa; aqui é a forma de leitura, usada por /executar?item=<id> (autor, com sessão) e pela
   página publicada /p/<inquilino>/<slug> (anônima, sem casca).

   Segurança (D23 e refutação "injeta HTML no texto"): texto é Markdown convertido pelo conversor mínimo da casa
   (web/js/widgets/seguro.js) e o HTML resultante passa pelo DOMPurify (base/dom.js::htmlSeguro) sem <style>,
   <form>, <input>, <button>; imagem, vídeo, áudio e botão só com URL segura (própria ou https, nunca
   javascript:/data: fora de imagem); embed sempre em <iframe sandbox> sem allow-same-origin; tabela é texto puro
   célula a célula. Nenhum HTML de documento entra por innerHTML. */
import { h, limpar, htmlSeguro } from '../base/dom.js';
import { markdownParaHtml, urlSegura, hostPermitido, sandboxDe } from '../widgets/seguro.js';
import { montarMapa } from './mapa_bloco.js';

const PROIBIR = ['style', 'form', 'input', 'button', 'textarea', 'select'];
const HOSTS_VIDEO = ['youtube.com', 'youtube-nocookie.com', 'vimeo.com'];

export function blocosDe(documento) {
  const nos = (documento && documento.corpo && Array.isArray(documento.corpo.nos)) ? documento.corpo.nos : [];
  return nos.filter((n) => !n.pai);
}

/* endereço de embed de vídeo: youtube watch/short → embed; vimeo → player */
export function urlEmbedVideo(url) {
  let u;
  try { u = new URL(url); } catch { return null; }
  if (u.protocol !== 'https:') return null;
  const host = u.hostname.replace(/^www\./, '');
  if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
    const id = u.searchParams.get('v') || (u.pathname.startsWith('/embed/') ? u.pathname.split('/')[2] : null)
      || (u.pathname.startsWith('/shorts/') ? u.pathname.split('/')[2] : null);
    return id && /^[A-Za-z0-9_-]{6,20}$/.test(id) ? `https://www.youtube-nocookie.com/embed/${id}` : null;
  }
  if (host === 'youtu.be') {
    const id = u.pathname.slice(1);
    return /^[A-Za-z0-9_-]{6,20}$/.test(id) ? `https://www.youtube-nocookie.com/embed/${id}` : null;
  }
  if (host === 'vimeo.com' || host === 'player.vimeo.com') {
    const id = u.pathname.split('/').filter(Boolean).pop();
    return id && /^\d{3,15}$/.test(id) ? `https://player.vimeo.com/video/${id}` : null;
  }
  return null;
}

export function celulasDeTabela(cabecalho, linhas) {
  const dividir = (l) => String(l).split('|').map((c) => c.trim());
  const cab = dividir(cabecalho || '');
  const corpo = String(linhas || '').split(/\r?\n/).filter((l) => l.trim()).map(dividir);
  return { cabecalho: cab, linhas: corpo.map((l) => cab.map((_, i) => l[i] ?? '')) };
}

function figura(conteudo, legenda, classe) {
  const f = h('figure', { class: `bloco-figura ${classe || ''}` }, conteudo);
  if (legenda) f.append(h('figcaption', {}, legenda));
  return f;
}

function erroBloco(no, mensagem) {
  return h('p', { class: 'bloco-erro', role: 'note', dataset: { bloco: no.id } }, mensagem);
}

/* ------------------------------------------------------------------ um desenhador por tipo */
const DESENHOS = {
  capa(no, p) {
    const cab = h('header', { class: 'bloco-capa' });
    if (p.imagem) {
      const url = urlSegura(p.imagem, { imagem: true });
      if (url) cab.append(h('img', { src: url, alt: p.alternativo || '', class: 'capa-imagem', loading: 'eager' }));
    }
    cab.append(h('h1', {}, p.titulo || ''));
    if (p.subtitulo) cab.append(h('p', { class: 'capa-subtitulo' }, p.subtitulo));
    return cab;
  },
  texto(no, p) {
    const el = h('div', { class: `bloco-texto alinhar-${p.alinhamento || 'esquerda'}` });
    el.append(htmlSeguro(markdownParaHtml(String(p.markdown || '')), { proibir: PROIBIR }));
    return el;
  },
  imagem(no, p) {
    const url = urlSegura(p.url, { imagem: true });
    if (!url) return erroBloco(no, 'imagem com endereço recusado');
    const img = h('img', { src: url, alt: p.alternativo || '', loading: 'lazy' });
    return figura(img, p.legenda, `largura-${p.largura || 'coluna'}`);
  },
  video(no, p) {
    const url = urlSegura(p.url);
    if (!url) return erroBloco(no, 'vídeo com endereço recusado');
    if (url.startsWith('/')) {
      const v = h('video', { controls: true, preload: 'metadata', src: url, 'aria-label': p.descricao || p.legenda || 'vídeo' });
      return figura(v, p.legenda, 'bloco-video');
    }
    const embed = urlEmbedVideo(url);
    if (!embed || !hostPermitido(embed, HOSTS_VIDEO)) return erroBloco(no, 'vídeo externo só do YouTube ou Vimeo');
    const iframe = h('iframe', { src: embed, title: p.descricao || p.legenda || 'vídeo', sandbox: sandboxDe(['allow-scripts', 'allow-popups', 'allow-presentation']),
      referrerpolicy: 'no-referrer', allow: 'fullscreen', loading: 'lazy', class: 'video-embed' });
    return figura(iframe, p.legenda, 'bloco-video');
  },
  audio(no, p) {
    const url = urlSegura(p.url);
    if (!url || !url.startsWith('/')) return erroBloco(no, 'áudio só de arquivo do inquilino');
    const a = h('audio', { controls: true, preload: 'metadata', src: url, 'aria-label': p.descricao || p.legenda || 'áudio' });
    const f = figura(a, p.legenda, 'bloco-audio');
    if (p.descricao) f.append(h('p', { class: 'transcricao' }, p.descricao));
    return f;
  },
  mapa(no, p, contexto) {
    const quadro = h('div', { class: 'bloco-mapa-quadro', dataset: { bloco: no.id } });
    const f = figura(quadro, p.legenda, 'bloco-mapa');
    if (p.filtro) quadro.dataset.filtro = p.filtro;
    const camadas = (p.vista && Array.isArray(p.vista.camadas)) ? p.vista.camadas : [];
    const montar = () => {
      try {
        const m = montarMapa(quadro, { vista: p.vista || null, interativo: contexto.interativo !== false, camadas });
        contexto.mapas?.set(no.id, m);
        quadro.platMapa = m;
        m.pronto.then(() => { quadro.dataset.pronto = '1'; });
      } catch (e) {
        quadro.replaceChildren(erroBloco(no, `mapa indisponível: ${e.message}`));
      }
    };
    // monta depois de o quadro estar no documento (o MapLibre mede o contêiner)
    queueMicrotask(() => (quadro.isConnected ? montar() : requestAnimationFrame(montar)));
    return f;
  },
  tabela(no, p) {
    const t = celulasDeTabela(p.cabecalho, p.linhas);
    const tabela = h('table', { class: 'bloco-tabela' },
      h('thead', {}, h('tr', {}, ...t.cabecalho.map((c) => h('th', { scope: 'col' }, c)))),
      h('tbody', {}, ...t.linhas.map((l) => h('tr', {}, ...l.map((c) => h('td', {}, c))))));
    if (p.legenda) tabela.prepend(h('caption', {}, p.legenda));
    return h('div', { class: 'bloco-tabela-rolagem' }, tabela);
  },
  botao(no, p) {
    const url = urlSegura(p.url);
    if (!url) return erroBloco(no, 'botão com endereço recusado');
    const a = h('a', { class: 'bloco-botao botao primario', href: url, rel: 'noopener noreferrer' }, p.rotulo || url);
    if (p.nova_aba !== false) a.target = '_blank';
    return h('p', { class: 'bloco-botao-linha' }, a);
  },
  separador(no, p) {
    return h('hr', { class: `bloco-separador estilo-${p.estilo || 'linha'}` });
  },
  incorporar(no, p) {
    if (!/^https:\/\//.test(String(p.url || ''))) return erroBloco(no, 'incorporar só aceita https');
    const iframe = h('iframe', {
      src: p.url, title: p.titulo || 'conteúdo incorporado', referrerpolicy: 'no-referrer', loading: 'lazy',
      sandbox: sandboxDe(p.permitir_scripts === false ? ['allow-forms', 'allow-popups'] : ['allow-scripts', 'allow-forms', 'allow-popups']),
    });
    iframe.style.height = `${p.altura || 400}px`;
    return figura(iframe, null, 'bloco-incorporar');
  },
  aplicativo(no, p, contexto) {
    if (!/^[0-9a-f-]{36}$/.test(String(p.item_id || ''))) return erroBloco(no, 'bloco de aplicativo sem item');
    const src = contexto.urlAplicativo ? contexto.urlAplicativo(p.item_id) : `/executar?item=${encodeURIComponent(p.item_id)}`;
    const iframe = h('iframe', { src, title: p.legenda || 'aplicativo da plataforma', loading: 'lazy', class: 'app-embed' });
    iframe.style.height = `${p.altura || 500}px`;
    return figura(iframe, p.legenda, 'bloco-aplicativo');
  },
};

export function desenharBloco(no, contexto = {}) {
  const f = DESENHOS[no.tipo];
  const p = no.propriedades || {};
  const el = f ? f(no, p, contexto) : erroBloco(no, `bloco de tipo desconhecido: ${no.tipo}`);
  const secao = h('section', { class: `bloco bloco-${no.tipo}`, dataset: { bloco: no.id, tipo: no.tipo } }, el);
  return secao;
}

/* monta a narrativa inteira em `raiz`; devolve {mapas: Map<id, {map, catalogo, pronto}>, blocos} */
export function montarNarrativa(raiz, documento, contexto = {}) {
  const ctx = { mapas: new Map(), ...contexto };
  limpar(raiz);
  const artigo = h('article', { class: 'narrativa', lang: 'pt-BR' });
  const blocos = blocosDe(documento);
  for (const no of blocos) artigo.append(desenharBloco(no, ctx));
  if (!blocos.length) artigo.append(h('p', { class: 'vazio' }, 'narrativa sem blocos'));
  raiz.append(artigo);
  return { mapas: ctx.mapas, blocos };
}
