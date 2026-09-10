/* plat — temas de marca, lado do navegador (item L5-10-temas-marca). Módulo compartilhado por
   /temas (editor) e /executar (executor): carrega GET /api/temas, resolve a cadeia
   documento -> inquilino -> padrão e APLICA os tokens como CSS custom properties `--t-*` no nó raiz —
   trocar de tema é re-aplicar propriedades (style.setProperty), NUNCA recarregar a página (cláusula 1
   do portão; a navegação do executor continua por history.pushState por cima disso).

   As regras deste arquivo são ESPELHO declarado das de app/temas.py (a mesma em três lugares:
   validação fica só no servidor; aqui entram resolução, nome de variável e contraste para o aviso
   AO VIVO do editor, que não pode esperar uma viagem ao servidor a cada arrasto de cor). Os nomes de
   `--t-*` seguem a MESMA regra de temas.css_variaveis (`--t-` + sublinhado vira hífen; seção + nível:
   `--t-raio-pequeno`; sombra vira uma declaração `x y desfoque cor`). O teste e2e confere a paridade
   comparando o valor computado no navegador com o valor servido pela API. */
import { obter } from '../base/api.js';

export async function carregar() {
  const r = await obter('/api/temas');
  if (r.status !== 200) throw Object.assign(new Error(`GET /api/temas devolveu ${r.status}`), { status: r.status });
  return r.json;
}

/* modo efetivo do navegador: escolha explícita (data-theme no <html>) senão preferência do sistema —
   a mesma ordem da regra de tema da casa para claro/escuro. */
export function modoEfetivo() {
  const escolhido = document.documentElement.dataset.theme;
  if (escolhido === 'escuro' || escolhido === 'dark') return 'escuro';
  if (escolhido === 'claro' || escolhido === 'light') return 'claro';
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro';
}

/* tema com um só modo serve nos dois: o modo ausente cai no que existe (a alternativa seria tela sem
   cor nenhuma — pior para quem só definiu o claro). */
export function modoDisponivel(definicao, modo) {
  if (!definicao || typeof definicao !== 'object') return modo;
  if (definicao[modo]) return modo;
  return definicao.claro ? 'claro' : 'escuro';
}

/* espelho de temas.resolver: `selecaoDocumento` é o corpo.tema do documento ({"id"} | {"definicao"} |
   ausente); `dados` é o que GET /api/temas devolveu. Devolve {definicao, origem} com origem em
   documento|inquilino|padrao. Documento sem tema nenhum renderiza com o padrão (cláusula 5). */
export function resolver(selecaoDocumento, dados) {
  if (selecaoDocumento && typeof selecaoDocumento === 'object') {
    if (selecaoDocumento.definicao && typeof selecaoDocumento.definicao === 'object') {
      return { definicao: selecaoDocumento.definicao, origem: 'documento' };
    }
    const id = selecaoDocumento.id;
    if (typeof id === 'string' && id !== 'inquilino' && dados.padroes[id]) {
      return { definicao: dados.padroes[id].tema, origem: 'documento' };
    }
    // id === 'inquilino' (ou desconhecido): o documento PEDIU a cadeia — segue para baixo
  }
  if (dados.inquilino && dados.inquilino.tema) return { definicao: dados.inquilino.tema, origem: 'inquilino' };
  return { definicao: dados.padroes.padrao.tema, origem: 'padrao' };
}

/* espelho de temas.css_variaveis: a MESMA regra de nome `--t-*` (o consumidor é web/estilo/temas.css). */
export function variaveis(modo) {
  const saida = {};
  const m = modo || {};
  for (const [k, v] of Object.entries(m.cores || {})) saida[`--t-${k.replaceAll('_', '-')}`] = v;
  for (const [k, v] of Object.entries(m.tipografia || {})) saida[`--t-${k.replaceAll('_', '-')}`] = v;
  for (const secao of ['raio', 'espacamento']) {
    for (const [k, v] of Object.entries(m[secao] || {})) saida[`--t-${secao}-${k}`] = v;
  }
  for (const [k, v] of Object.entries(m.sombra || {})) {
    saida[`--t-sombra-${k.replaceAll('_', '-')}`] = `${v.x}px ${v.y}px ${v.desfoque}px ${v.cor}`;
  }
  return saida;
}

/* aplica a definição (tema) na raiz e devolve {modo, variaveis, origem?}. Propriedades de um tema
   anterior NÃO são removidas — todo tema completo sobrescreve todas as chaves, e um tema parcial é
   sobreposição de propósito (herda o que não declarou). */
export function aplicar(raiz, definicao, modo = modoEfetivo()) {
  const m = modoDisponivel(definicao, modo);
  const vars = variaveis((definicao || {})[m]);
  for (const [k, v] of Object.entries(vars)) raiz.style.setProperty(k, v);
  raiz.classList.add('tema-aplicado');
  raiz.dataset.temaModo = m;
  return { modo: m, variaveis: vars };
}

export function limpar(raiz) {
  // remove o que ficou de chamadas anteriores sem conhecer a definição: varre as próprias propriedades
  for (let i = raiz.style.length - 1; i >= 0; i -= 1) {
    const nome = raiz.style.item(i);
    if (nome.startsWith('--t-')) raiz.style.removeProperty(nome);
  }
  raiz.classList.remove('tema-aplicado');
}

/* ---------------------------------------------------------------- seletor do executor: trocar tema sem
   recarregar. A lista é id + inquilino + padrões; a escolha só re-aplica tokens na raiz. */
export function montarSeletor({ raiz, dados, selecaoDocumento, aplicado }) {
  const envolucro = document.createElement('div');
  envolucro.className = 'tema-seletor';
  envolucro.dataset.papel = 'seletor-tema-envolucro';

  const rotulo = document.createElement('label');
  rotulo.textContent = 'tema';
  rotulo.setAttribute('for', 'seletor-tema');

  const escolha = document.createElement('select');
  escolha.id = 'seletor-tema';
  escolha.dataset.papel = 'seletor-tema';

  const opcaoSeguir = document.createElement('option');
  opcaoSeguir.value = '';
  opcaoSeguir.textContent = selecaoDocumento ? 'seguir o documento' : 'herdado (inquilino/padrão)';
  escolha.append(opcaoSeguir);
  if (dados.inquilino && dados.inquilino.tema) {
    const o = document.createElement('option');
    o.value = 'inquilino';
    o.textContent = `inquilino${dados.inquilino.nome ? ` — ${dados.inquilino.nome}` : ''}`;
    escolha.append(o);
  }
  for (const [id, p] of Object.entries(dados.padroes)) {
    const o = document.createElement('option');
    o.value = `tema-${id}`;
    o.textContent = p.nome;
    escolha.append(o);
  }
  if (selecaoDocumento && selecaoDocumento.definicao) {
    const o = document.createElement('option');
    o.value = 'documento';
    o.textContent = 'tema embutido no documento';
    escolha.append(o);
  }

  const modoSelect = document.createElement('select');
  modoSelect.dataset.papel = 'seletor-modo';
  modoSelect.setAttribute('aria-label', 'modo claro ou escuro');
  for (const [v, t] of [['sistema', 'modo do sistema'], ['claro', 'claro'], ['escuro', 'escuro']]) {
    const o = document.createElement('option');
    o.value = v;
    o.textContent = t;
    modoSelect.append(o);
  }

  function reAplicar() {
    let definicao;
    let origem;
    const v = escolha.value;
    if (v === '') ({ definicao, origem } = resolver(selecaoDocumento, dados));
    else if (v === 'documento') ({ definicao, origem } = { definicao: selecaoDocumento.definicao, origem: 'documento' });
    else if (v === 'inquilino') ({ definicao, origem } = { definicao: dados.inquilino.tema, origem: 'inquilino' });
    else ({ definicao, origem } = { definicao: dados.padroes[v.slice(5)].tema, origem: 'seletor' });
    const modo = modoSelect.value === 'sistema' ? modoEfetivo() : modoSelect.value;
    aplicar(raiz, definicao, modo);
    raiz.dataset.temaOrigem = origem;
    if (aplicado) aplicado({ escolha: v, origem, modo });
  }

  escolha.addEventListener('change', reAplicar);
  modoSelect.addEventListener('change', reAplicar);
  envolucro.append(rotulo, escolha, modoSelect);
  reAplicar();
  return envolucro;
}

/* ---------------------------------------------------------------- contraste (espelho das funções WCAG de
   app/temas.py) — o editor usa para o aviso ao vivo, sem viagem ao servidor a cada mudança de cor. */
const PARES_TEXTO = [
  ['texto', 'fundo'],
  ['texto', 'superficie'],
  ['texto_suave', 'fundo'],
  ['texto_suave', 'superficie'],
  ['texto_sobre_acento', 'acento'],
  ['erro', 'fundo'],
  ['erro', 'superficie'],
  ['sucesso', 'fundo'],
  ['sucesso', 'superficie'],
  ['acento', 'fundo'],
];
const MINIMO = 4.5;

function canal(c) {
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminancia(cor) {
  let h = String(cor).replace(/^#/, '');
  if (h.length === 3 || h.length === 4) h = [...h.slice(0, 3)].map((ch) => ch + ch).join('');
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);
}

export function contraste(cor1, cor2) {
  const [l1, l2] = [luminancia(cor1), luminancia(cor2)].sort((a, b) => b - a);
  return (l1 + 0.05) / (l2 + 0.05);
}

export function avaliarModo(modo) {
  const cores = (modo || {}).cores || {};
  const saida = [];
  for (const [frente, fundo] of PARES_TEXTO) {
    if (!(frente in cores) || !(fundo in cores)) continue;
    const razao = Math.round(contraste(cores[frente], cores[fundo]) * 100) / 100;
    saida.push({ par: `${frente}/${fundo}`, razao, minimo: MINIMO, ok: razao >= MINIMO });
  }
  return saida;
}

/* avisos de um tema inteiro: [{modo, par, razao, minimo}] só com o que fica abaixo de 4,5:1 */
export function avisos(definicao) {
  const saida = [];
  for (const modo of ['claro', 'escuro']) {
    if (!(definicao && typeof definicao === 'object' && definicao[modo])) continue;
    for (const p of avaliarModo(definicao[modo])) {
      if (!p.ok) saida.push({ modo, par: p.par, razao: p.razao, minimo: p.minimo });
    }
  }
  return saida;
}
