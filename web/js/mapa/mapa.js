/* plat · mapa — entrada da tela /mapa (item L2-01-a-basemap-local-pmtiles). Módulo ES sem build; cache resolvido
   por no-store no nginx: NUNCA ?v= nos imports. Requer sessão (ADR 0002, exigirSessao). MapLibre GL JS e o
   protocolo pmtiles vêm de <script> clássico (window.maplibregl / window.pmtiles, vendorizados em web/vendor/,
   VERSOES.txt) carregado ANTES deste módulo em mapa.html — os dois não são módulos ES.

   Mapa-base 100 % local: PMTiles estático (web/dados/basemap/guarulhos.pmtiles) lido por Range HTTP pelo próprio
   nginx do appliance (sem Martin, sem serviço de tiles dinâmico — isso é item futuro). Controles: navegação
   (zoom/pan, padrão MapLibre + arrastar/roda do mouse), escala, coordenadas do cursor (lê 'mousemove' do mapa) e
   seletor de camada base — mecanismo genérico por lista (BASES), uma opção hoje; a próxima base só entra na
   lista, o resto do fiação já funciona. body[data-pronto="1"] só depois do primeiro 'load' do mapa (o e2e espera
   por isso antes de tirar a captura que prova o canvas desenhado). */
import '../base/componentes.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from './estilo.js';
import * as api from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { AVISO_VENCIDA, selo } from '../acervo/frescor.js';
import { Desenho, kmlParaGeoJSON } from './desenho.js';
import { PainelAnotacoes } from './anotacoes.js';
import { PainelRotas } from './rotas.js';
import { Catalogo } from './catalogo.js';
import { icone } from '../base/icones.js';

const BASES = [
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', arquivo: 'guarulhos.pmtiles' },
];

const el = (id) => document.getElementById(id);

function urlDado(arquivo) {
  return `${location.origin}/static/dados/basemap/${arquivo}`;
}

function montarSeletorBase(map, baseAtual) {
  const sel = el('seletor-base');
  for (const base of BASES) {
    const opt = document.createElement('option');
    opt.value = base.id;
    opt.textContent = t(base.rotuloChave);
    sel.append(opt);
  }
  sel.value = (baseAtual || BASES[0]).id;
  sel.addEventListener('change', () => {
    const base = BASES.find((b) => b.id === sel.value) || BASES[0];
    /* construirEstilo recebe o descritor {tipo, url} (a união 10/09 trocou a assinatura e os chamadores
       de mapa.js ficaram passando string — caiam em estiloSemBase e a base nunca pintava; achado L0-07-a) */
    map.setStyle(construirEstilo({ tipo: 'pmtiles', url: urlDado(base.arquivo) }));
  });
}

function montarCoordenadas(map) {
  const caixa = el('coordenadas');
  const escrever = (lng, lat, zoom) => {
    caixa.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} · z${zoom.toFixed(1)}`;
  };
  const mostrarCentro = () => { const c = map.getCenter(); escrever(c.lng, c.lat, map.getZoom()); };
  map.on('mousemove', (ev) => escrever(ev.lngLat.lng, ev.lngLat.lat, map.getZoom()));
  map.on('mouseout', mostrarCentro);
  map.on('zoomend', mostrarCentro);
  mostrarCentro();
}

/* item L6-01-h-frescor-verificacao: lista as camadas EXPOSTAS do acervo com o estado de verificação, para que
   quem for usar uma camada veja o aviso ANTES de confiar nela. O selo e o texto vêm de web/js/acervo/frescor.js
   — o mesmo módulo que a ficha em /acervo usa, para o aviso não divergir entre as duas telas. O painel fica
   escondido quando a API não responde ou quando não há camada exposta: painel vazio não é informação. */
async function montarPainelAcervo() {
  const painel = el('painel-acervo');
  if (!painel) return { total: 0, vencidas: 0 };
  const r = await api.obter('/api/acervo/camadas?limite=50');
  if (r.status !== 200 || !r.json || !Array.isArray(r.json.itens) || !r.json.itens.length) {
    painel.hidden = true;
    return { total: 0, vencidas: 0 };
  }
  const { itens, total, vencidas } = r.json;
  el('acervo-resumo').textContent = vencidas
    ? `${vencidas} de ${total} com ${AVISO_VENCIDA}`
    : `${total} camada(s), nenhuma com ${AVISO_VENCIDA}`;
  const lista = el('acervo-lista');
  limpar(lista);
  for (const c of itens) {
    lista.append(h('li', { 'data-camada': c.acervo_camada_id, 'data-vencida': c.verificacao_vencida ? '1' : '0' },
      h('code', { title: `${c.fonte_nome || c.fonte_id}` }, `${c.schema_nome}.${c.tabela}`),
      selo(c, h)));
  }
  painel.hidden = false;
  return { total, vencidas };
}

/* item L2-01-k-desenho-anotacoes: painéis de desenho e de anotações ligados à tela. O desenho mora no
   documento do mapa (POST/PUT /api/itens tipo 'mapa', corpo.desenho.features — GeoJSON + estilo, sem
   tabela); "promover a camada" chama /api/mapa/{id}/desenho/promover (job de ingestão do L0-04); as
   anotações são as rotas /api/anotacoes (visibilidade por grupo, prova em tests/api/catalogo).
   'rotas' (UX-08) foi religado pelo L2-11-c: a fusão que trouxe o L2-01-k reescreveu esta tela e perdeu a
   montagem do painel de rotas que o tronco já tinha (rotas.js sobreviveu; a fiação, não). */
const PAINEIS_FLUTUANTES = { desenho: 'painel-desenho', anotacoes: 'painel-anotacoes', camadas: 'painel-camadas', rotas: 'painel-rotas' };
const TITULO_PAINEL = { desenho: 'mapa.desenho', anotacoes: 'mapa.anotacoes', rotas: 'rotas.titulo' };

function abrirPainel(nome, { foco = true } = {}) {
  const painel = el(PAINEIS_FLUTUANTES[nome]);
  if (!painel) return;
  if (typeof painel.abrir === 'function') {
    painel.titulo = t(TITULO_PAINEL[nome] || nome);
    painel.abrir();
  } else {
    painel.hidden = false;
  }
  if (foco) painel.querySelector('button, input, select, textarea')?.focus();
}

/* painel de camadas do catálogo: a lista vem de /api/mapa/camadas (Catalogo, item L2-01-mapa-web); clicar
   liga/desliga a camada no mapa. Sem lista o painel fica escondido — painel vazio não é informação. */
async function montarPainelCamadas(map, catalogo) {
  const secao = el('painel-camadas');
  const lista = h('ul', { id: 'lista-camadas', class: 'lista-camadas', 'aria-labelledby': 'camadas-titulo' });
  el('camadas').append(lista);
  const redesenhar = () => {
    limpar(lista);
    for (const c of catalogo.disponiveis) {
      const ativa = catalogo.ativas.includes(c.id);
      lista.append(h('li', { class: 'camada-item', dataset: { camada: c.id } },
        h('button', {
          type: 'button', class: 'pequeno texto camada-titulo', 'aria-pressed': String(ativa),
          onclick: async () => {
            try {
              if (ativa) catalogo.desligar(c.id);
              else await catalogo.ligar(c.id);
              redesenhar();
            } catch (e) {
              el('aviso').erro(`${t('mapa.erro_carregar')}: ${(e && e.message) || e}`);
            }
          },
        }, c.titulo || c.id)));
    }
    secao.hidden = !catalogo.disponiveis.length;
  };
  try {
    await catalogo.carregar();
  } catch {
    secao.hidden = true; // catálogo indisponível: o resto da tela continua de pé
    return;
  }
  redesenhar();
}

async function montarDesenhoAnotacoes(map) {
  el('btn-painel-desenho').addEventListener('click', () => abrirPainel('desenho'));
  el('btn-painel-anotacoes').addEventListener('click', () => abrirPainel('anotacoes'));
  el('btn-painel-camadas').addEventListener('click', () => abrirPainel('camadas'));
  el('btn-painel-rotas').addEventListener('click', () => abrirPainel('rotas'));

  const desenho = new Desenho(map, window.maplibregl, el('bloco-desenho'));
  const catalogo = new Catalogo(map);
  let mapaId = new URLSearchParams(location.search).get('mapa');

  const listaDesenho = el('lista-desenho');
  desenho.aoMudar((features) => {
    limpar(listaDesenho);
    for (const f of features) {
      const medida = desenho.medidaDe(f);
      const emEdicao = desenho.editando() === f.id;
      listaDesenho.append(h('li', { class: 'camada-item', dataset: { desenho: f.id } },
        h('span', { class: 'camada-titulo' }, `${f.properties.tipo_desenho}${medida ? ` · ${medida}` : ''}`),
        h('button', { type: 'button', class: 'pequeno texto',
          'aria-label': t(emEdicao ? 'mapa.desenho_editar_fim' : 'mapa.desenho_editar'),
          onclick: () => (emEdicao ? desenho.terminarEdicao() : desenho.editar(f.id)) },
          icone(emEdicao ? 'ok' : 'editar', { tamanho: 14 })),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_mover_cima'),
          onclick: () => desenho.mover(f.id, -1) }, icone('seta_cima', { tamanho: 14 })),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_mover_baixo'),
          onclick: () => desenho.mover(f.id, 1) }, icone('seta_baixo', { tamanho: 14 })),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_apagar'),
          onclick: () => desenho.apagar(f.id) }, icone('fechar', { tamanho: 14 }))));
    }
  });
  for (const botao of document.querySelectorAll('[data-desenho]')) {
    botao.addEventListener('click', () => {
      desenho.iniciarModo(botao.dataset.desenho);
      document.querySelectorAll('[data-desenho]').forEach((b) => b.setAttribute('aria-pressed', String(b === botao)));
    });
  }
  const pararDesenho = () => {
    desenho.pararModo();
    document.querySelectorAll('[data-desenho]').forEach((b) => b.setAttribute('aria-pressed', 'false'));
  };
  el('btn-desenho-parar').addEventListener('click', pararDesenho);
  el('btn-desenho-limpar').addEventListener('click', () => desenho.limparTudo());
  el('btn-desenho-editar-fim').addEventListener('click', () => desenho.terminarEdicao());
  const atualizarEstiloAtual = () => desenho.definirEstilo({
    cor: el('desenho-cor').value,
    contorno: getComputedStyle(document.documentElement).getPropertyValue('--i-fundo').trim(),
    opacidade: Number(el('desenho-opacidade').value),
    largura: Number(el('desenho-largura').value),
    tamanho_fonte: Number(el('desenho-fonte').value),
  });
  for (const id of ['desenho-cor', 'desenho-opacidade', 'desenho-largura', 'desenho-fonte']) {
    el(id).addEventListener('input', atualizarEstiloAtual);
  }
  atualizarEstiloAtual();
  el('desenho-snap').addEventListener('change', (ev) => desenho.definirSnap(ev.target.checked));

  const salvarDesenho = async () => {
    const corpo = { esquema_versao: 1, corpo: { desenho: { features: desenho.lista() } } };
    const r = mapaId
      ? await api.alterar(`/api/itens/${mapaId}`, { dados: corpo })
      : await api.enviar('/api/itens', { tipo: 'mapa', titulo: `${t('mapa.titulo')} ${new Date().toLocaleString('pt-BR')}`, dados: corpo });
    if (r.status >= 400) { el('desenho-saida').textContent = api.mensagemDe(r); return; }
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
    const r = await api.enviar(`/api/mapa/${mapaId}/desenho/promover`, { titulo });
    if (r.status >= 400) { el('desenho-saida').textContent = api.mensagemDe(r); return; }
    el('desenho-saida').textContent = t('mapa.desenho_promovido', { titulo, n: r.json.n_feicoes });
  });
  el('desenho-importar').addEventListener('change', async (ev) => {
    const arquivo = ev.target.files[0];
    if (!arquivo) return;
    const texto = await arquivo.text();
    try {
      const colecao = arquivo.name.toLowerCase().endsWith('.kml') ? kmlParaGeoJSON(texto) : JSON.parse(texto);
      el('desenho-saida').textContent = t('mapa.desenho_importado', { n: desenho.importarGeoJSON(colecao) });
    } catch (e) {
      el('desenho-saida').textContent = `${t('mapa.erro_carregar')}: ${(e && e.message) || e}`;
    }
    ev.target.value = '';
  });

  const anotacoes = new PainelAnotacoes(map, catalogo, {
    btnModo: el('btn-anotar'), corpo: el('anotacoes-corpo'), alvo: el('anotacoes-alvo'),
    lista: el('lista-anotacoes'), selGrupo: el('anotacao-grupo'), campoTexto: el('anotacao-texto'),
    btnEnviar: el('btn-anotacao-enviar'), estado: el('anotacoes-estado'), aviso: el('anotacoes-aviso'),
  });

  const rotas = new PainelRotas(map, window.maplibregl, el('rotas'));

  await montarPainelCamadas(map, catalogo);

  if (mapaId) {
    try {
      const r = await api.obter(`/api/itens/${mapaId}`);
      if (r.status === 200) {
        const features = r.json.dados?.corpo?.desenho?.features || [];
        if (features.length) desenho.carregarFeatures(features);
      }
    } catch { /* documento novo ou inexistente: começa vazio, sem quebrar a tela */ }
  }

  // ponto de inspeção do e2e, nunca de negócio
  window.plat = window.plat || {};
  window.plat.mapa = { map, desenho, anotacoes, painelAnotacoes: anotacoes, catalogo, rotas, abrirPainel, get mapaId() { return mapaId; } };
}

async function iniciarMapa(usuario) {
  if (!window.maplibregl || !window.pmtiles) {
    el('aviso').erro(t('mapa.erro_biblioteca'));
    return;
  }
  const protocolo = new window.pmtiles.Protocol();
  window.maplibregl.addProtocol('pmtiles', protocolo.tile);

  /* item L0-07-a: o mapa abre na vista padrão DO INQUILINO (Organização > Configurações > Mapa padrão,
     servida em /api/eu config_publica): centro+zoom quando há centro; senão extent (moldura); sem nada,
     o recorte do pmtiles de Guarulhos (metadado em PROVENIENCIA.md). basemap casa pelo id da lista BASES;
     id desconhecido cai na primeira base (o seletor continua mostrando o que está de fato ligado). */
  const pub = usuario?.inquilino?.config_publica || {};
  const base = BASES.find((b) => b.id === pub.basemap) || BASES[0];
  const vista = { style: construirEstilo({ tipo: 'pmtiles', url: urlDado(base.arquivo) }) };
  if (Array.isArray(pub.centro) && pub.centro.length === 2) {
    vista.center = pub.centro;
    vista.zoom = typeof pub.zoom === 'number' ? pub.zoom : 13;
  } else if (Array.isArray(pub.extent) && pub.extent.length === 4) {
    vista.bounds = [[pub.extent[0], pub.extent[1]], [pub.extent[2], pub.extent[3]]];
  } else {
    vista.center = [-46.593018, -23.493476]; // centro do recorte (metadado do pmtiles, PROVENIENCIA.md)
    vista.zoom = 13;
  }
  const map = new window.maplibregl.Map({
    container: 'mapa',
    ...vista,
    attributionControl: false,
    hash: false,
  });
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new window.maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new window.maplibregl.AttributionControl({ compact: false }), 'bottom-right');

  montarSeletorBase(map, base);
  montarCoordenadas(map);

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });

  await new Promise((resolve) => map.once('load', resolve));
  try {
    await montarPainelAcervo();
  } catch (e) {
    el('aviso').mostrar(`camadas do acervo indisponíveis: ${(e && e.message) || e}`, 'atencao');
  }
  await montarDesenhoAnotacoes(map);
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  try {
    await iniciarMapa(usuario);
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
