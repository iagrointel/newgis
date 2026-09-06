"""Portão de pronto do item L1-01-b (validação e isolamento da entrada raster; ADR 0015), cláusula a cláusula, cada
caso com um arquivo SINTÉTICO pequeno gerado em tmp_path (rasterio/GDAL ou cabeçalho TIFF/zip fabricado à mão).
Cada caso importa certo ou recusa/pede com a mensagem exata em português — nunca silêncio. Sem banco. Os 3 casos
do adversário (IFD circular, JP2 truncado, 65.535 bandas) estão aqui. Tempo e pico de RSS do subprocesso de cada
caso são gravados em tests/medidas/L1-01-b.json no fim do módulo."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.raster import validacao as v

RAIZ = Path(__file__).resolve().parents[2]
MEDIDAS = RAIZ / "tests" / "medidas" / "L1-01-b.json"
_registro: dict[str, dict] = {}
TRANSFORMACAO_BR = from_origin(-48.0, -15.0, 0.001, 0.001)      # graus, Goiás
TRANSFORMACAO_UTM = from_origin(300000.0, 8300000.0, 10.0, 10.0)  # metros, EPSG:31983
WKT_CUSTOM = ('PROJCS["Local sem EPSG",GEOGCS["GCS_SIRGAS",DATUM["D_SIRGAS_2000",SPHEROID["GRS_1980",6378137,'
              '298.257222101]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_'
              'Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-47.5],PARAMETER["scale_'
              'factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",10000000],UNIT["Meter",1]]')


def tif(caminho: Path, *, crs="EPSG:4674", nodata=0, dtype="uint8", count=3, transformacao=TRANSFORMACAO_BR,
        tags=None, largura=32, altura=32, **opcoes) -> Path:
    with rasterio.open(caminho, "w", driver="GTiff", width=largura, height=altura, count=count, dtype=dtype,
                       crs=crs, nodata=nodata, transform=transformacao, **opcoes) as d:
        if not opcoes.get("sparse_ok"):
            d.write(np.full((count, altura, largura), 7, dtype))
        d.update_tags(**(tags if tags is not None else {"TIFFTAG_DATETIME": "2026:08:01 10:00:00"}))
    return caminho


def tiff_fabricado(caminho: Path, *, largura: int, altura: int, bandas: int = 1, proximo_ifd: int | None = 0,
                   bigtiff: bool = False) -> Path:
    """TIFF clássico mínimo escrito à mão (little-endian): 10 tags, dados de faixa apontando para o offset 8 —
    KB em disco seja qual for a dimensão declarada. `proximo_ifd=8` fecha o IFD sobre ele mesmo (circular)."""
    assert not bigtiff
    entradas = [(256, 4, 1, largura), (257, 4, 1, altura), (258, 3, 1, 8), (259, 3, 1, 1), (262, 3, 1, 1),
                (273, 4, 1, 8), (277, 3, 1, bandas), (278, 4, 1, altura), (279, 4, 1, 1), (284, 3, 1, 1)]
    ifd = struct.pack("<H", len(entradas))
    for tag, tipo, n, valor in entradas:
        ifd += struct.pack("<HHI", tag, tipo, n) + (struct.pack("<H", valor) + b"\0\0" if tipo == 3
                                                    else struct.pack("<I", valor))
    ifd += struct.pack("<I", 8 if proximo_ifd == 8 else 0)
    caminho.write_bytes(b"II*\x00" + struct.pack("<I", 8) + ifd)
    return caminho


def zip_com(caminho: Path, arquivos: list[Path]) -> Path:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for a in arquivos:
            zf.write(a, a.name)
    return caminho


def zip_bomba_declarada(caminho: Path, fator: int = 50) -> Path:
    """Zip de UMA entrada pequena cujo cabeçalho (local + diretório central) declara tamanho descompactado = fator ×
    o comprimido — o `file_size` mentiroso é o que o portão pede; nada de gerar gigabytes."""
    dados = os.urandom(2048)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imagem.tif", dados)
    bruto = bytearray(caminho.read_bytes())
    with zipfile.ZipFile(caminho) as zf:
        info = zf.infolist()[0]
    comprimido = info.compress_size
    mentira = struct.pack("<I", comprimido * fator)
    # local header: tamanho descompactado no offset 22; diretório central: offset 24
    local = bruto.find(b"PK\x03\x04")
    central = bruto.find(b"PK\x01\x02")
    bruto[local + 22:local + 26] = mentira
    bruto[central + 24:central + 28] = mentira
    caminho.write_bytes(bytes(bruto))
    return caminho


def validar(nome: str, caminho: Path, **kw) -> dict:
    """Roda a validação e guarda tempo/RAM do subprocesso para tests/medidas/L1-01-b.json."""
    rel = v.validar(caminho, **kw)
    sub = rel.get("subprocesso") or {}
    _registro[nome] = {"estado": rel["estado"], "tempo_s": sub.get("tempo_s"), "ram_pico_kb": sub.get("ram_pico_kb"),
                       "morte": sub.get("morte"), "bytes": caminho.stat().st_size if caminho.exists() else None}
    assert rel["estado"] in ("aceito", "pendente", "recusado")
    if rel["estado"] == "recusado":
        assert rel["problemas"], "recusa sem mensagem"
    if rel["estado"] == "pendente":
        assert rel["pendencias"], "pendência sem pergunta"
    if sub:
        assert sub["ram_pico_kb"] < v.RLIMIT_AS_MB * 1024, "o subprocesso passou do RLIMIT_AS medido"
    return rel


@pytest.fixture(scope="module", autouse=True)
def gravar_medidas():
    yield
    if not _registro:
        return
    sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                         check=False).stdout.strip()
    medidas = {}
    for nome, m in _registro.items():
        if m["tempo_s"] is None:
            continue
        medidas[f"{nome}_tempo_s"] = {"valor": m["tempo_s"], "unidade": "s",
                                      "comando": f"tests/unit/test_raster_validacao.py caso {nome} "
                                                 f"({m['estado']}, arquivo {m['bytes']} bytes)"}
        medidas[f"{nome}_ram_pico_kb"] = {"valor": m["ram_pico_kb"], "unidade": "kB",
                                          "comando": f"ru_maxrss do subprocesso (os.wait4) no caso {nome}"
                                                     + (f"; morte={m['morte']}" if m["morte"] else "")}
    picos = [m["ram_pico_kb"] for m in _registro.values() if m["ram_pico_kb"]]
    medidas["ram_pico_maximo_kb"] = {"valor": max(picos), "unidade": "kB",
                                     "comando": f"maior ru_maxrss entre os {len(picos)} casos; RLIMIT_AS="
                                                f"{v.RLIMIT_AS_MB} MB, RLIMIT_CPU={v.RLIMIT_CPU_S} s, "
                                                f"timeout={v.TIMEOUT_S} s"}
    medidas["casos"] = {"valor": len(_registro), "unidade": "casos",
                        "comando": "cada caso = arquivo sintético gerado em tmp_path pelo teste"}
    MEDIDAS.write_text(json.dumps({"item": "L1-01-b", "medidas": medidas,
                                   "gerado_em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "git_sha": sha},
                                  ensure_ascii=False, indent=1) + "\n")


# ------------------------------------------------------------------ cláusulas do portão
def test_sem_crs_pede_e_resposta_grava(tmp_path):
    p = tif(tmp_path / "sem_crs.tif", crs=None)
    rel = validar("sem_crs", p)
    assert rel["estado"] == "pendente"
    assert [x["campo"] for x in rel["pendencias"]] == ["crs"]
    msg = rel["pendencias"][0]["mensagem"]
    assert "informe o código EPSG" in msg and "nunca assume" in msg
    assert rel["info"]["crs"] is None
    rel2 = validar("sem_crs_respondido", p, respostas={"crs": 31983})
    assert rel2["estado"] == "aceito"
    assert rel2["info"]["crs"] == {**rel2["info"]["crs"], "epsg": 31983, "origem": "informado"}
    assert rel2["respostas"] == {"crs": 31983}
    rel3 = validar("sem_crs_resposta_invalida", p, respostas={"crs": "EPSG:999999"})
    assert rel3["estado"] == "recusado" and "CRS informado não foi reconhecido" in rel3["problemas"][0]


def test_crs_sem_epsg_wkt_custom_aceita_com_wkt2(tmp_path):
    p = tif(tmp_path / "wkt.tif", crs=WKT_CUSTOM, transformacao=TRANSFORMACAO_UTM)
    rel = validar("crs_sem_epsg", p)
    assert rel["estado"] == "aceito"
    assert rel["info"]["crs"]["epsg"] is None and rel["info"]["crs"]["rotulo"] == "WKT2 sem EPSG"
    assert rel["info"]["crs"]["wkt2"].startswith("PROJCRS[")
    assert any("CRS sem código EPSG resolvível; gravado o WKT2" in a for a in rel["avisos"])


def test_nodata_ausente_pede_e_resposta_grava(tmp_path):
    p = tif(tmp_path / "sem_nodata.tif", nodata=None)
    rel = validar("nodata_ausente", p)
    assert rel["estado"] == "pendente"
    assert [x["campo"] for x in rel["pendencias"]] == ["nodata"]
    assert rel["pendencias"][0]["mensagem"].startswith("NoData não declarado no arquivo: informe o valor")
    rel2 = validar("nodata_respondido", p, respostas={"nodata": 255})
    assert rel2["estado"] == "aceito" and rel2["info"]["nodata"] == {"valor": 255.0, "origem": "informado"}


def test_16_bits_dados_aceita_visual_pede_escala(tmp_path):
    p = tif(tmp_path / "u16.tif", dtype="uint16")
    rel = validar("16_bits_dados", p)
    assert rel["estado"] == "aceito" and rel["info"]["tipo"] == "uint16"
    rel2 = validar("16_bits_visual", p, perfil="visual")
    assert rel2["estado"] == "pendente" and rel2["pendencias"][0]["campo"] == "escala"
    assert "uint16 (16 bits): informe [mínimo, máximo]" in rel2["pendencias"][0]["mensagem"]
    rel3 = validar("16_bits_visual_escala", p, perfil="visual", respostas={"escala": [0, 4000]})
    assert rel3["estado"] == "aceito" and rel3["info"]["escala"]["maximo"] == 4000.0


def test_bandas_tipos_diferentes_vrt(tmp_path):
    a = tif(tmp_path / "a.tif", dtype="uint8", count=1)
    b = tif(tmp_path / "b.tif", dtype="uint16", count=1)
    vrt = tmp_path / "misto.vrt"
    subprocess.run(["gdalbuildvrt", "-q", "-separate", str(vrt), str(a), str(b)], check=True)
    rel = validar("tipos_diferentes_vrt", vrt)
    assert rel["estado"] == "recusado"
    assert rel["problemas"] == ["bandas com tipos de dado diferentes: uint16, uint8; "
                                "todas as bandas têm de ter o mesmo tipo"]


def test_bandas_tipos_diferentes_zip_com_dois_tif(tmp_path):
    a = tif(tmp_path / "a.tif", dtype="uint8", count=1)
    b = tif(tmp_path / "b.tif", dtype="float32", count=1)
    z = zip_com(tmp_path / "dois.zip", [a, b])
    rel = validar("tipos_diferentes_zip", z)
    assert rel["estado"] == "recusado"
    assert rel["problemas"] == ["bandas com tipos de dado diferentes: float32, uint8; "
                                "todas as bandas têm de ter o mesmo tipo"]
    assert rel["info"]["zip_entradas"] == ["a.tif", "b.tif"]


def test_zip_com_dois_tif_iguais_aceita(tmp_path):
    a = tif(tmp_path / "a.tif", count=1)
    b = tif(tmp_path / "b.tif", count=1)
    rel = validar("zip_dois_tif_ok", zip_com(tmp_path / "dois.zip", [a, b]))
    assert rel["estado"] == "aceito" and rel["info"]["bandas"] == 2


def test_zip_bomba_declarada_50x_recusa_antes_de_extrair(tmp_path):
    z = zip_bomba_declarada(tmp_path / "bomba.zip", fator=50)
    rel = validar("zip_bomba_50x", z)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("zip declara razão de compressão de 50× (limite 50×)")
    assert "suspeita de zip-bomba; nada foi descompactado" in rel["problemas"][0]
    assert not (tmp_path / "zip_extraido").exists()
    z2 = zip_bomba_declarada(tmp_path / "acima_cota.zip", fator=50)
    rel2 = validar("zip_acima_cota", z2, cota_bytes=10_000)
    assert rel2["estado"] == "recusado" and "acima da cota de 10 kB; nada foi descompactado" in rel2["problemas"][0]


def test_zip_bomba_real_de_zeros(tmp_path):
    z = tmp_path / "zeros.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.tif", b"\0" * (4 << 20))  # 4 MiB de zeros → poucos KB
    assert z.stat().st_size < 64 << 10
    rel = validar("zip_bomba_real", z)
    assert rel["estado"] == "recusado" and "suspeita de zip-bomba" in rel["problemas"][0]


def test_tif_que_e_png_renomeado(tmp_path):
    png = tmp_path / "foto.png"
    with rasterio.open(png, "w", driver="PNG", width=8, height=8, count=1, dtype="uint8") as d:
        d.write(np.zeros((1, 8, 8), "uint8"))
    p = tmp_path / "foto.tif"
    p.write_bytes(png.read_bytes())
    assert p.read_bytes()[:4] == b"\x89PNG"
    rel = validar("png_renomeado_tif", p)
    assert rel["estado"] == "recusado"
    assert rel["problemas"] == ["o conteúdo não corresponde à extensão .tif: os primeiros bytes são de PNG, "
                                "não de GeoTIFF"]
    assert rel["subprocesso"] is None  # recusado no pai, sem abrir subprocesso


def test_extensao_desconhecida(tmp_path):
    p = tmp_path / "x.bmp"
    p.write_bytes(b"BM" + b"\0" * 64)
    rel = validar("extensao_desconhecida", p)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("extensão .bmp não é um formato raster aceito")


def test_epsg_4674_e_31983_aceitos_com_crs_gravado(tmp_path):
    a = tif(tmp_path / "sirgas.tif", crs="EPSG:4674")
    b = tif(tmp_path / "utm23s.tif", crs="EPSG:31983", transformacao=TRANSFORMACAO_UTM)
    ra = validar("epsg_4674", a)
    rb = validar("epsg_31983", b)
    assert ra["estado"] == "aceito" and ra["info"]["crs"]["epsg"] == 4674 and ra["info"]["crs"]["origem"] == "arquivo"
    assert rb["estado"] == "aceito" and rb["info"]["crs"]["epsg"] == 31983
    assert -48.1 < ra["info"]["bbox4326"][0] < -47.9 and -47 < rb["info"]["bbox4326"][0] < -46
    assert ra["info"]["data_aquisicao"] == {"valor": "2026-08-01", "origem": "metadado TIFFTAG_DATETIME"}
    assert ra["info"]["nodata"] == {"valor": 0.0, "origem": "arquivo"}
    assert ra["info"]["colorinterp"] == ["red", "green", "blue"]


def test_uma_banda_visual_recusa_dados_aceita(tmp_path):
    p = tif(tmp_path / "mono.tif", count=1)
    rel = validar("1_banda_visual", p, perfil="visual")
    assert rel["estado"] == "recusado"
    assert rel["problemas"] == ["perfil visual exige pelo menos 3 bandas (RGB); o arquivo tem 1"]
    rel2 = validar("1_banda_dados", p, perfil="dados")
    assert rel2["estado"] == "aceito" and rel2["info"]["banda_unica"] is True


def test_data_aquisicao_ausente_pede_e_resposta_grava(tmp_path):
    p = tif(tmp_path / "sem_data.tif", tags={})
    rel = validar("data_ausente", p)
    assert rel["estado"] == "pendente" and rel["pendencias"][0]["campo"] == "data_aquisicao"
    rel2 = validar("data_respondida", p, respostas={"data_aquisicao": "2026-07-15"})
    assert rel2["estado"] == "aceito"
    assert rel2["info"]["data_aquisicao"] == {"valor": "2026-07-15", "origem": "informado"}


def test_extensao_fora_do_brasil_avisa(tmp_path):
    p = tif(tmp_path / "europa.tif", crs="EPSG:4326", transformacao=from_origin(2.0, 48.0, 0.001, 0.001))
    rel = validar("fora_do_brasil", p)
    assert rel["estado"] == "aceito"
    assert any(a.startswith("extensão fora do território esperado (Brasil)") for a in rel["avisos"])


# ------------------------------------------------------------------ isolamento do subprocesso
def test_bigtiff_esparso_100gb_virtual_recusado_sem_derrubar_o_pai(tmp_path):
    p = tif(tmp_path / "100gb.tif", count=1, largura=320_000, altura=320_000, tiled=True, blockxsize=4096,
            blockysize=4096, sparse_ok=True, bigtiff="YES")
    assert p.stat().st_size < 200 << 10  # KB em disco, 102 GB declarados
    rel = validar("bigtiff_esparso_100gb", p, cota_bytes=20 << 30)
    assert rel["estado"] == "recusado"
    assert rel["problemas"] == ["tamanho descompactado estimado de 95.4 GB (320000×320000×1 bandas uint8) acima da "
                                "cota de 20.0 GB; nada foi lido"]
    assert rel["subprocesso"]["codigo_saida"] == 0 and rel["subprocesso"]["morte"] is None
    assert rel["subprocesso"]["rlimit_as_mb"] == v.RLIMIT_AS_MB == 768
    assert rel["subprocesso"]["timeout_s"] == v.TIMEOUT_S
    assert os.getpid()  # o processo pai (este) continua vivo e responde


def test_tiff_fabricado_dimensoes_enormes(tmp_path):
    p = tiff_fabricado(tmp_path / "gigante.tif", largura=400_000, altura=400_000)
    assert p.stat().st_size < 1024
    rel = validar("tiff_fabricado_160gb", p)
    assert rel["estado"] == "recusado" and rel["problemas"][0].startswith("tamanho descompactado estimado de 149.0 GB")


def test_estouro_de_memoria_no_filho_nao_derruba_o_pai(tmp_path):
    p = tif(tmp_path / "ok.tif")
    rel = validar("prova_memoria_2gb", p, _prova="memoria")
    assert rel["estado"] == "recusado" and rel["subprocesso"]["morte"] == "memoria"
    assert rel["problemas"][0].startswith("a validação excedeu a memória do subprocesso (768 MB)")
    assert rel["subprocesso"]["ram_pico_kb"] < 768 * 1024


def test_tempo_esgotado_mata_o_filho(tmp_path):
    p = tif(tmp_path / "ok.tif")
    rel = validar("prova_timeout_2s", p, _prova="tempo", timeout_s=2)
    assert rel["estado"] == "recusado" and rel["subprocesso"]["morte"] == "timeout"
    assert rel["problemas"][0].startswith("a validação passou de 2 s e foi interrompida")
    assert rel["subprocesso"]["codigo_saida"] == -9 and rel["subprocesso"]["tempo_s"] < 4


def test_caminho_vsi_e_vrt_remoto_recusados(tmp_path):
    rel = v.validar("/vsicurl/https://exemplo.invalido/x.tif")
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("caminho virtual do GDAL (/vsi…) não é aceito")
    vrt = tmp_path / "remoto.vrt"
    vrt.write_text('<VRTDataset rasterXSize="8" rasterYSize="8"><VRTRasterBand dataType="Byte" band="1">'
                   '<SimpleSource><SourceFilename relativeToVRT="0">/vsicurl/https://exemplo.invalido/x.tif'
                   '</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>')
    rel = validar("vrt_remoto", vrt)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("VRT com fonte fora do diretório do envio ou remota")
    cru = tmp_path / "cru.vrt"
    cru.write_text('<VRTDataset rasterXSize="8" rasterYSize="8"><VRTRawRasterBand dataType="Byte" band="1">'
                   '<SourceFilename relativeToVRT="0">/etc/passwd</SourceFilename></VRTRawRasterBand></VRTDataset>')
    rel = validar("vrt_raw", cru)
    assert rel["problemas"] == ["VRT com VRTRawRasterBand (leitura crua de arquivo arbitrário) não é aceito"]


def test_ambiente_do_filho_sem_readdir_e_sem_curl():
    assert v.AMBIENTE_FILHO["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"
    assert v.AMBIENTE_FILHO["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"].startswith(".nenhuma")
    assert v.RLIMIT_AS_MB <= 1024


# ------------------------------------------------------------------ os 3 casos do adversário
def test_adversario_tiff_com_ifd_circular(tmp_path):
    p = tiff_fabricado(tmp_path / "circular.tif", largura=8, altura=8, proximo_ifd=8)
    rel = validar("ifd_circular", p)
    assert rel["estado"] in ("recusado", "pendente")  # nunca aceito em silêncio, nunca travado
    assert rel["subprocesso"]["morte"] is None and rel["subprocesso"]["tempo_s"] < 10
    if rel["estado"] == "pendente":  # o GDAL corta o laço e vê um TIFF de 8×8 sem CRS/NoData/data: pede, não assume
        assert {x["campo"] for x in rel["pendencias"]} >= {"crs"}


def test_adversario_jp2_truncado(tmp_path):
    inteiro = tmp_path / "inteiro.jp2"
    with rasterio.open(inteiro, "w", driver="JP2OpenJPEG", width=256, height=256, count=1, dtype="uint8",
                       crs="EPSG:4674", transform=TRANSFORMACAO_BR, QUALITY="25", REVERSIBLE="NO") as d:
        d.write((np.random.default_rng(1).random((1, 256, 256)) * 255).astype("uint8"))
    dados = inteiro.read_bytes()
    truncado = tmp_path / "truncado.jp2"
    truncado.write_bytes(dados[: len(dados) // 2])
    rel = validar("jp2_truncado", truncado)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith(
        ("os dados de truncado.jp2 não puderam ser lidos (arquivo truncado ou corrompido)",
         "o GDAL não abriu truncado.jp2"))
    assert rel["subprocesso"]["morte"] is None


def test_adversario_geotiff_65535_bandas(tmp_path):
    p = tiff_fabricado(tmp_path / "bandas.tif", largura=64, altura=64, bandas=65_535)
    rel = validar("65535_bandas", p)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith(("65535 bandas; o máximo aceito é 512", "o GDAL não abriu bandas.tif"))
    assert rel["subprocesso"]["morte"] is None and rel["subprocesso"]["ram_pico_kb"] < 768 * 1024


# ------------------------------------------------------------------ conserto do turno 3 (laudo do adversário)
def test_vrt_aninhado_so_e_aceito_dentro_do_envio(tmp_path):
    """ACHADO 1/3: a conferência de fonte agora é RECURSIVA e resolve com realpath. VRT → VRT dentro do envio
    passa; a mesma cadeia apontando para fora, ou por ligação simbólica, é recusada."""
    envio, fora = tmp_path / "envio", tmp_path / "fora"
    envio.mkdir()
    fora.mkdir()
    tif(envio / "bom.tif", count=1)
    tif(fora / "segredo.tif", count=1)
    (envio / "b.vrt").write_text(_vrt_texto("bom.tif", relativo="1"))
    rel = validar("vrt_aninhado_dentro", _envolver(envio / "a.vrt", "b.vrt"),
                  respostas={"data_aquisicao": "2026-08-01"})
    assert rel["estado"] == "aceito", rel["problemas"]
    (envio / "b.vrt").write_text(_vrt_texto(str(fora / "segredo.tif"), relativo="0"))
    rel = validar("vrt_aninhado_fora", envio / "a.vrt")
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("VRT com fonte fora do diretório do envio ou remota")
    (envio / "link.tif").symlink_to(fora / "segredo.tif")
    (envio / "b.vrt").write_text(_vrt_texto("link.tif", relativo="1"))
    rel = validar("vrt_fonte_symlink", envio / "a.vrt")
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("VRT com fonte fora do diretório do envio ou remota")


def test_vrt_circular_e_profundo_demais_recusados(tmp_path):
    envio = tmp_path / "envio"
    envio.mkdir()
    tif(envio / "bom.tif", count=1)
    (envio / "a.vrt").write_text(_vrt_texto("b.vrt"))
    (envio / "b.vrt").write_text(_vrt_texto("a.vrt"))
    rel = validar("vrt_circular", envio / "a.vrt")
    assert rel["estado"] == "recusado" and "referência circular" in rel["problemas"][0]
    for i in range(9):
        (envio / f"n{i}.vrt").write_text(_vrt_texto(f"n{i + 1}.vrt"))
    (envio / "n9.vrt").write_text(_vrt_texto("bom.tif"))
    rel = validar("vrt_profundo", envio / "n0.vrt")
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith(f"VRT aninhado além de {v.VRT_PROFUNDIDADE_MAX} níveis")


def test_vrt_com_xml_acima_do_teto_recusado(tmp_path):
    """ACHADO 2: o XML é lido INTEIRO (o corte de 1 MiB escondia a segunda banda); acima do teto, recusa."""
    envio = tmp_path / "envio"
    envio.mkdir()
    tif(envio / "bom.tif", count=1)
    gordo = envio / "gordo.vrt"
    gordo.write_text(_vrt_texto("bom.tif").replace("</VRTDataset>",
                                                   f"<!--{'A' * (v.VRT_XML_MAX + 1024)}--></VRTDataset>"))
    rel = validar("vrt_xml_gordo", gordo)
    assert rel["estado"] == "recusado"
    assert rel["problemas"][0].startswith("o XML do VRT 'gordo.vrt' tem") and "máximo aceito é 16.0 MB" \
        in rel["problemas"][0]


def test_rede_fechada_no_processo_e_medida_no_proc_do_filho(tmp_path):
    """ACHADO 4: o filho recebe filtro seccomp; `Seccomp: 2` é lido no /proc dele PRÓPRIO e vai ao relatório."""
    rel = validar("isolamento_rede", tif(tmp_path / "ok.tif", count=1))
    isolamento = rel["info"]["isolamento"]
    assert isolamento["seccomp"] == 2 and isolamento["no_new_privs"] == 1
    assert isolamento["rede"].startswith("bloqueada no processo (seccomp")


def test_nodata_nan_grava_no_jsonb_do_banco(tmp_path, conexao_plat_app):
    """ACHADO 5: float32 com NoData NaN. O relatório sai com o texto 'NaN' declarado e ATRAVESSA o jsonb —
    é este o caminho que o `raster.validar` usa (psycopg2.extras.Json em coluna jsonb)."""
    import psycopg2.extras
    p = tif(tmp_path / "nan.tif", dtype="float32", nodata=float("nan"), count=1)
    rel = validar("nodata_nan", p)
    assert rel["estado"] == "aceito"
    assert rel["info"]["nodata"] == {"valor": "NaN", "origem": "arquivo"}
    json.dumps(rel, allow_nan=False)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT %s::jsonb AS r", (psycopg2.extras.Json({"validacao": rel}),))
        gravado = cur.fetchone()["r"]
    assert gravado["validacao"]["info"]["nodata"]["valor"] == "NaN"


def test_zip_com_volume_desproporcional_ao_envio_recusado(tmp_path):
    """ACHADO 7: teto de VOLUME ligado ao tamanho do envio, além da razão de 50× e da cota."""
    z = tmp_path / "grande.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.tif", b"\0" * (37 << 20) + os.urandom(3 << 20))
    with zipfile.ZipFile(z) as zf:
        infos = zf.infolist()
    assert sum(i.file_size for i in infos) / sum(i.compress_size for i in infos) < v.ZIP_RAZAO_MAX
    rel = validar("zip_volume_desproporcional", z, dir_trabalho=tmp_path / "trabalho")
    assert rel["estado"] == "recusado"
    assert "acima do teto de" in rel["problemas"][0] and "8× o enviado" in rel["problemas"][0]
    assert not (tmp_path / "trabalho" / "zip_extraido").exists()


def test_tipo_sem_conversao_e_declarado_no_relatorio(tmp_path):
    """Fronteira apontada pelo adversário: complex64/int64 passam na VALIDAÇÃO (o arquivo está íntegro), mas o
    relatório declara `tipo_convertivel: false` — a recusa é da conversão, não daqui (ADR 0015 seção 9)."""
    p = tif(tmp_path / "complexo.tif", dtype="complex64", count=1)
    rel = validar("tipo_complex64", p)
    assert rel["estado"] == "aceito" and rel["info"]["tipo_convertivel"] is False
    ok = validar("tipo_uint8", tif(tmp_path / "normal.tif", count=1))
    assert ok["info"]["tipo_convertivel"] is True


def _vrt_texto(fonte: str, relativo: str = "1") -> str:
    return ('<VRTDataset rasterXSize="32" rasterYSize="32">'
            '<SRS>EPSG:4674</SRS><GeoTransform>-48.0, 0.001, 0.0, -15.0, 0.0, -0.001</GeoTransform>'
            '<VRTRasterBand dataType="Byte" band="1"><NoDataValue>0</NoDataValue><SimpleSource>'
            f'<SourceFilename relativeToVRT="{relativo}">{fonte}</SourceFilename><SourceBand>1</SourceBand>'
            '<SrcRect xOff="0" yOff="0" xSize="32" ySize="32"/><DstRect xOff="0" yOff="0" xSize="32" ySize="32"/>'
            '</SimpleSource></VRTRasterBand></VRTDataset>')


def _envolver(caminho: Path, fonte: str) -> Path:
    caminho.write_text(_vrt_texto(fonte))
    return caminho


# ------------------------------------------------------------------ registro do tipo de job
def test_tipo_de_job_registrado(monkeypatch):
    from app import settings as cfg
    for k, val in {"PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat", "PLAT_SECRET": "ab" * 32,
                   "PLAT_AMBIENTE": "dev", "PLAT_URL_PUBLICA": "https://exemplo.invalido",
                   "PLAT_WORKER_MEMORIA_MB": "2048"}.items():
        monkeypatch.setenv(k, val)
    cfg.obter.cache_clear()
    from app.jobs.registro import REGISTRO, validar_parametros
    from app.raster import tarefas  # noqa: F401
    t = REGISTRO["raster.validar"]
    assert t.memoria_mb >= v.RLIMIT_AS_MB and t.tentativas == 1 and t.perfil_minimo == "editor"
    p = validar_parametros(t, {"arquivo_chave": "sig-teste/objeto/abc.tif", "respostas": {"crs": 4674}})
    assert p["perfil"] == "dados" and p["respostas"]["crs"] == 4674
    with pytest.raises(Exception, match="perfil|literal"):
        validar_parametros(t, {"arquivo_chave": "x.tif", "perfil": "cinema"})
    cfg.obter.cache_clear()
