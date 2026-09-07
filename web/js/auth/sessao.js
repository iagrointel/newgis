/* plat — sessão nas telas (ADR 0002 seção 15). exigirSessao({privilegio}) chama GET /api/eu:
   401 -> /entrar?inquilino=<localStorage plat_inquilino>&proximo=<caminho atual>; pendência -> /conta#senha | /conta#2fa;
   privilégio ausente -> tela "sem permissão" (não redireciona). Devolve o usuário ou null. sair() = POST /api/logout + /entrar. */
import { chamar, obter, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { loja, tem } from '../base/estado.js';
import { t } from '../base/i18n.js';

export const CHAVE_INQUILINO = 'plat_inquilino';
export const CHAVE_SESSAO = 'plat_sessao';

function guardar(chave, valor) { try { localStorage.setItem(chave, valor); } catch { /* armazenamento indisponível: segue sem lembrar */ } }
function ler(chave) { try { return localStorage.getItem(chave); } catch { return null; } }
function esquecer(chave) { try { localStorage.removeItem(chave); } catch { /* idem */ } }

export function lembrarInquilino(slug) { if (slug) guardar(CHAVE_INQUILINO, slug); }
export function inquilinoLembrado() { return ler(CHAVE_INQUILINO) || ''; }
export function marcarSessao(ativa) { if (ativa) guardar(CHAVE_SESSAO, '1'); else esquecer(CHAVE_SESSAO); }
export function sessaoProvavel() { return ler(CHAVE_SESSAO) === '1'; }

export function urlLogin(proximo = location.pathname + location.search) {
  const p = new URLSearchParams();
  /* item L7-03-e: sem o inquilino na URL, a tela de login perde de quem é a organização — e, quando a página
     está EMBUTIDA no sítio do cliente, o frame-ancestors da resposta seguinte já não conhece o inquilino e o
     navegador recusa o quadro no meio do caminho. O localStorage vem primeiro; a URL atual é a rede de baixo. */
  const slug = inquilinoLembrado() || new URLSearchParams(location.search).get('inquilino') || '';
  if (slug) p.set('inquilino', slug);
  if (proximo && proximo !== '/entrar') p.set('proximo', proximo);
  const q = p.toString();
  return `/entrar${q ? `?${q}` : ''}`;
}

export function irParaLogin() { marcarSessao(false); location.replace(urlLogin()); }

export function caminhoPendencia(pendencias) {
  if (!Array.isArray(pendencias) || !pendencias.length) return null;
  return pendencias.includes('trocar_senha') ? '/conta#senha' : '/conta#2fa';
}

function principal() { return document.getElementById('principal') || document.querySelector('main'); }

export function mostrarFalha(resp) {
  const m = principal();
  if (!m) return;
  limpar(m);
  m.append(h('h1', {}, t('erro.carregar_titulo')),
    h('plat-aviso', { 'data-tipo': 'erro', role: 'alert' }, `${t('erro.carregar')} (${resp.status}): ${mensagemDe(resp)}`),
    h('p', {}, h('a', { href: location.pathname + location.search }, t('erro.tentar_de_novo'))));
}

export function semPermissao(privilegio) {
  const m = principal();
  if (!m) return;
  limpar(m);
  m.classList.add('sem-permissao');
  m.append(h('h1', {}, t('erro.sem_permissao_titulo')),
    h('plat-aviso', { 'data-tipo': 'atencao', role: 'alert' }, t('erro.sem_permissao', { privilegio })),
    h('p', {}, h('a', { href: '/' }, t('nav.inicio'))));
}

export async function exigirSessao({ privilegio, permitirPendencia = false } = {}) {
  const r = await obter('/api/eu');
  if (r.status === 401) { irParaLogin(); return null; }
  if (r.status !== 200) { mostrarFalha(r); return null; }
  const usuario = r.json;
  marcarSessao(true);
  if (usuario.inquilino?.slug) lembrarInquilino(usuario.inquilino.slug);
  loja.definir({ usuario });
  const destino = caminhoPendencia(usuario.pendencias);
  if (destino && !permitirPendencia) { location.replace(destino); return null; }
  if (privilegio && !tem(privilegio, usuario)) { semPermissao(privilegio); return null; }
  return usuario;
}

export async function sair() {
  await chamar('POST', '/api/logout', {});
  marcarSessao(false);
  loja.definir({ usuario: null });
  location.href = urlLogin('/');
}

export { tem };
