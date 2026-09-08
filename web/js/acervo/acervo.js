/* plat · acervo — entrada da tela /acervo (item L6-01-c-tela-acervo; equivalente do Living Atlas do Esri).
   Módulo ES sem build; cache resolvido por no-store no nginx: NUNCA ?v= nos imports (armadilha conhecida do
   laço). Lista `GET /api/acervo` (domínio + busca por nome/órgão), ficha completa `GET /api/acervo/{fonte_id}`,
   "adicionar ao meu mapa" `POST /api/acervo/{fonte_id}/adicionar` — cria item tipo `conexao`, nunca copia dado
   (regra do L6-01-a/b: publicação sem cópia). Regra D17 (repetida aqui): fonte sem licença ESCRITA nunca chega
   a esta tela — o backend já filtra; esta tela não tenta "completar" a lista com nada que a API não devolveu.
   body[data-pronto="1"] após a 1ª carga (contrato dos e2e, tests/e2e/apoio.py::Tela.ir).

   Item UX-10-acervo-sem-tela: os quatro estados do sistema de design (UX-01) na lista (<plat-estado id="lista-estado">:
   carregando com esqueleto, vazio com "limpar filtros", erro com "tentar de novo", negado) e no controle "adicionar ao
   meu mapa", que vive DENTRO da ficha com o seu próprio <plat-estado id="adicionar-estado">: 403 vira negado com o
   privilégio exigido, 409 vira o diálogo de confirmação de risco de dado pessoal, 413/422/5xx mostram a mensagem da
   API com a referência — nunca o número cru, nunca tela quebrada (refutação do item). Quem não tem
   conteudo.registrar_fonte vê o estado negado antes mesmo de clicar. */
import { confirmar } from '../base/componentes.js';
import { tem } from '../base/estado.js';
import { h, limpar, marcador } from '../base/dom.js';
import { carregar as carregarIdioma, t, formatarData, formatarNumero } from '../base/i18n.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao, irParaLogin } from '../auth/sessao.js';
import { obter, enviar, mensagemDe } from '../base/api.js';
import { exigeAtribuicao, rotuloLicenca } from './licencas.js';

const el = (id) => document.getElementById(id);
const LIMITE = 24;
let estado = { dominio: '', q: '', deslocamento: 0, total: 0 };
let dialogo;
let saindo = false;

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  try { await iniciar(); } catch (e) { if (!(e && e.status === 401)) el('aviso').erro(`${t('acervo.erro_listar')}: ${(e && e.message) || e}`); }
}
if (!saindo) pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/acervo' });
  cabecalho(t('acervo.titulo'));
  dialogo = el('ficha');
  montarBusca();
  montarEstadoLista();
  await montarDominios();
  montarPaginacao();
  await carregarLista();
}

function montarBusca() {
  const busca = el('busca');
  busca.addEventListener('buscar', (e) => {
    const q = e.detail.q;
    if (q === estado.q) return;
    estado = { ...estado, q, deslocamento: 0 };
    carregarLista();
  });
}

async function montarDominios() {
  const sel = el('dominio-filtro');
  limpar(sel);
  sel.append(h('option', { value: '' }, t('acervo.dominio_todos')));
  let dominios = [];
  try {
    const r = await obter('/api/acervo/dominios');
    if (r.status === 401) { aoSemSessao(); return; }
    if (r.status >= 400) throw new Error(mensagemDe(r));
    dominios = r.json || [];
  } catch (e) {
    el('aviso').erro(`${t('acervo.erro_dominios')}: ${e.message || e}`);
    return;
  }
  for (const d of dominios) {
    sel.append(h('option', { value: d.dominio }, `${d.dominio} (${formatarNumero(d.fontes)})`));
  }
  sel.addEventListener('change', () => {
    estado = { ...estado, dominio: sel.value, deslocamento: 0 };
    carregarLista();
  });
}

function montarPaginacao() {
  el('paginacao').addEventListener('mudar', (e) => {
    estado = { ...estado, deslocamento: e.detail.deslocamento };
    carregarLista();
  });
}

function aoSemSessao() { saindo = true; irParaLogin(); }

function limparFiltros() {
  estado = { ...estado, dominio: '', q: '', deslocamento: 0 };
  el('dominio-filtro').value = '';
  const campo = el('busca').querySelector('input');
  if (campo) campo.value = '';
  carregarLista();
}

function montarEstadoLista() {
  el('lista-estado').addEventListener('acao', (e) => {
    if (e.detail.id === 'limpar') limparFiltros();
    else if (e.detail.id === 'tentar') carregarLista();
  });
}

async function carregarLista() {
  const grade = el('grade');
  const estadoLista = el('lista-estado');
  limpar(grade);
  estadoLista.carregando(t('acervo.carregando'));
  grade.setAttribute('aria-busy', 'true');
  const q = new URLSearchParams();
  if (estado.dominio) q.set('dominio', estado.dominio);
  if (estado.q) q.set('q', estado.q);
  q.set('limite', String(LIMITE));
  q.set('deslocamento', String(estado.deslocamento));
  let pagina;
  const r = await obter(`/api/acervo?${q.toString()}`);
  grade.setAttribute('aria-busy', 'false');
  if (r.status === 401) { aoSemSessao(); return; }
  if (r.status >= 400 || r.status === 0) {
    // 403 vira "negado" e 0 vira "sem rede" dentro do próprio componente; o resto é erro com referência
    estadoLista.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]);
    el('contagem').textContent = '';
    return;
  }
  pagina = r.json;
  estado = { ...estado, total: pagina.total };
  el('contagem').textContent = t('acervo.contagem', { n: formatarNumero(pagina.total) });
  el('paginacao').atualizar({ total: pagina.total, limite: LIMITE, deslocamento: estado.deslocamento });
  limpar(grade);
  if (!pagina.itens.length) {
    const filtrado = !!(estado.dominio || estado.q);
    estadoLista.mostrar({
      tipo: 'vazio',
      titulo: t('acervo.vazio_titulo'),
      texto: estado.dominio && !estado.q ? t('acervo.dominio_vazio') : t('acervo.vazio'),
      acoes: filtrado ? [{ id: 'limpar', rotulo: t('acervo.limpar_filtros') }] : [],
    });
  } else {
    estadoLista.limpar();
    for (const item of pagina.itens) grade.append(cartao(item));
  }
}

// O cartão traz uma ETIQUETA curta de licença; o texto livre de `licenca` (às vezes uma frase inteira do órgão)
// fica no atributo title e completo na ficha. Etiqueta é rótulo, não parágrafo: com a frase dentro dela o cartão
// deixava de caber num visor de celular (medido: corpo de 729 px num visor de 390 px).
function marcadorLicenca(item) {
  const curada = rotuloLicenca(item.licenca_curada_tipo);
  const m = marcador(
    curada || (item.licenca ? t('acervo.licenca_texto_livre') : t('acervo.licenca_nao_declarada')),
    exigeAtribuicao(item.licenca_curada_tipo) ? 'atencao' : 'ok',
  );
  if (!curada && item.licenca) m.title = item.licenca;
  return m;
}

function cartao(item) {
  const b = h('button', { type: 'button', class: 'acervo-cartao', 'data-fonte-id': item.fonte_id }, [
    h('h2', {}, item.nome),
    h('p', { class: 'acervo-cartao-orgao' }, item.orgao || '—'),
    h('div', { class: 'acervo-cartao-marcadores' }, [
      marcador(item.dominio, 'info'),
      marcadorLicenca(item),
    ]),
    h('p', { class: 'acervo-cartao-linha' }, `${t('acervo.frescor')}: ${item.frescor || t('acervo.frescor_nao_registrado')}`),
    h('p', { class: 'acervo-cartao-linha' }, `${t('acervo.registros')}: ${formatarNumero(item.registros_estimados)} · ${t('acervo.tabelas')}: ${formatarNumero(item.numero_tabelas)}`),
  ]);
  b.addEventListener('click', () => abrirFicha(item.fonte_id));
  return b;
}

function campo(rotulo, valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  return h('div', { class: 'acervo-campo' }, h('dt', {}, rotulo), h('dd', {}, valor));
}

async function abrirFicha(fonteId) {
  let ficha;
  try {
    const r = await obter(`/api/acervo/${encodeURIComponent(fonteId)}`);
    if (r.status === 401) { aoSemSessao(); return; }
    if (r.status === 404) { el('aviso').erro(t('acervo.erro_ficha')); return; }
    if (r.status >= 400) throw new Error(mensagemDe(r));
    ficha = r.json;
  } catch (e) {
    el('aviso').erro(`${t('acervo.erro_ficha')}: ${e.message || e}`);
    return;
  }

  const dl = h('dl', { class: 'acervo-ficha' }, [
    campo(t('acervo.orgao'), ficha.orgao),
    campo(t('acervo.dominio'), ficha.dominio),
    campo(t('acervo.licenca'), rotuloLicenca(ficha.licenca_curada_tipo) || ficha.licenca || t('acervo.licenca_nao_declarada')),
    campo(t('acervo.frescor'), ficha.frescor || t('acervo.frescor_nao_registrado')),
    campo(t('acervo.registros'), formatarNumero(ficha.registros_estimados)),
    campo(t('acervo.tabelas'), formatarNumero(ficha.numero_tabelas)),
    campo(t('acervo.data'), ficha.data_dado || t('acervo.data_nao_registrada')),
    campo(t('acervo.ficha_metodo'), ficha.metodo),
    campo(t('acervo.ficha_confianca'), ficha.confianca),
    campo(t('acervo.ficha_limites'), ficha.limites),
    campo(t('acervo.ficha_sha256'), ficha.sha256),
    campo(t('acervo.ficha_comando'), ficha.comando_reexecucao),
    campo(t('acervo.ficha_proxima_verificacao'), ficha.proxima_verificacao ? formatarData(ficha.proxima_verificacao, true) : null),
    campo(t('acervo.ficha_completude'), ficha.completude_texto || t('acervo.ficha_completude_nao_registrada')),
    campo(t('acervo.ficha_endpoints'), `${formatarNumero(ficha.endpoints_confirmados_vivos)} / ${formatarNumero(ficha.endpoints_total)}`),
  ].filter(Boolean));

  const corpo = h('div', {}, [
    dl,
    exigeAtribuicao(ficha.licenca_curada_tipo)
      ? h('p', { class: 'acervo-atribuicao', role: 'note' }, t('acervo.atribuicao_obrigatoria', { licenca: ficha.licenca_curada_tipo }))
      : null,
    h('h3', {}, t('acervo.ficha_previsualizacao')),
    previa(ficha),
    controleAdicionar(ficha),
  ].filter(Boolean));

  await dialogo.abrir({ titulo: `${t('acervo.ficha_titulo')} — ${ficha.nome}`, corpo, botoes: [] });
}

/* o controle da rota de escrita POST /api/acervo/{fonte_id}/adicionar (UX-10): botão + estado próprio, dentro
   da ficha, que fica aberta enquanto a chamada corre e enquanto houver um erro a ler */
function controleAdicionar(ficha) {
  const estadoCtl = h('plat-estado', { id: 'adicionar-estado', hidden: true });
  const botao = h('button', { type: 'button', class: 'primario', id: 'acervo-adicionar', dataset: { id: 'adicionar' } }, t('acervo.adicionar'));
  const caixa = h('div', { class: 'acervo-adicionar' }, h('h3', {}, t('acervo.adicionar_titulo')), botao, estadoCtl);
  if (!tem('conteudo.registrar_fonte')) {
    botao.disabled = true;
    estadoCtl.negado(t('acervo.negado_registrar', { privilegio: 'conteudo.registrar_fonte' }));
    return caixa;
  }
  botao.addEventListener('click', () => adicionar(ficha, false, { botao, estadoCtl }));
  // "tentar de novo" do estado de erro: um ouvinte só, ligado uma vez (não um por erro)
  estadoCtl.addEventListener('acao', (e) => { if (e.detail.id === 'tentar') adicionar(ficha, false, { botao, estadoCtl }); });
  return caixa;
}

function previa(ficha) {
  const vivo = (ficha.endpoints || []).find((ep) => ep.vivo && ep.url);
  if (!vivo) return h('p', { class: 'acervo-previa-vazia' }, t('acervo.previsualizacao_sem_endpoint'));
  return h('p', {}, h('a', { href: vivo.url, target: '_blank', rel: 'noopener noreferrer' }, vivo.url));
}

async function adicionar(ficha, confirmaPii = false, { botao, estadoCtl } = {}) {
  const corpo = confirmaPii ? { confirma_risco_pii: true } : undefined;
  if (botao) { botao.disabled = true; botao.setAttribute('aria-busy', 'true'); }
  estadoCtl?.carregando(t('acervo.adicionar_carregando'));
  const r = await enviar(`/api/acervo/${encodeURIComponent(ficha.fonte_id)}/adicionar`, corpo);
  if (botao) { botao.disabled = false; botao.removeAttribute('aria-busy'); }
  if (r.status === 401) { aoSemSessao(); return; }
  if (r.status === 409 && r.json && r.json.erro === 'confirmacao_pii_exigida') {
    estadoCtl?.limpar();
    const ok = await confirmar(
      t('acervo.pii_confirma_titulo'),
      (r.json.detalhe && r.json.detalhe.risco_pii_motivo) || t('acervo.risco_pii'),
      { ok: t('acervo.pii_confirmar'), perigo: true },
    );
    if (ok) await adicionar(ficha, true, { botao, estadoCtl });
    return;
  }
  if (r.status === 403) {
    // negado, com o privilégio que falta nomeado (o detalhe da API traz `exigido`)
    const exigido = (r.json && r.json.detalhe && r.json.detalhe.exigido) || 'conteudo.registrar_fonte';
    estadoCtl?.negado(`${r.json?.mensagem || t('estado.negado_texto')} (${exigido})`);
    if (botao) botao.disabled = true;
    return;
  }
  if (r.status >= 400 || r.status === 0) {
    // 413 cota, 422 corpo, 404 fonte, 5xx: a mensagem da API nomeada e a referência, no próprio controle
    estadoCtl?.erro(r, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo') }]);
    return;
  }
  estadoCtl?.limpar();
  dialogo.fechar('adicionado');
  const aviso = el('aviso');
  limpar(aviso);
  aviso.dataset.tipo = 'ok';
  aviso.setAttribute('role', 'status');
  aviso.hidden = false;
  aviso.append(`${t('acervo.adicionar_ok')} — `, h('a', { href: '/mapa', id: 'acervo-ver-no-mapa' }, t('acervo.ver_no_mapa')));
}
