/* plat · mapa — camada de desenho e anotações (item L2-01-k-desenho-anotacoes).

   Motor de interação: terra-draw (MIT, vendorizado em web/vendor/terra-draw/, mesma cópia já testada em
   wt/il201hselec — sha256 idêntico em VERSOES.txt) faz criação/seleção/edição de vértice/mover/apagar dos
   modos NATIVOS dele (ponto, linha, polígono, retângulo). texto, círculo e seta não têm modo nativo:
   texto e círculo nascem de um ponto (a diferença é só o formulário que aparece ao terminar — texto pede o
   conteúdo, círculo pede o raio em metros); seta nasce de uma linha, com uma ponta de flecha desenhada por
   cima. As três ficam marcadas em `properties.tipo_desenho` via `updateFeatureProperties` (API pública do
   terra-draw) assim que o desenho termina.

   Persistência: o terra-draw é só o EDITOR. A fonte de verdade em repouso é `this._features` (array na
   ORDEM de desenho = ordem de pintura, como o resto do mapa — comentário de `app/mapa/simbologia.py`) —
   o MESMO formato salvo no documento (`corpo.desenho.features`, GeoJSON + estilo, sem tabela; ver
   `app/catalogo/documento.py::erros_de_desenho`). Enquanto uma feição está sendo desenhada/editada ela mora
   SÓ no terra-draw; ao terminar (`finish`) ou ao sair do modo "editar" ela volta para `this._features` e o
   terra-draw esquece (`draw.clear()`) — assim nunca há duas fontes desenhando a mesma feição ao mesmo tempo,
   e o z-order (array) fica inteiramente sob nosso controle, coisa que a pilha interna do terra-draw não
   expõe. Render em repouso é uma camada MapLibre própria (`plat-desenho`), com raio de círculo em pixels
   calculado pela fórmula padrão de "metros por pixel" (Web Mercator) e halo de texto nativo do MapLibre. */

import { h } from '../base/dom.js';
import { t } from '../base/i18n.js';
import { area, comprimento, formatarArea, formatarDistancia } from './medicao.js';

const FONTE = 'plat-desenho';
const _CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

// ULID (mesmo formato do servidor, app/catalogo/documento.py::gerar_ulid/ULID_RE): 48 bits de tempo em ms +
// 80 bits aleatórios, Crockford base32, 26 caracteres. Implementação própria (nenhuma lib de ULID no vendor
// e o algoritmo cabe em poucas linhas — degrau 6/7 do PONYTAIL).
export function gerarUlid() {
  let ts = BigInt(Date.now());
  const aleatorio = crypto.getRandomValues(new Uint8Array(10));
  let valor = ts << 80n;
  for (let i = 0; i < 10; i += 1) valor |= BigInt(aleatorio[i]) << BigInt((9 - i) * 8);
  const caracteres = [];
  for (let i = 0; i < 26; i += 1) {
    caracteres.push(_CROCKFORD[Number(valor & 0x1fn)]);
    valor >>= 5n;
  }
  return caracteres.reverse().join('');
}

const MODOS_NATIVOS = { ponto: 'point', linha: 'linestring', poligono: 'polygon', retangulo: 'rectangle', seta: 'linestring' };
// modo do terra-draw que sabe EDITAR cada tipo nosso (retângulo volta como polígono: depois de desenhado é um
// Polygon como outro qualquer, e o modo `rectangle` do terra-draw só cria, não edita vértice)
const MODO_DE_EDICAO = { ponto: 'point', texto: 'point', circulo: 'point', linha: 'linestring', seta: 'linestring', poligono: 'polygon', retangulo: 'polygon' };
// sem `flags` o TerraDrawSelectMode NÃO deixa selecionar nem arrastar nada (`flags={}` é o padrão do pacote,
// conferido no arquivo vendorizado) — mover a feição, arrastar vértice e apagar vértice saem daqui.
const FLAGS_SELECAO = {
  point: { feature: { draggable: true } },
  linestring: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
  polygon: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
};
// halo do texto, em pixels de contorno de cada lado da letra (é `lineWidth/2` do strokeText)
const HALO_PX = 1.6;
const HALO_COR = '#ffffff';
// o texto GUARDADO pode ir a 10.000 caracteres (limite do documento); o DESENHADO é cortado, senão a
// imagem passaria do tamanho máximo de textura do navegador (medido: 10.000 letras a 14 px ≈ 70.000 px
// de largura, contra ~32.767 de teto). O corte é só do que aparece no mapa, nunca do dado salvo.
const TEXTO_DESENHADO_MAX = 120;
const ESTILO_PADRAO = () => ({ cor: '#d98a2b', contorno: '#10161a', largura: 2, preenchimento: true, opacidade: 0.85, tamanho_fonte: 14 });

function perguntar(mensagem, padrao) {
  // ponytail: window.prompt é o mínimo que funciona hoje (recurso nativo do navegador); um formulário no
  // painel lateral é o passo natural seguinte quando este item voltar para polimento de UX.
  return window.prompt(mensagem, padrao);
}

export class Desenho {
  constructor(map, maplibregl, painel) {
    this.map = map;
    this.maplibregl = maplibregl;
    this.painel = painel;
    this._features = [];          // GeoJSON Feature[]; ordem = ordem de pintura (corpo.desenho.features)
    this._estiloAtual = ESTILO_PADRAO();
    this._editandoId = null;      // ulid da feição atualmente emprestada ao terra-draw para edição
    this._idEmprestado = null;    // id que o terra-draw deu a essa feição enquanto ela é editada
    this._draw = null;
    this._snap = { ativo: false, toleranciaPx: 10 };
    this._aoMudar = null;         // callback(features) — o chamador decide quando salvar
    this._imagensTexto = new Map(); // nome da imagem -> assinatura (texto|tamanho|cor) já registrada
  }

  aoMudar(fn) { this._aoMudar = fn; }

  // ------------------------------------------------------------------------------------------- camada de render
  _garantirCamadas() {
    if (this.map.getSource(FONTE)) return;
    this.map.addSource(FONTE, { type: 'geojson', data: this._colecao() });
    const cor = ['coalesce', ['get', 'cor', ['get', 'estilo']], '#d98a2b'];
    const contorno = ['coalesce', ['get', 'contorno', ['get', 'estilo']], '#10161a'];
    const opacidade = ['coalesce', ['get', 'opacidade', ['get', 'estilo']], 0.85];
    const largura = ['coalesce', ['get', 'largura', ['get', 'estilo']], 2];
    this.map.addLayer({
      id: `${FONTE}-poligono`, type: 'fill', source: FONTE,
      filter: ['in', ['get', 'tipo_desenho'], ['literal', ['poligono', 'retangulo']]],
      paint: { 'fill-color': cor, 'fill-opacity': ['case', ['==', ['get', 'preenchimento', ['get', 'estilo']], false], 0, opacidade] },
    });
    this.map.addLayer({
      id: `${FONTE}-poligono-contorno`, type: 'line', source: FONTE,
      filter: ['in', ['get', 'tipo_desenho'], ['literal', ['poligono', 'retangulo']]],
      paint: { 'line-color': contorno, 'line-width': largura },
    });
    this.map.addLayer({
      id: `${FONTE}-linha`, type: 'line', source: FONTE,
      filter: ['in', ['get', 'tipo_desenho'], ['literal', ['linha', 'seta']]],
      paint: { 'line-color': cor, 'line-width': largura, 'line-opacity': opacidade },
    });
    this.map.addLayer({
      // raio geodésico aproximado: metros informados convertidos em pixels na latitude/zoom correntes
      id: `${FONTE}-circulo`, type: 'circle', source: FONTE,
      filter: ['==', ['get', 'tipo_desenho'], 'circulo'],
      paint: {
        // raio em PIXELS pré-calculado em `_colecao()` (não há expressão MapLibre para ler a coordenada da
        // geometria de dentro do paint; o cálculo usa a mesma fórmula de `metrosParaPixels`, por feição/lat)
        'circle-radius': ['coalesce', ['get', '_raio_px'], 4],
        'circle-color': cor, 'circle-opacity': ['*', opacidade, 0.35],
        'circle-stroke-color': contorno, 'circle-stroke-width': largura,
      },
    });
    this.map.addLayer({
      id: `${FONTE}-ponto`, type: 'circle', source: FONTE,
      filter: ['==', ['get', 'tipo_desenho'], 'ponto'],
      paint: { 'circle-radius': 6, 'circle-color': cor, 'circle-opacity': opacidade,
               'circle-stroke-color': contorno, 'circle-stroke-width': 1.5 },
    });
    this.map.addLayer({
      /* Texto com halo SEM servidor de glifos. `text-field` do MapLibre exige `glyphs` no estilo, e o estilo
         do mapa-base local não tem (o servidor de glifos é outro item, L2-02-e): MEDIDO aqui — o MapLibre 4
         aceita o addLayer e depois DESCARTA a camada em silêncio, `getLayer` devolve undefined. Por isso o
         texto é desenhado num canvas próprio (halo = `strokeText` por baixo, texto = `fillText` por cima, a
         mesma ordem que o MapLibre usa) e entra como IMAGEM da feição (`icon-image`), que não depende de
         glifo nenhum. Quando o L2-02-e entregar o servidor de glifos, esta camada pode voltar a ser
         `text-field`/`text-halo-width` sem mudar o documento salvo. */
      id: `${FONTE}-texto`, type: 'symbol', source: FONTE,
      filter: ['==', ['get', 'tipo_desenho'], 'texto'],
      layout: { 'icon-image': ['get', '_imagem_texto'], 'icon-anchor': 'left', 'icon-offset': [8, 0],
                'icon-allow-overlap': true, 'icon-ignore-placement': true },
      paint: { 'icon-opacity': opacidade },
    });
    this.map.addLayer({
      // ponta de seta: símbolo triangular girado para o rumo do último trecho da linha
      id: `${FONTE}-seta-ponta`, type: 'symbol', source: FONTE,
      filter: ['==', ['get', 'tipo_desenho'], 'seta'],
      layout: { 'icon-image': 'plat-seta-ponta', 'icon-size': 0.9, 'icon-rotate': ['get', 'rumo_graus'],
                'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true },
      paint: { 'icon-opacity': opacidade },
    });
    this._garantirIconeSeta();
    // círculo é raio_m convertido em pixels do zoom atual (comentário de _colecao); zoom muda o pixel/metro
    this.map.on('zoom', () => this._repintar());
  }

  _garantirIconeSeta() {
    if (this.map.hasImage('plat-seta-ponta')) return;
    const n = 24;
    const dados = new Uint8Array(n * n * 4);
    for (let y = 0; y < n; y += 1) {
      for (let x = 0; x < n; x += 1) {
        // triângulo apontando para +x (rumo 90° = leste), rotacionado depois por icon-rotate
        const dentro = x > n * 0.15 && Math.abs(y - n / 2) < (n / 2) * (1 - (x - n * 0.15) / (n * 0.85));
        const i = (y * n + x) * 4;
        dados[i] = 217; dados[i + 1] = 138; dados[i + 2] = 43; dados[i + 3] = dentro ? 255 : 0;
      }
    }
    this.map.addImage('plat-seta-ponta', { width: n, height: n, data: dados });
  }

  /** imagem do texto (halo por baixo, letra por cima) registrada no mapa; devolve o nome da imagem. */
  _imagemDoTexto(f) {
    const estilo = f.properties?.estilo || {};
    const tamanho = Math.min(Math.max(Number(estilo.tamanho_fonte) || 14, 4), 96);
    const cor = estilo.cor || '#d98a2b';
    const bruto = String(f.properties?.texto ?? '');
    const texto = bruto.length > TEXTO_DESENHADO_MAX ? `${bruto.slice(0, TEXTO_DESENHADO_MAX)}…` : bruto;
    const nome = `plat-texto-${f.id}`;
    const assinatura = `${texto}|${tamanho}|${cor}`;
    if (this._imagensTexto.get(nome) === assinatura) return nome;
    const escala = 2;                       // desenha no dobro e declara pixelRatio 2: letra nítida em tela retina
    const fonte = (px) => `${px}px ui-sans-serif, system-ui, sans-serif`;
    const cv = document.createElement('canvas');
    let ctx = cv.getContext('2d');
    ctx.font = fonte(tamanho * escala);
    const larguraTexto = Math.ceil(ctx.measureText(texto).width);
    const margem = Math.ceil((HALO_PX + 1) * escala);
    cv.width = Math.max(1, larguraTexto + margem * 2);
    cv.height = Math.ceil(tamanho * escala * 1.6) + margem * 2;
    ctx = cv.getContext('2d');
    ctx.font = fonte(tamanho * escala);
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    ctx.lineWidth = HALO_PX * 2 * escala;   // strokeText engrossa para os DOIS lados: metade fica visível
    ctx.strokeStyle = HALO_COR;
    ctx.strokeText(texto, margem, cv.height / 2);
    ctx.fillStyle = cor;
    ctx.fillText(texto, margem, cv.height / 2);
    const dados = ctx.getImageData(0, 0, cv.width, cv.height);
    if (this.map.hasImage(nome)) this.map.removeImage(nome);
    this.map.addImage(nome, { width: cv.width, height: cv.height, data: new Uint8Array(dados.data.buffer) },
                      { pixelRatio: escala });
    this._imagensTexto.set(nome, assinatura);
    return nome;
  }

  /** prova do halo para o teste: largura declarada e quantos pixels da cor do halo o desenho tem. */
  haloDoTexto(id) {
    const f = this._features.find((x) => x.id === id);
    if (!f || f.properties?.tipo_desenho !== 'texto') return null;
    const nome = this._imagemDoTexto(f);
    const img = this.map.getImage ? this.map.getImage(nome) : null;
    const dados = img?.data?.data || img?.data;
    let pixelsHalo = 0;
    if (dados) {
      for (let i = 0; i < dados.length; i += 4) {
        if (dados[i + 3] > 0 && dados[i] > 240 && dados[i + 1] > 240 && dados[i + 2] > 240) pixelsHalo += 1;
      }
    }
    return { imagem: nome, halo_px: HALO_PX, halo_cor: HALO_COR, pixels_de_halo: pixelsHalo };
  }

  _rumo(a, b) {
    const rad = Math.atan2(b[0] - a[0], b[1] - a[1]);
    return (rad * 180) / Math.PI;
  }

  _colecao() {
    return {
      type: 'FeatureCollection',
      features: this._features
        .filter((f) => f.id !== this._editandoId)
        .map((f) => {
          const tipo = f.properties?.tipo_desenho;
          if (tipo === 'seta') {
            const c = f.geometry.coordinates;
            const rumo = c.length >= 2 ? this._rumo(c[c.length - 2], c[c.length - 1]) : 0;
            return { ...f, properties: { ...f.properties, rumo_graus: rumo } };
          }
          if (tipo === 'texto') {
            return { ...f, properties: { ...f.properties, _imagem_texto: this._imagemDoTexto(f) } };
          }
          if (tipo === 'circulo') {
            const [, lat] = f.geometry.coordinates;
            const pxPorMetro = (2 ** this.map.getZoom()) / (78271.484 * Math.cos((lat * Math.PI) / 180));
            const raioPx = (f.properties.raio_m || 0) * Math.abs(pxPorMetro);
            return { ...f, properties: { ...f.properties, _raio_px: Math.min(raioPx, 4000) } };
          }
          return f;
        }),
    };
  }

  _repintar() {
    const src = this.map.getSource(FONTE);
    if (src) src.setData(this._colecao());
    if (this._aoMudar) this._aoMudar(this._features);
  }

  // ------------------------------------------------------------------------------------------------ terra-draw
  _garantirDraw() {
    if (this._draw) return;
    const TD = window.terraDraw;
    const Adapter = window.terraDrawMaplibreGlAdapter?.TerraDrawMapLibreGLAdapter;
    if (!TD || !Adapter) throw new Error(t('mapa.desenho_erro_biblioteca'));
    this._draw = new TD.TerraDraw({
      adapter: new Adapter({ map: this.map, coordinatePrecision: 9 }),
      modes: [
        new TD.TerraDrawPointMode({ snapping: this._snapping() }),
        new TD.TerraDrawLineStringMode({ snapping: this._snapping() }),
        new TD.TerraDrawPolygonMode({ snapping: this._snapping() }),
        new TD.TerraDrawRectangleMode(),
        new TD.TerraDrawSelectMode({ flags: FLAGS_SELECAO }),
      ],
    });
    this._draw.on('finish', (id) => this._aoTerminar(id));
    this._draw.start();
  }

  _tipoDoModoAtivo() {
    return this._modoDesenhoAtual;
  }

  _aoTerminar(idTerraDraw) {
    const feicao = this._draw.getSnapshot().find((f) => String(f.id) === String(idTerraDraw));
    if (!feicao) return;
    // MEDIDO: o modo `select` também dispara `finish` — ao SOLTAR o arrasto de um vértice. Sem esta guarda o
    // fim de um arrasto era tratado como desenho novo: criava uma cópia da feição, tirava a original do
    // terra-draw e a edição se perdia em silêncio. Em edição, o `finish` só atualiza a geometria emprestada.
    if (this._editandoId) {
      const emEdicao = this._features.find((f) => f.id === this._editandoId);
      if (emEdicao && feicao.geometry) emEdicao.geometry = feicao.geometry;
      return;
    }
    let tipoDesenho = this._tipoDoModoAtivo();
    const props = { tipo_desenho: tipoDesenho, estilo: { ...this._estiloAtual } };
    if (tipoDesenho === 'texto') {
      const texto = perguntar(t('mapa.desenho_pedir_texto'), '');
      if (!texto || !texto.trim()) { this._draw.removeFeatures([idTerraDraw]); return; }
      if (texto.length > 10000) { window.alert(t('mapa.desenho_texto_grande')); this._draw.removeFeatures([idTerraDraw]); return; }
      props.texto = texto;
    }
    if (tipoDesenho === 'circulo') {
      const raio = Number(perguntar(t('mapa.desenho_pedir_raio'), '250'));
      if (!raio || !(raio > 0) || raio > 2_000_000) { window.alert(t('mapa.desenho_raio_invalido')); this._draw.removeFeatures([idTerraDraw]); return; }
      const lat = feicao.geometry.coordinates[1];
      if (Math.abs(lat) > 85) { window.alert(t('mapa.desenho_circulo_polo')); this._draw.removeFeatures([idTerraDraw]); return; }
      props.raio_m = raio;
    }
    this._draw.updateFeatureProperties(idTerraDraw, props);
    const atualizada = this._draw.getSnapshot().find((f) => String(f.id) === String(idTerraDraw));
    const ulid = gerarUlid();
    this._features.push({ type: 'Feature', id: ulid, geometry: atualizada.geometry, properties: props });
    this._draw.removeFeatures([idTerraDraw]);
    this._repintar();
    this.map.getCanvas().style.cursor = '';
  }

  // ------------------------------------------------------------------------------------------------ API pública
  iniciarModo(tipoDesenho) {
    this._garantirCamadas();
    this._garantirDraw();
    if (this._editandoId) this.terminarEdicao();
    this._modoDesenhoAtual = tipoDesenho;
    const nativo = MODOS_NATIVOS[tipoDesenho] || (tipoDesenho === 'texto' || tipoDesenho === 'circulo' ? 'point' : 'point');
    this._draw.setMode(nativo);
  }

  pararModo() {
    if (this._editandoId) { this.terminarEdicao(); return; }
    if (this._draw) this._draw.setMode('static');
  }

  definirEstilo(parcial) {
    this._estiloAtual = { ...this._estiloAtual, ...parcial };
  }

  definirSnap(ativo) {
    // o `toCustom` lê `this._snap.ativo` na hora do clique, então ligar/desligar não reconstrói o terra-draw
    // (reconstruir perdia o desenho em curso e deixava o modo ativo pendurado).
    this._snap.ativo = !!ativo;
  }

  definirToleranciaSnap(px) { this._snap.toleranciaPx = Number(px) || 10; }

  /* Encaixe (snapping) em VÉRTICE de feição visível, com tolerância em PIXELS (10 px, o valor do portão do
     item). O terra-draw só sabe encaixar nas feições que ele mesmo está editando; o que interessa aqui é
     encaixar no dado do mapa — camadas do catálogo E as feições de desenho já em repouso. Por isso o
     `toCustom`: perguntamos ao MapLibre quais feições estão RENDERIZADAS numa caixa de ±tolerância em volta
     do ponteiro (`queryRenderedFeatures`, recurso nativo — degrau 4 do PONYTAIL) e devolvemos o vértice mais
     próximo em pixels, nunca em graus (em graus a tolerância mudaria com a latitude e com o zoom). */
  _snapping() {
    return {
      toCustom: (evento) => {
        if (!this._snap.ativo) return undefined;
        const c = this.encaixar(evento.containerX, evento.containerY);
        return c || undefined;
      },
    };
  }

  _verticesDe(geometria, saida) {
    const g = geometria || {};
    if (g.type === 'Point') saida.push(g.coordinates);
    else if (g.type === 'LineString' || g.type === 'MultiPoint') saida.push(...g.coordinates);
    else if (g.type === 'Polygon' || g.type === 'MultiLineString') for (const anel of g.coordinates) saida.push(...anel);
    else if (g.type === 'MultiPolygon') for (const p of g.coordinates) for (const anel of p) saida.push(...anel);
    return saida;
  }

  /** [lon, lat] do vértice visível mais próximo do pixel (x, y) dentro da tolerância; null se não houver. */
  encaixar(x, y) {
    const tol = this._snap.toleranciaPx;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    let renderizadas = [];
    try {
      renderizadas = this.map.queryRenderedFeatures([[x - tol, y - tol], [x + tol, y + tol]]) || [];
    } catch { /* estilo ainda carregando: sobram os vértices do próprio desenho */ }
    // As feições do NOSSO desenho entram pela lista em repouso, não pelo que voltou do MapLibre: uma fonte
    // GeoJSON é re-ladrilhada antes de desenhar, e a coordenada que volta do `queryRenderedFeatures` vem
    // arredondada ao ladrilho (medido: até 2,4e-3 grau de diferença). Encaixar no valor arredondado faria o
    // vértice novo NÃO coincidir com o vértice alvo — que é exatamente o que o portão do item exige.
    const alvos = [
      ...this._features.map((f) => f.geometry),
      ...renderizadas.filter((f) => f.source !== FONTE && !String(f.layer?.id || '').startsWith('td-'))
        .map((f) => f.geometry),
    ];
    let melhor = null;
    let melhorDist = Infinity;
    for (const geom of alvos) {
      for (const v of this._verticesDe(geom, [])) {
        if (!Array.isArray(v) || v.length < 2) continue;
        const p = this.map.project({ lng: v[0], lat: v[1] });
        const d = Math.hypot(p.x - x, p.y - y);
        if (d <= tol && d < melhorDist) { melhorDist = d; melhor = [v[0], v[1]]; }
      }
    }
    return melhor;
  }

  /* Edição: a feição sai do repouso (`this._features`) e é EMPRESTADA ao terra-draw no modo `select`, que
     move a feição inteira, arrasta vértice e apaga vértice (FLAGS_SELECAO). Enquanto está emprestada ela sai
     do render de repouso (`_colecao()` filtra `_editandoId`) — assim nunca aparece duas vezes. `terminarEdicao`
     devolve a geometria editada para o MESMO id e as MESMAS propriedades (estilo, texto, raio). */
  editar(id) {
    const f = this._features.find((x) => x.id === id);
    if (!f) return false;
    if (this._editandoId) this.terminarEdicao();
    this._garantirCamadas();
    this._garantirDraw();
    const modo = MODO_DE_EDICAO[f.properties?.tipo_desenho] || 'polygon';
    this._draw.clear();
    this._draw.setMode('select');
    this._draw.addFeatures([{ type: 'Feature', geometry: f.geometry, properties: { mode: modo } }]);
    // guardamos o id que o terra-draw deu: durante a edição o instantâneo ganha os pontos auxiliares de
    // vértice e de meio de aresta, e a ordem deles muda a cada arrasto — procurar por índice pegaria o
    // ponto auxiliar em vez da feição (foi o que aconteceu ao medir).
    this._idEmprestado = this._draw.getSnapshot().find((g) => g.properties?.mode === modo)?.id ?? null;
    this._editandoId = id;
    this._repintar();
    return true;
  }

  editando() { return this._editandoId; }

  terminarEdicao() {
    if (!this._editandoId) return null;
    const id = this._editandoId;
    const emprestada = this._draw
      ? this._draw.getSnapshot().find((g) => String(g.id) === String(this._idEmprestado))
      : null;
    const f = this._features.find((x) => x.id === id);
    if (f && emprestada && emprestada.geometry) f.geometry = emprestada.geometry;
    if (this._draw) { this._draw.clear(); this._draw.setMode('static'); }
    this._editandoId = null;
    this._idEmprestado = null;
    this._repintar();
    return f || null;
  }

  apagar(id) {
    if (this._editandoId === id) { this._editandoId = null; if (this._draw) { this._draw.clear(); this._draw.setMode('static'); } }
    this._features = this._features.filter((f) => f.id !== id);
    this._repintar();
  }

  mover(id, delta) {
    const i = this._features.findIndex((f) => f.id === id);
    if (i < 0) return;
    const j = i + delta;
    if (j < 0 || j >= this._features.length) return;
    [this._features[i], this._features[j]] = [this._features[j], this._features[i]];
    this._repintar();
  }

  limparTudo() {
    if (this._editandoId) { this._editandoId = null; if (this._draw) { this._draw.clear(); this._draw.setMode('static'); } }
    this._features = [];
    this._repintar();
  }

  lista() { return this._features; }

  carregarFeatures(features) {
    this._garantirCamadas();
    this._features = Array.isArray(features) ? features : [];
    this._repintar();
  }

  // texto/GeoJSON/KML importados entram como feições novas, com o MESMO caminho de validação do servidor
  // (id ULID próprio, tipo_desenho reconhecido) — nunca confiamos no id/propriedades do arquivo importado.
  importarGeoJSON(colecaoOuFeicao, tipoDesenhoPadrao = 'poligono') {
    const feicoes = colecaoOuFeicao.type === 'FeatureCollection' ? colecaoOuFeicao.features : [colecaoOuFeicao];
    let n = 0;
    for (const f of feicoes) {
      if (!f?.geometry) continue;
      const tipoGeom = f.geometry.type;
      let tipoDesenho = tipoDesenhoPadrao;
      if (tipoGeom === 'Point') tipoDesenho = 'ponto';
      else if (tipoGeom === 'LineString') tipoDesenho = 'linha';
      else if (tipoGeom === 'Polygon') tipoDesenho = tipoDesenhoPadrao === 'retangulo' ? 'retangulo' : 'poligono';
      else continue; // Multi*/GeometryCollection: fora do escopo deste item (7 tipos simples)
      this._features.push({
        type: 'Feature', id: gerarUlid(), geometry: f.geometry,
        properties: { tipo_desenho: tipoDesenho, estilo: ESTILO_PADRAO(), rotulo: f.properties?.nome || f.properties?.rotulo },
      });
      n += 1;
    }
    this._repintar();
    return n;
  }

  medidaDe(feicao) {
    const g = feicao.geometry;
    if (g.type === 'LineString') return formatarDistancia(comprimento(g.coordinates));
    if (g.type === 'Polygon') return formatarArea(area(g.coordinates[0]));
    if (feicao.properties?.tipo_desenho === 'circulo') {
      const r = feicao.properties.raio_m || 0;
      return formatarArea(Math.PI * r * r);
    }
    return null;
  }
}

// -------------------------------------------------------------------------------------- KML mínimo (nativo)
// Sem lib de conversão no vendor: DOMParser (nativo do navegador) lê Point/LineString/Polygon do KML — o
// suficiente para "importar desenho"; MultiGeometry e estilos do KML ficam fora (ponytail: escopo do item é
// os 7 tipos de desenho, não um leitor de KML completo).
export function kmlParaGeoJSON(textoKml) {
  const doc = new DOMParser().parseFromString(textoKml, 'text/xml');
  if (doc.querySelector('parsererror')) throw new Error('KML inválido');
  const coordsDeTexto = (txt) => txt.trim().split(/\s+/).map((par) => par.split(',').slice(0, 2).map(Number));
  const features = [];
  for (const placemark of doc.querySelectorAll('Placemark')) {
    const nome = placemark.querySelector('name')?.textContent?.trim();
    const ponto = placemark.querySelector('Point > coordinates');
    const linha = placemark.querySelector('LineString > coordinates');
    const poligono = placemark.querySelector('Polygon outerBoundaryIs coordinates, Polygon > coordinates');
    if (ponto) {
      const [c] = coordsDeTexto(ponto.textContent);
      features.push({ type: 'Feature', properties: { nome }, geometry: { type: 'Point', coordinates: c } });
    } else if (linha) {
      features.push({ type: 'Feature', properties: { nome }, geometry: { type: 'LineString', coordinates: coordsDeTexto(linha.textContent) } });
    } else if (poligono) {
      const anel = coordsDeTexto(poligono.textContent);
      features.push({ type: 'Feature', properties: { nome }, geometry: { type: 'Polygon', coordinates: [anel] } });
    }
  }
  return { type: 'FeatureCollection', features };
}
