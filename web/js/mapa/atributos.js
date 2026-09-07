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
import { copiarFeicao } from './exportar.js';

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

export function montarConteudo(porCamada, catalogo) {
  const caixa = h('div', { class: 'popup-conteudo' });
  let total = 0;
  for (const [camadaId, feicoes] of porCamada) {
    const ficha = catalogo.ficha(camadaId);
    total += feicoes.length;
    const bloco = h('div', { class: 'popup-camada', dataset: { camada: camadaId } },
      h('h3', {}, ficha.titulo));
    for (const feicao of feicoes.slice(0, 5)) {
      const fid = feicao.id ?? (feicao.properties && feicao.properties.fid);
      const tabela = h('table', { class: 'popup-tabela' });
      const corpo = h('tbody');
      for (const at of atributosDaFeicao(feicao, ficha.campos)) {
        corpo.append(h('tr', { dataset: { campo: at.nome, nulo: at.nulo ? '1' : '0' } },
          h('th', { scope: 'row' }, at.nome),
          h('td', { class: at.nulo ? 'nulo' : '' }, at.valor)));
      }
      tabela.append(corpo);
      bloco.append(tabela);
      if (fid !== undefined && fid !== null) {
        // copiar a feição INTEIRA: o que está no tile vem recortado na borda do tile e generalizado
        // pelo zoom, então o texto copiado é lido da tabela (GET .../feicoes/{fid}), não daqui
        const aviso = h('span', { class: 'popup-copiado', 'aria-live': 'polite' });
        const copiar = async (formato) => {
          try {
            const n = await copiarFeicao(camadaId, fid, formato);
            aviso.textContent = t('mapa.copiado', { n });
          } catch {
            aviso.textContent = t('mapa.copiar_falhou');
          }
        };
        bloco.append(h('div', { class: 'popup-acoes' },
          h('button', { type: 'button', class: 'botao secundario', dataset: { copiar: 'geojson', fid },
            onclick: () => copiar('geojson') }, t('mapa.copiar_geojson')),
          h('button', { type: 'button', class: 'botao secundario', dataset: { copiar: 'wkt', fid },
            onclick: () => copiar('wkt') }, t('mapa.copiar_wkt')),
          aviso));
      }
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
