/* plat · mapa — visualizador (item L2-01-mapa-web; polimento UX-04-tela-mapa-polimento).

   Módulo ES sem empacotador; cache resolvido por `no-store` no nginx — NUNCA `?v=` num import (duas URLs para
   o mesmo arquivo criam duas instâncias do módulo e a aplicação morre, armadilha já paga na casa). MapLibre GL
   JS, o protocolo PMTiles e o terra-draw vêm de <script> clássico (vendorizados em web/vendor/ com sha256 em
   VERSOES.txt), carregados ANTES deste módulo em mapa.html: não são módulos ES.

   Chrome único (UX-04): um trilho à esquerda com um botão por painel, uma gaveta com um <plat-painel> por
   função (pesquisa, camadas, legenda, medição, desenho, anotações, impressão, exportação) e a tabela de
   atributos ancorada ao rodapé do mapa. Cada painel novo de qualquer item futuro entra como mais um
   <plat-painel> na gaveta e um botão no trilho, sem CSS próprio. Atalhos de teclado (b c l m d a i e t, f tela
   cheia, Esc fecha, ? lista), tela cheia, impressão pelo navegador e painel inferior de 390 px em celular.

   O que esta tela junta:
     camadas do catálogo (Martin/PMTiles)      catalogo.js
     árvore de camadas (ordem/grupo/escala)    ../camadas.js (L2-01-c)
     legenda dinâmica do estilo MapLibre       ../legenda.js (L2-01-c)
     janela de atributos                       atributos.js (L2-01-d)
     medição geodésica                         medicao.js
     pesquisa de endereço e de coordenada      busca.js
     impressão PNG/PDF com escala e norte      impressao.js
     tabela de atributos                       tabela.js (L2-01-g)
     desenho e anotações                       desenho.js, anotacoes.js (L2-01-k)
     exportação de camada                      exportar.js (L2-01-l)

   `body[data-pronto="1"]` só depois do primeiro 'load' do mapa: o e2e espera por isso. */
import '../base/componentes.js';
import { carregar as carregarIdioma, t, aoTraduzir } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { alterar, enviar, mensagemDe, obter } from '../base/api.js';
import { exigirSessao } from '../auth/sessao.js';
import { construirEstilo } from './estilo.js';
import { Catalogo } from './catalogo.js';
import { Arvore } from '../camadas.js';
import { Legenda } from '../legenda.js';
import { instalarPopup } from './atributos.js';
import { Medicao } from './medicao.js';
import { interpretarCoordenada, sugerir, geocodificar } from './busca.js';
import { paraPng, paraPdf, escalaNumerica } from './impressao.js';
import '../widgets/mapa.js';
import { PainelRotas } from './rotas.js';
import { PainelMotor } from './motor.js';
import { criarTabela } from './tabela.js';
import { Desenho, kmlParaGeoJSON } from './desenho.js';
import { PainelAnotacoes } from './anotacoes.js';
import { PainelExportar } from './exportar.js';

const BASES = [
  { id: 'osm-guarulhos', rotuloChave: 'mapa.base_osm_guarulhos', arquivo: 'guarulhos.pmtiles' },
  { id: 'sem-base', rotuloChave: 'mapa.base_nenhuma', arquivo: null },
];
const CENTRO = [-46.593018, -23.493476];
const PAINEIS = ['busca', 'camadas', 'legenda', 'medicao', 'desenho', 'anotacoes', 'impressao', 'exportar', 'rotas', 'motor'];
const ATALHOS = { b: 'busca', c: 'camadas', l: 'legenda', m: 'medicao', d: 'desenho', a: 'anotacoes', i: 'impressao', e: 'exportar', r: 'rotas', o: 'motor' };
const CHAVE_PAINEL = 'plat_mapa_painel';
const el = (id) => document.getElementById(id);

function urlDado(arquivo) { return `${location.origin}/static/dados/basemap/${arquivo}`; }

/* ---------------------------------------------------------------- chrome: trilho, gaveta, atalhos, tela cheia */
function painelAberto() {
  const p = document.querySelector('.mapa-gaveta plat-painel:not([hidden])');
  return p ? p.id.replace('painel-', '') : null;
}

function abrirPainel(id, { foco = true } = {}) {
  if (!PAINEIS.includes(id)) return;
  el('gaveta').hidden = false;
  for (const p of PAINEIS) {
    const painel = el(`painel-${p}`);
    painel.hidden = p !== id;
    if (p === id) painel.removeAttribute('recolhido');
  }
  document.querySelectorAll('#trilho .trilho-botao[data-painel]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.painel === id)));
  document.body.dataset.painel = id;
  try { localStorage.setItem(CHAVE_PAINEL, id); } catch { /* sem armazenamento: só nesta página */ }
  if (foco) el(`painel-${id}`).querySelector('h2')?.focus();
}

function fecharGaveta({ devolverFoco = true } = {}) {
  const aberto = painelAberto();
  el('gaveta').hidden = true;
  for (const p of PAINEIS) el(`painel-${p}`).hidden = true;
  document.querySelectorAll('#trilho .trilho-botao[data-painel]').forEach((b) => b.setAttribute('aria-pressed', 'false'));
  delete document.body.dataset.painel;
  try { localStorage.removeItem(CHAVE_PAINEL); } catch { /* idem */ }
  if (devolverFoco && aberto) document.querySelector(`#trilho [data-painel="${aberto}"]`)?.focus();
}

function alternarPainel(id) { if (painelAberto() === id) fecharGaveta(); else abrirPainel(id); }

function montarChrome() {
  for (const p of PAINEIS) {
    const painel = el(`painel-${p}`);
    painel.titulo = t(painel.dataset.titulo);
    painel.querySelector('h2')?.setAttribute('tabindex', '-1');
    painel.addEventListener('fechar', () => { painel.hidden = false; fecharGaveta(); });
  }
  aoTraduzir(() => { for (const p of PAINEIS) { const painel = el(`painel-${p}`); painel.titulo = t(painel.dataset.titulo); } });
  document.querySelectorAll('#trilho .trilho-botao[data-painel]').forEach((b) => b.addEventListener('click', () => alternarPainel(b.dataset.painel)));

  // tela cheia: a tela inteira do mapa (barra + trilho + gaveta + mapa), não só o canvas
  const btTela = el('btn-tela-cheia');
  const raiz = el('principal');
  if (!document.fullscreenEnabled) btTela.hidden = true;
  btTela.addEventListener('click', () => { if (document.fullscreenElement) document.exitFullscreen(); else raiz.requestFullscreen?.(); });
  document.addEventListener('fullscreenchange', () => {
    const ativa = document.fullscreenElement === raiz;
    btTela.setAttribute('aria-pressed', String(ativa));
    document.body.dataset.telaCheia = ativa ? '1' : '0';
  });

  // impressão pelo navegador: @media print em mapa.css esconde o chrome e deixa o canvas inteiro na página
  const imprimir = () => window.print();
  el('btn-imprimir').addEventListener('click', imprimir);
  el('btn-imprimir-navegador').addEventListener('click', imprimir);

  // navegação do produto (barra lateral) como gaveta sobre o mapa: o mapa é tela cheia por padrão
  const btNav = el('btn-nav');
  const veu = el('nav-veu');
  const definirNav = (aberta) => { document.body.dataset.nav = aberta ? '1' : '0'; btNav.setAttribute('aria-expanded', String(aberta)); veu.hidden = !aberta; if (aberta) el('lateral').querySelector('a')?.focus(); };
  btNav.addEventListener('click', () => definirNav(document.body.dataset.nav !== '1'));
  veu.addEventListener('click', () => definirNav(false));

  // atalhos
  el('btn-atalhos').addEventListener('click', mostrarAtalhos);
  document.addEventListener('keydown', (e) => {
    const alvo = e.target;
    const emCampo = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'TEXTAREA' || alvo.tagName === 'SELECT' || alvo.isContentEditable);
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Escape') {
      if (document.querySelector('dialog[open]')) return;
      if (document.body.dataset.nav === '1') { definirNav(false); return; }
      if (!el('painel-tabela').hidden && document.activeElement?.closest('#painel-tabela')) { el('tabela-alternar').click(); el('tabela-alternar').focus(); return; }
      if (painelAberto()) { fecharGaveta(); return; }
      return;
    }
    if (emCampo || document.querySelector('dialog[open]')) return;
    const k = e.key.toLowerCase();
    if (ATALHOS[k]) { e.preventDefault(); alternarPainel(ATALHOS[k]); }
    else if (k === 't') { e.preventDefault(); el('tabela-alternar').click(); }
    else if (k === 'f') { e.preventDefault(); btTela.click(); }
    else if (e.key === '?') { e.preventDefault(); mostrarAtalhos(); }
  });
  el('tabela-fechar').addEventListener('click', () => { el('tabela-alternar').click(); el('tabela-alternar').focus(); });

  // painel lembrado (ou camadas, na primeira visita em tela larga)
  let lembrado = null;
  try { lembrado = localStorage.getItem(CHAVE_PAINEL); } catch { /* sem armazenamento */ }
  const largo = window.matchMedia('(min-width: 801px)').matches;
  if (lembrado && PAINEIS.includes(lembrado)) abrirPainel(lembrado, { foco: false });
  else if (largo) abrirPainel('camadas', { foco: false });
}

function mostrarAtalhos() {
  const linhas = [
    ...Object.entries(ATALHOS).map(([k, p]) => [k, t(el(`painel-${p}`).dataset.titulo)]),
    ['t', t('tabela.alternar')], ['f', t('mapa.tela_cheia')], ['Esc', t('mapa.atalho_fechar')], ['?', t('mapa.atalhos')],
  ];
  const tabela = h('table', { class: 'tabela' }, h('tbody', {}, ...linhas.map(([k, r]) => h('tr', {}, h('td', { class: 'mono' }, h('kbd', {}, k)), h('td', {}, r)))));
  el('dialogo-atalhos').abrir({ titulo: t('mapa.atalhos'), corpo: h('div', {}, h('p', { class: 'fraco' }, t('mapa.atalhos_ajuda')), tabela), botoes: [{ id: 'ok', rotulo: t('dialogo.fechar') }] });
}

/* ---------------------------------------------------------------- mapa */
function montarSeletorBase() {
  const sel = el('seletor-base');
  for (const base of BASES) sel.append(h('option', { value: base.id }, t(base.rotuloChave)));
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
  const cor = getComputedStyle(document.documentElement).getPropertyValue('--acento').trim() || undefined;
  const m = new maplibregl.Marker({ color: cor }).setLngLat(lonlat);
  if (rotulo) m.setPopup(new maplibregl.Popup({ closeButton: true }).setText(rotulo));
  m.addTo(map);
  return m;
}

async function iniciar() {
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
  // <plat-mapa> (motor de widgets, L5-06): ações do barramento chegam como eventos DOM no recipiente
  const recipiente = el('mapa');
  recipiente.addEventListener('plat-mapa-enquadrar', ({ detail }) => {
    if (Array.isArray(detail?.extensao) && detail.extensao.length === 4) {
      map.fitBounds([[detail.extensao[0], detail.extensao[1]], [detail.extensao[2], detail.extensao[3]]]);
    }
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
  montarCoordenadas(map);

  const catalogo = new Catalogo(map);
  const medicao = new Medicao(map, el('medicao-saida'));
  const estadoCamadas = el('camadas-estado');
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
    const titulo = window.prompt(t('mapa.novo_grupo_nome'), t('mapa.novo_grupo_padrao'));
    if (titulo !== null) arvore.criarGrupo(titulo);
  });

  // troca de mapa-base: refazer o estilo apaga as camadas do catálogo, que são re-somadas em seguida
  const sel = montarSeletorBase();
  sel.addEventListener('change', async () => {
    const base = BASES.find((b) => b.id === sel.value) || BASES[0];
    const ativas = [...catalogo.ativas];
    const opacidades = new Map(catalogo.opacidade);
    const fundo = getComputedStyle(document.documentElement).getPropertyValue('--i-fundo').trim();
    map.setStyle(base.arquivo ? construirEstilo(urlDado(base.arquivo))
      : { version: 8, name: 'plat-sem-base', sources: {}, layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': fundo } }] });
    await new Promise((r) => map.once('styledata', r));
    catalogo.ativas = [];
    catalogo.opacidade = opacidades;
    for (const id of [...ativas].reverse()) { try { await catalogo.ligar(id); } catch { /* segue */ } }
    catalogo.reordenar(ativas);
  });

  // --- medição
  const pressionar = (ativo) => {
    el('btn-distancia').setAttribute('aria-pressed', String(ativo === 'distancia'));
    el('btn-area').setAttribute('aria-pressed', String(ativo === 'area'));
  };
  el('btn-distancia').addEventListener('click', () => { medicao.iniciar('distancia'); pressionar(medicao.modo); });
  el('btn-area').addEventListener('click', () => { medicao.iniciar('area'); pressionar(medicao.modo); });
  el('btn-medicao-limpar').addEventListener('click', () => { medicao.limpar(); pressionar(null); });

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
    el('busca-form').setAttribute('aria-busy', 'true');
    const r = await geocodificar(texto);
    el('busca-form').removeAttribute('aria-busy');
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
        lista.append(h('li', {}, h('button', { type: 'button', class: 'sugestao', onclick: () => { campo.value = s.texto; buscar(); } }, s.texto)));
      }
    }, 250);
  });

  // --- desenho e anotações (item L2-01-k-desenho-anotacoes)
  const desenho = new Desenho(map, maplibregl, el('bloco-desenho'));
  const params = new URLSearchParams(location.search);
  let mapaId = params.get('mapa');

  const listaDesenho = el('lista-desenho');
  const redesenharLista = (features) => {
    limpar(listaDesenho);
    features.forEach((f) => {
      const medida = desenho.medidaDe(f);
      listaDesenho.append(h('li', { class: 'camada-item', dataset: { desenho: f.id } },
        h('span', { class: 'camada-titulo' }, `${f.properties.tipo_desenho}${medida ? ' · ' + medida : ''}`),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t(desenho.editando() === f.id ? 'mapa.desenho_editar_fim' : 'mapa.desenho_editar'),
          onclick: () => (desenho.editando() === f.id ? desenho.terminarEdicao() : desenho.editar(f.id)) }, desenho.editando() === f.id ? '✓' : '✎'),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_mover_cima'), onclick: () => desenho.mover(f.id, -1) }, '↑'),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_mover_baixo'), onclick: () => desenho.mover(f.id, 1) }, '↓'),
        h('button', { type: 'button', class: 'pequeno texto', 'aria-label': t('mapa.desenho_apagar'), onclick: () => desenho.apagar(f.id) }, '×')));
    });
  };
  desenho.aoMudar(redesenharLista);
  for (const botao of document.querySelectorAll('[data-desenho]')) {
    botao.addEventListener('click', () => {
      desenho.iniciarModo(botao.dataset.desenho);
      document.querySelectorAll('[data-desenho]').forEach((b) => b.setAttribute('aria-pressed', String(b === botao)));
    });
  }
  const pararDesenho = () => { desenho.pararModo(); document.querySelectorAll('[data-desenho]').forEach((b) => b.setAttribute('aria-pressed', 'false')); };
  el('btn-desenho-parar').addEventListener('click', pararDesenho);
  el('btn-desenho-limpar').addEventListener('click', () => desenho.limparTudo());
  const atualizarEstiloAtual = () => desenho.definirEstilo({
    cor: el('desenho-cor').value,
    contorno: getComputedStyle(document.documentElement).getPropertyValue('--i-fundo').trim(),
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
      el('desenho-saida').textContent = t('mapa.desenho_importado', { n: desenho.importarGeoJSON(colecao) });
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

  // --- exportação (item L2-01-l)
  const painelExportar = new PainelExportar(catalogo, map, {
    raiz: el('exportar'),
    aoErro: (e) => el('aviso').erro(`${t('mapa.exportar_falhou', { erro: (e && e.message) || e })}`),
  });

  // --- rotas (rota, isócrona, matriz) e motor multicritério de grades aninhadas (item UX-08)
  const painelRotas = new PainelRotas(map, maplibregl, el('rotas'));
  const painelMotor = new PainelMotor(map, maplibregl, el('motor'));

  // --- impressão PNG/PDF: a legenda impressa é a MESMA que o painel mostra
  const titulo = () => `${t('mapa.titulo')} — ${new Date().toLocaleDateString('pt-BR')}`;
  const atribuicao = '© colaboradores do OpenStreetMap — ODbL 1.0';
  const legendaDaTela = () => catalogo.ativas.map((id) => catalogo.ficha(id)).filter(Boolean).flatMap((f) => f.legenda || []).slice(0, 12);
  const imprimirComo = async (formato) => {
    const saida = el('impressao-saida');
    saida.textContent = t('mapa.impressao_gerando');
    try {
      const opcoes = { titulo: titulo(), atribuicao, legenda: legendaDaTela() };
      const r = formato === 'PNG'
        ? await paraPng(map, { ...opcoes, nome: 'mapa.png', escalaSaida: el('png-2x').checked ? 2 : 1 })
        : await paraPdf(map, { ...opcoes, nome: 'mapa.pdf' });
      saida.textContent = t('mapa.impressao_pronta', { formato, kb: Math.round(r.bytes / 1024) });
    } catch (e) {
      saida.textContent = `${t('mapa.impressao_falhou')}: ${(e && e.message) || e}`;
    }
  };
  el('btn-png').addEventListener('click', () => imprimirComo('PNG'));
  el('btn-pdf').addEventListener('click', () => imprimirComo('PDF'));

  map.on('error', (ev) => {
    const msg = (ev && ev.error && ev.error.message) || String(ev);
    el('aviso').erro(`${t('mapa.erro_carregar')}: ${msg}`);
  });
  map.on('moveend', () => {
    const limites = map.getBounds();
    recipiente.emitir?.('mapa.extensao_alterada', {
      extensao: [limites.getWest(), limites.getSouth(), limites.getEast(), limites.getNorth()],
    });
  });

  await new Promise((resolve) => map.once('load', resolve));
  estadoCamadas.carregando();
  try {
    await arvore.carregar();
    legenda.desenhar();
    await painelExportar.iniciar();
    estadoCamadas.limpar();
    if (!el('lista-camadas').children.length) estadoCamadas.mostrar({ tipo: 'vazio', titulo: t('mapa.sem_camadas_titulo'), texto: t('mapa.sem_camadas') });
  } catch (e) {
    estadoCamadas.erro({ status: e && e.status, json: { mensagem: (e && e.message) || String(e) } }, [{ id: 'tentar', rotulo: t('estado.tentar_de_novo'), classe: 'primario' }]);
    el('aviso').erro(`${t('mapa.erro_camada')}: ${(e && e.message) || e}`);
  }
  estadoCamadas.addEventListener('acao', async () => { estadoCamadas.carregando(); try { await arvore.carregar(); legenda.desenhar(); estadoCamadas.limpar(); } catch (e) { estadoCamadas.erro({ status: e && e.status, json: { mensagem: (e && e.message) || String(e) } }); } });

  // tabela de atributos (L2-01-g): painel ancorado ao rodapé do mapa; a seleção da tabela realça a feição
  await criarTabela(map, el('aviso')).iniciar();

  // item L2-01-d-popup-runtime: o fuso do inquilino, uma vez só (nunca por campo de data no popup)
  window.plat = window.plat || {};
  window.plat.org = window.plat.org || {};
  obter('/api/mapa/fuso').then((r) => { if (r.status === 200) window.plat.org.fuso = r.json.fuso; }).catch(() => {});
  // ponto de inspeção do e2e, nunca de negócio
  window.plat.mapa = { map, catalogo, medicao, arvore, legenda, desenho, painelAnotacoes, exportar: painelExportar, rotas: painelRotas, motor: painelMotor, abrirPainel, fecharGaveta, painelAberto, get mapaId() { return mapaId; } };
  document.body.dataset.pronto = '1';
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  montarLayout({ usuario, ativo: '/mapa' });
  montarChrome();
  try {
    await iniciar();
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
