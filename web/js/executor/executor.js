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

export function montarExecucao({ raiz, documento, paleta }) {
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
    for (const filho of doc.filhos(documento, pagina.id)) container.append(desenharNo(filho, documento, paleta, irPara));
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
   executor desenha uma caixa com o rótulo, para um widget novo da paleta nunca sumir da tela em silêncio. */
function desenharNo(no, documento, paleta, irPara) {
  const def = paleta.tipos[no.tipo] || { rotulo: no.tipo };
  const filhos = () => doc.filhos(documento, no.id).map((f) => desenharNo(f, documento, paleta, irPara));
  switch (no.tipo) {
    case 'cabecalho': return caixa(no, 'header', 'exec-cabecalho', filhos, { dataset: { fixo: String(!!no.propriedades?.fixo) } });
    case 'rodape': return caixa(no, 'footer', 'exec-rodape', filhos);
    case 'menu': return desenharMenu(no, documento, irPara);
    case 'linha': return desenharLinha(no, documento, paleta, irPara);
    case 'coluna': return desenharColuna(no, documento, paleta, irPara);
    case 'grade': return desenharGrade(no, documento, paleta, irPara);
    case 'acordeao': return desenharAcordeao(no, documento, paleta, irPara);
    case 'painel_fixo': return caixa(no, 'div', `exec-painel-fixo pos-${no.propriedades?.posicao || 'superior-direita'}`, filhos);
    case 'painel_lateral': return desenharPainelLateral(no, documento, paleta, irPara);
    case 'janela': return desenharJanela(no, documento, paleta, irPara);
    case 'secao_vistas': return desenharSecaoVistas(no, documento, paleta, irPara);
    case 'vista': return caixa(no, 'div', 'exec-vista', filhos);
    case 'grupo': return caixa(no, 'div', 'exec-grupo', filhos);
    case 'texto': return h('p', { class: `exec-texto exec-texto-${no.propriedades?.nivel || 'corpo'}`, dataset: { no: no.id, tipo: 'texto' } }, String(no.propriedades?.texto ?? ''));
    case 'imagem': return h('img', { class: 'exec-imagem', dataset: { no: no.id, tipo: 'imagem' }, src: no.propriedades?.url || '', alt: no.propriedades?.alternativo || '' });
    case 'mapa': return h('div', { class: 'exec-mapa', dataset: { no: no.id, tipo: 'mapa', zoom: String(no.propriedades?.zoom ?? '') } }, 'mapa (zoom inicial ' + (no.propriedades?.zoom ?? '-') + ')');
    case 'tabela': return h('div', { class: 'exec-tabela', dataset: { no: no.id, tipo: 'tabela' } }, `tabela (${no.propriedades?.linhas_por_pagina ?? '-'} linhas/página)`);
    default: return caixa(no, 'div', 'exec-desconhecido', filhos, {}, def.rotulo);
  }
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
function desenharLinha(no, documento, paleta, irPara) {
  const el = h('div', { class: `exec-linha alinhar-${no.propriedades?.alinhar || 'inicio'}`, dataset: { no: no.id, tipo: 'linha' } });
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara);
    filho.style.flex = `${Math.max(1, f.largura_colunas || 1)} 1 0`;
    filho.classList.add('exec-flex-item');
    el.append(filho);
  }
  return el;
}

function desenharColuna(no, documento, paleta, irPara) {
  const el = h('div', { class: `exec-coluna alinhar-${no.propriedades?.alinhar || 'inicio'}`, dataset: { no: no.id, tipo: 'coluna' } });
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara);
    filho.classList.add('exec-flex-item');
    el.append(filho);
  }
  return el;
}

/* ---------------------------------------------------------------- grade: CSS Grid `repeat(N, 1fr)` — a
   proporção entre dois filhos é uma razão de frações (fr), invariante à largura do contêiner por definição
   do próprio CSS Grid: é isso que a cláusula "grade responsiva mantém proporção" mede. */
function desenharGrade(no, documento, paleta, irPara) {
  const colunasGrade = Math.max(1, Math.min(12, no.propriedades?.colunas ?? 3));
  const el = h('div', { class: 'exec-grade', dataset: { no: no.id, tipo: 'grade', colunasGrade: String(colunasGrade) } });
  el.style.gridTemplateColumns = `repeat(${colunasGrade}, minmax(0, 1fr))`;
  for (const f of doc.filhos(documento, no.id)) {
    const filho = desenharNo(f, documento, paleta, irPara);
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
function desenharAcordeao(no, documento, paleta, irPara) {
  const multiplo = !!no.propriedades?.multiplo_aberto;
  const el = h('div', { class: 'exec-acordeao', dataset: { no: no.id, tipo: 'acordeao' } });
  const paineis = doc.filhos(documento, no.id);
  const secoes = [];
  paineis.forEach((f, i) => {
    const corpo = h('div', { class: 'exec-acordeao-corpo', dataset: { acordeaoCorpo: f.id }, hidden: i !== 0 });
    corpo.append(desenharNo(f, documento, paleta, irPara));
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
function desenharPainelLateral(no, documento, paleta, irPara) {
  const lado = no.propriedades?.lado || 'esquerda';
  let aberto = no.propriedades?.aberto_inicial !== false;
  const corpo = h('aside', { class: `exec-painel-lateral lado-${lado}`, dataset: { no: no.id, tipo: 'painel_lateral' }, 'aria-hidden': aberto ? 'false' : 'true' });
  for (const f of doc.filhos(documento, no.id)) corpo.append(desenharNo(f, documento, paleta, irPara));
  const envolucro = h('div', { class: `exec-painel-lateral-envolucro lado-${lado}${aberto ? '' : ' recolhido'}` });
  const bt = h('button', {
    type: 'button', class: 'exec-painel-lateral-alternar', dataset: { painelLateralAlternar: no.id }, 'aria-expanded': String(aberto),
    'aria-label': aberto ? 'Recolher painel lateral' : 'Expandir painel lateral',
  }, aberto ? '‹' : '›');
  if (no.propriedades?.recolhivel === false) bt.hidden = true;
  bt.addEventListener('click', () => {
    aberto = !aberto;
    envolucro.classList.toggle('recolhido', !aberto);
    corpo.setAttribute('aria-hidden', aberto ? 'false' : 'true');
    bt.setAttribute('aria-expanded', String(aberto));
    bt.setAttribute('aria-label', aberto ? 'Recolher painel lateral' : 'Expandir painel lateral');
    bt.textContent = aberto ? '‹' : '›';
  });
  if (lado === 'direita') envolucro.append(corpo, bt);
  else envolucro.append(bt, corpo);
  return envolucro;
}

/* ---------------------------------------------------------------- janela: modal (com <dialog>, Esc nativo)
   ou ancorada (popover manual perto do botão, Esc por tratador próprio — <dialog> não tem "ancorado") */
function desenharJanela(no, documento, paleta, irPara) {
  const modo = no.propriedades?.modo || 'modal';
  const rotuloBotao = no.propriedades?.rotulo_botao || 'Abrir';
  const envolucro = h('span', { class: 'exec-janela-envolucro', dataset: { no: no.id, tipo: 'janela' } });
  const bt = h('button', { type: 'button', class: 'exec-janela-botao', dataset: { janelaAbrir: no.id } }, rotuloBotao);
  const conteudo = () => doc.filhos(documento, no.id).map((f) => desenharNo(f, documento, paleta, irPara));

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
function desenharSecaoVistas(no, documento, paleta, irPara) {
  const vistas = doc.filhos(documento, no.id).filter((f) => f.tipo === 'vista');
  const el = h('div', { class: 'exec-secao-vistas', dataset: { no: no.id, tipo: 'secao_vistas' } });
  const barra = h('div', { class: 'exec-vistas-barra', role: 'tablist' });
  const painel = h('div', { class: 'exec-vistas-painel' });
  function mostrar(id) {
    limpar(painel);
    const v = vistas.find((x) => x.id === id) || vistas[0];
    if (v) painel.append(desenharNo(v, documento, paleta, irPara));
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
