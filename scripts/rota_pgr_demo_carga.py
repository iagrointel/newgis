#!/usr/bin/env python3
"""Carga da rede de demonstração pgRouting (item L2-11-c-rota-matriz-isocrona).

Lê osrm/guarulhos.osm.pbf (ogr2ogr -> GeoJSONSeq das linhas com highway), monta a topologia em Python
(vértice = coordenada de nó OSM, compartilhada pelas vias que se cruzam com nó comum) e grava em
`plat.rota_pgr_demo` + `plat.rota_pgr_demo_vertices_pgr` (desenho da migração 20260918T1142). Custos em
segundos por app.rede.pgr.custos_s (mesma tabela de velocidades do OSRM car.lua).

Idempotente: TRUNCATE + COPY a cada execução. Roda com o DSN do ambiente (PLAT_DSN) como o papel da
aplicação (INSERT/TRUNCATE concedidos na migração) — NUNCA como superuser.

Uso:  set -a; source <env da trilha>; set +a; venv/bin/python scripts/rota_pgr_demo_carga.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import psycopg2  # noqa: E402

from app.rede.pgr import custos_s, haversine_m  # noqa: E402
from app.schema_ambiente import CursorSchemaAmbiente  # noqa: E402

PBF = RAIZ / "osrm" / "guarulhos.osm.pbf"


def _linhas_osm():
    proc = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSONSeq", "/vsistdout/", str(PBF), "lines",
         "-where", "highway IS NOT NULL", "-nlt", "PROMOTE_TO_MULTI"],
        capture_output=True, text=True, check=True,
    )
    for linha in proc.stdout.splitlines():
        linha = linha.strip()
        if linha:
            yield json.loads(linha)


def main() -> None:
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        raise SystemExit("PLAT_DSN ausente (rode com o env da trilha)")

    vertices: dict[tuple[float, float], int] = {}
    arestas = []  # (osm_id, highway, name, oneway, source, target, cost, reverse_cost, wkt)
    for feicao in _linhas_osm():
        geo = feicao.get("geometry") or {}
        props = feicao.get("properties") or {}
        highway = props.get("highway")
        if not highway:
            continue
        for linha_coords in (geo.get("coordinates") or []):
            if len(linha_coords) < 2:
                continue
            ids = []
            for lon, lat, *_ in linha_coords:
                chave = (round(lon, 7), round(lat, 7))
                if chave not in vertices:
                    vertices[chave] = len(vertices) + 1
                ids.append(vertices[chave])
            # uma aresta por TRECHO entre nós (não por via inteira): assim cruzamentos com nó OSM no
            # meio da via conectam de verdade — como o pgr_createTopology faria ao quebrar as linhas
            for i in range(len(ids) - 1):
                trecho = haversine_m(linha_coords[i][:2], linha_coords[i + 1][:2])
                if trecho == 0:
                    continue
                c, cr = custos_s(highway, props.get("oneway"), trecho)
                arestas.append(
                    (props.get("osm_id"), highway, props.get("name"), props.get("oneway"),
                     ids[i], ids[i + 1], c, cr,
                     f"LINESTRING({linha_coords[i][0]} {linha_coords[i][1]},{linha_coords[i + 1][0]} {linha_coords[i + 1][1]})")
                )

    con = psycopg2.connect(dsn, cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            # DELETE (não TRUNCATE): a matriz de privilégio da trilha dá SELECT/INSERT/UPDATE/DELETE ao
            # papel da aplicação, sem TRUNCATE — os ids explícitos dos vértices vêm da carga, não do serial
            cur.execute("DELETE FROM plat.rota_pgr_demo")
            cur.execute("DELETE FROM plat.rota_pgr_demo_vertices_pgr")
            import io

            buf = io.StringIO()
            for (lon, lat), vid in vertices.items():
                buf.write(f"{vid}\t{lon}\t{lat}\tSRID=4326;POINT({lon} {lat})\n")
            buf.seek(0)
            cur.copy_expert("COPY plat.rota_pgr_demo_vertices_pgr (id, x, y, the_geom) FROM STDIN", buf)
            nulo = "\\N"

            def _txt(v):
                if v is None:
                    return nulo
                return str(v).replace("\t", " ").replace("\n", " ").replace("\r", " ")

            buf = io.StringIO()
            for osm_id, highway, name, oneway, src, dst, c, cr, wkt in arestas:
                buf.write(
                    f"{_txt(osm_id)}\t{_txt(highway)}\t{_txt(name)}\t{_txt(oneway)}"
                    f"\t{src}\t{dst}\t{c}\t{cr}\tSRID=4326;{wkt}\n"
                )
            buf.seek(0)
            cur.copy_expert(
                "COPY plat.rota_pgr_demo "
                "(osm_id, highway, name, oneway, source, target, cost, reverse_cost, geom) FROM STDIN",
                buf,
            )
            cur.execute("SELECT count(*) AS n FROM plat.rota_pgr_demo")
            n = cur.fetchone()["n"]
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print(f"rede de demonstração carregada: {len(vertices)} vértices, {n} arestas")


if __name__ == "__main__":
    main()
