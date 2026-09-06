/* plat — layout comum: barra lateral (marca, inquilino, navegação por privilégio, pessoa, sair) + área principal.
   montarLayout({usuario, ativo}) preenche <aside id="lateral"> e marca body.com-lateral. Links só aparecem com o
   privilégio correspondente (ADR 0002 seção 15); Grupos e Minha conta sempre. */
import { h, limpar } from './dom.js';
import { t } from './i18n.js';
import { tem } from './estado.js';
import { sair } from '../auth/sessao.js';

export const TELAS = [
  { caminho: '/', chave: 'nav.inicio' },
  { caminho: '/conteudo', chave: 'nav.conteudo' },
  { caminho: '/mapa', chave: 'nav.mapa' },
  { caminho: '/acervo', chave: 'nav.acervo' },
  { caminho: '/conexoes', chave: 'nav.conexoes' },
  { caminho: '/uploads', chave: 'nav.uploads', privilegio: 'conteudo.criar' },
  { caminho: '/conta', chave: 'nav.conta' },
  { caminho: '/admin/usuarios', chave: 'nav.usuarios', privilegio: 'membros.ver' },
  { caminho: '/admin/grupos', chave: 'nav.grupos' },
  { caminho: '/tarefas', chave: 'nav.tarefas', privilegio: 'jobs.executar' },
  { caminho: '/admin/papeis', chave: 'nav.papeis', privilegio: 'papeis.gerir' },
  { caminho: '/admin/tokens', chave: 'nav.tokens', privilegio: 'tokens.gerar' },
  { caminho: '/admin/log', chave: 'nav.log', privilegio: 'org.log_ver' },
  { caminho: '/admin/organizacao', chave: 'nav.organizacao', privilegio: 'org.configurar' },
];

export function telasVisiveis(usuario) {
  return TELAS.filter((tela) => !tela.privilegio || tem(tela.privilegio, usuario));
}

export function montarLayout({ usuario, ativo = location.pathname }) {
  const aside = document.getElementById('lateral');
  if (!aside) return;
  limpar(aside);
  document.body.classList.add('com-lateral');
  const inq = usuario.inquilino || {};
  aside.append(h('div', { class: 'marca' }, h('strong', {}, t('app.nome')), h('span', { title: inq.slug }, inq.nome || inq.slug || '')));
  const ul = h('ul');
  for (const tela of telasVisiveis(usuario)) {
    const a = h('a', { href: tela.caminho, 'aria-current': tela.caminho === ativo ? 'page' : undefined }, t(tela.chave));
    ul.append(h('li', {}, a));
  }
  aside.append(h('nav', { 'aria-label': t('nav.rotulo') }, ul));
  const btSair = h('button', { type: 'button', class: 'pequeno', id: 'sair' }, t('nav.sair'));
  btSair.addEventListener('click', () => sair());
  /* item L0-02-g-perfil-usuario: "ver a foto na barra" — a mesma foto de /conta; sem foto, sem <img> nenhum
     (nunca um ícone genérico fingindo ser a foto de alguém) */
  const foto = usuario.foto_url
    ? h('img', { class: 'foto-perfil', src: usuario.foto_url, alt: '', width: 32, height: 32, id: 'pessoa-foto' })
    : null;
  aside.append(h('div', { class: 'pessoa' },
    h('div', { class: 'pessoa-topo' },
      foto,
      h('a', { href: '/conta', id: 'pessoa-nome' }, usuario.nome || usuario.login, h('small', {}, `${usuario.login} · ${t(`perfil.${usuario.perfil}`)}`))),
    btSair));
}

/* cabeçalho da tela: h1 com contagem opcional + área de botões à direita */
export function cabecalho(titulo, { contagem, botoes = [] } = {}) {
  const h1 = document.querySelector('main > h1');
  if (h1) { h1.textContent = titulo; if (contagem !== undefined) h1.append(h('span', { class: 'contagem' }, `(${contagem})`)); }
  document.title = `${titulo} · ${t('app.nome')}`;
  const barra = document.getElementById('ferramentas');
  if (barra && botoes.length) { const dir = h('div', { class: 'direita' }, ...botoes); barra.append(dir); }
  return h1;
}

export function pronto() { document.body.dataset.pronto = '1'; }
