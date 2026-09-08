/* plat — tela /admin/grupos (ADR 0002 seção 15.4): abas Meus grupos · Do inquilino, busca, criar (grupos.criar), painel
   Visão geral / Membros (convidar com busca em /api/usuarios?q=, aprovar, mudar papel, remover), sair, apagar, pedir
   entrada / entrar. Botões condicionados a meu_papel, às marcações do grupo e aos privilégios. */
import { obter, enviar, alterar, apagar, mensagemDe, consulta } from '../base/api.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import { tem } from '../base/estado.js';
import '../base/componentes.js';
import { confirmar } from '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from './sessao.js';
import { seletor, estadoDeLista, eventoRegistrado } from './comum.js';

const LIMITE = 50;
const filtros = { meus: '1', q: '', limite: LIMITE, deslocamento: 0 };
let aba = 'meus';

const gereTodos = () => tem('grupos.gerir_todos');
const ehDono = (g) => g.meu_papel === 'dono' || gereTodos();
const ehGerente = (g) => g.meu_papel === 'dono' || g.meu_papel === 'gerente' || gereTodos();
const ehMembroAtivo = (g) => !!g.meu_papel && (g.meu_estado === 'ativo' || !g.meu_estado);

let seqLista = 0;

await carregar();
const usuario = await exigirSessao();
if (usuario) await iniciar();
pronto();
async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/grupos' });
  montarAbas();
  montarTabela();
  const botoes = [h('plat-busca', { rotulo: t('grupos.buscar') })];
  botoes[0].addEventListener('buscar', (e) => { filtros.q = e.detail.q; filtros.deslocamento = 0; carregarLista(); });
  if (tem('grupos.criar')) {
    const bt = h('button', { type: 'button', class: 'primario', id: 'novo' }, t('grupos.novo'));
    bt.addEventListener('click', () => abrirCriar());
    botoes.push(bt);
  }
  cabecalho(t('grupos.titulo'), { contagem: 0, botoes });
  document.getElementById('paginacao').addEventListener('mudar', (e) => { filtros.deslocamento = e.detail.deslocamento; carregarLista(); });
  document.getElementById('estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'tentar') carregarLista();
    if (ev.detail.id === 'novo') abrirCriar();
    if (ev.detail.id === 'inquilino') document.getElementById('aba-inquilino').click();
  });
  await carregarLista();
}

function montarAbas() {
  const area = document.getElementById('abas');
  const defs = [['meus', t('grupos.aba_meus')], ['inquilino', t('grupos.aba_inquilino')]];
  for (const [id, rotulo] of defs) {
    const b = h('button', { type: 'button', role: 'tab', id: `aba-${id}`, 'aria-selected': String(id === aba), 'aria-controls': 'painel-lista' }, rotulo);
    b.addEventListener('click', () => { aba = id; filtros.meus = id === 'meus' ? '1' : ''; filtros.deslocamento = 0; area.querySelectorAll('[role=tab]').forEach((x) => x.setAttribute('aria-selected', String(x === b))); carregarLista(); });
    area.append(b);
  }
}

function marcacoes(g) {
  const m = [];
  if (g.atualizacao_compartilhada) m.push(marcador(t('grupo.atualizacao_compartilhada'), 'info'));
  if (g.administrativo) m.push(marcador(t('grupo.administrativo'), 'atencao'));
  if (g.protegido) m.push(marcador(t('grupo.protegido'), ''));
  return h('span', {}, ...m);
}

function montarTabela() {
  const tab = document.getElementById('tabela');
  tab.colunas = [
    { chave: 'nome', titulo: t('campo.nome') },
    { chave: 'resumo', titulo: t('grupo.resumo'), formatar: (v) => (v || '').slice(0, 80) },
    { chave: 'membros', titulo: t('grupo.membros'), classe: 'num' },
    { chave: 'meu_papel', titulo: t('grupo.meu_papel'), formatar: (v, g) => (v ? t(`grupo.papel_${v}`) + (g.meu_estado && g.meu_estado !== 'ativo' ? ` (${t(`grupo.estado_${g.meu_estado}`)})` : '') : '') },
    { chave: 'entrada', titulo: t('grupo.entrada'), formatar: (v) => t(`grupo.entrada_${v}`) },
    { chave: 'visibilidade', titulo: t('grupo.visibilidade'), formatar: (v) => t(`grupo.visibilidade_${v}`) },
    { chave: 'id', titulo: t('grupo.marcacoes'), formatar: (_, g) => marcacoes(g) },
  ];
  tab.acoes = (g) => {
    const a = [{ id: 'abrir', rotulo: t('acao.abrir') }];
    if (g.meu_estado === 'convidado') a.push({ id: 'aceitar', rotulo: t('grupo.aceitar'), classe: 'primario' }, { id: 'recusar', rotulo: t('grupo.recusar') });
    else if (!g.meu_papel && tem('grupos.entrar')) {
      if (g.entrada === 'livre') a.push({ id: 'entrar', rotulo: t('grupo.entrar'), classe: 'primario' });
      else if (g.entrada === 'pedido') a.push({ id: 'entrar', rotulo: t('grupo.pedir_entrada') });
    }
    return a;
  };
  tab.addEventListener('acao', async (e) => {
    const g = e.detail.linha;
    const aviso = document.getElementById('aviso');
    aviso.limpar();
    if (e.detail.id === 'abrir') { await abrirGrupo(g.id); return; }
    const r = await enviar(`/api/grupos/${g.id}/${e.detail.id}`);
    if (r.status >= 200 && r.status < 300) {
      const est = r.json?.estado;
      aviso.ok(est === 'pedido' ? t('grupo.pedido_enviado') : (e.detail.id === 'recusar' ? t('grupo.recusado') : t('grupo.entrou', { nome: g.nome })));
      await carregarLista();
      eventoRegistrado();
    } else aviso.erro(mensagemDe(r));
  });
}

async function carregarLista() {
  const estado = document.getElementById('estado');
  const tab = document.getElementById('tabela');
  const seq = ++seqLista;
  if (!tab.linhas.length) estadoDeLista(estado, tab, null);
  const r = await obter(`/api/grupos${consulta(filtros)}`);
  if (seq !== seqLista) return; // resposta atrasada de um pedido anterior: descarta
  const acoes = [];
  if (aba === 'meus' && !filtros.q) acoes.push({ id: 'inquilino', rotulo: t('grupos.aba_inquilino') });
  if (tem('grupos.criar')) acoes.push({ id: 'novo', rotulo: t('grupos.novo'), classe: 'primario' });
  estadoDeLista(estado, tab, r, { vazio: filtros.q ? t('grupos.vazio_busca', { q: filtros.q }) : (aba === 'meus' ? t('grupos.vazio_meus') : t('grupos.vazio_inquilino')), acoes });
  if (r.status !== 200) { tab.linhas = []; return; }
  const total = r.json.total ?? (r.json.itens || []).length;
  tab.linhas = r.json.itens || [];
  document.getElementById('paginacao').atualizar({ total, limite: LIMITE, deslocamento: filtros.deslocamento });
  cabecalho(t('grupos.titulo'), { contagem: total });
}

function camposGrupo(g) {
  const novo = !g;
  const c = [
    { nome: 'nome', rotulo: t('campo.nome'), tipo: 'texto', obrigatorio: true, padrao: g?.nome || '', atributos: { maxlength: 128 } },
    { nome: 'resumo', rotulo: t('grupo.resumo'), tipo: 'area', padrao: g?.resumo || '', atributos: { maxlength: 2048 }, linhas: 3 },
    { nome: 'tags', rotulo: t('grupo.tags'), tipo: 'texto', padrao: (g?.tags || []).join(', '), ajuda: t('grupo.tags_ajuda') },
    { nome: 'visibilidade', rotulo: t('grupo.visibilidade'), tipo: 'select', padrao: g?.visibilidade || 'membros', opcoes: ['membros', 'inquilino'].map((v) => ({ valor: v, rotulo: t(`grupo.visibilidade_${v}`) })) },
    { nome: 'entrada', rotulo: t('grupo.entrada'), tipo: 'select', padrao: g?.entrada || 'convite', opcoes: ['convite', 'pedido', 'livre'].map((v) => ({ valor: v, rotulo: t(`grupo.entrada_${v}`) })) },
    { nome: 'contribuicao', rotulo: t('grupo.contribuicao'), tipo: 'select', padrao: g?.contribuicao || 'todos', opcoes: ['todos', 'dono_gerentes'].map((v) => ({ valor: v, rotulo: t(`grupo.contribuicao_${v}`) })) },
  ];
  if (novo && tem('grupos.atualizacao_compartilhada')) c.push({ nome: 'atualizacao_compartilhada', rotulo: t('grupo.atualizacao_compartilhada'), tipo: 'caixa', ajuda: t('grupo.atualizacao_ajuda') });
  if (tem('grupos.administrativo') && (novo || ehDono(g))) c.push({ nome: 'administrativo', rotulo: t('grupo.administrativo'), tipo: 'caixa', padrao: !!g?.administrativo, ajuda: t('grupo.administrativo_ajuda') });
  c.push({ nome: 'protegido', rotulo: t('grupo.protegido'), tipo: 'caixa', padrao: !!g?.protegido, ajuda: t('grupo.protegido_ajuda') });
  return c;
}

function corpoDe(v, novo) {
  const corpo = { nome: v.nome, resumo: v.resumo || '', tags: (v.tags || '').split(',').map((s) => s.trim()).filter(Boolean).slice(0, 50), visibilidade: v.visibilidade, entrada: v.entrada, contribuicao: v.contribuicao, protegido: !!v.protegido };
  if (novo && v.atualizacao_compartilhada !== undefined) corpo.atualizacao_compartilhada = !!v.atualizacao_compartilhada;
  if (v.administrativo !== undefined) corpo.administrativo = !!v.administrativo;
  return corpo;
}

function abrirCriar() {
  const painel = document.getElementById('painel');
  document.getElementById('aviso').limpar();
  const f = h('plat-formulario');
  f.campos = camposGrupo(null);
  f.botoes = [{ id: 'salvar', rotulo: t('acao.criar'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('acao.cancelar') }];
  f.addEventListener('botao', (e) => { if (e.detail.id === 'cancelar') painel.fechar(null); });
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const r = await enviar('/api/grupos', corpoDe(e.detail.valores, true));
    f.ocupado = false;
    if (r.status === 201) { painel.fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t('grupos.criado', { nome: r.json.nome })); eventoRegistrado(); return; }
    const campo = { nome_existente: 'nome', atualizacao_exige_convite_ou_pedido: 'entrada', limite_grupos: 'nome' }[r.json.erro];
    if (campo) f.erro(campo, mensagemDe(r)); else f.mensagem(mensagemDe(r), 'erro');
  });
  painel.abrir({ titulo: t('grupos.novo'), corpo: f }).then(() => {});
  f.focarPrimeiro();
}

async function abrirGrupo(id) {
  const painel = document.getElementById('painel');
  const r = await obter(`/api/grupos/${id}`);
  if (r.status !== 200) { document.getElementById('aviso').erro(mensagemDe(r)); return; }
  const g = r.json;
  const corpo = h('div');
  const abasEl = h('div', { class: 'abas', role: 'tablist' });
  const pVisao = h('div', { role: 'tabpanel', id: 'g-visao' });
  const pMembros = h('div', { role: 'tabpanel', id: 'g-membros', hidden: true });
  const defs = [['visao', t('grupo.aba_visao'), pVisao], ['membros', t('grupo.aba_membros'), pMembros]];
  for (const [aid, rot, pane] of defs) {
    const b = h('button', { type: 'button', role: 'tab', 'aria-selected': String(aid === 'visao'), 'aria-controls': pane.id }, rot);
    b.addEventListener('click', () => { abasEl.querySelectorAll('[role=tab]').forEach((x) => x.setAttribute('aria-selected', String(x === b))); pVisao.hidden = aid !== 'visao'; pMembros.hidden = aid !== 'membros'; });
    abasEl.append(b);
  }
  corpo.append(abasEl, pVisao, pMembros);
  montarVisao(g, pVisao);
  const podeVerMembros = ehMembroAtivo(g) || gereTodos();
  if (podeVerMembros) await montarMembros(g, pMembros); else pMembros.append(h('p', { class: 'fraco' }, t('grupo.membros_so_membros')));
  painel.abrir({ titulo: g.nome, corpo }).then(() => {});
}

function montarVisao(g, alvo) {
  const aviso = h('plat-aviso');
  const info = h('dl', { class: 'espaco' },
    h('dt', {}, t('grupo.dono')), h('dd', {}, g.dono?.nome || g.dono?.login || ''),
    h('dt', {}, t('grupo.membros')), h('dd', {}, String(g.membros ?? '')),
    h('dt', {}, t('campo.criado_em')), h('dd', {}, formatarData(g.criado_em)),
    h('dt', {}, t('grupo.marcacoes')), h('dd', {}, marcacoes(g)));
  alvo.append(aviso, info);
  if (ehGerente(g)) {
    const f = h('plat-formulario');
    f.campos = camposGrupo(g);
    f.botoes = [{ id: 'salvar', rotulo: t('acao.salvar'), tipo: 'submit' }];
    f.addEventListener('enviar', async (e) => {
      f.ocupado = true;
      const c = corpoDe(e.detail.valores, false);
      if (!ehDono(g)) delete c.administrativo;
      const r = await alterar(`/api/grupos/${g.id}`, c);
      f.ocupado = false;
      if (r.status === 200) { Object.assign(g, r.json); await carregarLista(); f.mensagem(t('grupos.salvo'), 'ok'); eventoRegistrado(); return; }
      const campo = { nome_existente: 'nome', atualizacao_so_na_criacao: 'entrada' }[r.json.erro];
      if (campo) f.erro(campo, mensagemDe(r)); else f.mensagem(mensagemDe(r), 'erro');
    });
    alvo.append(h('h3', {}, t('grupo.editar')), f);
  }
  const acoes = h('div', { class: 'botoes espaco' });
  if (ehDono(g)) {
    const bt = h('button', { type: 'button' }, t('grupo.transferir_dono'));
    bt.addEventListener('click', () => transferirDono(g, aviso));
    acoes.append(bt);
  }
  if (g.meu_papel && g.meu_papel !== 'dono') {
    if (g.administrativo) acoes.append(h('span', { class: 'fraco' }, t('grupo.nao_sai_administrativo')));
    else {
      const bt = h('button', { type: 'button', class: 'perigo', id: 'sair-grupo' }, t('grupo.sair'));
      bt.addEventListener('click', async () => {
        if (!(await confirmar(t('grupo.sair'), t('grupo.sair_confirma', { nome: g.nome }), { perigo: true }))) return;
        const r = await apagar(`/api/grupos/${g.id}/membros/${usuario.id}`);
        if (r.status === 204) { document.getElementById('painel').fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t('grupo.saiu', { nome: g.nome })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
      });
      acoes.append(bt);
    }
  }
  if (ehDono(g)) {
    if (g.protegido) acoes.append(h('span', { class: 'fraco' }, t('grupo.protegido_nao_apaga')));
    else {
      const bt = h('button', { type: 'button', class: 'perigo', id: 'apagar-grupo' }, t('acao.apagar'));
      bt.addEventListener('click', async () => {
        if (!(await confirmar(t('acao.apagar'), t('grupo.apagar_confirma', { nome: g.nome }), { perigo: true, ok: t('acao.apagar') }))) return;
        const r = await apagar(`/api/grupos/${g.id}`);
        if (r.status === 204) { document.getElementById('painel').fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t('grupo.apagado', { nome: g.nome })); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
      });
      acoes.append(bt);
    }
  }
  alvo.append(acoes);
}

async function transferirDono(g, aviso) {
  const r = await obter(`/api/grupos/${g.id}/membros`);
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  const ativos = (r.json || []).filter((m) => m.estado === 'ativo' && m.papel !== 'dono');
  if (!ativos.length) { aviso.mostrar(t('grupo.sem_membro_para_dono'), 'atencao'); return; }
  const f = h('plat-formulario');
  f.campos = [{ nome: 'dono_id', rotulo: t('grupo.novo_dono'), tipo: 'select', opcoes: ativos.map((m) => ({ valor: String(m.usuario.id), rotulo: `${m.usuario.nome} (${m.usuario.login})` })) }];
  f.botoes = [{ id: 'ok', rotulo: t('grupo.transferir_dono'), tipo: 'submit' }];
  f.addEventListener('enviar', async (e) => {
    f.ocupado = true;
    const x = await alterar(`/api/grupos/${g.id}`, { dono_id: Number(e.detail.valores.dono_id) });
    f.ocupado = false;
    if (x.status === 200) { document.getElementById('painel').fechar('ok'); await carregarLista(); document.getElementById('aviso').ok(t('grupo.dono_transferido')); eventoRegistrado(); } else f.mensagem(mensagemDe(x), 'erro');
  });
  aviso.after(f);
  f.focarPrimeiro();
}

async function montarMembros(g, alvo) {
  limpar(alvo);
  const aviso = h('plat-aviso');
  const tab = h('plat-tabela', { legenda: t('grupo.aba_membros') });
  tab.chave = 'uid';
  tab.colunas = [
    { chave: 'usuario', titulo: t('campo.nome'), formatar: (u) => `${u?.nome || ''} (${u?.login || ''})` },
    { chave: 'papel', titulo: t('grupo.papel'), formatar: (v) => t(`grupo.papel_${v}`) },
    { chave: 'estado', titulo: t('campo.estado'), formatar: (v) => marcador(t(`grupo.estado_${v}`), v === 'ativo' ? 'ok' : 'atencao') },
    { chave: 'criado_em', titulo: t('campo.desde'), formatar: (v) => formatarData(v) },
  ];
  const gerente = ehGerente(g);
  tab.acoes = (m) => {
    const a = [];
    if (!gerente || m.papel === 'dono') return a;
    if (m.estado === 'pedido') a.push({ id: 'aprovar', rotulo: t('grupo.aprovar'), classe: 'primario' });
    if (m.estado === 'ativo') a.push(m.papel === 'gerente' ? { id: 'membro', rotulo: t('grupo.tornar_membro') } : { id: 'gerente', rotulo: t('grupo.tornar_gerente') });
    a.push({ id: 'remover', rotulo: t('grupo.remover'), classe: 'perigo' });
    return a;
  };
  tab.addEventListener('acao', async (e) => {
    const m = e.detail.linha; const uid = m.usuario.id;
    let r;
    if (e.detail.id === 'aprovar') r = await enviar(`/api/grupos/${g.id}/membros/${uid}/aprovar`);
    else if (e.detail.id === 'remover') r = await apagar(`/api/grupos/${g.id}/membros/${uid}`);
    else r = await alterar(`/api/grupos/${g.id}/membros/${uid}`, { papel: e.detail.id });
    if (r.status >= 200 && r.status < 300) { await recarregar(); aviso.ok(t('grupo.membro_atualizado')); eventoRegistrado(); } else aviso.erro(mensagemDe(r));
  });
  async function recarregar() {
    const r = await obter(`/api/grupos/${g.id}/membros`);
    if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
    tab.linhas = (r.json || []).map((m) => ({ ...m, uid: m.usuario?.id }));
  }
  alvo.append(aviso, tab);
  if (gerente) {
    const busca = h('plat-busca', { rotulo: t('grupo.convidar_buscar') });
    const resultados = h('div', { class: 'espaco', id: 'convidar-resultados' });
    const papelSel = seletor('papel', [{ valor: 'membro', rotulo: t('grupo.papel_membro') }, { valor: 'gerente', rotulo: t('grupo.papel_gerente') }], 'membro');
    papelSel.setAttribute('aria-label', t('grupo.papel'));
    busca.addEventListener('buscar', async (e) => {
      limpar(resultados);
      if (!e.detail.q) return;
      const r = await obter(`/api/usuarios${consulta({ q: e.detail.q, ativo: '1', limite: 10 })}`);
      if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
      const itens = r.json.itens || [];
      if (!itens.length) { resultados.append(h('p', { class: 'fraco' }, t('grupo.ninguem_encontrado'))); return; }
      const ul = h('ul', { class: 'lista-codigos' });
      for (const u of itens) {
        const bt = h('button', { type: 'button', class: 'pequeno primario' }, t('grupo.convidar'));
        bt.addEventListener('click', async () => {
          const x = await enviar(`/api/grupos/${g.id}/membros`, { usuario_id: u.id, papel: papelSel.value });
          if (x.status === 201) { aviso.ok(t('grupo.convidado', { login: u.login })); limpar(resultados); busca.valor = ''; await recarregar(); eventoRegistrado(); } else aviso.erro(mensagemDe(x));
        });
        ul.append(h('li', {}, `${u.nome} (${u.login}) `, bt));
      }
      resultados.append(ul);
    });
    alvo.append(h('h3', {}, t('grupo.convidar')), h('div', { class: 'linha-ferramentas' }, busca, papelSel), resultados);
  }
  await recarregar();
}
