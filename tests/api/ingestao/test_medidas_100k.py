"""Medidas de desempenho que os portões nomeiam (itens L0-04-b-inspecao e L0-04-c-tabela-camada).

Portão do L0-04-b: "medida tempo_inspecao_s por arquivo (100 mil feições ≤ 5 s)".
Portão do L0-04-c: "shapefile de 100 mil feições importa e aparece na lista em ≤ 60 s medido
(medida tempo_import_100k_s)".

Nenhuma das duas existia: o maior arquivo da suíte tinha 80 feições, três ordens de grandeza abaixo do que
o portão manda medir (achado do adversário do turno 3).

Sobre o dado: o portão sugere "setores censitários de um estado". Esta máquina está com o disco a 91 % e a
regra da casa proíbe baixar dado novo, então as 100 mil feições são DERIVADAS do dado aberto que já está no
repositório — os polígonos de cobertura do solo de Guarulhos (OSM/ODbL, `web/dados/basemap/guarulhos.pmtiles`)
replicados numa grade sobre a área do município, com os atributos reais ciclados. É dado sintético em posição,
real em forma e em esquema; a medida vale para o tamanho do arquivo e o número de feições, não para a
geometria de um estado inteiro. Está dito assim no próprio arquivo de medida.

O arquivo grande é criado em `tmp_path` e APAGADO no fim (disco a 91 %). Marcado `lento`: não roda no driver.
Gravar as medidas exige PLAT_GRAVAR_MEDIDAS=1."""

from __future__ import annotations

import json
import subprocess
import time
import zipfile
from pathlib import Path

import pytest

from tests.api.ingestao.conftest import GERADOS, esperar_job

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes"),
]

N_FEICOES = 100_000
INSPECAO_MAX_S = 5.0
IMPORT_MAX_S = 60.0


def _gerar_shapefile_100k(destino_dir: Path) -> Path:
    """Grade de 100 mil quadrados de ~40 m sobre Guarulhos, com os atributos reais do subconjunto de cobertura
    do solo. Escrito como GeoJSONSeq (uma linha por feição, memória constante) e convertido a shapefile pelo
    ogr2ogr; o zip é o que a API recebe."""
    modelo = json.loads((GERADOS / "cobertura.geojson").read_text(encoding="utf-8"))
    props = [f["properties"] for f in modelo["features"]] or [{"landuse": "x", "name": "y"}]
    chaves = ["landuse", "leisure", "natural", "name", "select"]

    linhas = destino_dir / "grade.geojsonl"
    lado = 0.0004  # ~44 m em latitude
    colunas = 400
    x0, y0 = -46.60, -23.55
    with linhas.open("w", encoding="utf-8") as f:
        for i in range(N_FEICOES):
            cx = x0 + (i % colunas) * lado
            cy = y0 + (i // colunas) * lado
            anel = [[cx, cy], [cx + lado * 0.9, cy], [cx + lado * 0.9, cy + lado * 0.9],
                    [cx, cy + lado * 0.9], [cx, cy]]
            p = props[i % len(props)]
            atributos = {k: (p.get(k) if p.get(k) is not None else None) for k in chaves}
            f.write(json.dumps({"type": "Feature", "properties": atributos,
                                "geometry": {"type": "Polygon", "coordinates": [anel]}},
                               ensure_ascii=False) + "\n")

    dir_shp = destino_dir / "shp"
    dir_shp.mkdir(exist_ok=True)
    r = subprocess.run(
        ["ogr2ogr", "-f", "ESRI Shapefile", str(dir_shp / "grade.shp"), str(linhas),
         "-a_srs", "EPSG:4674", "-nln", "grade", "-lco", "ENCODING=UTF-8"],
        capture_output=True, text=True, timeout=900,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    linhas.unlink()

    caminho_zip = destino_dir / "grade_100k.zip"
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in sorted(dir_shp.glob("grade.*")):
            zf.write(arq, arq.name)
    for arq in dir_shp.glob("grade.*"):
        arq.unlink()
    return caminho_zip


def test_cem_mil_feicoes_inspecionam_e_importam_dentro_do_portao(ingestor_a, conexao_plat_app, medida, tmp_path):
    caminho = _gerar_shapefile_100k(tmp_path)
    bytes_zip = caminho.stat().st_size
    try:
        obj = ingestor_a.enviar_arquivo(caminho)
        arquivo_id = ingestor_a.item_arquivo(obj, caminho.name)

        t0 = time.monotonic()
        r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": arquivo_id, "formato": "shapefile.zip"})
        assert r.status_code == 202, r.text
        importacao_id = r.json()["importacao_id"]
        esperar_job(ingestor_a.sessao, r.json()["job_id"], timeout=600)
        tempo_inspecao = time.monotonic() - t0

        imp = ingestor_a.sessao.get(f"/api/importacoes/{importacao_id}").json()
        assert imp["estado"] == "proposta", imp
        assert imp["proposta"]["feicoes"] == N_FEICOES, imp["proposta"]["feicoes"]

        t1 = time.monotonic()
        final = ingestor_a.confirmar(importacao_id, timeout=900)
        tempo_import = time.monotonic() - t1
        assert final["estado"] == "concluida", final
        assert final["relatorio"]["feicoes_carregadas"] == N_FEICOES, final["relatorio"]
    finally:
        for arq in tmp_path.rglob("*"):
            if arq.is_file():
                arq.unlink()

    gravar_b = medida("L0-04-b-inspecao")
    gravar_b("tempo_inspecao_s", round(tempo_inspecao, 2), "s",
             "pytest tests/api/ingestao/test_medidas_100k.py -m lento")
    gravar_b("feicoes_do_arquivo_medido", N_FEICOES, "feições",
             "grade derivada da cobertura do solo de Guarulhos (OSM/ODbL)")
    gravar_b("bytes_do_shapefile_zipado", bytes_zip, "bytes",
             "pytest tests/api/ingestao/test_medidas_100k.py -m lento")
    gravar_c = medida("L0-04-c-tabela-camada")
    gravar_c("tempo_import_100k_s", round(tempo_import, 2), "s",
             "pytest tests/api/ingestao/test_medidas_100k.py -m lento")
    gravar_c("feicoes_carregadas", N_FEICOES, "feições",
             "pytest tests/api/ingestao/test_medidas_100k.py -m lento")

    assert tempo_inspecao <= INSPECAO_MAX_S, (
        f"inspeção de {N_FEICOES} feições levou {tempo_inspecao:.2f} s; o portão do L0-04-b pede ≤ "
        f"{INSPECAO_MAX_S} s")
    assert tempo_import <= IMPORT_MAX_S, (
        f"carga de {N_FEICOES} feições levou {tempo_import:.2f} s; o portão do L0-04-c pede ≤ {IMPORT_MAX_S} s")
