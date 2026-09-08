import { REGISTRO, validarEsquema } from './registro.js';

export { REGISTRO };

export class BarramentoWidgets extends EventTarget {
  #pilha = new Set();

  publicar(evento) {
    const chave = `${evento.origem}:${evento.nome}`;
    if (this.#pilha.has(chave)) return false;
    this.#pilha.add(chave);
    try { return this.dispatchEvent(new CustomEvent('evento', { detail: evento })); }
    finally { this.#pilha.delete(chave); }
  }
}

function corpoDe(documento) {
  if (documento?.corpo?.nos) return documento.corpo;
  if (documento?.dados?.corpo?.nos) return documento.dados.corpo;
  throw new Error('documento de widgets sem corpo.nos');
}

function erroWidget(no, mensagem) {
  const erro = document.createElement('section');
  erro.className = 'plat-widget-erro'; erro.dataset.widget = no.tipo;
  erro.setAttribute('role', 'alert'); erro.textContent = `Widget “${no.tipo}”: ${mensagem}`;
  return erro;
}

// Carrega só os módulos citados no documento. Módulo que não carrega (arquivo apagado do disco, 404,
// erro de sintaxe) NÃO derruba a página: o tipo entra em `falhas` e cada nó dele vira caixa de erro
// nomeada, os outros widgets seguem montando.
export async function carregarModulos(tipos) {
  const falhas = new Map();
  await Promise.all(tipos.map(async (tipo) => {
    const manifesto = REGISTRO.get(tipo);
    if (!manifesto) return;
    try { await import(manifesto.modulo); }
    catch (erro) { falhas.set(tipo, `módulo ${manifesto.modulo} não carregou (${erro.message})`); }
  }));
  return falhas;
}

// Chrome de edição = atributo na grade + rótulo por widget, desenhado pelo CSS (widgets.css). O mesmo
// elemento serve ao construtor (edicao=true) e à publicação (edicao=false): nada é re-renderizado ao
// alternar, só o atributo muda. O construtor de arrasto (L5-01) pendura o seu comportamento nisto.
function alternarEdicao(grade, ativo) {
  grade.toggleAttribute('data-edicao', ativo);
  for (const widget of grade.querySelectorAll('[data-no-id]')) {
    if (ativo) { widget.tabIndex = 0; widget.setAttribute('aria-label', `widget ${widget.dataset.tipo}`); }
    else { widget.removeAttribute('tabindex'); widget.removeAttribute('aria-label'); }
  }
  return ativo;
}

/* Um widget avulso para quem monta a árvore por fora (o executor de páginas, item L5-01-d): módulo já carregado por
   `carregarModulos`; tipo desconhecido, módulo que falhou ou configuração fora do esquema viram a mesma caixa de
   erro nomeada que `montarWidgets` produz. */
export function criarWidget(no, { barramento = null, falhas = new Map() } = {}) {
  const manifesto = REGISTRO.get(no.tipo);
  if (!manifesto) return erroWidget(no, 'tipo desconhecido');
  if (falhas.has(no.tipo)) return erroWidget(no, falhas.get(no.tipo));
  if (!customElements.get(manifesto.elemento)) return erroWidget(no, `módulo ${manifesto.modulo} não carregou`);
  try {
    validarEsquema(no.configuracao || {}, manifesto.esquema_config, `widget.${no.id}.configuracao`);
  } catch (erro) { return erroWidget(no, erro.message); }
  const widget = document.createElement(manifesto.elemento);
  widget.noId = no.id; widget.barramento = barramento; widget.configuracao = no.configuracao || {};
  widget.dataset.noId = no.id; widget.dataset.tipo = no.tipo;
  return widget;
}

export async function montarWidgets(destino, documento, { barramento = new BarramentoWidgets(), edicao = false } = {}) {
  const corpo = corpoDe(documento);
  const falhas = await carregarModulos([...new Set(corpo.nos.map((no) => no.tipo))]);

  const instancias = new Map();
  const grade = document.createElement('div'); grade.className = 'plat-widgets';
  for (const no of corpo.nos) {
    const manifesto = REGISTRO.get(no.tipo);
    if (!manifesto) { grade.append(erroWidget(no, 'tipo desconhecido')); continue; }
    if (falhas.has(no.tipo)) { grade.append(erroWidget(no, falhas.get(no.tipo))); continue; }
    try {
      validarEsquema(no.configuracao || {}, manifesto.esquema_config, `widget.${no.id}.configuracao`);
      const widget = document.createElement(manifesto.elemento);
      widget.noId = no.id; widget.barramento = barramento; widget.configuracao = no.configuracao || {};
      widget.dataset.noId = no.id; widget.dataset.tipo = no.tipo;
      if (no.posicao) {
        widget.style.gridColumn = `${no.posicao.coluna || 1} / span ${no.posicao.largura || 1}`;
        widget.style.gridRow = `${no.posicao.linha || 1} / span ${no.posicao.altura || 1}`;
      }
      instancias.set(no.id, widget); grade.append(widget);
    } catch (erro) { grade.append(erroWidget(no, erro.message)); }
  }

  barramento.addEventListener('evento', ({ detail }) => {
    for (const ligacao of corpo.ligacoes || []) {
      if (ligacao.origem !== detail.origem || (ligacao.evento && ligacao.evento !== detail.nome)) continue;
      const alvo = instancias.get(ligacao.alvo);
      const manifesto = alvo && REGISTRO.get(alvo.dataset.tipo);
      const acao = ligacao.acao || detail.nome;
      if (alvo && manifesto?.acoes.includes(acao)) alvo.executar(acao, detail.detalhe);
    }
  });
  alternarEdicao(grade, edicao);
  destino.replaceChildren(grade);
  return { barramento, instancias, falhas, edicao: (ativo) => alternarEdicao(grade, ativo) };
}
