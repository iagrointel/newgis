/* plat · mapa — visualizador (item L2-01-mapa-web; o mapa-base local é o L2-01-a).

   Módulo ES sem empacotador; cache resolvido por `no-store` no nginx — NUNCA `?v=` num import, porque
   duas URLs para o mesmo arquivo criam duas instâncias do módulo e a aplicação morre (armadilha já paga
   na casa). MapLibre GL JS e o protocolo PMTiles vêm de <script> clássico (window.maplibregl /
   window.pmtiles, vendorizados em web/vendor/ com sha256 em VERSOES.txt), carregados ANTES deste módulo
   em mapa.html: os dois não são módulos ES.

   O que esta tela junta:
     camadas do catálogo (Martin/PMTiles)     catalogo.js
     árvore de camadas (ordem/grupo/escala) ../camadas.js (item L2-01-c)
     legenda dinâmica do estilo MapLibre     ../legenda.js (item L2-01-c)
     edição de feições                        edicao.js (item L2-03)
     janela de atributos                      atributos.js
     medição geodésica                        medicao.js
     pesquisa de endereço e de coordenada     busca.js
     impressão PNG/PDF com escala e norte     impressao.js
   Navegação, barra de escala e coordenadas do cursor ficam aqui mesmo (são três controles pequenos).

   `body[data-pronto="1"]` só depois do primeiro 'load' do mapa: o e2e espera por isso. */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo, camadasRede } from './estilo.js';
import { carregar as carregarMapa, camadasDoTopo, salvarOrdem, alternarVisivel, salvarDocumento } from './documento.js';
import { montarPainel } from './painel_camadas.js';
import { Catalogo } from './catalogo.js';
import { Arvore } from '../camadas.js';
import { Legenda } from '../legenda.js';
import { instalarPopup, atributosDaFeicao } from './atributos.js';
import { obter } from '../base/api.js';
import { Medicao } from './medicao.js';
import { interpretarCoordenada, sugerir, geocodificar } from './busca.js';
import { paraPng, paraPdf, escalaNumerica } from './impressao.js';
import { Edicao } from './edicao.js';

/* BASE mundial primeiro e PADRÃO (correção 10/09: o mapa não pode abrir num vazio preto fora de Guarulhos —
   ver estilo.js). O recorte vetorial local continua disponível para quem quer o instrumento de alto detalhe. */
const BASES = [
  { id: 'osm-mundial', rotuloChave: 'mapa.base_osm_mundial', tipo: 'raster' },
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', tipo: 'pmtiles', arquivo: 'guarulhos.pmtiles' },
  { id: 'sem-base', rotuloChave: 'mapa.base_nenhuma', tipo: 'nenhuma' },
];
const CENTRO = [-46.593018, -23.493476];
const el = (id) => document.getElementById(id);

function urlDado(arquivo) { return `${location.origin}/static/dados/basemap/${arquivo}`; }

function descritorBase(base) {
  return { tipo: base.tipo, url: base.arquivo ? urlDado(base.arquivo) : undefined };
}

/* une as extensões (graus, [oeste,sul,leste,norte]) das fichas que já trazem uma; ignora as que não trazem
   (a listagem resumida só devolve extensão quando a ingestão a calculou — nunca mede ST_Extent aqui). */
function uniaoDeExtensoes(fichas) {
  let uniao = null;
  for (const f of fichas || []) {
    const e = f && f.extensao;
    if (!Array.isArray(e) || e.length !== 4 || e.some((v) => typeof v !== 'number' || !Number.isFinite(v))) continue;
    uniao = uniao
      ? [Math.min(uniao[0], e[0]), Math.min(uniao[1], e[1]), Math.max(uniao[2], e[2]), Math.max(uniao[3], e[3])]
      : [...e];
  }
  return uniao;
}

function montarSeletorBase(map) {
  const sel = el('seletor-base');
  for (const base of BASES) {
    sel.append(h('option', { value: base.id }, t(base.rotuloChave)));
  }
  sel.value = BASES[0].id;
  return sel;
}

function montarCoordenadas(map) {
  const caixa = el('coordenadas');
  const escrever = (lng, lat, zoom) => {
    caixa.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} · z${zoom.toFixed(1)} · 1:`
      + `${escalaNumerica(lat, zoom).toLocaleString('pt-BR')}`;
  };
  const centro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', centro);
  map.on('zoomend', centro);
  map.on('moveend', centro);
  centro();
}

function marcador(map, maplibregl, lonlat, rotulo) {
  const m = new maplibregl.Marker({ color: '#d98a2b' }).setLngLat(lonlat);
  if (rotulo) m.setPopup(new maplibregl.Popup({ closeButton: true }).setText(rotulo));
  m.addTo(map);
  return m;
}

/* --------------------------------------------------------------------------------------------------------
   Rede de utilidades (10/09): grupo próprio no painel lateral, fora da árvore do catálogo (Arvore/camadas.js
   é do documento de mapa; a rede é outro domínio, `/api/rede`, com sua própria RLS e seu próprio par de
   rotas `.geojson`). Duas fontes GeoJSON por rede ligada (linhas/pontos, `camadasRede` de estilo.js decide a
   cor por disciplina); a seção é criada por JS e inserida no DOM já existente de mapa.html — nenhum HTML
   novo, para não disputar arquivo com quem está convergindo a identidade visual das páginas. */
const PREFIXO_REDE = 'plat-rede-';

async function listarRedes() {
  const r = await obter('/api/rede?limite=200');
  if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao listar redes de utilidades');
  return r.json.itens || [];
}

/* varre coordinates de Point/LineString (a rede de demonstração só tem essas duas geometrias) e devolve
   [oeste,sul,leste,norte]; ST_AsGeoJSON já veio em 4326, mesma unidade do mapa. */
function estenderBbox(bbox, coordenadas) {
  if (!Array.isArray(coordenadas)) return bbox;
  if (typeof coordenadas[0] === 'number') {
    const [x, y] = coordenadas;
    if (!bbox) return [x, y, x, y];
    return [Math.min(bbox[0], x), Math.min(bbox[1], y), Math.max(bbox[2], x), Math.max(bbox[3], y)];
  }
  for (const parte of coordenadas) bbox = estenderBbox(bbox, parte);
  return bbox;
}

function bboxDasColecoes(colecoes) {
  let bbox = null;
  for (const fc of colecoes) {
    for (const feicao of (fc && fc.features) || []) bbox = estenderBbox(bbox, feicao.geometry && feicao.geometry.coordinates);
  }
  return bbox;
}

/* popup das camadas de rede: mesmo padrão visual de atributos.js (reusa `atributosDaFeicao`, que já trata
   campo nulo e formata número em pt-BR), mas com clique/consulta PRÓPRIOS — o de atributos.js só conhece
   camadas do catálogo (fonte `plat-<id>`, ficha em `catalogo.ficha`), a rede não tem ficha de catálogo. */
function instalarPopupRede(map, maplibregl, redesAtivas) {
  let popup = null;
  map.on('click', (ev) => {
    if (map.getCanvas().style.cursor === 'crosshair') return; // medição em curso
    const camadas = [...redesAtivas.values()].flatMap((r) => [r.layerLinhas, r.layerPontos])
      .filter((id) => map.getLayer(id));
    if (!camadas.length) return;
    const feicoes = map.queryRenderedFeatures(ev.point, { layers: camadas });
    if (popup) { popup.remove(); popup = null; }
    if (!feicoes.length) return;
    const caixa = h('div', { class: 'popup-conteudo' });
    for (const feicao of feicoes.slice(0, 5)) {
      const tabela = h('table', { class: 'popup-tabela' });
      const corpo = h('tbody');
      for (const at of atributosDaFeicao(feicao, null)) {
        corpo.append(h('tr', { dataset: { campo: at.nome, nulo: at.nulo ? '1' : '0' } },
          h('th', { scope: 'row' }, at.nome), h('td', { class: at.nulo ? 'nulo' : '' }, at.valor)));
      }
      tabela.append(corpo);
      caixa.append(h('div', { class: 'popup-camada' }, h('h3', {}, feicao.properties.tipo || '—'), tabela));
    }
    if (feicoes.length > 5) caixa.append(h('p', { class: 'popup-mais' }, t('mapa.popup_mais', { n: feicoes.length - 5 })));
    popup = new maplibregl.Popup({ closeButton: true, maxWidth: '360px', className: 'popup-plat' })
      .setLngLat(ev.lngLat).setDOMContent(caixa).addTo(map);
  });
}

function montarSecaoRede() {
  const status = h('p', { class: 'fraco', id: 'rede-utilidades-status' }, t('mapa.rede_utilidades_carregando'));
  const lista = h('ul', { class: 'lista-camadas', id: 'rede-utilidades-lista', role: 'list' });
  const secao = h('section', { class: 'bloco', id: 'rede-utilidades-painel', 'aria-label': t('mapa.rede_utilidades') },
    h('h2', {}, t('mapa.rede_utilidades')), status, lista);
  const painelLateral = document.querySelector('.mapa-painel-lateral');
  const antesDe = el('edicao-painel');
  if (painelLateral) painelLateral.insertBefore(secao, antesDe || null);
  return { status, lista };
}

async function montarRedeUtilidades(map, maplibregl) {
  const { status, lista } = montarSecaoRede();
  const redesAtivas = new Map(); // rede.id -> {fonteLinhas, fontePontos, layerLinhas, layerPontos}
  instalarPopupRede(map, maplibregl, redesAtivas);

  const ligar = async (rede) => {
    const base = `${PREFIXO_REDE}${rede.id}`;
    const fonteLinhas = `${base}-linhas`;
    const fontePontos = `${base}-pontos`;
    const layerLinhas = `${base}-linhas-camada`;
    const layerPontos = `${base}-pontos-camada`;
    const [rLinhas, rPontos] = await Promise.all([
      obter(`/api/rede/${rede.id}/feicoes/linhas.geojson`),
      obter(`/api/rede/${rede.id}/feicoes/pontos.geojson`),
    ]);
    if (rLinhas.status !== 200 || rPontos.status !== 200) {
      const erro = (rLinhas.json && rLinhas.json.mensagem) || (rPontos.json && rPontos.json.mensagem);
      throw new Error(erro || 'falha ao carregar a geometria da rede');
    }
    if (!map.getSource(fonteLinhas)) map.addSource(fonteLinhas, { type: 'geojson', data: rLinhas.json });
    if (!map.getSource(fontePontos)) map.addSource(fontePontos, { type: 'geojson', data: rPontos.json });
    for (const camada of camadasRede(layerLinhas, fonteLinhas, layerPontos, fontePontos)) {
      if (!map.getLayer(camada.id)) map.addLayer(camada);
    }
    redesAtivas.set(rede.id, { fonteLinhas, fontePontos, layerLinhas, layerPontos });
    const bbox = bboxDasColecoes([rLinhas.json, rPontos.json]);
    if (bbox) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { animate: false, padding: 40 });
    return { nLinhas: rLinhas.json.features.length, nPontos: rPontos.json.features.length };
  };

  const desligar = (redeId) => {
    const info = redesAtivas.get(redeId);
    if (!info) return;
    for (const layerId of [info.layerLinhas, info.layerPontos]) if (map.getLayer(layerId)) map.removeLayer(layerId);
    for (const fonteId of [info.fonteLinhas, info.fontePontos]) if (map.getSource(fonteId)) map.removeSource(fonteId);
    redesAtivas.delete(redeId);
  };

  const itemRede = (rede) => {
    const caixa = h('input', { type: 'checkbox', class: 'camada-visivel', 'aria-label': `mostrar ${rede.nome}` });
    const contagem = h('span', { class: 'fraco pequeno' }, '');
    caixa.addEventListener('change', async () => {
      caixa.disabled = true;
      try {
        if (caixa.checked) {
          const { nLinhas, nPontos } = await ligar(rede);
          contagem.textContent = `${nLinhas.toLocaleString('pt-BR')} linhas · ${nPontos.toLocaleString('pt-BR')} pontos`;
        } else {
          desligar(rede.id);
          contagem.textContent = '';
        }
      } catch (e) {
        caixa.checked = false;
        el('aviso').erro(`${t('mapa.rede_utilidades_erro')}: ${(e && e.message) || e}`);
      } finally {
        caixa.disabled = false;
      }
    });
    return h('li', { class: 'camada-linha' },
      h('label', { class: 'camada-rotulo' }, caixa,
        h('span', { class: 'camada-titulo' }, rede.nome),
        h('span', { class: 'camada-tipo' }, rede.disciplina)),
      contagem);
  };

  try {
    const redes = await listarRedes();
    if (!redes.length) { status.textContent = t('mapa.rede_utilidades_vazio'); return; }
    status.remove();
    for (const rede of redes) lista.append(itemRede(rede));
  } catch (e) {
    status.textContent = `${t('mapa.rede_utilidades_erro')}: ${(e && e.message) || e}`;
  }
}

/* Documento de mapa (item L2-01-a-documento-mapa): /mapa?id=<uuid> abre um mapa do catálogo. Sem `id` a tela
   segue sendo só o mapa-base local, como no item que a criou — nada de mapa de exemplo embutido. */
async function iniciarDocumento(map) {
  const id = new URLSearchParams(location.search).get('id');
  if (!id) return;
  const { completo, documento, erro } = await carregarMapa(id);
  if (erro) {
    el('aviso').erro(`${t('mapa.erro_documento')}: ${erro.mensagem}`);
    return;
  }
  let doc = documento;
  let ordem = camadasDoTopo(completo).map((c) => c.id);
  el('mapa-nome').textContent = completo.titulo;
  const painel = el('painel-camadas');
  painel.hidden = false;
  const salvar = el('salvar-mapa');
  salvar.hidden = false;
  if (!completo.camadas.length) {
    el('camadas').textContent = t('mapa.sem_camadas');
  } else {
    montarPainel({
      raiz: el('camadas'),
      camadas: camadasDoTopo(completo),
      aoReordenar: (ids) => { ordem = ids; salvar.dataset.sujo = '1'; },
      aoAlternarVisivel: (idLocal) => { doc = alternarVisivel(doc, idLocal); salvar.dataset.sujo = '1'; },
    });
  }
  salvar.addEventListener('click', async () => {
    salvar.disabled = true;
    const gravado = await (ordem.length ? salvarOrdem(id, doc, ordem) : salvarDocumento(id, doc));
    salvar.disabled = false;
    if (gravado.erro) {
      el('aviso').erro(`${t('mapa.erro_salvar')}: ${gravado.erro.mensagem}`);
      return;
    }
    doc = gravado.documento;
    delete salvar.dataset.sujo;
    el('aviso').ok(t('mapa.salvo'));
  });
  if (completo.extensao_inicial) {
    const [oeste, sul, leste, norte] = completo.extensao_inicial;
    map.fitBounds([[oeste, sul], [leste, norte]], { animate: false, padding: 20 });
  }
}


async function iniciar(usuario) {
  const maplibregl = window.maplibregl;
  if (!maplibregl || !window.pmtiles) { el('aviso').erro(t('mapa.erro_biblioteca')); return; }
  const protocolo = new window.pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocolo.tile);

  const map = new maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(descritorBase(BASES[0])),
    center: CENTRO,
    zoom: 11,
    attributionControl: false,
    hash: false,
    // obrigatório para a impressão ler o canvas depois do quadro composto (impressao.js explica)
    preserveDrawingBuffer: true,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');
  montarCoordenadas(map);

  const catalogo = new Catalogo(map);
  const medicao = new Medicao(map, el('medicao-saida'));
  const arvore = new Arvore(catalogo, map, el('lista-camadas'), {
    aoEnquadrar: async (id) => {
      const ext = await catalogo.extensao(id);
      if (ext) map.fitBounds([[ext[0], ext[1]], [ext[2], ext[3]]], { padding: 40, duration: 0 });
    },
    aoErro: (e) => el('aviso').erro(`${t('mapa.erro_camada')}: ${(e && e.message) || e}`),
    aoMudarEscala: () => legenda.desenhar(),
  });
  const legenda = new Legenda(map, el('legenda'), () => arvore.camadasParaLegenda());
  instalarPopup(map, catalogo, maplibregl);
  // a edição nasce depois do primeiro 'load'; a troca de mapa-base pode acontecer antes disso.
  let edicao = null;

  el('btn-novo-grupo').addEventListener('click', () => {
    const titulo = window.prompt('nome do grupo', 'grupo novo');
    if (titulo !== null) arvore.criarGrupo(titulo);
  });

  // troca de mapa-base: refazer o estilo apaga as camadas do catálogo, que são re-somadas em seguida
  const sel = montarSeletorBase(map);
  sel.addEventListener('change', async () => {
    const base = BASES.find((b) => b.id === sel.value) || BASES[0];
    const ativas = [...catalogo.ativas];
    const opacidades = new Map(catalogo.opacidade);
    map.setStyle(construirEstilo(descritorBase(base)));
    await new Promise((r) => map.once('styledata', r));
    catalogo.ativas = [];
    catalogo.opacidade = opacidades;
    for (const id of [...ativas].reverse()) { try { await catalogo.ligar(id); } catch { /* segue */ } }
    catalogo.reordenar(ativas);
    if (edicao) edicao._instalarFontesECamadas(); // setStyle apagou as fontes/camadas de edição também
  });

  // --- medição
  el('btn-distancia').addEventListener('click', () => {
    medicao.iniciar('distancia');
    el('btn-distancia').setAttribute('aria-pressed', medicao.modo === 'distancia' ? 'true' : 'false');
    el('btn-area').setAttribute('aria-pressed', 'false');
  });
  el('btn-area').addEventListener('click', () => {
    medicao.iniciar('area');
    el('btn-area').setAttribute('aria-pressed', medicao.modo === 'area' ? 'true' : 'false');
    el('btn-distancia').setAttribute('aria-pressed', 'false');
  });
  el('btn-medicao-limpar').addEventListener('click', () => {
    medicao.limpar();
    el('btn-area').setAttribute('aria-pressed', 'false');
    el('btn-distancia').setAttribute('aria-pressed', 'false');
  });

  // --- pesquisa (endereço ou coordenada)
  let alfinete = null;
  const campo = el('busca-campo');
  const lista = el('busca-sugestoes');
  const irPara = (lat, lon, rotulo) => {
    if (alfinete) alfinete.remove();
    alfinete = marcador(map, maplibregl, [lon, lat], rotulo);
    map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), 16), duration: 0 });
    el('busca-resultado').textContent = rotulo;
    limpar(lista);
  };
  const buscar = async () => {
    const texto = campo.value.trim();
    if (!texto) return;
    const coord = interpretarCoordenada(texto);
    if (coord) { irPara(coord.lat, coord.lon, `${coord.lat.toFixed(5)}, ${coord.lon.toFixed(5)}`); return; }
    const r = await geocodificar(texto);
    if (r) irPara(r.lat, r.lon, r.rotulo);
    else el('busca-resultado').textContent = t('mapa.busca_sem_resultado');
  };
  el('busca-form').addEventListener('submit', (ev) => { ev.preventDefault(); buscar(); });
  let pendente = null;
  campo.addEventListener('input', () => {
    clearTimeout(pendente);
    const texto = campo.value.trim();
    if (interpretarCoordenada(texto)) { limpar(lista); return; }
    pendente = setTimeout(async () => {
      const sugestoes = await sugerir(texto);
      limpar(lista);
      for (const s of sugestoes) {
        lista.append(h('li', {}, h('button', {
          type: 'button', class: 'sugestao',
          onclick: () => { campo.value = s.texto; buscar(); },
        }, s.texto)));
      }
    }, 250);
  });

  // --- impressão
  const titulo = () => `${t('mapa.titulo')} — ${new Date().toLocaleDateString('pt-BR')}`;
  const atribuicao = '© colaboradores do OpenStreetMap — ODbL 1.0';
  el('btn-png').addEventListener('click', async () => {
    const r = await paraPng(map, { titulo: titulo(), atribuicao, nome: 'mapa.png' });
    el('impressao-saida').textContent = t('mapa.impressao_pronta', { formato: 'PNG', kb: Math.round(r.bytes / 1024) });
  });
  el('btn-pdf').addEventListener('click', async () => {
    const r = await paraPdf(map, { titulo: titulo(), atribuicao, nome: 'mapa.pdf' });
    el('impressao-saida').textContent = t('mapa.impressao_pronta', { formato: 'PDF', kb: Math.round(r.bytes / 1024) });
  });

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  const temDocumento = !!new URLSearchParams(location.search).get('id');
  await iniciarDocumento(map);
  edicao = new Edicao(map, maplibregl, catalogo, {
    raiz: el('edicao-painel'),
    aoErro: (msg) => el('aviso').erro(msg),
  });
  try {
    await arvore.carregar();
    // Sem documento de mapa (`?id=`), o catálogo não pode abrir vazio (pedido do dono 10/09: "tem de
    // haver dado visível") — liga as camadas mais recentes do inquilino; documento salvo no navegador ou
    // escolha explícita do usuário (`ativarPadrao` só age se nada estiver ligado) nunca é sobrescrita.
    if (!temDocumento) await arvore.ativarPadrao(8);
    legenda.desenhar();
    // Sem documento de mapa (`?id=`), a vista inicial enquadra as camadas do inquilino em vez de abrir
    // sempre no recorte de Guarulhos (medido 10/09: camada fora de Guarulhos ficava "sobre o nada"). A
    // extensão vem da listagem (`/api/mapa/camadas`, ficha resumida — só quando a ingestão já a gravou;
    // camada sem extensão é ignorada, nunca medida aqui); sem nenhuma extensão disponível, mantém a vista
    // padrão do recorte (CENTRO/z11), como antes. Prioriza as camadas VISÍVEIS (ligadas); sem nenhuma
    // ativa ainda, cai para a união de todas as disponíveis — não deixa a vista sem enquadramento nenhum.
    if (!temDocumento) {
      const visiveis = catalogo.disponiveis.filter((f) => catalogo.ativas.includes(f.id));
      const uniao = uniaoDeExtensoes(visiveis.length ? visiveis : catalogo.disponiveis);
      if (uniao) map.fitBounds([[uniao[0], uniao[1]], [uniao[2], uniao[3]]], { animate: false, padding: 40 });
    }
  } catch (e) {
    el('aviso').erro(`${t('mapa.erro_camada')}: ${(e && e.message) || e}`);
  }
  // rede de utilidades: domínio próprio (`/api/rede`), fora da árvore do catálogo — uma falha aqui não pode
  // derrubar o resto do mapa, por isso o try/catch é dela sozinha.
  try {
    await montarRedeUtilidades(map, maplibregl);
  } catch (e) {
    el('aviso').erro(`${t('mapa.rede_utilidades_erro')}: ${(e && e.message) || e}`);
  }
  window.plat = window.plat || {};
  window.plat.mapa = { map, catalogo, medicao, arvore, legenda, edicao };  // ponto de inspeção do e2e, nunca de negócio
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  try {
    await iniciar(usuario);
  } catch (e) {
    el("aviso").erro(`${t("erro.carregar")}: ${(e && e.message) || e}`);
    pronto();
  }
}
