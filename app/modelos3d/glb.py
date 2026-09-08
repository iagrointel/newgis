"""glTF 2.0 binário (GLB): leitura, escrita, recusa de recurso externo e caixa envolvente.

Por que um leitor próprio e não uma biblioteca: o repositório não tem nenhuma dependência de glTF e a
parte do formato que a plataforma usa é pequena e fechada — recipiente GLB (cabeçalho de 12 bytes + os
pedaços JSON e BIN), nós com matriz ou TRS, malhas com POSITION/NORMAL e índices, e material com cor
base. Ler isso é a escada do PONYTAIL parando no degrau da biblioteca padrão (`struct`, `json`); trazer
um pacote novo por causa disso custaria mais do que resolve (ADR do item, seção 2).

Regra de segurança que este módulo carrega (refutação do item): **modelo com recurso externo é
recusado**. Um GLB que aponta `uri` de textura ou de buffer para fora de si mesmo faz o navegador do
usuário buscar aquele endereço — servidor de terceiro escolhido por quem enviou o arquivo. Ou o recurso
está embutido (`data:`) ou o modelo não entra. `recursos_externos()` devolve a lista; `exigir_embutido()`
levanta `GlbInvalido`.
"""

from __future__ import annotations

import base64
import json
import struct

MAGICO = 0x46546C67  # "glTF"
JSON_PEDACO = 0x4E4F534A
BIN_PEDACO = 0x004E4942
CABECALHO = 12
PEDACO = 8

# componentType do glTF -> (formato do struct, bytes)
COMPONENTES = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
ITENS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GlbInvalido(ValueError):
    """Arquivo que não é um GLB válido, ou que é válido mas a plataforma recusa (recurso externo)."""


def ler(dados: bytes) -> tuple[dict, bytes]:
    """Devolve (json do glTF, bytes do pedaço BIN). Levanta `GlbInvalido` em qualquer desvio do formato."""
    if len(dados) < CABECALHO:
        raise GlbInvalido("arquivo menor que o cabeçalho GLB (12 bytes)")
    magico, versao, total = struct.unpack_from("<III", dados, 0)
    if magico != MAGICO:
        raise GlbInvalido("assinatura glTF ausente: o arquivo não é um GLB")
    if versao != 2:
        raise GlbInvalido(f"GLB versão {versao}: só a versão 2 é aceita")
    if total != len(dados):
        raise GlbInvalido(f"tamanho declarado ({total}) diferente do tamanho real ({len(dados)})")
    corpo: dict | None = None
    binario = b""
    passo = CABECALHO
    while passo + PEDACO <= len(dados):
        tamanho, tipo = struct.unpack_from("<II", dados, passo)
        inicio = passo + PEDACO
        fim = inicio + tamanho
        if fim > len(dados):
            raise GlbInvalido("pedaço declara tamanho maior que o arquivo")
        if tipo == JSON_PEDACO and corpo is None:
            try:
                corpo = json.loads(dados[inicio:fim].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise GlbInvalido(f"pedaço JSON ilegível: {e}") from e
        elif tipo == BIN_PEDACO and not binario:
            binario = bytes(dados[inicio:fim])
        passo = fim + ((4 - tamanho % 4) % 4)
    if not isinstance(corpo, dict):
        raise GlbInvalido("GLB sem pedaço JSON")
    return corpo, binario


def escrever(gltf: dict, binario: bytes = b"") -> bytes:
    """Monta o GLB. Cada pedaço vai alinhado a 4 bytes, como o formato exige (JSON com espaço, BIN com zero)."""
    texto = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    texto += b" " * ((4 - len(texto) % 4) % 4)
    corpo_bin = binario + b"\x00" * ((4 - len(binario) % 4) % 4)
    total = CABECALHO + PEDACO + len(texto) + (PEDACO + len(corpo_bin) if corpo_bin else 0)
    partes = [struct.pack("<III", MAGICO, 2, total), struct.pack("<II", len(texto), JSON_PEDACO), texto]
    if corpo_bin:
        partes += [struct.pack("<II", len(corpo_bin), BIN_PEDACO), corpo_bin]
    return b"".join(partes)


def recursos_externos(gltf: dict) -> list[str]:
    """URIs que o modelo manda o navegador buscar fora do arquivo (buffer, imagem). `data:` não conta."""
    fora: list[str] = []
    for chave in ("buffers", "images"):
        for recurso in gltf.get(chave, []) or []:
            uri = recurso.get("uri") if isinstance(recurso, dict) else None
            if isinstance(uri, str) and uri and not uri.startswith("data:"):
                fora.append(uri)
    return fora


def exigir_embutido(gltf: dict) -> None:
    fora = recursos_externos(gltf)
    if fora:
        raise GlbInvalido(
            "modelo com recurso externo (o navegador buscaria em outro servidor): "
            + ", ".join(sorted(set(fora))[:5])
        )


# ------------------------------------------------------------------ leitura de acessor
def _bytes_do_buffer(gltf: dict, binario: bytes, indice: int) -> bytes:
    buffers = gltf.get("buffers") or []
    if indice >= len(buffers):
        raise GlbInvalido(f"buffer {indice} inexistente")
    uri = buffers[indice].get("uri")
    if not uri:
        return binario
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    raise GlbInvalido("buffer externo: use exigir_embutido() antes de ler")


def ler_acessor(gltf: dict, binario: bytes, indice: int) -> list[tuple]:
    """Devolve os elementos do acessor como tuplas (VEC3 -> tuplas de 3). Só o subconjunto sem esparso."""
    acessores = gltf.get("accessors") or []
    if indice >= len(acessores):
        raise GlbInvalido(f"acessor {indice} inexistente")
    ac = acessores[indice]
    formato, largura = COMPONENTES.get(ac.get("componentType"), (None, 0))
    if formato is None:
        raise GlbInvalido(f"componentType {ac.get('componentType')} desconhecido")
    n_itens = ITENS.get(ac.get("type"), 0)
    if not n_itens:
        raise GlbInvalido(f"type {ac.get('type')} desconhecido")
    quantidade = int(ac.get("count", 0))
    vistas = gltf.get("bufferViews") or []
    iv = ac.get("bufferView")
    if iv is None:
        return [tuple([0] * n_itens)] * quantidade
    vista = vistas[iv]
    dados = _bytes_do_buffer(gltf, binario, int(vista.get("buffer", 0)))
    base = int(vista.get("byteOffset", 0)) + int(ac.get("byteOffset", 0))
    passo = int(vista.get("byteStride") or (largura * n_itens))
    saida = []
    for i in range(quantidade):
        pos = base + i * passo
        if pos + largura * n_itens > len(dados):
            raise GlbInvalido("acessor aponta para fora do buffer")
        saida.append(struct.unpack_from("<" + formato * n_itens, dados, pos))
    return saida


# ------------------------------------------------------------------ caixa envolvente
def _matriz_do_no(no: dict) -> list[float]:
    """4x4 em ordem de COLUNA (convenção do glTF). Matriz explícita ganha de T/R/S, como o formato manda."""
    if "matrix" in no and isinstance(no["matrix"], list) and len(no["matrix"]) == 16:
        return [float(v) for v in no["matrix"]]
    t = [float(v) for v in no.get("translation", [0, 0, 0])]
    r = [float(v) for v in no.get("rotation", [0, 0, 0, 1])]  # quatérnio x,y,z,w
    s = [float(v) for v in no.get("scale", [1, 1, 1])]
    x, y, z, w = r
    rot = [
        1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
        2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
        2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y),
    ]
    m = [0.0] * 16
    for c in range(3):
        for l in range(3):  # noqa: E741 — l de linha; o alfabeto do domínio é português
            m[c * 4 + l] = rot[c * 3 + l] * s[c]
    m[12], m[13], m[14], m[15] = t[0], t[1], t[2], 1.0
    return m


def multiplicar(a: list[float], b: list[float]) -> list[float]:
    """a*b, as duas em ordem de coluna (o resultado aplica b primeiro, depois a)."""
    fora = [0.0] * 16
    for c in range(4):
        for l in range(4):  # noqa: E741
            fora[c * 4 + l] = sum(a[k * 4 + l] * b[c * 4 + k] for k in range(4))
    return fora


def aplicar(m: list[float], p: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


IDENTIDADE = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _cantos(minimo: list[float], maximo: list[float]) -> list[tuple[float, float, float]]:
    return [(minimo[0] if i & 1 else maximo[0], minimo[1] if i & 2 else maximo[1],
             minimo[2] if i & 4 else maximo[2]) for i in range(8)]


def caixa(gltf: dict, binario: bytes = b"") -> tuple[list[float], list[float]]:
    """Caixa envolvente do modelo no sistema do glTF (Y para cima), já com a matriz de cada nó aplicada.

    Usa `min`/`max` do acessor de POSITION, que o formato exige que estejam lá; quando faltam (arquivo
    fora do padrão), mede lendo os vértices. Nunca supõe: sem malha nenhuma, levanta."""
    minimo = [float("inf")] * 3
    maximo = [float("-inf")] * 3
    malhas = gltf.get("meshes") or []
    acessores = gltf.get("accessors") or []
    nos = gltf.get("nodes") or []

    def visitar(indice: int, pai: list[float]) -> None:
        no = nos[indice]
        m = multiplicar(pai, _matriz_do_no(no))
        i_malha = no.get("mesh")
        if i_malha is not None and i_malha < len(malhas):
            for prim in malhas[i_malha].get("primitives", []):
                ia = (prim.get("attributes") or {}).get("POSITION")
                if ia is None or ia >= len(acessores):
                    continue
                ac = acessores[ia]
                if isinstance(ac.get("min"), list) and isinstance(ac.get("max"), list):
                    pontos = _cantos([float(v) for v in ac["min"]], [float(v) for v in ac["max"]])
                else:
                    pontos = [tuple(float(v) for v in p) for p in ler_acessor(gltf, binario, ia)]
                for p in pontos:
                    q = aplicar(m, p)
                    for eixo in range(3):
                        minimo[eixo] = min(minimo[eixo], q[eixo])
                        maximo[eixo] = max(maximo[eixo], q[eixo])
        for filho in no.get("children", []) or []:
            visitar(int(filho), m)

    cenas = gltf.get("scenes") or []
    raizes = cenas[int(gltf.get("scene", 0))].get("nodes", []) if cenas else range(len(nos))
    for r in raizes:
        visitar(int(r), IDENTIDADE)
    if minimo[0] == float("inf"):
        raise GlbInvalido("modelo sem geometria: nenhuma malha com POSITION")
    return minimo, maximo


__all__ = ["GlbInvalido", "ler", "escrever", "recursos_externos", "exigir_embutido", "ler_acessor", "caixa",
           "multiplicar", "aplicar", "IDENTIDADE"]
