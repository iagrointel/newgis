"""Monta o GLB a partir dos elementos lidos do IFC.

Um NÓ por elemento, com o identificador global do elemento em `extras` — é assim que o clique na tela
volta a ter significado: o navegador acha o nó pelo raio, lê `extras.guid` e pede as propriedades daquele
GUID à API. Nada de índice posicional (que muda a cada conversão) e nada de extensão proprietária.

O sistema de saída é o do glTF (Y para cima) com a ORIGEM no canto sudoeste-inferior da caixa envolvente
do modelo, em metros: o IFC vem no sistema do projeto (Z para cima, origem arbitrária, às vezes a
milhares de metros da geometria) e mandar isso direto para o navegador custa precisão de float de 32 bits
no exato lugar em que ela dói. O deslocamento aplicado sai em `extras.origem_projeto` do documento glTF,
para quem quiser voltar ao sistema de origem.

Material: uma cor por TIPO IFC, determinística (o mesmo tipo tem a mesma cor em toda conversão). Sem
textura — nenhuma imagem entra, e por isso nenhum recurso externo pode entrar (a regra do `glb`).
"""

from __future__ import annotations

import base64
import struct
import zlib

from app.modelos3d import glb
from app.modelos3d.ifc import Elemento

CORES_POR_TIPO = {
    "IFCWALL": (0.85, 0.83, 0.78),
    "IFCWALLSTANDARDCASE": (0.85, 0.83, 0.78),
    "IFCSLAB": (0.72, 0.72, 0.74),
    "IFCROOF": (0.55, 0.30, 0.25),
    "IFCCOLUMN": (0.60, 0.62, 0.66),
    "IFCBEAM": (0.60, 0.62, 0.66),
    "IFCWINDOW": (0.55, 0.75, 0.88),
    "IFCDOOR": (0.66, 0.48, 0.30),
    "IFCSTAIR": (0.70, 0.68, 0.62),
    "IFCFURNITURE": (0.45, 0.55, 0.45),
}
COR_PADRAO = (0.78, 0.78, 0.80)


def cor_do_tipo(tipo: str) -> tuple[float, float, float]:
    """Cor fixa por tipo; tipo fora da lista recebe um tom estável derivado do próprio nome (nunca aleatório,
    nunca variável entre execuções — duas conversões do mesmo arquivo dão byte a byte o mesmo GLB)."""
    if tipo in CORES_POR_TIPO:
        return CORES_POR_TIPO[tipo]
    semente = zlib.crc32(tipo.encode("utf-8"))
    return (0.55 + ((semente >> 0) & 0xFF) / 640.0,
            0.55 + ((semente >> 8) & 0xFF) / 640.0,
            0.55 + ((semente >> 16) & 0xFF) / 640.0)


def _normais(vertices: list[float], indices: list[int]) -> list[float]:
    """Normal por vértice, média das faces (suavização simples). Vértice sem face fica com Y para cima."""
    n = len(vertices) // 3
    acc = [0.0] * (n * 3)
    for k in range(0, len(indices), 3):
        a, b, c = indices[k], indices[k + 1], indices[k + 2]
        if max(a, b, c) >= n:
            continue
        pa, pb, pc = vertices[a * 3:a * 3 + 3], vertices[b * 3:b * 3 + 3], vertices[c * 3:c * 3 + 3]
        u = [pb[i] - pa[i] for i in range(3)]
        v = [pc[i] - pa[i] for i in range(3)]
        w = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        for vert in (a, b, c):
            for i in range(3):
                acc[vert * 3 + i] += w[i]
    saida = []
    for i in range(n):
        x, y, z = acc[i * 3:i * 3 + 3]
        m = (x * x + y * y + z * z) ** 0.5
        saida += [x / m, y / m, z / m] if m > 1e-12 else [0.0, 1.0, 0.0]
    return saida


def montar(elementos: list[Elemento], nome: str = "modelo") -> tuple[bytes, dict]:
    """Devolve (bytes do GLB, resumo). O resumo diz quantos elementos entraram com forma e qual a caixa."""
    com_forma = [e for e in elementos if e.tem_geometria]
    if not com_forma:
        raise ValueError("nenhum elemento com geometria: não há GLB a montar")

    # deslocamento: origem no canto mínimo, para o navegador não trabalhar com coordenada de projeto grande
    minimo = [min(min(e.vertices[i::3]) for e in com_forma) for i in range(3)]

    binario = bytearray()
    vistas: list[dict] = []
    acessores: list[dict] = []
    malhas: list[dict] = []
    nos: list[dict] = []
    materiais: list[dict] = []
    material_do_tipo: dict[str, int] = {}

    def alinhar(quanto: int = 4) -> None:
        while len(binario) % quanto:
            binario.append(0)

    def guardar(dados: bytes, alvo: int | None = None) -> int:
        alinhar()
        deslocamento = len(binario)
        binario.extend(dados)
        vista = {"buffer": 0, "byteOffset": deslocamento, "byteLength": len(dados)}
        if alvo:
            vista["target"] = alvo
        vistas.append(vista)
        return len(vistas) - 1

    for elemento in com_forma:
        # IFC é Z para cima; glTF é Y para cima: (x, y, z)_ifc -> (x, z, -y)_gltf
        pos = []
        for k in range(0, len(elemento.vertices), 3):
            x = elemento.vertices[k] - minimo[0]
            y = elemento.vertices[k + 1] - minimo[1]
            z = elemento.vertices[k + 2] - minimo[2]
            pos += [x, z, -y]
        nor = _normais(pos, elemento.indices)
        n_vert = len(pos) // 3
        i_pos = guardar(struct.pack(f"<{len(pos)}f", *pos), 34962)
        i_nor = guardar(struct.pack(f"<{len(nor)}f", *nor), 34962)
        usar_int = n_vert > 65535
        fmt = "I" if usar_int else "H"
        i_idx = guardar(struct.pack(f"<{len(elemento.indices)}{fmt}", *elemento.indices), 34963)
        acessores.append({"bufferView": i_pos, "componentType": 5126, "count": n_vert, "type": "VEC3",
                          "min": [min(pos[i::3]) for i in range(3)],
                          "max": [max(pos[i::3]) for i in range(3)]})
        acessores.append({"bufferView": i_nor, "componentType": 5126, "count": n_vert, "type": "VEC3"})
        acessores.append({"bufferView": i_idx, "componentType": 5125 if usar_int else 5123,
                          "count": len(elemento.indices), "type": "SCALAR"})
        if elemento.tipo not in material_do_tipo:
            r, g, b = cor_do_tipo(elemento.tipo)
            materiais.append({"name": elemento.tipo, "doubleSided": True,
                              "pbrMetallicRoughness": {"baseColorFactor": [round(r, 4), round(g, 4),
                                                                           round(b, 4), 1.0],
                                                       "metallicFactor": 0.0, "roughnessFactor": 0.9}})
            material_do_tipo[elemento.tipo] = len(materiais) - 1
        base = len(acessores) - 3
        malhas.append({"primitives": [{"attributes": {"POSITION": base, "NORMAL": base + 1},
                                       "indices": base + 2, "material": material_do_tipo[elemento.tipo],
                                       "mode": 4}]})
        nos.append({"name": (elemento.nome or elemento.guid)[:200], "mesh": len(malhas) - 1,
                    "extras": {"guid": elemento.guid, "tipo": elemento.tipo,
                               "pavimento": elemento.pavimento}})

    gltf = {
        "asset": {"version": "2.0", "generator": "plat/modelos3d"},
        "scene": 0,
        "scenes": [{"name": nome[:200], "nodes": list(range(len(nos)))}],
        "nodes": nos,
        "meshes": malhas,
        "materials": materiais,
        "accessors": acessores,
        "bufferViews": vistas,
        "buffers": [{"byteLength": len(binario)}],
        "extras": {"origem_projeto": [round(v, 6) for v in minimo],
                   "elementos": len(com_forma)},
    }
    dados = glb.escrever(gltf, bytes(binario))
    minimo_gltf, maximo_gltf = glb.caixa(gltf, bytes(binario))
    return dados, {
        "elementos_com_forma": len(com_forma),
        "elementos": len(elementos),
        "bytes": len(dados),
        "caixa_minima": [round(v, 4) for v in minimo_gltf],
        "caixa_maxima": [round(v, 4) for v in maximo_gltf],
        "origem_projeto": [round(v, 6) for v in minimo],
    }


def caixa_glb(dados: bytes) -> tuple[list[float], list[float]]:
    gltf, binario = glb.ler(dados)
    glb.exigir_embutido(gltf)
    return glb.caixa(gltf, binario)


def data_uri(dados: bytes, tipo: str = "model/gltf-binary") -> str:
    return f"data:{tipo};base64," + base64.b64encode(dados).decode("ascii")


__all__ = ["montar", "cor_do_tipo", "caixa_glb", "data_uri", "CORES_POR_TIPO"]
