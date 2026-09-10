"""Cláusula do portão: "ST_Transform e pyproj e proj4js dão a mesma coordenada em 31982 para 20 pontos
(<= 0,01 m)" — item L2-17-crs-transformacoes. SIRGAS2000 geográfico (4674) <-> SIRGAS2000/UTM 22S
(31982) é projeção pura (sem grade de datum): as três ferramentas usam a MESMA definição PROJ
(`+proj=utm +zone=22 +south +ellps=GRS80`), então bater a <= 1 cm é esperado — o teste prova que as três
integrações desta plataforma (backend Python via pyproj, banco via PostGIS/ST_Transform, e navegador via
proj4js com a definição servida por `/api/crs/31982.proj4`) realmente usam a mesma definição, e não uma
cópia digitada à mão em algum dos três lugares que divergiu."""

import json
import math
import subprocess
from pathlib import Path

from pyproj import Transformer

from app.crs import registro

RAIZ = Path(__file__).resolve().parents[2]
NODE = "node"
PROJ4_JS = RAIZ / "web" / "vendor" / "proj4-2.15.0.js"
TOLERANCIA_M = 0.01

# 20 pontos espalhados pelo alcance de SIRGAS2000/UTM 22S (48°W-54°W; achado no bounds do próprio EPSG,
# ver test_crs_registro.py) — não são pontos oficiais do IBGE (essa exigência é só da cláusula da grade,
# em test_crs_grade_ibge.py); aqui o que importa é cobrir uma malha de coordenadas dentro da zona.
PONTOS_4674 = [(-51.0 + 0.15 * i, -20.0 - 0.2 * i) for i in range(20)]


def _via_pyproj():
    t = Transformer.from_crs(4674, 31982, always_xy=True)
    return [t.transform(lon, lat) for lon, lat in PONTOS_4674]


def _via_postgis(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT ST_X(g), ST_Y(g) FROM ("
            "  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(x, y), 4674), 31982) AS g"
            "  FROM unnest(%s::double precision[], %s::double precision[]) AS t(x, y)"
            ") s",
            ([p[0] for p in PONTOS_4674], [p[1] for p in PONTOS_4674]),
        )
        linhas = cur.fetchall()
    # RealDictCursor (CursorSchemaAmbiente) -> cada linha é um dict com chaves 'st_x'/'st_y' em minúsculo
    return [(float(r["st_x"]), float(r["st_y"])) for r in linhas]


def _via_proj4js():
    # as MESMAS definições que /api/crs/{epsg}.proj4 serve (app.crs.registro.proj4) — nunca EPSG:4326
    # "de memória" do proj4js, que é WGS84 e diverge de SIRGAS2000 (EPSG:4674) por centímetros a nível
    # global; sem isto o teste mediria a diferença de datum, não a paridade da projeção.
    proj4_4674 = registro.proj4(4674)
    proj4_31982 = registro.proj4(31982)
    script = (
        f"const proj4 = require({json.dumps(str(PROJ4_JS))});"
        f"proj4.defs('EPSG:4674', {json.dumps(proj4_4674)});"
        f"proj4.defs('EPSG:31982', {json.dumps(proj4_31982)});"
        f"const pontos = {json.dumps(PONTOS_4674)};"
        "const out = pontos.map(([lon, lat]) => proj4('EPSG:4674', 'EPSG:31982', [lon, lat]));"
        "console.log(JSON.stringify(out));"
    )
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    return [tuple(p) for p in json.loads(r.stdout)]


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_pyproj_postgis_proj4js_dao_a_mesma_coordenada_em_31982(conexao_plat_app, medida):
    pyproj_out = _via_pyproj()
    postgis_out = _via_postgis(conexao_plat_app)
    proj4js_out = _via_proj4js()
    assert len(pyproj_out) == len(postgis_out) == len(proj4js_out) == 20

    maior_pyproj_postgis = 0.0
    maior_pyproj_proj4js = 0.0
    for a, b, c in zip(pyproj_out, postgis_out, proj4js_out, strict=True):
        maior_pyproj_postgis = max(maior_pyproj_postgis, _dist(a, b))
        maior_pyproj_proj4js = max(maior_pyproj_proj4js, _dist(a, c))
    assert maior_pyproj_postgis <= TOLERANCIA_M, maior_pyproj_postgis
    assert maior_pyproj_proj4js <= TOLERANCIA_M, maior_pyproj_proj4js
    medida("L2-17-crs-transformacoes")(
        "paridade_31982_maior_diferenca_pyproj_x_postgis_m", round(maior_pyproj_postgis, 6), "m",
        "venv/bin/pytest tests/unit/test_crs_paridade_31982.py",
    )
    medida("L2-17-crs-transformacoes")(
        "paridade_31982_maior_diferenca_pyproj_x_proj4js_m", round(maior_pyproj_proj4js, 6), "m",
        "venv/bin/pytest tests/unit/test_crs_paridade_31982.py",
    )
