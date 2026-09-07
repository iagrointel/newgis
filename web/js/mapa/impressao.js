/* plat · mapa — impressão em PNG e PDF (item L2-01-mapa-web).

   O portão do item pede "PNG e PDF com escala e norte". A imagem sai do MESMO canvas que o usuário vê
   (WYSIWYG), o que só funciona com `preserveDrawingBuffer: true` no MapLibre — sem isso o navegador
   limpa o buffer depois de compor cada quadro e a leitura devolve tela preta (armadilha já paga na
   casa). Sobre a imagem do mapa, este módulo compõe uma faixa com: título, escala numérica (1:N)
   calculada da latitude do centro, barra de escala com o comprimento real do trecho, seta de norte e
   a atribuição das fontes.

   A escala numérica sai da resolução do Mercator na latitude do centro:
       metros por pixel = 156543,03392 * cos(latitude) / 2^zoom / (razão de pixel do dispositivo)
   e 1:N com N = metros por pixel / (0,00028 m), o "pixel padrão OGC" de 0,28 mm — a mesma constante
   que WMS/WMTS usam para dizer escala. */
import { paginaPdf, A4_PAISAGEM } from './pdf.js';

const PIXEL_OGC_M = 0.00028;
export const CIRCUNFERENCIA = 156543.03392;

export function metrosPorPixel(latitude, zoom) {
  return (CIRCUNFERENCIA * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

export function escalaNumerica(latitude, zoom) {
  return Math.round(metrosPorPixel(latitude, zoom) / PIXEL_OGC_M);
}

export function barraDeEscala(latitude, zoom, larguraMaxPx = 180) {
  /* escolhe 1, 2 ou 5 vezes uma potência de dez que caiba na largura máxima */
  const mpp = metrosPorPixel(latitude, zoom);
  const metrosMax = mpp * larguraMaxPx;
  const potencia = 10 ** Math.floor(Math.log10(metrosMax));
  let metros = potencia;
  for (const mult of [5, 2, 1]) {
    if (potencia * mult <= metrosMax) { metros = potencia * mult; break; }
  }
  const rotulo = metros >= 1000 ? `${(metros / 1000).toLocaleString('pt-BR')} km` : `${metros} m`;
  return { metros, pixels: metros / mpp, rotulo };
}

function desenharSetaNorte(ctx, x, y, tamanho, cor) {
  ctx.save();
  ctx.fillStyle = cor;
  ctx.strokeStyle = cor;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, y - tamanho);
  ctx.lineTo(x + tamanho * 0.42, y + tamanho * 0.6);
  ctx.lineTo(x, y + tamanho * 0.28);
  ctx.lineTo(x - tamanho * 0.42, y + tamanho * 0.6);
  ctx.closePath();
  ctx.fill();
  ctx.font = `bold ${Math.round(tamanho * 0.7)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText('N', x, y + tamanho * 1.35);
  ctx.restore();
}

/* compor(map, {titulo}) -> {canvas, escala, barra} : o canvas do mapa mais a faixa de informação */
export function compor(map, { titulo = 'Mapa', atribuicao = '' } = {}) {
/* Legenda desenhada NA IMAGEM (item L2-01-l): as entradas vêm prontas de `ficha.legenda`, geradas pelo
   servidor da mesma lista de classes que gerou o estilo (app/mapa/simbologia.py). O canvas não inventa
   cor nenhuma — se inventasse, a legenda impressa e o mapa impresso poderiam discordar. */
export function alturaDaLegenda(legenda, linhaPx = 15) {
  if (!legenda || !legenda.length) return 0;
  return 22 + legenda.length * linhaPx;   // título + uma linha por classe
}

function desenharLegenda(ctx, legenda, x, y, largura) {
  if (!legenda || !legenda.length) return;
  const linha = 15;
  ctx.save();
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.strokeStyle = '#b9c2c4';
  ctx.lineWidth = 1;
  const alturaCaixa = alturaDaLegenda(legenda, linha);
  ctx.fillRect(x, y, largura, alturaCaixa);
  ctx.strokeRect(x + 0.5, y + 0.5, largura - 1, alturaCaixa - 1);
  ctx.fillStyle = '#0f1416';
  ctx.font = 'bold 11px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('Legenda', x + 8, y + 15);
  ctx.font = '10px sans-serif';
  legenda.forEach((entrada, i) => {
    const linhaY = y + 22 + i * linha;
    ctx.fillStyle = entrada.cor;
    if (entrada.forma === 'ponto') {
      ctx.beginPath();
      ctx.arc(x + 13, linhaY + 4, 4, 0, Math.PI * 2);
      ctx.fill();
    } else if (entrada.forma === 'linha') {
      ctx.fillRect(x + 8, linhaY + 3, 12, 2.5);
    } else {
      ctx.fillRect(x + 8, linhaY, 12, 9);
    }
    ctx.fillStyle = '#26302f';
    ctx.fillText(String(entrada.rotulo).slice(0, 34), x + 26, linhaY + 8);
  });
  ctx.restore();
}

/* compor(map, {titulo, legenda}) -> {canvas, escala, barra} : o canvas do mapa mais a faixa de
   informação e, quando houver classes, a legenda sobre o canto inferior esquerdo do mapa. */
export function compor(map, { titulo = 'Mapa', atribuicao = '', legenda = [] } = {}) {
  const origem = map.getCanvas();
  const centro = map.getCenter();
  const zoom = map.getZoom();
  const razao = window.devicePixelRatio || 1;
  const largura = origem.width;
  const faixa = Math.round(76 * razao);  // 4 linhas de texto + a barra de escala e a seta de norte
  const destino = document.createElement('canvas');
  destino.width = largura;
  destino.height = origem.height + faixa;
  const ctx = destino.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, destino.width, destino.height);
  ctx.drawImage(origem, 0, 0);

  const escala = escalaNumerica(centro.lat, zoom);
  const barra = barraDeEscala(centro.lat, zoom, 180);
  const y0 = origem.height;
  ctx.save();
  ctx.scale(razao, razao);
  const l = largura / razao;
  const yb = y0 / razao;
  ctx.fillStyle = '#0f1416';
  ctx.font = 'bold 13px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(titulo, 12, yb + 18);
  ctx.font = '11px sans-serif';
  ctx.fillStyle = '#414a4d';
  ctx.fillText(`Escala aproximada 1:${escala.toLocaleString('pt-BR')}`, 12, yb + 34);
  ctx.fillText(`Centro ${centro.lat.toFixed(5)}, ${centro.lng.toFixed(5)} · WGS 84 (EPSG:4326) · z${zoom.toFixed(1)}`,
    12, yb + 49);
  // barra de escala
  const bx = l - 250;
  const by = yb + 44;
  ctx.strokeStyle = '#0f1416';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(bx, by - 5); ctx.lineTo(bx, by); ctx.lineTo(bx + barra.pixels, by);
  ctx.lineTo(bx + barra.pixels, by - 5);
  ctx.stroke();
  ctx.fillStyle = '#0f1416';
  ctx.font = '11px sans-serif';
  ctx.fillText(barra.rotulo, bx, by + 14);
  if (atribuicao) {
    // à esquerda, numa linha só sua: à direita ela colidia com o rótulo da barra de escala (medido na
    // captura de impressão do e2e, tests/e2e/capturas/L2-01-mapa-web_impressao.png)
    ctx.fillStyle = '#5b6467';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(atribuicao.slice(0, 140), 12, yb + 65);
  }
  ctx.textAlign = 'left';
  desenharSetaNorte(ctx, l - 34, yb + 28, 13, '#0f1416');
  ctx.restore();
  return { canvas: destino, escala, barra, centro, zoom };
  const alturaLegenda = alturaDaLegenda(legenda);
  if (alturaLegenda) desenharLegenda(ctx, legenda, 12, yb - alturaLegenda - 12, 168);
  ctx.restore();
  return { canvas: destino, escala, barra, centro, zoom, legenda: legenda ? legenda.length : 0 };
}

function baixar(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export async function paraPng(map, opcoes = {}) {
  const { canvas, escala } = compor(map, opcoes);
  const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
  baixar(blob, opcoes.nome || 'mapa.png');
  return { bytes: blob.size, escala, largura: canvas.width, altura: canvas.height };
/* PNG em 2x: o canvas da tela tem a resolução da tela, e ampliá-lo só interpola pixel. Para dobrar de
   verdade, um mapa TEMPORÁRIO é montado fora da tela com o dobro da largura e da altura, o mesmo estilo
   e a mesma câmera, e é ELE que é lido depois do 'idle'. Custa uma renderização a mais e entrega o
   dobro de detalhe de verdade — que é o que "2x" promete. */
async function mapaEmDobro(map) {
  const maplibregl = window.maplibregl;
  const origem = map.getCanvas();
  const caixa = document.createElement('div');
  caixa.style.cssText = `position:absolute;left:-10000px;top:0;width:${origem.clientWidth * 2}px;`
    + `height:${origem.clientHeight * 2}px`;
  document.body.append(caixa);
  const dobro = new maplibregl.Map({
    container: caixa,
    style: map.getStyle(),
    center: map.getCenter(),
    zoom: map.getZoom() + 1,   // o dobro de pixel por grau é um nível de zoom a mais
    bearing: map.getBearing(),
    pitch: map.getPitch(),
    attributionControl: false,
    interactive: false,
    preserveDrawingBuffer: true,
  });
  await new Promise((r) => dobro.once('idle', r));
  return { dobro, remover: () => { dobro.remove(); caixa.remove(); } };
}

export async function paraPng(map, opcoes = {}) {
  let alvo = map;
  let fechar = null;
  if (opcoes.escalaSaida === 2) {
    const d = await mapaEmDobro(map);
    alvo = d.dobro;
    fechar = d.remover;
  }
  try {
    const { canvas, escala, legenda } = compor(alvo, opcoes);
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
    baixar(blob, opcoes.nome || 'mapa.png');
    return { bytes: blob.size, escala, largura: canvas.width, altura: canvas.height, legenda };
  } finally {
    if (fechar) fechar();
  }
}

export async function paraPdf(map, opcoes = {}) {
  const { canvas, escala, barra, centro, zoom } = compor(map, opcoes);
  const blobJpeg = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.92));
  const jpeg = new Uint8Array(await blobJpeg.arrayBuffer());
  const pdf = paginaPdf({
    jpeg,
    largura: canvas.width,
    altura: canvas.height,
    tamanhoPagina: A4_PAISAGEM,
    textos: [
      { texto: `${opcoes.titulo || 'Mapa'} — escala aproximada 1:${escala.toLocaleString('pt-BR')}`,
        x: 24, y: 30, tamanho: 10 },
      { texto: `Barra de escala ${barra.rotulo} · norte no topo · centro ${centro.lat.toFixed(5)}, `
        + `${centro.lng.toFixed(5)} (EPSG:4326) · z${zoom.toFixed(1)}`, x: 24, y: 16, tamanho: 8 },
    ],
  });
  baixar(pdf, opcoes.nome || 'mapa.pdf');
  return { bytes: pdf.size, escala };
}
