/* plat — página /estilo (item L0-14-identidade-visual): o sistema de design VIVO. Lê web/estilo/tokens.css pela
   rede no momento em que a página abre, extrai todo token --i-* (valor escuro, valor claro e o valor calculado
   pelo navegador agora) e desenha a partir deles: paleta com razão de contraste medida aqui (fórmula WCAG 2 sobre
   a cor calculada — cada razão é uma RÉGUA, com a fórmula como comando), famílias e escala tipográfica, grade de
   espaçamento, forma, a família de ícones inteira e os 6 componentes de base nos 7 estados. Nada aqui é lista
   escrita à mão: se um token entra em tokens.css, aparece nesta página no próximo carregamento. A página é
   pública para quem conhece o endereço (não expõe dado de inquilino); com sessão mostra a barra lateral. */
import '../base/componentes.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto, seletorTema } from '../base/layout.js';
import { icone, nomesDeIcones } from '../base/icones.js';
import { regua, reguaTela } from '../base/regua.js';
import { obter } from '../base/api.js';
import { sessaoProvavel, marcarSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
const ARQUIVO = '/static/estilo/tokens.css';
const FORMULA = '(L1 + 0,05) / (L2 + 0,05), L = luminância relativa sRGB (WCAG 2.1, 1.4.3)';

/* ---------- leitura dos tokens ---------- */
function extrairBlocos(css) {
  /* devolve [{seletor, declaracoes: {nome: valor}}] só dos blocos que declaram --i-* */
  const blocos = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const seletor = m[1].trim();
    const decls = {};
    for (const linha of m[2].split(';')) {
      const i = linha.indexOf(':');
      if (i < 0) continue;
      const nome = linha.slice(0, i).trim();
      if (!nome.startsWith('--i-')) continue;
      decls[nome] = linha.slice(i + 1).replace(/\/\*[\s\S]*?\*\//g, '').trim();
    }
    if (Object.keys(decls).length) blocos.push({ seletor, declaracoes: decls });
  }
  return blocos;
}

function lerTokens(css) {
  const limpo = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocos = extrairBlocos(limpo);
  const escuro = {}; const claro = {}; const ordem = [];
  for (const b of blocos) {
    const eClaro = b.seletor.includes('data-theme="light"');
    const eEscuro = b.seletor.includes('data-theme="dark"');
    for (const [nome, valor] of Object.entries(b.declaracoes)) {
      if (!ordem.includes(nome)) ordem.push(nome);
      if (eClaro) claro[nome] = valor;
      else if (eEscuro) escuro[nome] = valor;
      else if (!(nome in escuro)) escuro[nome] = valor;
    }
  }
  return { ordem, escuro, claro };
}

const calc = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

/* cor calculada de fato (resolve color-mix e var) desenhando num elemento e lendo o computed color */
function corCalculada(valor) {
  const sonda = h('span', { style: `color: ${valor}; position: absolute; visibility: hidden` });
  document.body.append(sonda);
  const cor = getComputedStyle(sonda).color;
  sonda.remove();
  return cor;
}

function rgbDe(texto) {
  const m = texto.match(/rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)/);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4]) };
  const x = texto.match(/^#([0-9a-f]{6})$/i);
  if (x) return { r: parseInt(x[1].slice(0, 2), 16), g: parseInt(x[1].slice(2, 4), 16), b: parseInt(x[1].slice(4, 6), 16), a: 1 };
  return null;
}
function luminancia({ r, g, b }) {
  const f = (c) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function compor(frente, fundo) {
  if (!frente || frente.a >= 1) return frente;
  const a = frente.a;
  return { r: frente.r * a + fundo.r * (1 - a), g: frente.g * a + fundo.g * (1 - a), b: frente.b * a + fundo.b * (1 - a), a: 1 };
}
export function razaoContraste(corA, corB) {
  const a = rgbDe(corA); const b = rgbDe(corB);
  if (!a || !b) return null;
  const fa = compor(a, b); const fb = compor(b, { r: 0, g: 0, b: 0, a: 1 });
  const la = luminancia(fa); const lb = luminancia(fb);
  const hi = Math.max(la, lb); const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}
const fmt2 = (n) => n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ---------- paleta ---------- */
const CORES_TEXTO = ['--i-texto', '--i-texto-fraco', '--i-acento', '--i-sucesso', '--i-aviso', '--i-erro'];
const SUPERFICIES = ['--i-fundo', '--i-superficie', '--i-superficie-2'];

function amostraCor(nome, valorEscuro, valorClaro, superficies, agora) {
  const corAgora = corCalculada(agora);
  const eTexto = CORES_TEXTO.includes(nome) || nome === '--i-acento-texto' || nome === '--i-sobre-estado';
  const contrastes = h('div', { class: 'contrastes' });
  if (eTexto) {
    const alvos = nome === '--i-acento-texto' ? ['--i-acento'] : nome === '--i-sobre-estado' ? ['--i-sucesso', '--i-aviso', '--i-erro'] : superficies;
    for (const sup of alvos) {
      const r = razaoContraste(corAgora, corCalculada(calc(sup)));
      if (r === null) continue;
      const ok = r >= 4.5;
      contrastes.append(h('span', { class: 'contraste', title: `${nome} sobre ${sup}` },
        regua(`${fmt2(r)}:1`, { origem: `getComputedStyle(${nome}) × ${sup}`, comando: FORMULA }),
        h('span', { class: `marcador ${ok ? 'ok' : (r >= 3 ? 'atencao' : 'falha')}` }, ok ? 'AA' : (r >= 3 ? 'AA grande' : 'abaixo'))));
    }
  }
  return h('div', { class: 'amostra', dataset: { token: nome } },
    h('div', { class: 'cor', style: `background: ${agora}; color: ${eTexto ? 'inherit' : 'inherit'}` }),
    h('div', { class: 'legenda' },
      h('span', { class: 'nome' }, nome),
      h('span', { class: 'mono fraco' }, `agora ${corAgora}`),
      h('span', { class: 'mono fraco' }, `escuro ${valorEscuro || '—'} · claro ${valorClaro || '—'}`),
      contrastes));
}

function renderPaleta(tokens) {
  const caixa = limpar(el('paleta'));
  const carta = limpar(el('paleta-carta'));
  let n = 0;
  for (const nome of tokens.ordem) {
    const v = tokens.escuro[nome] || '';
    const eCor = /#[0-9a-f]{3,8}\b|rgba?\(|color-mix\(/i.test(v);
    if (!eCor) continue;
    n++;
    const alvo = nome.startsWith('--i-carta-') ? carta : caixa;
    alvo.append(amostraCor(nome, tokens.escuro[nome], tokens.claro[nome], SUPERFICIES, calc(nome)));
  }
  el('paleta-n').textContent = `(${n})`;
}

/* ---------- tipografia ---------- */
const FAMILIAS = [
  { token: '--i-fonte-titulo', papel: 'exibição', classe: 'titulo', amostra: 'Plataforma SIG · 1.234.567',
    motivo: 'Big Shoulders Display 700/800: condensada e industrial, letra de placa de instrumento. Marca, h1, h2, cabeçalho de tabela, número de destaque. Nunca em texto de corrida — condensada demais para parágrafo.' },
  { token: '--i-fonte-texto', papel: 'texto', classe: 'texto', amostra: 'O arquivo se contradiz em 24,9% dos 530 registros, contra 8,65% dos 164.202 da base.',
    motivo: 'IBM Plex Sans 400/500/600: humanista-neutra, legível em texto longo e em formulário, contraste deliberado com a exibição. A mesma fonte para tudo é o painel genérico que o dono rejeitou.' },
  { token: '--i-fonte-dado', papel: 'dado', classe: 'dado', amostra: '-23.49348, -46.59302 · z13.0 · 1.234.567,89 · 0123456789',
    motivo: 'IBM Plex Mono 400/500: algarismos de largura fixa (tabular-nums), para número alinhar em coluna como num mostrador digital. Tabela, coordenada, código, id, régua.' },
];

function renderTipografia(tokens) {
  const caixa = limpar(el('familias'));
  for (const f of FAMILIAS) {
    caixa.append(h('div', { class: 'familia', dataset: { token: f.token } },
      h('div', { class: `amostra-tipo ${f.classe}`, style: `font-family: ${calc(f.token)}` }, f.amostra),
      h('div', { class: 'motivo' }, h('div', { class: 'nome' }, `${f.token} · ${f.papel}`), h('div', { class: 'mono fraco' }, calc(f.token)), h('p', {}, f.motivo))));
  }
  const escala = limpar(el('escala'));
  for (const nome of tokens.ordem) {
    if (!/^--i-t-?\d$/.test(nome)) continue;
    const v = calc(nome);
    const px = parseFloat(v) * parseFloat(getComputedStyle(document.documentElement).fontSize);
    escala.append(h('div', { class: 'degrau' },
      h('span', { class: 'nome' }, nome),
      h('span', { class: 'valor' }, `${v} = ${fmt2(px)} px`),
      h('span', { style: `font-size: var(${nome})` }, 'Corredor Angicos–Itaporanga, 2.502,89 km')));
  }
}

/* ---------- espaçamento e forma ---------- */
function renderEspacos(tokens) {
  const caixa = limpar(el('espacos'));
  const sonda = h('div', { style: 'position: absolute; visibility: hidden' });
  document.body.append(sonda);
  for (const nome of tokens.ordem) {
    if (!/^--i-e\d$/.test(nome)) continue;
    sonda.style.width = `var(${nome})`;
    const px = sonda.getBoundingClientRect().width;
    caixa.append(h('div', { class: 'passo' },
      h('span', { class: 'nome' }, nome),
      h('span', { class: 'valor' }, `${tokens.escuro[nome]} = ${fmt2(px)} px`),
      h('div', {}, h('div', { class: 'barra', style: `width: var(${nome})` }))));
  }
  sonda.remove();
  el('espaco-densidade').textContent = `(densidade ${window.platTema?.densidadeAtual() || 'normal'} · fator ${calc('--i-densidade')})`;
}

function renderFormas(tokens) {
  const caixa = limpar(el('formas'));
  const amostras = {
    '--i-raio': 'raio', '--i-raio-pilula': 'pilula', '--i-sombra': 'sombra', '--i-sombra-leve': 'sombra-leve',
    '--i-fio-forte': 'fio-forte', '--i-fio-marca': 'fio-marca', '--i-foco-largura': 'foco',
  };
  for (const nome of tokens.ordem) {
    if (!/^--i-(raio|fio|foco|sombra|tique|regua|tempo|icone|traco|largura|mini|qr|barra|corte)/.test(nome)) continue;
    const classe = amostras[nome];
    const forma = h('div', { class: 'forma' }, h('span', { class: 'nome' }, nome), h('span', { class: 'mono' }, tokens.escuro[nome]));
    if (classe) forma.append(h('div', { class: `amostra-forma ${classe}` }));
    if (nome === '--i-tique') forma.append(h('div', { class: 'amostra-forma instrumento-moldura' }));
    if (nome === '--i-regua-passo') forma.append(regua('1.234,56', { origem: 'exemplo', comando: 'a régua sob um número' }));
    caixa.append(forma);
  }
}

/* ---------- ícones ---------- */
function renderIcones() {
  const caixa = limpar(el('icones'));
  const nomes = nomesDeIcones();
  for (const nome of nomes) caixa.append(h('div', { class: 'ic', dataset: { icone: nome } }, icone(nome, { tamanho: 24 }), h('span', {}, nome)));
  el('icones-n').textContent = `(${nomes.length})`;
}

/* ---------- componentes × estados ---------- */
const ESTADOS = ['repouso', 'foco', 'ativo', 'desativado', 'carregando', 'vazio', 'erro'];

function caixaEstado(nome, conteudo) {
  return h('div', { class: 'estado-caixa', dataset: { estado: nome } }, h('span', { class: 'nome' }, nome), conteudo);
}

function avisoEm(estado) {
  const a = h('plat-aviso');
  const depois = () => {
    switch (estado) {
      case 'repouso': a.mostrar('mensagem de estado da tela', 'info'); break;
      case 'foco': a.mostrar('aviso com foco de teclado', 'info'); a.classList.add('foco-simulado'); break;
      case 'ativo': a.ok('operação concluída'); break;
      case 'desativado': a.atencao('atenção: item somente leitura'); a.setAttribute('aria-disabled', 'true'); a.style.opacity = '.5'; break;
      case 'carregando': a.carregando('carregando a lista'); break;
      case 'vazio': a.limpar(); break;
      case 'erro': a.mostrar('não foi possível salvar (ref. abc123)', 'erro'); break;
      default:
    }
  };
  queueMicrotask(depois);
  return estado === 'vazio' ? h('div', {}, a, h('span', { class: 'fraco' }, 'vazio = oculto (hidden), sem ocupar espaço')) : a;
}

function buscaEm(estado) {
  const b = h('plat-busca', { rotulo: 'Buscar item' });
  queueMicrotask(() => {
    switch (estado) {
      case 'foco': b.querySelector('input').classList.add('foco-simulado'); b.valor = 'guarulhos'; break;
      case 'ativo': b.valor = 'guarulhos'; break;
      case 'desativado': b.desativada = true; b.valor = 'guarulhos'; break;
      case 'carregando': b.valor = 'guarulhos'; b.ocupado = true; break;
      case 'vazio': b.valor = ''; break;
      case 'erro': b.valor = 'tipo:'; b.erro('sintaxe: valor ausente depois de "tipo:"'); break;
      default:
    }
  });
  return b;
}

function formularioEm(estado) {
  const f = h('plat-formulario');
  queueMicrotask(() => {
    if (estado === 'vazio') { f.campos = []; return; }
    f.campos = [
      { nome: 'nome', rotulo: 'nome', tipo: 'texto', obrigatorio: true, padrao: estado === 'repouso' ? '' : 'Camada de lotes', desabilitado: estado === 'desativado' },
      { nome: 'senha', rotulo: 'senha', tipo: 'senha', ajuda: 'ao menos 12 caracteres', desabilitado: estado === 'desativado' },
    ];
    f.botoes = [{ id: 'salvar', rotulo: 'Salvar', tipo: 'submit' }];
    if (estado === 'foco') f.campo('nome').classList.add('foco-simulado');
    if (estado === 'ativo') f.querySelector('button[type=submit]').classList.add('ativo-simulado');
    if (estado === 'carregando') f.ocupado = true;
    if (estado === 'erro') { f.erro('nome', 'já existe um item com este nome'); f.mensagem('corrija os campos marcados', 'erro'); }
  });
  return f;
}

function paginacaoEm(estado) {
  const p = h('plat-paginacao', { sempre: '' });
  queueMicrotask(() => {
    switch (estado) {
      case 'repouso': p.atualizar({ total: 1234, limite: 50, deslocamento: 100, origem: 'GET /api/itens?limite=50&deslocamento=100' }); break;
      case 'foco': p.atualizar({ total: 1234, limite: 50, deslocamento: 100 }); p.querySelector('button:last-of-type').classList.add('foco-simulado'); break;
      case 'ativo': p.atualizar({ total: 1234, limite: 50, deslocamento: 100 }); p.querySelector('button:last-of-type').classList.add('ativo-simulado'); break;
      case 'desativado': p.atualizar({ total: 40, limite: 50, deslocamento: 0 }); p.hidden = false; break;
      case 'carregando': p.atualizar({ total: 1234, limite: 50, deslocamento: 100 }); p.ocupado = true; break;
      case 'vazio': p.atualizar({ total: 0, limite: 50, deslocamento: 0 }); p.hidden = false; break;
      case 'erro': p.atualizar({ total: 1234, limite: 50, deslocamento: 100 }); p.erro('a página não carregou (503)'); break;
      default:
    }
  });
  return p;
}

function tabelaEm(estado) {
  const tb = h('plat-tabela', { legenda: 'amostra' });
  queueMicrotask(() => {
    tb.colunas = [{ chave: 'nome', titulo: 'nome', ordenavel: true }, { chave: 'n', titulo: 'feições', classe: 'num', ordenavel: true }];
    tb.selecionavel = true;
    tb.acoes = () => [{ id: 'abrir', rotulo: 'abrir', icone: 'seta_dir' }];
    const linhas = [{ id: 1, nome: 'lotes_guarulhos', n: 73115 }, { id: 2, nome: 'zoneamento', n: 1284 }];
    switch (estado) {
      case 'repouso': tb.linhas = linhas; break;
      case 'foco': tb.linhas = linhas; tb.querySelector('tbody input').classList.add('foco-simulado'); break;
      case 'ativo': tb.linhas = linhas; tb.querySelector('tbody input').click(); break;
      case 'desativado': tb.linhas = linhas; tb.desativada = true; break;
      case 'carregando': tb.linhas = []; tb.ocupado = true; break;
      case 'vazio': tb.linhas = []; tb.vazio = 'nenhuma camada nesta pasta'; break;
      case 'erro': tb.linhas = []; tb.erro('a lista não carregou (503)', () => tb.erro('')); break;
      default:
    }
  });
  return tb;
}

function dialogoEm(estado) {
  /* um <dialog> estático (não modal) por estado, para todos ficarem visíveis lado a lado */
  const corpo = h('div', { class: 'dialogo-corpo', 'data-vazio': t('dialogo.vazio') });
  const botoes = h('div', { class: 'dialogo-botoes' });
  const dlg = h('dialog', { class: 'dialogo', open: true, 'aria-label': `diálogo em ${estado}` },
    h('div', { class: 'dialogo-cabecalho' }, h('h2', {}, 'apagar item'), h('button', { type: 'button', class: 'fechar-x icone-so', 'aria-label': 'fechar' }, icone('fechar', { tamanho: 18 }))),
    corpo, botoes);
  const cancelar = h('button', { type: 'button' }, 'Cancelar');
  const ok = h('button', { type: 'button', class: 'perigo' }, 'Apagar');
  if (estado !== 'vazio') corpo.append(h('p', {}, 'o item vai para a lixeira por 30 dias.'));
  botoes.append(cancelar, ok);
  switch (estado) {
    case 'foco': ok.classList.add('foco-simulado'); break;
    case 'ativo': ok.classList.add('ativo-simulado'); break;
    case 'desativado': cancelar.disabled = true; ok.disabled = true; break;
    case 'carregando': dlg.setAttribute('aria-busy', 'true'); cancelar.disabled = true; ok.disabled = true; break;
    case 'erro': botoes.prepend(h('span', { class: 'dialogo-erro', role: 'alert' }, icone('erro', { tamanho: 12 }), 'não foi possível apagar (409)')); break;
    default:
  }
  return dlg;
}

const COMPONENTES = [
  ['plat-aviso', avisoEm], ['plat-busca', buscaEm], ['plat-formulario', formularioEm],
  ['plat-paginacao', paginacaoEm], ['plat-tabela', tabelaEm], ['plat-dialogo', dialogoEm],
];

function renderComponentes() {
  const caixa = limpar(el('componentes'));
  for (const [nome, fabrica] of COMPONENTES) {
    const sec = h('div', { class: 'componente', dataset: { componente: nome } }, h('h3', {}, nome));
    const grade = h('div', { class: 'estados' });
    for (const estado of ESTADOS) grade.append(caixaEstado(estado, fabrica(estado)));
    sec.append(grade);
    caixa.append(sec);
  }
}

/* ---------- tabela de todos os tokens ---------- */
function renderTabelaTokens(tokens) {
  const corpo = limpar(el('tokens-tabela').querySelector('tbody'));
  for (const nome of tokens.ordem) {
    const agora = calc(nome);
    const eCor = /#[0-9a-f]{3,8}\b|rgba?\(|color-mix\(/i.test(tokens.escuro[nome] || '');
    corpo.append(h('tr', {},
      h('td', {}, nome),
      h('td', {}, tokens.escuro[nome] || ''),
      h('td', {}, tokens.claro[nome] || ''),
      h('td', {}, eCor ? h('span', { class: 'cor-chip', style: `background: ${agora}` }) : null, agora)));
  }
  el('tokens-n').textContent = `(${tokens.ordem.length})`;
}

/* ---------- controles ---------- */
function montarControles(tokens) {
  const pt = window.platTema;
  const alvo = limpar(el('controle-tema'));
  const sel = seletorTema();
  if (sel) alvo.append(sel);
  const dens = limpar(el('controle-densidade'));
  if (pt) {
    for (const d of pt.DENSIDADES) {
      const b = h('button', { type: 'button', 'aria-pressed': String(pt.densidadeAtual() === d), dataset: { densidade: d } }, t(`densidade.${d}`));
      b.addEventListener('click', () => { pt.definirDensidade(d); for (const x of dens.children) x.setAttribute('aria-pressed', String(x.dataset.densidade === d)); renderEspacos(tokens); });
      dens.append(b);
    }
  }
  const efetivo = () => { el('tema-efetivo').textContent = pt ? pt.efetivo() : '—'; };
  efetivo();
  const rerender = () => { efetivo(); renderPaleta(tokens); renderTabelaTokens(tokens); };
  document.addEventListener('plat:tema', rerender);
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', rerender);
}

/* ---------- entrada ---------- */
await carregarIdioma();
if (sessaoProvavel()) {
  const r = await obter('/api/eu');
  if (r.status === 200) montarLayout({ usuario: r.json, ativo: '/estilo' });
  else marcarSessao(false);
}
if (!document.body.classList.contains('com-lateral')) reguaTela(el('principal'));
try {
  const t0 = performance.now();
  const resp = await fetch(ARQUIVO, { cache: 'no-store' });
  const css = await resp.text();
  const tokens = lerTokens(css);
  el('estilo-origem').replaceChildren(regua(`${tokens.ordem.length} tokens`, { origem: `GET ${ARQUIVO}`, status: resp.status, ms: Math.round(performance.now() - t0), comando: "grep -c -- '--i-' web/estilo/tokens.css" }));
  const demo = limpar(el('regua-demo'));
  demo.append(h('dt', {}, 'tokens lidos'), h('dd', {}, regua(String(tokens.ordem.length), { origem: `GET ${ARQUIVO}`, status: resp.status, comando: "grep -o -- '--i-[a-z0-9-]*:' web/estilo/tokens.css | sort -u | wc -l" })));
  demo.append(h('dt', {}, 'ícones na família'), h('dd', {}, regua(String(nomesDeIcones().length), { origem: 'web/js/base/icones.js', comando: 'Object.keys(ICONES).length' })));
  demo.append(h('dt', {}, 'contraste texto × superfície'), h('dd', {}, regua(`${fmt2(razaoContraste(corCalculada(calc('--i-texto')), corCalculada(calc('--i-superficie'))))}:1`, { origem: 'getComputedStyle(--i-texto) × --i-superficie', comando: FORMULA })));
  montarControles(tokens);
  renderPaleta(tokens);
  renderTipografia(tokens);
  renderEspacos(tokens);
  renderFormas(tokens);
  renderIcones();
  renderComponentes();
  renderTabelaTokens(tokens);
} catch (e) {
  el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
}
pronto();
