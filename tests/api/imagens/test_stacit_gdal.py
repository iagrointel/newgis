"""Cláusula 7 do item L1-01-a: `GDAL STACIT` abre a busca — a prova de que QGIS/GDAL (e, por tabela, o
navegador STAC do ArcGIS Pro) consomem o catálogo por cima da API da casa, sem atalho ao banco.

Como a prova é de ponta a ponta DE VERDADE, ela precisa de três processos reais, todos levantados e
derrubados pelo próprio teste (nunca toca no plat-api de produção nem em porta alheia):

1. um COG pequeno (256x256, gerado na hora com rasterio) servido por `http.server` numa porta livre —
   é o ativo que o item STAC aponta (href http); sem raster de verdade o gdalinfo não teria o que abrir;
2. a API da casa de pé por uvicorn (`app.main:app`, porta livre escolhida pelo SO), falando com a base
   da trilha — é ela que responde `/svc/<token>/stac/search`, não o TestClient em processo, porque o
   gdalinfo é outro processo e precisa de HTTP de verdade;
3. o `gdalinfo` do sistema contra `STACIT:<url da busca>` — o driver STACIT busca o FeatureCollection,
   escolhe o ativo e monta o mosaico; "Size is 256, 256" na saída = abriu.

E a prova cruzada de graça: a MESMA busca com o token do inquilino B volta vazia (o isolamento já é
testado a fundo em test_isolamento.py) e o gdalinfo falha — ou seja, o cliente GIS de B não monta
mosaico nenhum com o dado de A nem pedindo o id exato.
"""

import http.client
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.api.imagens.conftest import item_stac

GDALINFO = shutil.which("gdalinfo")
RAIZ_REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(GDALINFO is None, reason="gdalinfo não está instalado nesta máquina")

# extensão do COG de prova dentro do Brasil central (coerente com os itens sintéticos da suíte)
COG_BBOX = (-48.0, -16.0, -47.0, -15.0)
COG_LADO = 256


def _porta_livre() -> int:
    """Porta livre escolhida pelo SO (bind na porta 0) — nunca um número fixo, que colidiria com outra
    trilha/serviço na máquina partilhada."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_de_pe(url: str, processo: subprocess.Popen, limite_s: float = 60.0) -> None:
    """Espera a API responder 200 na PRÓPRIA url de busca que o teste vai medir (não /saude: ela exige
    git_sha, que o worktree não expõe ao subprocesso)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < limite_s:
        if processo.poll() is not None:
            raise RuntimeError(f"uvicorn morreu ao subir (código {processo.returncode})")
        try:
            alvo = urlsplit(url)
            con = http.client.HTTPConnection(alvo.hostname, alvo.port, timeout=2)
            con.request("GET", f"{alvo.path}?{alvo.query}")
            resp = con.getresponse()
            resp.read()
            con.close()
            if resp.status == 200:
                return
        except OSError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"uvicorn não respondeu 200 em {limite_s}s em {url}")


def _cog_de_prova(pasta: Path) -> Path:
    """COG mínimo mas legítimo (driver COG do GDAL, com overviews), escrito com o rasterio do venv."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_bounds

    caminho = pasta / "prova.tif"
    xmin, ymin, xmax, ymax = COG_BBOX
    dados = (np.arange(COG_LADO * COG_LADO, dtype="uint16") % 251).astype("uint8").reshape(COG_LADO, COG_LADO)
    with rasterio.open(
        caminho, "w", driver="COG", width=COG_LADO, height=COG_LADO, count=1, dtype="uint8",
        crs="EPSG:4326", transform=from_bounds(xmin, ymin, xmax, ymax, COG_LADO, COG_LADO),
    ) as dst:
        dst.write(dados, 1)
    return caminho


@pytest.fixture(scope="module")
def infra_stacit(tmp_path_factory, token_stac_a, token_stac_b):
    """Sobe COG-server + API reais, semeia coleção/item com o ativo http e devolve as duas URLs de busca
    (token de A e token de B). Derruba só os processos que ela mesma levantou, pelo PID."""
    pasta = tmp_path_factory.mktemp("stacit")
    cog = _cog_de_prova(pasta)

    porta_cog = _porta_livre()
    porta_api = _porta_livre()
    proc_cog = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(porta_cog), "--bind", "127.0.0.1", "--directory", str(pasta)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        c = TestClient(app, base_url="http://testserver")
        tok_a, tok_b = token_stac_a["token"], token_stac_b["token"]
        slug = f"stacit-prova-{secrets.token_hex(4)}"  # sufixo aleatório: o pgstac é global e persiste entre rodadas
        r = c.post(f"/svc/{tok_a}/stac/collections", params={"slug": slug}, json={"title": "Prova GDAL STACIT"})
        assert r.status_code == 201, r.text
        colecao = r.json()["id"]
        href = f"http://127.0.0.1:{porta_cog}/{cog.name}"
        xmin, ymin, xmax, ymax = COG_BBOX
        item = {
            **item_stac("item-stacit-1", colecao, lon=(xmin + xmax) / 2, lat=(ymin + ymax) / 2),
            "bbox": [xmin, ymin, xmax, ymax],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]],
            },
            "assets": {
                "visual": {
                    "href": href,
                    "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                    "roles": ["data"],
                }
            },
        }
        ri = c.post(f"/svc/{tok_a}/stac/collections/{colecao}/items", json=item)
        assert ri.status_code == 201, ri.text

        base = f"http://127.0.0.1:{porta_api}"
        busca_a = f"{base}/svc/{tok_a}/stac/search?collections={colecao}&ids=item-stacit-1"

        # a API de pé só agora, com o item já gravado: a sonda de prontidão é a própria busca. O sha real
        # do HEAD vai no ambiente do subprocesso porque /saude (e o resto do app) o exige no worktree.
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=RAIZ_REPO, capture_output=True, text=True,
        ).stdout.strip()
        ambiente = {**os.environ, "PLAT_GIT_SHA": sha or "stacit-prova"}
        proc_api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(porta_api)],
            cwd=RAIZ_REPO, env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            _esperar_de_pe(busca_a, proc_api)
            yield {
                "busca_a": busca_a,
                "busca_a_mascarada": f"{base}/svc/<token-A>/stac/search?collections={colecao}&ids=item-stacit-1",
                "busca_b": f"{base}/svc/{tok_b}/stac/search?collections={colecao}&ids=item-stacit-1",
            }
        finally:
            proc_api.terminate()
            try:
                proc_api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc_api.kill()
                proc_api.wait(timeout=10)
    finally:
        proc_cog.terminate()
        try:
            proc_cog.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc_cog.kill()
            proc_cog.wait(timeout=10)


def _gdalinfo(url: str) -> subprocess.CompletedProcess:
    # a URL vai ENTRE ASPAS dentro da string de conexão: o driver STACIT separa a sintaxe
    # `STACIT:<arquivo>[:filtro=valor,...]` no caractere ':' e, sem as aspas, uma URL com porta
    # (http://127.0.0.1:45613/...) viraria 3+ tokens e o open falharia antes de qualquer HTTP
    # (medido com CPL_DEBUG=ON em GDAL 3.8.4; CSLT_HONOURSTRINGS preserva o token entre aspas).
    return subprocess.run(
        [GDALINFO, f'STACIT:"{url}"'], capture_output=True, text=True, timeout=180,
    )


def test_gdal_stacit_abre_a_busca(infra_stacit, medida):
    r = _gdalinfo(infra_stacit["busca_a"])
    assert r.returncode == 0, f"gdalinfo falhou:\n{r.stdout}\n{r.stderr}"
    assert f"Size is {COG_LADO}, {COG_LADO}" in r.stdout, r.stdout
    versao = subprocess.run([GDALINFO, "--version"], capture_output=True, text=True).stdout.strip()
    comando = (
        f"gdalinfo 'STACIT:\"{infra_stacit['busca_a_mascarada']}\"'  ({versao}; API por uvicorn em porta "
        f"livre + COG 256x256 servido por HTTP local, os dois levantados e derrubados pelo próprio teste)"
    )
    medida("L1-01-a")("gdal_stacit_abre_busca", 1, "0=falha,1=abriu", comando)


def test_gdal_stacit_com_token_de_b_nao_abre_item_de_a(infra_stacit):
    """O cliente GIS do inquilino B apontado para o id exato do item de A recebe busca vazia e o
    gdalinfo NÃO monta mosaico — o isolamento vale também fora da nossa suíte, no consumidor real."""
    r = _gdalinfo(infra_stacit["busca_b"])
    assert r.returncode != 0 or "Size is" not in r.stdout, (
        f"gdalinfo abriu dado de A com token de B:\n{r.stdout}\n{r.stderr}"
    )
