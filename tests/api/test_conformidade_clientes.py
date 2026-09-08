"""Clientes de terceiros contra os serviços desta plataforma (item L2-04-j).

O que este arquivo prova, com cliente de verdade e não com pedido `curl` escrito por nós:

  owslib  — biblioteca cliente OGC em Python, instalada na venv desta máquina. Lê o
            `GetCapabilities` do nosso WFS 2.0, monta o catálogo de tipos e faz um `GetFeature`
            pelo próprio código dela. Se a nossa saída não fosse WFS 2.0 de verdade, o parser
            dela levantaria exceção — é essa a prova.
  WMS     — não existe rota WMS neste repositório (o item que a constrói ainda não foi feito).
            O teste mede a AUSÊNCIA (404), para que a linha da matriz de conformidade diga
            "fora" com evidência, e não por afirmação.

QGIS e o cliente Python `arcgis` NÃO estão instalados nesta máquina, e nenhum dos dois cabe no
orçamento de disco desta trilha. As linhas da matriz que dependem deles ficam "nao_medido" com o
motivo medido aqui (`test_clientes_ausentes_sao_medidos_nao_presumidos`), nunca "suportado".

O servidor é um uvicorn PRÓPRIO desta trilha, na porta 8326, subido e derrubado pelo PID — owslib
fala HTTP de verdade e não aceita o cliente de teste em memória."""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_diretorio_esri import Camada, _sufixo

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 8326
BASE = f"http://127.0.0.1:{PORTA}"


def _porta_ocupada(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", porta)) == 0


@pytest.fixture(scope="module")
def servidor(env):
    """uvicorn da trilha em :8326. Nunca toca a unidade `plat-api`; morre pelo PID no fim."""
    if _porta_ocupada(PORTA):
        pytest.skip(f"porta {PORTA} já ocupada nesta máquina — outra trilha subiu servidor nela")
    proc = subprocess.Popen(
        [str(RAIZ / "venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app",
         "--port", str(PORTA), "--log-level", "warning"],
        cwd=str(RAIZ), env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
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
    camada = Camada(env, sessao_a, f"{PREFIXO_TESTE} camada conformidade {_sufixo()}")
    r = sessao_a.post("/api/tokens", json={
        "nome": f"{PREFIXO_TESTE}-conf-{_sufixo()}", "escopos": ["catalogo:ler", "camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield camada, tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")
    camada.apagar()


def _apontar_operacoes_para(wfs, url: str) -> None:
    """ACHADO deste item: um cliente OGC de verdade NÃO reusa a URL que você digitou — ele lê, do
    próprio GetCapabilities, o endereço de cada operação (`ows:OperationsMetadata`). Nós publicamos ali
    `PLAT_URL_PUBLICA`, que em produção é o domínio do inquilino e nesta trilha é um domínio que não
    resolve. Reapontar as operações para o endereço realmente alcançável é o que qualquer cliente atrás
    de proxy reverso faz — e deixa registrado que o endereço publicado é configuração, não código."""
    for operacao in wfs.operations:
        for metodo in getattr(operacao, "methods", []):
            if isinstance(metodo, dict):
                metodo["url"] = url


def test_owslib_le_o_getcapabilities_do_nosso_wfs_2_0(servidor, camada_e_token):
    """O parser de um cliente OGC de terceiros aceita o nosso GetCapabilities e acha o tipo."""
    from owslib.wfs import WebFeatureService

    camada, token = camada_e_token
    wfs = WebFeatureService(url=f"{servidor}/wfs/{camada.item_id}", version="2.0.0",
                            headers={"Authorization": f"Bearer {token}"})
    assert wfs.identification.type in ("WFS", "OGC WFS"), wfs.identification.type
    tipos = list(wfs.contents)
    assert len(tipos) == 1, tipos
    assert "GetFeature" in [op.name for op in wfs.operations], [op.name for op in wfs.operations]


def test_owslib_faz_getfeature_e_devolve_as_feicoes_da_camada(servidor, camada_e_token):
    """`GetFeature` montado pelo próprio owslib; a contagem bate com as feições semeadas na tabela."""
    from owslib.wfs import WebFeatureService

    camada, token = camada_e_token
    wfs = WebFeatureService(url=f"{servidor}/wfs/{camada.item_id}", version="2.0.0",
                            headers={"Authorization": f"Bearer {token}"})
    _apontar_operacoes_para(wfs, f"{servidor}/wfs/{camada.item_id}")
    tipo = list(wfs.contents)[0]
    corpo = wfs.getfeature(typename=[tipo], outputFormat="application/json").read()
    import json as _json

    dados = _json.loads(corpo)
    assert dados["type"] == "FeatureCollection", dados.get("type")
    assert len(dados["features"]) == 2, len(dados["features"])


def test_nao_existe_rota_wms_neste_repositorio(servidor, camada_e_token):
    """A linha 'WMS' da matriz é 'fora' por MEDIDA: a rota não existe (o item que a constrói é outro)."""
    camada, token = camada_e_token
    r = requests.get(f"{servidor}/wms/{camada.item_id}",
                     params={"SERVICE": "WMS", "REQUEST": "GetCapabilities", "token": token}, timeout=20)
    assert r.status_code == 404, (r.status_code, r.text[:200])
    caminhos = requests.get(f"{servidor}/api/openapi.json", timeout=20).json()["paths"]
    assert not [p for p in caminhos if "wms" in p.lower() or "wmts" in p.lower()], "surgiu rota WMS/WMTS"


def test_ogc_api_features_responde_ao_cliente_http_puro(servidor, camada_e_token):
    """Pouso + conformance + items pela porta HTTP real (o que QGIS faz ao 'Adicionar camada OGC API')."""
    camada, token = camada_e_token
    base = f"{servidor}/ogc/features/{camada.item_id}"
    r = requests.get(f"{base}/conformance", params={"token": token}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    assert any("ogcapi-features" in c for c in r.json()["conformsTo"]), r.json()
    r = requests.get(f"{base}/collections/0/items", params={"token": token, "limit": 5}, timeout=20)
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection", r.text[:200]


def test_featureserver_responde_ao_cliente_http_puro(servidor, camada_e_token):
    """Descritor + query pela porta HTTP real, com token na URL (forma que o protocolo Esri usa)."""
    camada, token = camada_e_token
    base = f"{servidor}/rest/services/{camada.item_id}/FeatureServer"
    r = requests.get(base, params={"f": "json", "token": token}, timeout=20)
    assert r.status_code == 200 and r.json()["layers"][0]["id"] == 0, r.text[:200]
    r = requests.get(f"{base}/0/query", params={"where": "1=1", "returnCountOnly": "true",
                                                "f": "json", "token": token}, timeout=20)
    assert r.status_code == 200 and r.json()["count"] == 2, r.text[:200]


def test_clientes_ausentes_sao_medidos_nao_presumidos():
    """QGIS e o pacote Python `arcgis` não existem nesta máquina — a matriz tem de dizer isso com medida.

    Este teste é a medida: se um dia qualquer um dos dois for instalado, ele reprova e obriga a
    matriz a sair de 'nao_medido' e passar a exercitar o cliente de verdade."""
    assert shutil.which("qgis_process") is None, "qgis_process apareceu: a matriz tem de medir o QGIS"
    assert shutil.which("qgis") is None, "qgis apareceu: a matriz tem de medir o QGIS"
    assert importlib.util.find_spec("arcgis") is None, "pacote arcgis apareceu: a matriz tem de exercitá-lo"
    assert importlib.util.find_spec("owslib") is not None, "owslib sumiu da venv: as linhas OGC ficam sem prova"
    assert sys.version_info[:2] >= (3, 11)
