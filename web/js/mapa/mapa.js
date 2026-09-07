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
import { construirEstilo } from './estilo.js';
import { Catalogo } from './catalogo.js';
import { Arvore } from '../camadas.js';
import { Legenda } from '../legenda.js';
import { instalarPopup } from './atributos.js';
import { Medicao } from './medicao.js';
import { interpretarCoordenada, sugerir, geocodificar } from './busca.js';
import { paraPng, paraPdf, escalaNumerica } from './impressao.js';
import { Desenho, kmlParaGeoJSON } from './desenho.js';
import { PainelAnotacoes } from './anotacoes.js';
import { alterar, enviar, mensagemDe, obter } from '../base/api.js';

const BASES = [
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', arquivo: 'guarulhos.pmtiles' },
  { id: 'sem-base', rotuloChave: 'mapa.base_nenhuma', arquivo: null },
];
const CENTRO = [-46.593018, -23.493476];
const el = (id) => document.getElementById(id);

function urlDado(arquivo) { return `${location.origin}/static/dados/basemap/${arquivo}`; }

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

async function iniciar(usuario) {
  const maplibregl = window.maplibregl;
  if (!maplibregl || !window.pmtiles) { el('aviso').erro(t('mapa.erro_biblioteca')); return; }
  const protocolo = new window.pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocolo.tile);

  const map = new maplibregl.Map({
    container: 'mapa',
    style: construirEstilo(urlDado(BASES[0].arquivo)),
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
    map.setStyle(base.arquivo ? construirEstilo(urlDado(base.arquivo))
      : { version: 8, name: 'plat-sem-base', sources: {}, layers: [
        { id: 'fundo', type: 'background', paint: { 'background-color': '#0b0f10' } }] });
    await new Promise((r) => map.once('styledata', r));
    catalogo.ativas = [];
    catalogo.opacidade = opacidades;
    for (const id of [...ativas].reverse()) { try { await catalogo.ligar(id); } catch { /* segue */ } }
    catalogo.reordenar(ativas);
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

  // --- desenho e anotações (item L2-01-k-desenho-anotacoes)
  const desenho = new Desenho(map, maplibregl, el('bloco-desenho'));
  const params = new URLSearchParams(location.search);
  let mapaId = params.get('mapa');

  const listaDesenho = el('lista-desenho');
  const redesenharLista = (features) => {
    limpar(listaDesenho);
    features.forEach((f, i) => {
      const medida = desenho.medidaDe(f);
      listaDesenho.append(h('li', { class: 'camada-item', dataset: { desenho: f.id } },
        h('span', { class: 'camada-titulo' }, `${f.properties.tipo_desenho}${medida ? ' · ' + medida : ''}`),
        h('button', {
          type: 'button', class: 'botao-mini',
          'aria-label': t(desenho.editando() === f.id ? 'mapa.desenho_editar_fim' : 'mapa.desenho_editar'),
          onclick: () => (desenho.editando() === f.id ? desenho.terminarEdicao() : desenho.editar(f.id)),
        }, desenho.editando() === f.id ? '✓' : '✎'),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('mapa.desenho_mover_cima'), onclick: () => desenho.mover(f.id, -1) }, '↑'),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('mapa.desenho_mover_baixo'), onclick: () => desenho.mover(f.id, 1) }, '↓'),
        h('button', { type: 'button', class: 'botao-mini', 'aria-label': t('mapa.desenho_apagar'), onclick: () => desenho.apagar(f.id) }, '×')));
    });
  };
  desenho.aoMudar(redesenharLista);

  for (const botao of document.querySelectorAll('[data-desenho]')) {
    botao.addEventListener('click', () => desenho.iniciarModo(botao.dataset.desenho));
  }
  el('btn-desenho-parar').addEventListener('click', () => desenho.pararModo());
  el('btn-desenho-limpar').addEventListener('click', () => desenho.limparTudo());
  const atualizarEstiloAtual = () => desenho.definirEstilo({
    cor: el('desenho-cor').value,
    contorno: '#10161a',
    opacidade: Number(el('desenho-opacidade').value),
    largura: Number(el('desenho-largura').value),
    tamanho_fonte: Number(el('desenho-fonte').value),
  });
  ['desenho-cor', 'desenho-opacidade', 'desenho-largura', 'desenho-fonte'].forEach((id) => el(id).addEventListener('input', atualizarEstiloAtual));
  atualizarEstiloAtual();
  el('desenho-snap').addEventListener('change', (ev) => desenho.definirSnap(ev.target.checked));
  el('btn-desenho-editar-fim').addEventListener('click', () => desenho.terminarEdicao());

  const salvarDesenho = async () => {
    const corpo = { esquema_versao: 1, corpo: { desenho: { features: desenho.lista() } } };
    const r = mapaId ? await alterar(`/api/itens/${mapaId}`, { dados: corpo })
      : await enviar('/api/itens', { tipo: 'mapa', titulo: `${t('mapa.titulo')} ${new Date().toLocaleString('pt-BR')}`, dados: corpo });
    if (r.status >= 400) { el('desenho-saida').textContent = mensagemDe(r); return; }
    if (!mapaId) {
      mapaId = r.json.id;
      const novaUrl = new URL(location.href);
      novaUrl.searchParams.set('mapa', mapaId);
      history.replaceState(null, '', novaUrl);
    }
    el('desenho-saida').textContent = t('mapa.desenho_salvo');
  };
  el('btn-desenho-salvar').addEventListener('click', salvarDesenho);

  el('btn-desenho-promover').addEventListener('click', async () => {
    if (!mapaId) await salvarDesenho();
    if (!mapaId) return;
    const titulo = window.prompt(t('mapa.desenho_promover_pedir_titulo'), `${t('mapa.desenho')} ${new Date().toLocaleDateString('pt-BR')}`);
    if (!titulo) return;
    const r = await enviar(`/api/mapa/${mapaId}/desenho/promover`, { titulo });
    if (r.status >= 400) { el('desenho-saida').textContent = mensagemDe(r); return; }
    el('desenho-saida').textContent = t('mapa.desenho_promovido', { titulo, n: r.json.n_feicoes });
    await arvore.carregar();
  });

  el('desenho-importar').addEventListener('change', async (ev) => {
    const arquivo = ev.target.files[0];
    if (!arquivo) return;
    const texto = await arquivo.text();
    try {
      const colecao = arquivo.name.toLowerCase().endsWith('.kml') ? kmlParaGeoJSON(texto) : JSON.parse(texto);
      const n = desenho.importarGeoJSON(colecao);
      el('desenho-saida').textContent = t('mapa.desenho_importado', { n });
    } catch (e) {
      el('desenho-saida').textContent = `${t('mapa.erro_carregar')}: ${(e && e.message) || e}`;
    }
    ev.target.value = '';
  });

  const painelAnotacoes = new PainelAnotacoes(map, catalogo, {
    btnModo: el('btn-anotar'), corpo: el('anotacoes-corpo'), alvo: el('anotacoes-alvo'),
    lista: el('lista-anotacoes'), selGrupo: el('anotacao-grupo'), campoTexto: el('anotacao-texto'),
    btnEnviar: el('btn-anotacao-enviar'),
  });

  if (mapaId) {
    try {
      const r = await obter(`/api/itens/${mapaId}`);
      if (r.status === 200) {
        const features = ((r.json.dados || {}).corpo || {}).desenho?.features || [];
        if (features.length) desenho.carregarFeatures(features);
      }
    } catch { /* documento novo ou inexistente: começa vazio, sem quebrar a tela */ }
  }

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  try {
    await arvore.carregar();
    legenda.desenhar();
  } catch (e) {
    el('aviso').erro(`${t('mapa.erro_camada')}: ${(e && e.message) || e}`);
  }
  window.plat = window.plat || {};
  // ponto de inspeção do e2e, nunca de negócio
  window.plat.mapa = { map, catalogo, medicao, arvore, legenda, desenho, painelAnotacoes, get mapaId() { return mapaId; } };
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  try {
    await iniciar(usuario);
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
