"""SEGUNDO ADVERSÁRIO do item L1-01-b (validação e isolamento da entrada raster).

O primeiro adversário refutou o item; o construtor consertou (commits 8be23a6/50611ed/e5c0885) e trocou o
mecanismo: agora a rede é fechada NO PROCESSO por um filtro seccomp BPF, `_conferir_vrt` é recursivo com
`realpath`, NaN vira texto, o zip tem teto de volume. Este arquivo ataca o MECANISMO NOVO.

Sem banco: `venv/bin/pytest tests/unit/test_raster_validacao_adversario2.py -q -rxX`.

Cada teste que EXPÕE defeito é `xfail(strict=True)`: o corpo afirma o que o item promete; se o produto
passar a cumprir, o `strict` transforma em falha e o achado não se perde. Os testes sem `xfail` são defesas
do mecanismo novo que eu ataquei e não caíram.

Resumo dos achados (detalhe no handoff L1-01-b-ADVERSARIO2.md):
* H1 (grave): `_conferir_vrt` só olha `<SourceFilename>`. Um VRTWarpedDataset usa `<SourceDataset>`, que
  NÃO é conferido. Um VRT enviado lê arquivo LOCAL fora do diretório do envio (seccomp ligado), e com o
  seccomp degradado leva `validar()` a bater na rede de um endereço escolhido por quem enviou.
* H2 (grave): o ambiente do filho vaza `PLAT_DSN_WORKER` (senha da role que escreve no banco) e
  `PLAT_GARAGE_ADMIN_TOKEN`; só `PLAT_DSN`/`PLAT_SECRET` são removidos. Como o seccomp deixa `AF_UNIX`
  passar, o filho conecta ao soquete local do Postgres. "o filho nunca fala com o banco" é falso.
"""
from __future__ import annotations

import http.server
import os
import socket
import subprocess
import sys
import threading
import time

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.raster import validacao as V


# ----------------------------------------------------------------------------- utilitários
def _tif(caminho, valor, largura=64, altura=64, bandas=1, dtype="uint8"):
    with rasterio.open(caminho, "w", driver="GTiff", width=largura, height=altura, count=bandas,
                       dtype=dtype, crs="EPSG:4674",
                       transform=from_origin(-47.0, -15.0, 0.001, 0.001)) as d:
        for b in range(1, bandas + 1):
            d.write(np.full((altura, largura), valor, dtype), b)


class _Ouvinte:
    """Servidor HTTP em 127.0.0.1 que só anota o que recebe e devolve 404."""

    def __init__(self):
        self.pedidos: list[str] = []
        pai = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # silêncio
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


# Template de VRTWarpedDataset VÁLIDO, capturado de `gdal.Warp(..., format="VRT")` (GDAL 3.12.1) e
# parametrizado. O ponto do ataque: a fonte fica em <SourceDataset>, que `_conferir_vrt` NUNCA confere,
# enquanto a isca <SourceFilename> (dentro de um comentário XML, que o regex do produto não respeita)
# aponta para um arquivo legítimo DENTRO do envio e faz a conferência passar.
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
    <SourceDataset relativeToVRT="0">__FONTE__</SourceDataset>
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


def _vrt_warped(fonte: str, isca: str = _ISCA) -> str:
    """VRTWarpedDataset: a fonte fica em <SourceDataset>, não em <SourceFilename>."""
    return _VRT_WARPED.replace("__ISCA__", isca).replace("__FONTE__", str(fonte))


# ============================================================================= ATAQUE 1 e 2 — VRT/seccomp
# CONSERTADO (turno 4): a conferência percorre todo nó do XML, inclusive <SourceDataset>.
def test_vrt_warped_sourcedataset_nao_deve_ler_arquivo_fora_do_envio(tmp_path):
    """Achado 1 do 1º adversário RENASCE por outro elemento do VRT. O construtor confere <SourceFilename>
    recursivamente, mas o VRTWarpedDataset referencia a fonte em <SourceDataset>, que passa direto."""
    envio = tmp_path / "envio"
    envio.mkdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    _tif(envio / "bom.tif", 1)
    _tif(fora / "segredo.tif", 222)
    (envio / "w.vrt").write_text(_vrt_warped(str(fora / "segredo.tif")))

    r = V.validar(envio / "w.vrt", respostas={"data_aquisicao": "2026-01-02"})
    # a promessa do item: fonte fora do diretório do envio é recusada.
    assert r["estado"] == "recusado", (
        f"o VRT warped foi {r['estado']} e leu {fora/'segredo.tif'} (fora do envio); "
        f"info={r['info'].get('arquivos')}")


# CONSERTADO (turno 4): a fonte remota do warp é recusada no XML, antes de o GDAL abrir o arquivo — a
# rede deixa de depender só do filtro de chamadas de sistema.
def test_vrt_warped_com_seccomp_degradado_nao_deve_bater_na_rede(tmp_path, monkeypatch):
    """A rede fechada depende SÓ do seccomp: as variáveis do GDAL não barram /vsicurl com a extensão que o
    atacante escolhe. Se a instalação do filtro falhar (kernel/arquitetura/libc), a SSRF volta e o
    <SourceDataset> não é conferido para impedir."""
    envio = tmp_path / "envio"
    envio.mkdir()
    _tif(envio / "bom.tif", 1)   # a isca <SourceFilename> tem de existir para a conferência passar
    ouvinte = _Ouvinte()
    monkeypatch.setattr(V, "_fechar_a_rede", lambda: False)  # simula seccomp indisponível
    url = f"/vsicurl/http://127.0.0.1:{ouvinte.porta}/x.nenhuma-extensao-permitida"
    (envio / "w.vrt").write_text(_vrt_warped(url))
    try:
        r = V.validar(envio / "w.vrt", respostas={"data_aquisicao": "2026-01-02"})
        time.sleep(0.7)
        assert ouvinte.pedidos == [], (
            f"validar() enviou pedido de rede com o seccomp degradado: {ouvinte.pedidos}; "
            f"estado={r['estado']} seccomp={r['info'].get('isolamento', {}).get('seccomp')}")
    finally:
        ouvinte.parar()


def test_seccomp_e_a_barreira_de_rede_ligado_bloqueia_desligado_libera(tmp_path):
    """DEFESA (passa): mede que o seccomp é a barreira que segura, e as variáveis do GDAL sozinhas NÃO
    seguram /vsicurl com a extensão da allowlist. Prova que, quando o filtro sobe, a rede fecha."""
    ouvinte = _Ouvinte()
    ambiente = {**os.environ, **V.AMBIENTE_FILHO}
    url = f"/vsicurl/http://127.0.0.1:{ouvinte.porta}/x.nenhuma-extensao-permitida"
    codigo = ("import rasterio\n"
              "try:\n"
              f"  rasterio.open({url!r}).read(1)\n"
              "except Exception as e:\n"
              "  print(type(e).__name__)\n")

    def _preexec_sem_seccomp():
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    try:
        subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=ambiente, preexec_fn=V._preparar_filho)
        time.sleep(0.5)
        com_seccomp = list(ouvinte.pedidos)
        ouvinte.pedidos.clear()
        subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=ambiente, preexec_fn=_preexec_sem_seccomp)
        time.sleep(0.5)
        sem_seccomp = list(ouvinte.pedidos)
    finally:
        ouvinte.parar()
    assert com_seccomp == [], f"seccomp ligado deixou passar pedido: {com_seccomp}"
    assert sem_seccomp, "sem seccomp a rede NÃO abriu — então o filtro não é o que segura (revisar a tese)"


def test_seccomp_bloqueia_af_inet_e_inet6_no_filho_preparado():
    """DEFESA (passa): o filtro faz socket(AF_INET/AF_INET6) devolver EAFNOSUPPORT."""
    codigo = ("import socket, json\n"
              "r = {}\n"
              "for nome, fam in [('AF_INET', socket.AF_INET), ('AF_INET6', socket.AF_INET6)]:\n"
              "    try:\n"
              "        socket.socket(fam, socket.SOCK_STREAM).close(); r[nome] = 'criou'\n"
              "    except OSError as e:\n"
              "        r[nome] = e.errno\n"
              "print(json.dumps(r))\n")
    ambiente = {**os.environ, **V.AMBIENTE_FILHO}
    p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=ambiente, preexec_fn=V._preparar_filho)
    import json
    r = json.loads(p.stdout)
    import errno
    assert r["AF_INET"] == errno.EAFNOSUPPORT and r["AF_INET6"] == errno.EAFNOSUPPORT, r


def test_descritor_de_soquete_herdado_do_pai_e_fechado_no_filho():
    """DEFESA (passa): o filtro impede CRIAR soquete, mas não usar um herdado — o furo clássico. Aqui o
    Popen (close_fds padrão) fecha os fds herdados, então o furo está fechado por outro motivo."""
    lst = socket.socket()
    lst.bind(("127.0.0.1", 0))
    lst.listen()
    fd = lst.fileno()
    codigo = ("import socket\n"
              "try:\n"
              f"    s = socket.socket(fileno={fd})\n"
              "    s.getsockname(); print('USAVEL')\n"
              "except OSError as e:\n"
              "    print('fechado', e.errno)\n")
    ambiente = {**os.environ, **V.AMBIENTE_FILHO}
    p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=ambiente, preexec_fn=V._preparar_filho)
    lst.close()
    assert "USAVEL" not in p.stdout, f"o filho usou um fd de soquete herdado: {p.stdout!r}"


# ============================================================================= ATAQUE 3 — falso senso de segurança
def test_seccomp_degradado_e_registrado_no_relatorio(tmp_path, monkeypatch):
    """DEFESA PARCIAL (passa): quando o filtro não sobe, o relatório NÃO diz `seccomp: 2` — grava
    `seccomp: 0` e troca o texto da rede. Não é silêncio total. PORÉM não recusa nem emite aviso/pendência,
    e (ver test_vrt_warped_com_seccomp_degradado_...) nesse modo a rede volta a abrir."""
    envio = tmp_path / "envio"
    envio.mkdir()
    _tif(envio / "a.tif", 1, bandas=3)
    monkeypatch.setattr(V, "_fechar_a_rede", lambda: False)
    r = V.validar(envio / "a.tif", respostas={"data_aquisicao": "2026-01-02"})
    iso = r["info"]["isolamento"]
    assert iso["seccomp"] == 0, iso
    assert "apenas por variável" in iso["rede"], iso
    # a fronteira honesta: nenhum aviso/pendência avisa que a rede ficou aberta
    assert not any("rede" in a.lower() or "seccomp" in a.lower() for a in r["avisos"]), \
        "documentado: o modo degradado não gera aviso — o operador tem de ler info.isolamento"


# ============================================================================= ATAQUE 1 — furo AF_UNIX + segredos
# CONSERTADO (turno 4): o ambiente do filho é montado por lista de permissão (`ambiente_do_filho`).
def test_segredos_do_worker_nao_devem_vazar_para_o_filho(monkeypatch):
    """`_executar_filho` faz {**os.environ, **AMBIENTE_FILHO} e remove só PLAT_DSN e PLAT_SECRET. A senha da
    role que ESCREVE no banco (PLAT_DSN_WORKER) e o token de administração do Garage seguem no ambiente do
    filho — que roda código do GDAL sobre arquivo hostil. "o filho nunca fala com o banco" pressupõe que a
    credencial não esteja lá."""
    monkeypatch.setenv("PLAT_DSN_WORKER", "postgresql://plat_worker:SENHA@127.0.0.1/iagro_sat")
    monkeypatch.setenv("PLAT_GARAGE_ADMIN_TOKEN", "token-admin-garage")
    ambiente = V.ambiente_do_filho()
    vazados = [k for k in ("PLAT_DSN_WORKER", "PLAT_GARAGE_ADMIN_TOKEN") if k in ambiente]
    assert vazados == [], f"o filho recebe segredos do worker: {vazados}"


def test_seccomp_deixa_af_unix_passar_documenta_a_fronteira():
    """DEFESA/FRONTEIRA (passa): o filtro só cobre AF_INET/AF_INET6. AF_UNIX segue permitido (a libc
    precisa), então o filho consegue criar soquete de domínio local. Combinado com o vazamento de
    PLAT_DSN_WORKER, um código-execução no filho alcança o Postgres pelo soquete local. Documento o fato;
    a fronteira do isolamento é de processo, não de máquina."""
    codigo = ("import socket\n"
              "try:\n"
              "    socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close(); print('AF_UNIX_OK')\n"
              "except OSError as e:\n"
              "    print('bloqueado', e.errno)\n")
    ambiente = {**os.environ, **V.AMBIENTE_FILHO}
    p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=ambiente, preexec_fn=V._preparar_filho)
    assert "AF_UNIX_OK" in p.stdout, p.stdout


# ============================================================================= ATAQUE 4 — VRT SimpleSource
def test_vrt_simplesource_defesas_seguraram(tmp_path):
    """DEFESA (passa): pelo <SourceFilename> (SimpleSource), tudo o que o ataque pediu é recusado:
    profundidade 6, ligação simbólica para fora, `..` que sai de vez, byte nulo, e um XML de 16 MiB - 1
    com a fonte hostil no fim. O `..` que sai e VOLTA para dentro do envio é legítimo e é aceito."""
    envio = tmp_path / "envio"
    envio.mkdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    _tif(envio / "bom.tif", 1)
    _tif(fora / "segredo.tif", 99)

    def vrt(nome, src, rel="1"):
        (envio / nome).write_text(
            f'<VRTDataset rasterXSize="64" rasterYSize="64"><VRTRasterBand dataType="Byte" band="1">'
            f'<SimpleSource><SourceFilename relativeToVRT="{rel}">{src}</SourceFilename>'
            f'<SrcRect xOff="0" yOff="0" xSize="64" ySize="64"/>'
            f'<DstRect xOff="0" yOff="0" xSize="64" ySize="64"/></SimpleSource></VRTRasterBand></VRTDataset>')
        return envio / nome

    # 7 níveis (um a mais que 5+1) -> recusado
    prev = "bom.tif"
    for i in range(7):
        vrt(f"v{i}.vrt", prev)
        prev = f"v{i}.vrt"
    assert V.validar(envio / "v6.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # ligação simbólica para fora -> recusado
    os.symlink(fora / "segredo.tif", envio / "link.tif")
    vrt("s.vrt", "link.tif")
    assert V.validar(envio / "s.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # `..` que sai de vez -> recusado
    vrt("o.vrt", "../fora/segredo.tif")
    assert V.validar(envio / "o.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # byte nulo -> recusado
    (envio / "n.vrt").write_bytes(
        ('<VRTDataset rasterXSize="64" rasterYSize="64"><VRTRasterBand dataType="Byte" band="1">'
         '<SimpleSource><SourceFilename relativeToVRT="0">' + str(fora / "segredo.tif")
         + '\x00.tif</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>').encode())
    assert V.validar(envio / "n.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # 16 MiB - 1, fonte hostil no fim -> recusado (XML lido inteiro)
    pad = "<!-- " + ("A" * (16 * 1024 * 1024)) + " -->"
    corpo = (f'<VRTDataset rasterXSize="64" rasterYSize="64">{pad}<VRTRasterBand dataType="Byte" band="1">'
             f'<SimpleSource><SourceFilename relativeToVRT="0">{fora/"segredo.tif"}</SourceFilename>'
             f'</SimpleSource></VRTRasterBand></VRTDataset>').encode()[: 16 * 1024 * 1024 - 1]
    (envio / "big.vrt").write_bytes(corpo)
    assert V.validar(envio / "big.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # `..` que sai e VOLTA para dentro -> legítimo, aceito/pendente (nunca recusado por fonte externa)
    (envio / "sub").mkdir()
    vrt("volta.vrt", "sub/../bom.tif")
    assert V.validar(envio / "volta.vrt", respostas={"data_aquisicao": "2026-01-02"})["estado"] != "recusado"


# ============================================================================= ATAQUE 5 — zip
def test_zip_defesas_seguraram(tmp_path):
    """DEFESA (passa): zip aninhado (2 níveis) recusado; entrada com nome `../` recusada e nada escapa;
    200 rasters legítimos são aceitos (abre um de cada vez, não estoura o RLIMIT_NOFILE); o volume escrito
    fica dentro do teto."""
    import io
    import shutil
    import zipfile
    envio = tmp_path / "envio"
    envio.mkdir()
    _tif(tmp_path / "r.tif", 7)
    raster = (tmp_path / "r.tif").read_bytes()

    def disco():
        d = envio / "zip_extraido"
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else 0

    # 200 rasters -> aceito
    z = envio / "muitos.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        for i in range(200):
            zf.writestr(f"r{i}.tif", raster)
    r = V.validar(z, respostas={"data_aquisicao": "2026-01-02"})
    assert r["estado"] != "recusado", (r["estado"], r["problemas"][:1])
    assert disco() <= 200 * len(raster) + 4096
    shutil.rmtree(envio / "zip_extraido", ignore_errors=True)

    # zip aninhado 2 níveis -> recusado
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("r.tif", raster)
    mid = io.BytesIO()
    with zipfile.ZipFile(mid, "w") as zf:
        zf.writestr("inner.zip", inner.getvalue())
    (envio / "outer.zip").write_bytes(mid.getvalue())
    assert V.validar(envio / "outer.zip", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"

    # nome ../ -> recusado, nada escapa
    with zipfile.ZipFile(envio / "trav.zip", "w") as zf:
        zf.writestr(zipfile.ZipInfo("../escapou.tif"), raster)
    assert V.validar(envio / "trav.zip", respostas={"data_aquisicao": "2026-01-02"})["estado"] == "recusado"
    assert not (tmp_path / "escapou.tif").exists()


# ============================================================================= ATAQUE 6 — NaN/Infinity
def test_nan_e_infinity_viram_texto_e_o_relatorio_e_json_estrito(tmp_path):
    """DEFESA (passa): NoData NaN vira o texto 'NaN'; NoData informado 1e400 vira 'Infinity'; -0.0 é
    preservado como número; o relatório inteiro passa por json.dumps(allow_nan=False). NaN em banda de
    inteiro é impossível de criar (o rasterio recusa), então esse vetor é vazio."""
    import json
    envio = tmp_path / "envio"
    envio.mkdir()

    _tif(envio / "nan.tif", 0.0, dtype="float32")
    with rasterio.open(envio / "nan.tif", "r+") as d:
        d.nodata = float("nan")
    r = V.validar(envio / "nan.tif", respostas={"data_aquisicao": "2026-01-02"})
    assert r["info"]["nodata"]["valor"] == "NaN"
    json.dumps(r, allow_nan=False)  # não levanta

    _tif(envio / "sem_nd.tif", 0.0, dtype="float32")   # sem NoData no arquivo: o informado é que vale
    r2 = V.validar(envio / "sem_nd.tif", respostas={"data_aquisicao": "2026-01-02", "nodata": float("1e400")})
    assert r2["info"]["nodata"]["valor"] == "Infinity"
    json.dumps(r2, allow_nan=False)

    _tif(envio / "z.tif", 0.0, dtype="float32")
    with rasterio.open(envio / "z.tif", "r+") as d:
        d.nodata = -0.0
    r3 = V.validar(envio / "z.tif", respostas={"data_aquisicao": "2026-01-02"})
    assert r3["info"]["nodata"]["valor"] == 0.0  # -0.0 preservado, e é JSON-válido
    json.dumps(r3, allow_nan=False)

    # NoData NaN em banda de INTEIRO: o vetor é vazio. Na criação o rasterio recusa o valor; gravado
    # depois, o GDAL o descarta silenciosamente (nodata volta None). Nenhum NaN chega ao relatório por
    # esse caminho — sobra apenas a pendência normal de NoData não declarado.
    _tif(envio / "int.tif", 0, dtype="int32")
    with rasterio.open(envio / "int.tif", "r+") as d:
        d.nodata = float("nan")
    with rasterio.open(envio / "int.tif") as d:
        assert d.nodata is None, f"o GDAL guardou NaN numa banda int32: {d.nodata}"
    r4 = V.validar(envio / "int.tif", respostas={"data_aquisicao": "2026-01-02"})
    assert r4["info"]["nodata"] is None
    assert any(p["campo"] == "nodata" for p in r4["pendencias"])
    json.dumps(r4, allow_nan=False)


# ============================================================================= ATAQUE 7 — medida
def test_medida_recomputada_e_o_pico_de_ram_nao_e_propriedade_do_ARQUIVO(tmp_path):
    """ATAQUE 7 (recomputar RAM e tempo). O TEMPO confere com o arquivo de medidas. O PICO DE RAM não é
    reprodutível como número do item: `ru_maxrss` do `os.wait4` conta as páginas que o filho herda do PAI
    no fork (o `preexec_fn` força fork antes do exec), então o valor segue o tamanho do worker, não o do
    raster. Medido aqui engordando o próprio pai."""
    import json
    import statistics as st

    envio = tmp_path / "envio"
    envio.mkdir()
    _tif(envio / "a.tif", 1, bandas=3)

    def _rss_do_pai():
        return int(open("/proc/self/status").read().split("VmRSS:")[1].split()[0])

    def _medir():
        r = V.validar(envio / "a.tif", respostas={"data_aquisicao": "2026-01-02"})
        return r["subprocesso"]["ram_pico_kb"], r["subprocesso"]["tempo_s"]

    magro_ram, magro_t = _medir()
    lastro = [bytearray(8 * 1024 * 1024) for _ in range(16)]        # +128 MB no PAI
    for b in lastro:
        b[::4096] = b"\x01" * len(b[::4096])
    gordo_ram, _ = _medir()
    del lastro

    medidas = json.load(open("tests/medidas/L1-01-b.json"))["medidas"]
    t_ref = st.median([v["valor"] for k, v in medidas.items() if k.endswith("tempo_s")])

    # o tempo é estável e confere com o arquivo do construtor
    assert abs(magro_t - t_ref) / t_ref < 0.50, (magro_t, t_ref)
    # o pico do filho segue o pai: engordar o pai em ~128 MB empurra o pico do filho para cima
    assert gordo_ram > magro_ram + 30_000, (
        f"pico do filho não acompanhou o pai (magro={magro_ram} kB, gordo={gordo_ram} kB): "
        "se isto falhar, a leitura de que ru_maxrss herda as páginas do pai está errada")
    # e em ambos os casos o filho fica MUITO abaixo do RLIMIT_AS declarado
    assert gordo_ram < V.RLIMIT_AS_MB * 1024, (gordo_ram, V.RLIMIT_AS_MB * 1024)
