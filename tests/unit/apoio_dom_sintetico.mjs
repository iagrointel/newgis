/* plat — DOM sintético mínimo para rodar widgets/executor em Node sem navegador (esta máquina não tem
   headless — ver CLAUDE.md do laço/plataforma). NÃO é um jsdom: cobre só o que `web/js/widgets/base.js`,
   os nove módulos de widget de página (item L5-01-d) e `web/js/executor/executor.js::desenharNo` tocam de
   verdade — `document.createElement` (elemento comum e CUSTOM ELEMENT, via `customElements`), `dataset`
   (Proxy sobre atributos `data-*`), `className`/`classList`, `append`/`appendChild`/`replaceChildren`/
   `remove`, `querySelector`/`querySelectorAll` (seletor simples: tag e/ou `[attr]`/`[attr="valor"]`, sem
   combinador — o único tipo que estes módulos usam) e `connectedCallback`/`disconnectedCallback` quando um
   nó entra ou sai da árvore cujo topo é `document` (sempre "conectado"). `addEventListener`/`dispatchEvent`
   vêm de graça do `EventTarget` nativo do Node — não reimplementados aqui; só não há bubbling de verdade
   (o widget dispara em `this` e quem ouve também ouve em `this`, então nunca precisou de propagação).

   Uso: `import { instalarDomSintetico } from './apoio_dom_sintetico.mjs'; instalarDomSintetico();` ANTES de
   importar qualquer módulo de `web/js/widgets/*.js` ou `web/js/executor/executor.js` — os módulos de widget
   chamam `customElements.define(...)` no TOPO do arquivo (`definir(...)` de `base.js`), na hora do import. */

function paraAtributo(chave) { return chave.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`); }
function paraCamel(atributo) { return atributo.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase()); }

class ListaClasses {
  constructor(el) { this.el = el; }
  #ler() { return (this.el.getAttribute('class') || '').split(/\s+/).filter(Boolean); }
  #escrever(lista) { this.el.setAttribute('class', lista.join(' ')); }
  add(...nomes) { const l = this.#ler(); for (const n of nomes) if (!l.includes(n)) l.push(n); this.#escrever(l); }
  remove(...nomes) { this.#escrever(this.#ler().filter((n) => !nomes.includes(n))); }
  toggle(nome, forcar) {
    const tem = this.#ler().includes(nome);
    const querTer = forcar === undefined ? !tem : forcar;
    if (querTer) this.add(nome); else this.remove(nome);
    return querTer;
  }
  contains(nome) { return this.#ler().includes(nome); }
}

function criarDataset(el) {
  return new Proxy({}, {
    get(_alvo, prop) {
      if (typeof prop !== 'string') return undefined;
      const v = el.getAttribute(`data-${paraAtributo(prop)}`);
      return v === null ? undefined : v;
    },
    set(_alvo, prop, valor) { el.setAttribute(`data-${paraAtributo(String(prop))}`, String(valor)); return true; },
    deleteProperty(_alvo, prop) { el.removeAttribute(`data-${paraAtributo(String(prop))}`); return true; },
    has(_alvo, prop) { return el.hasAttribute(`data-${paraAtributo(String(prop))}`); },
    ownKeys() { return [...el.__attrs.keys()].filter((k) => k.startsWith('data-')).map((k) => paraCamel(k.slice(5))); },
    getOwnPropertyDescriptor(_alvo, prop) {
      const v = el.getAttribute(`data-${paraAtributo(String(prop))}`);
      return v === null ? undefined : { enumerable: true, configurable: true, value: v };
    },
  });
}

function conectar(no) {
  no._conectado = true;
  if (typeof no.connectedCallback === 'function') no.connectedCallback();
  for (const filho of no.childNodes) conectar(filho);
}

function desconectar(no) {
  no._conectado = false;
  if (typeof no.disconnectedCallback === 'function') no.disconnectedCallback();
  for (const filho of no.childNodes) desconectar(filho);
}

function bate(el, seletor) {
  const m = seletor.trim().match(/^([a-zA-Z][a-zA-Z0-9-]*)?(\[[^\]]+\])?$/);
  if (!m) throw new Error(`seletor não suportado pelo DOM sintético: ${seletor}`);
  const [, tag, atributo] = m;
  if (tag && el.localName !== tag.toLowerCase()) return false;
  if (atributo) {
    const am = atributo.slice(1, -1).match(/^([a-zA-Z0-9_-]+)(?:="([^"]*)")?$/);
    if (!am) throw new Error(`seletor de atributo não suportado: ${atributo}`);
    const [, nome, valor] = am;
    if (!el.hasAttribute(nome)) return false;
    if (valor !== undefined && el.getAttribute(nome) !== valor) return false;
  }
  return true;
}

function buscar(raiz, seletor) {
  const achados = [];
  const visitar = (no) => {
    for (const filho of no.childNodes) {
      if (filho.nodeType === 1) { if (bate(filho, seletor)) achados.push(filho); visitar(filho); }
    }
  };
  visitar(raiz);
  return achados;
}

class NoSintetico extends EventTarget {
  constructor() {
    super();
    this.parentNode = null;
    this.childNodes = [];
    this._conectado = false;
  }

  get isConnected() { return this._conectado; }
  get firstChild() { return this.childNodes[0] || null; }

  appendChild(no) {
    if (no.parentNode) no.parentNode.removeChild(no);
    no.parentNode = this;
    this.childNodes.push(no);
    if (this.isConnected) conectar(no);
    return no;
  }

  append(...nos) { for (const n of nos) this.appendChild(typeof n === 'string' ? new TextoSintetico(n) : n); }

  prepend(...nos) {
    for (const n of nos.reverse()) {
      if (n.parentNode) n.parentNode.removeChild(n);
      n.parentNode = this;
      this.childNodes.unshift(n);
      if (this.isConnected) conectar(n);
    }
  }

  removeChild(no) {
    const i = this.childNodes.indexOf(no);
    if (i >= 0) {
      this.childNodes.splice(i, 1);
      no.parentNode = null;
      if (no.isConnected) desconectar(no);
    }
    return no;
  }

  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  replaceChildren(...nos) { for (const f of [...this.childNodes]) this.removeChild(f); this.append(...nos); }
  contains(no) { let n = no; while (n) { if (n === this) return true; n = n.parentNode; } return false; }
}

class TextoSintetico extends NoSintetico {
  constructor(texto) { super(); this.nodeType = 3; this.data = String(texto); }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}

export class ElementoSintetico extends NoSintetico {
  constructor(tag = '') {
    super();
    this.nodeType = 1;
    this.__localName = String(tag).toLowerCase();
    this.__attrs = new Map();
    this.style = {};
    this.dataset = criarDataset(this);
  }

  get localName() { return this.__localName; }
  get tagName() { return this.__localName.toUpperCase(); }
  get classList() { this.__classList ||= new ListaClasses(this); return this.__classList; }
  get className() { return this.getAttribute('class') || ''; }
  set className(v) { this.setAttribute('class', v); }
  get id() { return this.getAttribute('id') || ''; }
  set id(v) { this.setAttribute('id', v); }
  get hidden() { return this.hasAttribute('hidden'); }
  set hidden(v) { if (v) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); }

  setAttribute(nome, valor) { this.__attrs.set(nome, String(valor)); }
  getAttribute(nome) { return this.__attrs.has(nome) ? this.__attrs.get(nome) : null; }
  removeAttribute(nome) { this.__attrs.delete(nome); }
  hasAttribute(nome) { return this.__attrs.has(nome); }

  toggleAttribute(nome, forcar) {
    const tem = this.hasAttribute(nome);
    const querTer = forcar === undefined ? !tem : forcar;
    if (querTer) this.setAttribute(nome, ''); else this.removeAttribute(nome);
    return querTer;
  }

  get textContent() {
    return this.childNodes.map((n) => (n.nodeType === 1 ? n.textContent : n.data || '')).join('');
  }

  set textContent(v) { this.replaceChildren(); if (v !== '' && v != null) this.appendChild(new TextoSintetico(v)); }

  /* serialização simples (sem escape de entidade — não é usada como sanitizador, só para o teste ler o que
     `incorporar.js` põe em `iframe.srcdoc = limpo.innerHTML`) */
  get innerHTML() {
    return this.childNodes.map((n) => {
      if (n.nodeType !== 1) return n.data || '';
      const attrs = [...n.__attrs.entries()].map(([k, v]) => ` ${k}="${v}"`).join('');
      return `<${n.localName}${attrs}>${n.innerHTML}</${n.localName}>`;
    }).join('');
  }

  querySelectorAll(seletor) { return buscar(this, seletor); }
  querySelector(seletor) { return buscar(this, seletor)[0] || null; }

  closest(seletor) {
    let n = this;
    while (n) { if (n.nodeType === 1 && bate(n, seletor)) return n; n = n.parentNode; }
    return null;
  }
}

class DocumentoSintetico extends ElementoSintetico {
  constructor() { super('#document'); this._conectado = true; }
  createElement(tag) {
    const nome = String(tag).toLowerCase();
    const Ctor = globalThis.customElements?.get(nome);
    if (Ctor) { const el = new Ctor(); el.__localName = nome; return el; }
    return new ElementoSintetico(nome);
  }

  createTextNode(texto) { return new TextoSintetico(texto); }
  get documentElement() { this.__docEl ||= new ElementoSintetico('html'); return this.__docEl; }
  get body() { this.__body ||= new ElementoSintetico('body'); return this.__body; }
}

class RegistroElementosSintetico {
  #mapa = new Map();
  define(nome, Ctor) { this.#mapa.set(nome, Ctor); }
  get(nome) { return this.#mapa.get(nome); }
}

/* instala os globais que os módulos de widget/executor esperam achar prontos (nunca importados por eles —
   `document`/`customElements`/`HTMLElement`/`location`/`fetch`/`CSS` são globais de navegador de verdade). */
export function instalarDomSintetico({ href = 'http://localhost/executar?item=teste', fetch = null } = {}) {
  globalThis.Node = NoSintetico; // `dom.js::anexar` faz `f instanceof Node` para distinguir nó de texto puro
  globalThis.HTMLElement = ElementoSintetico;
  globalThis.customElements = new RegistroElementosSintetico();
  globalThis.document = new DocumentoSintetico();
  globalThis.window = globalThis;
  globalThis.location = new URL(href); // URL já tem href/origin/search/pathname — o suficiente aqui
  globalThis.CSS = { escape: (v) => String(v).replace(/[^a-zA-Z0-9_-]/g, (c) => `\\${c}`) };
  // login.js chama `obter('/api/eu')` (base/api.js::chamar → fetch); sem stub, a suíte tentaria rede de
  // verdade. Sem `fetch` explícito, responde 401 (não autenticado) — o caminho comum do widget.
  globalThis.fetch = fetch || (async () => ({ status: 401, headers: { get: () => null }, json: async () => ({}) }));
  return globalThis.document;
}

/* espera as microtarefas pendentes esvaziarem (o `atualizar()` assíncrono de `login.js` não é aguardado por
   `renderizar()` de propósito — é "dispara e some", igual ao navegador). Duas voltas de `setImmediate`
   cobrem a cadeia fetch→json→renderizar do stub acima com folga. */
export async function esvaziarMicrotarefas(voltas = 2) {
  for (let i = 0; i < voltas; i += 1) await new Promise((r) => setImmediate(r));
}
