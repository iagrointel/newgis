"""Gera o dado aberto usado pelos testes do item L3-06-criterios-de-feicao, a partir do mapa-base que já está
no repositório (`web/dados/basemap/guarulhos.pmtiles`, OpenStreetMap © colaboradores, ODbL 1.0 — proveniência
em `web/dados/basemap/PROVENIENCIA.md`). Não baixa nada (disco a 98 %) e não abre banco.

Saída (versionada, porque os testes têm de rodar sem GDAL e sem rede):
- `l3_06_feicoes.geojson`  — 1.000 PONTOS: centróide de edificação OSM, com o atributo numérico `area_m2`
  (área do polígono medida em EPSG:31983, SIRGAS 2000 / UTM 23S, a zona de Guarulhos) e `id` estável;
- `l3_06_camada_pontos.geojson` — os lugares OSM do mesmo recorte (camada de outra origem, usada pelos
  critérios de contagem em raio e de distância ao mais próximo).

Uso: `venv/bin/python tests/dados/gerar_l3_06.py` (exige ogr2ogr do GDAL, como `tests/dados/gerar.py`).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PMTILES = RAIZ / "web" / "dados" / "basemap" / "guarulhos.pmtiles"
AQUI = Path(__file__).resolve().parent
N_FEICOES = 1_000
SRID_TRABALHO = 31983  # SIRGAS 2000 / UTM 23S — zona do recorte


def _ogr2ogr(*args: str) -> None:
    r = subprocess.run(["ogr2ogr", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ogr2ogr falhou: {' '.join(args)}\n{r.stderr}")


def gerar() -> None:
    import geopandas as gpd

    with tempfile.TemporaryDirectory() as tmp:
        edif = Path(tmp) / "edificacoes.geojson"
        _ogr2ogr("-f", "GeoJSON", str(edif), str(PMTILES), "edificacoes", "-t_srs", "EPSG:4326",
                 "-dialect", "OGRSQL", "-sql",
                 f"SELECT mvt_id FROM edificacoes ORDER BY mvt_id LIMIT {N_FEICOES}")
        g = gpd.read_file(edif)
        g = g.to_crs(epsg=SRID_TRABALHO)
        area = g.geometry.area.round(2)
        centro = g.geometry.representative_point().to_crs(epsg=4326)
        feicoes = [
            {"type": "Feature", "id": f"e{k:04d}",
             "properties": {"id": f"e{k:04d}", "area_m2": float(a)},
             "geometry": {"type": "Point", "coordinates": [round(p.x, 6), round(p.y, 6)]}}
            for k, (a, p) in enumerate(zip(area, centro, strict=True))
        ]
        _escrever(AQUI / "l3_06_feicoes.geojson", feicoes)

        lugares = Path(tmp) / "lugares.geojson"
        _ogr2ogr("-f", "GeoJSON", str(lugares), str(PMTILES), "lugares", "-t_srs", "EPSG:4326",
                 "-dialect", "OGRSQL", "-sql", "SELECT mvt_id, place FROM lugares ORDER BY mvt_id")
        gl = gpd.read_file(lugares)
        pontos = [
            {"type": "Feature", "id": f"p{k:04d}",
             "properties": {"id": f"p{k:04d}", "place": (None if r.place is None else str(r.place))},
             "geometry": {"type": "Point", "coordinates": [round(pt.x, 6), round(pt.y, 6)]}}
            for k, (r, pt) in enumerate(zip(gl.itertuples(), gl.geometry.representative_point(), strict=True))
        ]
        _escrever(AQUI / "l3_06_camada_pontos.geojson", pontos)


def _escrever(caminho: Path, feicoes: list[dict]) -> None:
    corpo = {"type": "FeatureCollection",
             "fonte": "OpenStreetMap © colaboradores, ODbL 1.0 (recorte de Guarulhos-SP em "
                      "web/dados/basemap/guarulhos.pmtiles)",
             "crs_dos_valores": f"area_m2 medida em EPSG:{SRID_TRABALHO}",
             "features": feicoes}
    caminho.write_text(json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
    print(f"{caminho.name}: {len(feicoes)} feições")


if __name__ == "__main__":
    gerar()
