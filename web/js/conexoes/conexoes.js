/* plat · conexões — entrada da tela /conexoes (itens L6-02-l-saude, L6-05-proveniencia-camada-externa e UX-05).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do mesmo
   módulo = duas instâncias, app morre — regra da casa).
   A tela cobre TODAS as rotas de /api/conexoes (UX-13): lista com busca e ordenação por coluna, criar e editar por
   <plat-formulario> (nome, tipo, endereço, modo, config JSON e credencial — a credencial nunca volta do servidor:
   só "tem credencial" e a opção de remover), apagar com confirmação, testar agora, histórico (últimos 10 testes) e
   publicar camada (item de catálogo com a ficha de procedência lida do serviço). Estados explícitos por
   <plat-estado>: carregando, vazio (com a ação de criar), erro (com tentar de novo) e negado (403). Erros da API
   (400 endereço recusado, 409 nome repetido, 413 cota, 422 campo a campo) aparecem nomeados no controle. */
import * as api from '../base/api.js';
import { confirmar } from '../base/componentes.js';
import { loja } from '../base/estado.js';
import { aoTraduzir, aplicar, carregar as carregarIdioma, formatarData, t } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { caminhoPendencia, irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';

const TIPOS = ['wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'postgres_fdw', 's3', 'http'];
const MODOS = ['referenciada', 'copiada'];
const ESTADO_CLASSE = { ok: 'ok', degradado: 'atencao', fora: 'falha', nunca_testada: 'info' };
const ORDEM_ESTADO = { fora: 0, degradado: 1, nunca_testada: 2, ok: 3 };
const CAMPOS = ['nome', 'tipo', 'url', 'modo', 'config', 'credencial', 'remover_credencial'];
const PRIVILEGIO_CRIAR = 'conteudo.registrar_fonte';

let saindo = false;
const s = { itens: [], usuario: null, ordenar: 'nome:asc', busca: '', editando: null, form: null, carregando: false };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = document.getElementById(id);
  if (!n) return;
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

const podeCriar = () => {
  const u = s.usuario;
  return !u || !Array.isArray(u.privilegios) || u.privilegios.includes(PRIVILEGIO_CRIAR);
};
const podeEditar = (c) => {
  const u = s.usuario;
  if (!u || !Array.isArray(u.privilegios)) return true;
  return (c.dono && Number(c.dono.id) === Number(u.id)) || u.privilegios.includes('conteudo.editar_tudo');
};

const rotuloEstado = (estado) => t(`conexoes.estado_${estado || 'nunca_testada'}`);

function badgeEstado(estado) {
  const classe = ESTADO_CLASSE[estado] || 'info';
  const rotulo = rotuloEstado(estado);
  return h('span', { class: `marcador ${classe}`, title: t('conexoes.estado_titulo', { estado: rotulo }) }, rotulo);
}

function celulaDisponibilidade(c) {
  if (c.disponibilidade_30d_total === 0 || c.disponibilidade_30d_pct === null || c.disponibilidade_30d_pct === undefined) {
    return h('span', { class: 'ajuda' }, t('conexoes.sem_verificacao_30d'));
  }
  return h('span', {}, t('conexoes.disponibilidade', { pct: c.disponibilidade_30d_pct, n: c.disponibilidade_30d_total }));
}

/* ---------- ações por linha ---------- */

async function testarAgora(c, botao) {
  botao.disabled = true;
  botao.setAttribute('aria-busy', 'true');
  aviso('lista-aviso', '');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/testar`, {});
  botao.disabled = false;
  botao.removeAttribute('aria-busy');
  if (r.status !== 200) {
    aviso('lista-aviso', t('conexoes.erro_testar', { nome: c.nome, erro: api.mensagemDe(r) }));
    return;
  }
  await carregar({ silencioso: true });
}

function linhaHistoricoTabela(item) {
  return h('tr', {},
    h('td', {}, formatarData(item.verificada_em)),
    h('td', {}, h('span', { class: `marcador ${item.ok ? 'ok' : 'falha'}` }, item.ok ? t('conexoes.estado_ok') : t('conexoes.hist_erro'))),
    h('td', {}, item.status === null || item.status === undefined ? '—' : String(item.status)),
    h('td', {}, item.mensagem || '—'),
    h('td', {}, item.latencia_ms === null || item.latencia_ms === undefined ? '—' : `${item.latencia_ms} ms`));
}

async function verHistorico(c) {
  const dialogo = porId('dialogo');
  const r = await api.obter(`/api/conexoes/${encodeURIComponent(c.id)}/saude-historico?limite=10`);
  if (r.status !== 200) {
    aviso('lista-aviso', t('conexoes.erro_historico', { nome: c.nome, erro: api.mensagemDe(r) }));
    return;
  }
  const itens = r.json.itens || [];
  const corpo = h('div', {},
    h('p', {}, t('conexoes.hist_resumo', { nome: c.nome, n: itens.length })),
    itens.length
      ? h('div', { class: 'tabela-rolagem' }, h('table', { class: 'tabela', 'aria-label': t('conexoes.hist_titulo') },
          h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, t('conexoes.hist_quando')), h('th', { scope: 'col' }, t('conexoes.hist_resultado')),
            h('th', { scope: 'col' }, t('conexoes.hist_status')), h('th', { scope: 'col' }, t('conexoes.hist_mensagem')), h('th', { scope: 'col' }, t('conexoes.hist_latencia')))),
          h('tbody', {}, ...itens.map(linhaHistoricoTabela))))
      : h('p', { class: 'ajuda' }, t('conexoes.hist_vazio')));
  await dialogo.abrir({ titulo: t('conexoes.hist_titulo'), corpo, botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar') }] });
}

function linhaProcedencia(rotulo, valor) {
  return h('div', { class: 'campo' },
    h('strong', {}, rotulo), ': ',
    valor === null || valor === undefined || valor === '' ? h('em', {}, t('conexoes.nao_registrado')) : h('span', {}, String(valor)));
}

async function publicarCamada(c, botao) {
  const dialogo = porId('dialogo');
  botao.disabled = true;
  botao.setAttribute('aria-busy', 'true');
  const r = await api.enviar(`/api/conexoes/${encodeURIComponent(c.id)}/publicar`, {});
  botao.disabled = false;
  botao.removeAttribute('aria-busy');
  if (r.status !== 201) {
    aviso('lista-aviso', t('conexoes.erro_publicar', { nome: c.nome, erro: api.mensagemDe(r) }));
    return;
  }
  const item = r.json;
  const proc = (item.dados && item.dados.procedencia) || {};
  const corpo = h('div', {},
    h('p', {}, h('a', { href: `/conteudo/${encodeURIComponent(item.id)}` }, t('conexoes.abrir_no_catalogo', { titulo: item.titulo }))),
    linhaProcedencia(t('conexoes.proc_fonte'), proc.fonte),
    linhaProcedencia(t('conexoes.proc_url'), proc.url),
    linhaProcedencia(t('conexoes.proc_licenca'), proc.licenca),
    linhaProcedencia(t('conexoes.proc_data_acesso'), proc.data_de_acesso),
    linhaProcedencia(t('conexoes.proc_metodo'), proc.metodo),
    linhaProcedencia(t('conexoes.proc_confianca'), proc.confianca),
    linhaProcedencia(t('conexoes.proc_frescor'), proc.frescor),
    linhaProcedencia(t('conexoes.proc_sha256'), proc.sha256),
    linhaProcedencia(t('conexoes.proc_reexecucao'), proc.comando_reexecucao),
    linhaProcedencia(t('conexoes.proc_creditos'), item.creditos),
    proc.limites && proc.limites.length ? h('p', { class: 'ajuda' }, t('conexoes.proc_ressalvas', { lista: proc.limites.join('; ') })) : null);
  await dialogo.abrir({ titulo: t('conexoes.publicada_titulo'), corpo, botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar') }] });
  aviso('lista-aviso', t('conexoes.publicada', { nome: c.nome }), 'ok');
}

async function apagarConexao(c) {
  const ok = await confirmar(t('conexoes.apagar_titulo'), t('conexoes.apagar_texto', { nome: c.nome }), { ok: t('acao.apagar'), perigo: true });
  if (!ok) return;
  const r = await api.apagar(`/api/conexoes/${encodeURIComponent(c.id)}`);
  if (r.status !== 204) {
    aviso('lista-aviso', t('conexoes.erro_apagar', { nome: c.nome, erro: api.mensagemDe(r) }));
    return;
  }
  if (s.editando === c.id) fecharFormulario();
  aviso('lista-aviso', t('conexoes.apagada', { nome: c.nome }), 'ok');
  await carregar({ silencioso: true });
}

/* ---------- formulário (criar / editar) ---------- */

function errosPorCampo(detalhe) {
  const m = {};
  const junta = (campo, msg) => { m[campo] = m[campo] ? `${m[campo]}; ${msg}` : msg; };
  if (Array.isArray(detalhe)) {
    for (const d of detalhe) {
      const loc = Array.isArray(d.loc) ? d.loc.filter((x) => typeof x === 'string' && x !== 'body') : [];
      junta(CAMPOS.includes(loc[0]) ? loc[0] : '_', d.msg || JSON.stringify(d));
    }
  } else if (detalhe && typeof detalhe === 'object') {
    for (const [k, v] of Object.entries(detalhe)) junta(CAMPOS.includes(k) ? k : '_', typeof v === 'string' ? v : JSON.stringify(v));
  } else if (typeof detalhe === 'string') {
    m._ = detalhe;
  }
  return m;
}

function mostrarErros(erros) {
  s.form.limparErros();
  for (const [campo, msg] of Object.entries(erros)) {
    if (campo === '_') s.form.mensagem(msg, 'erro');
    else s.form.erro(campo, msg);
  }
  s.form.querySelector('[aria-invalid="true"]')?.focus();
}

function validar(v) {
  const erros = {};
  let config = {};
  const texto = (v.config || '').trim();
  if (texto) {
    try {
      config = JSON.parse(texto);
      if (!config || typeof config !== 'object' || Array.isArray(config)) erros.config = t('conexoes.erro_config_objeto');
    } catch {
      erros.config = t('conexoes.erro_config_json');
    }
  }
  const url = (v.url || '').trim();
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) erros.url = t('conexoes.erro_url_esquema');
  const dados = { nome: v.nome, url, modo: v.modo || 'referenciada', config };
  if (!s.editando) dados.tipo = v.tipo;
  if (v.credencial) dados.credencial = v.credencial;
  if (s.editando && v.remover_credencial) dados.remover_credencial = true;
  return { dados, erros };
}

function camposDoFormulario(editando) {
  const campos = [
    { nome: 'nome', rotulo: t('conexoes.campo_nome'), tipo: 'texto', obrigatorio: true, atributos: { maxlength: '200', autocomplete: 'off' } },
    { nome: 'tipo', rotulo: t('conexoes.campo_tipo'), tipo: 'select', obrigatorio: true, desabilitado: !!editando,
      opcoes: [{ valor: '', rotulo: t('conexoes.escolha') }, ...TIPOS.map((x) => ({ valor: x, rotulo: t(`conexoes.tipo_${x}`) }))],
      ajuda: editando ? t('conexoes.campo_tipo_fixo') : t('conexoes.campo_tipo_ajuda') },
    { nome: 'url', rotulo: t('conexoes.campo_url'), tipo: 'texto', obrigatorio: true,
      ajuda: t('conexoes.campo_url_ajuda'), atributos: { maxlength: '2048', autocomplete: 'off', spellcheck: 'false', inputmode: 'url' } },
    { nome: 'modo', rotulo: t('conexoes.campo_modo'), tipo: 'select', padrao: 'referenciada',
      opcoes: MODOS.map((x) => ({ valor: x, rotulo: t(`conexoes.modo_${x}`) })), ajuda: t('conexoes.campo_modo_ajuda') },
    { nome: 'config', rotulo: t('conexoes.campo_config'), tipo: 'area', padrao: '{}', linhas: 3, ajuda: t('conexoes.campo_config_ajuda'),
      atributos: { spellcheck: 'false' } },
    { nome: 'credencial', rotulo: t('conexoes.campo_credencial'), tipo: 'senha',
      ajuda: editando && editando.tem_credencial ? t('conexoes.campo_credencial_existe') : t('conexoes.campo_credencial_ajuda'),
      atributos: { maxlength: '4096', autocomplete: 'new-password' } },
  ];
  if (editando && editando.tem_credencial) {
    campos.push({ nome: 'remover_credencial', rotulo: t('conexoes.campo_remover_credencial'), tipo: 'caixa' });
  }
  return campos;
}

async function abrirFormulario(conexao = null) {
  let completa = conexao;
  if (conexao) {
    // GET /api/conexoes/{id}: a lista não traz config nem tem_credencial
    const r = await api.obter(`/api/conexoes/${encodeURIComponent(conexao.id)}`);
    if (r.status !== 200) {
      aviso('lista-aviso', t('conexoes.erro_ler', { nome: conexao.nome, erro: api.mensagemDe(r) }));
      return;
    }
    completa = r.json;
  }
  s.editando = completa ? completa.id : null;
  porId('conexao-form-titulo').textContent = completa ? t('conexoes.form_editar', { nome: completa.nome }) : t('conexoes.form_nova');
  s.form.campos = camposDoFormulario(completa);
  s.form.botoes = [
    { id: 'salvar', rotulo: completa ? t('acao.salvar') : t('acao.criar'), tipo: 'submit' },
    { id: 'cancelar', rotulo: t('acao.cancelar'), tipo: 'button' },
  ];
  s.form.definir({
    nome: completa ? completa.nome : '',
    tipo: completa ? completa.tipo : '',
    url: completa ? completa.url : '',
    modo: completa ? completa.modo : 'referenciada',
    config: completa ? JSON.stringify(completa.config || {}, null, 2) : '{}',
    credencial: '',
  });
  porId('conexao-form-caixa').hidden = false;
  s.form.focarPrimeiro();
}

function fecharFormulario() {
  porId('conexao-form-caixa').hidden = true;
  s.editando = null;
  porId('conexao-nova').focus();
}

async function salvar(valores) {
  const { dados, erros } = validar(valores);
  if (Object.keys(erros).length) {
    mostrarErros(erros);
    return;
  }
  s.form.ocupado = true;
  const r = s.editando
    ? await api.chamar('PATCH', `/api/conexoes/${encodeURIComponent(s.editando)}`, dados)
    : await api.enviar('/api/conexoes', dados);
  s.form.ocupado = false;
  if (r.status === 200 || r.status === 201) {
    const nome = r.json.nome || dados.nome;
    const editava = !!s.editando;
    fecharFormulario();
    aviso('lista-aviso', editava ? t('conexoes.salva', { nome }) : t('conexoes.criada', { nome }), 'ok');
    await carregar({ silencioso: true });
    const tr = document.querySelector(`tr[data-id="${CSS.escape(r.json.id)}"]`);
    if (tr) tr.scrollIntoView({ block: 'nearest' });
    return;
  }
  const j = r.json || {};
  const m = {};
  // 422 tem três formas: url_insegura (SSRF recusado na entrada), config_grande_demais e a lista do pydantic
  if (r.status === 422 && j.erro === 'url_insegura') m.url = j.mensagem || t('conexoes.erro_url_recusada');
  else if (r.status === 422 && j.erro === 'config_grande_demais') m.config = j.mensagem || t('conexoes.erro_config_json');
  else if (r.status === 422) Object.assign(m, errosPorCampo(j.detalhe));
  if (r.status === 409) m.nome = j.mensagem || t('conexoes.erro_nome_existente');
  if (r.status === 413) m._ = j.mensagem || t('conexoes.erro_cota');
  if (r.status === 403) m._ = j.mensagem || t('conexoes.erro_sem_privilegio');
  if (!Object.keys(m).length) m._ = t('conexoes.erro_salvar', { status: r.status || 'rede', erro: api.mensagemDe(r) });
  mostrarErros(m);
}

/* ---------- lista ---------- */

function linha(c) {
  const tr = h('tr', { dataset: { id: c.id, estado: c.estado_saude } });
  const btTestar = h('button', { type: 'button', class: 'pequeno acao-testar' }, t('conexoes.testar_agora'));
  btTestar.addEventListener('click', () => testarAgora(c, btTestar));
  const btHistorico = h('button', { type: 'button', class: 'pequeno acao-historico' }, t('conexoes.historico'));
  btHistorico.addEventListener('click', () => verHistorico(c));
  const btPublicar = h('button', { type: 'button', class: 'pequeno acao-publicar' }, t('conexoes.publicar_camada'));
  btPublicar.addEventListener('click', () => publicarCamada(c, btPublicar));
  const acoes = h('div', { class: 'acoes-linha' }, btTestar, btHistorico, btPublicar);
  if (podeEditar(c)) {
    const btEditar = h('button', { type: 'button', class: 'pequeno texto acao-editar' }, t('acao.editar'));
    btEditar.addEventListener('click', () => abrirFormulario(c));
    const btApagar = h('button', { type: 'button', class: 'pequeno perigo acao-apagar' }, t('acao.apagar'));
    btApagar.addEventListener('click', () => apagarConexao(c));
    acoes.append(btEditar, btApagar);
  }
  tr.append(
    h('td', { class: 'c-nome' }, h('span', { class: 'nome' }, c.nome), h('span', { class: 'ajuda url mono' }, c.url || '')),
    h('td', {}, t(`conexoes.tipo_${c.tipo}`)),
    h('td', {}, t(`conexoes.modo_${c.modo}`)),
    h('td', {}, badgeEstado(c.estado_saude)),
    h('td', {}, celulaDisponibilidade(c)),
    h('td', {}, c.saude_verificada_em ? formatarData(c.saude_verificada_em) : h('span', { class: 'ajuda' }, t('conexoes.estado_nunca_testada'))),
    h('td', {}, acoes),
  );
  return tr;
}

function valorOrdem(c, campo) {
  switch (campo) {
    case 'estado_saude': return ORDEM_ESTADO[c.estado_saude] ?? 9;
    case 'disponibilidade_30d_pct': return c.disponibilidade_30d_pct === null || c.disponibilidade_30d_pct === undefined ? -1 : Number(c.disponibilidade_30d_pct);
    case 'saude_verificada_em': return c.saude_verificada_em ? new Date(c.saude_verificada_em).getTime() : 0;
    default: return String(c[campo] || '').toLocaleLowerCase();
  }
}

function visiveis() {
  const [campo, dir] = s.ordenar.split(':');
  const q = s.busca.toLocaleLowerCase();
  const lista = s.itens.filter((c) => !q || `${c.nome} ${c.tipo} ${c.url} ${c.modo}`.toLocaleLowerCase().includes(q));
  const sinal = dir === 'desc' ? -1 : 1;
  lista.sort((a, b) => {
    const va = valorOrdem(a, campo), vb = valorOrdem(b, campo);
    if (va < vb) return -sinal;
    if (va > vb) return sinal;
    return String(a.nome).localeCompare(String(b.nome));
  });
  return lista;
}

function renderizar() {
  const estado = porId('lista-estado');
  const caixa = porId('lista-caixa');
  const corpo = porId('lista-corpo');
  limpar(corpo);
  const lista = visiveis();
  porId('lista-total').textContent = s.busca ? `(${lista.length}/${s.itens.length})` : `(${s.itens.length})`;
  const [campo, dir] = s.ordenar.split(':');
  for (const th of document.querySelectorAll('#lista th[data-campo]')) {
    th.setAttribute('aria-sort', th.dataset.campo === campo ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
  }
  if (!s.itens.length) {
    caixa.hidden = true;
    estado.vazio(t('conexoes.vazio_texto'), podeCriar() ? [{ id: 'nova', rotulo: t('conexoes.nova'), classe: 'primario' }] : []);
    return;
  }
  if (!lista.length) {
    caixa.hidden = true;
    estado.mostrar({ tipo: 'vazio', titulo: t('conexoes.busca_vazia_titulo'), texto: t('conexoes.busca_vazia_texto', { q: s.busca }), acoes: [{ id: 'limpar-busca', rotulo: t('conexoes.limpar_busca') }] });
    return;
  }
  estado.limpar();
  caixa.hidden = false;
  for (const c of lista) corpo.append(linha(c));
}

async function carregar({ silencioso = false } = {}) {
  const estado = porId('lista-estado');
  const caixa = porId('lista-caixa');
  if (!silencioso) {
    caixa.hidden = true;
    estado.carregando(t('conexoes.carregando'));
  }
  porId('lista').setAttribute('aria-busy', 'true');
  const r = await api.obter('/api/conexoes');
  porId('lista').setAttribute('aria-busy', 'false');
  if (r.status !== 200) {
    if (r.status === 401) return;
    caixa.hidden = true;
    estado.erro(r);
    porId('lista-total').textContent = '';
    return;
  }
  s.itens = r.json.itens || [];
  renderizar();
}

function ordenarPor(campo) {
  const [atual, dir] = s.ordenar.split(':');
  s.ordenar = `${campo}:${atual === campo && dir === 'asc' ? 'desc' : 'asc'}`;
  renderizar();
}

/* ---------- montagem ---------- */

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/conexoes' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho(t('conexoes.titulo'));
}

function traduzirEstaticos() {
  aplicar(document);
  const busca = porId('lista-busca');
  const rotulo = t('conexoes.buscar');
  busca.querySelector('label').textContent = rotulo;
  busca.querySelector('input').setAttribute('aria-label', rotulo);
  document.title = `${t('conexoes.titulo')} · ${t('app.nome')}`;
}

function ligarControles() {
  s.form = porId('conexao-form');
  s.form.addEventListener('enviar', (ev) => salvar(ev.detail.valores));
  s.form.addEventListener('botao', (ev) => { if (ev.detail.id === 'cancelar') fecharFormulario(); });
  const nova = porId('conexao-nova');
  nova.hidden = !podeCriar();
  nova.addEventListener('click', () => abrirFormulario());
  porId('lista-recarregar').addEventListener('click', () => carregar());
  porId('lista-busca').addEventListener('buscar', (ev) => { s.busca = ev.detail.q; renderizar(); });
  porId('lista-estado').addEventListener('acao', (ev) => {
    if (ev.detail.id === 'nova') abrirFormulario();
    else if (ev.detail.id === 'limpar-busca') { porId('lista-busca').valor = ''; s.busca = ''; renderizar(); }
    else if (ev.detail.id === 'tentar') carregar();
  });
  for (const th of document.querySelectorAll('#lista th[data-campo]')) {
    th.addEventListener('click', () => ordenarPor(th.dataset.campo));
    th.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ordenarPor(th.dataset.campo); }
    });
  }
  // aoTraduzir roda já na inscrição: a primeira chamada é pulada (a lista ainda não foi lida)
  let primeira = true;
  aoTraduzir(() => { if (primeira) { primeira = false; return; } traduzirEstaticos(); renderizar(); });
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { saindo = true; irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
    const destino = caminhoPendencia(usuario.pendencias);
    if (destino) { saindo = true; location.replace(destino); return; }
  } else {
    aviso('aviso', t('conexoes.sessao_indisponivel', { status: r.status }), 'atencao');
  }
  s.usuario = usuario;
  layout(usuario);
  traduzirEstaticos();
  ligarControles();
  await carregar();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', t('conexoes.erro_tela', { status: (e && e.status) || 'rede', erro: (e && e.message) || e }));
} finally {
  if (!saindo) pronto();
}
