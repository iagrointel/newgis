import { PlatWidget, definir } from './base.js';
import { envelope } from '../app/cql2.js';

export const contrato = Object.freeze({
  eventos: ['clique', 'selecao_mudou', 'extensao_mudou', 'registros_carregados', 'mapa.selecao', 'mapa.extensao_alterada'],
  acoes: ['filtrar', 'selecionar', 'limpar_filtro', 'limpar_selecao', 'zoom', 'pan', 'piscar', 'popup', 'mapa.enquadrar', 'mapa.destacar'],
});

/* Widget de mapa do app (L5-06 base; L5-07 dado). Desenha as feições da VISTA num SVG próprio, projetadas do
   envelope da vista para a caixa do widget (equiretangular): ponto vira círculo, linha vira polilinha, polígono
   vira caminho; clique na feição muda a seleção da vista (evento `clique` + `selecao_mudou` pela vista); a
   extensão visível é um estado real (`zoom`/`pan` mudam-na e emitem `extensao_mudou`); `popup` abre um
   `<dialog>` com as propriedades; `piscar` destaca por 1,2 s. O mapa-base MapLibre e o estilo por camada são o
   item L5-01-b (widgets de mapa): este renderizador é a camada de DADO do widget, e continua válido por baixo. */
class PlatMapa extends PlatWidget {
  #extensao = null;   // [xmin, ymin, xmax, ymax] visível
  #extensaoDoDado = false;  // false = extensão padrão (antes de a fonte carregar); recalcula quando o dado chega
  #destaque = new Set();

  renderizar() {
    this.setAttribute('role', 'application');
    this.setAttribute('aria-label', this.configuracao.rotulo || 'mapa');
    const altura = this.configuracao.altura || 320;
    const largura = Math.max(200, this.clientWidth || 600);
    const feicoes = this.vista ? this.vista.registros() : [];
    const selecao = this.vista ? this.vista.selecao : new Set();
    if (!this.#extensao || (!this.#extensaoDoDado && feicoes.length)) {
      const env = envelopeDe(feicoes);
      this.#extensao = env || [-75, -35, -30, 6];
      this.#extensaoDoDado = !!env;
    }
    const [xmin, ymin, xmax, ymax] = this.#extensao;
    const sx = largura / Math.max(1e-9, xmax - xmin); const sy = altura / Math.max(1e-9, ymax - ymin);
    const px = (x) => ((x - xmin) * sx).toFixed(1); const py = (y) => (altura - (y - ymin) * sy).toFixed(1);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
    svg.setAttribute('width', '100%'); svg.setAttribute('height', String(altura));
    svg.setAttribute('aria-label', `${feicoes.length} feição(ões)`);
    const camada = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    camada.setAttribute('class', 'mapa-feicoes');
    let desenhadas = 0;
    for (const f of feicoes) {
      const el = desenhar(f.geometria, px, py);
      if (!el) continue;
      el.setAttribute('class', 'feicao' + (selecao.has(f.id) ? ' selecionada' : '') + (this.#destaque.has(f.id) ? ' destaque' : ''));
      el.dataset.id = String(f.id);
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      const rotulo = this.configuracao.campo_rotulo ? f.propriedades?.[this.configuracao.campo_rotulo] : f.id;
      const titulo = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      titulo.textContent = String(rotulo ?? f.id);
      el.append(titulo);
      el.addEventListener('click', (e) => { e.stopPropagation(); this.#clique(f, e.shiftKey); });
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.#clique(f, e.shiftKey); } });
      camada.append(el);
      desenhadas += 1;
    }
    svg.append(camada);
    svg.addEventListener('click', () => { if (this.vista && this.vista.selecao.size) this.vista.definirSelecao([], this.noId); });
    this.dataset.total = String(desenhadas);
    this.dataset.extensao = this.#extensao.map((v) => v.toFixed(4)).join(',');
    const barra = document.createElement('div');
    barra.className = 'mapa-barra';
    barra.textContent = `${desenhadas} feição(ões) · ${selecao.size} selecionada(s)`;
    this.replaceChildren(svg, barra);
  }

  #clique(f, acumular) {
    if (!this.vista) { this.emitir('clique', { id: f.id, ids: [f.id] }); return; }
    const ids = acumular ? [...this.vista.selecao, f.id] : [f.id];
    this.emitir('clique', { id: f.id, ids });
    this.vista.definirSelecao(ids, this.noId);
    this.emitir('mapa.selecao', { ids });
  }

  #definirExtensao(ext) {
    this.#extensao = ext;
    this.#extensaoDoDado = true;
    this.renderizar();
    this.emitir('extensao_mudou', { extensao: ext });
    this.emitir('mapa.extensao_alterada', { extensao: ext });
  }

  acao_zoom(detalhe = {}) {
    const alvo = detalhe.extensao || envelopeDe(detalhe.registros || []) || this.vista?.envelopeSelecao();
    if (!alvo) return;
    const fator = Number(detalhe.fator || 1.2);
    const cx = (alvo[0] + alvo[2]) / 2; const cy = (alvo[1] + alvo[3]) / 2;
    const w = Math.max(1e-6, (alvo[2] - alvo[0]) * fator); const h = Math.max(1e-6, (alvo[3] - alvo[1]) * fator);
    this.#definirExtensao([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]);
  }

  acao_pan(detalhe = {}) {
    const alvo = detalhe.extensao || envelopeDe(detalhe.registros || []) || this.vista?.envelopeSelecao();
    if (!alvo || !this.#extensao) return;
    const w = this.#extensao[2] - this.#extensao[0]; const h = this.#extensao[3] - this.#extensao[1];
    const cx = (alvo[0] + alvo[2]) / 2; const cy = (alvo[1] + alvo[3]) / 2;
    this.#definirExtensao([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]);
  }

  acao_piscar(detalhe = {}) {
    const ids = (detalhe.registros || []).map((f) => f.id);
    if (!ids.length) { super.acao_piscar(); return; }
    this.#destaque = new Set(ids);
    this.renderizar();
    clearTimeout(this._piscar);
    this._piscar = setTimeout(() => { this.#destaque = new Set(); this.renderizar(); }, 1200);
  }

  acao_popup(detalhe = {}) {
    const f = (detalhe.registros || [])[0];
    if (!f) return;
    this.querySelector('dialog')?.remove();
    const dlg = document.createElement('dialog');
    dlg.className = 'mapa-popup';
    const dl = document.createElement('dl');
    for (const [k, v] of Object.entries(f.propriedades || {})) {
      if (k === '__id') continue;
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = String(v ?? '');
      dl.append(dt, dd);
    }
    const fechar = document.createElement('button'); fechar.type = 'button'; fechar.textContent = 'Fechar';
    fechar.addEventListener('click', () => dlg.close());
    dlg.append(dl, fechar);
    this.append(dlg);
    dlg.show();
  }

  acao_mapa_enquadrar(detalhe) { this.acao_zoom({ ...detalhe, fator: 1 }); this.dispatchEvent(new CustomEvent('plat-mapa-enquadrar', { detail: detalhe })); }
  acao_mapa_destacar(detalhe) { this.acao_piscar(detalhe); this.dispatchEvent(new CustomEvent('plat-mapa-destacar', { detail: detalhe })); }
}

function envelopeDe(feicoes) {
  let env = null;
  for (const f of feicoes) {
    const e = envelope(f.geometria);
    if (!e) continue;
    env = env ? [Math.min(env[0], e[0]), Math.min(env[1], e[1]), Math.max(env[2], e[2]), Math.max(env[3], e[3])] : e;
  }
  if (!env) return null;
  const w = env[2] - env[0] || 0.01; const h = env[3] - env[1] || 0.01;
  return [env[0] - w * 0.05, env[1] - h * 0.05, env[2] + w * 0.05, env[3] + h * 0.05];
}

function desenhar(g, px, py) {
  if (!g) return null;
  const ns = 'http://www.w3.org/2000/svg';
  if (g.type === 'Point') {
    const c = document.createElementNS(ns, 'circle');
    c.setAttribute('cx', px(g.coordinates[0])); c.setAttribute('cy', py(g.coordinates[1])); c.setAttribute('r', '6');
    return c;
  }
  const anel = (coords) => coords.map((p) => `${px(p[0])},${py(p[1])}`).join(' ');
  if (g.type === 'LineString') { const el = document.createElementNS(ns, 'polyline'); el.setAttribute('points', anel(g.coordinates)); return el; }
  if (g.type === 'Polygon') { const el = document.createElementNS(ns, 'path'); el.setAttribute('d', g.coordinates.map((r) => 'M' + anel(r) + 'Z').join(' ')); return el; }
  if (g.type === 'MultiPoint' || g.type === 'MultiLineString' || g.type === 'MultiPolygon') {
    const grupo = document.createElementNS(ns, 'g');
    const tipo = g.type.slice(5);
    for (const c of g.coordinates) { const el = desenhar({ type: tipo, coordinates: c }, px, py); if (el) grupo.append(el); }
    return grupo;
  }
  return null;
}

definir('plat-mapa', PlatMapa);
