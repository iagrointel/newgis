/* plat — layout comum: barra lateral (marca, inquilino, navegação por privilégio com ícone da família única,
   pessoa, tema, sair) + área principal com a RÉGUA da tela no rodapé (item L0-14). montarLayout({usuario, ativo})
   preenche <aside id="lateral"> e marca body.com-lateral. Links só aparecem com o privilégio correspondente
   (ADR 0002 seção 15); Grupos e Minha conta sempre. */
import { h, limpar } from './dom.js';
import { t } from './i18n.js';
import { tem } from './estado.js';
import { icone } from './icones.js';
import { regua, reguaTela } from './regua.js';
import { sair } from '../auth/sessao.js';

export const TELAS = [
  { caminho: '/', chave: 'nav.inicio', icone: 'inicio' },
  { caminho: '/conteudo', chave: 'nav.conteudo', icone: 'camada' },
  { caminho: '/mapa', chave: 'nav.mapa', icone: 'mapa' },
  { caminho: '/conexoes', chave: 'nav.conexoes', icone: 'conexao' },
  { caminho: '/uploads', chave: 'nav.uploads', privilegio: 'conteudo.criar', icone: 'enviar' },
  { caminho: '/conta', chave: 'nav.conta', icone: 'usuario' },
  { caminho: '/admin/usuarios', chave: 'nav.usuarios', privilegio: 'membros.ver', icone: 'usuarios' },
  { caminho: '/admin/grupos', chave: 'nav.grupos', icone: 'grupo' },
  { caminho: '/tarefas', chave: 'nav.tarefas', privilegio: 'jobs.executar', icone: 'tarefas' },
  { caminho: '/admin/papeis', chave: 'nav.papeis', privilegio: 'papeis.gerir', icone: 'papel' },
  { caminho: '/admin/tokens', chave: 'nav.tokens', privilegio: 'tokens.gerar', icone: 'chave' },
  { caminho: '/admin/log', chave: 'nav.log', privilegio: 'org.log_ver', icone: 'log' },
  { caminho: '/admin/organizacao', chave: 'nav.organizacao', privilegio: 'org.configurar', icone: 'organizacao' },
  { caminho: '/estilo', chave: 'nav.estilo', icone: 'paleta' },
];

export function telasVisiveis(usuario) {
  return TELAS.filter((tela) => !tela.privilegio || tem(tela.privilegio, usuario));
}

/* seletor de tema (sistema · claro · escuro) — botões reais, gravam em localStorage via window.platTema
   (web/js/base/tema.js, script clássico carregado no <head>). Sem o script (tela sem tema.js) não monta. */
export function seletorTema() {
  const pt = window.platTema;
  if (!pt) return null;
  const grupo = h('div', { class: 'seletor-tema', role: 'group', 'aria-label': t('tema.rotulo') });
  const opcoes = [['sistema', 'sistema', 'tema.sistema'], ['claro', 'sol', 'tema.claro'], ['escuro', 'lua', 'tema.escuro']];
  const atualizar = () => { for (const b of grupo.children) b.setAttribute('aria-pressed', String(b.dataset.tema === pt.temaAtual())); };
  for (const [tema, ic, chave] of opcoes) {
    const b = h('button', { type: 'button', dataset: { tema }, 'aria-label': t(chave), title: t(chave), 'aria-pressed': 'false' }, icone(ic, { tamanho: 14 }));
    b.addEventListener('click', () => { pt.definirTema(tema); atualizar(); });
    grupo.append(b);
  }
  atualizar();
  return grupo;
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
    const a = h('a', { href: tela.caminho, 'aria-current': tela.caminho === ativo ? 'page' : undefined }, icone(tela.icone, { tamanho: 16 }), t(tela.chave));
    ul.append(h('li', {}, a));
  }
  aside.append(h('nav', { 'aria-label': t('nav.rotulo') }, ul));
  const btSair = h('button', { type: 'button', class: 'pequeno', id: 'sair' }, icone('sair', { tamanho: 14 }), t('nav.sair'));
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
    h('div', { class: 'pessoa-acoes' }, seletorTema(), btSair)));
  /* RÉGUA da tela: rodapé com as últimas chamadas à API (rota, status, hora, ms) */
  reguaTela(document.getElementById('principal') || document.querySelector('main'));
}

/* cabeçalho da tela: h1 com contagem opcional (como RÉGUA: leva a procedência da chamada que a produziu)
   + área de botões à direita */
export function cabecalho(titulo, { contagem, botoes = [], origem } = {}) {
  const h1 = document.querySelector('main > h1');
  if (h1) {
    h1.textContent = titulo;
    if (contagem !== undefined) h1.append(regua(`(${contagem})`, { classe: 'contagem', ...(origem ? { origem } : {}) }));
  }
  document.title = `${titulo} · ${t('app.nome')}`;
  const barra = document.getElementById('ferramentas');
  if (barra && botoes.length) { const dir = h('div', { class: 'direita' }, ...botoes); barra.append(dir); }
  return h1;
}

export function pronto() { document.body.dataset.pronto = '1'; }
