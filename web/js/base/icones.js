/* plat — FAMÍLIA ÚNICA DE ÍCONES (item L0-14-identidade-visual). Desenhados aqui, em SVG por DOM (sem HTML em
   string), caixa 24×24, traço de 1,6 px (--i-traco-icone), pontas e junções redondas, cor corrente. Todo ícone
   do produto sai desta lista: nenhum emoji, nenhum glifo de texto (✓ ✗ ○ ● ⋯ ▾ ↑ ↓ ×) fora daqui —
   tests/unit/test_estilo_tokens.py varre web/ e reprova. aria-hidden porque o rótulo textual vai ao lado;
   quando o ícone está sozinho num botão, o botão leva aria-label. Nome desconhecido = ícone genérico. */
const NS = 'http://www.w3.org/2000/svg';

/* cada ícone: lista de elementos [tag, atributos] */
export const ICONES = {
  /* --- tipos de item do catálogo --- */
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

  /* --- interface: navegação e ação --- */
  inicio: [['path', { d: 'M4 11 L12 4 L20 11 V20 H14 V14 H10 V20 H4 Z' }]],
  usuario: [['circle', { cx: 12, cy: 8, r: 4 }], ['path', { d: 'M4 21 A8 7 0 0 1 20 21' }]],
  usuarios: [['circle', { cx: 9, cy: 8, r: 3.5 }], ['path', { d: 'M2 20 A7 6 0 0 1 16 20' }], ['circle', { cx: 17, cy: 9, r: 2.5 }], ['path', { d: 'M17 14 A5 5 0 0 1 22 20' }]],
  grupo: [['circle', { cx: 7, cy: 9, r: 3 }], ['circle', { cx: 17, cy: 9, r: 3 }], ['path', { d: 'M2 20 A5 5 0 0 1 12 20 A5 5 0 0 1 22 20' }]],
  papel: [['path', { d: 'M12 3 L20 6 V12 C20 17 16 20 12 21 C8 20 4 17 4 12 V6 Z' }], ['polyline', { points: '9 12 11 14 15 10' }]],
  chave: [['circle', { cx: 8, cy: 14, r: 4 }], ['path', { d: 'M11 11 L20 2 M16 6 L19 9 M13 9 L16 12' }]],
  log: [['path', { d: 'M5 3 H19 V21 H5 Z' }], ['line', { x1: 8, y1: 8, x2: 16, y2: 8 }], ['line', { x1: 8, y1: 12, x2: 16, y2: 12 }], ['line', { x1: 8, y1: 16, x2: 13, y2: 16 }]],
  organizacao: [['rect', { x: 3, y: 8, width: 18, height: 13 }], ['path', { d: 'M8 8 V4 H16 V8' }], ['line', { x1: 12, y1: 12, x2: 12, y2: 17 }], ['line', { x1: 9.5, y1: 14.5, x2: 14.5, y2: 14.5 }]],
  tarefas: [['polyline', { points: '4 7 6 9 9 5' }], ['line', { x1: 12, y1: 7, x2: 20, y2: 7 }], ['polyline', { points: '4 14 6 16 9 12' }], ['line', { x1: 12, y1: 14, x2: 20, y2: 14 }], ['line', { x1: 12, y1: 20, x2: 20, y2: 20 }]],
  enviar: [['path', { d: 'M12 17 V5' }], ['polyline', { points: '7 10 12 5 17 10' }], ['path', { d: 'M4 19 H20' }]],
  baixar: [['path', { d: 'M12 5 V17' }], ['polyline', { points: '7 12 12 17 17 12' }], ['path', { d: 'M4 20 H20' }]],
  sair: [['path', { d: 'M10 4 H5 V20 H10' }], ['path', { d: 'M13 12 H21' }], ['polyline', { points: '17 8 21 12 17 16' }]],
  entrar: [['path', { d: 'M14 4 H19 V20 H14' }], ['path', { d: 'M3 12 H11' }], ['polyline', { points: '7 8 11 12 7 16' }]],
  mais: [['line', { x1: 12, y1: 5, x2: 12, y2: 19 }], ['line', { x1: 5, y1: 12, x2: 19, y2: 12 }]],
  menos: [['line', { x1: 5, y1: 12, x2: 19, y2: 12 }]],
  fechar: [['line', { x1: 6, y1: 6, x2: 18, y2: 18 }], ['line', { x1: 18, y1: 6, x2: 6, y2: 18 }]],
  buscar: [['circle', { cx: 10.5, cy: 10.5, r: 6.5 }], ['line', { x1: 15.5, y1: 15.5, x2: 21, y2: 21 }]],
  filtro: [['path', { d: 'M3 5 H21 L14 13 V20 L10 18 V13 Z' }]],
  editar: [['path', { d: 'M4 20 L8 19 L19 8 L16 5 L5 16 Z' }], ['line', { x1: 14, y1: 7, x2: 17, y2: 10 }]],
  copiar: [['rect', { x: 9, y: 9, width: 11, height: 11, rx: 1.5 }], ['path', { d: 'M5 15 V5 H15' }]],
  atualizar: [['path', { d: 'M20 12 A8 8 0 1 1 17.6 6.3' }], ['polyline', { points: '18 2 18 7 13 7' }]],
  reticencias: [['circle', { cx: 6, cy: 12, r: 1.4, fill: 'currentColor' }], ['circle', { cx: 12, cy: 12, r: 1.4, fill: 'currentColor' }], ['circle', { cx: 18, cy: 12, r: 1.4, fill: 'currentColor' }]],
  menu: [['line', { x1: 4, y1: 7, x2: 20, y2: 7 }], ['line', { x1: 4, y1: 12, x2: 20, y2: 12 }], ['line', { x1: 4, y1: 17, x2: 20, y2: 17 }]],
  seta_esq: [['line', { x1: 20, y1: 12, x2: 4, y2: 12 }], ['polyline', { points: '10 6 4 12 10 18' }]],
  seta_dir: [['line', { x1: 4, y1: 12, x2: 20, y2: 12 }], ['polyline', { points: '14 6 20 12 14 18' }]],
  seta_cima: [['line', { x1: 12, y1: 20, x2: 12, y2: 4 }], ['polyline', { points: '6 10 12 4 18 10' }]],
  seta_baixo: [['line', { x1: 12, y1: 4, x2: 12, y2: 20 }], ['polyline', { points: '6 14 12 20 18 14' }]],
  chevron_esq: [['polyline', { points: '15 5 8 12 15 19' }]],
  chevron_dir: [['polyline', { points: '9 5 16 12 9 19' }]],
  chevron_cima: [['polyline', { points: '5 15 12 8 19 15' }]],
  chevron_baixo: [['polyline', { points: '5 9 12 16 19 9' }]],
  ordenar: [['polyline', { points: '8 9 12 5 16 9' }], ['polyline', { points: '8 15 12 19 16 15' }]],
  ordenar_asc: [['polyline', { points: '8 10 12 6 16 10' }], ['line', { x1: 12, y1: 6, x2: 12, y2: 19 }]],
  ordenar_desc: [['polyline', { points: '8 14 12 18 16 14' }], ['line', { x1: 12, y1: 5, x2: 12, y2: 18 }]],
  olho: [['path', { d: 'M2 12 C5 6 9 4 12 4 C15 4 19 6 22 12 C19 18 15 20 12 20 C9 20 5 18 2 12 Z' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  olho_fechado: [['path', { d: 'M2 12 C5 6 9 4 12 4 C15 4 19 6 22 12 C19 18 15 20 12 20 C9 20 5 18 2 12 Z' }], ['line', { x1: 4, y1: 4, x2: 20, y2: 20 }]],
  link: [['path', { d: 'M10 14 A4 4 0 0 0 15.6 14 L18 11.6 A4 4 0 0 0 12.4 6 L11 7.4' }], ['path', { d: 'M14 10 A4 4 0 0 0 8.4 10 L6 12.4 A4 4 0 0 0 11.6 18 L13 16.6' }]],
  compartilhar: [['circle', { cx: 18, cy: 5, r: 2.5 }], ['circle', { cx: 6, cy: 12, r: 2.5 }], ['circle', { cx: 18, cy: 19, r: 2.5 }], ['line', { x1: 8.2, y1: 10.8, x2: 15.8, y2: 6.2 }], ['line', { x1: 8.2, y1: 13.2, x2: 15.8, y2: 17.8 }]],
  arrastar: [['circle', { cx: 9, cy: 6, r: 1.3, fill: 'currentColor' }], ['circle', { cx: 15, cy: 6, r: 1.3, fill: 'currentColor' }], ['circle', { cx: 9, cy: 12, r: 1.3, fill: 'currentColor' }], ['circle', { cx: 15, cy: 12, r: 1.3, fill: 'currentColor' }], ['circle', { cx: 9, cy: 18, r: 1.3, fill: 'currentColor' }], ['circle', { cx: 15, cy: 18, r: 1.3, fill: 'currentColor' }]],

  /* --- estado --- */
  ok: [['polyline', { points: '4 12.5 9.5 18 20 7' }]],
  erro: [['circle', { cx: 12, cy: 12, r: 9 }], ['line', { x1: 8.5, y1: 8.5, x2: 15.5, y2: 15.5 }], ['line', { x1: 15.5, y1: 8.5, x2: 8.5, y2: 15.5 }]],
  atencao: [['path', { d: 'M12 3 L22 20 H2 Z' }], ['line', { x1: 12, y1: 9, x2: 12, y2: 14 }], ['circle', { cx: 12, cy: 17, r: .9, fill: 'currentColor' }]],
  info: [['circle', { cx: 12, cy: 12, r: 9 }], ['line', { x1: 12, y1: 11, x2: 12, y2: 17 }], ['circle', { cx: 12, cy: 7.5, r: .9, fill: 'currentColor' }]],
  carregando: [['path', { d: 'M12 3 A9 9 0 1 1 3.8 8.5' }]],
  pendente: [['circle', { cx: 12, cy: 12, r: 8 }]],
  rodando: [['circle', { cx: 12, cy: 12, r: 8 }], ['path', { d: 'M12 6 A6 6 0 0 1 18 12' }]],
  concluido: [['circle', { cx: 12, cy: 12, r: 8 }], ['polyline', { points: '8 12.5 11 15.5 16.5 9.5' }]],
  falhou: [['circle', { cx: 12, cy: 12, r: 8 }], ['line', { x1: 9, y1: 9, x2: 15, y2: 15 }], ['line', { x1: 15, y1: 9, x2: 9, y2: 15 }]],
  cancelado: [['circle', { cx: 12, cy: 12, r: 8 }], ['line', { x1: 8, y1: 12, x2: 16, y2: 12 }]],
  vazio: [['rect', { x: 4, y: 6, width: 16, height: 13, rx: 1.5, 'stroke-dasharray': '3 2' }], ['path', { d: 'M4 11 H9 L11 13 H13 L15 11 H20' }]],
  desconhecido: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9.5 9.5 A2.5 2.5 0 1 1 12 13 V14.5' }], ['circle', { cx: 12, cy: 17.5, r: .9, fill: 'currentColor' }]],

  /* --- tema, densidade, régua --- */
  sol: [['circle', { cx: 12, cy: 12, r: 4 }], ['path', { d: 'M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M4.9 4.9 L7 7 M17 17 L19.1 19.1 M4.9 19.1 L7 17 M17 7 L19.1 4.9' }]],
  lua: [['path', { d: 'M20 14 A8 8 0 1 1 10 4 A6.5 6.5 0 0 0 20 14 Z' }]],
  sistema: [['rect', { x: 3, y: 4, width: 18, height: 12, rx: 1.5 }], ['line', { x1: 8, y1: 20, x2: 16, y2: 20 }], ['line', { x1: 12, y1: 16, x2: 12, y2: 20 }]],
  densidade: [['line', { x1: 4, y1: 6, x2: 20, y2: 6 }], ['line', { x1: 4, y1: 10, x2: 20, y2: 10 }], ['line', { x1: 4, y1: 14, x2: 20, y2: 14 }], ['line', { x1: 4, y1: 18, x2: 20, y2: 18 }]],
  regua: [['rect', { x: 2, y: 8, width: 20, height: 8 }], ['line', { x1: 6, y1: 8, x2: 6, y2: 12 }], ['line', { x1: 10, y1: 8, x2: 10, y2: 11 }], ['line', { x1: 14, y1: 8, x2: 14, y2: 12 }], ['line', { x1: 18, y1: 8, x2: 18, y2: 11 }]],
  paleta: [['path', { d: 'M12 3 A9 9 0 1 0 12 21 C14 21 14 19 13 18 C12 17 13 15 15 15 H17 A4 4 0 0 0 21 11 C21 6.5 17 3 12 3 Z' }], ['circle', { cx: 8, cy: 10, r: 1.2, fill: 'currentColor' }], ['circle', { cx: 12, cy: 7.5, r: 1.2, fill: 'currentColor' }], ['circle', { cx: 16, cy: 10, r: 1.2, fill: 'currentColor' }]],
  tipo: [['path', { d: 'M5 19 L11 5 H13 L19 19' }], ['line', { x1: 7.5, y1: 14, x2: 16.5, y2: 14 }]],
};

export function icone(nome, { tamanho = 20, classe = '', rotulo } = {}) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(tamanho));
  svg.setAttribute('height', String(tamanho));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  if (rotulo) { svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', rotulo); } else svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', `icone icone-${nome} ${classe}`.trim());
  svg.dataset.icone = nome;
  for (const [tag, atributos] of ICONES[nome] || ICONES.generico) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(atributos)) el.setAttribute(k, String(v));
    svg.append(el);
  }
  return svg;
}

export function temIcone(nome) { return Object.prototype.hasOwnProperty.call(ICONES, nome); }

export function nomesDeIcones() { return Object.keys(ICONES); }

/* ícone do tipo de item: o nome vem de tipo_item.icone; se não existir aqui, a família; senão o genérico */
export function iconeDoTipo(tipo, opcoes) {
  if (!tipo) return icone('generico', opcoes);
  if (temIcone(tipo.icone)) return icone(tipo.icone, opcoes);
  if (temIcone(tipo.nome)) return icone(tipo.nome, opcoes);
  if (temIcone(tipo.familia)) return icone(tipo.familia, opcoes);
  return icone('generico', opcoes);
}
