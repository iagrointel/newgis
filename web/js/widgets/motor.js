import { REGISTRO, validarEsquema } from './registro.js';
import { criarFontes } from '../app/fontes.js';
import { criarVistas } from '../app/vistas.js';
import { Barramento } from '../app/barramento.js';

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
async function carregarModulos(tipos) {
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

/* Monta os widgets de um documento. Item L5-07: `corpo.fontes`/`corpo.vistas`/`corpo.mensagens` viram Fonte,
   Vista e Barramento (app/*.js); cada widget com `configuracao.vista` recebe a Vista e o barramento de
   mensagens; as fontes carregam depois de tudo montado (os widgets repintam em `registros_carregados`).
   `antesDoBarramento(vistas)` deixa quem chama restaurar o estado da URL antes de as mensagens começarem a
   ouvir (senão o estado restaurado dispararia as mensagens de novo). As ligações simples do L5-06
   (`corpo.ligacoes`) continuam valendo. */
export async function montarWidgets(destino, documento, {
  barramento = new BarramentoWidgets(), edicao = false, antesDoBarramento = null, carregarFontes = true, buscar = undefined,
} = {}) {
  const corpo = corpoDe(documento);
  const falhas = await carregarModulos([...new Set(corpo.nos.map((no) => no.tipo))]);

  const fontes = criarFontes(corpo);
  const vistas = criarVistas(corpo, fontes);
  if (antesDoBarramento) antesDoBarramento(vistas, fontes);
  const instancias = new Map();
  const barramentoApp = new Barramento(corpo, { vistas, widgets: instancias });

  const grade = document.createElement('div'); grade.className = 'plat-widgets';
  for (const no of corpo.nos) {
    const manifesto = REGISTRO.get(no.tipo);
    if (!manifesto) { grade.append(erroWidget(no, 'tipo desconhecido')); continue; }
    if (falhas.has(no.tipo)) { grade.append(erroWidget(no, falhas.get(no.tipo))); continue; }
    try {
      validarEsquema(no.configuracao || {}, manifesto.esquema_config, `widget.${no.id}.configuracao`);
      const vistaId = no.configuracao?.vista;
      if (vistaId && !vistas.has(vistaId)) throw new Error(`vista inexistente no documento: ${vistaId}`);
      const widget = document.createElement(manifesto.elemento);
      widget.noId = no.id; widget.barramento = barramento; widget.barramentoApp = barramentoApp;
      widget.configuracao = no.configuracao || {};
      if (vistaId) widget.vista = vistas.get(vistaId);
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

  const errosFontes = new Map();
  if (carregarFontes) {
    await Promise.all([...fontes.values()].map(async (f) => {
      try { await f.carregar(buscar); } catch (e) { errosFontes.set(f.id, e.message); }
    }));
    for (const [id, msg] of errosFontes) {
      const aviso = document.createElement('section');
      aviso.className = 'plat-widget-erro'; aviso.setAttribute('role', 'alert'); aviso.dataset.fonte = id;
      aviso.textContent = `Fonte “${fontes.get(id).nome}”: ${msg}`;
      grade.prepend(aviso);
    }
  }
  return { barramento, barramentoApp, fontes, vistas, instancias, falhas, errosFontes, edicao: (ativo) => alternarEdicao(grade, ativo) };
}
