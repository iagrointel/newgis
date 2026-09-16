"""Formatos aceitos (ADR 0005 seção 3.3 e 10.1; item L6-02-o-importacao-exportacao-formatos, item L0-04-d do
portão de ingestão). Restaurado 16/09 (achado da re-triagem pós-fusão: `app/ingestao/formatos.py` só trazia os
4 da fundação + os 5 do L6-02-o — os 4 formatos que o portão do L0-04-b pede a mais (GML, FlatGeobuf, GDB, e o
próprio DXF já presente) e 3 do L0-04-d (KMZ, GPX) nunca sobreviveram à fusão dos 198 ramos, embora o commit
que os mediu (`wt/g3fix`, "Ingestão vetorial: 13 formatos...") exista na árvore). Os 9 do portão do L0-04-d
(shapefile zipado, GeoPackage, GeoJSON, GeoJSONSeq, KML, KMZ, CSV/TXT, GPX, XLSX) e os 4 que o L0-04-b pede a
mais (GML, FlatGeobuf, DXF, File Geodatabase zipada) — o GDAL desta instalação tem driver para todos
(`ogrinfo --formats`). DWG (item L0-04-e, ADR 0020-leitura-de-cad-dxf-e-dwg) também entra: convertido para DXF
antes de ler pelo `dwg2dxf` do GNU LibreDWG (GPL-3, processo separado, nunca ligado à aplicação).

"gdb" é um ALIAS de "filegdb.zip" (mesmo conteúdo, mesma verificação, dois nomes em uso por duas gerações de
teste do mesmo item — nenhuma delas errada, então as duas ficam). MVT, PMTiles e MSSQLSpatial são só destino de
EXPORTAÇÃO (`app/ingestao/exportar.py`) — não entram aqui porque não são fonte de importação de camada nesta
plataforma (mosaico de tiles e banco externo, não arquivo de origem). Apache Parquet/GeoParquet e Oracle
Spatial (OCI) NÃO existem no GDAL desta instalação — declarados em FORMATOS_FORA_DE_ESCOPO, nunca prometidos.
Cada formato tem: extensões aceitas, prova pelo CONTEÚDO (nunca só a extensão — a mesma regra do L0-11/L7-03-b,
aqui aplicada ao tipo declarado no upload), e o driver GDAL usado na inspeção/carga."""

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
    "geojsonseq": Formato("geojsonseq", (".geojsonl", ".geojsons", ".ndjson"), "GeoJSON sequencial (NDJSON)",
                          "GeoJSONSeq"),
    "kml": Formato("kml", (".kml",), "KML", "LIBKML"),
    "kmz": Formato("kmz", (".kmz",), "KMZ (KML zipado)", "LIBKML"),
    "gpx": Formato("gpx", (".gpx",), "GPX (trilhas, rotas, pontos)", "GPX"),
    "dxf": Formato("dxf", (".dxf",), "DXF (CAD)", "DXF"),
    "dwg": Formato("dwg", (".dwg",), "DWG (CAD, convertido para DXF antes de ler)", "DXF"),
    "xlsx": Formato("xlsx", (".xlsx",), "Excel (XLSX)", "XLSX"),
    "filegdb.zip": Formato("filegdb.zip", (".zip",), "File Geodatabase (zip)", "OpenFileGDB"),
    # "gdb" é o MESMO formato de "filegdb.zip" com outro nome de item (portão do L0-04-b): duas gerações de
    # teste do mesmo item usam identificadores diferentes para o mesmo zip de File Geodatabase — em vez de
    # forçar uma a mudar (regra da casa: nunca afrouxar teste, e os dois estão certos), os dois convivem.
    "gdb": Formato("gdb", (".zip",), "File Geodatabase (zip)", "OpenFileGDB"),
    "gml": Formato("gml", (".gml", ".xml"), "GML", "GML"),
    "flatgeobuf": Formato("flatgeobuf", (".fgb",), "FlatGeobuf", "FlatGeobuf"),
}

# Formatos que o portão pede para DECLARAR como fora de escopo (nunca prometer, nunca esconder): a rota
# GET /api/importacoes/formatos os lista com aceito=False e o motivo, em vez de omiti-los como se não
# existissem. GeoParquet/Parquet e MapInfo TAB não têm driver nesta instalação do GDAL (medido, `ogrinfo
# --formats`); a lista é fechada por decisão de escopo do item L0-04-b, não por falta de medição.
FORMATOS_FORA_DE_ESCOPO: dict[str, str] = {
    "geoparquet": "o GDAL desta instalação não tem os drivers Parquet/GeoParquet (Apache Arrow) compilados",
    "mapinfo": "o driver MapInfo TAB não está nesta instalação; fora do escopo do item L0-04-b",
}

# formatos que só existem como DESTINO de exportação (app/ingestao/exportar.py); nunca aparecem em FORMATOS de
# importação nem em `GET /api/importacoes/formatos` — não são fonte de carga nesta plataforma.
FORMATOS_EXPORTACAO: dict[str, Formato] = {
    **FORMATOS,
    "mvt": Formato("mvt", (), "Mapbox Vector Tiles (mosaico)", "MVT"),
    "pmtiles": Formato("pmtiles", (), "PMTiles", "PMTiles"),
    "mssqlspatial": Formato("mssqlspatial", (), "Microsoft SQL Server (MSSQLSpatial)", "MSSQLSpatial"),
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


def _gdb_no_zip(zf: zipfile.ZipFile) -> str | None:
    """Nome do primeiro `<algo>.gdb/` no zip que tem ao menos um `a*.gdbtable` dentro (catálogo do FileGDB)."""
    diretorios: dict[str, int] = {}
    for info in zf.infolist():
        nome = info.filename.replace("\\", "/")
        m = nome.lower().find(".gdb/")
        if m == -1:
            continue
        base = nome[: m + 4]
        if nome.lower().endswith(".gdbtable"):
            diretorios[base] = diretorios.get(base, 0) + 1
    for base, n in diretorios.items():
        if n:
            return base
    return None


def verificar_conteudo(tipo_declarado: str, dados: bytes) -> None:
    """Levanta ConteudoNaoCorresponde quando os bytes não provam `tipo_declarado`."""
    if tipo_declarado == "shapefile.zip":
        zf = conferir_zip(dados)
        if not _shapefile_no_zip(zf):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo shapefile.zip: nenhum trio .shp/.shx/.dbf encontrado no zip"
            )
    elif tipo_declarado in ("filegdb.zip", "gdb"):
        zf = conferir_zip(dados)
        if _gdb_no_zip(zf) is None:
            raise ConteudoNaoCorresponde(
                f"conteúdo não corresponde ao tipo {tipo_declarado}: nenhuma pasta <nome>.gdb com catálogo "
                "(a*.gdbtable) encontrada no zip"
            )
    elif tipo_declarado == "kmz":
        zf = conferir_zip(dados)
        if not any(i.filename.lower().endswith(".kml") for i in zf.infolist()):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo kmz: nenhum arquivo .kml dentro do zip"
            )
    elif tipo_declarado == "gpx":
        inicio = dados[:4096]
        minusculo = inicio.lower()
        if b"<gpx" not in minusculo or b"topografix.com/gpx" not in dados[:65536].lower():
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gpx: falta a tag <gpx> do schema topografix no início do "
                "arquivo"
            )
    elif tipo_declarado == "gml":
        minusculo = dados[:65536].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
        if not minusculo.startswith(b"<") or (b"gml" not in minusculo and b"opengis.net" not in minusculo):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gml: o arquivo é " + _o_que_e(dados)
            )
    elif tipo_declarado == "flatgeobuf":
        if dados[:3] != b"fgb" or dados[3:4] != bytes([3]):  # magic "fgb" + versão 3 do FlatGeobuf
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo flatgeobuf: faltam os 4 bytes mágicos 'fgb'+versão 3"
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
    elif tipo_declarado == "geojsonseq":
        primeira = dados[:65536].lstrip(b"\x1e \t\r\n")
        if not primeira.startswith(b"{") or b'"type"' not in primeira[:4096] or b"\x00" in dados[:65536]:
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo geojsonseq: a primeira linha não é um objeto GeoJSON"
            )
    elif tipo_declarado == "kml":
        inicio = dados[:4096]
        if b"<kml" not in inicio or (b"<?xml" not in inicio and not inicio.lstrip().startswith(b"<kml")):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo kml: falta a tag <kml> no início do arquivo"
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
    elif tipo_declarado == "xlsx":
        e_zip = dados[:4] == b"PK\x03\x04"
        tem_indicio_ooxml = b"xl/workbook.xml" in dados[:65536] or b"[Content_Types]" in dados[:2048]
        if not e_zip or not tem_indicio_ooxml:
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo xlsx: não é um pacote OOXML (zip com xl/workbook.xml)"
            )
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
