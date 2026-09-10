/* plat · cena — slides (vistas salvas) do documento de cena (item L2-09-b-cena-extrusao-slides).

   Um slide é o estado da cena que o leitor quer reencontrar: câmera (centro, zoom, inclinação,
   rotação), quais camadas estavam visíveis, a hora do dia e o exagero do terreno. Fica dentro do
   CORPO do documento — nenhuma tabela nova, nenhum arquivo à parte —, e a miniatura é gerada no
   navegador a partir do próprio canvas do mapa.

   Restaurar usa `jumpTo`, não `flyTo`: o slide guarda a vista, e a vista restaurada tem de ser a
   mesma até a casa decimal (o portão do item mede ±0,01°), não uma aproximação com animação. */
import { gerarUlid } from './documento.js';

export const LARGURA_MINIATURA = 240;

export function camaraDoMapa(map) {
  const c = map.getCenter();
  return {
    centro: [Number(c.lng.toFixed(6)), Number(c.lat.toFixed(6))],
    zoom: Number(map.getZoom().toFixed(4)),
    inclinacao: Number(map.getPitch().toFixed(4)),
    rotacao: Number(((((map.getBearing() % 360) + 360) % 360)).toFixed(4)),
  };
}

/* miniatura: o canvas do mapa reduzido para LARGURA_MINIATURA px de largura, em JPEG. Exige o mapa
   criado com `preserveDrawingBuffer: true` — sem isso o canvas volta em branco depois do quadro. */
export function miniaturaDoMapa(map, largura = LARGURA_MINIATURA) {
  const origem = map.getCanvas();
  if (!origem.width || !origem.height) return null;
  const escala = largura / origem.width;
  const destino = document.createElement('canvas');
  destino.width = largura;
  destino.height = Math.max(1, Math.round(origem.height * escala));
  const ctx = destino.getContext('2d');
  ctx.drawImage(origem, 0, 0, destino.width, destino.height);
  return destino.toDataURL('image/jpeg', 0.6);
}

export class Slides {
  /** `estado()` devolve {camadas_visiveis, instante, exagero} do resto da tela. */
  constructor(map, documento, estado) {
    this.map = map;
    this.documento = documento;
    this.estado = estado;
  }

  get lista() { return this.documento.corpo.slides; }

  capturar(nome) {
    const extra = this.estado();
    const slide = {
      id: gerarUlid(),
      nome: (nome || '').trim() || `vista ${this.lista.length + 1}`,
      camera: camaraDoMapa(this.map),
      camadas_visiveis: extra.camadas_visiveis,
      instante: extra.instante,
      exagero: extra.exagero,
    };
    const mini = miniaturaDoMapa(this.map);
    if (mini && mini.length <= 200000) slide.miniatura = mini;
    this.lista.push(slide);
    return slide;
  }

  remover(id) {
    const i = this.lista.findIndex((s) => s.id === id);
    if (i < 0) return false;
    this.lista.splice(i, 1);
    return true;
  }

  /** aplica o slide: câmera exata + camadas visíveis + hora + exagero (o chamador redesenha a cena). */
  aplicar(slide) {
    const c = slide.camera || {};
    this.map.jumpTo({
      center: c.centro,
      zoom: c.zoom ?? this.map.getZoom(),
      pitch: c.inclinacao ?? this.map.getPitch(),
      bearing: c.rotacao ?? this.map.getBearing(),
    });
    const visiveis = Array.isArray(slide.camadas_visiveis) ? new Set(slide.camadas_visiveis) : null;
    if (visiveis) for (const camada of this.documento.corpo.camadas) camada.visivel = visiveis.has(camada.id);
    if (slide.instante) this.documento.corpo.iluminacao.instante = slide.instante;
    if (Number.isFinite(slide.exagero)) this.documento.corpo.terreno.exagero = slide.exagero;
    return slide;
  }
}
