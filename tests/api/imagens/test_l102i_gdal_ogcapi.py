"""Item L1-02-i (OGC API – Tiles e Maps) — a cláusula do portão que o adversário de linha L1 (T9) achou
sem prova nenhuma: "`gdalinfo` abre via driver OGCAPI".

Até 17/09/2026 toda a evidência do item era `curl`/`requests` comparando bytes com o XYZ e o WMS. Isso
prova que a fachada responde o que o motor desenha, mas NÃO prova que um cliente de verdade consegue
abrir o serviço — e o driver OGCAPI do GDAL é exatamente o cliente que o QGIS ≥ 3.34 e o ArcGIS Pro
usam para "map tiles" de OGC API.

Aqui a prova é o próprio GDAL: um `uvicorn` de verdade (a `TestClient` é transporte ASGI em processo e
não é alcançável por um processo externo) e `gdalinfo OGCAPI:<landing>` em subprocesso. Se o driver não
entender o documento, o comando falha — não há como este teste passar por acidente.

Driver conferido nesta máquina: `gdalinfo --formats` lista `OGCAPI -raster,vector- (rov)` no GDAL 3.8.4.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[3]
def _porta_livre() -> int:
    """Porta escolhida pelo sistema, não cravada no arquivo.

    18/09/2026: aqui havia `PORTA = 8251`. Quando o pytest é morto pelo relógio do lançador (este
    arquivo sobe uvicorn e chama `gdalinfo`, e passa dos 600 s padrão), o uvicorn filho SOBREVIVE e
    continua segurando a porta; toda rodada seguinte pulava com "address already in use", e o portão
    do item lia esse pulo como se a cláusula não fosse verificável nesta máquina. Porta livre por
    rodada tira a colisão entre uma rodada e o cadáver da anterior — e entre duas rodadas paralelas,
    que o semáforo de `roda_teste.sh` permite."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORTA = _porta_livre()
BASE = f"http://127.0.0.1:{PORTA}"
MEDIDA = RAIZ / "tests" / "medidas" / "L1-02-i-ogc-api-tiles-e-maps.json"


def _tem_driver_ogcapi() -> bool:
    if not shutil.which("gdalinfo"):
        return False
    saida = subprocess.run(["gdalinfo", "--formats"], capture_output=True, text=True, check=False).stdout
    return "OGCAPI" in saida


pytestmark = pytest.mark.skipif(
    not _tem_driver_ogcapi(),
    reason="GDAL sem o driver OGCAPI nesta máquina — a cláusula do portão não é verificável aqui")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def token_ogc(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-ogcapi-gdal",
                                           "escopos": ["tiles:ler", "imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def servidor_vivo():
    """Mesmo padrão de `tests/api/imagens/test_estilo_raster_e2e.py::servidor_vivo` (uvicorn próprio,
    nunca `systemctl restart`): o GDAL é um processo separado e precisa de HTTP de verdade."""
    env = dict(os.environ)
    env.setdefault("PLAT_GIT_SHA", subprocess.run(
        ["git", "-C", str(RAIZ), "rev-parse", "--short=12", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip())
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORTA), "--host", "127.0.0.1"],
        cwd=str(RAIZ), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{BASE}/saude", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        else:
            saida = proc.stdout.read() if proc.stdout else ""
            proc.terminate()
            pytest.skip(f"uvicorn não respondeu em 30s na porta {PORTA}: {saida[-1500:]}")
        yield BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _gdalinfo(alvo: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gdalinfo", "-json", *extra, alvo],
                          capture_output=True, text=True, check=False, timeout=180)


def test_gdalinfo_abre_o_servico_pelo_driver_ogcapi(servidor_vivo, token_ogc, raster_demo):
    """A cláusula literal. `OGCAPI:<landing>` é a string de conexão do driver (doc do GDAL)."""
    alvo = f"OGCAPI:{BASE}/svc/{token_ogc['token']}/ogc/tiles"
    r = _gdalinfo(alvo)
    assert r.returncode == 0, f"gdalinfo falhou em {alvo}\nstdout={r.stdout[-1500:]}\nstderr={r.stderr[-1500:]}"
    doc = json.loads(r.stdout)
    assert doc.get("driverShortName") == "OGCAPI", doc.get("driverShortName")
    # o serviço anuncia as coleções como subdatasets; a nossa tem de estar entre elas
    texto = r.stdout
    assert raster_demo["item_id"] in texto, (
        f"o item {raster_demo['item_id']} não aparece no que o driver leu:\n{texto[-2000:]}")


def test_gdalinfo_abre_a_colecao_do_item_e_le_a_grade(servidor_vivo, token_ogc, raster_demo):
    """Abrir a COLEÇÃO (não só a landing) é o que o QGIS faz ao adicionar a camada: aqui o driver tem de
    devolver tamanho, sistema de referência e bandas."""
    item = raster_demo["item_id"]
    alvo = f"OGCAPI:{BASE}/svc/{token_ogc['token']}/ogc/tiles/collections/{item}"
    r = _gdalinfo(alvo)
    assert r.returncode == 0, f"gdalinfo falhou em {alvo}\nstdout={r.stdout[-1500:]}\nstderr={r.stderr[-1500:]}"
    doc = json.loads(r.stdout)
    assert doc.get("driverShortName") == "OGCAPI"
    assert doc["size"][0] > 0 and doc["size"][1] > 0, doc.get("size")
    assert doc.get("bands"), "o driver não enxergou banda nenhuma"
    wkt = json.dumps(doc.get("coordinateSystem") or {})
    assert re.search(r"3857|Pseudo-Mercator|WGS 84", wkt), wkt[:400]


def test_token_invalido_nao_abre_pelo_driver(servidor_vivo, raster_demo):
    """Controle: o driver não é uma porta lateral — sem token válido não abre."""
    r = _gdalinfo(f"OGCAPI:{BASE}/svc/plat_token_que_nao_existe/ogc/tiles")
    assert r.returncode != 0, f"gdalinfo abriu um serviço sem token válido: {r.stdout[-800:]}"


def test_a_medida_do_item_registra_a_prova_por_driver(servidor_vivo, token_ogc, raster_demo):
    """A evidência commitada tem de citar a string de conexão do driver — era isso que faltava para
    alguém conseguir REPRODUZIR a cláusula sem confiar no relato."""
    dados = json.loads(MEDIDA.read_text(encoding="utf-8"))
    texto = json.dumps(dados, ensure_ascii=False)
    assert "OGCAPI:" in texto, "a medida do item não registra a prova pelo driver OGCAPI do GDAL"
