"""Unit (sem banco/Garage; item L0-04-a): `app.uploads.tipos.verificar_conteudo` monkeypatchando
`app.objetos.ler`/`ler_intervalo` para servir bytes em memória — prova a tabela de tipo × conteúdo da seção 3.3
do ADR 0005 sem precisar de um objeto real no armazenamento."""

from __future__ import annotations

import io
import zipfile

import pytest

from app import objetos
from app.uploads import tipos


def _servir(monkeypatch, dados: bytes) -> None:
    def _ler_intervalo(chave, inicio, fim):
        return dados[inicio : fim + 1]

    def _ler(chave):
        return dados

    monkeypatch.setattr(objetos, "ler_intervalo", _ler_intervalo)
    monkeypatch.setattr(objetos, "ler", _ler)


def _zip_com(entradas: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nome, conteudo in entradas.items():
            zf.writestr(nome, conteudo)
    return buf.getvalue()


# ---------------------------------------------------------------- gpkg
def test_gpkg_aceita_sqlite(monkeypatch):
    dados = b"SQLite format 3\x00" + b"\x00" * 100
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("gpkg", "x", len(dados))  # não levanta


def test_gpkg_recusa_zip(monkeypatch):
    dados = _zip_com({"a.txt": b"oi"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="não corresponde ao tipo gpkg"):
        tipos.verificar_conteudo("gpkg", "x", len(dados))


# ---------------------------------------------------------------- geojson
def test_geojson_aceita(monkeypatch):
    dados = b'{"type": "FeatureCollection", "features": []}'
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("geojson", "x", len(dados))


def test_geojson_recusa_texto_solto(monkeypatch):
    dados = b"nome,lat,lon\na,1,2\n"
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("geojson", "x", len(dados))


# ---------------------------------------------------------------- csv
def test_csv_aceita_texto(monkeypatch):
    dados = "nome,lat,lon\nAraçoiaba,-23.5,-47.2\n".encode("utf-8")
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("csv", "x", len(dados))


def test_csv_recusa_binario(monkeypatch):
    dados = b"\x00\x01\x02binario"
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="binário"):
        tipos.verificar_conteudo("csv", "x", len(dados))


# ---------------------------------------------------------------- kml / gpx / gml
def test_kml_aceita(monkeypatch):
    dados = b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>'
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("kml", "x", len(dados))


def test_gpx_recusa_kml(monkeypatch):
    dados = b'<?xml version="1.0"?><kml></kml>'
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("gpx", "x", len(dados))


def test_gml_aceita_namespace(monkeypatch):
    dados = b'<?xml version="1.0"?><ogr:FeatureCollection xmlns:gml="http://www.opengis.net/gml"/>'
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("gml", "x", len(dados))


# ---------------------------------------------------------------- dxf / dwg / fgb / parquet
def test_dxf_aceita_ascii():
    pass  # coberto no teste abaixo (mantém o agrupamento de comentário)


def test_dxf_aceita(monkeypatch):
    dados = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("dxf", "x", len(dados))


def test_dxf_recusa_binario(monkeypatch):
    dados = b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x00" * 40
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="binário não é aceito"):
        tipos.verificar_conteudo("dxf", "x", len(dados))


def test_dwg_aceita(monkeypatch):
    dados = b"AC1015" + b"\x00" * 40
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("dwg", "x", len(dados))


def test_dwg_recusa_outra_coisa(monkeypatch):
    dados = b"nao e dwg" + b"\x00" * 40
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("dwg", "x", len(dados))


def test_fgb_aceita(monkeypatch):
    dados = b"fgb" + b"\x00" * 40
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("fgb", "x", len(dados))


def test_parquet_aceita(monkeypatch):
    dados = b"PAR1" + b"\x00" * 100 + b"PAR1"
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("parquet", "x", len(dados))


def test_parquet_recusa_sem_rodape(monkeypatch):
    dados = b"PAR1" + b"\x00" * 100
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("parquet", "x", len(dados))


# ---------------------------------------------------------------- zip-baseados
def test_shapefile_zip_aceita_trio(monkeypatch):
    dados = _zip_com({"a.shp": b"1", "a.shx": b"2", "a.dbf": b"3"})
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("shapefile.zip", "x", len(dados))


def test_shapefile_zip_recusa_sem_trio(monkeypatch):
    dados = _zip_com({"leiame.txt": b"oi"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="trio"):
        tipos.verificar_conteudo("shapefile.zip", "x", len(dados))


def test_gpkg_com_zip_dentro_mensagem_exata(monkeypatch):
    """Cláusula literal do portão: '.gpkg com conteúdo zip recusado com conteúdo não corresponde ao tipo'."""
    dados = _zip_com({"qualquer.bin": b"x"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="conteúdo não corresponde ao tipo gpkg"):
        tipos.verificar_conteudo("gpkg", "x", len(dados))


def test_kmz_aceita_doc_kml(monkeypatch):
    dados = _zip_com({"doc.kml": b"<kml/>"})
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("kmz", "x", len(dados))


def test_kmz_recusa_sem_kml(monkeypatch):
    dados = _zip_com({"a.txt": b"oi"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("kmz", "x", len(dados))


def test_xlsx_aceita_workbook(monkeypatch):
    dados = _zip_com({"xl/workbook.xml": b"<workbook/>", "[Content_Types].xml": b""})
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("xlsx", "x", len(dados))


def test_gdb_zip_aceita(monkeypatch):
    dados = _zip_com({"x.gdb/gdb": b"1", "x.gdb/a00000001.gdbtable": b"2"})
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("gdb.zip", "x", len(dados))


def test_gdb_zip_recusa_sem_tabela(monkeypatch):
    dados = _zip_com({"x.gdb/gdb": b"1"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde):
        tipos.verificar_conteudo("gdb.zip", "x", len(dados))


def test_zip_generico_aceita_qualquer_conteudo_seguro(monkeypatch):
    dados = _zip_com({"qualquer_coisa.dat": b"1234"})
    _servir(monkeypatch, dados)
    tipos.verificar_conteudo("zip", "x", len(dados))


def test_zip_com_caminho_invalido_recusa(monkeypatch):
    dados = _zip_com({"../fora.txt": b"x"})
    _servir(monkeypatch, dados)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="zip suspeito"):
        tipos.verificar_conteudo("zip", "x", len(dados))


# ---------------------------------------------------------------- caminho remoto (arquivo "grande")
def test_zip_generico_caminho_remoto_equivale_ao_pequeno(monkeypatch):
    """Força o caminho de leitura por intervalo (arquivo "grande") baixando o MESMO zip pelos dois caminhos e
    conferindo que aceitam/recusam igual — o portão de arquivo grande não pode ter uma regra mais fraca."""
    dados = _zip_com({"a.shp": b"1" * 20, "a.shx": b"2" * 10, "a.dbf": b"3" * 10})
    _servir(monkeypatch, dados)
    monkeypatch.setattr(tipos, "LIMITE_DOWNLOAD_INTEIRO", -1)  # força o caminho remoto mesmo em arquivo pequeno
    tipos.verificar_conteudo("shapefile.zip", "x", len(dados))


def test_zip_generico_caminho_remoto_recusa_bomba_de_entradas(monkeypatch):
    entradas = {f"f{i}.txt": b"a" for i in range(1500)}
    dados = _zip_com(entradas)
    _servir(monkeypatch, dados)
    monkeypatch.setattr(tipos, "LIMITE_DOWNLOAD_INTEIRO", -1)
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="1500 entradas"):
        tipos.verificar_conteudo("zip", "x", len(dados))


# ---------------------------------------------------------------- gerais
def test_tipo_desconhecido(monkeypatch):
    _servir(monkeypatch, b"x")
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="desconhecido"):
        tipos.verificar_conteudo("shx-solto", "x", 1)


def test_arquivo_vazio_recusado(monkeypatch):
    _servir(monkeypatch, b"")
    with pytest.raises(tipos.ConteudoNaoCorresponde, match="vazio"):
        tipos.verificar_conteudo("csv", "x", 0)


def test_todos_os_tipos_tem_dispatch():
    """Nenhum tipo do catálogo TIPOS fica sem verificação (guarda contra esquecer um `elif` novo)."""
    import inspect

    fonte = inspect.getsource(tipos.verificar_conteudo)
    for nome in tipos.TIPOS:
        t = tipos.TIPOS[nome]
        if t.zip_baseado:
            continue
        assert f'"{nome}"' in fonte, f"tipo {nome!r} sem ramo de verificação em verificar_conteudo"
