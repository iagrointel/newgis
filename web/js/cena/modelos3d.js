/* plat · cena — modelos 3D sobre o MapLibre (item L2-09-c-modelos-gltf-ifc-3dtiles).

   Dois caminhos, escolhidos pelo campo `modo` do documento de cena:

   * `gltf` — CAMADA PERSONALIZADA do MapLibre desenhada com three.js (MIT, vendorizado). O MapLibre passa
     a matriz de projeção do quadro; a camada compõe com a matriz que leva o sistema local do modelo
     (metros, X leste, Y cima, -Z norte) para o sistema do mundo do MapLibre (coordenada de Mercator
     normalizada). Clique lança um raio pela mesma matriz e devolve o `extras.guid` do nó atingido — é
     esse GUID que a tela usa para pedir as propriedades do elemento à API.
   * `tileset` — deck.gl (MIT, vendorizado) por cima do mapa: `MapboxOverlay` interpolado no MapLibre e
     `Tile3DLayer` lendo a árvore OGC 3D Tiles 1.1 pela URL do inquilino. É o caminho para malha grande,
     onde carregar o modelo inteiro de uma vez não cabe.

   Por que não uma biblioteca de BIM pronta: a que o SIG de teste interno usa é AGPL, e a spec veta (DOC.md
   22). `make sem-agpl` guarda a regra a cada rodada. */
import { THREE, carregarGlb } from './modelogltf.js';

const RAIO_TERRA_M = 6378137;
const CIRCUNFERENCIA_M = 2 * Math.PI * RAIO_TERRA_M;

/** Metros por unidade de Mercator normalizada, na latitude dada (o MapLibre chama isto de "meterInMercatorCoordinateUnits"). */
export function unidadesPorMetro(lat) {
  return 1 / (CIRCUNFERENCIA_M * Math.cos((lat * Math.PI) / 180));
}

/** Matriz que leva o sistema local do modelo ao sistema do mundo do MapLibre.

    Os dois sistemas discordam em duas coisas, e é preciso dizer as duas por extenso, porque errar o
    sinal aqui põe o modelo do outro lado da rua sem nenhum erro na tela:

    * o glTF é Y para CIMA e -Z para o NORTE (convenção declarada em app/modelos3d/posicionamento.py);
    * o Mercator do MapLibre é X para o leste, Y para o SUL e Z para cima.

    Logo o eixo Y do modelo (cima) vira o Z do Mercator, e o eixo Z do modelo vira o Y do Mercator SEM
    troca de sinal: z do modelo negativo (norte) dá Y de Mercator negativo, que é justamente o norte. A
    troca de dois eixos sem inverter sinal é um espelhamento, e é assim mesmo: o Mercator é canhoto em
    relação ao sistema leste-norte-cima. */
export function matrizDoModelo(maplibregl, modelo) {
  const ancora = maplibregl.MercatorCoordinate.fromLngLat(
    [modelo.lon, modelo.lat], modelo.altura_m || 0);
  const s = ancora.meterInMercatorCoordinateUnits() * (modelo.escala || 1);
  // azimute horário a partir do norte: (0,0,-1) do modelo tem de sair apontando para `rotacao_graus`
  const giro = new THREE.Matrix4().makeRotationY(-((modelo.rotacao_graus || 0) * Math.PI) / 180);
  const eixos = new THREE.Matrix4().set(
    s, 0, 0, 0,
    0, 0, s, 0,
    0, s, 0, 0,
    0, 0, 0, 1);
  return new THREE.Matrix4()
    .makeTranslation(ancora.x, ancora.y, ancora.z)
    .multiply(eixos)
    .multiply(giro);
}

export class CamadaModeloGltf {
  constructor(modelo, { aoClicar } = {}) {
    this.id = `plat-modelo-${modelo.id}`;
    this.type = 'custom';
    this.renderingMode = '3d';
    this.modelo = modelo;
    this.aoClicar = aoClicar;
    this.pronto = false;
    this.erro = null;
    this._raio = new THREE.Raycaster();
    this._mvp = new THREE.Matrix4();   // projeção do quadro × matriz do modelo, guardada no render
  }

  async onAdd(map, gl) {
    this.map = map;
    this.camera = new THREE.Camera();
    this.cena = new THREE.Scene();
    this.cena.add(new THREE.AmbientLight(0xffffff, 1.4));
    const sol = new THREE.DirectionalLight(0xffffff, 1.6);
    sol.position.set(0.4, 1, 0.6);
    this.cena.add(sol);
    this.renderizador = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
    this.renderizador.autoClear = false;
    try {
      const { raiz } = await carregarGlb(this.modelo.url_glb);
      this.raiz = raiz;
      this.cena.add(raiz);
      this.pronto = true;
    } catch (e) {
      this.erro = e.message || String(e);
    }
    map.triggerRepaint();
  }

  render(gl, opcoes) {
    if (!this.pronto) return;
    const projecao = new THREE.Matrix4().fromArray(
      opcoes.defaultProjectionData ? opcoes.defaultProjectionData.mainMatrix : opcoes);
    this.camera.projectionMatrix = projecao.multiply(matrizDoModelo(window.maplibregl, this.modelo));
    this._mvp.copy(this.camera.projectionMatrix);
    this.renderizador.resetState();
    this.renderizador.render(this.cena, this.camera);
  }

  /** Caixa envolvente do que foi DESENHADO, em graus e metros — a medida que o portão do item compara
      com a caixa que o servidor calculou. Sai do grafo do three.js, não da ficha da API: é a prova de que
      o navegador pôs o modelo onde o servidor disse, e não de que os dois leram o mesmo número. */
  caixaGeografica() {
    if (!this.pronto || !this.raiz) return null;
    const maplibregl = window.maplibregl;
    const caixa = new THREE.Box3().setFromObject(this.raiz);
    const m = matrizDoModelo(maplibregl, this.modelo);
    const cantos = [];
    for (let i = 0; i < 8; i += 1) {
      const p = new THREE.Vector3(
        i & 1 ? caixa.max.x : caixa.min.x,
        i & 2 ? caixa.max.y : caixa.min.y,
        i & 4 ? caixa.max.z : caixa.min.z).applyMatrix4(m);
      const mc = new maplibregl.MercatorCoordinate(p.x, p.y, p.z);
      const ll = mc.toLngLat();
      cantos.push([ll.lng, ll.lat, mc.toAltitude()]);
    }
    return {
      cantos,
      oeste: Math.min(...cantos.map((c) => c[0])), leste: Math.max(...cantos.map((c) => c[0])),
      sul: Math.min(...cantos.map((c) => c[1])), norte: Math.max(...cantos.map((c) => c[1])),
      altura_minima: Math.min(...cantos.map((c) => c[2])), altura_maxima: Math.max(...cantos.map((c) => c[2])),
    };
  }

  /** Caixa do modelo em PIXELS do canvas, projetando os 8 cantos pela mesma matriz que desenhou o quadro.

      `map.project()` não serve aqui: ele projeta longitude e latitude no CHÃO, e o modelo tem altura —
      com a câmera inclinada, o topo aparece bem acima da pegada. */
  caixaNaTela() {
    if (!this.pronto || !this.raiz) return null;
    const canvas = this.map.getCanvas();
    const caixa = new THREE.Box3().setFromObject(this.raiz);
    const pontos = [];
    for (let i = 0; i < 8; i += 1) {
      const p = new THREE.Vector3(
        i & 1 ? caixa.max.x : caixa.min.x,
        i & 2 ? caixa.max.y : caixa.min.y,
        i & 4 ? caixa.max.z : caixa.min.z).applyMatrix4(this._mvp);
      pontos.push({ x: ((p.x + 1) / 2) * canvas.clientWidth, y: ((1 - p.y) / 2) * canvas.clientHeight });
    }
    return {
      x0: Math.min(...pontos.map((p) => p.x)), x1: Math.max(...pontos.map((p) => p.x)),
      y0: Math.min(...pontos.map((p) => p.y)), y1: Math.max(...pontos.map((p) => p.y)),
    };
  }

  /** Centro do modelo em pixels do canvas — é por onde o teste de navegador começa a procurar. */
  centroNaTela() {
    const c = this.caixaNaTela();
    return c ? { x: (c.x0 + c.x1) / 2, y: (c.y0 + c.y1) / 2 } : null;
  }

  /** Nó atingido por um clique na tela, ou null. Devolve o que o servidor gravou em `extras`. */
  elementoNoPonto(ponto) {
    if (!this.pronto || !this.raiz) return null;
    const canvas = this.map.getCanvas();
    const nx = (ponto.x / canvas.clientWidth) * 2 - 1;
    const ny = -((ponto.y / canvas.clientHeight) * 2 - 1);
    // O raio é montado à mão, e não por `setFromCamera`: a câmera desta camada é uma THREE.Camera crua
    // (a matriz de projeção vem PRONTA do MapLibre, não de um campo de visão), e o lançador de raios do
    // three.js só sabe tratar câmera perspectiva ou ortográfica — com a câmera crua ele recusa e escreve
    // "Unsupported camera type" no console. Invertendo a mesma matriz que desenhou o quadro, os dois
    // pontos do segmento voltam ao sistema do MODELO, que é onde a geometria está.
    const inversa = new THREE.Matrix4().copy(this._mvp).invert();
    const perto = new THREE.Vector3(nx, ny, -1).applyMatrix4(inversa);
    const longe = new THREE.Vector3(nx, ny, 1).applyMatrix4(inversa);
    this._raio.set(perto, longe.sub(perto).normalize());
    const alvos = this._raio.intersectObjects([this.raiz], true);
    for (const alvo of alvos) {
      let objeto = alvo.object;
      while (objeto) {
        if (objeto.userData && objeto.userData.guid) {
          return { ...objeto.userData, distancia: alvo.distance };
        }
        objeto = objeto.parent;
      }
    }
    return null;
  }

  onRemove() {
    if (this.raiz) this.cena.remove(this.raiz);
    this.pronto = false;
  }
}

/** Sobreposição deck.gl com uma Tile3DLayer por tileset visível. Só cria a sobreposição se houver tileset. */
export class Tilesets3D {
  constructor(map) {
    this.map = map;
    this.camadas = new Map();
    this.sobreposicao = null;
  }

  ativar(modelo, { aoCarregar } = {}) {
    const deck = window.deck;
    if (!deck || !deck.MapboxOverlay || !deck.Tile3DLayer) {
      throw new Error('deck.gl não carregou: a camada de 3D Tiles não pode ser montada');
    }
    if (!this.sobreposicao) {
      this.sobreposicao = new deck.MapboxOverlay({ interleaved: true, layers: [] });
      this.map.addControl(this.sobreposicao);
    }
    this.camadas.set(modelo.id, new deck.Tile3DLayer({
      id: `plat-tileset-${modelo.id}`,
      data: modelo.url_tileset,
      loadOptions: { fetch: { credentials: 'same-origin' } },
      pickable: true,
      onTilesetLoad: (tileset) => { if (aoCarregar) aoCarregar(tileset); },
    }));
    this._aplicar();
  }

  desativar(modeloId) {
    this.camadas.delete(modeloId);
    this._aplicar();
  }

  _aplicar() {
    if (this.sobreposicao) this.sobreposicao.setProps({ layers: [...this.camadas.values()] });
  }
}

export function urlDoModelo(id) {
  return {
    glb: `/api/modelos/${id}/glb`,
    tileset: `/api/modelos/${id}/3dtiles/tileset.json`,
  };
}
