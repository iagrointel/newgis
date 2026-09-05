/* plat · tarefas — entrada da tela /tarefas e /tarefas/<id>. Módulos ES sem build; o cache é resolvido por
   no-store no nginx: NUNCA ?v= nos imports (duas URLs do mesmo módulo = duas instâncias).
   Sessão: GET /api/eu (trilha de identidade, ADR 0002): 401 → /entrar?proximo=...; 200 → usuário (perfil decide
   o filtro "quem" e a seção de agendas); outro status (rota ainda não publicada) → segue só com a API de jobs,
   que valida o cookie por conta própria. Depois: layout comum, tipos, lista, detalhe (por URL), agendas,
   body[data-pronto="1"] ao terminar a primeira carga. */
import { obter } from '../base/api.js';
import '../base/componentes.js';
import { loja } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';
import { h } from '../base/dom.js';
import * as agendas from './agendas.js';
import * as api from './api.js';
import * as detalhe from './detalhe.js';
import * as lista from './lista.js';
import { aviso } from './util.js';

const ID_NA_URL = /^\/tarefas\/([^/]+)\/?$/;
let saindo = false;

function idDaUrl() {
  const m = ID_NA_URL.exec(location.pathname);
  return m ? decodeURIComponent(m[1]) : null;
}

/* barra lateral comum + contador de tarefas ativas no item "Tarefas" (montarLayout lê TELAS de js/base/layout.js) */
function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/tarefas' });
  const aside = document.getElementById('lateral');
  if (!usuario) {
    const pessoa = aside && aside.querySelector('.pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  let link = aside && aside.querySelector('nav a[href="/tarefas"]');
  if (!link && aside) {
    // a entrada "Tarefas" ainda não está em TELAS: acrescenta o item sem tocar no resto do menu
    const ul = aside.querySelector('nav ul');
    link = h('a', { href: '/tarefas', 'aria-current': 'page' }, 'Tarefas');
    if (ul) ul.append(h('li', {}, link));
  }
  if (link) link.append(' ', h('span', { id: 'tarefas-ativas', class: 'marcador info', hidden: true, 'aria-label': 'tarefas ativas' }, '0'));
  cabecalho('Tarefas');
}

async function principal() {
  api.definirSemSessao(() => {
    saindo = true;
    irParaLogin();
  });
  const r = await obter('/api/eu');
  if (r.status === 401) {
    saindo = true;
    irParaLogin();
    return;
  }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) {
      saindo = true;
      location.replace(destino);
      return;
    }
  } else {
    aviso('aviso', `dados da sessão indisponíveis (GET /api/eu devolveu ${r.status}); a tela segue com a API de tarefas`, 'atencao');
  }
  layout(usuario);

  let tipos = [];
  try {
    tipos = await api.tipos();
  } catch (e) {
    if (e.status === 401) return;
    aviso('aviso', `não foi possível carregar os tipos de tarefa (${e.status || 'rede'}): ${e.message}`);
  }

  detalhe.iniciar({
    aoAbrir: (id) => lista.selecionar(id),
    aoFechar: () => lista.selecionar(null),
    aoNovoJob: () => lista.recarregar(),
  });
  await lista.iniciar({ usuario, tipos, aoAbrir: (id) => detalhe.abrir(id) });
  await agendas.iniciar({
    usuario,
    tipos,
    aoNovoJob: (job) => {
      lista.recarregar();
      detalhe.abrir(job.id);
    },
  });

  const id = idDaUrl();
  if (id) await detalhe.abrir(id, { empurrarUrl: false });

  window.addEventListener('popstate', () => {
    const alvo = idDaUrl();
    if (alvo) detalhe.abrir(alvo, { empurrarUrl: false });
    else detalhe.fechar({ empurrarUrl: false });
  });
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (!saindo) pronto();
}
