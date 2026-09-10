/* plat · mapa — janela de atributos (popup) do item L2-01-mapa-web.

   Clique no mapa: o MapLibre devolve as feições DESENHADAS naquele ponto (queryRenderedFeatures), com
   os atributos que vieram dentro do tile vetorial — não há uma segunda ida ao banco por clique.

   Dois casos da refutação do item tratados aqui, de propósito:
   * campo NULO: o MVT simplesmente não carrega a chave da feição quando o valor é nulo no banco. A
     janela mostra o campo mesmo assim, com o texto "sem valor" — some da tela é pior que aparecer
     vazio, porque o usuário não sabe se o campo existe.
   * geometria MULTI: um multipolígono vira VÁRIAS feições no tile (uma por peça) e o clique pode
     devolver a mesma feição repetida. A janela deduplica por (camada, fid) antes de contar. */
import { h, limpar } from '../base/dom.js';
import { t } from '../base/i18n.js';

const SEM_VALOR = '—';

function valorTexto(v) {
  if (v === null || v === undefined || v === '') return SEM_VALOR;
  if (typeof v === 'number') return v.toLocaleString('pt-BR');
  return String(v);
}

export function atributosDaFeicao(feicao, campos) {
  /* devolve [{nome, valor, nulo}] na ordem declarada no catálogo; campos fora do catálogo entram depois */
  const props = feicao.properties || {};
  const saida = [];
  const vistos = new Set();
  for (const c of campos || []) {
    const nome = c.nome ?? c;
    vistos.add(nome);
    const tem = Object.prototype.hasOwnProperty.call(props, nome) && props[nome] !== null;
    saida.push({ nome, valor: tem ? valorTexto(props[nome]) : SEM_VALOR, nulo: !tem });
  }
  for (const [k, v] of Object.entries(props)) {
    if (vistos.has(k) || k === '_truncado') continue;
    saida.push({ nome: k, valor: valorTexto(v), nulo: v === null || v === undefined });
  }
  return saida;
}

export function agrupar(feicoes, catalogo) {
  /* {camadaId: [feição, ...]} sem repetir a mesma feição (multi-geometria vem em pedaços) */
  const porCamada = new Map();
  for (const f of feicoes) {
    const camadaId = (f.layer && f.layer.source || '').replace(/^plat-/, '');
    if (!catalogo.ficha(camadaId)) continue;
    const chave = `${camadaId}:${f.id ?? (f.properties && f.properties.fid) ?? JSON.stringify(f.properties)}`;
    const lista = porCamada.get(camadaId) || [];
    if (lista.some((x) => x._chave === chave)) continue;
    f._chave = chave;
    lista.push(f);
    porCamada.set(camadaId, lista);
  }
  return porCamada;
}

export function camposDestaque(campos, limite = 6) {
  const lista = campos || [];
  const destacados = lista.filter((c) => c.destaque === true);
  return destacados.length ? destacados : lista.slice(0, limite);
}

/* atributosDaFeicao preserva extras para os outros consumidores. Aqui a lista reduzida é explícita,
   senão os extras recolocariam todos os campos que acabamos de esconder. */
export function montarTabelaPopup(feicao, campos, maxCampos = 6) {
  const lista = campos?.length ? campos : Object.keys(feicao.properties || {})
    .filter((nome) => nome !== '_truncado').map((nome) => ({ nome }));
  const nomes = new Set(camposDestaque(lista, maxCampos).map((c) => c.nome ?? c));
  const completos = atributosDaFeicao(feicao, campos);
  const reduzidos = atributosDaFeicao(feicao, camposDestaque(lista, maxCampos)).filter((at) => nomes.has(at.nome));
  const caixa = h('div');
  const corpo = h('tbody');
  const desenhar = (atributos) => {
    limpar(corpo);
    for (const at of atributos) corpo.append(h('tr', { dataset: { campo: at.nome, nulo: at.nulo ? '1' : '0' } },
      h('th', { scope: 'row' }, at.nome), h('td', { class: at.nulo ? 'nulo' : '' }, at.valor)));
  };
  desenhar(reduzidos);
  caixa.append(h('table', { class: 'popup-tabela' }, corpo));
  if (completos.length > reduzidos.length) {
    const botao = h('button', { type: 'button', class: 'popup-ver-todos', onclick: () => {
      desenhar(completos); botao.remove();
    } }, t('mapa.popup_ver_todos'));
    caixa.append(botao);
  }
  return caixa;
}

export function montarConteudo(porCamada, catalogo, opcoes = {}) {
  const caixa = h('div', { class: 'popup-conteudo' });
  let total = 0;
  for (const [camadaId, feicoes] of porCamada) {
    const ficha = catalogo.ficha(camadaId);
    total += feicoes.length;
    const bloco = h('div', { class: 'popup-camada', dataset: { camada: camadaId } },
      h('h3', {}, ficha.titulo));
    for (const feicao of feicoes.slice(0, 5)) {
      bloco.append(montarTabelaPopup(feicao, ficha.campos, opcoes.maxCampos ?? 6));
    }
    if (feicoes.length > 5) {
      bloco.append(h('p', { class: 'popup-mais' }, t('mapa.popup_mais', { n: feicoes.length - 5 })));
    }
    caixa.append(bloco);
  }
  return { caixa, total };
}

export function instalarPopup(map, catalogo, maplibregl) {
  let popup = null;
  const fechar = () => { if (popup) { popup.remove(); popup = null; } };
  map.on('click', (ev) => {
    if (map.getCanvas().style.cursor === 'crosshair') return; // medição em curso: o clique é dela
    const camadas = catalogo.ativas.flatMap((id) => catalogo.idsDeEstilo(id))
      .filter((idc) => map.getLayer(idc));
    if (!camadas.length) return;
    const feicoes = map.queryRenderedFeatures(ev.point, { layers: camadas });
    const porCamada = agrupar(feicoes, catalogo);
    fechar();
    if (!porCamada.size) return;
    const { caixa } = montarConteudo(porCamada, catalogo);
    const vazio = h('div');
    limpar(vazio);
    popup = new maplibregl.Popup({ closeButton: true, maxWidth: '360px', className: 'popup-plat' })
      .setLngLat(ev.lngLat)
      .setDOMContent(caixa)
      .addTo(map);
  });
  return { fechar };
}
