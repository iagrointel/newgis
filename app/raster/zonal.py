"""Estatísticas zonais sobre COG remoto, janela por janela (item L2-05-e).

O que este módulo faz e o que NÃO faz:

* lê SÓ a janela de cada zona, e a janela em faixas de no máximo `FAIXA_LINHAS` linhas — o consumo de
  memória depende da largura da zona e da faixa, nunca do tamanho do arquivo. É por isso que um raster
  de dezenas de gigabytes é processado com centenas de megabytes de RSS;
* pondera cada pixel pela FRAÇÃO da sua área coberta pelo polígono (`fracao=True`, padrão), medida
  rasterizando a zona num sub-pixel de `SUBPIXEL`×`SUBPIXEL` com `rasterio.features.rasterize` e tirando
  a média do bloco. O `exactextract`, que faz isso por geometria exata, NÃO está instalado nesta
  máquina, e a fração por sub-pixel é a aproximação declarada no lugar dele: com `SUBPIXEL=5` o peso de
  um pixel de borda erra no máximo 1/25 da sua área;
* com `fracao=False` o critério passa a ser o do `rasterstats`/ArcGIS clássico — pixel entra inteiro se
  o CENTRO cai dentro do polígono. É esse o modo que reproduz o `rasterstats` pixel a pixel;
* `todos_pixels=True` é o `all_touched` do GDAL: todo pixel tocado entra com peso 1 (só faz sentido com
  `fracao=False`, e as zonas menores que um pixel dependem dele para não ficarem vazias).

Mediana, majoritário e percentual por classe saem de um histograma acumulado quando o tipo é inteiro
(exatos, memória constante); em ponto flutuante a mediana precisa dos valores, e por isso existe teto
(`PIXELS_MEDIANA_MAX`): acima dele a ferramenta recusa a mediana em vez de encher a memória em silêncio.
"""

from __future__ import annotations

import math

import numpy as np
from rasterio import features, windows

FAIXA_LINHAS = 64          # altura máxima da faixa lida de uma vez dentro da janela da zona
SUBPIXEL = 5               # lado do bloco de amostragem da fração de pixel (25 amostras por pixel)
PIXELS_MEDIANA_MAX = 20_000_000   # teto de valores guardados para mediana de raster em ponto flutuante
ESTATISTICAS = ("contagem", "soma", "media", "minimo", "maximo", "desvio", "mediana", "majoritario", "classes")


class ZonaGrande(ValueError):
    """A zona tem mais pixels válidos do que o teto declarado para a estatística pedida."""


def _janela_da_zona(ds, limites: tuple[float, float, float, float]) -> windows.Window | None:
    """Janela inteira do dataset que cobre os limites da zona; None quando não há interseção."""
    x0, y0, x1, y1 = limites
    if x1 <= ds.bounds.left or x0 >= ds.bounds.right or y1 <= ds.bounds.bottom or y0 >= ds.bounds.top:
        return None
    j = windows.from_bounds(x0, y0, x1, y1, transform=ds.transform)
    j = j.round_offsets(op="floor").round_lengths(op="ceil")
    # uma orla de um pixel: a fração de borda precisa do pixel que o limite só encosta
    j = windows.Window(j.col_off - 1, j.row_off - 1, j.width + 2, j.height + 2)
    inteira = windows.Window(0, 0, ds.width, ds.height)
    j = j.intersection(inteira) if windows.intersect(j, inteira) else None
    if j is None or j.width <= 0 or j.height <= 0:
        return None
    return j


def _pesos(geometria: dict, faixa: windows.Window, transform, fracao: bool, todos_pixels: bool) -> np.ndarray:
    """Peso de cada pixel da faixa em [0, 1]."""
    forma = (int(faixa.height), int(faixa.width))
    if not fracao:
        m = features.rasterize([(geometria, 1)], out_shape=forma, transform=transform, fill=0,
                               all_touched=todos_pixels, dtype="uint8")
        return m.astype("float32")
    fina = transform * transform.scale(1.0 / SUBPIXEL, 1.0 / SUBPIXEL)
    m = features.rasterize([(geometria, 1)], out_shape=(forma[0] * SUBPIXEL, forma[1] * SUBPIXEL),
                           transform=fina, fill=0, all_touched=False, dtype="uint8")
    return m.reshape(forma[0], SUBPIXEL, forma[1], SUBPIXEL).mean(axis=(1, 3)).astype("float32")


class _Acumulador:
    """Soma ponderada, extremos e histograma; nada guarda o raster inteiro."""

    def __init__(self, inteiro: bool, precisa_mediana: bool, precisa_classes: bool):
        self.inteiro = inteiro
        self.precisa_mediana = precisa_mediana
        self.precisa_classes = precisa_classes
        self.peso = 0.0
        self.pixels = 0
        self.soma = 0.0
        self.soma2 = 0.0
        self.minimo = None
        self.maximo = None
        self.hist: dict[int, float] = {}
        self.valores: list[np.ndarray] = []
        self.pesos: list[np.ndarray] = []
        self.guardados = 0

    def somar(self, valores: np.ndarray, pesos: np.ndarray) -> None:
        if valores.size == 0:
            return
        v = valores.astype("float64", copy=False)
        p = pesos.astype("float64", copy=False)
        self.peso += float(p.sum())
        self.pixels += int((p > 0).sum())
        self.soma += float((v * p).sum())
        self.soma2 += float((v * v * p).sum())
        vmin, vmax = float(v.min()), float(v.max())
        self.minimo = vmin if self.minimo is None else min(self.minimo, vmin)
        self.maximo = vmax if self.maximo is None else max(self.maximo, vmax)
        if self.inteiro and (self.precisa_mediana or self.precisa_classes):
            chaves = valores.astype("int64", copy=False)
            for chave, peso in zip(*_agrupar(chaves, p), strict=True):
                self.hist[int(chave)] = self.hist.get(int(chave), 0.0) + float(peso)
        elif self.precisa_mediana:
            self.guardados += v.size
            if self.guardados > PIXELS_MEDIANA_MAX:
                raise ZonaGrande(
                    f"zona com mais de {PIXELS_MEDIANA_MAX} pixels válidos em raster de ponto flutuante: "
                    "peça as estatísticas sem 'mediana' ou recorte o raster antes"
                )
            self.valores.append(v.copy())
            self.pesos.append(p.copy())

    def mediana(self) -> float | None:
        if self.peso <= 0:
            return None
        if self.inteiro:
            itens = sorted(self.hist.items())
            alvo, soma = self.peso / 2.0, 0.0
            for valor, peso in itens:
                soma += peso
                if soma >= alvo:
                    return float(valor)
            return float(itens[-1][0]) if itens else None
        v = np.concatenate(self.valores)
        p = np.concatenate(self.pesos)
        ordem = np.argsort(v, kind="stable")
        v, p = v[ordem], p[ordem]
        acumulado = np.cumsum(p)
        i = int(np.searchsorted(acumulado, self.peso / 2.0))
        return float(v[min(i, v.size - 1)])

    def classes(self) -> dict | None:
        if not self.precisa_classes or self.peso <= 0:
            return None
        return {str(int(k)): round(100.0 * v / self.peso, 6) for k, v in sorted(self.hist.items())}

    def majoritario(self) -> float | None:
        if not self.hist:
            return None
        return float(max(self.hist.items(), key=lambda kv: (kv[1], -kv[0]))[0])


def _agrupar(chaves: np.ndarray, pesos: np.ndarray):
    """(valores distintos, peso somado) — `np.unique` com soma por grupo, sem laço em Python por pixel."""
    ordem = np.argsort(chaves, kind="stable")
    c, p = chaves[ordem], pesos[ordem]
    limites = np.flatnonzero(np.diff(c)) + 1
    inicio = np.concatenate(([0], limites))
    somas = np.add.reduceat(p, inicio)
    return c[inicio], somas


def estatisticas_da_zona(ds, banda: int, geometria: dict, limites, pedidas: tuple[str, ...], *,
                         fracao: bool = True, todos_pixels: bool = False, nodata=None) -> dict:
    """Estatísticas de UMA zona. `geometria` em GeoJSON no CRS do raster; `limites` os seus bounds."""
    precisa_mediana = "mediana" in pedidas
    precisa_classes = "classes" in pedidas or "majoritario" in pedidas
    nd = ds.nodatavals[banda - 1] if nodata is None else nodata
    inteiro = np.dtype(ds.dtypes[banda - 1]).kind in "iub"
    acc = _Acumulador(inteiro, precisa_mediana, precisa_classes)
    janela = _janela_da_zona(ds, limites)
    if janela is not None:
        for topo in range(0, int(janela.height), FAIXA_LINHAS):
            altura = min(FAIXA_LINHAS, int(janela.height) - topo)
            faixa = windows.Window(janela.col_off, janela.row_off + topo, janela.width, altura)
            transform = ds.window_transform(faixa)
            peso = _pesos(geometria, faixa, transform, fracao, todos_pixels)
            if not peso.any():
                continue
            dados = ds.read(banda, window=faixa)
            valido = peso > 0
            if nd is not None:
                valido &= dados != nd
            if np.dtype(dados.dtype).kind == "f":
                valido &= np.isfinite(dados)
            if not valido.any():
                continue
            acc.somar(dados[valido], peso[valido])
    return _resultado(acc, pedidas)


def _resultado(acc: _Acumulador, pedidas: tuple[str, ...]) -> dict:
    media = acc.soma / acc.peso if acc.peso > 0 else None
    variancia = (acc.soma2 / acc.peso - media * media) if acc.peso > 0 else None
    saida = {
        "contagem": acc.pixels,
        "peso": round(acc.peso, 6),
        "soma": acc.soma if acc.peso > 0 else None,
        "media": media,
        "minimo": acc.minimo,
        "maximo": acc.maximo,
        "desvio": math.sqrt(max(variancia, 0.0)) if variancia is not None else None,
        "mediana": acc.mediana() if "mediana" in pedidas else None,
        "majoritario": acc.majoritario() if "majoritario" in pedidas else None,
        "classes": acc.classes() if "classes" in pedidas else None,
    }
    return {k: v for k, v in saida.items() if k in pedidas or k in ("contagem", "peso")}


__all__ = ["ESTATISTICAS", "FAIXA_LINHAS", "PIXELS_MEDIANA_MAX", "SUBPIXEL", "ZonaGrande",
           "estatisticas_da_zona"]
