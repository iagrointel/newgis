import { REGISTRO, validarEsquema } from './registro.js';

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

export async function montarWidgets(destino, documento, { barramento = new BarramentoWidgets() } = {}) {
  const corpo = corpoDe(documento);
  const tipos = [...new Set(corpo.nos.map((no) => no.tipo))];
  await Promise.all(tipos.map(async (tipo) => {
    const manifesto = REGISTRO.get(tipo);
    if (manifesto) await import(manifesto.modulo);
  }));

  const instancias = new Map();
  const grade = document.createElement('div'); grade.className = 'plat-widgets';
  for (const no of corpo.nos) {
    const manifesto = REGISTRO.get(no.tipo);
    if (!manifesto) { grade.append(erroWidget(no, 'tipo desconhecido')); continue; }
    try {
      validarEsquema(no.configuracao || {}, manifesto.esquema_config, `widget.${no.id}.configuracao`);
      const widget = document.createElement(manifesto.elemento);
      widget.noId = no.id; widget.barramento = barramento; widget.configuracao = no.configuracao || {};
      widget.dataset.noId = no.id;
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
      const manifesto = alvo && REGISTRO.get(alvo.localName.slice(5));
      const acao = ligacao.acao || detail.nome;
      if (alvo && manifesto?.acoes.includes(acao)) alvo.executar(acao, detail.detalhe);
    }
  });
  destino.replaceChildren(grade);
  return { barramento, instancias };
}
