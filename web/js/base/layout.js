/* plat — layout comum: barra lateral (marca, inquilino, navegação por privilégio, pessoa, sair) + área principal.
   montarLayout({usuario, ativo}) preenche <aside id="lateral"> e marca body.com-lateral. Links só aparecem com o
   privilégio correspondente (ADR 0002 seção 15); Grupos e Minha conta sempre. */
import { h, limpar } from './dom.js';
import { t } from './i18n.js';
import { tem } from './estado.js';
import { sair } from '../auth/sessao.js';
import { icone } from './icones.js';

/* rótulo de grupo (caixa alta, --fraco) mostrado ANTES do primeiro item de cada `grupo` — só aparece quando o
   grupo muda em relação ao item anterior (telasVisiveis filtra por privilégio antes, então o rótulo nunca some
   sozinho: o grupo todo pode ficar vazio e some junto). Sem colapsar (item L do pedido do dono): é só um
   separador visual para a barra não virar uma lista indiferenciada de 17 itens. */
export const ROTULOS_GRUPO = {
  campo: 'nav.grupo_campo',
  rede: 'nav.grupo_rede',
  conta: 'nav.grupo_conta',
  administracao: 'nav.grupo_administracao',
};

export const TELAS = [
  { caminho: '/', chave: 'nav.inicio' },
  { caminho: '/conteudo', chave: 'nav.conteudo' },
  { caminho: '/mapa', chave: 'nav.mapa' },
  { caminho: '/acervo', chave: 'nav.acervo' },
  { caminho: '/campo/filas', chave: 'nav.campo_filas', privilegio: 'campo.coletar', grupo: 'campo' },
  /* rede de utilidades: leitura é `rls:visibilidade` no backend (app/rede_utilidades/rotas*.py LER) — não há
     privilégio "rede.ver" no catálogo (app/auth/privilegios.py só tem rede.tracar/rede.editar), então ver a
     tela é igual a Mapa/Conexões: qualquer sessão válida, sem `privilegio` aqui. */
  { caminho: '/redes/simples', chave: 'nav.redes_simples', grupo: 'rede' },
  { caminho: '/redes/diagrama', chave: 'nav.redes_diagrama', grupo: 'rede' },
  { caminho: '/redes/controladores', chave: 'nav.redes_controladores', grupo: 'rede' },
  { caminho: '/redes/configuracoes', chave: 'nav.redes_configuracoes', grupo: 'rede' },
  { caminho: '/conexoes', chave: 'nav.conexoes', grupo: 'conta' },
  { caminho: '/uploads', chave: 'nav.uploads', privilegio: 'conteudo.criar', grupo: 'conta' },
  { caminho: '/construtor-camada', chave: 'nav.construtor_camada', privilegio: 'conteudo.publicar_camada', grupo: 'conta' },
  { caminho: '/conta', chave: 'nav.conta', grupo: 'conta' },
  { caminho: '/tarefas', chave: 'nav.tarefas', privilegio: 'jobs.executar', grupo: 'conta' },
  { caminho: '/admin/usuarios', chave: 'nav.usuarios', privilegio: 'membros.ver', grupo: 'administracao' },
  { caminho: '/admin/grupos', chave: 'nav.grupos', grupo: 'administracao' },
  { caminho: '/admin/papeis', chave: 'nav.papeis', privilegio: 'papeis.gerir', grupo: 'administracao' },
  { caminho: '/admin/tokens', chave: 'nav.tokens', privilegio: 'tokens.gerar', grupo: 'administracao' },
  { caminho: '/admin/log', chave: 'nav.log', privilegio: 'org.log_ver', grupo: 'administracao' },
  { caminho: '/admin/organizacao', chave: 'nav.organizacao', privilegio: 'org.configurar', grupo: 'administracao' },
  { caminho: '/admin/backup', chave: 'nav.backup', privilegio: 'org.configurar', grupo: 'administracao' },
  { caminho: '/admin/uso', chave: 'nav.uso', privilegio: 'org.configurar', grupo: 'administracao' },
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
  /* item L0-07-a: marca do inquilino na barra — logotipo e cor principal (tenant.config via /api/eu
     config_publica). A cor vira um CHIP ao lado do nome, nunca sobrepõe os tokens do sistema de design:
     repintar --acento com uma cor arbitrária derrubaria o contraste medido do tema (a marca completa por
     tokens é o L5-10, /temas, com aviso de contraste). Sem logo/cor, sem elemento nenhum. */
  const pub = inq.config_publica || {};
  const marcaFilhos = [];
  if (pub.logo) marcaFilhos.push(h('img', { id: 'marca-logo', class: 'marca-logo', src: `/api/arquivos/${pub.logo}?classe=org_logo`, alt: '', width: 28, height: 28 }));
  marcaFilhos.push(h('strong', {}, t('app.nome')));
  if (pub.cor) marcaFilhos.push(h('span', { id: 'marca-cor', class: 'marca-cor', title: pub.cor, style: `background:${pub.cor}` }));
  marcaFilhos.push(h('span', { title: inq.slug, id: 'marca-inquilino' }, inq.nome || inq.slug || ''));
  aside.append(h('div', { class: 'marca' }, ...marcaFilhos));
  const ul = h('ul');
  let grupoAberto = null;
  let sublista = null;
  for (const tela of telasVisiveis(usuario)) {
    if (tela.grupo !== grupoAberto) {
      grupoAberto = tela.grupo;
      const chaveRotulo = ROTULOS_GRUPO[grupoAberto];
      /* rótulo de grupo como <span> num <li> dono de uma sub-lista: li[role=separator] solto dentro de <ul>
         derruba a regra "list" do axe (séria) em TODA tela com a lateral — achado do L2-11-c no e2e UX-08. */
      if (chaveRotulo) {
        sublista = h('ul');
        ul.append(h('li', { class: 'grupo-nav' }, h('span', { class: 'grupo-rotulo' }, t(chaveRotulo)), sublista));
      } else {
        sublista = null;
      }
    }
    const a = h('a', { href: tela.caminho, 'aria-current': tela.caminho === ativo ? 'page' : undefined }, t(tela.chave));
    (sublista || ul).append(h('li', {}, a));
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
