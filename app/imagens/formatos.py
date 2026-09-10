"""Tabela canônica de formatos de entrada raster (item L1-01-f-formatos-de-entrada): a ÚNICA fonte do que a
plataforma aceita e do que recusa. Quem lista formatos para o usuário — a rota `GET /api/imagens/formatos` e
a tela de upload que a lê — busca AQUI (`lista()`), nunca mantém a própria lista à mão: tabela da tela
diferente da tabela do código é a refutação nomeada do item.

Cada aceito carrega as ASSINATURAS medidas nos primeiros bytes (extensão declara, bytes provam — mesma regra
do `app.uploads.tipos`), e os recusados carregam a mensagem EXATA devolvida ao usuário. As recusas de ECW e
MrSID são medidas: `gdalinfo --formats` do GDAL desta instalação (3.8.4) não lista nenhum dos dois drivers,
porque os SDKs deles são proprietários e não acompanham a distribuição — a mensagem diz isso e aponta a
conversão prévia no software de origem. GeoPDF e HDF5 têm recusas medidas próprias (o rasterio do subprocesso
de validação não traz backend de leitura de PDF; o HDF5 abre, mas nenhuma convenção de georreferência dele é
resolvível — testados GEOTRANSFORM, GeoTransform global + crs_wkt e StructMetadata.0/HDF-EOS).
"""

from __future__ import annotations

from dataclasses import dataclass

# nenhum byte de assinatura (formato texto sem marca fixa, ou contêiner sem assinatura própria: o .dat do
# ENVI, cujo cabeçalho vive no .hdr irmão)
SEM_ASSINATURA: tuple[bytes, ...] | None = None


@dataclass(frozen=True)
class Formato:
    chave: str
    rotulo: str
    extensoes: tuple[str, ...]
    driver: str                      # driver do GDAL que abre (o mesmo nome que o relatório devolve)
    georreferencia: str              # de onde vem a georreferência
    assinaturas: tuple[bytes, ...] | None
    texto: bool = False              # assinatura textual (comparada com lstrip e minúsculas)
    observacao: str = ""
    exige_sidecar: tuple[str, ...] = ()   # sufixos irmãos obrigatórios (qualquer um deles, mesmo nome)
    sidecar_mensagem: str = ""            # recusa dirigida quando falta o irmão


@dataclass(frozen=True)
class Recusado:
    chave: str
    rotulo: str
    extensoes: tuple[str, ...]
    mensagem: str


FORMATOS: dict[str, Formato] = {
    "geotiff": Formato(
        "geotiff", "GeoTIFF / BigTIFF", (".tif", ".tiff"), "GTiff",
        "no arquivo (GeoTIFF tags)", (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"),
    ),
    "jpeg2000": Formato(
        "jpeg2000", "JPEG 2000", (".jp2",), "JP2OpenJPEG",
        "no arquivo (caixa jp2)", (b"\x00\x00\x00\x0cjP  \r\n\x87\n",),
        observacao="codorna bruta .j2k (sem caixas) não é aceita: sem caixas não há georreferência",
    ),
    "erdas_img": Formato(
        "erdas_img", "Erdas Imagine (.img)", (".img",), "HFA",
        "no arquivo", (b"EHFA_HEADER_TAG\x00",),
        observacao="pirâmides externas .rrd/.aux, quando existirem, viajam junto (par dentro de um zip)",
    ),
    "envi": Formato(
        "envi", "ENVI (dat + hdr)", (".dat", ".bin"), "ENVI",
        "no arquivo (cabeçalho no .hdr irmão)", SEM_ASSINATURA,
        observacao="o par dat/hdr tem de vir junto, dentro de um zip",
        exige_sidecar=(".hdr",),
        sidecar_mensagem="o arquivo ENVI precisa do cabeçalho irmão .hdr (mesmo nome base, mesmo diretório): "
        "envie o par .dat/.hdr dentro de um zip",
    ),
    "ascii_grid": Formato(
        "ascii_grid", "ASCII Grid (ESRI)", (".asc",), "AAIGrid",
        "no arquivo (.prj irmão) quando presente; pode faltar — informe o EPSG no envio",
        SEM_ASSINATURA, texto=True,
        observacao="ponto decimal obrigatório; arquivo com vírgula decimal é recusado",
    ),
    "png": Formato(
        "png", "PNG com world file", (".png",), "PNG",
        "world file irmão (.pgw/.wld)", (b"\x89PNG\r\n\x1a\n",),
        observacao="world file não traz CRS: informe o EPSG (normalmente 4326) no envio",
        exige_sidecar=(".pgw", ".pngw", ".wld"),
        sidecar_mensagem="PNG não carrega georreferência: envie o world file irmão (.pgw ou .wld, mesmo nome "
        "base) junto com a imagem, dentro de um zip",
    ),
    "jpeg": Formato(
        "jpeg", "JPEG com world file", (".jpg", ".jpeg"), "JPEG",
        "world file irmão (.jgw/.wld)", (b"\xff\xd8\xff",),
        observacao="world file não traz CRS: informe o EPSG (normalmente 4326) no envio",
        exige_sidecar=(".jgw", ".jpgw", ".wld"),
        sidecar_mensagem="JPEG não carrega georreferência: envie o world file irmão (.jgw ou .wld, mesmo nome "
        "base) junto com a imagem, dentro de um zip",
    ),
    "netcdf": Formato(
        "netcdf", "netCDF (1 variável × 1 tempo)", (".nc",), "netCDF",
        "no arquivo (convenções CF)", (b"CDF\x01", b"CDF\x02", b"\x89HDF\r\n\x1a\n"),
        observacao="assinaturas clássicas CDF e a mágica HDF5 do netCDF-4 (o formato NETCDF4 é um HDF5 por "
                   "baixo); uma variável de um tempo só vira raster — série temporal e múltiplas variáveis "
                   "são o item L1-19 (dados multidimensionais)",
    ),
    "grib": Formato(
        "grib", "GRIB (1 mensagem)", (".grb", ".grb2"), "GRIB",
        "no arquivo (template da projeção)", (b"GRIB",),
        observacao="uma mensagem por arquivo; série de passos de tempo é o item L1-19",
    ),
    "zarr": Formato(
        "zarr", "Zarr (armazém zipado)", (".zarr",), "Zarr",
        "no arquivo (coordenadas X/Y do armazém)", (b"PK\x03\x04",),
        observacao="leitura só: o armazém .zarr zipado é extraído e aberto no lugar; o store em chunks "
                   "remotos (fsspec/s3) é o item L1-19",
    ),
    "kmz": Formato(
        "kmz", "KMZ superoverlay (imagem base)", (".kmz",), "KMZ (doc.kml GroundOverlay)",
        "no doc.kml (LatLonBox)", (b"PK\x03\x04",),
        observacao="só o GroundOverlay da imagem base vira raster, em EPSG:4326; rotação diferente de zero "
                   "é recusada; KML vetorial segue o caminho vetorial da plataforma",
    ),
    "zip": Formato(
        "zip", "zip de rasters (mosaico)", (".zip",), "contêiner",
        "a de cada cena de dentro",
        (b"PK\x03\x04",),
        observacao="vários rasters de mesmo CRS, dimensões, tipo e resolução viram 1 mosaico (VRT -> COG); "
                   "cenas de CRS diferentes são recusadas, com a lista de CRS de cada arquivo",
    ),
}

RECUSADOS: dict[str, Recusado] = {
    "ecw": Recusado(
        "ecw", "ECW", (".ecw",),
        "o formato ECW precisa de um SDK proprietário que o GDAL desta instalação não tem (a lista de "
        "drivers do servidor não traz ECW). Converta o arquivo para GeoTIFF ou JPEG 2000 no software de "
        "origem e envie de novo",
    ),
    "mrsid": Recusado(
        "mrsid", "MrSID", (".sid",),
        "o formato MrSID precisa de um SDK proprietário que o GDAL desta instalação não tem (a lista de "
        "drivers do servidor não traz MrSID). Converta o arquivo para GeoTIFF ou JPEG 2000 no software de "
        "origem e envie de novo",
    ),
    "geopdf": Recusado(
        "geopdf", "GeoPDF", (".pdf",),
        "GeoPDF (PDF georreferenciado): a validação desta instalação não abre PDF raster (o rasterio do "
        "subprocesso de validação não traz backend de leitura de PDF). Exporte o mapa como GeoTIFF "
        "georreferenciado no software de origem e envie de novo",
    ),
    "hdf5": Recusado(
        "hdf5", "HDF5", (".h5", ".hdf5"),
        "HDF5: o arquivo abre no GDAL, mas o formato não carrega georreferência resolvível automaticamente "
        "(nenhuma convenção de CRS ou matriz de afim declarada). Exporte a variável como GeoTIFF ou como "
        "netCDF com convenções CF e envie de novo",
    ),
}

# o que pode vir dentro de um zip: rasters aceitos + sidecars que acompanham o raster irmão de mesmo nome
EXTENSOES_RASTER_EM_ZIP = tuple(
    ext for f in FORMATOS.values() if f.chave not in ("zip", "kmz", "zarr") for ext in f.extensoes
)
SIDECARES_EM_ZIP = (
    ".hdr",    # ENVI
    ".wld", ".pgw", ".pngw", ".jgw", ".jpgw",  # world files
    ".prj",    # CRS textual (ASCII Grid)
    ".rrd", ".aux", ".aux.xml",  # pirâmides e metadados auxiliares (Erdas/PAM)
)


def por_extensao(ext: str) -> Formato | None:
    """Formato aceito para a extensão (minúsculas, com ponto), ou None."""
    for f in FORMATOS.values():
        if ext in f.extensoes:
            return f
    return None


def recusado_por_extensao(ext: str) -> Recusado | None:
    for r in RECUSADOS.values():
        if ext in r.extensoes:
            return r
    return None


def lista() -> list[dict]:
    """O que a rota `/api/imagens/formatos` devolve e a tela desenha: aceitos primeiro (ordem da tabela),
    depois os recusados com a mensagem exata. É a MESMA tabela do código — a tela nunca mantém cópia."""
    aceitos = [
        {
            "aceito": True, "chave": f.chave, "rotulo": f.rotulo, "extensoes": list(f.extensoes),
            "georreferencia": f.georreferencia, "observacao": f.observacao,
        }
        for f in FORMATOS.values()
    ]
    recusados = [
        {
            "aceito": False, "chave": r.chave, "rotulo": r.rotulo, "extensoes": list(r.extensoes),
            "mensagem": r.mensagem,
        }
        for r in RECUSADOS.values()
    ]
    return aceitos + recusados


__all__ = [
    "FORMATOS", "RECUSADOS", "Formato", "Recusado", "SEM_ASSINATURA", "EXTENSOES_RASTER_EM_ZIP",
    "SIDECARES_EM_ZIP", "por_extensao", "recusado_por_extensao", "lista",
]
