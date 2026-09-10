"""Geração de OGC 3D Tiles 1.1 (Community Standard 18-053r2) a partir de um GLB.

Por que gerar aqui e não chamar a ferramenta de linha de comando: o `3d-tiles-tools` (Apache-2.0, Node)
é excelente e é o VALIDADOR que a casa usa para conferir o que sai daqui (`scripts/tiles3d_validar.sh`),
mas exigi-lo em PRODUÇÃO significaria pôr um runtime Node dentro do trabalhador da fila só para escrever
um `tileset.json` e recortar nós de um glTF que já está aberto na memória. O padrão 1.1 admite glTF/GLB
como conteúdo de tile diretamente (não é preciso b3dm, que é 1.0), então o gerador cabe em umas poucas
dezenas de linhas sobre o módulo `glb` que já existe. A conferência independente continua sendo do
validador oficial — é ele que reprova o que este arquivo escreveu, não um teste que se olha no espelho.
(ADR do item, decisão 3.)

Desenho da árvore: raiz com `transform` geocêntrico (posicionamento.matriz_ecef) e refinamento `ADD`;
os filhos são quadrantes no plano horizontal, divididos enquanto o número de nós do quadrante passar de
`NOS_POR_TILE` e a profundidade for menor que `PROFUNDIDADE_MAXIMA`. Cada folha carrega um GLB com os
nós daquele quadrante — os mesmos nós do modelo original, com `extras.guid` intacto, para o clique
continuar significando alguma coisa depois do recorte.

`geometricError`: metade da diagonal horizontal da caixa do tile, dividido por 16 — é uma regra
declarada, não medida, e está dita assim no `tileset.json` (`extras.criterio_erro_geometrico`).
"""

from __future__ import annotations

import json
import math

from app.modelos3d import glb, posicionamento

NOS_POR_TILE = 64
PROFUNDIDADE_MAXIMA = 4
DIVISOR_ERRO = 16.0
VERSAO = "1.1"


def _centro_do_no(gltf: dict, binario: bytes, indice: int) -> tuple[float, float, float]:
    caixa = _caixa_do_no(gltf, binario, indice)
    return tuple((caixa[0][i] + caixa[1][i]) / 2 for i in range(3))


def _caixa_do_no(gltf: dict, binario: bytes, indice: int) -> tuple[list[float], list[float]]:
    recorte = dict(gltf)
    recorte["scenes"] = [{"nodes": [indice]}]
    recorte["scene"] = 0
    return glb.caixa(recorte, binario)


def _uniao(caixas):
    minimo = [min(c[0][i] for c in caixas) for i in range(3)]
    maximo = [max(c[1][i] for c in caixas) for i in range(3)]
    return minimo, maximo


def _caixa_zup(minimo, maximo) -> list[float]:
    """`boundingVolume.box` do 3D Tiles, no sistema Z-para-cima do tile.

    O conteúdo é glTF (Y para cima) e o cliente aplica a troca Y->Z antes do `transform`; a caixa tem de
    estar no sistema JÁ trocado: (x, y, z) do glTF vira (x, -z, y)."""
    def troca(p):
        return (p[0], -p[2], p[1])
    a, b = troca(minimo), troca(maximo)
    lo = [min(a[i], b[i]) for i in range(3)]
    hi = [max(a[i], b[i]) for i in range(3)]
    centro = [(lo[i] + hi[i]) / 2 for i in range(3)]
    meio = [max((hi[i] - lo[i]) / 2, 1e-6) for i in range(3)]
    return [centro[0], centro[1], centro[2], meio[0], 0.0, 0.0, 0.0, meio[1], 0.0, 0.0, 0.0, meio[2]]


def _erro(minimo, maximo) -> float:
    diagonal = math.hypot(maximo[0] - minimo[0], maximo[2] - minimo[2])
    return round(max(diagonal / DIVISOR_ERRO, 0.0), 4)


def _recorte(gltf: dict, binario: bytes, indices: list[int]) -> bytes:
    """GLB só com os nós pedidos. O binário inteiro viaja junto (as vistas de buffer apontam para ele);
    trocar isso por um binário podado seria otimização não pedida — o tamanho já cai com a divisão."""
    novo = {k: v for k, v in gltf.items() if k not in ("scenes", "scene")}
    novo["scenes"] = [{"nodes": list(indices)}]
    novo["scene"] = 0
    return glb.escrever(novo, binario)


def _dividir(gltf, binario, indices, caixas, profundidade) -> list[dict]:
    """Devolve a lista de folhas: cada uma {indices, minimo, maximo}."""
    minimo, maximo = _uniao([caixas[i] for i in indices])
    if len(indices) <= NOS_POR_TILE or profundidade >= PROFUNDIDADE_MAXIMA:
        return [{"indices": indices, "minimo": minimo, "maximo": maximo}]
    meio_x = (minimo[0] + maximo[0]) / 2
    meio_z = (minimo[2] + maximo[2]) / 2
    baldes: dict[int, list[int]] = {}
    for i in indices:
        c = [(caixas[i][0][k] + caixas[i][1][k]) / 2 for k in range(3)]
        baldes.setdefault((1 if c[0] > meio_x else 0) | (2 if c[2] > meio_z else 0), []).append(i)
    if len(baldes) < 2:  # tudo caiu no mesmo quadrante: dividir mais não separa nada
        return [{"indices": indices, "minimo": minimo, "maximo": maximo}]
    folhas: list[dict] = []
    for grupo in baldes.values():
        folhas += _dividir(gltf, binario, grupo, caixas, profundidade + 1)
    return folhas


def gerar(dados_glb: bytes, lon: float, lat: float, altura: float = 0.0, rotacao: float = 0.0,
          escala: float = 1.0, nome: str = "modelo") -> tuple[dict, dict[str, bytes]]:
    """(tileset, {caminho relativo: bytes}). O tileset referencia os conteúdos por caminho RELATIVO, que é
    o que faz a mesma árvore servir por qualquer URL sem reescrita."""
    gltf, binario = glb.ler(dados_glb)
    glb.exigir_embutido(gltf)
    nos = gltf.get("nodes") or []
    cenas = gltf.get("scenes") or []
    raizes = list(cenas[int(gltf.get("scene", 0))].get("nodes", [])) if cenas else list(range(len(nos)))
    raizes = [i for i in raizes if int(i) < len(nos)]
    if not raizes:
        raise glb.GlbInvalido("GLB sem nó na cena: não há o que empacotar em 3D Tiles")
    caixas = {int(i): _caixa_do_no(gltf, binario, int(i)) for i in raizes}
    folhas = _dividir(gltf, binario, [int(i) for i in raizes], caixas, 0)

    conteudos: dict[str, bytes] = {}
    filhos: list[dict] = []
    for n, folha in enumerate(folhas):
        caminho = f"conteudo/{n}.glb"
        conteudos[caminho] = _recorte(gltf, binario, folha["indices"])
        filhos.append({
            "boundingVolume": {"box": _caixa_zup(folha["minimo"], folha["maximo"])},
            "geometricError": 0.0,
            "content": {"uri": caminho},
        })
    minimo, maximo = _uniao(list(caixas.values()))
    if escala != 1.0:
        minimo = [v * escala for v in minimo]
        maximo = [v * escala for v in maximo]
        for filho in filhos:
            filho["boundingVolume"]["box"] = [v * escala for v in filho["boundingVolume"]["box"]]
    raiz_erro = _erro(minimo, maximo)
    tileset = {
        "asset": {"version": VERSAO, "generator": "plat/modelos3d"},
        "geometricError": raiz_erro,
        "root": {
            "transform": _transform(lon, lat, altura, rotacao, escala),
            "boundingVolume": {"box": _caixa_zup(minimo, maximo)},
            "geometricError": raiz_erro,
            "refine": "ADD",
            "children": filhos,
        },
        "extras": {
            "nome": nome[:200],
            "criterio_erro_geometrico": "diagonal horizontal da caixa dividida por 16 (regra declarada, "
                                        "não medida)",
            "nos": len(raizes),
            "tiles": len(filhos),
        },
    }
    return tileset, conteudos


def _transform(lon: float, lat: float, altura: float, rotacao: float, escala: float) -> list[float]:
    """ECEF do ponto, com a rotação em torno da vertical e a escala do modelo já embutidas."""
    m = posicionamento.matriz_ecef(lon, lat, altura)
    a = math.radians(rotacao)
    sen, cos = math.sin(a), math.cos(a)
    # giro horário a partir do norte no plano leste-norte, e escala uniforme
    giro = [cos * escala, -sen * escala, 0.0, 0.0,
            sen * escala, cos * escala, 0.0, 0.0,
            0.0, 0.0, escala, 0.0,
            0.0, 0.0, 0.0, 1.0]
    return [round(v, 9) for v in glb.multiplicar(m, giro)]


def escrever_json(tileset: dict) -> bytes:
    return json.dumps(tileset, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


__all__ = ["gerar", "escrever_json", "NOS_POR_TILE", "PROFUNDIDADE_MAXIMA", "VERSAO"]
