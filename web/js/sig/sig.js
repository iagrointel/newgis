/* plat · SIG — casca de tela cheia (item L2-01-a-casca-sig, 10/09/2026; ordem do dono "casca 10× melhor
   que a deles", especificação em plataforma/laco/handoffs/T8/ESPEC_CASCA_SIG.md).

   Este módulo é a ORQUESTRAÇÃO nova: nenhum módulo de web/js/mapa/*.js ou web/js/camadas.js foi reescrito
   — Catalogo, Arvore, Legenda, Medicao, Edicao, atributos, busca, impressão e documento de mapa são os
   MESMOS motores que `/mapa` usa (web/js/mapa/mapa.js, que este arquivo não importa nem edita: /mapa
   continua no ar até a casca nova ser aprovada). O que muda é só a CASCA: painéis flutuantes arrastáveis
   em vez de coluna fixa, barra de instrumento de 56 px, tema claro/escuro com padrão escuro, base OSM
   mundial + ortofoto GeoSampa via proxy público, arrastar-para-publicar e composição salva.

   `body[data-pronto="1"]` só depois do primeiro 'load' do mapa — mesmo contrato de /mapa, para o e2e. */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { pronto } from '../base/layout.js';
import { h, limpar, menuContexto } from '../base/dom.js';
import { exigirSessao } from '../auth/sessao.js';
import { obter, enviar, alterar } from '../base/api.js';
import { construirEstilo, camadasRede, ATRIBUICAO_OSM } from '../mapa/estilo.js';
import { carregar as carregarMapaDoc, camadasDoTopo, salvarOrdem, alternarVisivel, salvarDocumento } from '../mapa/documento.js';
import { Catalogo } from '../mapa/catalogo.js';
import { Arvore } from '../camadas.js';
import { Legenda } from '../legenda.js';
import { instalarPopup, montarTabelaPopup } from '../mapa/atributos.js';
import { montarGaveta, fonteDeCamada, fonteDeRede } from '../mapa/tabela_atributos.js';
import { Medicao } from '../mapa/medicao.js';
import { interpretarCoordenada, sugerir, geocodificar } from '../mapa/busca.js';
import { paraPng, paraPdf, escalaNumerica } from '../mapa/impressao.js';
import { PainelExportar } from '../mapa/exportar.js';
import { Edicao } from '../mapa/edicao.js';
import { instalarComparar } from './comparar.js';
import { enviarArquivo, publicar, obterTipos, extensaoDe, TIPOS_RASTER } from '../uploads/nucleo.js';
import { icone, pintarIcones } from '../base/icones.js';

const el = (id) => document.getElementById(id);
const CENTRO = [-46.593018, -23.493476];
const CHAVE_TEMA = 'plat.sig.tema';

/* ------------------------------------------------------------------------------------------- tema claro/
   escuro (princípio 3): escuro é o PADRÃO — se nada foi escolhido ainda, grava 'dark' no localStorage em
   vez de deixar o navegador decidir pela preferência de sistema (que é o comportamento padrão de
   tokens.css sem `data-theme`). Depois disso o toggle só troca o valor gravado. */
function temaInicial() {
  try {
    const salvo = window.localStorage.getItem(CHAVE_TEMA);
    if (salvo === 'dark' || salvo === 'light') return salvo;
  } catch { /* localStorage indisponível: segue com o padrão escuro sem persistir */ }
  return 'dark';
}

function aplicarTema(tema) {
  document.documentElement.setAttribute('data-theme', tema);
  try { window.localStorage.setItem(CHAVE_TEMA, tema); } catch { /* melhor esforço */ }
}

function instalarTema() {
  aplicarTema(temaInicial());
  el('alternar-tema').addEventListener('click', () => {
    const atual = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    aplicarTema(atual === 'dark' ? 'light' : 'dark');
  });
}

/* ------------------------------------------------------------------------------------------------ bases
   (princípio 7): OSM mundial (padrão) · recorte vetorial de Guarulhos · ortofoto GeoSampa via
   /api/publico/wms/geosampa (proxy sem sessão, app/mapa/proxy_wms.py) · sem base. `construirEstilo` de
   estilo.js já cobre os três primeiros tipos ('raster'/'pmtiles'/'nenhuma'); o WMS é um caso que ele não
   conhece (a base local não tem esse conceito), então o estilo MapLibre da ortofoto é montado aqui —
   sem tocar estilo.js. */
const BASES = [
  { id: 'osm-mundial', rotulo: 'OSM mundial', tipo: 'raster', atribuicao: ATRIBUICAO_OSM },
  { id: 'osm-guarulhos', rotulo: 'Guarulhos — recorte local', tipo: 'pmtiles', arquivo: 'guarulhos.pmtiles', atribuicao: ATRIBUICAO_OSM },
  { id: 'geosampa-ortofoto', rotulo: 'Ortofoto GeoSampa 10–20 cm', tipo: 'wms', atribuicao: '© Prefeitura de São Paulo — GeoSampa' },
  { id: 'sem-base', rotulo: 'sem base', tipo: 'nenhuma', atribuicao: '' },
];

const TILE_GEOSAMPA_ORTOFOTO = `${location.origin}/api/publico/wms/geosampa?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap`
  + '&LAYERS=MOSAICO_ORTO_RGB_10CM_20CM&STYLES=&CRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256'
  + '&FORMAT=image/png&TRANSPARENT=true';

function estiloWmsGeosampa(atribuicao) {
  return {
    version: 8,
    name: 'plat-sig-geosampa-ortofoto',
    sources: { base: { type: 'raster', tiles: [TILE_GEOSAMPA_ORTOFOTO], tileSize: 256, maxzoom: 20, attribution: atribuicao } },
    layers: [
      { id: 'fundo', type: 'background', paint: { 'background-color': '#0b0f10' } },
      { id: 'base-raster', type: 'raster', source: 'base' },
    ],
  };
}

function estiloDaBase(base) {
  if (base.tipo === 'wms') return estiloWmsGeosampa(base.atribuicao);
  if (base.tipo === 'pmtiles') return construirEstilo({ tipo: 'pmtiles', url: `${location.origin}/static/dados/basemap/${base.arquivo}` });
  if (base.tipo === 'raster') return construirEstilo({ tipo: 'raster' });
  return construirEstilo({ tipo: 'nenhuma' });
}

function montarListaBases(map, aoTrocar) {
  const lista = el('lista-bases');
  limpar(lista);
  let atual = BASES[0].id;
  for (const base of BASES) {
    const rb = h('input', {
      type: 'radio', name: 'base-mapa', value: base.id, checked: base.id === atual,
      onchange: async () => { atual = base.id; await aoTrocar(base); },
    });
    lista.append(h('li', {}, h('label', {}, rb, base.rotulo)));
  }
  return { atual: () => BASES.find((b) => b.id === atual) };
}

/* --------------------------------------------------------------------------------------- barra inferior */
function montarBarraInferior(map) {
  const coord = el('coordenadas');
  const escala = el('escala');
  const escrever = (lng, lat, zoom) => {
    coord.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    escala.textContent = `z${zoom.toFixed(1)} · 1:${escalaNumerica(lat, zoom).toLocaleString('pt-BR')}`;
  };
  const centro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', centro);
  map.on('zoomend', centro);
  map.on('moveend', centro);
  centro();
}

function definirAtribuicao(texto) { el('atribuicao').textContent = texto || ''; }

/* ---------------------------------------------------------------------------------- painéis flutuantes
   (princípio 1/2/10): a barra de instrumento abre/fecha um painel por ícone; o cabeçalho arrasta; Esc
   fecha o painel com foco. "Recolhível a um trilho": o próprio ícone da barra É o trilho — fechar o
   painel não perde estado (a árvore/medição/edição continuam vivas por baixo, só escondidas). */
let zTopo = 30;
let cascata = 0;

function instalarArrastoPainel(painel) {
  const cabecalho = painel.querySelector('.sig-painel-cabecalho');
  const area = el('mapa-area');
  let arrastando = false;
  let dx = 0;
  let dy = 0;
  cabecalho.addEventListener('pointerdown', (ev) => {
    if (ev.target.closest('[data-fechar]')) return;
    arrastando = true;
    zTopo += 1;
    painel.style.zIndex = String(zTopo);
    const r = painel.getBoundingClientRect();
    dx = ev.clientX - r.left;
    dy = ev.clientY - r.top;
    try { cabecalho.setPointerCapture(ev.pointerId); } catch { /* jsdom/teste sem PointerEvent completo */ }
    painel.classList.add('arrastando');
  });
  cabecalho.addEventListener('pointermove', (ev) => {
    if (!arrastando) return;
    const areaR = area.getBoundingClientRect();
    const left = Math.max(4, Math.min(ev.clientX - dx - areaR.left, areaR.width - 60));
    const top = Math.max(4, Math.min(ev.clientY - dy - areaR.top, areaR.height - 40));
    painel.style.left = `${left}px`;
    painel.style.top = `${top}px`;
  });
  const soltar = (ev) => {
    arrastando = false;
    painel.classList.remove('arrastando');
    try { cabecalho.releasePointerCapture(ev.pointerId); } catch { /* nada a liberar */ }
  };
  cabecalho.addEventListener('pointerup', soltar);
  cabecalho.addEventListener('pointercancel', soltar);
}

/* estado aberto/fechado de cada painel, lembrado por painel (pedido do orientador 10/09: hoje o Camadas
   abria fechado e "o mapa parece sem controle" — o padrão de fábrica é o Camadas ABERTO; qualquer outra
   escolha do usuário, uma vez feita, vence o padrão da próxima vez que a tela abrir). */
function chaveEstadoPainel(id) { return `plat.sig.painel.${id}.aberto`; }
function estadoLembradoDoPainel(id) {
  try { return window.localStorage.getItem(chaveEstadoPainel(id)); } catch { return null; }
}
function lembrarEstadoDoPainel(id, aberto) {
  try { window.localStorage.setItem(chaveEstadoPainel(id), aberto ? '1' : '0'); } catch { /* melhor esforço */ }
}

function instalarPaineis() {
  const paineis = [...document.querySelectorAll('.sig-painel')];
  for (const painel of paineis) instalarArrastoPainel(painel);

  const icone = (id) => document.querySelector(`.sig-icone[data-painel="${id}"]`);

  const posicionar = (painel, id) => {
    if (painel.dataset.posicionado) return;
    if (id === 'camadas') {
      // "encostado à direita, como na referência" (pedido do orientador): o único painel com posição de
      // fábrica fixa; os demais continuam em cascata a partir do canto esquerdo do mapa.
      painel.style.right = 'var(--e4)';
      painel.style.left = 'auto';
      painel.style.top = 'calc(var(--e4) + 3.4rem)';
    } else {
      const desloc = (cascata % 6) * 26;
      painel.style.left = `${68 + desloc}px`;
      painel.style.top = `${16 + desloc}px`;
      cascata += 1;
    }
    painel.dataset.posicionado = '1';
  };

  const abrir = (id) => {
    const painel = el(`painel-${id}`);
    if (!painel) return;
    posicionar(painel, id);
    painel.hidden = false;
    zTopo += 1;
    painel.style.zIndex = String(zTopo);
    icone(id)?.setAttribute('aria-pressed', 'true');
    lembrarEstadoDoPainel(id, true);
    const foco = painel.querySelector('input, button, [tabindex]');
    if (foco) foco.focus({ preventScroll: true });
  };
  const fechar = (id) => {
    const painel = el(`painel-${id}`);
    if (painel) painel.hidden = true;
    icone(id)?.setAttribute('aria-pressed', 'false');
    lembrarEstadoDoPainel(id, false);
  };
  const alternar = (id) => {
    const painel = el(`painel-${id}`);
    if (!painel) return;
    if (painel.hidden) abrir(id); else fechar(id);
  };

  document.querySelectorAll('.sig-icone[data-painel]').forEach((btn) => {
    btn.addEventListener('click', () => alternar(btn.dataset.painel));
  });
  document.querySelectorAll('.sig-painel [data-fechar]').forEach((btn) => {
    btn.addEventListener('click', () => fechar(btn.closest('.sig-painel').dataset.painelId));
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    const aberto = paineis.find((p) => !p.hidden && p.contains(document.activeElement));
    if (aberto) fechar(aberto.dataset.painelId);
  });

  // estado de fábrica: só o painel Camadas abre sozinho; os outros respeitam o que o localStorage lembrar
  // (sem chave gravada ainda = fechado, exceto Camadas). `abrir()` já grava a chave, então isto não duplica
  // gravação — só decide o estado inicial da visita.
  for (const painel of paineis) {
    const id = painel.dataset.painelId;
    const lembrado = estadoLembradoDoPainel(id);
    const deveAbrir = lembrado === '1' || (lembrado === null && id === 'camadas');
    if (deveAbrir) abrir(id);
  }

  // grupos recolhíveis dentro do painel Camadas (princípio 6)
  document.querySelectorAll('.sig-grupo-cabecalho').forEach((btn) => {
    btn.addEventListener('click', () => {
      const grupo = btn.closest('.sig-grupo');
      const fechado = grupo.hasAttribute('data-fechado');
      if (fechado) grupo.removeAttribute('data-fechado'); else grupo.setAttribute('data-fechado', '');
      btn.setAttribute('aria-expanded', fechado ? 'true' : 'false');
    });
  });

  // atalhos de teclado (princípio 10): L camadas, F pesquisa, M medir, E editar — só fora de campo de texto
  document.addEventListener('keydown', (ev) => {
    const alvo = ev.target;
    const digitando = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'TEXTAREA' || alvo.isContentEditable);
    if (digitando || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const tecla = ev.key.toLowerCase();
    const mapa = { l: 'camadas', f: 'pesquisa', m: 'medicao', e: 'edicao', c: 'comparar', x: 'exportar' };
    if (mapa[tecla]) { ev.preventDefault(); alternar(mapa[tecla]); }
  });

  return { abrir, fechar, alternar };
}

/* -------------------------------------------------------------------------------------- painel de busca
   e2e: `/api/sugerir`/`/api/geocodificar` já existem (item L2-11-b) — busca.js só interpreta o texto. */
function instalarBusca(map, maplibregl, paineis) {
  let alfinete = null;
  const campo = el('busca-campo');
  const lista = el('busca-sugestoes');
  const irPara = (lat, lon, rotulo) => {
    if (alfinete) alfinete.remove();
    alfinete = new maplibregl.Marker({ color: '#d98a2b' }).setLngLat([lon, lat]);
    if (rotulo) alfinete.setPopup(new maplibregl.Popup({ closeButton: true }).setText(rotulo));
    alfinete.addTo(map);
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
    else el('busca-resultado').textContent = 'sem resultado';
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
}

function instalarMedicao(medicao) {
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
}

function instalarImpressao(map) {
  const titulo = () => `SIG — ${new Date().toLocaleDateString('pt-BR')}`;
  el('btn-png').addEventListener('click', async () => {
    const r = await paraPng(map, { titulo: titulo(), atribuicao: el('atribuicao').textContent, nome: 'mapa.png' });
    el('impressao-saida').textContent = `PNG pronto · ${Math.round(r.bytes / 1024)} KB`;
  });
  el('btn-pdf').addEventListener('click', async () => {
    const r = await paraPdf(map, { titulo: titulo(), atribuicao: el('atribuicao').textContent, nome: 'mapa.pdf' });
    el('impressao-saida').textContent = `PDF pronto · ${Math.round(r.bytes / 1024)} KB`;
  });
}

function instalarFiltroCamadas() {
  const campo = el('camadas-busca');
  campo.addEventListener('input', () => {
    const termo = campo.value.trim().toLowerCase();
    const raiz = el('lista-camadas');
    raiz.querySelectorAll('li[data-tipo]').forEach((li) => {
      const titulo = (li.querySelector('.arvore-titulo')?.textContent || '').toLowerCase();
      li.classList.toggle('filtrada', !!termo && !titulo.includes(termo));
    });
  });
}

/* link de serviço "honesto por tipo" (mesma regra usada ao publicar por arrasto, mais abaixo): camada
   vetorial tem WFS de verdade (app/consulta/rotas_wfs.py); imagem publicada não tem WFS nem WMTS por essa
   rota de sessão — copia o template XYZ que o próprio mapa já usa para desenhá-la. */
function linkDeServico(catalogo, id) {
  const ficha = catalogo.ficha(id) || {};
  if (ficha.tipo === 'raster') return { url: `${location.origin}/api/imagens/${id}/tiles/{z}/{x}/{y}.png`, rotulo: 'de tiles (XYZ)' };
  return { url: `${location.origin}/wfs/${id}`, rotulo: 'WFS' };
}

/* ícone "compartilhar" direto em cada linha de camada ativa (pedido do orientador 10/09), além do menu de reticências
   que já existe. web/js/camadas.js não é editado nesta casca (é um dos quatro arquivos reservados para a
   outra frente) — o botão é injetado por fora, via MutationObserver no container que a Árvore desenha,
   sem duplicar o desenho dela nem guardar estado próprio (o observer roda de novo a cada redesenho e só
   acrescenta o botão que ainda não existe naquela linha). Só aparece em camada ATIVA: é onde a Árvore já
   desenha a fileira de botões (`.arvore-controles`) — camada desligada não tem link de serviço para copiar
   enquanto não for ligada. */
function instalarCompartilharCamadas(catalogo) {
  const raiz = el('lista-camadas');
  const injetar = () => {
    raiz.querySelectorAll('li[data-tipo="camada"]').forEach((li) => {
      const controles = li.querySelector('.arvore-controles');
      const id = li.dataset.camada;
      if (!controles || !id || controles.querySelector('[data-acao="compartilhar-link"]')) return;
      controles.appendChild(h('button', {
        type: 'button', class: 'botao-mini', dataset: { acao: 'compartilhar-link' },
        title: 'compartilhar link de serviço', 'aria-label': 'compartilhar link de serviço',
        onclick: (ev) => {
          ev.stopPropagation();
          const { url, rotulo } = linkDeServico(catalogo, id);
          navigator.clipboard?.writeText(url).catch(() => {});
          el('aviso').ok(`link ${rotulo} copiado`);
        },
      }, icone('copiar', { tamanho: 14 })));
    });
  };
  new MutationObserver(injetar).observe(raiz, { childList: true, subtree: true });
  injetar();
}

/* --------------------------------------------------------------------------------- rede de utilidades
   (grupo próprio dentro do painel Camadas — `/api/rede`, fora do documento de mapa/catálogo; mesma lógica
   de dados que /mapa usa, adaptada aos ids do painel flutuante do SIG). */
const PREFIXO_REDE = 'plat-rede-';

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
  for (const fc of colecoes) for (const feicao of (fc && fc.features) || []) bbox = estenderBbox(bbox, feicao.geometry && feicao.geometry.coordinates);
  return bbox;
}

/* une várias extensões (graus, [oeste,sul,leste,norte]) numa só — usado no enquadramento inicial da tela
   (catálogo + rede de utilidades juntos, princípio 4); ignora qualquer valor que não seja um par de
   coordenadas válido, nunca lança. */
function uniaoDeExtensoes(extensoes) {
  let uniao = null;
  for (const e of extensoes || []) {
    if (!Array.isArray(e) || e.length !== 4 || e.some((v) => typeof v !== 'number' || !Number.isFinite(v))) continue;
    uniao = uniao
      ? [Math.min(uniao[0], e[0]), Math.min(uniao[1], e[1]), Math.max(uniao[2], e[2]), Math.max(uniao[3], e[3])]
      : [...e];
  }
  return uniao;
}

function instalarPopupRede(map, maplibregl, redesAtivas) {
  let popup = null;
  map.on('click', (ev) => {
    if (map.getCanvas().style.cursor === 'crosshair') return;
    const camadas = [...redesAtivas.values()].flatMap((r) => [r.layerLinhas, r.layerPontos]).filter((id) => map.getLayer(id));
    if (!camadas.length) return;
    const feicoes = map.queryRenderedFeatures(ev.point, { layers: camadas });
    if (popup) { popup.remove(); popup = null; }
    if (!feicoes.length) return;
    const caixa = h('div', { class: 'popup-conteudo' });
    for (const feicao of feicoes.slice(0, 5)) {
      const campos = Object.keys(feicao.properties || {}).filter((nome) => nome !== 'id').map((nome) => ({ nome }));
      const tabela = montarTabelaPopup(feicao, campos);
      caixa.append(h('div', { class: 'popup-camada' }, h('h3', {}, feicao.properties.tipo || '—'), tabela));
    }
    popup = new maplibregl.Popup({ closeButton: true, maxWidth: '360px', className: 'popup-plat' }).setLngLat(ev.lngLat).setDOMContent(caixa).addTo(map);
  });
}

async function instalarRede(map, maplibregl, { ativarTudo = false, gavetaTabela } = {}) {
  const status = el('rede-status');
  const lista = el('rede-lista');
  const redesAtivas = new Map(); // rede.id -> {..., bbox}: o bbox fica guardado para o enquadramento
  // inicial da tela (união com as camadas do catálogo — ver `uniaoDeExtensoes` em `iniciar()`), não só
  // para o fitBounds imediato que `ligar` já fazia.
  instalarPopupRede(map, maplibregl, redesAtivas);

  const ligar = async (rede, { enquadrar = true } = {}) => {
    const base = `${PREFIXO_REDE}${rede.id}`;
    const fonteLinhas = `${base}-linhas`;
    const fontePontos = `${base}-pontos`;
    const layerLinhas = `${base}-linhas-camada`;
    const layerPontos = `${base}-pontos-camada`;
    const [rLinhas, rPontos] = await Promise.all([
      obter(`/api/rede/${rede.id}/feicoes/linhas.geojson`),
      obter(`/api/rede/${rede.id}/feicoes/pontos.geojson`),
    ]);
    if (rLinhas.status !== 200 || rPontos.status !== 200) throw new Error('falha ao carregar a geometria da rede');
    if (!map.getSource(fonteLinhas)) map.addSource(fonteLinhas, { type: 'geojson', data: rLinhas.json });
    if (!map.getSource(fontePontos)) map.addSource(fontePontos, { type: 'geojson', data: rPontos.json });
    for (const camada of camadasRede(layerLinhas, fonteLinhas, layerPontos, fontePontos)) {
      if (!map.getLayer(camada.id)) map.addLayer(camada);
    }
    const bbox = bboxDasColecoes([rLinhas.json, rPontos.json]);
    redesAtivas.set(rede.id, { fonteLinhas, fontePontos, layerLinhas, layerPontos, bbox });
    if (bbox && enquadrar) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { animate: false, padding: 40 });
    return { nLinhas: rLinhas.json.features.length, nPontos: rPontos.json.features.length };
  };
  const desligar = (redeId) => {
    const info = redesAtivas.get(redeId);
    if (!info) return;
    if (gavetaTabela.fonteAtual()?.chave.startsWith(`rede:${redeId}:`)) gavetaTabela.fechar();
    for (const layerId of [info.layerLinhas, info.layerPontos]) if (map.getLayer(layerId)) map.removeLayer(layerId);
    for (const fonteId of [info.fonteLinhas, info.fontePontos]) if (map.getSource(fonteId)) map.removeSource(fonteId);
    redesAtivas.delete(redeId);
  };

  const itemRede = (rede) => {
    const caixa = h('input', { type: 'checkbox', class: 'camada-visivel', 'aria-label': `mostrar ${rede.nome}` });
    const contagem = h('span', { class: 'arvore-conta' }, '');
    const aoAlternar = async ({ enquadrar = true } = {}) => {
      caixa.disabled = true;
      try {
        if (caixa.checked) {
          const { nLinhas, nPontos } = await ligar(rede, { enquadrar });
          contagem.textContent = `${nLinhas.toLocaleString('pt-BR')} linhas · ${nPontos.toLocaleString('pt-BR')} pontos`;
        } else { desligar(rede.id); contagem.textContent = ''; }
      } catch (e) {
        caixa.checked = false;
        el('aviso').erro(`rede de utilidades: ${(e && e.message) || e}`);
      } finally { caixa.disabled = false; }
    };
    caixa.addEventListener('change', () => aoAlternar());
    const li = h('li', { class: 'camada-linha' },
      h('div', { class: 'camada-cabecalho' }, caixa,
        h('span', { class: 'camada-titulo' }, rede.nome),
        h('span', { class: 'camada-tipo' }, rede.disciplina)),
      contagem);
    const abrirMenu = (x, y) => menuContexto([{ rotulo: t('mapa.camadas_mostrar_tabela'),
      aoClicar: () => gavetaTabela.abrir(fonteDeRede(map, {
        id: rede.id, nome: rede.nome, ...(redesAtivas.get(rede.id) || {}),
      }, 'pontos')),
    }], x, y);
    li.addEventListener('contextmenu', (ev) => {
      ev.preventDefault(); ev.stopPropagation(); abrirMenu(ev.clientX, ev.clientY);
    });
    li.querySelector('.camada-cabecalho').append(h('button', { type: 'button', class: 'botao-mini',
      'aria-label': t('mapa.camadas_menu'), 'aria-haspopup': 'menu', onclick: (ev) => {
        const r = ev.currentTarget.getBoundingClientRect(); abrirMenu(r.left, r.bottom);
      } }, icone('reticencias', { tamanho: 14 })));
    return { li, caixa, aoAlternar };
  };

  try {
    const r = await obter('/api/rede?limite=200');
    if (r.status !== 200) throw new Error((r.json && r.json.mensagem) || 'falha ao listar redes de utilidades');
    const redes = r.json.itens || [];
    if (!redes.length) { status.textContent = 'nenhuma rede de utilidades neste inquilino'; return { redesAtivas, ligar, desligar }; }
    status.remove();
    const itens = redes.map(itemRede);
    for (const it of itens) lista.append(it.li);
    // "dado visível ao abrir" (princípio 4) vale para a rede também: sem documento salvo, liga tudo — o
    // enquadramento de CADA uma é pulado aqui (`enquadrar:false`) porque o enquadramento de verdade é a
    // UNIÃO com as camadas do catálogo, feita uma vez só depois (`uniaoDeExtensoes` em `iniciar()`).
    if (ativarTudo) {
      for (const it of itens) {
        it.caixa.checked = true;
        await it.aoAlternar({ enquadrar: false });
      }
    }
  } catch (e) {
    status.textContent = `rede de utilidades: ${(e && e.message) || e}`;
  }
  return { redesAtivas, ligar, desligar };
}

/* ------------------------------------------------------------------------------------- arrastar-publica
   (princípio 5): arrastar um arquivo sobre o MAPA (não um formulário) publica pelo MESMO protocolo de
   web/js/uploads/nucleo.js — nenhuma reimplementação de parte/token/confirmação aqui, só a decisão de
   QUAL tipo declarar (mesma regra de web/js/uploads/enviar.js: casar a extensão do arquivo com
   `/api/uploads/tipos`) e o que fazer com o item publicado (ligar no mapa e enquadrar). */
function temArquivo(ev) { return ev.dataTransfer && [...ev.dataTransfer.types].includes('Files'); }

async function publicarArquivoNoMapa(arquivo, { map, catalogo, paineis }) {
  paineis.abrir('envio');
  const status = el('envio-status');
  const linksBox = el('envio-links');
  linksBox.hidden = true;
  status.textContent = `enviando ${arquivo.name}…`;
  try {
    const tipos = await obterTipos();
    const ext = extensaoDe(arquivo.name);
    const achado = tipos.find((tp) => tp.extensoes.includes(ext));
    if (!achado) throw new Error(`tipo de arquivo não reconhecido (${ext || 'sem extensão'})`);
    const concluido = await enviarArquivo(arquivo, achado.tipo, {
      aoIniciar: () => {},
      aoProgredir: (feitas, total) => { status.textContent = `enviando ${arquivo.name} · parte ${feitas}/${total}`; },
    });
    const { itemId, publicado } = await publicar(concluido.arquivo_id, achado.tipo, arquivo.name, {
      aoStatus: (msg) => { status.textContent = msg; },
      aoProgredir: () => {},
    });
    if (!publicado) {
      status.textContent = `${arquivo.name} enviado, mas este formato ainda não publica automaticamente — item em /conteudo/${itemId}`;
      return;
    }
    status.textContent = `publicada — ${arquivo.name}`;
    // recarregar o catálogo já sincroniza a árvore sozinha (catalogo.aoMudar, ligado no construtor de
    // Arvore); só falta ligar a camada nova, que nasce desligada como qualquer outra do catálogo.
    await catalogo.carregar();
    if (!catalogo.ativas.includes(itemId)) await catalogo.ligar(itemId);
    const ext2 = await catalogo.extensao(itemId);
    if (ext2 && map) map.fitBounds([[ext2[0], ext2[1]], [ext2[2], ext2[3]]], { padding: 40, animate: false });
    linksBox.hidden = false;
    // WFS (app/consulta/rotas_wfs.py, prefixo /wfs/{item_id}) só existe para camada VETORIAL; imagem
    // publicada não tem WFS — em vez de fingir um link OGC que este produto ainda não serve para raster
    // (WMTS de verdade exige token de serviço, item L1-02, e não é a mesma rota de sessão do catálogo),
    // o botão de raster copia o template XYZ que o próprio mapa já usa para desenhá-la.
    const ehRaster = TIPOS_RASTER.has(achado.tipo);
    el('envio-copiar-wfs').hidden = ehRaster;
    el('envio-copiar-wmts').hidden = !ehRaster;
    el('envio-copiar-wmts').textContent = 'copiar link de tiles (XYZ)';
    if (!ehRaster) {
      const wfs = `${location.origin}/wfs/${itemId}`;
      el('envio-copiar-wfs').onclick = () => navigator.clipboard?.writeText(wfs).catch(() => {});
    } else {
      const tiles = `${location.origin}/api/imagens/${itemId}/tiles/{z}/{x}/{y}.png`;
      el('envio-copiar-wmts').onclick = () => navigator.clipboard?.writeText(tiles).catch(() => {});
    }
  } catch (e) {
    status.textContent = `falha ao publicar: ${(e && e.message) || e}`;
    el('aviso').erro(`falha ao publicar ${arquivo.name}: ${(e && e.message) || e}`);
  }
}

function instalarArrastarPublicar(ctx) {
  const area = el('mapa-area');
  const aviso = el('sig-largar');
  let contagem = 0;
  area.addEventListener('dragenter', (ev) => { if (temArquivo(ev)) { ev.preventDefault(); contagem += 1; aviso.hidden = false; } });
  area.addEventListener('dragover', (ev) => { if (temArquivo(ev)) ev.preventDefault(); });
  area.addEventListener('dragleave', () => { contagem = Math.max(0, contagem - 1); if (!contagem) aviso.hidden = true; });
  area.addEventListener('drop', async (ev) => {
    if (!temArquivo(ev)) return;
    ev.preventDefault();
    contagem = 0;
    aviso.hidden = true;
    const arquivo = ev.dataTransfer.files[0];
    if (arquivo) await publicarArquivoNoMapa(arquivo, ctx);
  });
  el('envio-arquivo').addEventListener('change', async (ev) => {
    const arquivo = ev.target.files[0];
    if (arquivo) await publicarArquivoNoMapa(arquivo, ctx);
    ev.target.value = '';
  });
}

/* -------------------------------------------------------------------------------------- composição
   (princípio 8): título editável + salvar grava `/api/mapas` (mesmo contrato de documento.js que /mapa
   usa — a ordem da lista do topo para o fundo é convertida por `camadasDoTopo`/`salvarOrdem`). O campo de
   título nunca fica `disabled` (pedido do orientador 10/09: "o clique nele edita"): sem composição ainda,
   editar o título e sair do campo CRIA a composição com aquele título — não exige passar pelo botão
   "nova composição" primeiro; com composição já aberta, editar o título só renomeia (PUT parcial, não
   mexe na ordem/documento). As duas ações confirmam em `plat-aviso`, como o salvar de ordem já fazia. */
const TITULO_PADRAO = 'Composição sem título';

async function instalarComposicoes({ map, catalogo, arvore, legenda, edicao }) {
  const tituloInput = el('composicao-titulo');
  const salvarBtn = el('composicao-salvar');
  const lista = el('composicoes-lista');
  const vazio = el('composicoes-vazio');
  let mapaId = new URLSearchParams(location.search).get('id');
  let doc = null;
  let ordem = [];

  async function abrirComposicao(id) {
    const { completo, documento, erro } = await carregarMapaDoc(id);
    if (erro) { el('aviso').erro(`erro ao abrir composição: ${erro.mensagem}`); return; }
    mapaId = id;
    doc = documento;
    ordem = camadasDoTopo(completo).map((c) => c.id);
    tituloInput.value = completo.titulo;
    salvarBtn.hidden = false;
    history.replaceState(null, '', `/sig?id=${encodeURIComponent(id)}`);
    if (completo.extensao_inicial) {
      const [oeste, sul, leste, norte] = completo.extensao_inicial;
      map.fitBounds([[oeste, sul], [leste, norte]], { animate: false, padding: 20 });
    }
  }

  salvarBtn.addEventListener('click', async () => {
    if (!mapaId) return;
    salvarBtn.disabled = true;
    const gravado = await (ordem.length ? salvarOrdem(mapaId, doc, ordem) : salvarDocumento(mapaId, doc));
    salvarBtn.disabled = false;
    if (gravado.erro) { el('aviso').erro(`erro ao salvar: ${gravado.erro.mensagem}`); return; }
    doc = gravado.documento;
    el('aviso').ok('composição salva');
  });

  async function criarComposicao(titulo) {
    const criado = await enviar('/api/mapas', { titulo });
    if (criado.status !== 201) { el('aviso').erro((criado.json && criado.json.mensagem) || 'falha ao criar composição'); return null; }
    await carregarListaComposicoes();
    await abrirComposicao(criado.json.id);
    el('aviso').ok('composição criada');
    return criado.json.id;
  }

  el('composicao-nova').addEventListener('click', async () => {
    tituloInput.value = TITULO_PADRAO;
    await criarComposicao(TITULO_PADRAO);
  });

  // clique no título = editar (o campo nunca é `disabled`); ao sair do campo com o texto mudado, salva —
  // cria a composição se ainda não existir, renomeia se já existir. Enter confirma sem esperar o blur.
  tituloInput.addEventListener('focus', () => tituloInput.select());
  let tituloAnterior = tituloInput.value;
  async function confirmarTitulo() {
    const titulo = tituloInput.value.trim() || TITULO_PADRAO;
    tituloInput.value = titulo;
    if (titulo === tituloAnterior) return;
    tituloAnterior = titulo;
    if (!mapaId) {
      await criarComposicao(titulo);
      return;
    }
    const r = await alterar(`/api/mapas/${encodeURIComponent(mapaId)}`, { titulo });
    if (r.status !== 200) { el('aviso').erro((r.json && r.json.mensagem) || 'falha ao renomear'); return; }
    await carregarListaComposicoes();
    el('aviso').ok('título salvo');
  }
  tituloInput.addEventListener('blur', confirmarTitulo);
  tituloInput.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); tituloInput.blur(); } });

  async function carregarListaComposicoes() {
    const r = await obter('/api/mapas?limite=50');
    if (r.status !== 200) return;
    const itens = r.json.itens || [];
    limpar(lista);
    vazio.hidden = !!itens.length;
    for (const item of itens) {
      const btn = h('button', { type: 'button', class: 'arvore-titulo', onclick: () => abrirComposicao(item.id) }, item.titulo);
      lista.append(h('li', { class: 'camada-linha' }, btn));
    }
  }

  await carregarListaComposicoes();
  if (mapaId) await abrirComposicao(mapaId);
  return { temComposicao: () => !!mapaId };
}

/* ---------------------------------------------------------------------------------------------- início */
async function iniciar() {
  instalarTema();
  pintarIcones();  /* troca os <span data-icone> da marcação estática pelo SVG da família única */
  const paineis = instalarPaineis();

  const maplibregl = window.maplibregl;
  if (!maplibregl || !window.pmtiles) { el('aviso').erro('biblioteca de mapa indisponível'); return; }
  const protocolo = new window.pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocolo.tile);

  const map = new maplibregl.Map({
    locale: { 'NavigationControl.ZoomIn': 'aproximar', 'NavigationControl.ZoomOut': 'afastar', 'NavigationControl.ResetBearing': 'norte para cima', 'ScaleControl.Meters': 'm', 'ScaleControl.Kilometers': 'km', 'AttributionControl.ToggleAttribution': 'atribuição', 'FullscreenControl.Enter': 'tela cheia', 'FullscreenControl.Exit': 'sair da tela cheia' },
    container: 'mapa',
    style: estiloDaBase(BASES[0]),
    center: CENTRO,
    zoom: 11,
    attributionControl: false,
    hash: false,
    preserveDrawingBuffer: true,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  montarBarraInferior(map);
  definirAtribuicao(BASES[0].atribuicao);

  const catalogo = new Catalogo(map);
  const gavetaTabela = montarGaveta({
    elGaveta: el('tabela-gaveta'), elAlca: el('tabela-gaveta-alca'),
    elTitulo: el('tabela-gaveta-titulo'), elContagem: el('tabela-gaveta-contagem'),
    elFiltro: el('tabela-gaveta-filtro'), elAbas: el('tabela-gaveta-abas'),
    elCabecalho: el('tabela-gaveta-cabecalho'), elCorpo: el('tabela-gaveta-corpo'),
    elFechar: el('tabela-gaveta-fechar'), elSentinela: el('tabela-gaveta-sentinela'), map,
  });
  // O realce usa a fonte original: retire-o ANTES que Catalogo remova essa fonte, inclusive em grupos.
  const desligarCamada = catalogo.desligar.bind(catalogo);
  catalogo.desligar = (id) => {
    if (gavetaTabela.fonteAtual()?.chave === `camada:${id}`) gavetaTabela.fechar();
    return desligarCamada(id);
  };
  const medicao = new Medicao(map, el('medicao-saida'));
  const arvore = new Arvore(catalogo, map, el('lista-camadas'), {
    chaveDocumento: 'plat.sig.documento.v1',
    aoAbrirPainel: (acao, camadaId) => {
      if (acao === 'tabela') gavetaTabela.abrir(fonteDeCamada(catalogo, map, camadaId));
    },
    aoEnquadrar: async (id) => {
      const ext = await catalogo.extensao(id);
      if (ext) map.fitBounds([[ext[0], ext[1]], [ext[2], ext[3]]], { padding: 40, duration: 0 });
    },
    aoErro: (e) => el('aviso').erro(`camada: ${(e && e.message) || e}`),
    aoMudarEscala: () => legenda.desenhar(),
  });
  const legenda = new Legenda(map, el('legenda'), () => arvore.camadasParaLegenda());
  instalarPopup(map, catalogo, maplibregl);
  instalarFiltroCamadas();
  instalarCompartilharCamadas(catalogo);
  instalarMedicao(medicao);
  instalarImpressao(map);
  /* bloco Exportar (item L2-01-l): o MESMO PainelExportar do /mapa antigo — camada ligada, formato, EPSG,
     "só a vista", job no servidor e link com validade; estilo MapLibre/SLD e importação de pacote. */
  const exportar = new PainelExportar(catalogo, map,
    { raiz: el('exportar-corpo'), aoErro: (e) => el('aviso').erro(`exportar: ${(e && e.message) || e}`) });
  try {
    await exportar.iniciar();
  } catch (e) {
    el('aviso').erro(`exportar: ${(e && e.message) || e}`);
  }
  let edicao = null;

  el('btn-novo-grupo').addEventListener('click', () => {
    const titulo = window.prompt('nome do grupo', 'grupo novo');
    if (titulo !== null) arvore.criarGrupo(titulo);
  });

  let redeCtl = null;
  const { atual: baseAtual } = montarListaBases(map, async (base) => {
    gavetaTabela.fechar();
    const ativas = [...catalogo.ativas];
    const opacidades = new Map(catalogo.opacidade);
    const redesLigadas = redeCtl ? [...redeCtl.redesAtivas.keys()] : [];
    map.setStyle(estiloDaBase(base));
    await new Promise((r) => map.once('styledata', r));
    catalogo.ativas = [];
    catalogo.opacidade = opacidades;
    for (const id of [...ativas].reverse()) { try { await catalogo.ligar(id); } catch { /* segue */ } }
    catalogo.reordenar(ativas);
    if (edicao) edicao._instalarFontesECamadas();
    // troca de estilo apaga as fontes/camadas da rede também (mesmo motivo do catálogo acima); religa as
    // que estavam ativas — os checkboxes do painel continuam marcados, então o estado da tela não muda.
    if (redeCtl) {
      for (const id of [...redeCtl.redesAtivas.keys()]) redeCtl.desligar(id);
      for (const id of redesLigadas) { try { await redeCtl.ligar({ id }, { enquadrar: false }); } catch { /* segue */ } }
    }
    definirAtribuicao(base.atribuicao);
  });
  void baseAtual;

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`mapa: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  instalarBusca(map, maplibregl, paineis);
  edicao = new Edicao(map, maplibregl, catalogo, { raiz: el('edicao-painel'), aoErro: (msg) => el('aviso').erro(msg) });

  const temDocumento = !!new URLSearchParams(location.search).get('id');
  try {
    await arvore.carregar();
    if (!temDocumento) await arvore.ativarPadrao(8);
    legenda.desenhar();
    el('camadas-vazio').hidden = !!catalogo.disponiveis.length;
  } catch (e) {
    el('aviso').erro(`camadas: ${(e && e.message) || e}`);
  }

  try {
    redeCtl = await instalarRede(map, maplibregl, { ativarTudo: !temDocumento, gavetaTabela });
  } catch (e) {
    el('aviso').erro(`rede de utilidades: ${(e && e.message) || e}`);
  }

  // enquadramento inicial (princípio 4, corrigido 10/09 depois da revisão no demo real): sem documento de
  // mapa salvo, a vista abre na UNIÃO de tudo que está ligado — camadas do catálogo (extensão que a
  // listagem já trouxe) + rede de utilidades (só as que `ativarTudo` ligou acima; uma rede desligada não
  // entra). Sem nenhuma extensão disponível, mantém a vista padrão (CENTRO/z11).
  if (!temDocumento) {
    const extensoesCatalogo = catalogo.disponiveis
      .filter((f) => catalogo.ativas.includes(f.id) && Array.isArray(f.extensao) && f.extensao.length === 4)
      .map((f) => f.extensao);
    const extensoesRede = redeCtl ? [...redeCtl.redesAtivas.values()].map((r) => r.bbox).filter(Boolean) : [];
    const uniao = uniaoDeExtensoes([...extensoesCatalogo, ...extensoesRede]);
    if (uniao) map.fitBounds([[uniao[0], uniao[1]], [uniao[2], uniao[3]]], { animate: false, padding: 40 });
  }

  try {
    await instalarComposicoes({ map, catalogo, arvore, legenda, edicao });
  } catch (e) {
    el('aviso').erro(`composições: ${(e && e.message) || e}`);
  }

  instalarArrastarPublicar({ map, catalogo, arvore, paineis });

  let comparar = null;
  try {
    comparar = await instalarComparar({ map, catalogo, maplibregl, el, aoErro: (e) => el('aviso').erro(`comparar: ${(e && e.message) || e}`) });
  } catch (e) {
    el('aviso').erro(`comparar: ${(e && e.message) || e}`);
  }

  window.plat = window.plat || {};
  window.plat.sig = { map, catalogo, medicao, arvore, legenda, edicao, comparar, exportar,
    abrirPainel: paineis.abrir, fecharPainel: paineis.fechar }; // ponto de inspeção do e2e
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  window.plat = window.plat || {};
  window.plat.usuario = usuario;
  el('conta-usuario').textContent = `${usuario.nome || usuario.login} · ${usuario.inquilino?.nome || usuario.inquilino?.slug || ''}`;
  try {
    await iniciar();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
