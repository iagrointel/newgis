"""Conversão para COG nos dois perfis declarados (item L1-01-ingest-raster; ADR 20260906T2127
decisão 2): `visual` (JPEG sem alfa / WEBP com alfa, 8 bits escalados pelo percentil 2-98 medido no
BRUTO) e `cientifico` (ZSTD, dtype e nodata originais, predictor 2 inteiro / 3 flutuante). Toda
conversão roda como neto do job (`ctx.subprocesso`, RLIMIT herdado, `GDAL_DISABLE_READDIR_ON_OPEN`)
e todo produto é validado pelo rio-cogeo (`cog_validate`) antes de subir — COG que o validador
reprova nunca sai do diretório de trabalho.

A escolha JPEG × WEBP é regra escrita: fonte com alfa ou 4 bandas (RGBA) usa WEBP (único dos dois
que aceita alfa); o resto usa JPEG. Fonte com mais de 3 bandas usa as 3 primeiras no visual (o
científico sempre leva todas — nada se perde); a seleção é registrada na saída.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rio_cogeo import __version__ as RIO_COGEO_VERSAO
from rio_cogeo.cogeo import cog_validate

from app import limites
from app.imagens.validacao import RelatorioValidacao, ambiente_isolado

QUALIDADE_JPEG = 80
QUALIDADE_WEBP = 80
PERCENTIS = (2.0, 98.0)


class ErroConversao(RuntimeError):
    """A conversão ou a validação rio-cogeo falhou; a mensagem nomeia o perfil e a causa."""


@dataclass
class ProdutoCOG:
    perfil: str
    caminho: Path
    bytes: int
    sha256: str
    compressao: str          # 'JPEG' | 'WEBP' | 'ZSTD'
    bandas_usadas: list[int]  # 1-based, como no GDAL


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for pedaco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(pedaco)
    return h.hexdigest()


def _rodar(ctx, argv: list[str], perfil: str) -> None:
    r = ctx.subprocesso(argv, env=ambiente_isolado())
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise ErroConversao(
            f"perfil {perfil}: {' '.join(argv[:2])} saiu com código {r.returncode}: "
            f"{(linhas[-1] if linhas else 'sem detalhe')[:300]}"
        )


def _validar_cog(caminho: Path, perfil: str) -> None:
    valido, erros, _avisos = cog_validate(str(caminho), strict=True)
    if not valido or erros:
        raise ErroConversao(f"perfil {perfil}: rio-cogeo reprovou o produto: {'; '.join(erros)[:400]}")


def estatisticas_bruto(caminho: Path, rel: RelatorioValidacao) -> list[dict]:
    """Estatísticas por banda lidas do BRUTO (rasterio, amostra limitada): min/max/mean/std e os
    percentis 2-98 que escalam o perfil visual. A amostra é por diezimação determinística — nunca
    lê mais que ~RASTER_ESTATISTICA_AMOSTRA pixels por banda."""
    import numpy as np

    nodata_final = rel.nodata_final()
    saida: list[dict] = []
    with rasterio.open(caminho) as ds:
        for i in range(1, ds.count + 1):
            passo = max(1, int(((ds.width * ds.height) / limites.RASTER_ESTATISTICA_AMOSTRA) ** 0.5))
            arr = ds.read(i)[::passo, ::passo]
            nd = nodata_final[i - 1] if i - 1 < len(nodata_final) else None
            if nd is not None:
                arr = arr[arr != nd]
            arr = arr[np.isfinite(arr)] if arr.dtype.kind == "f" else arr.ravel()
            if arr.size == 0:
                saida.append({"banda": i, "min": None, "max": None, "mean": None, "std": None,
                              "percentil_2": None, "percentil_98": None, "nodata": nd})
                continue
            p2, p98 = np.percentile(arr.astype("float64"), PERCENTIS)
            saida.append({
                "banda": i, "min": float(arr.min()), "max": float(arr.max()),
                "mean": float(arr.mean()), "std": float(arr.std()),
                "percentil_2": float(p2), "percentil_98": float(p98), "nodata": nd,
            })
    return saida


def _argv_base_cog(perfil: str) -> list[str]:
    return [
        "-of", "COG", "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO",
        "-co", "NUM_THREADS=ALL_CPUS", "-co", "BIGTIFF=IF_SAFER",
        "-co", "OVERVIEW_RESAMPLING=AVERAGE",
    ]


def converter_cientifico(ctx, bruto: Path, rel: RelatorioValidacao, saida: Path) -> ProdutoCOG:
    predictor = "3" if rel.dtype.startswith("Float") else "2"
    argv = ["gdal_translate", *_argv_base_cog("cientifico"),
            "-co", "COMPRESS=ZSTD", "-co", f"PREDICTOR={predictor}", "-mo", "PLAT_PERFIL=cientifico"]
    # OVERVIEW_RESAMPLING=MODE para categórico (classe majoritária, nunca média de classe)
    if rel.categorico:
        argv += ["-co", "OVERVIEW_RESAMPLING=MODE"]
    nodata = rel.nodata_final()
    if nodata and nodata[0] is not None:
        argv += ["-a_nodata", str(nodata[0])]
    elif rel.nodata_corrigido is not None:
        argv += ["-a_nodata", "none"]  # nodata inválido descartado pela validação: não propagar
    argv += [str(bruto), str(saida)]
    _rodar(ctx, argv, "cientifico")
    _validar_cog(saida, "cientifico")
    return ProdutoCOG("cientifico", saida, saida.stat().st_size, _sha256(saida), "ZSTD",
                      list(range(1, rel.bandas + 1)))


def _bandas_visual(rel: RelatorioValidacao) -> list[int]:
    """1-based. RGBA (4 bandas) e RGB ficam como estão; 1-2 bandas ficam como estão (cinza/GA); mais
    de 4 bandas usam as 3 primeiras (regra escrita no ADR — a seleção entra na saída e na proveniência)."""
    if rel.bandas <= 4:
        return list(range(1, rel.bandas + 1))
    return [1, 2, 3]


def converter_visual(ctx, bruto: Path, rel: RelatorioValidacao, stats: list[dict], saida: Path) -> ProdutoCOG:
    bandas = _bandas_visual(rel)
    webp = rel.bandas == 4  # 4 bandas (RGBA): WEBP, único dos dois codecs com alfa (regra do ADR)
    vrt = saida.with_suffix(".vrt")

    argv_vrt = ["gdal_translate", "-of", "VRT", "-ot", "Byte"]
    for b in bandas:
        argv_vrt += ["-b", str(b)]
    for b in bandas:
        if rel.bandas == 4 and b == 4:
            continue  # alfa nunca é escalado por percentil: 0 (transparente) e 255 (opaco) ficam como estão
        st = stats[b - 1] if b - 1 < len(stats) else {}
        lo = st.get("percentil_2")
        hi = st.get("percentil_98")
        if lo is None or hi is None or hi <= lo:
            lo, hi = (st.get("min"), st.get("max"))
        if lo is None or hi is None or hi <= lo:
            lo, hi = 0.0, 255.0 if rel.dtype == "Byte" else 65535.0
        argv_vrt += ["-scale", f"{lo}", f"{hi}", "1", "255"]
    argv_vrt += [str(bruto), str(vrt)]
    _rodar(ctx, argv_vrt, "visual")

    compressao = "WEBP" if webp else "JPEG"
    # o driver COG tem opção de nível própria por codec: QUALITY (JPEG) x WEBP_LEVEL (WEBP)
    opcao_nivel = ["-co", f"WEBP_LEVEL={QUALIDADE_WEBP}"] if webp else ["-co", f"QUALITY={QUALIDADE_JPEG}"]
    argv = ["gdal_translate", *_argv_base_cog("visual"), "-co", f"COMPRESS={compressao}",
            *opcao_nivel, "-mo", "PLAT_PERFIL=visual", str(vrt), str(saida)]
    _rodar(ctx, argv, "visual")
    vrt.unlink(missing_ok=True)
    _validar_cog(saida, "visual")
    return ProdutoCOG("visual", saida, saida.stat().st_size, _sha256(saida), compressao, bandas)


def miniatura_png(ctx, visual: ProdutoCOG, saida: Path) -> dict:
    """PNG pequeno para o Conteúdo (lado maior RASTER_VISUAL_MAX_LADO), derivado do COG visual
    (já 8 bits) — nunca do bruto de 16 bits."""
    with rasterio.open(visual.caminho) as ds:
        lado = max(ds.width, ds.height)
    if lado <= limites.RASTER_VISUAL_MAX_LADO:
        largura, altura = None, None
    else:
        fator = limites.RASTER_VISUAL_MAX_LADO / lado
        with rasterio.open(visual.caminho) as ds:
            largura = max(1, int(ds.width * fator))
            altura = max(1, int(ds.height * fator))
    argv = ["gdal_translate", "-of", "PNG"]
    if largura:
        argv += ["-outsize", str(largura), str(altura)]
    argv += [str(visual.caminho), str(saida)]
    _rodar(ctx, argv, "miniatura")
    return {"caminho": saida, "bytes": saida.stat().st_size, "sha256": _sha256(saida)}


def versoes_software() -> dict:
    from osgeo import gdal

    import app.versao as versao_app

    return {
        "gdal": gdal.VersionInfo("RELEASE_NAME") or "",
        "rio-cogeo": RIO_COGEO_VERSAO,
        "rasterio": rasterio.__version__,
        "plat": versao_app.versao(),
    }
