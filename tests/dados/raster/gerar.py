"""Gera os arquivos de teste dos FORMATOS DE ENTRADA raster (item L1-01-f). Tudo é SINTÉTICO, gerado na
casa, determinístico, sem licença restritiva (ver FONTE_E_LICENCA.md) e minúsculo (o maior fica bem
abaixo de 1 MB). Reproduz os mesmos comandos usados na fundação empírica do item (os bytes de assinatura
de cada formato foram medidos na máquina; ver app/imagens/formatos.py).

Uso: venv/bin/python tests/dados/raster/gerar.py  (idempotente; sobrescreve)
Exige os binários do GDAL no PATH (gdal_translate, gdaladdo) e os pacotes rasterio, netCDF4 e h5py do
venv — nenhum download, nenhuma rede.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

AQUI = Path(__file__).resolve().parent
W, H = 96, 72
X0, Y0 = 200000.0, 7200000.0
RES = 10.0


def _rodar(*argv: str) -> None:
    r = subprocess.run(list(argv), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{argv[0]} falhou: {r.stderr[-400:]}")


def _grade(valor_inicial: int = 0) -> np.ndarray:
    return ((np.arange(W * H, dtype=np.uint16).reshape(H, W) + valor_inicial) % 251).astype(np.uint8)


def _tiff(nome: str, dados: np.ndarray, *, bigtiff: bool = False, epsg: str = "EPSG:31983",
          transform=None) -> None:
    transform = transform or from_origin(X0, Y0, RES, RES)
    contagem = 1 if dados.ndim == 2 else dados.shape[0]
    with rasterio.open(
        AQUI / nome, "w", driver="GTiff", width=W, height=H, count=contagem,
        dtype=str(dados.dtype), crs=epsg, transform=transform,
        BIGTIFF="YES" if bigtiff else "IF_SAFER",
    ) as d:
        if dados.ndim == 2:
            d.write(dados, 1)
        else:
            for i in range(contagem):
                d.write(dados[i], i + 1)


def _zip(nome_zip: str, membros: list[str]) -> None:
    with zipfile.ZipFile(AQUI / nome_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for m in membros:
            z.write(AQUI / m, m)


# --------------------------------------------------------------------------------------------- formatos
def geotiffs() -> None:
    _tiff("geotiff_sintetico.tif", _grade())
    _tiff("geotiff_rgb.tif", np.stack([_grade(0), _grade(60), _grade(120)]))
    _tiff("geotiff_16bits.tif", (_grade().astype(np.uint16) * 200))
    _tiff("bigtiff_sintetico.tif", _grade(), bigtiff=True)


def jpeg2000() -> None:
    _rodar("gdal_translate", "-q", "-of", "JP2OpenJPEG", "-co", "REVERSIBLE=YES",
           str(AQUI / "geotiff_rgb.tif"), str(AQUI / "jpeg2000_sintetico.jp2"))
    # "12 bits": valores na faixa de 12 bits em UInt16 (o driver JP2OpenJPEG não expõe NBITS; o que a
    # refutação prova é que JP2 de mais de 8 bits por pixel importa com o dtype preservado)
    _rodar("gdal_translate", "-q", "-of", "JP2OpenJPEG", "-ot", "UInt16", "-scale", "0", "255", "0", "4095",
           "-co", "REVERSIBLE=YES", str(AQUI / "geotiff_sintetico.tif"), str(AQUI / "jpeg2000_12bits.jp2"))


def erdas() -> None:
    _rodar("gdal_translate", "-q", "-of", "HFA", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "erdas_sintetico.img"))
    # pirâmides EXTERNAS (.rrd): o HFA guarda overviews internos por padrão — limpar primeiro, depois
    # HFA_USE_RRD=YES força o .rrd irmão
    _rodar("gdal_translate", "-q", "-of", "HFA", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "erdas_rrd.img"))
    _rodar("gdaladdo", "-clean", str(AQUI / "erdas_rrd.img"))
    Path(AQUI / "erdas_rrd.img.aux.xml").unlink(missing_ok=True)
    _rodar("gdaladdo", "--config", "HFA_USE_RRD", "YES", str(AQUI / "erdas_rrd.img"), "2", "4")
    _zip("erdas_piramides_externas.zip", ["erdas_rrd.img", "erdas_rrd.rrd"])


def envi() -> None:
    _rodar("gdal_translate", "-q", "-of", "ENVI", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "envi.dat"))
    _zip("envi_par.zip", ["envi.dat", "envi.hdr"])


def ascii_grid() -> None:
    _rodar("gdal_translate", "-q", "-of", "AAIGrid", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "ascii_grid_sintetico.asc"))
    # o AAIGrid grava o .prj IRMÃO (ascii_grid_sintetico.prj): tirá-lo deixa a grade sem CRS declarado,
    # que é o caso comum do formato (georreferência só pela matriz de afim do cabeçalho)
    Path(AQUI / "ascii_grid_sintetico.prj").unlink(missing_ok=True)
    linhas = ["ncols         8", "nrows         6", "xllcorner     200000,0", "yllcorner     7199280,0",
              "cellsize      10,0", "NODATA_value  -9999"]
    for linha in np.arange(48).reshape(6, 8) % 7:
        linhas.append(" ".join(f"{v},0" for v in linha))
    (AQUI / "ascii_grid_virgula.asc").write_text("\n".join(linhas) + "\n")


def imagens_com_world_file() -> None:
    # PNG/JPEG não guardam georreferência: o world file é ESCRITO à mão ao lado (convenção ESRI)
    _rodar("gdal_translate", "-q", "-of", "PNG", "-b", "1", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "mundo.png"))
    _rodar("gdal_translate", "-q", "-of", "JPEG", "-b", "1", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "mundo.jpg"))
    grau_por_px = RES / 111_320.0
    wld = f"{grau_por_px!r}\n0\n0\n{-grau_por_px!r}\n{-46.0 + grau_por_px / 2!r}\n{-23.0 - grau_por_px / 2!r}\n"
    (AQUI / "mundo.pgw").write_text(wld)
    (AQUI / "mundo.jgw").write_text(wld)
    _zip("png_world.zip", ["mundo.png", "mundo.pgw"])
    _zip("jpeg_world.zip", ["mundo.jpg", "mundo.jgw"])


def geopdf() -> None:
    _rodar("gdal_translate", "-q", "-of", "PDF", str(AQUI / "geotiff_rgb.tif"), str(AQUI / "geopdf_sintetico.pdf"))


def netcdf() -> None:
    import netCDF4

    def _convencoes_cf(ds, projeta: bool) -> None:
        ds.Conventions = "CF-1.8"
        x = ds.createDimension("x", W)
        y = ds.createDimension("y", H)
        vx = ds.createVariable("x", "f8", ("x",))
        vy = ds.createVariable("y", "f8", ("y",))
        vx.standard_name = "projection_x_coordinate"
        vy.standard_name = "projection_y_coordinate"
        vx.axis, vy.axis = "X", "Y"
        vx.units = vy.units = "m"
        vx[:] = X0 + (np.arange(W) + 0.5) * RES
        vy[:] = Y0 - (np.arange(H) + 0.5) * RES
        if projeta:
            crs = ds.createVariable("crs", "i4")
            crs.grid_mapping_name = "transverse_mercator"
            crs.scale_factor_at_central_meridian = 0.9996
            crs.longitude_of_central_meridian = -45.0
            crs.latitude_of_projection_origin = 0.0
            crs.false_easting = 500000.0
            crs.false_northing = 10000000.0
            crs.spatial_ref = rasterio.crs.CRS.from_epsg(31983).to_wkt()
            crs.GeoTransform = " ".join(str(v) for v in from_origin(X0, Y0, RES, RES).to_gdal())
        return x, y

    ds = netCDF4.Dataset(AQUI / "netcdf_sintetico.nc", "w", format="NETCDF4_CLASSIC")
    x, y = _convencoes_cf(ds, projeta=True)
    # NETCDF4_CLASSIC é netCDF-3 estrito: sem NC_UBYTE (dtype "u1" reprova) — banda vira byte assinado
    v = ds.createVariable("banda1", "i1", ("y", "x"))
    v.grid_mapping = "crs"
    v[:] = _grade().astype(np.int8)
    ds.close()

    # eixo de tempo (refutação: recusa com a mensagem do L1-19, não importa como 4 bandas silenciosas)
    ds = netCDF4.Dataset(AQUI / "netcdf_eixo_tempo.nc", "w")  # NETCDF4 (HDF5 por baixo — mágica \x89HDF)
    _convencoes_cf(ds, projeta=True)
    ds.createDimension("time", 4)
    vt = ds.createVariable("time", "f8", ("time",))
    vt.standard_name = "time"
    vt.units = "days since 2026-01-01"
    vt[:] = [0, 10, 20, 30]
    v = ds.createVariable("banda1", "u1", ("time", "y", "x"))
    v.grid_mapping = "crs"
    for i in range(4):
        v[i, :, :] = _grade(i * 30)
    ds.close()


def grib() -> None:
    _rodar("gdal_translate", "-q", "-of", "GRIB", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "grib_sintetico.grb2"))


def zarr() -> None:
    loja = AQUI / "armazem_tmp.zarr"
    _rodar("gdal_translate", "-q", "-of", "Zarr", str(AQUI / "geotiff_sintetico.tif"), str(loja))
    destino = AQUI / "loja_zarr.zarr"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(loja.rglob("*")):
            if p.is_file():
                z.write(p, (Path("armazem.zarr") / p.relative_to(loja)).as_posix())
    shutil.rmtree(loja)


def hdf5() -> None:
    import h5py

    with h5py.File(AQUI / "hdf5_sem_georref.h5", "w") as f:
        d = f.create_dataset("banda1", data=_grade())
        d.attrs["descricao"] = "raster sintetico sem nenhuma convencao de georreferencia"


def mosaicos() -> None:
    # 4 cenas contíguas em grade 2×2 (mesmo CRS, dimensões, dtype e resolução)
    nomes = []
    for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1)]):
        tf = from_origin(X0 + dx * W * RES, Y0 - dy * H * RES, RES, RES)
        nome = f"mosaico_cena{i + 1}.tif"
        with rasterio.open(AQUI / nome, "w", driver="GTiff", width=W, height=H, count=1, dtype="uint8",
                           crs="EPSG:31983", transform=tf) as d:
            d.write(_grade(i), 1)
        nomes.append(nome)
    _zip("mosaico_4cenas.zip", nomes)
    # a mesma 1ª cena + uma em EPSG:4326 (refutação: recusa dizendo o CRS de CADA arquivo)
    tf4326 = from_origin(-46.0, -23.0, 0.001, 0.001)
    with rasterio.open(AQUI / "mosaico_cena_geo.tif", "w", driver="GTiff", width=W, height=H, count=1,
                       dtype="uint8", crs="EPSG:4326", transform=tf4326) as d:
        d.write(_grade(), 1)
    _zip("mosaico_crs_diferente.zip", ["mosaico_cena1.tif", "mosaico_cena_geo.tif"])
    for nome in (*nomes, "mosaico_cena_geo.tif"):
        (AQUI / nome).unlink()


def kmz() -> None:
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>superoverlay sintetico</name>
    <GroundOverlay>
      <name>base</name>
      <Icon><href>base_overlay.png</href></Icon>
      <LatLonBox>
        <north>-23.0</north><south>-23.048</south><east>-45.952</east><west>-46.0</west>
        <rotation>0</rotation>
      </LatLonBox>
    </GroundOverlay>
  </Document>
</kml>
"""
    (AQUI / "doc.kml").write_text(kml)
    _rodar("gdal_translate", "-q", "-of", "PNG", "-b", "1", str(AQUI / "geotiff_sintetico.tif"),
           str(AQUI / "base_overlay.png"))
    with zipfile.ZipFile(AQUI / "superoverlay.kmz", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(AQUI / "doc.kml", "doc.kml")
        z.write(AQUI / "base_overlay.png", "base_overlay.png")
    (AQUI / "doc.kml").unlink()
    (AQUI / "base_overlay.png").unlink()


def proprietarios() -> None:
    # bytes de GeoTIFF legítimo com extensão proprietária: prova que a recusa ECW/MrSID é pela EXTENSÃO
    # (tabela de formatos), não por conteúdo corrompido
    shutil.copyfile(AQUI / "geotiff_sintetico.tif", AQUI / "proprietario.ecw")
    shutil.copyfile(AQUI / "geotiff_sintetico.tif", AQUI / "proprietario.sid")


def intermediarios_fora() -> None:
    # cenas soltas que viraram zip + caches de estatística (.aux.xml) que o GDAL escreve ao lado
    for nome in ("mundo.png", "mundo.jpg", "mundo.pgw", "mundo.jgw", "envi.dat", "envi.hdr",
                 "erdas_rrd.img", "erdas_rrd.rrd", "base_overlay.png", "doc.kml",
                 "ascii_grid_sintetico.asc.aux.xml", "ascii_grid_sintetico.prj",
                 "envi.dat.aux.xml", "erdas_sintetico.img.aux.xml", "mundo.png.aux.xml",
                 "mundo.jpg.aux.xml", "base_overlay.png.aux.xml"):
        (AQUI / nome).unlink(missing_ok=True)


if __name__ == "__main__":
    geotiffs()
    jpeg2000()
    erdas()
    envi()
    ascii_grid()
    imagens_com_world_file()
    geopdf()
    netcdf()
    grib()
    zarr()
    hdf5()
    mosaicos()
    kmz()
    proprietarios()
    intermediarios_fora()
    print(f"ok: arquivos em {AQUI}")
