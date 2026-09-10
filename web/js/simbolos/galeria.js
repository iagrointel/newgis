/* plat · símbolos — entrada da tela /simbolos (item L2-02-e-simbolos-sprites-glifos). Módulo ES sem build;
   cache resolvido por no-store no nginx: NUNCA ?v= nos imports. Requer sessão.

   A galeria lê a lista de /api/simbolos e recorta cada ícone do sprite.png do PRÓPRIO inquilino
   (/api/simbolos/sprite/{slug}.png + .json) num <canvas> pequeno — o mesmo par que o MapLibre consome via
   `sprite:` no estilo. Clicar num ícone da galeria recorta a MESMA região do sprite para um <img> (data URL)
   e usa esse elemento como marcador do MapLibre no centro do mapa: "escolher ícone da galeria e ver no mapa"
   (cláusula de e2e do portão) usa exatamente o sprite servido pela API, não uma cópia à parte. */
import '../base/componentes.js';
import { obter, enviar } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar as carregarIdioma, t } from '../base/i18n.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const el = (id) => document.getElementById(id);
let SPRITE_JSON = null;
let SPRITE_IMG = null;
let MAPA = null;
let SLUG = null;

async function carregarSprite(slug) {
  const [rJson, img] = await Promise.all([
    fetch(`/api/simbolos/sprite/${slug}.json`, { credentials: 'same-origin', cache: 'no-store' }).then((r) => r.json()),
    new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = reject;
      im.src = `/api/simbolos/sprite/${slug}.png?_=${Date.now()}`;
    }),
  ]);
  SPRITE_JSON = rJson;
  SPRITE_IMG = img;
}

function recortarParaCanvas(nome, ladoCss = 24) {
  const meta = SPRITE_JSON[nome];
  const canvas = document.createElement('canvas');
  canvas.width = ladoCss;
  canvas.height = ladoCss;
  if (!meta || !SPRITE_IMG) return canvas;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(SPRITE_IMG, meta.x, meta.y, meta.width, meta.height, 0, 0, ladoCss, ladoCss);
  return canvas;
}

function recortarParaDataUrl(nome, lado = 32) {
  const c = recortarParaCanvas(nome, lado);
  return c.toDataURL('image/png');
}

function colocarNoMapa(nome) {
  if (!MAPA) return;
  const dataUrl = recortarParaDataUrl(nome, 32);
  const imgEl = document.createElement('img');
  imgEl.src = dataUrl;
  imgEl.width = 32;
  imgEl.height = 32;
  imgEl.alt = nome;
  const centro = MAPA.getCenter();
  // jitter pequeno para não empilhar marcadores exatamente no mesmo ponto a cada clique
  const jitter = () => (Math.random() - 0.5) * 0.01;
  new window.maplibregl.Marker({ element: imgEl })
    .setLngLat([centro.lng + jitter(), centro.lat + jitter()])
    .addTo(MAPA);
  el('mapa').dataset.ultimoIcone = nome;
}

function montarGrade(itens) {
  const grade = el('grade');
  limpar(grade);
  for (const item of itens) {
    const botao = h(
      'button',
      { type: 'button', class: 'simbolos-icone', role: 'listitem', title: item.nome, onClick: () => colocarNoMapa(item.nome) },
      recortarParaCanvas(item.nome),
      h('span', {}, item.nome),
    );
    grade.append(botao);
  }
}

function montarFiltroCategoria(categorias) {
  const sel = el('categoria');
  limpar(sel);
  sel.append(h('option', { value: '' }, t('simbolos.todas_categorias')));
  for (const chave of Object.keys(categorias).sort()) {
    sel.append(h('option', { value: chave }, categorias[chave].rotulo || chave));
  }
}

async function recarregarGaleria() {
  const busca = el('busca').value.trim();
  const categoria = el('categoria').value;
  const params = new URLSearchParams();
  if (busca) params.set('busca', busca);
  if (categoria) params.set('categoria', categoria);
  const r = await obter(`/api/simbolos?${params.toString()}`);
  if (r.status !== 200) {
    el('aviso').erro(t('simbolos.erro_carregar'));
    return;
  }
  if (r.status === 200 && !el('categoria').childElementCount) montarFiltroCategoria(r.json.categorias);
  montarGrade(r.json.itens);
}

async function enviarIcone(ev) {
  ev.preventDefault();
  const nome = el('up-nome').value.trim();
  const categoria = el('up-categoria').value.trim() || 'personalizado';
  const arquivo = el('up-svg').files[0];
  if (!arquivo) return;
  const conteudo_svg = await arquivo.text();
  const r = await enviar('/api/simbolos', { nome, categoria, conteudo_svg });
  if (r.status !== 201) {
    el('aviso').erro(r.json.mensagem || t('simbolos.erro_enviar'));
    return;
  }
  el('aviso').ok(t('simbolos.enviado'));
  await carregarSprite(SLUG);
  await recarregarGaleria();
  ev.target.reset();
}

function montarMapa() {
  const map = new window.maplibregl.Map({
    container: 'mapa',
    style: {
      version: 8,
      // glifos embutidos (Noto Sans/Open Sans) do PRÓPRIO item — qualquer camada de texto desta tela (e a
      // do e2e) lê daqui, não de um serviço de terceiro.
      glyphs: `${location.origin}/api/simbolos/fontes/{fontstack}/{range}.pbf`,
      sources: {},
      layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#0b0f10' } }],
    },
    center: [-46.593018, -23.493476],
    zoom: 12,
    attributionControl: false,
  });
  map.addControl(new window.maplibregl.NavigationControl(), 'top-right');
  MAPA = map;
  // exposto só para o e2e do item confirmar que os glifos embutidos (fontes/sprite desta MESMA tela)
  // renderizam texto com acento — não é um endpoint novo, é a instância que a página já criou.
  window.__platMapaSimbolos = map;
  return new Promise((resolve) => map.once('load', resolve));
}

async function iniciar(usuario) {
  montarLayout({ usuario, ativo: '/simbolos' });
  cabecalho(t('simbolos.titulo'));
  SLUG = usuario.inquilino.slug;
  await montarMapa();
  await carregarSprite(SLUG);
  await recarregarGaleria();
  el('busca').addEventListener('input', recarregarGaleria);
  el('categoria').addEventListener('change', recarregarGaleria);
  el('form-upload').addEventListener('submit', enviarIcone);
  pronto();
}

await carregarIdioma();
const usuario = await exigirSessao();
if (usuario) {
  try {
    await iniciar(usuario);
  } catch (e) {
    el('aviso').erro(`${t('erro.carregar')}: ${(e && e.message) || e}`);
    pronto();
  }
}
