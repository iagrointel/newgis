"""Adversário de linha L1 imagens (parte 2, turno 9) — item `L1-02-i-ogc-api-tiles-e-maps`. Dois
achados:

1. Status inflado: este brief (linha-L1, parte 2) rastreia o item como "ENTREGUE". A PRÓPRIA
   evidência de fechamento (`tests/medidas/L1-02-i-ogc-api-tiles-e-maps.json`, campo
   `adversario_independente.valor`) registra o veredito do adversário independente que fechou o item
   como **"PARCIAL"**, não "ENTREGUE" — o mesmo padrão achado pelo adversário da linha irmã L2, parte
   2 (item citado por um status que a própria evidência commitada contradiz).
2. Portão: "`gdalinfo` abre via driver OGCAPI". Não há, em nenhuma medição ou teste committed do
   item, uma única menção ao driver OGCAPI do GDAL — só comparações byte-a-byte contra o XYZ/WMS
   feitas via `curl`/`requests`, nunca abrindo com GDAL de fato.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_ogc_tiles_gate.py -q -rxX`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEDIDA = ROOT / "tests" / "medidas" / "L1-02-i-ogc-api-tiles-e-maps.json"


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-i CAI: este brief rastreia o item como ENTREGUE, mas o proprio JSON de fechamento "
    "(campo adversario_independente.valor) registra o veredito 'PARCIAL' do adversario que fechou "
    "o item — status inflado em relacao a propria evidencia commitada (mesmo padrao da linha L2, "
    "parte 2: L2-09-a/L2-09-b/L2-08-b/L2-12-a)."
))
def test_status_do_item_bate_com_o_veredito_da_propria_evidencia():
    dados = json.loads(MEDIDA.read_text(encoding="utf-8"))
    veredito = dados["medidas"]["adversario_independente"]["valor"]
    assert veredito == "ENTREGUE", (
        f"o brief rastreia L1-02-i como ENTREGUE, mas a evidencia de fechamento diz "
        f"adversario_independente.valor={veredito!r}")


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-i CAI: portao exige 'gdalinfo abre via driver OGCAPI'; nenhuma medicao ou teste committed "
    "do item usa o driver OGCAPI do GDAL (so curl/requests + sha256 contra XYZ/WMS)."
))
def test_gdalinfo_via_driver_ogcapi_esta_provado():
    """Busca a string de conexão real do driver OGCAPI do GDAL (`OGCAPI:` — ver docs do GDAL), não
    apenas a substring 'ogcapi', que também aparece nas URIs de conformidade da spec
    ('ogcapi-tiles-1', 'ogcapi-common-1') e daria falso negativo ao achado."""
    dados = json.loads(MEDIDA.read_text(encoding="utf-8"))
    texto = json.dumps(dados, ensure_ascii=False)
    teste_texto = (ROOT / "tests" / "api" / "imagens" / "test_ogc_tiles.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "OGCAPI:" in texto or "OGCAPI:" in teste_texto, (
        "nenhuma referência à string de conexão do driver OGCAPI do GDAL ('OGCAPI:...') na "
        "evidência de fechamento nem nos testes do item — só há URIs de conformidade da spec "
        "('ogcapi-tiles-1'), que não é a mesma coisa que abrir com o driver GDAL")
