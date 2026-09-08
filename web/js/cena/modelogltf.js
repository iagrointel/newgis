/* plat · cena — leitor mínimo de glTF binário no navegador (item L2-09-c-modelos-gltf-ifc-3dtiles).

   Lê o MESMO subconjunto que `app/modelos3d/glb.py` escreve: recipiente GLB 2.0, nós com matriz ou T/R/S,
   malhas com POSITION/NORMAL e índices, e material com cor base. Nada de textura — o servidor recusa
   modelo com recurso externo, e o que sobra é cor por elemento.

   Por que não o carregador de exemplo do three.js: ele mora em `examples/jsm`, importa de `three` por
   nome de módulo e puxa mais dois arquivos (utilitários de geometria e de esqueleto). Isso obrigaria a
   vendorizar quatro arquivos e a montar um mapa de importação só para ler o que já sai daqui de casa.
   A escada do PONYTAIL para no degrau anterior: o formato que a nossa conversão produz cabe neste
   arquivo. Modelo de terceiro com recurso que este leitor não conhece cai no aviso, não em tela branca. */
import * as THREE from '/static/vendor/three-0.185.1/three.module.min.js';

const MAGICO = 0x46546c67;
const PEDACO_JSON = 0x4e4f534a;
const PEDACO_BIN = 0x004e4942;

const COMPONENTES = {
  5120: Int8Array, 5121: Uint8Array, 5122: Int16Array,
  5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array,
};
const ITENS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

export class GlbInvalido extends Error {}

/** Separa o GLB em (json, binário). Mesmas recusas do lado do servidor. */
export function lerGlb(buffer) {
  const visao = new DataView(buffer);
  if (buffer.byteLength < 12) throw new GlbInvalido('arquivo menor que o cabeçalho GLB');
  if (visao.getUint32(0, true) !== MAGICO) throw new GlbInvalido('assinatura glTF ausente');
  if (visao.getUint32(4, true) !== 2) throw new GlbInvalido('só a versão 2 do GLB é lida');
  let json = null;
  let binario = new ArrayBuffer(0);
  let passo = 12;
  while (passo + 8 <= buffer.byteLength) {
    const tamanho = visao.getUint32(passo, true);
    const tipo = visao.getUint32(passo + 4, true);
    const inicio = passo + 8;
    const fim = inicio + tamanho;
    if (fim > buffer.byteLength) throw new GlbInvalido('pedaço maior que o arquivo');
    if (tipo === PEDACO_JSON && json === null) {
      json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, inicio, tamanho)));
    } else if (tipo === PEDACO_BIN && binario.byteLength === 0) {
      binario = buffer.slice(inicio, fim);
    }
    passo = fim + ((4 - (tamanho % 4)) % 4);
  }
  if (!json) throw new GlbInvalido('GLB sem pedaço JSON');
  return { json, binario };
}

/** URIs que o modelo mandaria o navegador buscar fora do arquivo. Vazio é a única resposta aceita. */
export function recursosExternos(json) {
  const fora = [];
  for (const chave of ['buffers', 'images']) {
    for (const r of json[chave] || []) {
      if (r && typeof r.uri === 'string' && r.uri && !r.uri.startsWith('data:')) fora.push(r.uri);
    }
  }
  return fora;
}

function acessor(json, binario, indice) {
  const ac = json.accessors[indice];
  const Tipo = COMPONENTES[ac.componentType];
  const n = ITENS[ac.type];
  if (!Tipo || !n) throw new GlbInvalido(`acessor ${indice} com tipo desconhecido`);
  if (ac.bufferView === undefined) return new Tipo(ac.count * n);
  const vista = json.bufferViews[ac.bufferView];
  const base = (vista.byteOffset || 0) + (ac.byteOffset || 0);
  return new Tipo(binario, base, ac.count * n);
}

function materialDe(json, indice) {
  const m = (json.materials || [])[indice] || {};
  const cor = (m.pbrMetallicRoughness || {}).baseColorFactor || [0.8, 0.8, 0.8, 1];
  return new THREE.MeshLambertMaterial({
    color: new THREE.Color(cor[0], cor[1], cor[2]),
    transparent: cor[3] < 1,
    opacity: cor[3],
    side: m.doubleSided ? THREE.DoubleSide : THREE.FrontSide,
  });
}

function aplicarTransformacao(objeto, no) {
  if (Array.isArray(no.matrix) && no.matrix.length === 16) {
    objeto.applyMatrix4(new THREE.Matrix4().fromArray(no.matrix));
    return;
  }
  if (no.translation) objeto.position.fromArray(no.translation);
  if (no.rotation) objeto.quaternion.fromArray(no.rotation);
  if (no.scale) objeto.scale.fromArray(no.scale);
}

/** Constrói o grafo do three.js. Cada objeto leva em `userData` o que veio de `extras` (o GUID). */
export function montarCena(json, binario) {
  if (recursosExternos(json).length) {
    throw new GlbInvalido('modelo com recurso externo: recusado antes de desenhar');
  }
  const materiais = (json.materials || []).map((_, i) => materialDe(json, i));
  const padrao = materialDe(json, -1);
  const malhaDe = (indiceMalha) => {
    const grupo = new THREE.Group();
    for (const prim of (json.meshes[indiceMalha].primitives || [])) {
      const geometria = new THREE.BufferGeometry();
      const pos = acessor(json, binario, prim.attributes.POSITION);
      geometria.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      if (prim.attributes.NORMAL !== undefined) {
        geometria.setAttribute('normal',
          new THREE.BufferAttribute(acessor(json, binario, prim.attributes.NORMAL), 3));
      }
      if (prim.indices !== undefined) {
        geometria.setIndex(new THREE.BufferAttribute(acessor(json, binario, prim.indices), 1));
      }
      if (prim.attributes.NORMAL === undefined) geometria.computeVertexNormals();
      grupo.add(new THREE.Mesh(geometria, materiais[prim.material] || padrao));
    }
    return grupo;
  };
  const construir = (indice) => {
    const no = json.nodes[indice];
    const objeto = new THREE.Group();
    objeto.name = no.name || `no-${indice}`;
    objeto.userData = { ...(no.extras || {}) };
    aplicarTransformacao(objeto, no);
    if (no.mesh !== undefined) objeto.add(malhaDe(no.mesh));
    for (const filho of no.children || []) objeto.add(construir(filho));
    return objeto;
  };
  const raiz = new THREE.Group();
  const cena = (json.scenes || [])[json.scene || 0] || { nodes: json.nodes.map((_, i) => i) };
  for (const i of cena.nodes || []) raiz.add(construir(i));
  return raiz;
}

export async function carregarGlb(url) {
  const resposta = await fetch(url, { credentials: 'same-origin' });
  if (!resposta.ok) throw new GlbInvalido(`o servidor recusou o modelo (${resposta.status})`);
  const { json, binario } = lerGlb(await resposta.arrayBuffer());
  return { json, raiz: montarCena(json, binario) };
}

export { THREE };
