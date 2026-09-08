"""Cliente OGC de terceiros contra o WMS/WMTS desta plataforma (item L2-04-i).

O portão pede "QGIS carrega WMS e WMTS da demo e desenha". **QGIS não está instalado nesta máquina**
(medido em `test_conformidade_clientes.py`, item L2-04-j, e conferido aqui), e instalar não cabe no
orçamento de disco da trilha. O substituto é o cliente OGC que ESTÁ aqui e que o próprio QGIS carrega
por baixo em vários caminhos: os drivers **WMS e WMTS do GDAL** (`gdalinfo`/`gdal_translate`). Eles leem
o `GetCapabilities`, montam a lista de camadas, calculam a caixa e o sistema de coordenadas e BAIXAM a
imagem — se a nossa saída não fosse WMS 1.3.0 / WMTS 1.0.0 de verdade, o driver falharia na leitura.

O servidor é um uvicorn PRÓPRIO da trilha (porta 8567), morto pelo PID no fim; a autenticação é um
token de serviço na querystring, que é como QGIS/Pro consomem uma URL protegida.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_diretorio_esri import Camada, _sufixo

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 8567
BASE = f"http://127.0.0.1:{PORTA}"
ITEM = "L2-04-i-wms-wmts-sld"


def _porta_ocupada(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", porta)) == 0


@pytest.fixture(scope="module")
def servidor(env):
    if _porta_ocupada(PORTA):
        pytest.skip(f"porta {PORTA} ocupada nesta máquina")
    proc = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
         "--port", str(PORTA), "--log-level", "warning"],
        cwd=str(RAIZ), env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(120):
            if proc.poll() is not None:
                erro = proc.stderr.read().decode("utf-8", "replace")[-800:] if proc.stderr else ""
                pytest.fail(f"uvicorn da trilha morreu ao subir: {erro}")
            try:
                requests.get(f"{BASE}/api/openapi.json", timeout=1)
                break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            pytest.fail(f"uvicorn não respondeu em {BASE} em 60 s")
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def camada_e_token(env, sessao_a):
    camada = Camada(env, sessao_a, f"{PREFIXO_TESTE} camada wms {_sufixo()}")
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-wms-{_sufixo()}",
                                           "escopos": ["catalogo:ler", "camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield camada, tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")
    camada.apagar()


def _gdal(programa: str) -> str:
    caminho = shutil.which(programa)
    if not caminho:
        pytest.skip(f"{programa} não está instalado nesta máquina")
    return caminho


def _rodar(args, timeout=120):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def test_gdal_le_o_getcapabilities_do_wms_e_acha_a_camada(servidor, camada_e_token, medida):
    """Driver WMS do GDAL: lê as capacidades e lista a camada como subdataset."""
    gdalinfo = _gdal("gdalinfo")
    camada, token = camada_e_token
    url = f"{servidor}/wms/{camada.item_id}?service=WMS&version=1.3.0&request=GetCapabilities&token={token}"
    t0 = time.perf_counter()
    rc, saida, erro = _rodar([gdalinfo, f"WMS:{url}"])
    ms = (time.perf_counter() - t0) * 1000
    assert rc == 0, f"gdalinfo falhou: {erro[-600:]}"
    assert "SUBDATASET" in saida.upper(), saida[:800]
    assert camada.item_id in saida, saida[:800]
    medida(ITEM)("cliente_gdal_getcapabilities_wms_ms", round(ms, 1), "ms",
                 "gdalinfo WMS:<GetCapabilities> lendo as capacidades do serviço vivo desta trilha")


def test_gdal_baixa_uma_imagem_do_getmap(servidor, camada_e_token, tmp_path, medida):
    """Driver WMS do GDAL montando o pedido sozinho e escrevendo um GeoTIFF — o mesmo caminho do QGIS."""
    gdal_translate = _gdal("gdal_translate")
    gdalinfo = _gdal("gdalinfo")
    camada, token = camada_e_token
    xml = tmp_path / "servico.xml"
    xml.write_text(f"""<GDAL_WMS>
  <Service name="WMS">
    <Version>1.3.0</Version>
    <ServerUrl>{servidor}/wms/{camada.item_id}?token={token}&amp;</ServerUrl>
    <CRS>EPSG:3857</CRS>
    <ImageFormat>image/png</ImageFormat>
    <Layers>{camada.item_id}</Layers>
    <Styles></Styles>
    <Transparent>TRUE</Transparent>
  </Service>
  <DataWindow>
    <UpperLeftX>-5600000</UpperLeftX><UpperLeftY>-2400000</UpperLeftY>
    <LowerRightX>-5000000</LowerRightX><LowerRightY>-2900000</LowerRightY>
    <SizeX>512</SizeX><SizeY>512</SizeY>
  </DataWindow>
  <BandsCount>4</BandsCount>
  <Cache/>
</GDAL_WMS>""", encoding="utf-8")
    rc, saida, erro = _rodar([gdalinfo, str(xml)])
    assert rc == 0, f"gdalinfo do serviço WMS falhou: {erro[-600:]}"
    assert "Size is 512, 512" in saida, saida[:600]
    destino = tmp_path / "mapa.tif"
    t0 = time.perf_counter()
    rc, _s, erro = _rodar([gdal_translate, "-of", "GTiff", "-outsize", "256", "256", str(xml), str(destino)])
    ms = (time.perf_counter() - t0) * 1000
    assert rc == 0, f"gdal_translate falhou: {erro[-800:]}"
    assert destino.exists() and destino.stat().st_size > 1000
    medida(ITEM)("cliente_gdal_getmap_ms", round(ms, 1), "ms",
                 "gdal_translate baixando 256x256 do GetMap por um XML GDAL_WMS (driver WMS do GDAL)")


def test_gdal_le_o_wmts_e_baixa_um_tile(servidor, camada_e_token, tmp_path, medida):
    """Driver WMTS do GDAL lendo as capacidades, e o tile baixado do endereço RESTful.

    ACHADO desta trilha (o mesmo que o item L2-04-j registrou para o WFS): depois de LER as capacidades,
    o driver WMTS busca os tiles no endereço que o próprio documento publica (`ResourceURL`), e nós
    publicamos ali `PLAT_URL_PUBLICA` — que em produção é o domínio do inquilino e nesta trilha é um
    domínio que não resolve (`trilha-*.invalido`). Por isso o download do tile é provado apontando o
    driver de ladrilho do GDAL direto para o MESMO endereço RESTful que as capacidades descrevem: o que
    fica sem prova aqui é a resolução do domínio publicado, que é configuração de implantação."""
    gdalinfo = _gdal("gdalinfo")
    gdal_translate = _gdal("gdal_translate")
    camada, token = camada_e_token
    url = (f"{servidor}/wmts/{camada.item_id}?service=WMTS&version=1.0.0&request=GetCapabilities"
           f"&token={token}")
    rc, saida, erro = _rodar([gdalinfo, f"WMTS:{url}"])
    assert rc == 0, f"gdalinfo WMTS falhou: {erro[-800:]}"
    # o driver abre a camada direto (só existe uma neste serviço): confere o driver e a grade deduzida
    assert "Driver: WMTS" in saida, saida[:400]
    assert "Pseudo-Mercator" in saida or "3857" in saida, saida[:800]
    modelo = (f"{servidor}/wmts/{camada.item_id}/rest/{camada.item_id}/padrao/GoogleMapsCompatible/"
              "${z}/${y}/${x}.png?token=" + token)
    xml = tmp_path / "wmts_tms.xml"
    xml.write_text(f"""<GDAL_WMS>
  <Service name="TMS"><ServerUrl>{modelo}</ServerUrl></Service>
  <DataWindow>
    <UpperLeftX>-20037508.34</UpperLeftX><UpperLeftY>20037508.34</UpperLeftY>
    <LowerRightX>20037508.34</LowerRightX><LowerRightY>-20037508.34</LowerRightY>
    <TileLevel>8</TileLevel><TileCountX>1</TileCountX><TileCountY>1</TileCountY>
    <YOrigin>top</YOrigin>
  </DataWindow>
  <Projection>EPSG:3857</Projection>
  <BlockSizeX>256</BlockSizeX><BlockSizeY>256</BlockSizeY>
  <BandsCount>4</BandsCount>
  <Cache/>
</GDAL_WMS>""", encoding="utf-8")
    destino = tmp_path / "tile.tif"
    t0 = time.perf_counter()
    rc, _s, erro = _rodar([gdal_translate, "-of", "GTiff", "-srcwin", "0", "0", "512", "512",
                           "-outsize", "256", "256", str(xml), str(destino)])
    ms = (time.perf_counter() - t0) * 1000
    assert rc == 0, f"gdal_translate do ladrilho WMTS falhou: {erro[-800:]}"
    assert destino.exists() and destino.stat().st_size > 1000
    medida(ITEM)("cliente_gdal_wmts_tile_ms", round(ms, 1), "ms",
                 "gdal_translate baixando ladrilhos do endereço RESTful do WMTS (driver de ladrilho do GDAL)")


def test_qgis_ausente_e_medido_nao_presumido(medida):
    """A cláusula do portão nomeia o QGIS; ele não está nesta máquina. Fica registrado com evidência."""
    achados = {p: shutil.which(p) for p in ("qgis", "qgis_process", "qgis-bin")}
    assert not any(achados.values()), f"QGIS apareceu: {achados} — refaça a cláusula com ele"
    medida(ITEM)("cliente_qgis", 0, "presente",
                 "which qgis/qgis_process/qgis-bin: nenhum encontrado nesta máquina; a cláusula do portão "
                 "foi cumprida com os drivers WMS/WMTS do GDAL (mesma pilha OGC), e o QGIS fica pendente")
