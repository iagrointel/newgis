/* plat — tela /admin (item UX-06): a porta única da administração do inquilino. Um cartão por assunto, cada um
   com o número que importa e o caminho para a tela que o gere: usuários (ativos/cota), grupos, papéis, tokens,
   convites pendentes, armazenamento (uso/cota), provedor LDAP, acervo com licença, log. Cada cartão só aparece
   com o privilégio da tela correspondente (o mesmo critério da barra lateral) e cada número vem da rota que já
   existe — nenhuma rota nova. Quem não tem NENHUM privilégio administrativo vê o estado "sem permissão" com o
   caminho de volta (refutação do item: 403 amigável, nunca tela quebrada). Fecha com os últimos eventos do
   inquilino (GET /api/eventos) para quem tem org.log_ver. */
import { obter, consulta } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';

const ADMINISTRATIVOS = ['membros.ver', 'papeis.gerir', 'tokens.gerir_todos', 'org.log_ver', 'org.configurar', 'org.integracoes', 'conteudo.registrar_fonte'];

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin' });
  cabecalho(t('admin.titulo'));
  const estado = document.getElementById('estado');
  if (!ADMINISTRATIVOS.some((p) => tem(p))) {
    estado.mostrar({ tipo: 'negado', texto: t('admin.negado_texto'), acoes: [{ id: 'inicio', rotulo: t('nav.inicio') }, { id: 'conta', rotulo: t('nav.conta') }] });
    estado.addEventListener('acao', (ev) => { location.href = ev.detail.id === 'conta' ? '/conta' : '/'; });
    return;
  }
  estado.carregando(t('admin.carregando'));
  await montarResumo();
  estado.limpar();
  document.getElementById('resumo').hidden = false;
  if (tem('org.log_ver')) await montarEventos();
}

/* um cartão: título, número grande (ou estado curto), linha de apoio e o caminho da tela */
function cartao({ id, titulo, caminho, numero, apoio, marcador, classe = '' }) {
  const a = h('a', { class: `admin-cartao ${classe}`.trim(), href: caminho, id: `cartao-${id}` },
    h('span', { class: 'admin-cartao-titulo' }, titulo),
    h('span', { class: 'admin-cartao-numero' }, numero ?? '—'),
    apoio ? h('span', { class: 'admin-cartao-apoio' }, apoio) : null,
    marcador ? h('span', { class: `marcador ${marcador.classe}` }, marcador.texto) : null);
  return a;
}

function cartaoErro({ id, titulo, caminho, r }) {
  const negado = r.status === 403;
  return cartao({ id, titulo, caminho, numero: negado ? t('admin.sem_acesso') : t('admin.indisponivel'), apoio: negado ? t('estado.negado_titulo') : (r.json?.mensagem || `${r.status}`), classe: negado ? 'negado' : 'erro' });
}

async function montarResumo() {
  const grade = document.getElementById('resumo');
  const pedidos = [];
  const cartoes = [];
  const acrescenta = (cond, id, titulo, caminho, pedido, montar) => {
    if (!cond) return;
    const pos = cartoes.length;
    cartoes.push(null);
    pedidos.push(pedido().then((r) => { cartoes[pos] = r.status === 200 ? montar(r.json) : cartaoErro({ id, titulo, caminho, r }); }));
  };
  const org = tem('org.configurar') ? obter('/api/org') : null;
  acrescenta(tem('membros.ver'), 'usuarios', t('nav.usuarios'), '/admin/usuarios', () => obter(`/api/usuarios${consulta({ limite: 1, ativo: '1' })}`), (j) => cartao({
    id: 'usuarios', titulo: t('nav.usuarios'), caminho: '/admin/usuarios', numero: formatarNumero(j.total ?? 0), apoio: t('admin.usuarios_ativos'),
  }));
  acrescenta(tem('membros.ver'), 'convites', t('convite.titulo'), '/admin/usuarios#convites', () => obter('/api/convites'), (j) => {
    const itens = Array.isArray(j) ? j : (j.itens || []); // GET /api/convites só devolve os pendentes
    return cartao({ id: 'convites', titulo: t('convite.titulo'), caminho: '/admin/usuarios#convites', numero: formatarNumero(itens.length), apoio: t('admin.convites_pendentes') });
  });
  acrescenta(true, 'grupos', t('nav.grupos'), '/admin/grupos', () => obter(`/api/grupos${consulta({ limite: 1, meus: '' })}`), (j) => cartao({
    id: 'grupos', titulo: t('nav.grupos'), caminho: '/admin/grupos', numero: formatarNumero(j.total ?? (j.itens || []).length), apoio: t('admin.grupos_do_inquilino'),
  }));
  acrescenta(tem('papeis.gerir'), 'papeis', t('nav.papeis'), '/admin/papeis', () => obter('/api/papeis'), (j) => cartao({
    id: 'papeis', titulo: t('nav.papeis'), caminho: '/admin/papeis', numero: formatarNumero((j.personalizados || []).length), apoio: t('admin.papeis_personalizados'),
  }));
  acrescenta(tem('tokens.gerar'), 'tokens', t('nav.tokens'), '/admin/tokens', () => obter(`/api/tokens${consulta({ todos: tem('tokens.gerir_todos') ? '1' : '' })}`), (j) => {
    const itens = Array.isArray(j) ? j : (j.itens || []);
    const validos = itens.filter((k) => !k.revogado_em && (!k.expira_em || new Date(k.expira_em) > new Date()));
    return cartao({ id: 'tokens', titulo: t('nav.tokens'), caminho: '/admin/tokens', numero: formatarNumero(validos.length), apoio: t(tem('tokens.gerir_todos') ? 'admin.tokens_validos_inquilino' : 'admin.tokens_validos_meus') });
  });
  if (org) {
    acrescenta(true, 'armazenamento', t('org.armazenamento'), '/admin/organizacao#cotas', () => org, (j) => {
      const uso = j.armazenamento?.bytes_usados ?? 0; const cota = j.armazenamento?.cota_bytes ?? 0;
      const pct = cota ? Math.round((uso / cota) * 100) : 0;
      return cartao({ id: 'armazenamento', titulo: t('org.armazenamento'), caminho: '/admin/organizacao#cotas', numero: `${pct} %`, apoio: t('admin.armazenamento_uso', { uso: mb(uso), cota: mb(cota) }), marcador: pct >= 90 ? { classe: 'atencao', texto: t('admin.cota_quase') } : null });
    });
    acrescenta(true, 'cota-usuarios', t('org.usuarios'), '/admin/organizacao#usuarios', () => org, (j) => cartao({
      id: 'cota-usuarios', titulo: t('org.usuarios'), caminho: '/admin/organizacao#usuarios', numero: `${formatarNumero(j.usuarios?.ativos ?? 0)} / ${formatarNumero(j.usuarios?.cota ?? 0)}`, apoio: t('admin.usuarios_cota'),
    }));
  }
  acrescenta(tem('org.integracoes'), 'ldap', t('ldap.titulo'), '/admin/organizacao#ldap', () => obter('/api/org/ldap'), (j) => cartao({
    id: 'ldap', titulo: t('ldap.titulo'), caminho: '/admin/organizacao#ldap', numero: j ? (j.habilitado ? t('ldap.habilitado') : t('ldap.desabilitado')) : t('ldap.nao_configurado'), apoio: j?.url || t('ldap.sem_url'),
    marcador: j && j.habilitado ? { classe: 'ok', texto: t('ldap.habilitado') } : null,
  }));
  acrescenta(tem('conteudo.registrar_fonte'), 'acervo', t('nav.acervo'), '/admin/acervo', () => obter(`/api/acervo${consulta({ limite: 1 })}`), (j) => cartao({
    id: 'acervo', titulo: t('nav.acervo'), caminho: '/admin/acervo', numero: formatarNumero(j.total ?? 0), apoio: t('admin.acervo_fontes'),
  }));
  acrescenta(tem('org.log_ver'), 'log', t('nav.log'), '/admin/log', () => obter(`/api/log${consulta({ limite: 1, desde: new Date(Date.now() - 86400000).toISOString() })}`), (j) => cartao({
    id: 'log', titulo: t('nav.log'), caminho: '/admin/log', numero: formatarNumero(j.total ?? 0), apoio: t('admin.acessos_24h'),
  }));
  await Promise.all(pedidos);
  limpar(grade);
  grade.append(h('h2', { class: 'sr-only' }, t('admin.resumo')));
  for (const c of cartoes) if (c) grade.append(c);
}

// declaração de função (içada): o `await iniciar()` de nível de módulo roda antes desta linha (achado UX-01/UX-06)
function mb(n) { return `${formatarNumero(Math.round((n || 0) / (1024 * 1024)))} MB`; }

async function montarEventos() {
  const sec = document.getElementById('eventos');
  const estado = document.getElementById('eventos-estado');
  const tab = document.getElementById('eventos-tabela');
  sec.hidden = false;
  tab.colunas = [
    { chave: 'em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'tipo', titulo: t('log.tipo_evento'), classe: 'mono' },
    { chave: 'ator', titulo: t('log.ator'), formatar: (a) => a?.login || '', classe: 'mono' },
    { chave: 'alvo_tipo', titulo: t('log.alvo'), formatar: (v, l) => [v, l.alvo_id].filter(Boolean).join(':'), classe: 'mono' },
  ];
  tab.hidden = true;
  estado.carregando();
  const r = await obter(`/api/eventos${consulta({ limite: 8 })}`);
  if (r.status !== 200) { estado.erro(r); return; }
  const itens = r.json.itens || [];
  if (!itens.length) { estado.vazio(t('admin.eventos_vazio')); return; }
  estado.limpar();
  tab.hidden = false;
  tab.linhas = itens;
}
