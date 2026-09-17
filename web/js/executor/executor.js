/* plat — executor: renderiza um documento `app` (paleta de páginas e layout, `paleta_paginas.js`) como um
   APLICATIVO DE VERDADE navegável, item L5-01-a-layout-paginas.

   Diferença para `web/js/editor/editor.js`: o editor desenha CAIXAS GENÉRICAS de arrasto (todo nó é o mesmo
   quadrado com título e alça); o executor desenha o que cada tipo SIGNIFICA em produção — página cheia ou
   rolável, menu de verdade, painel lateral que recolhe, janela que abre e fecha. Os dois lêem o MESMO
   documento e a MESMA paleta; nenhum dos dois conhece o outro.

   Roteamento: a URL de execução é `/executar?item=<id>&pagina=<caminho>` (querystring, não segmento de
   caminho — mesma convenção de `/construtor?item=<id>` do L5-08; ver ADR desta entrega). Trocar de página
   muda a querystring com `history.pushState` (sem recarregar) e o back/forward do navegador funciona via
   `popstate`; abrir a URL direto (ou dar F5) lê `pagina` de nada além da própria URL — não há estado de
   sessão envolvido em qual página abre. */
import { h, limpar } from '../base/dom.js';
import * as doc from '../editor/documento.js';
import { paginas, paginasNoMenu, paginaPorCaminho, paginaInicial } from './paginas.js';
import { REGISTRO } from '../widgets/registro.js';
import { BarramentoWidgets, montarWidgets } from '../widgets/motor.js';
import { icone } from '../base/icones.js';

/* --- widgets da tela (item L5-01-d-widgets-pagina-menu) --------------------------------------------------
   Um nó da paleta de páginas PODE ser também um widget do motor (REGISTRO, `../widgets/registro.js`): o
   executor carregaria o módulo dele aqui, antes do primeiro desenho, para que um módulo que falhe vire uma
   caixa de erro nomeada — não uma tela morta (mesmo raciocínio do carregador interno de `widgets/motor.js`).
   A API antiga que esta função usava (REGISTRO/carregarModulos/criarWidget importados de `widgets/motor.js`)
   não existe mais: `git log -S prepararWidgets --all -- web/js/executor/executar_tela.js web/js/widgets/motor.js
   web/js/executor/executor.js` só acha os commits f3a286696/b6f9e3f69 (07/09), e a fusão que uniu os ramos
   depois disso descartou as mudanças de f3a286696 neste arquivo (nenhum commit de `executor.js` na história
   do ramo atual além da criação, item L5-01-a) enquanto manteve o import quebrado que b6f9e3f69 introduziu em
   `executar_tela.js`. Hoje o motor expõe `BarramentoWidgets`/`montarWidgets` (web/js/widgets/motor.js), e é
   sobre eles que esta versão está escrita: reusa o PRÓPRIO carregador de `montarWidgets` contra um documento
   sintético só com os tipos candidatos, montado num elemento nunca preso ao DOM (nunca fica visível nem
   dispara efeito nenhum — só devolve `falhas`, o mapa tipo→mensagem que a chamadora usa).

   Restaurado em 15/09/2026: o lote L5-01-d (`botão, cartão, incorporar, divisor, menu de widget,
   controlador, compartilhar, login, idioma, tema`) voltou a `editor/paleta_paginas.js` e a
   `widgets/registro.js` — nove tipos batem por NOME entre os dois catálogos e entram abaixo. Os que colidem
   por acaso (`texto`, `imagem`, `mapa`, `tabela`) continuam DE FORA de propósito: são esquemas DIFERENTES do
   executor (desenhados por `desenharNo`, nunca pelo motor) — casar por nome seria falso positivo, carregaria
   `widgets/mapa.js` (que puxa o MapLibre) toda vez que a página tivesse uma caixa de mapa que nem usa o
   motor. O menu de widget é o mesmo caso por um motivo a mais: o tipo de PÁGINA se chama `menu_widget` na
   paleta (para não pisar no `menu` de navegação entre páginas, que já existe e é um esquema à parte — ver
   `desenharMenu` abaixo), enquanto o manifesto do motor continua se chamando `menu` (nome do módulo/i18n,
   `widgets/registro.js`); os dois nomes não batem de propósito, então `menu_widget` também fica fora desta
   lista.

   Completado em 16/09/2026 (resto do L5-01-d apontado pelo worker dos widgets): `desenharNo` agora MONTA
   os nove pelo motor de verdade (`desenharWidgetPagina` abaixo). Os módulos já foram importados por
   `prepararWidgets` ANTES desta função rodar (`executar_tela.js` sempre chama as duas nesta ordem) — então
   o custom element já está registrado em `customElements` e `document.createElement(manifesto.elemento)`
   aqui é síncrono, sem novo `import()`. `no.propriedades` (paleta) e `configuracao` (manifesto) usam o
   MESMO vocabulário de propósito (comentário de `paleta_paginas.js`), então não há tradução nenhuma. Um
   `BarramentoWidgets` por PÁGINA (não por execução inteira — cada `desenhar()` cria o dele, ver
   `criarContextoWidgets`) liga `documento.corpo.ligacoes` entre os widgets da mesma página, igual
   `widgets/motor.js::montarWidgets`; `dataset.noId` no elemento é a MESMA convenção que o motor já usa
   nos widgets do `/aplicativo` (`plat-tabela[data-no-id=...]`, ver `test_widgets_dado.py`), o que também é
   o que `widgets/controlador.js::_alvo` já lê. Navegação por `botao`/`cartao` com `acao.tipo === 'pagina'`
   não precisa de ligação: o próprio `emitir()` de `base.js` despacha um `CustomEvent` nativo (bubbles),
   então basta ouvir `botao.pagina`/`cartao.pagina` no elemento e chamar `irPara`. Módulo que falhou no
   preload (`falhas`, mapa tipo→mensagem) vira caixa de erro nomeada em vez do widget morto — mesma regra
   de `widgets/motor.js::erroWidget`. ATENÇÃO: `menu_widget` continua de propósito fora de `TIPOS_WIDGET_PAGINA`
   (nome não bate com o `menu` do registro) — segue caindo em `exec-desconhecido`, sem mudança aqui. */
const TIPOS_WIDGET_PAGINA = new Set([
  'botao', 'cartao', 'incorporar', 'divisor', 'controlador', 'compartilhar', 'login', 'idioma', 'tema',
]);

export function tiposDeWidget(documento) {
  return [...new Set(doc.nos(documento).map((n) => n.tipo))].filter((t) => TIPOS_WIDGET_PAGINA.has(t) && REGISTRO.has(t));
}

export async function prepararWidgets(documento) {
  const tipos = tiposDeWidget(documento);
  if (!tipos.length) return new Map();
  const docSintetico = { corpo: { nos: tipos.map((tipo) => ({ id: tipo, tipo, configuracao: {} })), fontes: [], vistas: [], ligacoes: [] } };
  const { falhas } = await montarWidgets(document.createElement('div'), docSintetico, { barramento: new BarramentoWidgets(), carregarFontes: false });
  return falhas;
}

/* um `BarramentoWidgets` + mapa `id do nó → instância` por PÁGINA desenhada (recriado a cada `desenhar()`,
   nunca reusado entre páginas: um widget de uma página que já saiu de cena não é alvo válido de ligação
   nem de controlador). Escuta `documento.corpo.ligacoes` com a MESMA regra de `widgets/motor.js::montarWidgets`
   (origem+evento→alvo+ação), para o dia em que um documento de páginas gravar ligações entre estes widgets. */
export function criarContextoWidgets(documento, falhas) {
  const barramento = new BarramentoWidgets();
  const instancias = new Map();
  barramento.addEventListener('evento', ({ detail }) => {
    for (const ligacao of documento?.corpo?.ligacoes || []) {
      if (ligacao.origem !== detail.origem || (ligacao.evento && ligacao.evento !== detail.nome)) continue;
      const alvo = instancias.get(ligacao.alvo);
      const manifesto = alvo && REGISTRO.get(alvo.dataset.tipo);
      const acao = ligacao.acao || detail.nome;
      if (alvo && manifesto?.acoes.includes(acao)) alvo.executar(acao, detail.detalhe);
    }
  });
  return { barramento, instancias, falhas };
}

const PARAM_PAGINA = 'pagina';

export function caminhoDaUrl(url = location.href) {
  return new URL(url).searchParams.get(PARAM_PAGINA) || '';
}

function urlComPagina(caminho) {
  const u = new URL(location.href);
  if (caminho) u.searchParams.set(PARAM_PAGINA, caminho);
  else u.searchParams.delete(PARAM_PAGINA);
  return u;
}

/* devolve a página ativa para o documento e a URL atual: pelo caminho da querystring quando existe e é de
   uma página real; senão a página inicial (regra em `paginas.js`). */
export function paginaAtiva(documento, url = location.href) {
  const caminho = caminhoDaUrl(url);
  if (caminho) {
    const p = paginaPorCaminho(documento, caminho);
    if (p) return p;
  }
  return paginaInicial(documento);
}

export function montarExecucao({ raiz, documento, paleta, falhas = new Map() }) {
  let doAtiva = null;

  function irPara(caminho, { substituir = false } = {}) {
    const u = urlComPagina(caminho);
    if (substituir) history.replaceState({}, '', u);
    else history.pushState({}, '', u);
    desenhar();
  }

  function desenhar() {
    limpar(raiz);
    const pagina = paginaAtiva(documento, location.href);
    doAtiva = pagina;
    if (!pagina) { raiz.append(h('p', { class: 'exec-vazio' }, 'este aplicativo ainda não tem nenhuma página')); return; }
    const props = pagina.propriedades || {};
    const telaCheia = props.tipo_pagina === 'tela_cheia';
    const container = h('div', {
      class: `exec-pagina exec-pagina-${telaCheia ? 'tela-cheia' : 'rolavel'}`,
      dataset: { pagina: props.caminho, tipoPagina: props.tipo_pagina },
    });
    const ctxWidgets = criarContextoWidgets(documento, falhas);
    for (const filho of doc.filhos(documento, pagina.id)) container.append(desenharNo(filho, documento, paleta, irPara, ctxWidgets));
    raiz.append(container);
    document.title = props.titulo ? `${props.titulo} · plat` : document.title;
  }

  window.addEventListener('popstate', desenhar);
  desenhar();

  return {
    irPara,
    paginaAtiva: () => doAtiva,
    redesenhar(novoDocumento) { documento = novoDocumento; desenhar(); },
  };
}

/* ---------------------------------------------------------------- despacho por tipo (a única função com
   `if (tipo === ...)` do executor — o resto é genérico, igual ao editor). Nenhum tipo desconhecido explode: o
   executor desenha uma caixa com o rótulo, para um widget novo da paleta nunca sumir da tela em silêncio.
   `ctxWidgets` ({barramento, instancias, falhas} de `criarContextoWidgets`) é opcional (default vazio) só
   para quem chama `desenharNo` isolado (teste unitário) sem passar por `montarExecucao`. */
export function desenharNo(no, documento, paleta, irPara, ctxWidgets = criarContextoWidgets(documento, new Map())) {
  const def = paleta.tipos[no.tipo] || { rotulo: no.tipo };
  const filhos = () => doc.filhos(documento, no.id).map((f) => desenharNo(f, documento, paleta, irPara, ctxWidgets));
  switch (no.tipo) {
    case 'cabecalho': return caixa(no, 'header', 'exec-cabecalho', filhos, { dataset: { fixo: String(!!no.propriedades?.fixo) } });
    case 'rodape': return caixa(no, 'footer', 'exec-rodape', filhos);
    case 'menu': return desenharMenu(no, documento, irPara);
    case 'linha': return desenharLinha(no, documento, paleta, irPara, ctxWidgets);
    case 'coluna': return desenharColuna(no, documento, paleta, irPara, ctxWidgets);
    case 'grade': return desenharGrade(no, documento, paleta, irPara, ctxWidgets);
    case 'acordeao': return desenharAcordeao(no, documento, paleta, irPara, ctxWidgets);
    case 'painel_fixo': return caixa(no, 'div', `exec-painel-fixo pos-${no.propriedades?.posicao || 'superior-direita'}`, filhos);
    case 'painel_lateral': return desenharPainelLateral(no, documento, paleta, irPara, ctxWidgets);
    case 'janela': return desenharJanela(no, documento, paleta, irPara, ctxWidgets);
    case 'secao_vistas': return desenharSecaoVistas(no, documento, paleta, irPara, ctxWidgets);
    case 'vista': return caixa(no, 'div', 'exec-vista', filhos);
    case 'grupo': return caixa(no, 'div', 'exec-grupo', filhos);
    case 'texto': return h('p', { class: `exec-texto exec-texto-${no.propriedades?.nivel || 'corpo'}`, dataset: { no: no.id, tipo: 'texto' } }, String(no.propriedades?.texto ?? ''));
    case 'imagem': return h('img', { class: 'exec-imagem', dataset: { no: no.id, tipo: 'imagem' }, src: no.propriedades?.url || '', alt: no.propriedades?.alternativo || '' });
    case 'mapa': return h('div', { class: 'exec-mapa', dataset: { no: no.id, tipo: 'mapa', zoom: String(no.propriedades?.zoom ?? '') } }, 'mapa (zoom inicial ' + (no.propriedades?.zoom ?? '-') + ')');
    case 'tabela': return h('div', { class: 'exec-tabela', dataset: { no: no.id, tipo: 'tabela' } }, `tabela (${no.propriedades?.linhas_por_pagina ?? '-'} linhas/página)`);
    // item L5-01-d (resto, 16/09): os nove widgets de página batem por nome com `widgets/registro.js` (ver
    // `TIPOS_WIDGET_PAGINA` acima) e são montados pelo motor de verdade, não pela caixa genérica.
    case 'botao': case 'cartao': case 'incorporar': case 'divisor': case 'controlador':
    case 'compartilhar': case 'login': case 'idioma': case 'tema':
      return desenharWidgetPagina(no, ctxWidgets, irPara);
    default: return caixa(no, 'div', 'exec-desconhecido', filhos, {}, def.rotulo);
  }
}

/* ---------------------------------------------------------------- widgets de página pelo motor (resto do
   L5-01-d): cria o CUSTOM ELEMENT de verdade (`REGISTRO.get(no.tipo).elemento`, já registrado em
   `customElements` porque `prepararWidgets` importou o módulo antes de `montarExecucao` chamar esta
   função), com `no.propriedades` como `configuracao` (mesmo vocabulário do manifesto, de propósito) e
   `dataset.noId`/`noId` na convenção que o motor já usa (`widgets/controlador.js::_alvo`, `plat-tabela
   [data-no-id=...]` do `/aplicativo`). Falha de carregamento (`ctxWidgets.falhas`) vira caixa de erro
   nomeada — nunca um elemento morto sem `.configuracao`/`.renderizar`. Navegação (`acao.tipo === 'pagina'`
   de botão/cartão) ouve o `CustomEvent` nativo que `base.js::emitir` já despacha (bubbles) e troca de
   página pelo MESMO `irPara` do menu — sem caminho de rota novo. */
function desenharWidgetPagina(no, ctxWidgets, irPara) {
  if (ctxWidgets.falhas.has(no.tipo)) {
    return h('section', { class: 'exec-widget-erro plat-widget-erro', dataset: { noId: no.id, tipo: no.tipo }, role: 'alert' },
      `Widget "${no.tipo}": ${ctxWidgets.falhas.get(no.tipo)}`);
  }
  const manifesto = REGISTRO.get(no.tipo);
  if (!manifesto) return caixa(no, 'div', 'exec-desconhecido', () => [], {}, no.tipo);
  const el = document.createElement(manifesto.elemento);
  el.noId = no.id;
  el.barramento = ctxWidgets.barramento;
  el.dataset.tipo = no.tipo;
  el.dataset.noId = no.id;
  el.configuracao = no.propriedades || {};
  el.addEventListener('botao.pagina', (ev) => irPara(String(ev.detail?.pagina || '')));
  el.addEventListener('cartao.pagina', (ev) => irPara(String(ev.detail?.pagina || '')));
  ctxWidgets.instancias.set(no.id, el);
  return el;
}

function caixa(no, tag, classe, filhosFn, extra = {}, rotuloDesconhecido = null) {
  const el = h(tag, { class: classe, dataset: { no: no.id, tipo: no.tipo }, ...extra });
  if (rotuloDesconhecido) el.append(h('span', { class: 'exec-rotulo-desconhecido' }, rotuloDesconhecido));
  el.append(...filhosFn());
  return el;
}

/* ---------------------------------------------------------------- menu: nav de verdade entre páginas do
   MESMO documento (não lê filho nenhum do próprio nó — a lista vem da raiz inteira, ver paginas.js) */
function desenharMenu(no, documento, irPara) {
  const estilo = no.propriedades?.estilo || 'horizontal';
  const nav = h('nav', { class: `exec-menu exec-menu-${estilo}`, dataset: { no: no.id, tipo: 'menu' }, 'aria-label': 'Navegação entre páginas' });
  const atual = caminhoDaUrl(location.href) || (paginaInicial(documento)?.propriedades || {}).caminho;
  for (const p of paginasNoMenu(documento)) {
    const caminho = (p.propriedades || {}).caminho;
    const a = h('a', {
      href: `?${new URLSearchParams({ ...Object.fromEntries(new URL(location.href).searchParams), pagina: caminho })}`,
      dataset: { irPagina: caminho },
      'aria-current': caminho === atual ? 'page' : undefined,
    }, (p.propriedades || {}).titulo || caminho);
    a.addEventListener('click', (ev) => { ev.preventDefault(); irPara(caminho); });
    nav.append(a);
  }
  return nav;
}

/* ---------------------------------------------------------------- linha/coluna: flex com proporção por
   `largura_colunas` (flex-grow), `min-width:0`/`min-height:0` para NUNCA estourar em aninhamento profundo
   (achado direto da refutação do adversário: sem isto, 6 níveis de linha/coluna vazam largura) */
function desenharLinha(no, documento, paleta, irPara, ctxWidgets) {
  const el = h('div', { class: `exec-linha alinhar-${no.propriedades?.alinhar || 'inicio'}`, dataset: { no: no.id, tipo: 'linha' } });
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara, ctxWidgets);
    filho.style.flex = `${Math.max(1, f.largura_colunas || 1)} 1 0`;
    filho.classList.add('exec-flex-item');
    el.append(filho);
  }
  return el;
}

function desenharColuna(no, documento, paleta, irPara, ctxWidgets) {
  const el = h('div', { class: `exec-coluna alinhar-${no.propriedades?.alinhar || 'inicio'}`, dataset: { no: no.id, tipo: 'coluna' } });
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara, ctxWidgets);
    filho.classList.add('exec-flex-item');
    el.append(filho);
  }
  return el;
}

/* ---------------------------------------------------------------- grade: CSS Grid `repeat(N, 1fr)` — a
   proporção entre dois filhos é uma razão de frações (fr), invariante à largura do contêiner por definição
   do próprio CSS Grid: é isso que a cláusula "grade responsiva mantém proporção" mede. */
function desenharGrade(no, documento, paleta, irPara, ctxWidgets) {
  const colunasGrade = Math.max(1, Math.min(12, no.propriedades?.colunas ?? 3));
  const el = h('div', { class: 'exec-grade', dataset: { no: no.id, tipo: 'grade', colunasGrade: String(colunasGrade) } });
  el.style.gridTemplateColumns = `repeat(${colunasGrade}, minmax(0, 1fr))`;
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara, ctxWidgets);
    const vaoSpan = Math.max(1, Math.min(colunasGrade, Math.round(((f.largura_colunas || doc.COLUNAS) / doc.COLUNAS) * colunasGrade)));
    filho.style.gridColumn = `span ${vaoSpan}`;
    filho.classList.add('exec-grade-item');
    el.append(filho);
  }
  return el;
}

/* ---------------------------------------------------------------- acordeão: um painel por filho; fecha os
   outros a não ser que `multiplo_aberto` — nunca usa `display:none` fixo no CABEÇALHO (só no CORPO), então
   nenhum painel vira um "widget oculto" que o adversário procura */
function desenharAcordeao(no, documento, paleta, irPara, ctxWidgets) {
  const multiplo = !!no.propriedades?.multiplo_aberto;
  const el = h('div', { class: 'exec-acordeao', dataset: { no: no.id, tipo: 'acordeao' } });
  const paineis = doc.filhos(documento, no.id);
  const secoes = [];
  paineis.forEach((f, i) => {
    const corpo = h('div', { class: 'exec-acordeao-corpo', dataset: { acordeaoCorpo: f.id }, hidden: i !== 0 });
    corpo.append(desenharNo(f, documento, paleta, irPara, ctxWidgets));
    const bt = h('button', {
      type: 'button', class: 'exec-acordeao-cabecalho', dataset: { acordeaoAbrir: f.id }, 'aria-expanded': i === 0 ? 'true' : 'false',
    }, (f.propriedades || {}).rotulo ?? (f.propriedades || {}).titulo ?? paleta.tipos[f.tipo]?.rotulo ?? f.tipo);
    bt.addEventListener('click', () => {
      const abrir = corpo.hidden;
      if (!multiplo) for (const s of secoes) { s.corpo.hidden = true; s.bt.setAttribute('aria-expanded', 'false'); }
      corpo.hidden = !abrir;
      bt.setAttribute('aria-expanded', String(abrir));
    });
    secoes.push({ corpo, bt });
    el.append(h('div', { class: 'exec-acordeao-painel' }, bt, corpo));
  });
  return el;
}

/* ---------------------------------------------------------------- painel lateral: recolhível por botão;
   recolhido = LARGURA zero + `aria-hidden`, nunca `display:none` no próprio painel (o botão de reabrir
   continua fora dele, sempre visível) */
function desenharPainelLateral(no, documento, paleta, irPara, ctxWidgets) {
  const lado = no.propriedades?.lado || 'esquerda';
  let aberto = no.propriedades?.aberto_inicial !== false;
  const corpo = h('aside', { class: `exec-painel-lateral lado-${lado}`, dataset: { no: no.id, tipo: 'painel_lateral' }, 'aria-hidden': aberto ? 'false' : 'true' });
  for (const f of doc.filhos(documento, no.id)) corpo.append(desenharNo(f, documento, paleta, irPara, ctxWidgets));
  const envolucro = h('div', { class: `exec-painel-lateral-envolucro lado-${lado}${aberto ? '' : ' recolhido'}` });
  const bt = h('button', {
    type: 'button', class: 'exec-painel-lateral-alternar', dataset: { painelLateralAlternar: no.id }, 'aria-expanded': String(aberto),
    'aria-label': aberto ? 'Recolher painel lateral' : 'Expandir painel lateral',
  }, icone(aberto ? 'chevron_esq' : 'chevron_dir', { tamanho: 14 }));
  if (no.propriedades?.recolhivel === false) bt.hidden = true;
  bt.addEventListener('click', () => {
    aberto = !aberto;
    envolucro.classList.toggle('recolhido', !aberto);
    corpo.setAttribute('aria-hidden', aberto ? 'false' : 'true');
    bt.setAttribute('aria-expanded', String(aberto));
    bt.setAttribute('aria-label', aberto ? 'Recolher painel lateral' : 'Expandir painel lateral');
    bt.replaceChildren(icone(aberto ? 'chevron_esq' : 'chevron_dir', { tamanho: 14 }));
  });
  if (lado === 'direita') envolucro.append(corpo, bt);
  else envolucro.append(bt, corpo);
  return envolucro;
}

/* ---------------------------------------------------------------- janela: modal (com <dialog>, Esc nativo)
   ou ancorada (popover manual perto do botão, Esc por tratador próprio — <dialog> não tem "ancorado") */
function desenharJanela(no, documento, paleta, irPara, ctxWidgets) {
  const modo = no.propriedades?.modo || 'modal';
  const rotuloBotao = no.propriedades?.rotulo_botao || 'Abrir';
  const envolucro = h('span', { class: 'exec-janela-envolucro', dataset: { no: no.id, tipo: 'janela' } });
  const bt = h('button', { type: 'button', class: 'exec-janela-botao', dataset: { janelaAbrir: no.id } }, rotuloBotao);
  const conteudo = () => doc.filhos(documento, no.id).map((f) => desenharNo(f, documento, paleta, irPara, ctxWidgets));

  if (modo === 'modal') {
    const dialogo = h('dialog', { class: 'exec-janela exec-janela-modal', dataset: { janela: no.id } });
    dialogo.append(...conteudo());
    bt.addEventListener('click', () => dialogo.showModal());
    envolucro.append(bt, dialogo);
    return envolucro;
  }

  // ancorada: div posicionada perto do botão; abre/fecha manual; Esc fecha; clique fora fecha
  const painel = h('div', { class: 'exec-janela exec-janela-ancorada', dataset: { janela: no.id }, hidden: true });
  painel.append(...conteudo());
  function fechar() { painel.hidden = true; document.removeEventListener('keydown', aoTeclado); document.removeEventListener('click', aoClicarFora, true); }
  function aoTeclado(ev) { if (ev.key === 'Escape') fechar(); }
  function aoClicarFora(ev) { if (!painel.contains(ev.target) && ev.target !== bt) fechar(); }
  bt.addEventListener('click', () => {
    if (!painel.hidden) { fechar(); return; }
    painel.hidden = false;
    document.addEventListener('keydown', aoTeclado);
    document.addEventListener('click', aoClicarFora, true);
  });
  envolucro.append(bt, painel);
  return envolucro;
}

/* ---------------------------------------------------------------- seção com vistas (abas) */
function desenharSecaoVistas(no, documento, paleta, irPara, ctxWidgets) {
  const vistas = doc.filhos(documento, no.id).filter((f) => f.tipo === 'vista');
  const el = h('div', { class: 'exec-secao-vistas', dataset: { no: no.id, tipo: 'secao_vistas' } });
  const barra = h('div', { class: 'exec-vistas-barra', role: 'tablist' });
  const painel = h('div', { class: 'exec-vistas-painel' });
  function mostrar(id) {
    limpar(painel);
    const v = vistas.find((x) => x.id === id) || vistas[0];
    if (v) painel.append(desenharNo(v, documento, paleta, irPara, ctxWidgets));
    for (const bt of barra.children) bt.setAttribute('aria-selected', bt.dataset.vista === (v ? v.id : '') ? 'true' : 'false');
  }
  vistas.forEach((v) => {
    const bt = h('button', { type: 'button', role: 'tab', dataset: { vista: v.id }, 'aria-selected': 'false' }, (v.propriedades || {}).rotulo || 'Vista');
    bt.addEventListener('click', () => mostrar(v.id));
    barra.append(bt);
  });
  el.append(barra, painel);
  if (vistas.length) mostrar(vistas[0].id);
  return el;
}
