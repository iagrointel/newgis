/* plat · mapa — popup em tempo de execução (item L2-01-d-popup-runtime; a base era o popup simples do
   item L2-01-mapa-web, com campo nulo marcado — este item ACRESCENTA paginação, formato por tipo,
   painel acoplado em tela estreita, campo/expressão resolvidos no servidor e zoom para a feição).

   Clique no mapa: o MapLibre devolve as feições DESENHADAS naquele ponto (queryRenderedFeatures), com
   os atributos que vieram dentro do tile vetorial — sem ida ao banco por clique. As camadas são
   consultadas na ORDEM de desenho (`catalogo.ativas`, a de cima primeiro), e o resultado de todas vira
   UMA lista só: é nela que a paginação "i de N" anda, não uma tabela por camada.

   Dois casos da refutação do item-pai (L2-01-mapa-web) continuam tratados aqui:
   * campo NULO: o MVT não carrega a chave quando o valor é nulo no banco; a janela mostra "—", nunca
     "null"/"undefined" (`formato.js::SEM_VALOR`), porque sumir da tela é pior que aparecer vazio.
   * geometria MULTI: um multipolígono vira várias feições no tile; a lista deduplica por
     (camada, fid) antes de contar — é o que faz "1 de 3" ser o número de FEIÇÕES, não de pedaços.

   Campo marcado `servidor: true` na configuração (`app/mapa/popup.py::normalizar`) e toda `expressão`
   nunca vêm do tile: a janela pede `GET /api/camadas/{id}/feicoes/{fid}/popup` só quando o usuário está
   OLHANDO aquela feição (não para as N-1 outras da paginação) e escreve o resultado por cima do
   texto de espera "carregando…" quando chega — cliques rápidos cancelam o pedido anterior
   (AbortController), a refutação "50 cliques sem consulta pendurada". */
import { h, limpar } from '../base/dom.js';
import { obter } from '../base/api.js';
import { t } from '../base/i18n.js';
import { SEM_VALOR, valorExibicao, urlSegura } from './formato.js';

const LARGURA_PAINEL_ACOPLADO = 480; // <= este valor: painel inferior, não popup flutuante (viewport 390 do portão)

function tituloDaFeicao(ficha, props) {
  const modelo = (ficha.popup && ficha.popup.titulo) || null;
  if (modelo) {
    return modelo.replace(/\{(\w+)\}/g, (_, k) => (props[k] === undefined || props[k] === null ? SEM_VALOR : String(props[k])));
  }
  return ficha.titulo;
}

function camposDaFicha(ficha) {
  const cfg = ficha.popup;
  if (cfg && cfg.campos && cfg.campos.length) return cfg.campos;
  // camada sem popup configurado: todo campo do catálogo, como texto (comportamento anterior preservado)
  return (ficha.campos || []).map((c) => ({ nome: c.nome, rotulo: c.nome, tipo: 'texto', decimais: null, servidor: false }));
}

/* {camadaId: [feição, ...]} na ORDEM de `ativas`, sem repetir a mesma feição (multi-geometria em pedaços) */
export function agrupar(feicoesPorCamada, catalogo) {
  const porCamada = new Map();
  for (const camadaId of catalogo.ativas) {
    const lista = [];
    const vistos = new Set();
    for (const f of feicoesPorCamada.get(camadaId) || []) {
      const chave = `${camadaId}:${f.id ?? (f.properties && f.properties.fid) ?? JSON.stringify(f.properties)}`;
      if (vistos.has(chave)) continue;
      vistos.add(chave);
      f._chave = chave;
      lista.push(f);
    }
    if (lista.length && catalogo.ficha(camadaId)) porCamada.set(camadaId, lista);
  }
  return porCamada;
}

/* achata {camadaId: [feição]} numa lista única [{camadaId, ficha, feicao}], ordem de `ativas` */
function listaUnica(porCamada, catalogo) {
  const saida = [];
  for (const [camadaId, feicoes] of porCamada) {
    const ficha = catalogo.ficha(camadaId);
    for (const feicao of feicoes) saida.push({ camadaId, ficha, feicao });
  }
  return saida;
}

function linhaDeCampo(campo, valor, fuso) {
  const nulo = valor === null || valor === undefined || valor === '';
  const td = h('td', { class: nulo ? 'nulo' : '' });
  if (!nulo && campo.tipo === 'url') {
    const href = urlSegura(valor);
    if (href) td.append(h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, href));
    else td.append(String(valor));
  } else if (!nulo && campo.tipo === 'imagem') {
    const href = urlSegura(valor);
    if (href) td.append(h('img', { src: href, alt: campo.rotulo, loading: 'lazy', class: 'popup-imagem' }));
    else td.append(String(valor));
  } else {
    td.append(nulo ? SEM_VALOR : valorExibicao(valor, campo, fuso));
  }
  return h('tr', { dataset: { campo: campo.nome, nulo: nulo ? '1' : '0' } },
    h('th', { scope: 'row' }, campo.rotulo), td);
}

function linhaServidor(nome, rotulo) {
  return h('tr', { dataset: { campo: nome, servidor: '1' } },
    h('th', { scope: 'row' }, rotulo), h('td', { class: 'carregando' }, t('mapa.popup_carregando')));
}

/* busca os campos "servidor" e as expressões desta feição e escreve por cima do "carregando…";
   `sinal` cancela um pedido anterior ainda em voo (refutação "50 cliques sem consulta pendurada"). */
async function preencherDoServidor(caixa, camadaId, fid, ficha, sinal) {
  const r = await obter(`/api/camadas/${camadaId}/feicoes/${fid}/popup`, { signal: sinal });
  if (sinal.aborted) return; // outro clique já assumiu; nunca escreve numa janela que não é mais a atual
  if (r.status !== 200) {
    caixa.querySelectorAll('td.carregando').forEach((td) => { td.textContent = SEM_VALOR; td.classList.remove('carregando'); });
    return;
  }
  const corpo = r.json;
  for (const campo of camposDaFicha(ficha)) {
    if (!campo.servidor) continue;
    const linha = caixa.querySelector(`tr[data-campo="${CSS.escape(campo.nome)}"]`);
    if (!linha) continue;
    const info = corpo.campos_servidor && corpo.campos_servidor[campo.nome];
    const td = linha.querySelector('td');
    limpar(td);
    td.classList.remove('carregando');
    const texto = info && info.formatado !== null && info.formatado !== undefined ? info.formatado : SEM_VALOR;
    td.dataset.nulo = texto === SEM_VALOR ? '1' : '0';
    if (texto === SEM_VALOR) td.classList.add('nulo');
    td.append(texto);
  }
  for (const [nome, res] of Object.entries(corpo.expressoes || {})) {
    const linha = caixa.querySelector(`tr[data-expressao="${CSS.escape(nome)}"]`);
    if (!linha) continue;
    const td = linha.querySelector('td');
    limpar(td);
    td.classList.remove('carregando');
    td.append(res.erro ? SEM_VALOR : (res.formatado ?? SEM_VALOR));
  }
}

/* monta a ficha de UMA feição (o corpo do popup, sem o cabeçalho de paginação) */
function montarFicha(item, fuso, sinalServidor) {
  const { ficha, feicao, camadaId } = item;
  const props = feicao.properties || {};
  const fid = props.fid ?? feicao.id;
  const campos = camposDaFicha(ficha);
  const corpo = h('div', { class: 'popup-conteudo' });
  corpo.append(h('h3', {}, tituloDaFeicao(ficha, props)));
  const tabela = h('table', { class: 'popup-tabela' });
  const tbody = h('tbody');
  for (const campo of campos) {
    if (campo.servidor) tbody.append(linhaServidor(campo.nome, campo.rotulo));
    else tbody.append(linhaDeCampo(campo, props[campo.nome], fuso));
  }
  for (const exp of (ficha.popup && ficha.popup.expressoes) || []) {
    tbody.append(h('tr', { dataset: { expressao: exp.nome } },
      h('th', { scope: 'row' }, exp.rotulo), h('td', { class: 'carregando' }, t('mapa.popup_carregando'))));
  }
  tabela.append(tbody);
  corpo.append(tabela);

  const temServidor = campos.some((c) => c.servidor) || ((ficha.popup && ficha.popup.expressoes) || []).length > 0;
  if (temServidor && fid !== undefined && fid !== null) {
    preencherDoServidor(corpo, camadaId, fid, ficha, sinalServidor).catch(() => {
      /* aborto ou rede fora: os "carregando…" ficam SEM_VALOR só se a resposta chegar; senão a janela
         mostra "carregando…" até fechar — aceitável, nunca escreve dado errado (fronteira honesta) */
    });
  }

  const acoes = h('div', { class: 'popup-acoes' });
  acoes.append(h('button', {
    type: 'button', class: 'botao-mini', onclick: () => item._zoom && item._zoom(),
  }, t('mapa.popup_zoom')));
  corpo.append(acoes);
  return corpo;
}

function bboxDaGeometria(geom) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  const visitar = (c) => {
    if (typeof c[0] === 'number') {
      const [x, y] = c;
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    } else c.forEach(visitar);
  };
  visitar(geom.coordinates);
  return [[minX, minY], [maxX, maxY]];
}

export class JanelaPopup {
  constructor(map, catalogo, maplibregl) {
    this.map = map;
    this.catalogo = catalogo;
    this.maplibregl = maplibregl;
    this.itens = [];
    this.indice = 0;
    this.popup = null;
    this.painel = document.getElementById('popup-dock');
    this.controlador = null;
  }

  get acoplado() {
    return window.matchMedia(`(max-width: ${LARGURA_PAINEL_ACOPLADO}px)`).matches;
  }

  fechar() {
    if (this.controlador) { this.controlador.abort(); this.controlador = null; }
    if (this.popup) { this.popup.remove(); this.popup = null; }
    if (this.painel) { this.painel.hidden = true; limpar(this.painel); }
    this.itens = [];
  }

  fuso() {
    return (window.plat && window.plat.org && window.plat.org.fuso) || 'America/Sao_Paulo';
  }

  render(lngLat) {
    if (!this.itens.length) return this.fechar();
    if (this.controlador) this.controlador.abort();
    this.controlador = new AbortController();
    const item = this.itens[this.indice];
    item._zoom = () => {
      const [sw, ne] = bboxDaGeometria(item.feicao.geometry);
      this.map.fitBounds([sw, ne], { maxZoom: 18, padding: 60, duration: 300 });
    };
    const corpo = h('div', { class: 'popup-plat-raiz' });
    if (this.itens.length > 1) {
      const pager = h('div', { class: 'popup-pager' },
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('mapa.popup_anterior'),
          onclick: () => { this.indice = (this.indice - 1 + this.itens.length) % this.itens.length; this.render(lngLat); } }, '◀'),
        h('span', { class: 'popup-pager-texto' }, t('mapa.popup_paginacao', { i: this.indice + 1, n: this.itens.length })),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('mapa.popup_proximo'),
          onclick: () => { this.indice = (this.indice + 1) % this.itens.length; this.render(lngLat); } }, '▶'));
      corpo.append(pager);
    }
    corpo.append(montarFicha(item, this.fuso(), this.controlador.signal));

    if (this.acoplado) {
      if (this.popup) { this.popup.remove(); this.popup = null; }
      limpar(this.painel);
      const fecharBtn = h('button', { type: 'button', class: 'popup-dock-fechar', 'aria-label': t('mapa.popup_fechar'),
        onclick: () => this.fechar() }, '×');
      this.painel.append(fecharBtn, corpo);
      this.painel.hidden = false;
      this.painel.classList.add('popup-dock-aberto');
    } else {
      if (this.painel) { this.painel.hidden = true; limpar(this.painel); }
      if (!this.popup) {
        this.popup = new this.maplibregl.Popup({ closeButton: true, maxWidth: '360px', className: 'popup-plat' })
          .setLngLat(lngLat)
          .on('close', () => { this.itens = []; this.popup = null; if (this.controlador) this.controlador.abort(); });
        this.popup.addTo(this.map);
      }
      this.popup.setDOMContent(corpo);
    }
  }

  abrirEm(ev) {
    const camadas = this.catalogo.ativas.flatMap((id) => this.catalogo.idsDeEstilo(id))
      .filter((idc) => this.map.getLayer(idc));
    this.fechar();
    if (!camadas.length) return;
    const feicoesPorCamada = new Map();
    for (const camadaId of this.catalogo.ativas) {
      const ids = this.catalogo.idsDeEstilo(camadaId).filter((idc) => this.map.getLayer(idc));
      if (!ids.length) continue;
      feicoesPorCamada.set(camadaId, this.map.queryRenderedFeatures(ev.point, { layers: ids }));
    }
    const porCamada = agrupar(feicoesPorCamada, this.catalogo);
    this.itens = listaUnica(porCamada, this.catalogo);
    this.indice = 0;
    if (!this.itens.length) return;
    this.render(ev.lngLat);
  }
}

export function instalarPopup(map, catalogo, maplibregl) {
  const janela = new JanelaPopup(map, catalogo, maplibregl);
  map.on('click', (ev) => {
    if (map.getCanvas().style.cursor === 'crosshair') return; // medição em curso: o clique é dela
    janela.abrirEm(ev);
  });
  return { fechar: () => janela.fechar(), janela };
}
