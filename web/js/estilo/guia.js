/* plat · guia de estilo (/estilo-guia, item UX-01-sistema-de-design). Renderiza de verdade, com os tokens vivos, toda
   variação do sistema de design: tokens (cor com razão de contraste calculada no navegador, tipo, espaço, raio, sombra,
   foco) e componentes (botão, campo, seletor, tabela, painel, diálogo, notificação, estados, aviso, marcador, abas,
   paginação). É a referência viva: o que aparece aqui é o que o produto usa. O e2e (tests/e2e/test_estilo_guia.py)
   confere contagens, roda o axe nos dois temas e prova que trocar um token muda todas as telas. Sem HTML em string. */
import '../base/componentes.js';
import { confirmar, notificar } from '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const CORES = ['fundo', 'painel', 'painel-2', 'painel-3', 'borda', 'borda-forte', 'texto', 'fraco', 'acento', 'acento-texto', 'ok', 'atencao', 'falha', 'info', 'selecao', 'veu'];
const TEXTOS = ['texto', 'fraco', 'acento', 'ok', 'atencao', 'falha', 'info'];
const TIPOS = ['t-3', 't-2', 't-1', 't0', 't1', 't2', 't3', 't4'];
const ESPACOS = ['e0', 'e1', 'e2', 'e3', 'e4', 'e5', 'e6'];

const raiz = document.getElementById('guia');
const estilo = () => getComputedStyle(document.documentElement);
const token = (nome) => estilo().getPropertyValue(`--${nome}`).trim();

/* razão de contraste WCAG 2.x a partir da cor calculada pelo navegador (rgb/rgba); alfa é composta sobre o fundo */
function canal(c) { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }
function rgb(texto) {
  const m = /rgba?\(([^)]+)\)/.exec(texto);
  if (!m) return null;
  const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
  return { r: p[0], g: p[1], b: p[2], a: p[3] === undefined ? 1 : p[3] };
}
function compor(frente, fundo) {
  const a = frente.a;
  return { r: frente.r * a + fundo.r * (1 - a), g: frente.g * a + fundo.g * (1 - a), b: frente.b * a + fundo.b * (1 - a), a: 1 };
}
function luminancia(c) { return 0.2126 * canal(c.r) + 0.7152 * canal(c.g) + 0.0722 * canal(c.b); }
export function contraste(frente, fundo) {
  const f = compor(frente, fundo);
  const l1 = luminancia(f); const l2 = luminancia(fundo);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
function corCalculada(nome, propriedade = 'background-color') {
  const sonda = h('span', { class: 'sonda' });
  sonda.style.setProperty(propriedade, `var(--${nome})`);
  document.body.append(sonda);
  const v = getComputedStyle(sonda).getPropertyValue(propriedade);
  sonda.remove();
  return rgb(v);
}

function secao(id, chave, ...filhos) {
  return h('section', { class: 'cartao guia-secao', id: `sec-${id}`, 'aria-labelledby': `t-${id}` }, h('h2', { id: `t-${id}` }, t(chave)), ...filhos);
}

function secaoTokens() {
  const fundoPainel = corCalculada('painel');
  const cores = h('div', { class: 'amostras' });
  for (const nome of CORES) {
    const amostra = h('div', { class: 'amostra', dataset: { token: nome } });
    amostra.style.setProperty('--amostra', `var(--${nome})`);
    const linha = [h('code', {}, `--${nome}`), h('span', { class: 'fraco valor-token' }, token(nome))];
    if (TEXTOS.includes(nome)) {
      const razao = contraste(corCalculada(nome), fundoPainel);
      linha.push(h('span', { class: `marcador ${razao >= 4.5 ? 'ok' : 'falha'}`, dataset: { contraste: razao.toFixed(2) } }, `${razao.toFixed(2)}:1`));
    }
    cores.append(h('div', { class: 'amostra-par' }, amostra, h('div', { class: 'amostra-info' }, ...linha)));
  }
  const tipos = h('div', { class: 'escala-tipo' });
  for (const nome of TIPOS) {
    const ex = h('p', { class: 'exemplo-tipo' }, `${t('guia.exemplo')} — ${nome} = ${token(nome)}`);
    ex.style.setProperty('font-size', `var(--${nome})`);
    tipos.append(ex);
  }
  tipos.append(h('p', { class: 'exemplo-tipo titulo-exemplo' }, 'Big Shoulders Display — título'), h('p', { class: 'exemplo-tipo mono' }, 'IBM Plex Mono — 0123456789 dado'));
  const espacos = h('div', { class: 'escala-espaco' });
  for (const nome of ESPACOS) {
    const barra = h('span', { class: 'barra-espaco' });
    barra.style.setProperty('width', `var(--${nome})`);
    espacos.append(h('div', { class: 'linha-espaco' }, h('code', {}, `--${nome}`), barra, h('span', { class: 'fraco' }, token(nome))));
  }
  const forma = h('div', { class: 'forma' },
    h('div', { class: 'caixa-forma raio' }, `--raio ${token('raio')}`),
    h('div', { class: 'caixa-forma pilula' }, `--raio-pilula`),
    h('div', { class: 'caixa-forma sombra' }, `--sombra`),
    h('div', { class: 'caixa-forma sombra-1' }, `--sombra-1`),
    h('button', { type: 'button', class: 'foco-exemplo' }, `--foco (Tab até aqui)`));
  return secao('tokens', 'guia.tokens',
    h('h3', {}, t('guia.cores')), h('p', { class: 'fraco' }, t('guia.contraste')), cores,
    h('h3', {}, t('guia.tipografia')), tipos,
    h('h3', {}, t('guia.espaco')), espacos,
    h('h3', {}, t('guia.raio_sombra_foco')), forma);
}

function secaoBotoes() {
  const b = (classe, chave, extra = {}) => h('button', { type: 'button', class: classe, ...extra }, t(chave));
  return secao('botoes', 'guia.botoes', h('div', { class: 'botoes' },
    b('', 'guia.padrao'), b('primario', 'guia.primario'), b('perigo', 'guia.perigo'), b('texto', 'guia.texto'),
    b('pequeno', 'guia.pequeno'), b('', 'guia.desabilitado', { disabled: true }), b('', 'guia.pressionado', { 'aria-pressed': 'true' }),
    h('a', { class: 'botao', href: '#sec-botoes' }, 'link.botao')));
}

function secaoCampos() {
  const form = h('plat-formulario', { id: 'form-guia' });
  form.campos = [
    { nome: 'texto', rotulo: t('guia.campo_texto'), tipo: 'texto', obrigatorio: true, ajuda: t('guia.campo_ajuda'), padrao: 'valor' },
    { nome: 'invalido', rotulo: t('guia.campo_invalido'), tipo: 'texto', padrao: 'a b c!' },
    { nome: 'senha', rotulo: t('guia.campo_senha'), tipo: 'senha', padrao: 'segredo' },
    { nome: 'numero', rotulo: t('guia.campo_numero'), tipo: 'numero', padrao: 42 },
    { nome: 'seletor', rotulo: t('guia.seletor'), tipo: 'select', opcoes: [1, 2, 3].map((n) => ({ valor: String(n), rotulo: t('guia.seletor_opcao', { n }) })), padrao: '2' },
    { nome: 'caixa', rotulo: t('guia.campo_caixa'), tipo: 'caixa', padrao: true },
    { nome: 'area', rotulo: t('guia.campo_area'), tipo: 'area', padrao: 'linha 1\nlinha 2' },
    { nome: 'desabilitado', rotulo: t('guia.campo_desabilitado'), tipo: 'texto', padrao: 'fixo', desabilitado: true },
  ];
  form.botoes = [{ id: 'enviar', rotulo: t('guia.primario'), tipo: 'submit' }, { id: 'cancelar', rotulo: t('dialogo.cancelar') }];
  form.addEventListener('enviar', (e) => { e.preventDefault(); notificar(t('guia.toast_texto_ok'), { tipo: 'ok' }); });
  queueMicrotask(() => form.erro('invalido', t('guia.campo_erro')));
  return secao('campos', 'guia.campos', form);
}

function secaoTabela() {
  const tabela = h('plat-tabela', { legenda: t('guia.tabela') });
  tabela.colunas = [
    { chave: 'nome', titulo: t('guia.tabela_nome') },
    { chave: 'tipo', titulo: t('guia.tabela_tipo'), formatar: (v) => h('span', { class: 'marcador info' }, v) },
    { chave: 'quando', titulo: t('guia.tabela_quando'), classe: 'mono' },
    { chave: 'n', titulo: t('guia.tabela_n'), classe: 'num' },
  ];
  tabela.selecionavel = true;
  tabela.acoes = () => [{ id: 'abrir', rotulo: t('guia.tabela_acao') }];
  tabela.linhas = [1, 2, 3].map((i) => ({ id: i, nome: `${t('guia.exemplo')} ${i}`, tipo: 'camada', quando: `2026-09-0${i} 10:0${i}`, n: i * 1234 }));
  tabela.addEventListener('acao', (e) => notificar(`${e.detail.id}: ${e.detail.linha.nome}`));
  const vazia = h('plat-tabela', { legenda: t('guia.tabela_vazia') });
  vazia.colunas = [{ chave: 'nome', titulo: t('guia.tabela_nome') }];
  vazia.linhas = [];
  return secao('tabela', 'guia.tabela', tabela, h('h3', { class: 'espaco' }, t('guia.tabela_vazia')), vazia,
    h('h3', { class: 'espaco' }, t('guia.abas')), h('plat-paginacao', { id: 'pag-guia' }));
}

function secaoPainel() {
  const p = h('plat-painel', { titulo: t('guia.painel_titulo'), recolhivel: '', fechavel: '', id: 'painel-guia' },
    h('button', { type: 'button', class: 'pequeno', slot: 'acoes' }, t('guia.painel_acao')),
    h('p', {}, t('guia.painel_corpo')),
    h('button', { type: 'button', class: 'pequeno primario', slot: 'rodape' }, t('guia.primario')));
  p.addEventListener('fechar', () => setTimeout(() => p.abrir(), 800));
  return secao('painel', 'guia.painel', h('div', { class: 'grade-paineis' }, p,
    h('plat-painel', { titulo: t('guia.tabela'), denso: '' }, h('p', { class: 'fraco' }, t('guia.painel_corpo')))));
}

function secaoDialogo() {
  const dlg = document.getElementById('dialogo');
  const lateral = document.getElementById('dialogo-lateral');
  const b1 = h('button', { type: 'button', id: 'abrir-dialogo' }, t('guia.abrir_dialogo'));
  b1.addEventListener('click', () => dlg.abrir({ titulo: t('guia.dialogo_titulo'), corpo: h('p', {}, t('guia.dialogo_texto')), botoes: [{ id: 'ok', rotulo: t('dialogo.confirmar'), classe: 'primario' }] }));
  const b2 = h('button', { type: 'button', id: 'abrir-lateral' }, t('guia.abrir_lateral'));
  b2.addEventListener('click', () => lateral.abrir({ titulo: t('guia.dialogo_titulo'), corpo: h('p', {}, t('guia.dialogo_texto')), botoes: [{ id: 'fechar', rotulo: t('dialogo.fechar') }] }));
  const b3 = h('button', { type: 'button', class: 'perigo', id: 'abrir-confirmar' }, t('guia.confirmar_perigo'));
  b3.addEventListener('click', async () => { const ok = await confirmar(t('guia.dialogo_titulo'), t('guia.dialogo_texto'), { perigo: true }); notificar(String(ok), { tipo: ok ? 'ok' : 'info' }); });
  return secao('dialogo', 'guia.dialogo', h('div', { class: 'botoes' }, b1, b2, b3));
}

function secaoToast() {
  const b = (id, chave, fn) => { const x = h('button', { type: 'button', id }, t(chave)); x.addEventListener('click', fn); return x; };
  return secao('toast', 'guia.toast', h('div', { class: 'botoes' },
    b('toast-ok', 'guia.toast_ok', () => notificar(t('guia.toast_texto_ok'), { tipo: 'ok' })),
    b('toast-erro', 'guia.toast_erro', () => notificar(t('guia.toast_texto_erro'), { tipo: 'erro' })),
    b('toast-acao', 'guia.toast_acao', async () => { const r = await notificar(t('guia.toast_texto_acao'), { tipo: 'info', acoes: [{ id: 'desfazer', rotulo: t('guia.desfazer') }] }); if (r) notificar(t('guia.desfazer'), { tipo: 'ok' }); })));
}

function secaoEstados() {
  const grade = h('div', { class: 'grade-estados' });
  for (const tipo of ['vazio', 'carregando', 'erro', 'negado']) {
    const e = h('plat-estado', { id: `estado-${tipo}` });
    grade.append(h('div', {}, h('h3', {}, tipo), e));
    queueMicrotask(() => {
      if (tipo === 'erro') e.erro({ status: 500, json: { mensagem: t('guia.toast_texto_erro'), req_id: 'a1b2c3d4' } });
      else if (tipo === 'negado') e.negado(t('guia.estado_negado_texto'));
      else if (tipo === 'carregando') e.carregando();
      else e.vazio(undefined, [{ id: 'criar', rotulo: t('guia.primario'), classe: 'primario' }]);
    });
    e.addEventListener('acao', (ev) => notificar(ev.detail.id));
  }
  return secao('estados', 'guia.estados', grade);
}

function secaoAvisos() {
  const avisos = h('div', { class: 'grade-avisos' });
  for (const tipo of ['info', 'ok', 'atencao', 'erro']) {
    const a = h('plat-aviso', { id: `aviso-${tipo}` });
    avisos.append(a);
    queueMicrotask(() => a.mostrar(t(`guia.aviso_${tipo}`), tipo));
  }
  const marcadores = h('div', { class: 'botoes' }, ...['', 'ok', 'falha', 'atencao', 'info'].map((c) => h('span', { class: `marcador ${c}`.trim() }, `${t('guia.marcador')} ${c}`.trim())));
  const abas = h('div', { class: 'abas', role: 'tablist' }, ...['aba_1', 'aba_2', 'aba_3'].map((k, i) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(i === 0), tabindex: i === 0 ? '0' : '-1' }, t(`guia.${k}`))));
  abas.addEventListener('click', (e) => { const b = e.target.closest('[role=tab]'); if (!b) return; abas.querySelectorAll('[role=tab]').forEach((x) => { x.setAttribute('aria-selected', String(x === b)); x.tabIndex = x === b ? 0 : -1; }); });
  return secao('avisos', 'guia.avisos', avisos, h('h3', { class: 'espaco' }, t('guia.marcador')), marcadores, h('h3', { class: 'espaco' }, t('guia.abas')), abas);
}

function render() {
  limpar(raiz);
  raiz.append(secaoTokens(), secaoBotoes(), secaoCampos(), secaoTabela(), secaoPainel(), secaoDialogo(), secaoToast(), secaoEstados(), secaoAvisos());
  document.getElementById('pag-guia').atualizar({ total: 123, limite: 50, deslocamento: 50 });
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/estilo-guia' });
  render();
  // tema trocado: as razões de contraste são recalculadas com as cores novas
  document.addEventListener('plat:tema', () => render());
  pronto();
}
