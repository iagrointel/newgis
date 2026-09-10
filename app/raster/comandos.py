"""Chamadas de linha de comando do GDAL usadas pelas ferramentas raster (item L2-05-e).

Por que subprocesso e não a API Python do GDAL: é a mesma decisão do item L1-01 (`app/imagens/cog.py`) —
o utilitário do GDAL é o programa de referência, o resultado é comparável byte a byte com o que o
usuário rodaria à mão, e o neto herda os limites de memória e o cancelamento do job (`ctx.subprocesso`).
As ferramentas aqui não reimplementam declividade, curva de nível ou visibilidade: elas preparam os
argumentos, chamam `gdaldem`/`gdal_contour`/`gdal_viewshed`/`gdal_proximity` e conferem o produto.

Todo produto raster termina em `finalizar_cog`: um `gdal_translate -of COG` com compressão declarada,
blocos de 512 e pirâmide (`OVERVIEWS=AUTO`), validado pelo `rio-cogeo` antes de sair do diretório de
trabalho — é a mesma regra do L1-01, e é o que responde à medida de disco do adversário.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import rasterio
from rio_cogeo.cogeo import cog_validate

REAMOSTRAGENS = ("vizinho", "bilinear", "cubica", "cubicspline", "lanczos", "media", "moda", "minimo", "maximo")
_REAMOSTRAGEM_GDAL = {"vizinho": "near", "bilinear": "bilinear", "cubica": "cubic", "cubicspline": "cubicspline",
                      "lanczos": "lanczos", "media": "average", "moda": "mode", "minimo": "min", "maximo": "max"}
COMPRESSOES = ("ZSTD", "DEFLATE", "LZW")
BLOCO = 512


class ErroComando(RuntimeError):
    """Um utilitário do GDAL saiu com código diferente de zero; a mensagem traz a última linha do erro."""


def reamostragem_gdal(nome: str) -> str:
    if nome not in _REAMOSTRAGEM_GDAL:
        raise ErroComando(f"reamostragem desconhecida: {nome} (use uma de {', '.join(REAMOSTRAGENS)})")
    return _REAMOSTRAGEM_GDAL[nome]


def rodar(ctx, argv: list[str], env: dict, etapa: str) -> str:
    r = ctx.subprocesso([str(a) for a in argv], env=env)
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise ErroComando(f"{etapa}: {argv[0]} saiu com código {r.returncode}: "
                          f"{(linhas[-1] if linhas else 'sem detalhe')[:300]}")
    return r.stdout or ""


def _predictor(dtype: str) -> str:
    return "3" if str(dtype).startswith("float") else "2"


def finalizar_cog(ctx, bruto: Path, saida: Path, env: dict, *, compressao: str = "ZSTD",
                  categorico: bool = False) -> dict:
    """Converte o produto intermediário em COG validado. Devolve {bytes, compressao, blocos, pirâmide}."""
    if compressao not in COMPRESSOES:
        raise ErroComando(f"compressão desconhecida: {compressao} (use uma de {', '.join(COMPRESSOES)})")
    with rasterio.open(bruto) as ds:
        dtype = ds.dtypes[0]
        forma = (ds.height, ds.width)
    argv = ["gdal_translate", "-of", "COG", "-co", f"BLOCKSIZE={BLOCO}", "-co", "OVERVIEWS=AUTO",
            "-co", f"COMPRESS={compressao}", "-co", f"PREDICTOR={_predictor(dtype)}",
            "-co", "OVERVIEW_RESAMPLING=" + ("MODE" if categorico else "AVERAGE"),
            "-co", "BIGTIFF=IF_SAFER", "-co", "NUM_THREADS=ALL_CPUS", str(bruto), str(saida)]
    rodar(ctx, argv, env, "conversão para COG")
    valido, erros, _avisos = cog_validate(str(saida), strict=True)
    if not valido or erros:
        raise ErroComando(f"o rio-cogeo reprovou o produto: {'; '.join(erros)[:400]}")
    with rasterio.open(saida) as ds:
        piramide = len(ds.overviews(1))
    return {"bytes": saida.stat().st_size, "compressao": compressao, "bloco": BLOCO, "niveis_piramide": piramide,
            "dimensoes": [forma[1], forma[0]], "dtype": dtype}


def declividade(ctx, entrada: str, saida: Path, env: dict, *, modo: str, escala: float | None,
                fator_z: float, unidade: str = "grau", azimute: float = 315.0, altitude: float = 45.0) -> None:
    """gdaldem nos modos slope/aspect/hillshade/roughness/TPI (o mesmo programa, o mesmo resultado)."""
    argv = ["gdaldem", modo, str(entrada), str(saida), "-of", "GTiff", "-co", "TILED=YES",
            "-co", "COMPRESS=DEFLATE", "-b", "1", "-compute_edges"]
    if modo == "slope":
        argv += ["-p"] if unidade == "porcento" else []
        argv += ["-z", str(fator_z)]
    if modo == "hillshade":
        argv += ["-z", str(fator_z), "-az", str(azimute), "-alt", str(altitude)]
    if escala is not None and modo in ("slope", "hillshade"):
        argv += ["-s", str(escala)]
    rodar(ctx, argv, env, f"gdaldem {modo}")


def curvas(ctx, entrada: str, saida: Path, env: dict, *, intervalo: float, banda: int, campo: str = "cota",
           base: float = 0.0) -> None:
    argv = ["gdal_contour", "-b", str(banda), "-a", campo, "-i", str(intervalo), "-off", str(base),
            "-f", "GeoJSON", str(entrada), str(saida)]
    rodar(ctx, argv, env, "gdal_contour")


def vetorizar(ctx, entrada: str, saida: Path, env: dict, *, banda: int, campo: str = "valor",
              mascara: str | None = None) -> None:
    argv = ["gdal_polygonize.py", str(entrada), "-b", str(banda), "-f", "GeoJSON", str(saida), "vetorizado", campo]
    if mascara:
        argv[3:3] = ["-mask", mascara]
    rodar(ctx, argv, env, "gdal_polygonize")


def rasterizar(ctx, fonte_ogr: str, saida: Path, env: dict, *, campo: str | None, valor_fixo: float | None,
               resolucao: float, limites: tuple[float, float, float, float], tipo: str, nodata: float,
               camada: str | None = None) -> None:
    x0, y0, x1, y1 = limites
    argv = ["gdal_rasterize", "-of", "GTiff", "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
            "-a_nodata", str(nodata), "-ot", tipo, "-tr", str(resolucao), str(resolucao),
            "-te", str(x0), str(y0), str(x1), str(y1)]
    if campo:
        argv += ["-a", campo]
    else:
        argv += ["-burn", str(valor_fixo if valor_fixo is not None else 1)]
    if camada:
        argv += ["-l", camada]
    argv += [str(fonte_ogr), str(saida)]
    rodar(ctx, argv, env, "gdal_rasterize")


def visibilidade(ctx, entrada: str, saida: Path, env: dict, *, x: float, y: float, altura_observador: float,
                 altura_alvo: float, raio: float, banda: int = 1) -> None:
    argv = ["gdal_viewshed", "-b", str(banda), "-ox", str(x), "-oy", str(y), "-oz", str(altura_observador),
            "-tz", str(altura_alvo), "-md", str(raio), "-of", "GTiff", "-co", "TILED=YES",
            "-co", "COMPRESS=DEFLATE", str(entrada), str(saida)]
    rodar(ctx, argv, env, "gdal_viewshed")


def proximidade(ctx, entrada: str, saida: Path, env: dict, *, banda: int, valores: list[float] | None,
                unidade: str, maxima: float | None) -> None:
    argv = ["gdal_proximity.py", str(entrada), str(saida), "-srcband", str(banda), "-of", "GTiff",
            "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-distunits", "GEO" if unidade == "mapa" else "PIXEL",
            "-ot", "Float32", "-nodata", "-9999"]
    if valores:
        argv += ["-values", ",".join(str(int(v)) for v in valores)]
    if maxima:
        argv += ["-maxdist", str(maxima)]
    rodar(ctx, argv, env, "gdal_proximity")


def reprojetar(ctx, entradas: list[str], saida: Path, env: dict, *, epsg_destino: int | None,
               resolucao: float | None, reamostragem: str, recorte: str | None = None,
               recorte_camada: str | None = None, cortar_pela_camada: bool = False,
               nodata_destino: float | None = None) -> None:
    """gdalwarp: reprojeção, reamostragem, mosaico (várias entradas) e recorte por polígono."""
    argv = ["gdalwarp", "-of", "GTiff", "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
            "-r", reamostragem_gdal(reamostragem), "-multi", "-wo", "NUM_THREADS=2", "-overwrite"]
    if epsg_destino:
        argv += ["-t_srs", f"EPSG:{int(epsg_destino)}"]
    if resolucao:
        argv += ["-tr", str(resolucao), str(resolucao)]
    if nodata_destino is not None:
        argv += ["-dstnodata", str(nodata_destino)]
    if recorte:
        argv += ["-cutline", recorte]
        if recorte_camada:
            argv += ["-cl", recorte_camada]
        if cortar_pela_camada:
            argv += ["-crop_to_cutline"]
    argv += [*[str(e) for e in entradas], str(saida)]
    rodar(ctx, argv, env, "gdalwarp")


def copiar_para_trabalho(origem: Path, destino: Path) -> Path:
    shutil.copyfile(origem, destino)
    return destino


__all__ = ["BLOCO", "COMPRESSOES", "ErroComando", "REAMOSTRAGENS", "curvas", "declividade", "finalizar_cog",
           "proximidade", "rasterizar", "reamostragem_gdal", "reprojetar", "rodar", "vetorizar", "visibilidade"]
