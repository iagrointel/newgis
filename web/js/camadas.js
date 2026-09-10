/* plat · camadas — painel "Camadas" em árvore (item L2-01-c-lista-camadas-legenda).

   Módulo REUTILIZÁVEL (o item pede: "web/js/camadas.js reutilizável pelo widget do L5-01-b"). Não sabe
   nada de HTTP: recebe um `Catalogo` já pronto (web/js/mapa/catalogo.js, que fala com o Martin) e desenha
   a ÁRVORE por cima dele — grupo, ordem, renomear, remover, faixa de escala. O Catalogo continua sendo o
   ÚNICO dono da pilha real de camadas do MapLibre (fonte, camada de estilo, ordem de desenho); esta
   árvore só decide EM QUE ORDEM pedir ao Catalogo para desenhar (`catalogo.reordenar(...)`), nunca mexe
   direto no mapa. Por isso não há duplicação com o painel mais simples do item L2-01-mapa-web
   (web/js/mapa/painel.js): aquele item entrega o motor (Catalogo) e um painel mínimo; este entrega a
   árvore de verdade, reaproveitando o motor.

   Documento (ordem + grupos + título no mapa) é gravado no NAVEGADOR (localStorage), chave por mapa —
   este item não duplica o "documento de mapa" do catálogo (item L2-01-a-documento-mapa, formato/servidor
   próprios); quando aquele existir, quem persiste a árvore no servidor troca só `_gravar`/`_ler` abaixo,
   sem mexer no resto do módulo. */

import { h, limpar } from './base/dom.js';

const CHAVE_PADRAO = 'plat.mapa.documento.v1';
const PROFUNDIDADE_MAXIMA = 6; // a refutação do item usa 3 níveis; a trava evita ciclo/estouro

function idCurto() { return Math.random().toString(36).slice(2, 10); }

function noCamada(id, extra) { return { tipo: 'camada', id, chave: idCurto(), tituloMapa: null, faixaEscala: null, ...extra }; }
function noGrupo(titulo, filhos) { return { tipo: 'grupo', id: `g-${idCurto()}`, chave: idCurto(), titulo: titulo || 'grupo novo', aberto: true, itens: filhos || [] }; }

/* percorre a árvore em pré-ordem (nó antes dos filhos) devolvendo só os ids de camada — é a ordem de
   desenho: o primeiro da lista é o de cima. Usado para sincronizar com `catalogo.reordenar`. */
function achatar(itens) {
  const saida = [];
  for (const no of itens) {
    if (no.tipo === 'camada') saida.push(no.id);
    else saida.push(...achatar(no.itens));
  }
  return saida;
}

function encontrar(itens, chave, caminho = []) {
  for (let i = 0; i < itens.length; i += 1) {
    const no = itens[i];
    if (no.chave === chave) return { no, pai: itens, indice: i, caminho };
    if (no.tipo === 'grupo') {
      const achado = encontrar(no.itens, chave, [...caminho, no.chave]);
      if (achado) return achado;
    }
  }
  return null;
}

function remover(itens, chave) {
  const achado = encontrar(itens, chave);
  if (!achado) return null;
  achado.pai.splice(achado.indice, 1);
  return achado.no;
}

function inserirApos(itens, chaveAlvo, no) {
  if (chaveAlvo === null) { itens.push(no); return true; }
  const achado = encontrar(itens, chaveAlvo);
  if (!achado) return false;
  achado.pai.splice(achado.indice + 1, 0, no);
  return true;
}

function profundidadeDe(itens, chave, atual = 0) {
  for (const no of itens) {
    if (no.chave === chave) return atual;
    if (no.tipo === 'grupo') {
      const p = profundidadeDe(no.itens, chave, atual + 1);
      if (p !== null) return p;
    }
  }
  return null;
}

export class Arvore {
  constructor(catalogo, map, raizCamadas, {
    chaveDocumento = CHAVE_PADRAO,
    aoEnquadrar = () => {},
    aoErro = () => {},
    aoAbrirPainel = () => {}, // (acao: 'tabela'|'propriedades'|'estilo'|'grafico', camadaId) — painéis de itens irmãos
    aoMudarEscala = () => {}, // chamado quando a faixa de escala de alguma camada muda ou o zoom muda
  } = {}) {
    this.catalogo = catalogo;
    this.map = map;
    this.raiz = raizCamadas;
    this.chaveDocumento = chaveDocumento;
    this.aoEnquadrar = aoEnquadrar;
    this.aoErro = aoErro;
    this.aoAbrirPainel = aoAbrirPainel;
    this.aoMudarEscala = aoMudarEscala;
    this.itens = [];
    this._arrastando = null;
    this._foco = null;
    catalogo.aoMudar(() => this._sincronizarDisponiveis());
    map.on('zoom', () => { this._atualizarForaDeEscala(); this.desenhar(); this.aoMudarEscala(); });
  }

  /* ids de estilo (camadas MapLibre) de uma camada do catálogo — mesma função que o Catalogo usa. */
  _idsDeEstilo(id) { return this.catalogo.idsDeEstilo(id); }

  _no(chave) { const a = encontrar(this.itens, chave); return a ? a.no : null; }

  _sincronizarDisponiveis() {
    // camadas novas do catálogo que ainda não têm nó na árvore entram no topo; nenhuma é removida
    // sozinha (remover é ação explícita do usuário — "remove" no portão).
    const presentes = new Set(achatar(this.itens));
    for (const f of this.catalogo.disponiveis) {
      if (!presentes.has(f.id)) this.itens.unshift(noCamada(f.id));
    }
    this._aplicarOrdemNoMapa();
    this.desenhar();
  }

  // -------------------------------------------------------------- documento (ordem+grupos), no navegador
  documento() {
    const limpo = (itens) => itens.map((no) => no.tipo === 'grupo'
      ? { tipo: 'grupo', id: no.id, titulo: no.titulo, aberto: no.aberto, itens: limpo(no.itens) }
      : { tipo: 'camada', id: no.id, tituloMapa: no.tituloMapa, faixaEscala: no.faixaEscala });
    return { versao: 1, itens: limpo(this.itens) };
  }

  salvar() {
    try {
      window.localStorage.setItem(this.chaveDocumento, JSON.stringify(this.documento()));
      return true;
    } catch (e) { this.aoErro(e); return false; }
  }

  documentoSalvo() {
    try {
      const bruto = window.localStorage.getItem(this.chaveDocumento);
      return bruto ? JSON.parse(bruto) : null;
    } catch { return null; }
  }

  aplicarDocumento(doc) {
    const reidratar = (itens) => (itens || []).map((no) => no.tipo === 'grupo'
      ? noGrupoDe(no, reidratar(no.itens))
      : Object.assign(noCamada(no.id), { tituloMapa: no.tituloMapa ?? null, faixaEscala: no.faixaEscala ?? null }));
    this.itens = reidratar(doc.itens);
    this._sincronizarDisponiveis();
  }

  // ---------------------------------------------------------------------------------------- construção
  async carregar() {
    await this.catalogo.carregar();
    const salvo = this.documentoSalvo();
    if (salvo && salvo.versao === 1) { this.aplicarDocumento(salvo); return; }
    this.itens = this.catalogo.disponiveis.map((f) => noCamada(f.id));
    this._sincronizarDisponiveis();
  }

  // ------------------------------------------------------------------------------------- grupo/estrutura
  criarGrupo(titulo) {
    const g = noGrupo(titulo, []);
    this.itens.unshift(g);
    this.desenhar();
    return g.chave;
  }

  renomearGrupo(chave, titulo) {
    const no = this._no(chave);
    if (no && no.tipo === 'grupo') { no.titulo = titulo || no.titulo; this.desenhar(); this.salvar(); }
  }

  renomearCamada(chave, tituloMapa) {
    const no = this._no(chave);
    if (no && no.tipo === 'camada') { no.tituloMapa = tituloMapa || null; this.desenhar(); this.salvar(); }
  }

  tituloExibido(no) {
    if (no.tipo === 'grupo') return no.titulo;
    return no.tituloMapa || (this.catalogo.ficha(no.id) || {}).titulo || no.id;
  }

  async remover(chave) {
    const no = remover(this.itens, chave);
    if (!no) return;
    if (no.tipo === 'camada' && this.catalogo.ativas.includes(no.id)) this.catalogo.desligar(no.id);
    else if (no.tipo === 'grupo') {
      for (const id of achatar(no.itens)) if (this.catalogo.ativas.includes(id)) this.catalogo.desligar(id);
    }
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
  }

  async alternar(chave) {
    const no = this._no(chave);
    if (!no) return;
    if (no.tipo === 'camada') {
      try { await this.catalogo.alternar(no.id); } catch (e) { this.aoErro(e); }
      // "a mais recente entra no topo": a camada que acabou de ser ligada sobe para o topo do seu grupo, como o
      // catálogo já faz em `ativas` (unshift) — sem isto a árvore e o mapa discordam da ordem de desenho
      if (this.catalogo.ativas.includes(no.id)) {
        const achado = encontrar(this.itens, chave);
        if (achado && achado.indice > 0) achado.pai.splice(0, 0, achado.pai.splice(achado.indice, 1)[0]);
      }
    } else {
      // grupo: liga tudo se algo estiver desligado, senão desliga tudo
      const ids = achatar(no.itens);
      const algumDesligado = ids.some((id) => !this.catalogo.ativas.includes(id));
      for (const id of ids) {
        try {
          if (algumDesligado && !this.catalogo.ativas.includes(id)) await this.catalogo.ligar(id);
          if (!algumDesligado) this.catalogo.desligar(id);
        } catch (e) { this.aoErro(e); }
      }
    }
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
  }

  // ---------------------------------------------------------------------------------------- reordenação
  /* move o nó `chave` para logo depois de `chaveAlvo` (ou para o INÍCIO da lista quando chaveAlvo é
     null), opcionalmente para DENTRO do grupo `paraGrupo` (chave do grupo, ou null = nível onde está o
     alvo). Usado tanto pelo drag-and-drop quanto pelos atalhos de teclado — o MESMO caminho de código,
     que é a razão de as duas formas darem a mesma ordem no documento salvo. */
  mover(chave, chaveAlvo, paraGrupo) {
    if (chave === chaveAlvo) return false;
    const destino = paraGrupo ? (this._no(paraGrupo) || {}).itens : this.itens;
    if (!destino) return false;
    if (paraGrupo) {
      // nunca mover um grupo para dentro de si mesmo ou de um descendente seu
      if (achatarChaves(this._no(chave)).includes(paraGrupo)) return false;
    }
    const no = remover(this.itens, chave);
    if (!no) return false;
    const alvoNesteNivel = chaveAlvo && destino.some((n) => n.chave === chaveAlvo) ? chaveAlvo : null;
    if (chaveAlvo && !alvoNesteNivel) destino.push(no);
    else if (alvoNesteNivel) destino.splice(destino.findIndex((n) => n.chave === alvoNesteNivel) + 1, 0, no);
    else destino.unshift(no);
    if (profundidadeMaxima(this.itens) > PROFUNDIDADE_MAXIMA) { // desfaz: estouro de profundidade
      remover(destino, no.chave);
      this.itens.splice(0, 0, no);
      return false;
    }
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
    return true;
  }

  /* sobe/desce UM lugar entre os irmãos do mesmo nível — usado pelo teclado (ArrowUp/ArrowDown) e pelos
     botões ▲▼, e é o MESMO `mover()` do arrasto: arrasto para cima de um vizinho e ArrowUp resultam na
     idêntica troca de posição na lista de irmãos. */
  moverRelativo(chave, delta) {
    const achado = encontrar(this.itens, chave);
    if (!achado) return false;
    const { pai, indice } = achado;
    const destino = indice + delta;
    if (destino < 0 || destino >= pai.length) return false;
    const [no] = pai.splice(indice, 1);
    pai.splice(destino, 0, no);
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
    return true;
  }

  indentar(chave) {
    const achado = encontrar(this.itens, chave);
    if (!achado || achado.indice === 0) return false;
    const irmaoAcima = achado.pai[achado.indice - 1];
    if (irmaoAcima.tipo !== 'grupo') return false;
    return this.mover(chave, null, irmaoAcima.chave) || this._colocarNoTopoDoGrupo(chave, irmaoAcima.chave);
  }

  _colocarNoTopoDoGrupo(chave, grupoChave) {
    const no = remover(this.itens, chave);
    const grupo = this._no(grupoChave);
    if (!no || !grupo) return false;
    grupo.itens.unshift(no);
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
    return true;
  }

  outdentar(chave) {
    const achado = encontrar(this.itens, chave);
    if (!achado || !achado.caminho.length) return false;
    const chaveGrupoPai = achado.caminho[achado.caminho.length - 1];
    const grupoAvo = achado.caminho.length > 1 ? achado.caminho[achado.caminho.length - 2] : null;
    const no = remover(this.itens, chave);
    if (!no) return false;
    const destino = grupoAvo ? this._no(grupoAvo).itens : this.itens;
    const posGrupoPai = destino.findIndex((n) => n.chave === chaveGrupoPai);
    destino.splice(posGrupoPai + 1, 0, no);
    this._aplicarOrdemNoMapa();
    this.desenhar();
    this.salvar();
    return true;
  }

  _aplicarOrdemNoMapa() {
    const ativasNaOrdem = achatar(this.itens).filter((id) => this.catalogo.ativas.includes(id));
    this.catalogo.reordenar(ativasNaOrdem);
  }

  // -------------------------------------------------------------------------------------- faixa de escala
  definirFaixaDeEscala(chave, minzoom, maxzoom) {
    const no = this._no(chave);
    if (!no || no.tipo !== 'camada') return;
    no.faixaEscala = (minzoom === null && maxzoom === null) ? null : [minzoom ?? 0, maxzoom ?? 24];
    for (const id of this._idsDeEstilo(no.id)) {
      if (this.map.getLayer(id)) this.map.setLayerZoomRange(id, no.faixaEscala ? no.faixaEscala[0] : 0, no.faixaEscala ? no.faixaEscala[1] : 24);
    }
    this._atualizarForaDeEscala();
    this.desenhar();
    this.salvar();
    this.aoMudarEscala();
  }

  _foraDeEscala(no) {
    if (no.tipo !== 'camada' || !no.faixaEscala) return false;
    const z = this.map.getZoom();
    const [mn, mx] = no.faixaEscala;
    return z < mn || z >= mx;
  }

  _atualizarForaDeEscala() {
    // nada a computar aqui além do que _foraDeEscala já faz sob demanda; existe como ponto único de
    // chamada para quem quiser reagir ao evento de zoom sem duplicar a conta.
  }

  // --------------------------------------------------------------------------------------- desenho (DOM)
  /* usado pela Legenda (web/js/legenda.js) para respeitar a MESMA visibilidade/escala/ordem da árvore,
     sem recalcular por conta própria. */
  camadasParaLegenda() {
    const ativos = [];
    const varrer = (itens) => {
      for (const no of itens) {
        if (no.tipo === 'grupo') { varrer(no.itens); continue; }
        if (!this.catalogo.ativas.includes(no.id)) continue;
        ativos.push({ id: no.id, tituloExibido: this.tituloExibido(no),
          idsDeEstilo: this._idsDeEstilo(no.id), foraDeEscala: this._foraDeEscala(no) });
      }
    };
    varrer(this.itens);
    return ativos;
  }

  desenhar() {
    const raiz = this.raiz;
    limpar(raiz);
    const desenharNivel = (itens, alvo, nivel) => {
      for (const no of itens) alvo.append(this._linha(no, nivel));
    };
    desenharNivel(this.itens, raiz, 0);
  }

  _linha(no, nivel) {
    const ativa = no.tipo === 'camada' ? this.catalogo.ativas.includes(no.id) : achatar(no.itens).some((id) => this.catalogo.ativas.includes(id));
    const foraDeEscala = no.tipo === 'camada' && this._foraDeEscala(no);
    const li = h('li', {
      class: `arvore-linha${ativa ? ' ativa' : ''}${foraDeEscala ? ' fora-de-escala' : ''}${no.tipo === 'grupo' ? ' grupo' : ''}`,
      dataset: { chave: no.chave, tipo: no.tipo, camada: no.tipo === 'camada' ? no.id : '' },
      style: `--nivel: ${nivel}`,
      draggable: 'true',
      tabindex: '0',
      role: 'treeitem',
      'aria-selected': this._foco === no.chave ? 'true' : 'false',
    });
    li.addEventListener('focus', () => { this._foco = no.chave; });
    this._instalarTeclado(li, no);
    this._instalarArrasto(li, no);

    const caixa = h('input', {
      type: 'checkbox', checked: ativa, id: `chk-${no.chave}`,
      'aria-label': `mostrar ${this.tituloExibido(no)}`,
      onchange: () => this.alternar(no.chave),
    });
    const tituloEl = no.tipo === 'grupo'
      ? h('button', { type: 'button', class: 'arvore-titulo arvore-titulo-grupo', onclick: () => { no.aberto = !no.aberto; this.desenhar(); } },
          no.aberto ? '▾ ' : '▸ ', this.tituloExibido(no))
      : h('label', { class: 'arvore-titulo camada-titulo', for: `chk-${no.chave}`, title: this.tituloExibido(no) }, this.tituloExibido(no));
    const cabecalho = h('div', { class: 'arvore-cabecalho' }, caixa, tituloEl);

    if (no.tipo === 'camada' && ativa) {
      const f = this.catalogo.ficha(no.id) || {};
      const opacidade = h('input', {
        type: 'range', min: '0', max: '100', step: '1', class: 'camada-opacidade',
        value: String(Math.round((this.catalogo.opacidade.get(no.id) ?? 1) * 100)),
        'aria-label': `opacidade de ${this.tituloExibido(no)}`,
        oninput: (ev) => this.catalogo.definirOpacidade(no.id, Number(ev.target.value) / 100),
      });
      const btn = (rotulo, acao, aria) => h('button', {
        type: 'button', class: 'botao-mini', dataset: { acao }, 'aria-label': aria,
        onclick: (ev) => { ev.stopPropagation(); this._acao(acao, no); },
      }, rotulo);
      const linhaBotoes = h('div', { class: 'arvore-controles' },
        btn('▲', 'subir', 'subir'), btn('▼', 'descer', 'descer'),
        btn('⤢', 'enquadrar', 'enquadrar'), btn('✎', 'renomear', 'renomear no mapa'),
        btn('⌗', 'tabela', 'mostrar tabela'), btn('ℹ', 'propriedades', 'propriedades'),
        btn('◐', 'estilo', 'estilo'), btn('▥', 'grafico', 'gráfico'), btn('✕', 'remover', 'remover'));
      const faixa = this._controleDeEscala(no);
      li.append(cabecalho, h('div', { class: 'arvore-linha-controles' }, opacidade, linhaBotoes), faixa);
      if (f.n_feicoes !== undefined && f.n_feicoes !== null) {
        cabecalho.append(h('span', { class: 'arvore-conta' }, f.n_feicoes.toLocaleString('pt-BR')));
      }
    } else if (no.tipo === 'grupo') {
      const btnRemover = h('button', { type: 'button', class: 'botao-mini', 'aria-label': 'remover grupo',
        onclick: (ev) => { ev.stopPropagation(); this.remover(no.chave); } }, '✕');
      cabecalho.append(btnRemover);
      li.append(cabecalho);
      if (no.aberto) {
        const sub = h('ul', { class: 'arvore-sub' });
        for (const filho of no.itens) sub.append(this._linha(filho, nivel + 1));
        li.append(sub);
      }
    } else {
      li.append(cabecalho, h('button', { type: 'button', class: 'botao-mini', 'aria-label': 'remover',
        onclick: (ev) => { ev.stopPropagation(); this.remover(no.chave); } }, '✕'));
    }
    return li;
  }

  _controleDeEscala(no) {
    const faixa = no.faixaEscala || [null, null];
    const min = h('input', { type: 'number', min: '0', max: '24', step: '1', class: 'escala-min',
      value: faixa[0] === null ? '' : String(faixa[0]), placeholder: '0', 'aria-label': 'zoom mínimo' });
    const max = h('input', { type: 'number', min: '0', max: '24', step: '1', class: 'escala-max',
      value: faixa[1] === null ? '' : String(faixa[1]), placeholder: '24', 'aria-label': 'zoom máximo' });
    const aplicar = () => {
      const mn = min.value === '' ? null : Number(min.value);
      const mx = max.value === '' ? null : Number(max.value);
      this.definirFaixaDeEscala(no.chave, mn, mx === null ? null : mx);
    };
    min.addEventListener('change', aplicar);
    max.addEventListener('change', aplicar);
    return h('div', { class: 'arvore-escala' }, h('span', {}, 'faixa de escala z'), min, h('span', {}, '–'), max);
  }

  _acao(acao, no) {
    if (acao === 'subir') return this.moverRelativo(no.chave, -1);
    if (acao === 'descer') return this.moverRelativo(no.chave, 1);
    if (acao === 'enquadrar') return this.aoEnquadrar(no.id);
    if (acao === 'remover') return this.remover(no.chave);
    if (acao === 'renomear') {
      const novo = window.prompt('título no mapa', this.tituloExibido(no));
      if (novo !== null) this.renomearCamada(no.chave, novo);
      return null;
    }
    if (acao === 'tabela' || acao === 'propriedades' || acao === 'estilo' || acao === 'grafico') {
      this.aoAbrirPainel(acao, no.id);
      this.raiz.dispatchEvent(new CustomEvent('plat:abrir-painel', { detail: { acao, camada: no.id }, bubbles: true }));
      return null;
    }
    return null;
  }

  _instalarTeclado(li, no) {
    li.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowUp' && !ev.altKey) { ev.preventDefault(); if (this.moverRelativo(no.chave, -1)) this._focar(no.chave); }
      else if (ev.key === 'ArrowDown' && !ev.altKey) { ev.preventDefault(); if (this.moverRelativo(no.chave, 1)) this._focar(no.chave); }
      else if (ev.key === 'ArrowRight' && ev.altKey) { ev.preventDefault(); if (this.indentar(no.chave)) this._focar(no.chave); }
      else if (ev.key === 'ArrowLeft' && ev.altKey) { ev.preventDefault(); if (this.outdentar(no.chave)) this._focar(no.chave); }
      else if (ev.key === ' ' || ev.key === 'Enter') { ev.preventDefault(); this.alternar(no.chave); }
      else if (ev.key === 'Delete') { ev.preventDefault(); this.remover(no.chave); }
    });
  }

  _focar(chave) {
    requestAnimationFrame(() => {
      const el = this.raiz.querySelector(`[data-chave="${chave}"]`);
      if (el) el.focus();
    });
  }

  _instalarArrasto(li, no) {
    li.addEventListener('dragstart', (ev) => {
      this._arrastando = no.chave;
      ev.dataTransfer.effectAllowed = 'move';
      try { ev.dataTransfer.setData('text/plain', no.chave); } catch { /* alguns navegadores recusam em teste */ }
    });
    li.addEventListener('dragover', (ev) => { ev.preventDefault(); li.classList.add('alvo'); });
    li.addEventListener('dragleave', () => li.classList.remove('alvo'));
    li.addEventListener('drop', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      li.classList.remove('alvo');
      const origem = this._arrastando || ev.dataTransfer.getData('text/plain');
      this._arrastando = null;
      if (!origem || origem === no.chave) return;
      if (no.tipo === 'grupo' && ev.shiftKey) this.mover(origem, null, no.chave); // shift+solto = entra no grupo
      else this.mover(origem, no.chave, null);
    });
  }
}

function noGrupoDe(no, itens) {
  return { tipo: 'grupo', id: no.id, chave: idCurto(), titulo: no.titulo, aberto: no.aberto !== false, itens };
}

function achatarChaves(no) {
  if (!no) return [];
  if (no.tipo === 'camada') return [no.chave];
  const saida = [no.chave];
  for (const filho of no.itens) saida.push(...achatarChaves(filho));
  return saida;
}

function profundidadeMaxima(itens, atual = 1) {
  let maior = atual;
  for (const no of itens) {
    if (no.tipo === 'grupo') maior = Math.max(maior, profundidadeMaxima(no.itens, atual + 1));
  }
  return maior;
}

export { achatar, CHAVE_PADRAO };
