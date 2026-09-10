"""Bancada dos testes do item L2-09-c: um GLB pequeno, gerado na hora, e o IFC aberto da buildingSMART.

O GLB é uma CAIXA de dimensões declaradas (`LARGURA_M`, `ALTURA_M`, `PROFUNDIDADE_M`), montada pelo mesmo
`app/modelos3d/glb.py` que a aplicação usa para ler. Gerar em vez de versionar um binário: a caixa tem
dimensão conhecida ao milímetro, e é isso que faz a cláusula do portão ("aparece na posição e escala
corretas, com folga de 0,5 m") ser uma medida e não uma impressão.

O IFC é `tests/dados/Building-Architecture.ifc`, arquivo público da buildingSMART International
(CC BY 4.0), citado com endereço e sha256 em `tests/dados/FONTES_MODELOS3D.md`.

Ponto no globo: o vértice geodésico do IBGE em São Paulo usado pelas outras bancadas desta linha; é dado
aberto e nunca endereço de cliente.
"""

from __future__ import annotations

import struct
from pathlib import Path

from app.modelos3d import glb

RAIZ = Path(__file__).resolve().parents[1]
IFC_ABERTO = RAIZ / "tests" / "dados" / "Building-Architecture.ifc"

LON = -46.633308
LAT = -23.550520
ALTURA_M = 760.0

LARGURA_M = 12.0     # eixo X do modelo (leste, antes da rotação)
CAIXA_ALTURA_M = 8.0  # eixo Y do modelo (para cima)
PROFUNDIDADE_M = 20.0  # eixo Z do modelo (-Z é o norte)


def caixa_vertices(largura=LARGURA_M, altura=CAIXA_ALTURA_M, profundidade=PROFUNDIDADE_M):
    """8 vértices de uma caixa com o canto mínimo na origem do modelo."""
    return [(x, y, z) for z in (-profundidade, 0.0) for y in (0.0, altura) for x in (0.0, largura)]


_FACES = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
          (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]


def glb_caixa(nome: str = "caixa-de-teste", guid: str = "0CAIXA0000000000000001") -> bytes:
    """GLB de uma caixa, com `extras.guid` no nó (é por ele que o clique acha o elemento)."""
    vertices = caixa_vertices()
    posicoes = b"".join(struct.pack("<3f", *v) for v in vertices)
    indices = b"".join(struct.pack("<3H", *f) for f in _FACES)
    binario = posicoes + indices + b"\x00" * ((4 - len(indices) % 4) % 4)
    minimo = [min(v[i] for v in vertices) for i in range(3)]
    maximo = [max(v[i] for v in vertices) for i in range(3)]
    gltf = {
        "asset": {"version": "2.0", "generator": "plat/testes"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": nome, "mesh": 0, "extras": {"guid": guid, "tipo": "IFCBUILDINGELEMENTPROXY"}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0, "mode": 4}]}],
        "materials": [{"name": "teste", "doubleSided": True,
                       "pbrMetallicRoughness": {"baseColorFactor": [0.9, 0.4, 0.2, 1.0],
                                                "metallicFactor": 0.0, "roughnessFactor": 0.9}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3",
             "min": minimo, "max": maximo},
            {"bufferView": 1, "componentType": 5123, "count": len(_FACES) * 3, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(posicoes), "target": 34962},
            {"buffer": 0, "byteOffset": len(posicoes), "byteLength": len(indices), "target": 34963},
        ],
        "buffers": [{"byteLength": len(binario)}],
    }
    return glb.escrever(gltf, binario)


def glb_com_textura_externa() -> bytes:
    """O mesmo GLB, mas apontando uma imagem para FORA do arquivo: tem de ser recusado (refutação do item)."""
    dados = glb_caixa()
    gltf, binario = glb.ler(dados)
    gltf["images"] = [{"uri": "https://exemplo.invalido/textura.png"}]
    gltf["samplers"] = [{}]
    gltf["textures"] = [{"source": 0, "sampler": 0}]
    return glb.escrever(gltf, binario)


__all__ = ["glb_caixa", "glb_com_textura_externa", "caixa_vertices", "IFC_ABERTO", "LON", "LAT", "ALTURA_M",
           "LARGURA_M", "CAIXA_ALTURA_M", "PROFUNDIDADE_M"]
