"""Formatos aceitos nesta instalação (ADR 0005 seção 3.3 e 10.1). Cada um tem: extensões aceitas, prova pelo
CONTEÚDO (nunca só a extensão — a mesma regra do L0-11/L7-03-b, aqui aplicada ao tipo declarado no upload) e o
driver GDAL usado na inspeção/carga. Os 9 formatos do portão do L0-04-d (shapefile zipado, GeoPackage, GeoJSON,
GeoJSONSeq, KML, KMZ, CSV/TXT, GPX, XLSX) e os 4 que o portão do L0-04-b pede a mais (GML, FlatGeobuf, DXF,
File Geodatabase zipada) estão todos aqui, porque o GDAL 3.8.4 desta instalação tem driver para todos —
conferido com `ogrinfo --formats` e gravado em tests/medidas/L0-04-d-formatos-base.json.

O que NÃO entra e por quê: **DWG** depende de conversor de terceiro (ODA File Converter, binário gratuito com
licença própria, ou LibreDWG sob GPL-3) — é decisão do dono, registrada como pendência do item L0-04-e, e não
uma limitação técnica desta camada. `formato_nao_suportado` continua sendo a recusa para qualquer tipo fora
deste dicionário.

Profundidade honesta: aceitar e inspecionar não é o mesmo que tratar a semântica própria de cada formato. O
tratamento de blocos/georreferência do DXF fica no item L0-04-e e o de domínios/subtipos da File Geodatabase
no L0-04-f; aqui os dois entram pelo caminho comum do GDAL, com as camadas todas listadas na proposta."""

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
    "geojsonseq": Formato("geojsonseq", (".geojsonl", ".geojsons", ".ndjson"), "GeoJSON Sequence", "GeoJSONSeq"),
    "csv": Formato("csv", (".csv", ".txt", ".tsv", ".psv"), "CSV / texto delimitado", "CSV"),
    "kml": Formato("kml", (".kml",), "KML", "LIBKML"),
    "kmz": Formato("kmz", (".kmz",), "KMZ (KML zipado)", "LIBKML"),
    "gpx": Formato("gpx", (".gpx",), "GPX (trilhas, rotas, pontos)", "GPX"),
    "xlsx": Formato("xlsx", (".xlsx", ".xlsm"), "Planilha XLSX", "XLSX"),
    "gml": Formato("gml", (".gml", ".xml"), "GML", "GML"),
    "flatgeobuf": Formato("flatgeobuf", (".fgb",), "FlatGeobuf", "FlatGeobuf"),
    "dxf": Formato("dxf", (".dxf",), "DXF (AutoCAD)", "DXF"),
    "gdb": Formato("gdb", (".zip", ".gdb.zip"), "File Geodatabase (zip)", "OpenFileGDB"),
}

# Formatos cuja leitura depende de programa de TERCEIRO com licença própria: nunca entram no dicionário acima
# sem decisão do dono (item L0-04-e). A recusa cita o motivo em vez de fingir que o tipo não existe.
FORMATOS_QUE_DEPENDEM_DE_LICENCA: dict[str, str] = {
    "dwg": ("a leitura de DWG depende de conversor de terceiro (ODA File Converter, licença própria, ou "
            "LibreDWG sob GPL-3); esta instalação não o traz e a escolha do conversor é decisão do dono. "
            "Converta para DXF e envie como 'dxf'."),
}


class ArquivoRecusado(ValueError):
    """Mãe de toda recusa de ENTRADA da ingestão. A rota captura ESTA classe e devolve 422 com mensagem em
    português; classes irmãs sem mãe comum foi exatamente o defeito que fazia um zip malformado sair como 500
    (achado do adversário do turno 3). Toda recusa nova de conteúdo herda daqui."""


class ZipSuspeito(ArquivoRecusado):
    """Zip-bomba, zip malformado ou caminho malicioso (ADR 0005 seção 3.2): nunca chega a ser extraído."""


class ConteudoNaoCorresponde(ArquivoRecusado):
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


def _membros_do_zip(dados: bytes) -> list[str]:
    return [i.filename for i in conferir_zip(dados).infolist()]


def _e_xml_com(dados: bytes, marcas: tuple[bytes, ...]) -> bool:
    """XML (com ou sem BOM/declaração) cuja abertura cita uma das marcas nos primeiros 64 KiB."""
    amostra = dados[:65536].lstrip(b"\xef\xbb\xbf \r\n\t")
    if not amostra.startswith(b"<"):
        return False
    minusculo = dados[:65536].lower()
    return any(m in minusculo for m in marcas)


def _verificar_kmz(dados: bytes) -> None:
    membros = _membros_do_zip(dados)
    if not any(m.lower().endswith(".kml") for m in membros):
        raise ConteudoNaoCorresponde(
            "conteúdo não corresponde ao tipo kmz: nenhum arquivo .kml dentro do zip"
        )


def _verificar_xlsx(dados: bytes) -> None:
    membros = _membros_do_zip(dados)
    if "xl/workbook.xml" not in membros:
        raise ConteudoNaoCorresponde(
            "conteúdo não corresponde ao tipo xlsx: falta xl/workbook.xml no pacote"
        )


def _verificar_gdb(dados: bytes) -> None:
    membros = _membros_do_zip(dados)
    if not any(".gdb/" in m.lower().replace("\\", "/") for m in membros):
        raise ConteudoNaoCorresponde(
            "conteúdo não corresponde ao tipo gdb: nenhuma pasta .gdb dentro do zip"
        )


def _verificar_dxf(dados: bytes) -> None:
    if dados[:22] == b"AutoCAD Binary DXF\r\n\x1a\x00":
        return  # DXF binário: o driver do GDAL lê
    amostra = dados[:65536].upper()
    if b"SECTION" not in amostra or (b"HEADER" not in amostra and b"ENTITIES" not in amostra):
        raise ConteudoNaoCorresponde(
            "conteúdo não corresponde ao tipo dxf: o arquivo é " + _o_que_e(dados)
        )


def _verificar_geojsonseq(dados: bytes) -> None:
    """Uma feição por linha (RS opcional). A 1ª linha não vazia tem de ser um objeto JSON com "type"."""
    for linha in dados[:65536].splitlines():
        limpa = linha.strip(b"\x1e \t\r\n\xef\xbb\xbf")
        if not limpa:
            continue
        if not limpa.startswith(b"{") or b'"type"' not in limpa:
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo geojsonseq: a primeira linha não é um objeto GeoJSON"
            )
        return
    raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo geojsonseq: arquivo vazio")


def verificar_conteudo(tipo_declarado: str, dados: bytes) -> None:
    """Levanta ConteudoNaoCorresponde quando os bytes não provam `tipo_declarado`."""
    if tipo_declarado == "kmz":
        return _verificar_kmz(dados)
    if tipo_declarado == "xlsx":
        return _verificar_xlsx(dados)
    if tipo_declarado == "gdb":
        return _verificar_gdb(dados)
    if tipo_declarado == "dxf":
        return _verificar_dxf(dados)
    if tipo_declarado == "geojsonseq":
        return _verificar_geojsonseq(dados)
    if tipo_declarado == "kml":
        if not _e_xml_com(dados, (b"<kml", b"http://www.opengis.net/kml",
                                  b"http://earth.google.com/kml")):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo kml: o arquivo é " + _o_que_e(dados)
            )
        return
    if tipo_declarado == "gpx":
        if not _e_xml_com(dados, (b"<gpx", b"http://www.topografix.com/gpx")):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gpx: o arquivo é " + _o_que_e(dados)
            )
        return
    if tipo_declarado == "gml":
        if not _e_xml_com(dados, (b"gml", b"http://www.opengis.net/wfs")):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gml: o arquivo é " + _o_que_e(dados)
            )
        return
    if tipo_declarado == "flatgeobuf":
        if dados[:4] != b"\x66\x67\x62\x03":  # "fgb" + versão 3 (magic do FlatGeobuf)
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo flatgeobuf: o arquivo é " + _o_que_e(dados)
            )
        return
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
    elif tipo_declarado == "csv":
        amostra = dados[:65536]
        if b"\x00" in amostra:
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo csv: o arquivo tem bytes nulos (binário)")
    elif tipo_declarado in FORMATOS_QUE_DEPENDEM_DE_LICENCA:
        raise ConteudoNaoCorresponde(FORMATOS_QUE_DEPENDEM_DE_LICENCA[tipo_declarado])
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
