"""Álgebra de mapa bloco a bloco (item L2-05-e): calculadora de expressão, reclassificação por faixas e
amostragem de valores em pontos.

A expressão é a MESMA do motor de ladrilho (`app.imagens.tiles.expressao_valida` — gramática fechada:
referência de banda `b1..b99`, número, aritmética, parênteses e um punhado de funções) e o avaliador é o
MESMO que roda dentro do TiTiler (`numexpr`, chamado como o `rio_tiler.expression.apply_expression` chama).
Por isso o resultado da calculadora é comparável pixel a pixel com o que o TiTiler devolveria para a
mesma expressão — e é o que a suíte mede.

Bloco a bloco: a saída é escrita janela por janela, com o tamanho de bloco do raster de entrada. Nenhuma
função deste módulo materializa o raster inteiro; o pico de memória depende do bloco, não do arquivo.

Numeração das bandas: os rasters entram em ORDEM, e as bandas são numeradas em sequência sobre eles —
com dois rasters de 3 bandas, `b4` é a primeira banda do segundo raster. Está escrito assim na descrição
do parâmetro porque é a única parte não óbvia da expressão.
"""

from __future__ import annotations

import re
from pathlib import Path

import numexpr
import numpy as np
import rasterio
from rasterio.windows import Window

from app.imagens.tiles import bandas_da_expressao, expressao_valida

TIPOS_SAIDA = ("float32", "float64", "int16", "int32", "uint8", "uint16")
_FAIXA = re.compile(r"^\s*(-?[0-9.]+|\*)\s*-\s*(-?[0-9.]+|\*)\s*:\s*(-?[0-9.]+|nodata)\s*$", re.IGNORECASE)


class ErroCalculo(ValueError):
    """Expressão, tabela de reclassificação ou alinhamento de rasters fora do contrato."""


def conferir_alinhamento(datasets: list) -> None:
    """Rasters de uma mesma conta têm de estar na mesma grade: mesmo CRS, mesma transformação e mesmo
    tamanho. Quando não estão, a mensagem diz o que difere — a reamostragem é DECLARADA pelo usuário
    (parâmetro `reamostragem` da ferramenta), nunca escolhida em silêncio."""
    base = datasets[0]
    for i, ds in enumerate(datasets[1:], start=2):
        if ds.crs != base.crs:
            raise ErroCalculo(f"raster {i}: CRS {ds.crs} diferente do primeiro ({base.crs})")
        if (ds.width, ds.height) != (base.width, base.height):
            raise ErroCalculo(f"raster {i}: {ds.width}x{ds.height} diferente do primeiro "
                              f"({base.width}x{base.height})")
        if not _mesma_transformacao(ds.transform, base.transform):
            raise ErroCalculo(f"raster {i}: transformação {tuple(round(v, 9) for v in ds.transform[:6])} "
                              f"diferente do primeiro {tuple(round(v, 9) for v in base.transform[:6])}")


def _mesma_transformacao(a, b, tol: float = 1e-9) -> bool:
    return all(abs(x - y) <= tol * max(1.0, abs(y)) for x, y in zip(a[:6], b[:6], strict=True))


def mapa_de_bandas(datasets: list) -> list[tuple[int, int]]:
    """b1..bN -> (índice do dataset, banda dentro dele), na ordem em que os rasters foram dados."""
    mapa = []
    for i, ds in enumerate(datasets):
        for b in range(1, ds.count + 1):
            mapa.append((i, b))
    return mapa


def blocos(ds) -> list[Window]:
    janelas = [j for _, j in ds.block_windows(1)]
    return janelas or [Window(0, 0, ds.width, ds.height)]


def calcular(datasets: list, expressao: str, saida: Path, *, dtype: str = "float32",
             nodata: float | None = None) -> dict:
    """Avalia a expressão bloco a bloco e grava o GeoTIFF de saída. Devolve {blocos, pixels, bandas_usadas}."""
    ok, motivo = expressao_valida(expressao)
    if not ok:
        raise ErroCalculo(f"expressão recusada: {motivo}")
    if dtype not in TIPOS_SAIDA:
        raise ErroCalculo(f"tipo de saída desconhecido: {dtype} (use um de {', '.join(TIPOS_SAIDA)})")
    conferir_alinhamento(datasets)
    mapa = mapa_de_bandas(datasets)
    usadas = bandas_da_expressao(expressao)
    if not usadas or max(usadas) > len(mapa):
        raise ErroCalculo(f"a expressão usa b{max(usadas) if usadas else '?'} e só há {len(mapa)} bandas "
                          "nos rasters informados")
    base = datasets[0]
    perfil = base.profile.copy()
    perfil.update(driver="GTiff", count=1, dtype=dtype, tiled=True, blockxsize=512, blockysize=512,
                  compress="deflate", nodata=nodata)
    pixels = 0
    with rasterio.open(saida, "w", **perfil) as destino:
        for janela in blocos(base):
            local = {}
            mascara = None
            for b in usadas:
                i, banda = mapa[b - 1]
                arr = datasets[i].read(banda, window=janela)
                nd = datasets[i].nodatavals[banda - 1]
                if nd is not None:
                    invalido = arr == nd
                    mascara = invalido if mascara is None else (mascara | invalido)
                local[f"b{b}"] = arr
            valor = numexpr.evaluate(expressao, local_dict=local)
            valor = np.asarray(valor)
            if nodata is not None:
                sem_valor = ~np.isfinite(valor) if valor.dtype.kind == "f" else np.zeros(valor.shape, dtype=bool)
                if mascara is not None:
                    sem_valor = sem_valor | mascara
                valor = np.where(sem_valor, nodata, valor)
            destino.write(valor.astype(dtype), 1, window=janela)
            pixels += int(janela.width * janela.height)
    return {"blocos": len(blocos(base)), "pixels": pixels, "bandas_usadas": usadas}


def tabela_de_reclassificacao(texto: str) -> list[tuple[float, float, float | None]]:
    """`"0-10:1; 10-20:2; 20-*:3"` -> [(0,10,1), (10,20,2), (20,inf,3)]. `*` é aberto; a classe pode ser
    `nodata`. Intervalo fechado no início e ABERTO no fim (como a tabela do Reclassify da Esri)."""
    faixas = []
    for parte in [p for p in texto.replace("\n", ";").split(";") if p.strip()]:
        m = _FAIXA.match(parte)
        if not m:
            raise ErroCalculo(f"faixa fora do formato 'min-max:classe': {parte.strip()!r}")
        ini, fim, classe = m.group(1), m.group(2), m.group(3)
        a = -np.inf if ini == "*" else float(ini)
        b = np.inf if fim == "*" else float(fim)
        if b <= a:
            raise ErroCalculo(f"faixa vazia (fim <= início): {parte.strip()!r}")
        faixas.append((a, b, None if classe.lower() == "nodata" else float(classe)))
    if not faixas:
        raise ErroCalculo("tabela de reclassificação vazia")
    return faixas


def reclassificar(ds, faixas: list[tuple[float, float, float | None]], saida: Path, *, banda: int = 1,
                  dtype: str = "int16", nodata: float = -9999, classe_fora: float | None = None) -> dict:
    """Reescreve o raster trocando valor por classe, bloco a bloco. Pixel fora de toda faixa vira
    `classe_fora` (ou nodata, quando não declarada)."""
    if dtype not in TIPOS_SAIDA:
        raise ErroCalculo(f"tipo de saída desconhecido: {dtype}")
    perfil = ds.profile.copy()
    perfil.update(driver="GTiff", count=1, dtype=dtype, tiled=True, blockxsize=512, blockysize=512,
                  compress="deflate", nodata=nodata)
    nd_entrada = ds.nodatavals[banda - 1]
    contagem = dict.fromkeys(range(len(faixas)), 0)
    fora = 0
    with rasterio.open(saida, "w", **perfil) as destino:
        for janela in blocos(ds):
            arr = ds.read(banda, window=janela).astype("float64")
            saida_bloco = np.full(arr.shape, nodata, dtype="float64")
            atribuido = np.zeros(arr.shape, dtype=bool)
            for i, (a, b, classe) in enumerate(faixas):
                sel = (arr >= a) & (arr < b) & ~atribuido
                if nd_entrada is not None:
                    sel &= arr != nd_entrada
                if classe is not None:
                    saida_bloco[sel] = classe
                atribuido |= sel
                contagem[i] += int(sel.sum())
            resto = ~atribuido
            if nd_entrada is not None:
                resto &= arr != nd_entrada
            fora += int(resto.sum())
            if classe_fora is not None:
                saida_bloco[resto] = classe_fora
            destino.write(saida_bloco.astype(dtype), 1, window=janela)
    return {"por_faixa": {str(i): n for i, n in contagem.items()}, "fora_das_faixas": fora}


def amostrar(ds, pontos: list[tuple[float, float]], bandas: list[int]) -> list[list[float | None]]:
    """Valor de cada banda nos pontos (coordenadas no CRS do raster). Ponto fora da extensão e pixel
    nodata devolvem None — nunca zero, que é valor legítimo."""
    fora = [None] * len(bandas)
    saida: list[list[float | None]] = []
    dentro = []
    indices = []
    for i, (x, y) in enumerate(pontos):
        if ds.bounds.left <= x <= ds.bounds.right and ds.bounds.bottom <= y <= ds.bounds.top:
            dentro.append((x, y))
            indices.append(i)
        saida.append(list(fora))
    if not dentro:
        return saida
    for posicao, valores in zip(indices, ds.sample(dentro, indexes=bandas), strict=True):
        linha = []
        for j, banda in enumerate(bandas):
            v = float(valores[j])
            nd = ds.nodatavals[banda - 1]
            linha.append(None if (nd is not None and v == nd) or not np.isfinite(v) else v)
        saida[posicao] = linha
    return saida


__all__ = ["ErroCalculo", "TIPOS_SAIDA", "amostrar", "blocos", "calcular", "conferir_alinhamento",
           "mapa_de_bandas", "reclassificar", "tabela_de_reclassificacao"]
