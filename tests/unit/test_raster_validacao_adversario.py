"""Ataque independente ao item L1-01-b (validação e isolamento da entrada raster). Escrito pelo ADVERSÁRIO, que
não participou da construção: nenhum caso aqui reaproveita arquivo, função auxiliar ou afirmação do
tests/unit/test_raster_validacao.py — todos os arquivos são fabricados de novo em tmp_path.

Leitura do resultado:
* teste comum que passa = a defesa segurou o ataque;
* teste marcado `xfail(strict=True)` = o teste afirma o que o ITEM PROMETE e a promessa NÃO se cumpre hoje.
  Cada um desses é um achado, com a explicação na razão do marcador. Quando o buraco for tapado, o `strict`
  transforma o xpass em falha e o marcador tem de sair — é assim que o achado não se perde.

ESTADO EM 06/09/2026 (turno 3): os 9 achados foram consertados no ramo `wt/valida` (ADR 0015, seção "conserto
do turno 3"). Os 9 marcadores `xfail(strict=True)` saíram, e o texto de cada achado ficou como comentário em
cima do teste correspondente. Nenhum caso foi apagado, afrouxado ou reescrito: os 23 testes deste arquivo são
os mesmos do commit b62d88a e agora todos passam.

Sem banco, sem worker, sem rede externa (o único socket é um ouvinte em 127.0.0.1 criado pelo próprio teste
para medir se a validação sai à rede)."""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.raster import validacao as v

TRANSFORMACAO = from_origin(-47.0, -15.0, 0.001, 0.001)
RESPOSTA_DATA = {"data_aquisicao": "2026-01-02"}


# ------------------------------------------------------------------ utilidades do adversário
def tif(caminho: Path, *, valor: int = 1, crs="EPSG:4674", lado: int = 8, transformacao=TRANSFORMACAO,
        nodata=0, dtype="uint8", **opcoes) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(caminho, "w", driver="GTiff", width=lado, height=lado, count=1, dtype=dtype,
                       crs=crs, transform=transformacao, nodata=nodata, **opcoes) as d:
        d.write(np.full((lado, lado), valor, dtype), 1)
        d.update_tags(TIFFTAG_DATETIME="2026:01:02 00:00:00")
    return caminho


def vrt(caminho: Path, fonte: str, *, relativo: str = "1", lado: int = 8, miolo: str = "", com_srs: bool = True,
        banda_extra: str = "") -> Path:
    srs = ('<SRS>EPSG:4674</SRS>\n<GeoTransform>-47.0, 0.001, 0.0, -15.0, 0.0, -0.001</GeoTransform>'
           if com_srs else "")
    caminho.write_text(
        f'<VRTDataset rasterXSize="{lado}" rasterYSize="{lado}">\n{srs}\n'
        f'<VRTRasterBand dataType="Byte" band="1"><NoDataValue>0</NoDataValue><SimpleSource>\n'
        f'<SourceFilename relativeToVRT="{relativo}">{fonte}</SourceFilename><SourceBand>1</SourceBand>\n'
        f'<SrcRect xOff="0" yOff="0" xSize="{lado}" ySize="{lado}"/>'
        f'<DstRect xOff="0" yOff="0" xSize="{lado}" ySize="{lado}"/>\n'
        f'</SimpleSource></VRTRasterBand>\n{miolo}{banda_extra}</VRTDataset>', "utf-8")
    return caminho


def tiff_a_mao(caminho: Path, entradas: list[tuple[int, int, int, int]], *, proximo: int = 0,
               rabo: int = 64) -> Path:
    """TIFF clássico little-endian escrito byte a byte: o adversário controla cada tag."""
    entradas = sorted(entradas)
    corpo = struct.pack("<H", len(entradas))
    inicio_dados = 8 + 2 + len(entradas) * 12 + 4
    for tag, tipo, n, valor in entradas:
        valor = inicio_dados if tag == 273 else valor
        corpo += (struct.pack("<HHI2H", tag, tipo, n, valor, 0) if tipo == 3
                  else struct.pack("<HHII", tag, tipo, n, valor))
    corpo += struct.pack("<I", proximo)
    caminho.write_bytes(b"II*\x00" + struct.pack("<I", 8) + corpo + b"\x00" * rabo)
    return caminho


def bytes_no_diretorio(raiz: Path) -> int:
    return sum(p.stat().st_size for p in raiz.rglob("*") if p.is_file())


# =========================================================== ATAQUE 1 — fuga do isolamento
# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 1: a conferência de fonte do VRT só olha o VRT ENVIADO. Um VRT que aponta para outro VRT local passa, e o
# segundo aponta para caminho absoluto fora do envio: o GDAL lê o arquivo de fora DENTRO da validação.
def test_vrt_aninhado_nao_deve_ler_arquivo_fora_do_envio(tmp_path: Path) -> None:
    envio, fora = tmp_path / "envio", tmp_path / "fora"
    tif(envio / "bom.tif", valor=1)
    segredo = tif(fora / "segredo.tif", valor=222)
    vrt(envio / "b.vrt", str(segredo), relativo="0", com_srs=False)
    alvo = vrt(envio / "a.vrt", "b.vrt")
    relatorio = v.validar(alvo, respostas=RESPOSTA_DATA)
    with rasterio.open(alvo) as d:
        pixel = int(d.read(1)[0, 0])
    assert pixel == 222, "o GDAL leu mesmo o arquivo de fora do envio"
    assert relatorio["estado"] == "recusado", relatorio["estado"]


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 2: _conferir_vrt lê só os primeiros 1 MiB do XML. Com 1 MiB de comentário antes dela, a segunda banda aponta
# para caminho absoluto fora do envio e o arquivo é ACEITO.
def test_vrt_com_fonte_depois_de_1mib_de_texto_nao_deve_passar(tmp_path: Path) -> None:
    envio, fora = tmp_path / "envio", tmp_path / "fora"
    tif(envio / "bom.tif", valor=1)
    segredo = tif(fora / "segredo.tif", valor=222)
    banda2 = (f'<!--{"A" * (1 << 20)}-->\n<VRTRasterBand dataType="Byte" band="2"><SimpleSource>'
              f'<SourceFilename relativeToVRT="0">{segredo}</SourceFilename><SourceBand>1</SourceBand>'
              f'<SrcRect xOff="0" yOff="0" xSize="8" ySize="8"/><DstRect xOff="0" yOff="0" xSize="8" ySize="8"/>'
              f'</SimpleSource></VRTRasterBand>')
    alvo = vrt(envio / "a.vrt", "bom.tif", banda_extra=banda2)
    relatorio = v.validar(alvo, respostas=RESPOSTA_DATA)
    with rasterio.open(alvo) as d:
        assert int(d.read(2)[0, 0]) == 222
    assert relatorio["estado"] == "recusado", f"{relatorio['estado']}, {relatorio['info'].get('bandas')} bandas"


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 3: o link simbólico é recusado no arquivo ENVIADO e nas entradas do zip, mas não na FONTE do VRT: origem.tif
# -> caminho de fora é aceito.
def test_vrt_com_fonte_por_link_simbolico_nao_deve_passar(tmp_path: Path) -> None:
    envio, fora = tmp_path / "envio", tmp_path / "fora"
    segredo = tif(fora / "segredo.tif", valor=177)
    envio.mkdir(parents=True, exist_ok=True)
    (envio / "origem.tif").symlink_to(segredo)
    alvo = vrt(envio / "b.vrt", "origem.tif")
    relatorio = v.validar(alvo, respostas=RESPOSTA_DATA)
    with rasterio.open(alvo) as d:
        assert int(d.read(1)[0, 0]) == 177
    assert relatorio["estado"] == "recusado", relatorio["estado"]


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 4: pelo VRT aninhado a validação SAI À REDE. A lista branca CPL_VSIL_CURL_ALLOWED_EXTENSIONS tem uma
# extensão inventada, e quem escreve a URL escolhe a extensão; 'http://' direto também conecta.
def test_validacao_nao_deve_abrir_conexao_de_rede(tmp_path: Path) -> None:
    pedidos: list[str] = []
    ouvinte = socket.socket()
    ouvinte.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ouvinte.bind(("127.0.0.1", 0))
    ouvinte.listen(4)
    porta = ouvinte.getsockname()[1]

    def atender() -> None:
        ouvinte.settimeout(25)
        while True:
            try:
                conexao, _ = ouvinte.accept()
            except OSError:
                return
            conexao.settimeout(3)
            try:
                pedidos.append(conexao.recv(2048).decode("latin1").splitlines()[0])
            except (OSError, IndexError, UnicodeDecodeError):
                pedidos.append("conexão sem pedido legível")
            conexao.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            conexao.close()

    thread = threading.Thread(target=atender, daemon=True)
    thread.start()
    try:
        envio = tmp_path / "envio"
        tif(envio / "bom.tif")
        for nome, url in (("b1.vrt", f"/vsicurl/http://127.0.0.1:{porta}/x.nenhuma-extensao-permitida"),
                          ("b2.vrt", f"http://127.0.0.1:{porta}/y.tif")):
            vrt(envio / nome, url, relativo="0", com_srs=False)
            v.validar(vrt(envio / f"a_{nome}", nome), respostas=RESPOSTA_DATA)
        time.sleep(1.5)
    finally:
        ouvinte.close()
        thread.join(timeout=5)
    assert pedidos == [], f"a validação conectou em 127.0.0.1:{porta}: {pedidos}"


def test_vrt_remoto_no_topo_e_recusado(tmp_path: Path) -> None:
    """Defesa que segurou: fonte remota ou /vsi… no VRT ENVIADO é recusada antes de qualquer leitura."""
    envio = tmp_path / "envio"
    tif(envio / "bom.tif")
    for fonte in ("http://exemplo.invalido/x.tif", "/vsicurl/http://exemplo.invalido/x.tif",
                  "/vsis3/balde/x.tif", "/vsizip//tmp/x.zip/x.tif", "../fora.tif", "/etc/passwd"):
        alvo = vrt(envio / "a.vrt", fonte, relativo="0")
        relatorio = v.validar(alvo, respostas=RESPOSTA_DATA)
        assert relatorio["estado"] == "recusado", f"{fonte} passou"
        assert relatorio["problemas"][0].startswith(("VRT com fonte fora", "VRT referencia fonte inexistente")), \
            relatorio["problemas"]


def test_vrtrawrasterband_aninhado_nao_le_arquivo_do_sistema(tmp_path: Path) -> None:
    """Defesa que segurou (pelo GDAL, não pela conferência): mesmo escondida num VRT de segundo nível, a banda
    crua não lê /etc/passwd, porque o ambiente do filho tem GDAL_VRT_ENABLE_RAWRASTERBAND=NO."""
    envio = tmp_path / "envio"
    tif(envio / "bom.tif")
    (envio / "b.vrt").write_text(
        '<VRTDataset rasterXSize="16" rasterYSize="16">'
        '<VRTRasterBand dataType="Byte" band="1" subClass="VRTRawRasterBand">'
        '<SourceFilename relativeToVRT="0">/etc/passwd</SourceFilename>'
        '<ImageOffset>0</ImageOffset><PixelOffset>1</PixelOffset><LineOffset>16</LineOffset>'
        '</VRTRasterBand></VRTDataset>', "utf-8")
    alvo = vrt(envio / "a.vrt", "b.vrt", lado=16)
    relatorio = v.validar(alvo, respostas=RESPOSTA_DATA)
    assert relatorio["estado"] == "recusado", relatorio
    assert relatorio["subprocesso"]["morte"] is None


def test_arquivo_vizinho_aux_xml_e_ignorado(tmp_path: Path) -> None:
    """Defesa que segurou: um .aux.xml plantado ao lado não empresta CRS nem data ao arquivo enviado
    (GDAL_PAM_ENABLED=NO). A pergunta do CRS continua sendo feita."""
    envio = tmp_path / "envio"
    alvo = tif(envio / "sem_crs.tif", crs=None)
    (envio / "sem_crs.tif.aux.xml").write_text(
        '<PAMDataset><SRS>EPSG:4674</SRS><Metadata>'
        '<MDI key="ACQUISITIONDATETIME">1999-01-01</MDI></Metadata></PAMDataset>', "utf-8")
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "pendente"
    assert [p["campo"] for p in relatorio["pendencias"]] == ["crs"]
    assert relatorio["info"]["crs"] is None
    assert relatorio["info"]["data_aquisicao"]["valor"] == "2026-01-02"  # do TIFFTAG do próprio arquivo


# =========================================================== ATAQUE 2 — aceitação silenciosa
# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 5: NoData NaN (comum em float32) entra no relatório como NaN, que não é JSON válido. psycopg2.extras.Json
# produz 'NaN' e o jsonb do Postgres recusa — o relatório não chega a ser gravado no job.
def test_relatorio_com_nodata_nan_tem_de_ser_json_valido(tmp_path: Path) -> None:
    alvo = tif(tmp_path / "nan.tif", dtype="float32", nodata=float("nan"))
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "aceito"
    json.dumps(relatorio, allow_nan=False)   # é isto que o jsonb exige


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 6: extensão impossível (latitude 7.400.000° num CRS geográfico) sai como AVISO e o arquivo é aceito. 'fora
# do Brasil' e 'coordenada que não existe' recebem o mesmo tratamento.
def test_extensao_geografica_impossivel_nao_deve_ser_aceita(tmp_path: Path) -> None:
    alvo = tif(tmp_path / "utm.tif", crs=None, transformacao=from_origin(300000.0, 7400000.0, 10.0, 10.0))
    relatorio = v.validar(alvo, respostas={"crs": 4674})
    assert relatorio["info"]["bbox4326"][3] > 90     # latitude declarada acima do polo
    assert relatorio["estado"] != "aceito", relatorio["avisos"]


def test_tipo_de_dado_exotico_passa_sem_uma_palavra(tmp_path: Path) -> None:
    """Não é promessa do portão, então não é achado: fica registrado que complex64 e int64 são ACEITOS sem
    aviso nem pergunta, embora nenhum COG/tile sirva esses tipos. Fronteira, não defeito."""
    for tipo in ("complex64", "int64"):
        alvo = tif(tmp_path / f"{tipo}.tif", dtype=tipo, nodata=None)
        relatorio = v.validar(alvo, respostas={"nodata": 0})
        assert relatorio["estado"] == "aceito"
        assert relatorio["avisos"] == []
        assert relatorio["info"]["tipo"] == tipo


# =========================================================== ATAQUE 3 — limite que não segura
def test_limites_do_filho_conferidos_no_proc_do_processo_vivo(tmp_path: Path) -> None:
    """Prova independente (não olha o código do pai): enquanto o filho roda, lê /proc/<pid>/limits e
    /proc/<pid>/environ dele."""
    alvo = tif(tmp_path / "x.tif", lado=64)
    os.environ["PLAT_DSN"] = "dbname=nao_devia_chegar_aqui"
    os.environ["PLAT_SECRET"] = "segredo"
    achado: dict = {}

    def espiar() -> None:
        fim = time.time() + 20
        while time.time() < fim and not achado:
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                    if argv[1:3] != [b"-m", b"app.raster.validacao"]:
                        continue
                    achado.update(limites=Path(f"/proc/{pid}/limits").read_text(),
                                  ambiente=Path(f"/proc/{pid}/environ").read_bytes())
                    return
                except (OSError, IndexError):
                    continue
            time.sleep(0.0005)

    try:
        for _ in range(3):
            thread = threading.Thread(target=espiar)
            thread.start()
            v.validar(alvo)
            thread.join()
            if achado:
                break
    finally:
        os.environ.pop("PLAT_DSN", None)
        os.environ.pop("PLAT_SECRET", None)
    assert achado, "não consegui capturar o filho vivo"
    def valor(rotulo: str) -> str:
        return [ln for ln in achado["limites"].splitlines() if ln.startswith(rotulo)][0].split()[-3]
    assert valor("Max address space") == str(v.RLIMIT_AS_MB * 1024 * 1024)
    assert valor("Max cpu time") == str(v.RLIMIT_CPU_S)
    assert valor("Max open files") == str(v.RLIMIT_NOFILE)
    assert valor("Max core file size") == "0"
    ambiente = dict(e.decode("utf-8", "replace").split("=", 1)
                    for e in achado["ambiente"].split(b"\0") if b"=" in e)
    assert "PLAT_DSN" not in ambiente and "PLAT_SECRET" not in ambiente
    assert ambiente["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"
    assert ambiente["GDAL_PAM_ENABLED"] == "NO"
    assert ambiente["GDAL_VRT_ENABLE_RAWRASTERBAND"] == "NO"


def test_bloco_de_1_gb_declarado_no_cabecalho_nao_derruba_ninguem(tmp_path: Path) -> None:
    """Ataque de memória por CABEÇALHO (sem o atalho `_prova` do construtor): GeoTIFF válido de 1024×1024 com as
    tags de ladrilho reescritas para 32768×32768, ou seja, 1 GiB por bloco contra RLIMIT_AS de 768 MB."""
    alvo = tif(tmp_path / "ladrilho.tif", lado=1024, tiled=True, blockxsize=256, blockysize=256)
    bruto = bytearray(alvo.read_bytes())
    inicio = struct.unpack_from("<I", bruto, 4)[0]
    quantas = struct.unpack_from("<H", bruto, inicio)[0]
    reescritas = 0
    for i in range(quantas):
        posicao = inicio + 2 + i * 12
        tag, tipo = struct.unpack_from("<HH", bruto, posicao)
        if tag in (322, 323) and tipo == 3:
            struct.pack_into("<H", bruto, posicao + 8, 32768)
            reescritas += 1
    assert reescritas == 2
    alvo.write_bytes(bytes(bruto))
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "recusado", relatorio
    assert relatorio["problemas"][0].startswith(("os dados de", "a validação")), relatorio["problemas"]
    assert relatorio["subprocesso"]["ram_pico_kb"] < v.RLIMIT_AS_MB * 1024
    assert relatorio["subprocesso"]["morte"] in (None, "memoria")


def test_faixa_unica_de_858_mb_nao_derruba_ninguem(tmp_path: Path) -> None:
    """Outro caminho de memória: 30.000×30.000 esparso com a faixa inteira num bloco só (858 MB), 597 bytes em
    disco. Tem de sair recusa, com o pai vivo e o pico bem abaixo do RLIMIT."""
    alvo = tmp_path / "faixa.tif"
    with rasterio.open(alvo, "w", driver="GTiff", width=30000, height=30000, count=1, dtype="uint8",
                       crs="EPSG:4674", transform=from_origin(-47, -15, 0.00001, 0.00001), nodata=0,
                       compress="deflate", blockysize=30000, SPARSE_OK=True, BIGTIFF="YES") as d:
        d.update_tags(TIFFTAG_DATETIME="2026:01:02 00:00:00")
    assert alvo.stat().st_size < 100 * 1024
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "recusado"
    assert relatorio["subprocesso"]["ram_pico_kb"] < v.RLIMIT_AS_MB * 1024
    assert os.getpid() > 0   # o pai continua de pé para afirmar isto


def test_bigtiff_esparso_de_95_gb_recusado_com_arquivo_proprio(tmp_path: Path) -> None:
    """Refaço o caso do construtor com arquivo meu: 320.000×320.000 esparso."""
    alvo = tmp_path / "esparso.tif"
    with rasterio.open(alvo, "w", driver="GTiff", width=320000, height=320000, count=1, dtype="uint8",
                       crs="EPSG:4674", transform=from_origin(-47, -15, 0.00001, 0.00001), nodata=0,
                       BIGTIFF="YES", SPARSE_OK=True, tiled=True, blockxsize=512, blockysize=512) as d:
        d.update_tags(TIFFTAG_DATETIME="2026:01:02 00:00:00")
    inicio = time.monotonic()
    relatorio = v.validar(alvo)
    decorrido = time.monotonic() - inicio
    assert relatorio["estado"] == "recusado"
    assert relatorio["problemas"][0].startswith("tamanho descompactado estimado de 95.4 GB")
    assert relatorio["subprocesso"]["morte"] is None
    assert relatorio["subprocesso"]["ram_pico_kb"] < 200_000
    assert decorrido < 5, decorrido


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 7: a conta de bomba zip é uma RAZÃO (50×). Um zip a 42× é extraído inteiro para o disco ANTES de qualquer
# checagem de raster: o que limita a escrita é a cota do inquilino (4 GiB por omissão), não o tamanho do envio.
def test_zip_abaixo_da_razao_nao_deveria_escrever_dezenas_de_mb(tmp_path: Path) -> None:
    dentro = tmp_path / "fonte"
    pequeno = tif(dentro / "a.tif").read_bytes()
    carga = pequeno + b"\x00" * (24 * 1024 * 1024) + os.urandom(600 * 1024)
    alvo = tmp_path / "quase.zip"
    with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.tif", pequeno)
        zf.writestr("carga.tif", carga)
    with zipfile.ZipFile(alvo) as zf:
        razao = sum(i.file_size for i in zf.infolist()) / sum(i.compress_size for i in zf.infolist())
    assert razao < v.ZIP_RAZAO_MAX, razao
    relatorio = v.validar(alvo, cota_bytes=32 * 1024 * 1024, respostas=RESPOSTA_DATA,
                          dir_trabalho=tmp_path / "trabalho")
    escrito = bytes_no_diretorio(tmp_path / "trabalho")
    assert relatorio["estado"] in ("aceito", "recusado")
    assert escrito < 10 * alvo.stat().st_size, (f"{escrito} bytes escritos a partir de um envio de "
                                                f"{alvo.stat().st_size} bytes ({escrito / alvo.stat().st_size:.0f}×)")


def test_zip_em_camadas_e_recusado(tmp_path: Path) -> None:
    """Defesa que segurou: zip dentro de zip, inclusive disfarçado de .tif."""
    pequeno = tif(tmp_path / "fonte" / "a.tif").read_bytes()
    interno = tmp_path / "interno.zip"
    with zipfile.ZipFile(interno, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("b.tif", pequeno + b"\x00" * (8 * 1024 * 1024))
    for nome_dentro in ("dentro.zip", "dentro.tif"):
        alvo = tmp_path / f"camadas_{nome_dentro}.zip"
        with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.tif", pequeno)
            zf.writestr(nome_dentro, interno.read_bytes())
        relatorio = v.validar(alvo, cota_bytes=32 * 1024 * 1024, dir_trabalho=tmp_path / f"t_{nome_dentro}")
        assert relatorio["estado"] == "recusado", nome_dentro
        # o disfarçado de .tif só cai na conferência de assinatura DEPOIS de ser escrito: o que é escrito é o
        # tamanho declarado (poucos kB aqui), nunca a bomba de dentro.
        assert bytes_no_diretorio(tmp_path / f"t_{nome_dentro}") < 64 * 1024, nome_dentro


def test_ifd_circular_nao_trava_e_nao_e_aceito_em_silencio(tmp_path: Path) -> None:
    """Caso clássico do adversário, arquivo meu: o próximo IFD aponta para o próprio IFD."""
    alvo = tiff_a_mao(tmp_path / "circular.tif",
                      [(256, 3, 1, 8), (257, 3, 1, 8), (258, 3, 1, 8), (259, 3, 1, 1), (262, 3, 1, 1),
                       (273, 4, 1, 0), (277, 3, 1, 1), (278, 3, 1, 8), (279, 4, 1, 64), (339, 3, 1, 1)],
                      proximo=8)
    inicio = time.monotonic()
    relatorio = v.validar(alvo)
    assert time.monotonic() - inicio < 10
    assert relatorio["estado"] in ("pendente", "recusado")
    assert relatorio["estado"] != "aceito"
    assert relatorio["subprocesso"]["morte"] is None


def test_65535_bandas_recusado_sem_estourar_a_memoria(tmp_path: Path) -> None:
    alvo = tiff_a_mao(tmp_path / "bandas.tif",
                      [(256, 3, 1, 8), (257, 3, 1, 8), (258, 3, 1, 8), (259, 3, 1, 1), (262, 3, 1, 1),
                       (273, 4, 1, 0), (277, 3, 1, 65535), (278, 3, 1, 8), (279, 4, 1, 64), (284, 3, 1, 1),
                       (339, 3, 1, 1)])
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "recusado"
    assert relatorio["subprocesso"]["ram_pico_kb"] < v.RLIMIT_AS_MB * 1024
    assert relatorio["subprocesso"]["morte"] is None


def test_tif_que_e_png_nao_abre_subprocesso(tmp_path: Path) -> None:
    alvo = tmp_path / "foto.tif"
    alvo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 128)
    relatorio = v.validar(alvo)
    assert relatorio["estado"] == "recusado"
    assert relatorio["subprocesso"] is None, "abriu subprocesso para um arquivo que o pai já sabia recusar"
    assert relatorio["problemas"][0] == ("o conteúdo não corresponde à extensão .tif: os primeiros bytes são de "
                                         "PNG, não de GeoTIFF")


# =========================================================== ATAQUE 4 — mensagem
# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 8: um GeoTIFF sem geotransform com CRS respondido derruba o filho por exceção NÃO capturada
# (rasterio._err.CPLE_AppDefinedError não é RasterioError nem ValueError). A recusa sai com a linha crua do
# traceback, em inglês, e sem dizer o que fazer.
def test_arquivo_sem_geotransform_tem_de_sair_com_mensagem_em_portugues(tmp_path: Path) -> None:
    from rasterio.transform import Affine
    alvo = tif(tmp_path / "sem_transform.tif", transformacao=Affine.identity())
    relatorio = v.validar(alvo, respostas={"crs": 4674})
    problema = relatorio["problemas"][0] if relatorio["problemas"] else ""
    assert "CPLE_" not in problema and "rasterio._err" not in problema, problema
    assert relatorio["subprocesso"]["codigo_saida"] == 0, problema


# CONSERTADO (turno 3, ADR 0015): o achado abaixo foi tapado e este teste passa; o marcador
# xfail(strict=True) do adversário saiu porque o conserto o transformaria em falha. O texto do
# achado fica aqui para que nada se perca.
# ACHADO 9: um zip legítimo com 200 GeoTIFF pequenos é recusado por causa do RLIMIT_NOFILE=64 (todos os arquivos são
# abertos ao mesmo tempo), com mensagem em inglês do GDAL e com o CAMINHO ABSOLUTO do servidor dentro dela.
def test_zip_com_200_rasters_legitimos_nao_deve_ser_recusado_em_ingles(tmp_path: Path) -> None:
    pequeno = tif(tmp_path / "fonte" / "a.tif").read_bytes()
    alvo = tmp_path / "muitos.zip"
    with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(200):
            zf.writestr(f"t{i:03d}.tif", pequeno)
    relatorio = v.validar(alvo, respostas=RESPOSTA_DATA, dir_trabalho=tmp_path / "trabalho")
    problema = relatorio["problemas"][0] if relatorio["problemas"] else ""
    assert "Too many open files" not in problema, problema
    assert str(tmp_path) not in problema, "a mensagem entrega o caminho absoluto do servidor"
    assert relatorio["estado"] != "recusado", problema


def test_mensagens_de_recusa_carregam_texto_em_ingles_do_gdal(tmp_path: Path) -> None:
    """Registro, não promessa quebrada: várias recusas terminam com o texto do GDAL/zipfile em inglês colado
    depois do prefixo em português. Este teste passa hoje e serve de linha de base."""
    ingles = []
    alvo = tmp_path / "vazio.zip"
    alvo.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    ingles.append(v.validar(alvo)["problemas"][0])
    jp2 = tmp_path / "trunc.jp2"
    jp2.write_bytes(b"\x00\x00\x00\x0cjP  \r\n\x87\n" + b"\x00" * 200)
    ingles.append(v.validar(jp2)["problemas"][0])
    assert ingles[0] == "zip inválido: File is not a zip file"
    assert ingles[1] == "o GDAL não abriu trunc.jp2: No code-stream in JP2 file"


# =========================================================== ATAQUE 5 — medida
def test_medida_de_ram_e_tempo_confere_com_o_arquivo_de_medidas(tmp_path: Path) -> None:
    """Mede por fora (`/usr/bin/time -v` no filho, chamado à mão) e compara com tests/medidas/L1-01-b.json.
    Tolerância de 30 % contra a MEDIANA do arquivo do construtor."""
    medidas = json.loads((Path(__file__).resolve().parents[1] / "medidas" / "L1-01-b.json").read_text())["medidas"]
    rams = sorted(m["valor"] for k, m in medidas.items() if k.endswith("ram_pico_kb"))
    tempos = sorted(m["valor"] for k, m in medidas.items() if k.endswith("tempo_s"))
    mediana_ram = rams[len(rams) // 2]
    mediana_tempo = tempos[len(tempos) // 2]
    alvo = tif(tmp_path / "medida.tif", lado=64)
    argumento = json.dumps({"caminho": str(alvo), "perfil": "dados", "respostas": {},
                            "cota_bytes": 4 * 1024 ** 3, "dir_trabalho": str(tmp_path), "prova": None})
    saida = subprocess.run(["/usr/bin/time", "-v", sys.executable, "-m", "app.raster.validacao", argumento],
                           capture_output=True, cwd=str(Path(__file__).resolve().parents[2]), timeout=120,
                           check=True)
    linhas = saida.stderr.decode("utf-8", "replace").splitlines()
    rss = int([ln for ln in linhas if "Maximum resident set size" in ln][0].split()[-1])
    decorrido = [ln for ln in linhas if "Elapsed (wall clock)" in ln][0].split()[-1]
    segundos = float(decorrido.split(":")[-1])
    assert abs(rss - mediana_ram) / mediana_ram < 0.30, (rss, mediana_ram)
    assert abs(segundos - mediana_tempo) / mediana_tempo < 0.30, (segundos, mediana_tempo)
    assert rss < v.RLIMIT_AS_MB * 1024
