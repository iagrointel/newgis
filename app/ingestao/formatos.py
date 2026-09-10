"""Formatos aceitos: shapefile zipado, GeoPackage, GeoJSON, CSV/TXT (lat/lon) — ADR 0005 seções 3.3 e 10.1 — e
os dois de CAD, DXF e DWG (ADR 0020, item L0-04-e). Cada um tem: extensões aceitas, prova pelo CONTEÚDO (nunca
só a extensão — a mesma regra do L0-11/L7-03-b, aqui aplicada ao tipo declarado no upload), e o driver GDAL
usado na inspeção/carga. O que ainda falta (KML/KMZ, GPX, XLSX, FileGDB, FlatGeobuf, GML, MapInfo, GeoParquet)
está documentado no ADR 0005 seções 10-12 e no handoff do item; `formato_nao_suportado` é a recusa para
qualquer um deles."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO

ZIP_ENTRADAS_MAX = 1000
ZIP_DESCOMPRIMIDO_MAX = 8 * 1024 * 1024 * 1024  # 8 GiB
ZIP_RAZAO_MAX = 100
ZIP_NOME_MAX = 255


@dataclass(frozen=True)
class Formato:
    nome: str
    extensoes: tuple[str, ...]
    rotulo: str
    driver: str


FORMATOS: dict[str, Formato] = {
    "shapefile.zip": Formato("shapefile.zip", (".zip",), "Shapefile (zip)", "ESRI Shapefile"),
    "gpkg": Formato("gpkg", (".gpkg",), "GeoPackage", "GPKG"),
    "geojson": Formato("geojson", (".geojson", ".json"), "GeoJSON", "GeoJSON"),
    "csv": Formato("csv", (".csv", ".txt", ".tsv", ".psv"), "CSV / texto delimitado", "CSV"),
    "dxf": Formato("dxf", (".dxf",), "DXF (desenho CAD)", "DXF"),
    "dwg": Formato("dwg", (".dwg",), "DWG (desenho CAD)", "DXF"),
}


class ZipSuspeito(ValueError):
    """Zip-bomba ou caminho malicioso (ADR 0005 seção 3.2): nunca chega a ser extraído."""


class ConteudoNaoCorresponde(ValueError):
    """Bytes não provam o tipo declarado (ADR 0005 seção 3.3)."""


def conferir_zip(dados: bytes) -> zipfile.ZipFile:
    """Levanta ZipSuspeito ANTES de qualquer extração: nº de entradas, tamanho total descomprimido, razão de
    compressão, nome de caminho (sem `..`, `/` inicial, `\\`, byte de controle, > 255 bytes), sem zip aninhado,
    sem link simbólico (atributo externo alto = modo unix com bit S_IFLNK)."""
    try:
        zf = zipfile.ZipFile(BytesIO(dados))
        infos = zf.infolist()
    except zipfile.BadZipFile as e:
        raise ZipSuspeito(f"zip inválido: {e}") from e
    if len(infos) > ZIP_ENTRADAS_MAX:
        raise ZipSuspeito(f"zip com {len(infos)} entradas; o máximo é {ZIP_ENTRADAS_MAX}")
    total_descomprimido = sum(i.file_size for i in infos)
    total_comprimido = max(1, sum(i.compress_size for i in infos))
    razao = total_descomprimido / total_comprimido
    if total_descomprimido > ZIP_DESCOMPRIMIDO_MAX:
        raise ZipSuspeito(f"zip descomprimiria para {total_descomprimido} bytes; o máximo é {ZIP_DESCOMPRIMIDO_MAX}")
    if razao > ZIP_RAZAO_MAX:
        raise ZipSuspeito(f"razão de compressão {razao:.1f}x acima do máximo ({ZIP_RAZAO_MAX}x)")
    for info in infos:
        nome = info.filename
        if len(nome.encode("utf-8", errors="replace")) > ZIP_NOME_MAX:
            raise ZipSuspeito(f"nome de entrada com mais de {ZIP_NOME_MAX} bytes: {nome!r}")
        if ".." in nome.replace("\\", "/").split("/") or nome.startswith("/") or "\\" in nome:
            raise ZipSuspeito(f"caminho de entrada inválido: {nome!r}")
        if any(ord(c) < 0x20 for c in nome):
            raise ZipSuspeito(f"caractere de controle no nome de entrada: {nome!r}")
        if nome.lower().endswith(".zip"):
            raise ZipSuspeito(f"zip aninhado: {nome!r}")
        modo_unix = (info.external_attr >> 16) & 0xFFFF
        if modo_unix and (modo_unix & 0xF000) == 0xA000:  # S_IFLNK
            raise ZipSuspeito(f"link simbólico no zip: {nome!r}")
    return zf


def _shapefile_no_zip(zf: zipfile.ZipFile) -> list[str]:
    """Nomes-base (sem extensão) que têm ao menos .shp+.shx+.dbf no zip, case-insensitive."""
    por_base: dict[str, set[str]] = {}
    for info in zf.infolist():
        nome = info.filename.rsplit("/", 1)[-1]
        if "." not in nome:
            continue
        base, ext = nome.rsplit(".", 1)
        por_base.setdefault(base.lower(), set()).add(ext.lower())
    return [b for b, exts in por_base.items() if {"shp", "shx", "dbf"} <= exts]


def verificar_conteudo(tipo_declarado: str, dados: bytes) -> None:
    """Levanta ConteudoNaoCorresponde quando os bytes não provam `tipo_declarado`."""
    if tipo_declarado == "shapefile.zip":
        zf = conferir_zip(dados)
        if not _shapefile_no_zip(zf):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo shapefile.zip: nenhum trio .shp/.shx/.dbf encontrado no zip"
            )
    elif tipo_declarado == "gpkg":
        if dados[:16] != b"SQLite format 3\x00":
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gpkg: o arquivo é " + _o_que_e(dados)
            )
    elif tipo_declarado == "geojson":
        inicio = dados[:4096].lstrip()
        if not inicio.startswith(b"{") or b'"type"' not in dados[:4096]:
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo geojson: o arquivo é " + _o_que_e(dados)
            )
    elif tipo_declarado in ("dxf", "dwg"):
        from app.ingestao import cad

        visto = cad.assinatura(dados[:8192])
        if tipo_declarado == "dwg":
            if visto != "dwg":
                raise ConteudoNaoCorresponde(
                    "conteúdo não corresponde ao tipo dwg: os bytes iniciais não trazem a marca de versão do "
                    "DWG (AC10xx)")
        elif visto == "dxf_binario":
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo dxf: o arquivo é um DXF BINÁRIO, formato que o leitor de DXF "
                "do GDAL não abre; grave como DXF de texto (ASCII)")
        elif visto == "dwg":
            _marca, versao = cad.versao_dwg(dados[:8192])
            raise ConteudoNaoCorresponde(
                f"conteúdo não corresponde ao tipo dxf: o arquivo é um DWG na versão {versao}; declare o tipo dwg")
        elif visto != "dxf":
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo dxf: o arquivo é " + _o_que_e(dados))
    elif tipo_declarado == "csv":
        amostra = dados[:65536]
        if b"\x00" in amostra:
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo csv: o arquivo tem bytes nulos (binário)")
    else:
        raise ConteudoNaoCorresponde(f"tipo declarado desconhecido nesta instalação: {tipo_declarado}")


def _o_que_e(dados: bytes) -> str:
    if dados[:4] == b"PK\x03\x04":
        return "um zip"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "uma imagem PNG"
    if dados[:4] in (b"%PDF",):
        return "um PDF"
    return "um formato não reconhecido pelos bytes iniciais"


def shapefile_membros(zf: zipfile.ZipFile, base: str) -> dict[str, str]:
    """{extensão: nome do membro no zip} para a base (primeiro trio .shp encontrado, case-insensitive)."""
    saida: dict[str, str] = {}
    for info in zf.infolist():
        nome = info.filename.rsplit("/", 1)[-1]
        if "." not in nome:
            continue
        b, ext = nome.rsplit(".", 1)
        if b.lower() == base.lower():
            saida[ext.lower()] = info.filename
    return saida
