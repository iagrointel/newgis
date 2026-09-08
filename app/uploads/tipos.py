"""Tipo declarado × bytes reais (item L0-04-a; ADR 0005 seção 3.3): o vocabulário aceito nesta fase de upload
(mais amplo que os 4 formatos que a inspeção sabe ler hoje, `app.ingestao.formatos.FORMATOS` — um arquivo
`dwg`/`parquet`/`gdb.zip` já pode ser ENVIADO e guardado; a inspeção (L0-04-b/c, formatos reduzidos) é quem
recusa depois, com `formato_nao_suportado`, se o usuário tentar importá-lo como camada. É o "aceito como
arquivo, recusado na inspeção" da seção 3.4 do ADR).

`verificar_conteudo(tipo_declarado, chave, tamanho)` prova o tipo pelos BYTES, nunca só pela extensão do nome:
para os tipos zip-baseados (shapefile.zip, kmz, xlsx, gdb.zip, zip genérico) delega a `_verificar_zip`, que
decide entre baixar o objeto inteiro (arquivo pequeno, reaproveita `app.ingestao.formatos.conferir_zip`, já
testado) ou inspecionar só o fim do arquivo por leitura em intervalo (`app.uploads.zip_remoto`, arquivo grande —
nunca materializa o objeto inteiro em RAM); para os demais, lê só o CABEÇALHO (e, no caso do parquet, também a
CAUDA) via `objetos.ler_intervalo`."""

from __future__ import annotations

from dataclasses import dataclass

from app import objetos
from app.ingestao import formatos as formatos_ingestao
from app.ingestao.formatos import ZipSuspeito
from app.uploads import zip_remoto

CABECALHO_BYTES = 65536
LIMITE_DOWNLOAD_INTEIRO = 64 * 1024 * 1024  # 64 MiB: ver docstring de app.uploads.zip_remoto


class ConteudoNaoCorresponde(ValueError):
    """Bytes não provam o tipo declarado (mesma família de erro de `app.ingestao.formatos.ConteudoNaoCorresponde`,
    reexportada com nome próprio para não acoplar os dois módulos por importação cruzada)."""


@dataclass(frozen=True)
class Tipo:
    nome: str
    extensoes: tuple[str, ...]
    rotulo: str
    zip_baseado: bool
    content_type_garagem: str  # só decide a EXTENSÃO cosmética da chave no Garage (app.objetos.EXTENSOES)


# content_type_garagem usa só os que já existem em app.objetos.EXTENSOES (evita editar aquele módulo, de outra
# trilha já entregue): tipos sem correspondência ficam com extensão ".bin" na chave — cosmético, a inspeção
# nunca lê a extensão da chave para decidir o formato (usa o `formato` declarado em POST /api/importacoes)
TIPOS: dict[str, Tipo] = {
    "shapefile.zip": Tipo("shapefile.zip", (".zip",), "Shapefile (zip)", True, "application/zip"),
    "gpkg": Tipo("gpkg", (".gpkg",), "GeoPackage", False, "application/octet-stream"),
    "geojson": Tipo("geojson", (".geojson", ".json"), "GeoJSON", False, "application/geo+json"),
    "kml": Tipo("kml", (".kml",), "KML", False, "application/octet-stream"),
    "kmz": Tipo("kmz", (".kmz",), "KMZ", True, "application/vnd.google-earth.kmz"),
    "csv": Tipo("csv", (".csv", ".txt"), "CSV / texto delimitado", False, "text/csv"),
    "gpx": Tipo("gpx", (".gpx",), "GPX", False, "application/octet-stream"),
    "xlsx": Tipo("xlsx", (".xlsx",), "Planilha (xlsx)", True, "application/zip"),
    "dxf": Tipo("dxf", (".dxf",), "DXF", False, "application/octet-stream"),
    "dwg": Tipo("dwg", (".dwg",), "DWG", False, "application/octet-stream"),
    "gdb.zip": Tipo("gdb.zip", (".zip",), "File Geodatabase (zip)", True, "application/zip"),
    "parquet": Tipo("parquet", (".parquet",), "GeoParquet", False, "application/octet-stream"),
    "fgb": Tipo("fgb", (".fgb",), "FlatGeobuf", False, "application/octet-stream"),
    "gml": Tipo("gml", (".gml",), "GML", False, "application/octet-stream"),
    "zip": Tipo("zip", (".zip",), "Zip (genérico)", True, "application/zip"),
}


def _cabecalho(chave: str, tamanho: int) -> bytes:
    fim = min(tamanho, CABECALHO_BYTES) - 1
    if fim < 0:
        return b""
    return objetos.ler_intervalo(chave, 0, fim)


def _cauda(chave: str, tamanho: int, n: int) -> bytes:
    inicio = max(0, tamanho - n)
    if tamanho == 0:
        return b""
    return objetos.ler_intervalo(chave, inicio, tamanho - 1)


def _texto_comeca_com(cabecalho: bytes, *prefixos: bytes) -> bool:
    """Ignora BOM UTF-8 e espaço em branco líder (a mesma tolerância que ogrinfo/GDAL aplicam)."""
    dado = cabecalho
    if dado[:3] == b"\xef\xbb\xbf":
        dado = dado[3:]
    dado = dado.lstrip(b" \t\r\n")
    return any(dado.startswith(p) for p in prefixos)


def _nomes_do_zip(chave: str, tamanho: int) -> list[str]:
    """Lista de nomes de entrada, pelo caminho pequeno (baixa tudo) ou grande (remoto) — ver módulo."""
    if tamanho <= LIMITE_DOWNLOAD_INTEIRO:
        dados = objetos.ler(chave)
        try:
            zf = formatos_ingestao.conferir_zip(dados)
        except ZipSuspeito as e:
            raise ConteudoNaoCorresponde(f"zip suspeito: {e}") from e
        return [i.filename for i in zf.infolist()]
    def leitor(a: int, b: int) -> bytes:
        return objetos.ler_intervalo(chave, a, b)

    try:
        entradas = zip_remoto.inspecionar_zip_remoto(leitor, tamanho)
    except ZipSuspeito as e:
        raise ConteudoNaoCorresponde(f"zip suspeito: {e}") from e
    return [e.nome for e in entradas]


def _o_que_e(cabecalho: bytes) -> str:
    if cabecalho[:2] == b"PK" and cabecalho[2:4] in (b"\x03\x04", b"\x05\x06", b"\x07\x08"):
        return "um zip"
    if cabecalho[:16] == b"SQLite format 3\x00":
        return "um SQLite/GeoPackage"
    if cabecalho[:4] == b"%PDF":
        return "um PDF"
    if cabecalho[:8] == b"\x89PNG\r\n\x1a\n":
        return "uma imagem PNG"
    if cabecalho[:4] == b"AC10":
        return "um DWG"
    if _texto_comeca_com(cabecalho, b"<?xml", b"<"):
        return "um XML/texto"
    return "um formato não reconhecido pelos bytes iniciais"


def _verificar_zip(tipo: str, chave: str, tamanho: int) -> None:
    nomes = _nomes_do_zip(chave, tamanho)
    bases = {n.rsplit("/", 1)[-1].lower() for n in nomes}
    if tipo in ("shapefile.zip", "gdb.zip") and not nomes:
        raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo {tipo}: zip vazio")
    if tipo == "shapefile.zip":
        por_base: dict[str, set[str]] = {}
        for n in nomes:
            base = n.rsplit("/", 1)[-1]
            if "." not in base:
                continue
            b, ext = base.rsplit(".", 1)
            por_base.setdefault(b.lower(), set()).add(ext.lower())
        if not any({"shp", "shx", "dbf"} <= exts for exts in por_base.values()):
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo shapefile.zip: nenhum trio .shp/.shx/.dbf encontrado no zip"
            )
    elif tipo == "kmz":
        if "doc.kml" not in bases and not any(n.lower().endswith(".kml") for n in nomes):
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo kmz: nenhum .kml encontrado no zip")
    elif tipo == "xlsx":
        if "xl/workbook.xml" not in {n.lower() for n in nomes}:
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo xlsx: xl/workbook.xml ausente do zip")
    elif tipo == "gdb.zip":
        gdb_dirs = {n.split("/", 1)[0] for n in nomes if "/" in n and n.split("/", 1)[0].lower().endswith(".gdb")}
        tem_gdbtable = any(n.lower().endswith("a00000001.gdbtable") for n in nomes)
        if not gdb_dirs or not tem_gdbtable:
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo gdb.zip: diretório *.gdb/ com a00000001.gdbtable ausente"
            )
    # tipo == "zip" (genérico): a verificação de zip válido/seguro já rodou em _nomes_do_zip; nenhuma exigência
    # de conteúdo além disso — a inspeção decide o que fazer com o que encontrar dentro (seção 3.4 do ADR)


def verificar_conteudo(tipo_declarado: str, chave: str, tamanho: int) -> None:
    """Levanta `ConteudoNaoCorresponde` quando os bytes não provam `tipo_declarado`. `tamanho` é o tamanho REAL
    do objeto já gravado no Garage (nunca o declarado pelo cliente)."""
    tipo = TIPOS.get(tipo_declarado)
    if tipo is None:
        raise ConteudoNaoCorresponde(f"tipo declarado desconhecido nesta instalação: {tipo_declarado}")
    if tamanho == 0:
        raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo {tipo_declarado}: arquivo vazio")

    if tipo.zip_baseado:
        _verificar_zip(tipo_declarado, chave, tamanho)
        return

    cabecalho = _cabecalho(chave, tamanho)

    if tipo_declarado == "gpkg":
        if cabecalho[:16] != b"SQLite format 3\x00":
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo gpkg: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "geojson":
        inicio = cabecalho.lstrip(b" \t\r\n\xef\xbb\xbf")
        if not inicio.startswith(b"{") or b'"type"' not in cabecalho[:4096]:
            raise ConteudoNaoCorresponde(
                f"conteúdo não corresponde ao tipo geojson: o arquivo é {_o_que_e(cabecalho)}"
            )
    elif tipo_declarado == "kml":
        if b"<kml" not in cabecalho[:4096]:
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo kml: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "gpx":
        if b"<gpx" not in cabecalho[:4096]:
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo gpx: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "gml":
        if b"opengis.net/gml" not in cabecalho[:4096]:
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo gml: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "csv":
        if b"\x00" in cabecalho:
            raise ConteudoNaoCorresponde("conteúdo não corresponde ao tipo csv: o arquivo tem bytes nulos (binário)")
    elif tipo_declarado == "dxf":
        if cabecalho[:20] == b"AutoCAD Binary DXF\r\n":
            raise ConteudoNaoCorresponde(
                "conteúdo não corresponde ao tipo dxf: DXF binário não é aceito nesta instalação"
            )
        if not _texto_comeca_com(cabecalho, b"0\r\nSECTION", b"0\nSECTION", b"999\r\n", b"999\n"):
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo dxf: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "dwg":
        if cabecalho[:4] != b"AC10":
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo dwg: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "fgb":
        if cabecalho[:3] != b"fgb":
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo fgb: o arquivo é {_o_que_e(cabecalho)}")
    elif tipo_declarado == "parquet":
        cauda = _cauda(chave, tamanho, 4)
        if cabecalho[:4] != b"PAR1" or cauda[-4:] != b"PAR1":
            raise ConteudoNaoCorresponde(f"conteúdo não corresponde ao tipo parquet: o arquivo é {_o_que_e(cabecalho)}")
    else:  # pragma: no cover — TIPOS e o dispatch acima são mantidos em sincronia manualmente
        raise ConteudoNaoCorresponde(f"tipo declarado sem verificação implementada: {tipo_declarado}")
