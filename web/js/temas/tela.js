/* plat · temas — tela /temas (item L5-10-temas-marca). Editor do tema do inquilino: lista os 6 temas
   padrão (clique = começar uma cópia na edição), mostra o tema gravado do inquilino, edita a cópia por
   arrasto de cor/fonte para o campo do token (além de inputs diretos), pré-visualiza ao vivo com o MESMO
   remapeamento do executor (web/estilo/temas.css, .tema-aplicado), calcula os 10 pares de contraste
   WCAG 1.4.3 ao vivo (espelho de app/temas.py — a validação ESTRITA continua no servidor, PUT /api/org/tema)
   e exporta/importa a definição como JSON. Literais em português de propósito, mesma convenção do
   executor e do construtor (a i18n dos dicionários cobre o cromo compartilhado). */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { loja, tem } from '../base/estado.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { cabecalho, montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { irParaLogin, lembrarInquilino, marcarSessao } from '../auth/sessao.js';
import { avaliarModo, carregar as carregarTemas, aplicar } from './temas.js';

const NOMES_COR = {
  fundo: 'fundo', superficie: 'superfície', texto: 'texto', texto_suave: 'texto suave',
  acento: 'acento', texto_sobre_acento: 'texto sobre acento', borda: 'borda',
  sucesso: 'sucesso', erro: 'erro',
};
const NOMES_FONTE = { familia_texto: 'fonte de texto', familia_titulo: 'fonte de título', familia_dado: 'fonte de dado' };
const NOMES_FAMILIA = {
  'Big Shoulders Display': 'Big Shoulders Display', 'IBM Plex Sans': 'IBM Plex Sans', 'IBM Plex Mono': 'IBM Plex Mono',
  serif: 'serif', 'sans-serif': 'sans-serif', monospace: 'monospace', 'system-ui': 'system-ui',
};
const FAMILIAS = Object.keys(NOMES_FAMILIA);
const NIVEIS = { pequeno: 'pequeno', medio: 'médio', grande: 'grande' };
const CAMPOS_SOMBRA = { x: 'x', y: 'y', desfoque: 'desfoque', cor: 'cor' };

const s = { dados: null, definicao: null, modo: 'claro' };

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(texto, tipo = 'erro') {
  const n = porId('aviso');
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function avisoInquilino(texto, tipo = 'erro') {
  const n = porId('inquilino-aviso');
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

/* ---------------------------------------------------------------- estado em edição (definição parcial:
   os slots só mostram o que o tema declara; o resto herda a plataforma — sobreposição é forma legítima) */

function modoAtual() {
  if (!s.definicao[s.modo]) s.definicao[s.modo] = {};
  return s.definicao[s.modo];
}

function secao(nome) {
  const m = modoAtual();
  if (!m[nome]) m[nome] = {};
  return m[nome];
}

function descartarSecaoVazia(nome) {
  const m = s.definicao[s.modo];
  if (m && m[nome] && Object.keys(m[nome]).length === 0) delete m[nome];
  if (s.definicao[s.modo] && Object.keys(s.definicao[s.modo]).length === 0) delete s.definicao[s.modo];
}

function corValor(nome) {
  return (modoAtual().cores || {})[nome] || '';
}

function definirCor(nome, valor) {
  const v = String(valor || '').trim();
  if (!v) { delete secao('cores')[nome]; descartarSecaoVazia('cores'); }
  else secao('cores')[nome] = v.toLowerCase();
  redesenhar();
}

function definirFonte(nome, valor) {
  if (!valor) { delete secao('tipografia')[nome]; descartarSecaoVazia('tipografia'); }
  else secao('tipografia')[nome] = valor;
  redesenhar();
}

function definirMedida(secaoNome, nivel, valor) {
  const v = String(valor || '').trim();
  if (!v) { delete secao(secaoNome)[nivel]; descartarSecaoVazia(secaoNome); }
  else secao(secaoNome)[nivel] = v;
  redesenhar();
}

function definirSombra(nivel, campo, valor) {
  const sh = secao('sombra');
  if (!sh[nivel]) sh[nivel] = { x: 0, y: 0, desfoque: 0, cor: '#00000066' };
  if (campo === 'cor') sh[nivel].cor = String(valor || '').trim().toLowerCase();
  else {
    const n = Number(valor);
    sh[nivel][campo] = Number.isFinite(n) ? n : 0;
  }
  redesenhar();
}

/* ---------------------------------------------------------------- desenho */

function amostras(definicao, modo) {
  const cores = (definicao && definicao[modo] && definicao[modo].cores) || {};
  return h('div', { class: 'tema-amostras' },
    ...['fundo', 'superficie', 'texto', 'acento', 'borda'].map((c) =>
      h('span', { class: 'tema-amostra', style: `background:${cores[c] || '#888'};`, title: NOMES_COR[c] })));
}

function desenharCartoes() {
  const alvo = porId('tema-cartoes');
  limpar(alvo);
  for (const [id, p] of Object.entries(s.dados.padroes)) {
    const cartao = h('button', { type: 'button', class: 'tema-cartao', dataset: { tema: id } },
      h('span', { class: 'nome' }, p.nome),
      amostras(p.tema, 'claro'),
      h('span', { class: 'ajuda' }, p.avisos.length === 0 ? 'contraste em ordem nos dois modos' : `${p.avisos.length} aviso(s) de contraste`));
    cartao.addEventListener('click', () => {
      // cópia PROFUNDA do padrão: o padrão da plataforma nunca é editado in place
      s.definicao = JSON.parse(JSON.stringify(p.tema));
      s.modo = 'claro';
      porId('editor-modo').value = 'claro';
      aviso(`edição começou a partir de “${p.nome}” — nada foi gravado ainda`, 'info');
      redesenhar();
    });
    alvo.append(cartao);
  }
}

function desenharInquilino() {
  const atual = s.dados.inquilino && s.dados.inquilino.tema ? s.dados.inquilino.tema : null;
  porId('inquilino-estado').textContent = atual
    ? 'há um tema gravado do inquilino (os apps publicados herdam).'
    : 'nenhum tema gravado: os apps publicados usam o padrão da plataforma.';
  const avisosAtuais = s.dados.inquilino ? s.dados.inquilino.avisos || [] : [];
  const saida = porId('inquilino-avisos');
  limpar(saida);
  if (avisosAtuais.length) {
    saida.append(h('ul', { class: 'tema-aviso-lista' },
      ...avisosAtuais.map((a) => h('li', { class: 'tema-par-aviso' },
        `contraste ${a.razao}:1 no par ${a.par} (${a.modo}) fica abaixo do mínimo de ${a.minimo}:1`))));
  }
  const pode = tem('org.configurar', loja.ler('usuario'));
  porId('inquilino-salvar').disabled = !pode;
  porId('inquilino-remover').disabled = !pode || !atual;
  if (!pode) porId('inquilino-remover').title = 'só quem configura a organização grava ou remove o tema';
}

function slotCor(nome) {
  const valor = corValor(nome);
  const entradaTexto = h('input', { type: 'text', value: valor, placeholder: '#rrggbb', 'aria-label': `cor ${NOMES_COR[nome]} (texto)` });
  const entradaCor = h('input', { type: 'color', value: valor || '#888888', 'aria-label': `cor ${NOMES_COR[nome]} (seletor)` });
  entradaTexto.addEventListener('change', () => definirCor(nome, entradaTexto.value));
  entradaCor.addEventListener('input', () => definirCor(nome, entradaCor.value));
  const slot = h('div', { class: 'tema-slot', dataset: { slot: `cor:${nome}` } },
    h('span', { class: 'rotulo' }, NOMES_COR[nome]), entradaCor, entradaTexto);
  ligarArrasto(slot, (texto) => definirCor(nome, texto));
  return slot;
}

function slotFonte(nome) {
  const valor = (modoAtual().tipografia || {})[nome] || '';
  const escolha = h('select', { 'aria-label': NOMES_FONTE[nome] },
    h('option', { value: '' }, '— herdar da plataforma —'),
    ...FAMILIAS.map((f) => h('option', { value: f, selected: f === valor }, NOMES_FAMILIA[f])));
  escolha.addEventListener('change', () => definirFonte(nome, escolha.value));
  const slot = h('div', { class: 'tema-slot', dataset: { slot: `fonte:${nome}` } },
    h('span', { class: 'rotulo' }, NOMES_FONTE[nome]), escolha);
  ligarArrasto(slot, (texto) => { if (FAMILIAS.includes(texto)) definirFonte(nome, texto); });
  return slot;
}

function slotMedida(secaoNome, nivel) {
  const valor = ((modoAtual()[secaoNome] || {})[nivel]) || '';
  const titulo = secaoNome === 'raio' ? `raio ${NIVEIS[nivel]}` : `espaçamento ${NIVEIS[nivel]}`;
  const entrada = h('input', { type: 'text', value: valor, placeholder: 'ex.: 4px', 'aria-label': titulo });
  entrada.addEventListener('change', () => definirMedida(secaoNome, nivel, entrada.value));
  const slot = h('div', { class: 'tema-slot', dataset: { slot: `${secaoNome}:${nivel}` } },
    h('span', { class: 'rotulo' }, titulo), entrada);
  ligarArrasto(slot, (texto) => definirMedida(secaoNome, nivel, texto));
  return slot;
}

function slotSombra(nivel) {
  const atual = (modoAtual().sombra || {})[nivel];
  const slot = h('div', { class: 'tema-slot', dataset: { slot: `sombra:${nivel}` } },
    h('span', { class: 'rotulo' }, `sombra ${nivel === 'nivel_1' ? '1' : '2'}`));
  for (const [campo, rotuloCampo] of Object.entries(CAMPOS_SOMBRA)) {
    const entrada = h('input', {
      type: 'text', value: atual ? String(atual[campo]) : '', placeholder: campo === 'cor' ? '#rrggbbaa' : '0',
      'aria-label': `sombra ${nivel} campo ${rotuloCampo}`, style: 'max-width:64px;',
    });
    entrada.addEventListener('change', () => definirSombra(nivel, campo, entrada.value));
    slot.append(entrada);
  }
  return slot;
}

function desenharSlots() {
  limpar(porId('slots-cores'));
  for (const nome of Object.keys(NOMES_COR)) porId('slots-cores').append(slotCor(nome));
  limpar(porId('slots-fontes'));
  for (const nome of Object.keys(NOMES_FONTE)) porId('slots-fontes').append(slotFonte(nome));
  limpar(porId('slots-medidas'));
  for (const nivel of Object.keys(NIVEIS)) porId('slots-medidas').append(slotMedida('raio', nivel));
  for (const nivel of Object.keys(NIVEIS)) porId('slots-medidas').append(slotMedida('espacamento', nivel));
  limpar(porId('slots-sombra'));
  for (const nivel of ['nivel_1', 'nivel_2']) porId('slots-sombra').append(slotSombra(nivel));
}

function desenharPaleta() {
  const cores = porId('paleta-cores');
  limpar(cores);
  const usadas = modoAtual().cores || {};
  for (const [nome, valor] of Object.entries(usadas)) {
    cores.append(chip(nome, valor, `cor ${NOMES_COR[nome]}`));
  }
  if (!cores.children.length) cores.append(h('span', { class: 'ajuda' }, 'as cores do tema em edição aparecem aqui para arrastar'));
  const fontes = porId('paleta-fontes');
  limpar(fontes);
  const tipografia = modoAtual().tipografia || {};
  for (const [nome, valor] of Object.entries(tipografia)) fontes.append(chip(nome, valor, NOMES_FONTE[nome] || nome));
  if (!fontes.children.length) fontes.append(h('span', { class: 'ajuda' }, 'as fontes do tema em edição aparecem aqui para arrastar'));
}

function chip(nome, valor, rotulo) {
  const c = h('span', { class: 'tema-chip', draggable: 'true', dataset: { chip: `${nome}:${valor}` }, title: `${rotulo} — arraste para um campo` },
    valor.startsWith('#') ? h('span', { class: 'quad', style: `background:${valor};` }) : h('span', { class: 'quad', style: 'background:repeating-linear-gradient(45deg,#ccc,#ccc 2px,#fff 2px,#fff 4px);' }),
    `${rotulo}: ${valor}`);
  c.addEventListener('dragstart', (ev) => {
    ev.dataTransfer.setData('text/plain', valor);
    ev.dataTransfer.effectAllowed = 'copy';
    c.classList.add('arrastando');
  });
  c.addEventListener('dragend', () => c.classList.remove('arrastando'));
  return c;
}

/* soltar em um slot: o valor arrastado (cor hexadecimal ou família de fonte) define o token do campo */
function ligarArrasto(slot, aplicarValor) {
  slot.addEventListener('dragover', (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy'; slot.classList.add('sobre'); });
  slot.addEventListener('dragleave', () => slot.classList.remove('sobre'));
  slot.addEventListener('drop', (ev) => {
    ev.preventDefault();
    slot.classList.remove('sobre');
    const texto = ev.dataTransfer.getData('text/plain');
    if (texto) aplicarValor(texto);
  });
}

/* pré-visualização: o MESMO .tema-aplicado do executor (web/estilo/temas.css) — o que se vê aqui é o que
   o app executado recebe, por remapeamento de variáveis e não por estilo paralelo */
function desenharPrevia() {
  const previa = porId('previa');
  for (let i = previa.style.length - 1; i >= 0; i -= 1) {
    const nome = previa.style.item(i);
    if (nome.startsWith('--t-')) previa.style.removeProperty(nome);
  }
  previa.classList.remove('tema-aplicado');
  const tokens = (s.definicao[s.modo === 'claro' ? 'claro' : 'escuro']) || s.definicao.claro || s.definicao.escuro || {};
  aplicar(previa, { [modoComTokens()]: tokens }, s.modo);
  limpar(previa);
  previa.append(
    h('header', { class: 'exec-cabecalho' }, h('strong', {}, 'Título do app'), h('nav', { class: 'exec-menu exec-menu-horizontal', 'aria-label': 'pré-visualização' },
      h('a', { href: '#', 'aria-current': 'page', onclick: (e) => e.preventDefault() }, 'início'),
      h('a', { href: '#', onclick: (e) => e.preventDefault() }, 'mapa'))),
    h('div', { class: 'previa-corpo' },
      h('p', { class: 'exec-texto exec-texto-corpo' }, 'Texto de corrida no tema: a leitura precisa ficar confortável nos dois modos.'),
      h('p', { class: 'exec-texto exec-texto-corpo' }, h('small', { class: 'ajuda' }, 'Texto suave para informação secundária.')),
      h('div', { class: 'exec-linha' },
        h('button', { type: 'button', class: 'primario' }, 'Ação principal'),
        h('button', { type: 'button' }, 'Ação neutra')),
      h('div', { class: 'exec-acordeao' },
        h('div', { class: 'exec-acordeao-painel' },
          h('button', { type: 'button', class: 'exec-acordeao-cabecalho' }, 'Painel dobrável'),
          h('div', { class: 'exec-acordeao-corpo' }, 'Conteúdo de apoio.')))));
}

function modoComTokens() {
  return s.definicao[s.modo] ? s.modo : (s.definicao.claro ? 'claro' : 'escuro');
}

function desenharContraste() {
  const saida = porId('contraste-saida');
  limpar(saida);
  const pares = avaliarModo(s.definicao[s.modo]);
  const reprovados = pares.filter((p) => !p.ok);
  if (!pares.length) {
    saida.append(h('p', { class: 'ajuda' }, 'declare as cores para calcular o contraste.'));
    return;
  }
  const tabela = h('table', { class: 'tema-pares' },
    h('thead', {}, h('tr', {}, h('th', {}, 'par'), h('th', {}, 'razão'), h('th', {}, 'mínimo'), h('th', {}, 'veredito'))),
    h('tbody', {}, ...pares.map((p) => h('tr', {},
      h('td', {}, p.par),
      h('td', { class: 'mono' }, `${p.razao.toFixed ? p.razao.toFixed(2) : p.razao}:1`),
      h('td', { class: 'mono' }, `${p.minimo}:1`),
      h('td', { class: p.ok ? 'tema-par-ok' : 'tema-par-aviso' }, p.ok ? 'ok' : 'abaixo do mínimo')))));
  saida.append(tabela);
  if (reprovados.length) {
    saida.append(h('p', { class: 'tema-par-aviso' },
      `${reprovados.length} de ${pares.length} pares ficam abaixo de 4,5:1 no modo ${s.modo}. O tema pode ser gravado, mas o aviso acompanha o tema no GET /api/temas.`));
  } else {
    saida.append(h('p', { class: 'tema-par-ok' }, `os ${pares.length} pares avaliados passam de 4,5:1 no modo ${s.modo}.`));
  }
}

function redesenhar() {
  desenharSlots();
  desenharPaleta();
  desenharPrevia();
  desenharContraste();
  desenharInquilino();
  porId('json').value = JSON.stringify(s.definicao, null, 2);
}

/* ---------------------------------------------------------------- ações */

async function gravarNoInquilino() {
  avisoInquilino('');
  const r = await api.alterar('/api/org/tema', { tema: s.definicao });
  if (r.status !== 200) {
    avisoInquilino(`o servidor recusou o tema: ${api.mensagemDe(r)}`);
    return;
  }
  s.dados.inquilino = { tema: r.json.tema, avisos: r.json.avisos || [] };
  if (r.json.avisos && r.json.avisos.length) {
    avisoInquilino(`tema gravado com ${r.json.avisos.length} aviso(s) de contraste (o tema fica em vigor; o aviso é obrigatório)`, 'atencao');
  } else {
    avisoInquilino('tema gravado.', 'ok');
  }
  redesenhar();
}

async function removerDoInquilino() {
  avisoInquilino('');
  const r = await api.alterar('/api/org/tema', { tema: null });
  if (r.status !== 200) {
    avisoInquilino(`não foi possível remover: ${api.mensagemDe(r)}`);
    return;
  }
  s.dados.inquilino = null;
  avisoInquilino('tema do inquilino removido; os apps publicados voltam ao padrão da plataforma.', 'ok');
  redesenhar();
}

function importarJson() {
  const bruto = porId('json').value;
  let dados;
  try {
    dados = JSON.parse(bruto);
  } catch {
    aviso('o JSON não pôde ser lido: sintaxe inválida', 'erro');
    return;
  }
  if (!dados || typeof dados !== 'object' || Array.isArray(dados) || (!dados.claro && !dados.escuro)) {
    aviso('o tema importado precisa ser um objeto com “claro” e/ou “escuro”', 'erro');
    return;
  }
  s.definicao = dados;
  s.modo = dados.claro ? 'claro' : 'escuro';
  porId('editor-modo').value = s.modo;
  aviso('tema importado para a edição — a validação estrita acontece no servidor, ao gravar.', 'info');
  redesenhar();
}

function exportarJson() {
  porId('json').value = JSON.stringify(s.definicao, null, 2);
  aviso('definição exportada para o campo JSON.', 'info');
}

function copiarClaroParaEscuro() {
  if (!s.definicao.claro) { aviso('não há modo claro para copiar', 'erro'); return; }
  s.definicao.escuro = JSON.parse(JSON.stringify(s.definicao.claro));
  porId('editor-modo').value = 'escuro';
  s.modo = 'escuro';
  redesenhar();
}

function trocarModo() {
  s.modo = porId('editor-modo').value;
  redesenhar();
}

/* ---------------------------------------------------------------- arranque */

function layout(usuario) {
  montarLayout({ usuario: usuario || { inquilino: {}, login: '', nome: '', perfil: '' }, ativo: '/temas' });
  if (!usuario) {
    const pessoa = document.querySelector('#lateral .pessoa');
    if (pessoa) pessoa.hidden = true;
  }
  cabecalho('Temas');
}

async function principal() {
  const r = await api.obter('/api/eu');
  if (r.status === 401) { irParaLogin(); return; }
  const usuario = r.status === 200 ? r.json : null;
  if (usuario) {
    marcarSessao(true);
    if (usuario.inquilino && usuario.inquilino.slug) lembrarInquilino(usuario.inquilino.slug);
    loja.definir({ usuario });
  }
  layout(usuario);
  s.dados = await carregarTemas();
  // começa SEM definição: nenhum slot preenchido até a pessoa escolher um padrão ou importar
  s.definicao = {};
  porId('editor-modo').addEventListener('change', trocarModo);
  porId('copiar-para-escuro').addEventListener('click', copiarClaroParaEscuro);
  porId('exportar').addEventListener('click', exportarJson);
  porId('importar').addEventListener('click', importarJson);
  porId('inquilino-salvar').addEventListener('click', gravarNoInquilino);
  porId('inquilino-remover').addEventListener('click', removerDoInquilino);
  redesenhar();
}

await carregarIdioma();
try {
  await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso(`não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  pronto();
}
