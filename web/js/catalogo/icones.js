/* plat · catálogo — ícones SVG por nome (tipo_item.icone) criados por DOM (sem HTML em string). Traço de 1,6 px,
   caixa 24×24, cor corrente; aria-hidden porque o rótulo textual vai ao lado. Nome desconhecido = ícone genérico. */
const NS = 'http://www.w3.org/2000/svg';

/* cada ícone: lista de elementos [tag, atributos] */
const ICONES = {
  camada: [['polygon', { points: '12 3 21 8 12 13 3 8' }], ['polyline', { points: '3 13 12 18 21 13' }]],
  camada_vetorial: [['polygon', { points: '12 3 21 8 12 13 3 8' }], ['polyline', { points: '3 13 12 18 21 13' }]],
  vista: [['polygon', { points: '12 4 21 9 12 14 3 9' }], ['circle', { cx: 18, cy: 17, r: 3 }], ['line', { x1: 20.5, y1: 19.5, x2: 23, y2: 22 }]],
  raster: [['rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }], ['line', { x1: 3, y1: 9, x2: 21, y2: 9 }], ['line', { x1: 3, y1: 15, x2: 21, y2: 15 }], ['line', { x1: 9, y1: 3, x2: 9, y2: 21 }], ['line', { x1: 15, y1: 3, x2: 15, y2: 21 }]],
  mapa: [['polygon', { points: '3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21' }], ['line', { x1: 9, y1: 3, x2: 9, y2: 18 }], ['line', { x1: 15, y1: 6, x2: 15, y2: 21 }]],
  cena: [['path', { d: 'M3 17 L12 7 L21 17 Z' }], ['circle', { cx: 18, cy: 6, r: 2 }]],
  estilo: [['circle', { cx: 12, cy: 12, r: 9 }], ['circle', { cx: 8, cy: 10, r: 1.5 }], ['circle', { cx: 12, cy: 7, r: 1.5 }], ['circle', { cx: 16, cy: 10, r: 1.5 }]],
  app: [['rect', { x: 4, y: 3, width: 16, height: 18, rx: 2 }], ['line', { x1: 9, y1: 18, x2: 15, y2: 18 }]],
  painel: [['rect', { x: 3, y: 3, width: 8, height: 8 }], ['rect', { x: 13, y: 3, width: 8, height: 5 }], ['rect', { x: 13, y: 10, width: 8, height: 11 }], ['rect', { x: 3, y: 13, width: 8, height: 8 }]],
  formulario: [['rect', { x: 4, y: 3, width: 16, height: 18, rx: 2 }], ['line', { x1: 8, y1: 8, x2: 16, y2: 8 }], ['line', { x1: 8, y1: 12, x2: 16, y2: 12 }], ['line', { x1: 8, y1: 16, x2: 12, y2: 16 }]],
  fluxo: [['circle', { cx: 5, cy: 6, r: 2.5 }], ['circle', { cx: 19, cy: 6, r: 2.5 }], ['circle', { cx: 12, cy: 18, r: 2.5 }], ['line', { x1: 7, y1: 7.5, x2: 10.5, y2: 16 }], ['line', { x1: 17, y1: 7.5, x2: 13.5, y2: 16 }]],
  rede: [['circle', { cx: 5, cy: 12, r: 2.5 }], ['circle', { cx: 19, cy: 5, r: 2.5 }], ['circle', { cx: 19, cy: 19, r: 2.5 }], ['line', { x1: 7.5, y1: 11, x2: 16.5, y2: 6 }], ['line', { x1: 7.5, y1: 13, x2: 16.5, y2: 18 }]],
  conexao: [['path', { d: 'M9 15 L5 19 M15 9 L19 5' }], ['path', { d: 'M8 8 L12 4 L20 12 L16 16 Z' }]],
  arquivo: [['path', { d: 'M6 3 H14 L19 8 V21 H6 Z' }], ['polyline', { points: '14 3 14 8 19 8' }]],
  ferramenta: [['path', { d: 'M14 4 A5 5 0 0 0 9 10 L3 16 L6 19 L12 13 A5 5 0 0 0 19 8 L16 11 L13 8 Z' }]],
  documento: [['path', { d: 'M6 3 H14 L19 8 V21 H6 Z' }], ['line', { x1: 9, y1: 12, x2: 16, y2: 12 }], ['line', { x1: 9, y1: 16, x2: 16, y2: 16 }]],
  modelo_amc: [['rect', { x: 3, y: 13, width: 4, height: 8 }], ['rect', { x: 10, y: 8, width: 4, height: 13 }], ['rect', { x: 17, y: 4, width: 4, height: 17 }]],
  pasta: [['path', { d: 'M3 6 H9 L11 8 H21 V19 H3 Z' }]],
  pasta_aberta: [['path', { d: 'M3 6 H9 L11 8 H20 V11 H6 L3 19 Z' }], ['path', { d: 'M6 11 H23 L20 19 H3' }]],
  estrela: [['polygon', { points: '12 3 14.8 9 21 9.6 16.3 13.8 17.7 20 12 16.8 6.3 20 7.7 13.8 3 9.6 9.2 9' }]],
  lixeira: [['polyline', { points: '4 7 20 7' }], ['path', { d: 'M6 7 L7 21 H17 L18 7' }], ['path', { d: 'M9 7 V4 H15 V7' }]],
  cadeado: [['rect', { x: 5, y: 11, width: 14, height: 10, rx: 2 }], ['path', { d: 'M8 11 V7 A4 4 0 0 1 16 7 V11' }]],
  grade: [['rect', { x: 3, y: 3, width: 7, height: 7 }], ['rect', { x: 14, y: 3, width: 7, height: 7 }], ['rect', { x: 3, y: 14, width: 7, height: 7 }], ['rect', { x: 14, y: 14, width: 7, height: 7 }]],
  lista: [['line', { x1: 4, y1: 6, x2: 20, y2: 6 }], ['line', { x1: 4, y1: 12, x2: 20, y2: 12 }], ['line', { x1: 4, y1: 18, x2: 20, y2: 18 }]],
  tabela: [['rect', { x: 3, y: 4, width: 18, height: 16 }], ['line', { x1: 3, y1: 10, x2: 21, y2: 10 }], ['line', { x1: 3, y1: 15, x2: 21, y2: 15 }], ['line', { x1: 10, y1: 4, x2: 10, y2: 20 }]],
  generico: [['rect', { x: 4, y: 4, width: 16, height: 16, rx: 3 }]],
};

export function icone(nome, { tamanho = 20, classe = '' } = {}) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(tamanho));
  svg.setAttribute('height', String(tamanho));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', `icone ${classe}`.trim());
  for (const [tag, atributos] of ICONES[nome] || ICONES.generico) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(atributos)) el.setAttribute(k, String(v));
    svg.append(el);
  }
  return svg;
}

export function temIcone(nome) { return Object.prototype.hasOwnProperty.call(ICONES, nome); }

/* ícone do tipo: o nome vem de tipo_item.icone; se não existir aqui, a família; senão o genérico */
export function iconeDoTipo(tipo, opcoes) {
  if (!tipo) return icone('generico', opcoes);
  if (temIcone(tipo.icone)) return icone(tipo.icone, opcoes);
  if (temIcone(tipo.nome)) return icone(tipo.nome, opcoes);
  if (temIcone(tipo.familia)) return icone(tipo.familia, opcoes);
  return icone('generico', opcoes);
}
