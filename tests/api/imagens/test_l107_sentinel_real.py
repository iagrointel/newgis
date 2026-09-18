"""Item L1-07 — a cláusula do portão que pedia cenas REAIS: "mosaico de >= 6 cenas Sentinel-2 abertas
(recortes pequenos) registrado pela tela; tile do mosaico em z 8-14 medido (frio/quente) em
`tests/medidas/L1-07.json`".

A medição que existia usava uma grade SINTÉTICA 3x2 gerada em memória. Ela prova o compositor — e é a
prova certa para isso — mas não prova que o produto abre cena de satélite de verdade, com a geometria,
o tipo de dado e a escala de uma. Aqui as cenas são reais: catálogo público Element84 (sem chave) e
bucket público `sentinel-cogs`, de onde se lê apenas uma JANELA de 512x512 px de cada cena (a cena
inteira tem cerca de 1 GB; o portão pede "recortes pequenos").

O teste PULA quando não há rede — o portão não é verificável sem catálogo, e fingir que é seria pior.
Para regravar `tests/medidas/L1-07.json`, rode com `PLAT_GRAVAR_MEDIDAS=1`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "scripts"))
MEDIDA = RAIZ / "tests" / "medidas" / "L1-07.json"
LON, LAT = -47.90, -15.79
MINIMO_DE_CENAS = 6


def _tem_catalogo() -> bool:
    try:
        req = urllib.request.Request(
            "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a", method="GET")
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


pytestmark = pytest.mark.skipif(
    not _tem_catalogo(),
    reason="sem alcance ao catálogo público Element84 — a cláusula de cenas Sentinel-2 abertas não é "
           "verificável nesta máquina agora")


@pytest.fixture(scope="module")
def bancada(tenant_id_a, sessao_a):
    """Busca, recorta, semeia e mede. Apaga tudo no fim."""
    import bench_l107_sentinel as bench

    from tests.api.imagens.apoio_mosaico import apagar_grade

    meia = bench.LADO_PX * 10 / 2 / 111_000
    bbox = [LON - meia, LAT - meia, LON + meia, LAT + meia]
    cenas = bench.buscar_cenas(bbox, "2026-03-01T00:00:00Z", "2026-09-01T00:00:00Z", MINIMO_DE_CENAS)
    dados = bench.semear(tenant_id_a, "demo", cenas, LON, LAT)
    try:
        yield dados
    finally:
        apagar_grade(tenant_id_a, dados)


@pytest.fixture(scope="module")
def token_l107(sessao_a):
    r = sessao_a.post("/api/tokens", json={
        "nome": "zt-l107-sentinel", "escopos": ["imagens:escrever", "imagens:ler", "tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def test_seis_cenas_sentinel2_abertas_viram_um_mosaico_e_o_ladrilho_e_medido(bancada, token_l107):
    import bench_l107_sentinel as bench
    from fastapi.testclient import TestClient

    from app.main import app

    assert len(bancada["itens"]) >= MINIMO_DE_CENAS, bancada["itens"]
    ids = [i["cena"] for i in bancada["itens"]]
    assert all(c.startswith("S2") and c.endswith("L2A") for c in ids), ids
    assert len({i["datetime"][:10] for i in bancada["itens"]}) >= MINIMO_DE_CENAS, (
        "as cenas têm de ser de datas distintas, senão o mosaico compõe duplicatas do mesmo dia")

    with TestClient(app, base_url="http://testserver") as cliente:
        resultado = bench.medir(bancada, (8, 10, 12, 13, 14), cliente, token_l107["token"])

    for z, m in resultado["por_zoom"].items():
        assert m["ms_frio"] > 0 and m["ms_quente_mediana"] > 0, (z, m)
        assert m["status_frio"] < 500, (
            f"{z}: o ladrilho devolveu erro de SERVIDOR sobre cena Sentinel-2 real — {m}")
    servidos = [z for z, m in resultado["por_zoom"].items() if m["status_frio"] == 200]
    assert servidos, f"nenhum zoom devolveu ladrilho com pixel: {resultado['por_zoom']}"

    if os.environ.get("PLAT_GRAVAR_MEDIDAS") == "1":
        saida = bench.montar_saida(bancada, resultado, "demo", LON, LAT)
        MEDIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def test_a_medida_commitada_e_de_cena_sentinel2_aberta_e_nao_sintetica():
    """O que o portão do adversário confere: o arquivo com o nome literal existe e a medição nele não
    é de dado sintético."""
    assert MEDIDA.exists(), "tests/medidas/L1-07.json (nome literal do portão) não existe"
    dados = json.loads(MEDIDA.read_text(encoding="utf-8"))
    comandos = " ".join(v.get("comando", "") for v in dados["medidas"].values())
    assert "sentinel" in comandos.lower(), comandos[:300]
    assert "sintétic" not in comandos.lower() and "sintetic" not in comandos.lower(), comandos[:300]
    assert len(dados["cenas"]) >= MINIMO_DE_CENAS, dados["cenas"]
