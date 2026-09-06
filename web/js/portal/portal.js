/* plat — portal da API (item L7-08-d). Lê /api/openapi.json e /api/portal/exemplos da PRÓPRIA origem;
   nenhum recurso de fora entra nesta tela (a resposta de /portal traz uma CSP que só admite 'self', e
   tests/e2e/test_portal.py intercepta a rede e reprova qualquer pedido para outro host).

   Três coisas acontecem aqui: o índice de rotas com o escopo que cada uma exige, o "experimentar" (uma
   requisição de verdade, com a chave que o operador colou, mostrando status, tipo de conteúdo e corpo) e
   a lista dos exemplos executáveis lidos do diretório exemplos/. A chave NUNCA é gravada: vive no campo
   de senha e no fechamento deste módulo, some ao recarregar a página. */
import '../base/componentes.js';
import { obterJSON } from '../core.js';

// web/style.css esconde `.lateral` até `montarLayout()` (app/js/base/layout.js) marcar `body.com-lateral` —
// gate contra flash de barra lateral com usuário errado. O portal não chama `montarLayout()` (ADR 0018
// decisão 1: tela própria, sem sessão de usuário na barra) e a marca do índice de rotas já nasce estática
// no HTML, então a revelação é imediata, sem depender de nenhuma resposta assíncrona.
document.body.classList.add('com-lateral');

const ESPECIAIS = {
  publico: 'rota aberta, sem credencial',
  sessao: 'só cookie de sessão; chave de API recebe 403',
  superadmin: 'só sessão de operador da plataforma',
  'token:qualquer': 'qualquer chave válida serve',
};
const VERBOS = ['get', 'post', 'put', 'patch', 'delete'];
const aviso = document.getElementById('aviso');
const el = (id) => document.getElementById(id);
let rotas = [];
let selecionada = null;
let exemplos = [];
let linguagem = 'python';

function criar(tag, classe, texto) {
  const n = document.createElement(tag);
  if (classe) n.className = classe;
  if (texto != null) n.textContent = texto;
  return n;
}

function chave() {
  return el('chave').value.trim();
}

function descreverEscopo(escopo) {
  return ESPECIAIS[escopo] || '';
}

// ---------------------------------------------------------------- índice de rotas
function montarRotas(spec) {
  const saida = [];
  for (const [caminho, operacoes] of Object.entries(spec.paths || {})) {
    for (const [verbo, op] of Object.entries(operacoes)) {
      if (!VERBOS.includes(verbo)) continue;
      saida.push({
        caminho,
        verbo,
        escopo: op['x-plat-escopo'] || 'publico',
        auth: op['x-auth'] || '-',
        privilegio: op['x-privilegio'] || '-',
        resumo: op.summary || '',
        descricao: op.description || '',
        parametros: op.parameters || [],
        temCorpo: Boolean(op.requestBody),
        grupo: (op.tags || ['outras'])[0],
      });
    }
  }
  saida.sort((a, b) => a.caminho.localeCompare(b.caminho) || VERBOS.indexOf(a.verbo) - VERBOS.indexOf(b.verbo));
  return saida;
}

function desenharIndice(filtro) {
  const indice = el('indice');
  indice.replaceChildren();
  const termo = (filtro || '').trim().toLowerCase();
  const visiveis = rotas.filter((r) => !termo
    || r.caminho.toLowerCase().includes(termo)
    || r.escopo.toLowerCase().includes(termo)
    || r.grupo.toLowerCase().includes(termo));
  const porGrupo = new Map();
  for (const r of visiveis) {
    if (!porGrupo.has(r.grupo)) porGrupo.set(r.grupo, []);
    porGrupo.get(r.grupo).push(r);
  }
  for (const [grupo, lista] of [...porGrupo].sort((a, b) => a[0].localeCompare(b[0]))) {
    indice.appendChild(criar('h2', 'portal-grupo', grupo));
    const ul = criar('ul', 'portal-lista');
    for (const r of lista) {
      const li = document.createElement('li');
      const b = criar('button', 'portal-rota');
      b.type = 'button';
      b.dataset.id = `${r.verbo} ${r.caminho}`;
      b.appendChild(criar('span', `portal-verbo v-${r.verbo}`, r.verbo.toUpperCase()));
      b.appendChild(criar('span', 'portal-caminho mono', r.caminho));
      b.appendChild(criar('span', 'portal-escopo mono', r.escopo));
      b.addEventListener('click', () => selecionar(r));
      li.appendChild(b);
      ul.appendChild(li);
    }
    indice.appendChild(ul);
  }
  el('contagem').textContent = `${visiveis.length} de ${rotas.length} rotas`;
}

// ---------------------------------------------------------------- rota escolhida
function exemploCurl(r) {
  const partes = [`curl -i -X ${r.verbo.toUpperCase()} "$PLAT_URL${r.caminho}"`];
  if (r.escopo !== 'publico') partes.push('  -H "Authorization: Bearer $PLAT_CHAVE"');
  if (r.temCorpo) partes.push('  -H "Content-Type: application/json"', "  -d '{}'");
  return partes.join(' \\\n');
}

function selecionar(r) {
  selecionada = r;
  el('cartao-rota').hidden = false;
  el('rota-verbo').textContent = r.verbo.toUpperCase();
  el('rota-verbo').className = `portal-verbo v-${r.verbo}`;
  el('rota-caminho').textContent = r.caminho;
  el('rota-resumo').textContent = r.descricao || r.resumo || 'sem descrição no esquema';
  el('rota-escopo').textContent = r.escopo + (descreverEscopo(r.escopo) ? ` — ${descreverEscopo(r.escopo)}` : '');
  el('rota-auth').textContent = r.auth;
  el('rota-privilegio').textContent = r.privilegio;
  const caixa = el('rota-parametros');
  caixa.replaceChildren();
  if (r.parametros.length) {
    caixa.appendChild(criar('h3', null, 'Parâmetros'));
    const ul = criar('ul', 'portal-parametros');
    for (const p of r.parametros) {
      const li = document.createElement('li');
      li.appendChild(criar('code', 'mono', p.name));
      li.appendChild(criar('span', 'portal-em', ` (${p.in}${p.required ? ', obrigatório' : ''})`));
      if (p.description) li.appendChild(criar('span', null, ` — ${p.description}`));
      ul.appendChild(li);
    }
    caixa.appendChild(ul);
  }
  el('exp-caminho').value = r.caminho;
  el('campo-corpo').hidden = !r.temCorpo;
  el('exp-dica').textContent = r.escopo === 'publico'
    ? 'rota pública: a chave não é enviada'
    : `a chave precisa do escopo ${r.escopo}`;
  el('resposta').hidden = true;
  el('rota-curl').textContent = exemploCurl(r);
  el('cartao-rota').scrollIntoView({ block: 'start' });
}

// ---------------------------------------------------------------- experimentar
async function experimentar(evento) {
  evento.preventDefault();
  if (!selecionada) return;
  const caminho = el('exp-caminho').value.trim();
  if (!caminho.startsWith('/')) {
    aviso.erro('o caminho tem de começar com barra e ficar nesta origem');
    return;
  }
  // esconde a resposta ANTES do fetch: repetir a mesma rota (ex. depois de revogar a chave) sem trocar de
  // rota deixava `#resposta` já visível da vez anterior, e quem espera "#resposta:not([hidden])" (e2e e
  // qualquer leitor de tela) via a resposta VELHA achando que já era a nova.
  el('resposta').hidden = true;
  const cabecalhos = { Accept: 'application/json' };
  const k = chave();
  if (k && selecionada.escopo !== 'publico') cabecalhos.Authorization = `Bearer ${k}`;
  const opcoes = { method: selecionada.verbo.toUpperCase(), headers: cabecalhos, cache: 'no-store' };
  if (selecionada.temCorpo) {
    cabecalhos['Content-Type'] = 'application/json';
    opcoes.body = el('exp-corpo').value.trim() || '{}';
  }
  const t0 = performance.now();
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch (erro) {
    aviso.erro(`a requisição não completou: ${erro}`);
    return;
  }
  const ms = Math.round(performance.now() - t0);
  const texto = await resposta.text();
  let corpo = texto;
  try {
    corpo = JSON.stringify(JSON.parse(texto), null, 2);
  } catch { /* resposta não-JSON: mostra crua */ }
  el('resposta').hidden = false;
  const estado = el('resp-status');
  estado.textContent = `HTTP ${resposta.status}`;
  estado.dataset.faixa = resposta.status < 300 ? 'ok' : (resposta.status < 500 ? 'recusa' : 'falha');
  el('resp-tipo').textContent = resposta.headers.get('content-type') || '(sem tipo)';
  el('resp-tempo').textContent = `${ms} ms`;
  el('resp-corpo').textContent = corpo.slice(0, 20000);
  el('resposta').dataset.status = String(resposta.status);
  aviso.limpar();
}

// ---------------------------------------------------------------- exemplos
function desenharExemplos() {
  const ul = el('lista-exemplos');
  ul.replaceChildren();
  const lista = exemplos.filter((e) => e.linguagem === linguagem);
  for (const e of lista) {
    const li = document.createElement('li');
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    sum.appendChild(criar('span', 'portal-exemplo-nome mono', e.arquivo));
    sum.appendChild(criar('span', 'portal-exemplo-titulo', e.titulo));
    det.appendChild(sum);
    det.appendChild(criar('p', 'portal-em', e.ambiente));
    det.appendChild(criar('pre', 'portal-corpo mono', e.codigo));
    li.appendChild(det);
    ul.appendChild(li);
  }
  el('contagem-exemplos').textContent = `${exemplos.length} no total, ${lista.length} em ${linguagem}`;
}

function ligarAbas() {
  for (const [id, valor] of [['aba-python', 'python'], ['aba-js', 'js']]) {
    el(id).addEventListener('click', () => {
      linguagem = valor;
      el('aba-python').setAttribute('aria-selected', String(valor === 'python'));
      el('aba-js').setAttribute('aria-selected', String(valor === 'js'));
      desenharExemplos();
    });
  }
}

// ---------------------------------------------------------------- partida
function desenharEscopos(spec) {
  const corpo = el('tabela-escopos').querySelector('tbody');
  corpo.replaceChildren();
  for (const linha of spec['x-plat-escopos'] || []) {
    const tr = document.createElement('tr');
    const td = criar('td', 'mono', linha.escopo);
    tr.appendChild(td);
    tr.appendChild(criar('td', null, linha.descricao));
    corpo.appendChild(tr);
  }
  const ul = el('perfis');
  ul.replaceChildren();
  for (const p of spec['x-plat-perfis-de-chave'] || []) {
    const li = document.createElement('li');
    li.appendChild(criar('strong', null, p.perfil));
    li.appendChild(criar('span', null, ` — ${p.descricao}`));
    li.appendChild(criar('div', 'mono portal-em', p.escopos.join(' · ')));
    ul.appendChild(li);
  }
}

function descricaoEmParagrafos(texto) {
  const caixa = el('descricao');
  caixa.replaceChildren();
  for (const bloco of (texto || '').split('\n\n')) {
    if (bloco.trim()) caixa.appendChild(criar('p', null, bloco.replace(/\s+/g, ' ').trim()));
  }
}

async function iniciar() {
  const spec = await obterJSON('/api/openapi.json');
  if (spec.status !== 200) {
    aviso.erro(`o esquema OpenAPI respondeu ${spec.status}`);
    document.body.dataset.pronto = '1';
    return;
  }
  rotas = montarRotas(spec.json);
  descricaoEmParagrafos(spec.json.info?.description);
  desenharEscopos(spec.json);
  desenharIndice('');
  const lista = await obterJSON('/api/portal/exemplos');
  exemplos = lista.status === 200 ? (lista.json.exemplos || []) : [];
  desenharExemplos();
  el('filtro').addEventListener('input', (e) => desenharIndice(e.target.value));
  el('form-experimentar').addEventListener('submit', experimentar);
  el('chave').addEventListener('input', () => {
    const k = chave();
    el('chave-estado').textContent = k.startsWith('plat_')
      ? `chave de ${k.length} caracteres na memória desta aba; nada é gravado`
      : 'nenhuma chave: só as rotas públicas respondem';
  });
  ligarAbas();
  document.body.dataset.pronto = '1';
}

iniciar();
