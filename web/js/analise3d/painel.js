/* plat · análise 3D — entrada da tela /analise3d (item L2-09-d-analise-3d-visibilidade).
   Módulos ES sem build; o cache é resolvido por no-store no nginx: NUNCA ?v= nos imports (duas URLs do
   mesmo módulo = duas instâncias, app morre — regra da casa).
   Gera nesta página uma grade de elevação de exemplo (determinística) e roda as quatro análises do
   /api/analise3d sobre ela: linha de visada, bacia visual (viewshed via gdal_viewshed), perfil de
   elevação e sombra projetada. O terreno vai INLINE no corpo do pedido (app/analise3d/terreno.py);
   o resultado viewshed chega como GeoTIFF base64 mais um PNG pintado sobre o relevo sombreado. */
import * as api from '../base/api.js';
import '../base/componentes.js';
import { carregar as carregarIdioma } from '../base/i18n.js';
import { montarLayout, pronto } from '../base/layout.js';
import { h, limpar } from '../base/dom.js';
import { exigirSessao } from '../auth/sessao.js';

// --- terreno de exemplo: 60×60 células de 20 m (1,2 km), SRID 31983 (SIRGAS 2000 UTM 23S).
// Morro central (cume ~180 m sobre a base 20 m) e vale raso a oeste; determinístico, sem aleatório.
const SRID = 31983;
const N = 60;
const CELULA = 20.0;
const X0 = 220000.0;
const Y0 = 7450000.0;

function alturaExemplo(i, j) {
  // i = linha (0 = norte), j = coluna; coordenadas locais em metros
  const x = j * CELULA;
  const y = i * CELULA;
  const xc = x - 700;
  const yc = y - 620;
  const raio = Math.hypot(xc, yc);
  const morro = 180 * Math.exp(-(raio * raio) / (2 * 160 * 160));
  const vale = -12 * Math.exp(-Math.pow((x - 150) / 220, 2));
  return Math.round((20 + morro + vale) * 10) / 10;
}

function terrenoExemplo() {
  const alturas = [];
  for (let i = 0; i < N; i++) {
    const linha = [];
    for (let j = 0; j < N; j++) linha.push(alturaExemplo(i, j));
    alturas.push(linha);
  }
  return { srid: SRID, x0: X0, y0: Y0, celula_m: CELULA, alturas };
}

// observador na borda oeste, alvo na borda leste, os dois atravessando o morro
const OBS = [X0 + 2 * CELULA, Y0 + 30 * CELULA];
const ALVO = [X0 + 57 * CELULA, Y0 + 30 * CELULA];
// sólido da sombra: prisma no sopé do morro (polígono quadrado de 40 m de lado)
const POLIGONO_SOLIDO = {
  type: 'Polygon',
  coordinates: [[
    [X0 + 20 * CELULA, Y0 + 28 * CELULA],
    [X0 + 22 * CELULA, Y0 + 28 * CELULA],
    [X0 + 22 * CELULA, Y0 + 30 * CELULA],
    [X0 + 20 * CELULA, Y0 + 30 * CELULA],
    [X0 + 20 * CELULA, Y0 + 28 * CELULA],
  ]],
};

function porId(id) {
  const n = document.getElementById(id);
  if (!n) throw new Error(`elemento #${id} ausente na página`);
  return n;
}

function aviso(id, texto, tipo = 'erro') {
  const n = porId(id);
  if (texto) n.mostrar(texto, tipo);
  else n.limpar();
}

function linhaProcedencia(p) {
  const partes = [`ferramenta: ${p.ferramenta}`];
  if (p.versao_gdal) partes.push(`GDAL ${p.versao_gdal}`);
  if (p.sha256_terreno) partes.push(`sha256 do terreno: ${String(p.sha256_terreno).slice(0, 12)}…`);
  return h('p', { class: 'ajuda' }, partes.join(' · '));
}

function mostrar(analise, titulo, ...filhos) {
  porId('saida-cartao').hidden = false;
  porId('saida-titulo').textContent = titulo;
  const saida = porId('saida');
  limpar(saida);
  saida.append(...filhos);
  saida.dataset.analise = analise;
}

async function rodarVisada() {
  aviso('saida-aviso', '');
  const r = await api.enviar('/api/analise3d/visada', {
    terreno: terrenoExemplo(),
    observador: OBS,
    alvo: ALVO,
    altura_observador_m: 2,
    altura_alvo_m: 0,
  });
  if (r.status !== 200) { aviso('saida-aviso', `linha de visada falhou: ${api.mensagemDe(r)}`); return; }
  const d = r.json;
  const veredito = d.visivel
    ? `visível: o alvo é visto do observador a ${d.distancia_m.toFixed(0)} m`
    : `obstruído: o terreno cobre a reta a ${d.distancia_m.toFixed(0)} m do observador`;
  const ob = d.ponto_de_obstrucao;
  const detalhe = ob
    ? `ponto de obstrução em (${ob.x.toFixed(0)}, ${ob.y.toFixed(0)}), terreno em ${ob.z_terreno_m.toFixed(1)} m contra a reta em ${ob.z_linha_m.toFixed(1)} m`
    : 'sem ponto de obstrução';
  mostrar('visada', 'linha de visada',
    h('p', {}, `${veredito}. ${detalhe}. ${d.amostras_n} amostras com passo de ${d.passo_m.toFixed(1)} m.`),
    perfilSvg(d.amostras.map((a) => [a.d_m, a.z_terreno_m]), d.amostras.map((a) => [a.d_m, a.z_linha_m])),
    linhaProcedencia(d.procedencia));
}

function perfilSvg(serie1, serie2) {
  const w = 720; const hgt = 180;
  const xs = serie1.map((p) => p[0]).concat(serie2 ? serie2.map((p) => p[0]) : []);
  const ys = serie1.map((p) => p[1]).concat(serie2 ? serie2.map((p) => p[1]) : []);
  const xmin = Math.min(...xs); const xmax = Math.max(...xs);
  const ymin = Math.min(...ys); const ymax = Math.max(...ys);
  const px = (v) => 40 + ((v - xmin) / (xmax - xmin || 1)) * (w - 60);
  const py = (v) => hgt - 20 - ((v - ymin) / (ymax - ymin || 1)) * (hgt - 40);
  const pts = (serie) => serie.map((p) => `${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join(' ');
  return h('svg', { viewBox: `0 0 ${w} ${hgt}`, width: '100%', role: 'img',
    'aria-label': 'perfil do terreno e reta de visada' },
    h('polyline', { points: pts(serie1), fill: 'none', stroke: '#5a7d4f', 'stroke-width': 2 }),
    serie2 ? h('polyline', { points: pts(serie2), fill: 'none', stroke: '#a04b2a',
      'stroke-width': 1.5, 'stroke-dasharray': '5 4' }) : null);
}

async function rodarViewshed() {
  aviso('saida-aviso', '');
  const r = await api.enviar('/api/analise3d/viewshed', {
    terreno: terrenoExemplo(),
    observador: OBS,
    altura_observador_m: 2,
    altura_alvo_m: 0,
    distancia_max_m: 30000,
  });
  if (r.status !== 200) { aviso('saida-aviso', `bacia visual falhou: ${api.mensagemDe(r)}`); return; }
  const d = r.json;
  const texto = `bacia visual do observador: ${d.celulas_visiveis} células visíveis, ` +
    `${d.celulas_invisiveis} invisíveis, raster ${d.dimensoes.colunas}×${d.dimensoes.linhas} ` +
    `(modo ${d.modo}), executado pelo binário ${d.ferramenta}.`;
  const moldura = h('div', { style: 'position:relative;max-width:520px' });
  const base = h('img', { alt: 'relevo sombreado do terreno', src: `data:image/png;base64,${d.png_relevo_base64}`,
    style: 'display:block;width:100%;image-rendering:pixelated' });
  const porCima = h('img', { alt: 'células visíveis sobre o relevo', src: `data:image/png;base64,${d.png_viewshed_base64}`,
    style: 'position:absolute;inset:0;width:100%;image-rendering:pixelated' });
  moldura.append(base, porCima);
  mostrar('viewshed', 'bacia visual (viewshed)',
    h('p', {}, texto),
    moldura,
    h('p', { class: 'ajuda' }, `sha256 do raster de saída: ${String(d.sha256_viewshed_geotiff).slice(0, 16)}…`),
    linhaProcedencia(d.procedencia));
}

async function rodarPerfil() {
  aviso('saida-aviso', '');
  const r = await api.enviar('/api/analise3d/perfil', {
    terreno: terrenoExemplo(),
    ponto_a: [X0 + 2 * CELULA, Y0 + 30 * CELULA],
    ponto_b: [X0 + 57 * CELULA, Y0 + 30 * CELULA],
    n_amostras: 200,
  });
  if (r.status !== 200) { aviso('saida-aviso', `perfil falhou: ${api.mensagemDe(r)}`); return; }
  const d = r.json;
  const e = d.estatisticas;
  mostrar('perfil', 'perfil de elevação',
    h('p', {}, `linha de ${(d.distancia_m / 1000).toFixed(2)} km com ${d.amostras.length} amostras: ganho de ` +
      `${e.ganho_m.toFixed(0)} m, perda de ${e.perda_m.toFixed(0)} m, declividade máxima ` +
      `${e.declividade_max_graus.toFixed(1)}° (${e.declividade_max_pct.toFixed(1)} %) a ` +
      `${e.declividade_max_distancia_m.toFixed(0)} m do ponto A; cota entre ${e.z_min_m.toFixed(1)} m e ${e.z_max_m.toFixed(1)} m.`),
    perfilSvg(d.amostras.map((a) => [a.d_m, a.z_terreno_m])),
    linhaProcedencia(d.procedencia));
}

async function rodarSombra() {
  aviso('saida-aviso', '');
  const r = await api.enviar('/api/analise3d/sombra', {
    srid: SRID,
    data_hora: '2026-12-21T14:00:00-03:00',
    solidos: [{ poligono: POLIGONO_SOLIDO, altura_m: 50 }],
  });
  if (r.status !== 200) { aviso('saida-aviso', `sombra falhou: ${api.mensagemDe(r)}`); return; }
  const d = r.json;
  const so = d.solidos[0];
  const xs = []; const ys = [];
  for (const anel of so.sombra_geojson.coordinates) for (const [x, y] of anel) { xs.push(x); ys.push(y); }
  const xmin = Math.min(...xs); const xmax = Math.max(...xs);
  const ymin = Math.min(...ys); const ymax = Math.max(...ys);
  const w = 420; const hgt = 300; const borda = 30;
  const esc = Math.min((w - 2 * borda) / (xmax - xmin || 1), (hgt - 2 * borda) / (ymax - ymin || 1));
  const px = (v) => borda + (v - xmin) * esc;
  const py = (v) => hgt - borda - (v - ymin) * esc;
  const anel = so.sombra_geojson.coordinates[0].map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join(' ');
  mostrar('sombra', 'sombra projetada',
    h('p', {}, `prisma de ${so.altura_m} m em 21/12 às 14h (fuso −03): Sol a ${so.elevacao_sol_graus.toFixed(1)}° de ` +
      `elevação e ${so.azimute_sol_graus.toFixed(1)}° de azimute; sombra de ${so.comprimento_sombra_m.toFixed(1)} m ` +
      `na direção ${so.direcao_sombra_graus.toFixed(1)}°.`),
    h('svg', { viewBox: `0 0 ${w} ${hgt}`, width: '100%', role: 'img', 'aria-label': 'polígono da sombra' },
      h('polygon', { points: anel, fill: 'rgba(60,60,80,0.55)', stroke: '#333' })),
    linhaProcedencia(d.procedencia));
}

function ligar() {
  porId('bt-visada').addEventListener('click', () => rodarVisada().catch((e) => aviso('saida-aviso', String(e.message || e))));
  porId('bt-viewshed').addEventListener('click', () => rodarViewshed().catch((e) => aviso('saida-aviso', String(e.message || e))));
  porId('bt-perfil').addEventListener('click', () => rodarPerfil().catch((e) => aviso('saida-aviso', String(e.message || e))));
  porId('bt-sombra').addEventListener('click', () => rodarSombra().catch((e) => aviso('saida-aviso', String(e.message || e))));
  const t = terrenoExemplo();
  porId('terreno-resumo').textContent =
    `grade ${t.alturas.length}×${t.alturas[0].length}, célula de ${CELULA} m`;
}

async function principal() {
  const usuario = await exigirSessao();
  if (!usuario) return false;
  montarLayout({ usuario });
  ligar();
  return true;
}

await carregarIdioma();
let ok = false;
try {
  ok = await principal();
} catch (e) {
  if (!(e && e.status === 401)) aviso('aviso', `não foi possível carregar a tela (${(e && e.status) || 'rede'}): ${(e && e.message) || e}`);
} finally {
  if (ok) pronto();
}
