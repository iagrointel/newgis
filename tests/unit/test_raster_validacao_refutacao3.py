"""Refutação do 2º adversário do item L1-01-b, escrita ANTES do conserto (achados H1 e H2).

H1: `_conferir_vrt` casava só `<SourceFilename>` por expressão regular. Um `VRTWarpedDataset` põe a fonte em
`<SourceDataset>`, que passava direto: um VRT enviado lia arquivo LOCAL fora do diretório do envio, com o
filtro de chamadas de sistema ligado. A isca `<SourceFilename>` dentro de um comentário XML fazia a
conferência antiga achar que havia fonte legítima.

H2: o ambiente do filho era `{**os.environ, **AMBIENTE_FILHO}` menos `PLAT_DSN`/`PLAT_SECRET`. Toda outra
variável do worker (`PLAT_DSN_WORKER`, `PLAT_GARAGE_ADMIN_TOKEN`, …) chegava ao processo que abre o arquivo
hostil. Como o filtro deixa `AF_UNIX` passar, a credencial bastava para falar com o Postgres local.

Sem banco: `venv/bin/pytest tests/unit/test_raster_validacao_refutacao3.py -q`.
"""
from __future__ import annotations

import http.server
import threading
import time

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.raster import validacao as V

RESP = {"data_aquisicao": "2026-01-02"}


def _tif(caminho, valor=1, largura=64, altura=64, bandas=1, dtype="uint8"):
    with rasterio.open(caminho, "w", driver="GTiff", width=largura, height=altura, count=bandas,
                       dtype=dtype, crs="EPSG:4674",
                       transform=from_origin(-47.0, -15.0, 0.001, 0.001)) as d:
        for b in range(1, bandas + 1):
            d.write(np.full((altura, largura), valor, dtype), b)


class _Ouvinte:
    """Servidor HTTP local que só anota o que recebe."""

    def __init__(self):
        self.pedidos: list[str] = []
        pai = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                pai.pedidos.append(self.requestline)
                self.send_error(404)

            do_HEAD = do_GET

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def parar(self):
        self.srv.shutdown()


_VRT_WARPED = '''<VRTDataset rasterXSize="64" rasterYSize="64" subClass="VRTWarpedDataset">
  <SRS>EPSG:4326</SRS>
  <GeoTransform>-47.0, 0.001, 0.0, -15.0, 0.0, -0.001</GeoTransform>
  __ISCA__
  <VRTRasterBand dataType="Byte" band="1" subClass="VRTWarpedRasterBand"><ColorInterp>Gray</ColorInterp></VRTRasterBand>
  <BlockXSize>64</BlockXSize>
  <BlockYSize>64</BlockYSize>
  <GDALWarpOptions>
    <WarpMemoryLimit>6.71089e+07</WarpMemoryLimit>
    <ResampleAlg>NearestNeighbour</ResampleAlg>
    <WorkingDataType>Byte</WorkingDataType>
    <Option name="INIT_DEST">0</Option>
    <SourceDataset relativeToVRT="__REL__">__FONTE__</SourceDataset>
    <Transformer><ApproxTransformer><MaxError>0.125</MaxError><BaseTransformer><GenImgProjTransformer>
      <SrcGeoTransform>-47,0.001,0,-15,0,-0.001</SrcGeoTransform>
      <SrcInvGeoTransform>47000,1000,0,-15000,0,-1000</SrcInvGeoTransform>
      <DstGeoTransform>-47,0.001,0,-15,0,-0.001</DstGeoTransform>
      <DstInvGeoTransform>47000,1000,0,-15000,0,-1000</DstInvGeoTransform>
    </GenImgProjTransformer></BaseTransformer></ApproxTransformer></Transformer>
    <BandList><BandMapping src="1" dst="1" /></BandList>
  </GDALWarpOptions>
</VRTDataset>'''

_ISCA = '<!-- <SourceFilename relativeToVRT="1">bom.tif</SourceFilename> -->'


def _warped(fonte: str, rel: str = "0", isca: str = _ISCA) -> str:
    return _VRT_WARPED.replace("__ISCA__", isca).replace("__REL__", rel).replace("__FONTE__", str(fonte))


@pytest.fixture()
def envio(tmp_path):
    d = tmp_path / "envio"
    d.mkdir()
    _tif(d / "bom.tif", 1)
    fora = tmp_path / "fora"
    fora.mkdir()
    _tif(fora / "segredo.tif", 222)
    return d


def _recusa(caminho) -> dict:
    r = V.validar(caminho, respostas=RESP)
    assert r["estado"] == "recusado", f"aceito indevidamente: {r['estado']} info={r['info'].get('arquivos')}"
    return r


# ============================================================= H1 — toda referência de dado no XML é conferida
def test_sourcedataset_absoluto_fora_do_envio_e_recusado(envio):
    """O ataque exato do adversário: VRTWarpedDataset com a fonte em <SourceDataset> apontando para fora."""
    alvo = envio.parent / "fora" / "segredo.tif"
    (envio / "w.vrt").write_text(_warped(str(alvo), rel="0"))
    r = _recusa(envio / "w.vrt")
    assert r["problemas"][0].startswith("VRT com fonte fora do diretório do envio ou remota")


def test_sourcedataset_relativo_que_sai_do_envio_e_recusado(envio):
    (envio / "w.vrt").write_text(_warped("../fora/segredo.tif", rel="1"))
    _recusa(envio / "w.vrt")


def test_sourcedataset_com_vsicurl_e_recusado_sem_bater_na_rede(envio):
    """A recusa é do XML, não do filtro de chamadas de sistema: nenhum pedido chega ao servidor local."""
    ouvinte = _Ouvinte()
    try:
        url = f"/vsicurl/http://127.0.0.1:{ouvinte.porta}/x.nenhuma-extensao-permitida"
        (envio / "w.vrt").write_text(_warped(url))
        r = _recusa(envio / "w.vrt")
        time.sleep(0.5)
        assert ouvinte.pedidos == [], f"a validação bateu na rede: {ouvinte.pedidos}"
        assert r["problemas"][0].startswith("VRT com fonte fora do diretório do envio ou remota")
    finally:
        ouvinte.parar()


def test_sourcedataset_com_vsizip_de_fora_e_recusado(envio):
    alvo = envio.parent / "fora" / "pacote.zip"
    alvo.write_bytes(b"PK\x03\x04" + b"\0" * 32)
    (envio / "w.vrt").write_text(_warped(f"/vsizip/{alvo}/dentro.tif"))
    _recusa(envio / "w.vrt")


def test_sourcefilename_absoluto_com_relativetovrt_zero_e_recusado(envio):
    alvo = envio.parent / "fora" / "segredo.tif"
    (envio / "s.vrt").write_text(
        f'<VRTDataset rasterXSize="64" rasterYSize="64"><VRTRasterBand dataType="Byte" band="1">'
        f'<SimpleSource><SourceFilename relativeToVRT="0">{alvo}</SourceFilename>'
        f'</SimpleSource></VRTRasterBand></VRTDataset>')
    _recusa(envio / "s.vrt")


def test_caminho_de_fora_escondido_em_atributo_e_recusado(envio):
    """Qualquer nó do XML que referencie dado conta, inclusive atributo."""
    alvo = envio.parent / "fora" / "segredo.tif"
    (envio / "a.vrt").write_text(
        f'<VRTDataset rasterXSize="64" rasterYSize="64"><VRTRasterBand dataType="Byte" band="1">'
        f'<SimpleSource><SourceFilename relativeToVRT="1">bom.tif</SourceFilename>'
        f'<SrcRect xOff="0" yOff="0" xSize="64" ySize="64" arquivo="{alvo}"/>'
        f'</SimpleSource></VRTRasterBand></VRTDataset>')
    _recusa(envio / "a.vrt")


def test_vrt_sem_referencia_nenhuma_e_recusado(envio):
    """A isca em comentário não é referência: o XML fica sem fonte e é recusado."""
    (envio / "vazio.vrt").write_text(
        f'<VRTDataset rasterXSize="64" rasterYSize="64">{_ISCA}'
        f'<VRTRasterBand dataType="Byte" band="1"><ColorInterp>Gray</ColorInterp></VRTRasterBand></VRTDataset>')
    _recusa(envio / "vazio.vrt")


def test_vrt_warped_legitimo_dentro_do_envio_nao_e_recusado(envio):
    """O conserto não pode matar o caso legítimo: fonte dentro do envio segue passando."""
    (envio / "ok.vrt").write_text(_warped("bom.tif", rel="1", isca=""))
    r = V.validar(envio / "ok.vrt", respostas=RESP)
    assert r["estado"] != "recusado", (r["estado"], r["problemas"][:2])


# ============================================================= H2 — o filho não recebe segredo nenhum
def test_ambiente_do_filho_nao_leva_segredo_do_worker(monkeypatch):
    monkeypatch.setenv("PLAT_DSN_WORKER", "postgresql://plat_worker:SENHA@127.0.0.1/iagro_sat")
    monkeypatch.setenv("PLAT_GARAGE_ADMIN_TOKEN", "token-admin-garage")
    monkeypatch.setenv("PLAT_DSN", "dbname=nao_devia_chegar")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "chave")
    ambiente = V.ambiente_do_filho()
    proibidas = [k for k in ambiente if k.startswith(("PLAT_", "AWS_", "PG"))]
    assert proibidas == [], f"o filho recebe variável do worker: {proibidas}"
    assert ambiente["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"
    assert "PATH" in ambiente


def test_processo_filho_vivo_nao_tem_segredo_no_ambiente(tmp_path, monkeypatch):
    """Medido no próprio filho, não no dicionário do pai."""
    monkeypatch.setenv("PLAT_DSN_WORKER", "postgresql://plat_worker:SENHA@127.0.0.1/iagro_sat")
    monkeypatch.setenv("PLAT_GARAGE_ADMIN_TOKEN", "token-admin-garage")
    alvo = tmp_path / "x.tif"
    _tif(alvo)
    r = V.validar(alvo, respostas=RESP, _prova="ambiente")
    chaves = r["info"]["ambiente_chaves"]
    assert [k for k in chaves if k.startswith("PLAT_")] == [], chaves
