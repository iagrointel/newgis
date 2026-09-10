"""Item L2-01-f-navegacao-medicao-coordenadas, oráculo = PostGIS desta instalação (conexao_plat_app):
  * 5 segmentos entre vértices fixos (coordenadas aproximadas de estações RBMC/IBGE, gravadas neste arquivo) medidos
    por web/js/mapa/medicao.js (Vincenty, GRS80) com erro ≤ 0,1 % contra ST_Length(geography);
  * 3 polígonos com erro ≤ 0,1 % contra ST_Area(geography) (projeção equivalente local do proj4);
  * conversão de 5 pontos para EPSG:31982 pelo proj4 vendorizado com erro ≤ 0,01 m contra ST_Transform;
  * as definições PROJ de web/js/mapa/crs.js são as de spatial_ref_sys, texto a texto;
  * 'ir para' aceita as três formas do portão e recusa texto malformado (refutação).
Os módulos rodam no node com o proj4 do vendor injetado (mesmo arquivo que o navegador carrega)."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# estações da RBMC (IBGE) — coordenadas aproximadas em graus (SIRGAS 2000); servem de vértices conhecidos; a
# verdade da medida é o PostGIS, não estes números
VERTICES = {
    "BRAZ": (-47.877869, -15.947475), "POAL": (-51.119810, -30.074020), "RECF": (-34.951370, -8.050890),
    "MANA": (-60.000070, -3.116310), "CUIB": (-56.069900, -15.555300), "SALV": (-38.516500, -12.974900),
    "BELE": (-48.462600, -1.408700), "CHPI": (-44.985200, -22.687100), "UFPR": (-49.230900, -25.448400),
}
SEGMENTOS = [("BRAZ", "POAL"), ("RECF", "SALV"), ("MANA", "BELE"), ("CUIB", "CHPI"), ("UFPR", "POAL")]
POLIGONOS = [
    ["BRAZ", "CUIB", "CHPI"],
    ["RECF", "SALV", "BRAZ", "BELE"],
    [(-46.60, -23.50), (-46.50, -23.50), (-46.50, -23.60), (-46.60, -23.60)],
]
PONTOS_31982 = [(-51.1198, -30.0740), (-49.2309, -25.4484), (-53.0, -27.0), (-48.0001, -33.7), (-52.5, -20.0)]

CABECALHO = """
  import { createRequire } from 'node:module';
  const require = createRequire(import.meta.url);
  const proj4 = require('./web/vendor/proj4-2.22.0.js');
  const crs = await import('./web/js/mapa/crs.js');
  crs.usarProj4(proj4);
  const med = await import('./web/js/mapa/medicao.js');
"""


def executar_js(codigo: str):
    p = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _coord(v):
    return VERTICES[v] if isinstance(v, str) else v


def test_distancia_de_5_segmentos_erro_ate_0_1_por_cento_contra_st_length(conexao_plat_app):
    pares = [[_coord(a), _coord(b)] for a, b in SEGMENTOS]
    js = executar_js(CABECALHO + f"console.log(JSON.stringify({json.dumps(pares)}"
                     ".map(([a, b]) => med.distancia(a, b))));")
    with conexao_plat_app.cursor() as cur:
        for (a, b), nosso in zip(pares, js, strict=True):
            cur.execute("SELECT ST_Length(ST_MakeLine(ST_SetSRID(ST_MakePoint(%s, %s), 4326), "
                        "ST_SetSRID(ST_MakePoint(%s, %s), 4326))::geography) AS m", (*a, *b))
            ref = float(cur.fetchone()["m"])
            erro = abs(nosso - ref) / ref
            assert erro <= 0.001, (a, b, nosso, ref, erro)
            assert ref > 100_000  # segmentos de centenas de km: o erro esférico (0,3-0,5 %) reprovaria aqui


def test_area_de_3_poligonos_erro_ate_0_1_por_cento_contra_st_area(conexao_plat_app):
    aneis = [[_coord(v) for v in pol] for pol in POLIGONOS]
    js = executar_js(CABECALHO + f"""
      const aneis = {json.dumps(aneis)};
      console.log(JSON.stringify({{areas: aneis.map((a) => med.area(a)), metodo: med.metodoArea(),
        esfera: aneis.map((a) => med.areaEsferica(a))}}));""")
    assert js["metodo"].startswith("elipsoide")
    with conexao_plat_app.cursor() as cur:
        for anel, nosso, esf in zip(aneis, js["areas"], js["esfera"], strict=True):
            wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in anel + [anel[0]]) + "))"
            cur.execute("SELECT ST_Area(ST_GeomFromText(%s, 4326)::geography) AS a", (wkt,))
            ref = float(cur.fetchone()["a"])
            erro = abs(nosso - ref) / ref
            assert erro <= 0.001, (anel, nosso, ref, erro, "esfera:", abs(esf - ref) / ref)


def test_coordenada_em_31982_bate_com_st_transform_ate_1_cm(conexao_plat_app):
    js = executar_js(CABECALHO + f"console.log(JSON.stringify({json.dumps(PONTOS_31982)}"
                     ".map(([lon, lat]) => crs.converter(lon, lat, 31982))));")
    with conexao_plat_app.cursor() as cur:
        for (lon, lat), (x, y) in zip(PONTOS_31982, js, strict=True):
            cur.execute("SELECT ST_X(g) AS x, ST_Y(g) AS y "
                        "FROM ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 31982) g", (lon, lat))
            r = cur.fetchone()
            assert abs(x - float(r["x"])) <= 0.01 and abs(y - float(r["y"])) <= 0.01, (lon, lat, x, y, r)
    # ida e volta
    volta = executar_js(CABECALHO + f"console.log(JSON.stringify({json.dumps(js)}"
                        ".map(([x, y]) => crs.paraLonLat(x, y, 31982))));")
    for (lon, lat), (lon2, lat2) in zip(PONTOS_31982, volta, strict=True):
        assert abs(lon - lon2) < 1e-7 and abs(lat - lat2) < 1e-7


def test_definicoes_proj_de_crs_js_sao_as_de_spatial_ref_sys(conexao_plat_app):
    js = executar_js(CABECALHO + "console.log(JSON.stringify(crs.CRS.map((c) => [c.srid, c.proj])));")
    with conexao_plat_app.cursor() as cur:
        for srid, proj in js:
            cur.execute("SELECT proj4text FROM spatial_ref_sys WHERE srid = %s", (srid,))
            r = cur.fetchone()
            assert r is not None, srid
            assert r["proj4text"].strip() == proj.strip(), (srid, r["proj4text"], proj)


@pytest.mark.parametrize("texto, esperado", [
    ("−23,55 −46,63", {"lat": -23.55, "lon": -46.63, "formato": "decimal"}),
    ("-23.55, -46.63", {"lat": -23.55, "lon": -46.63, "formato": "decimal"}),
    ("23°33′S 46°38′W", {"lat": -23.55, "lon": -(46 + 38 / 60), "formato": "gms"}),
    ("23°29'36\"S 46°35'34\"W", {"lat": -(23 + 29 / 60 + 36 / 3600), "lon": -(46 + 35 / 60 + 34 / 3600),
                                 "formato": "gms"}),
    ("333.000 7.394.000 EPSG:31983", {"formato": "projetado", "srid": 31983}),
    ("333000,5 7394000 EPSG:31983", {"formato": "projetado", "srid": 31983}),
])
def test_ir_para_aceita_as_formas_do_portao(texto, esperado, conexao_plat_app):
    js = executar_js(CABECALHO + f"""
      const b = await import('./web/js/mapa/busca.js');
      console.log(JSON.stringify(b.interpretarCoordenada({json.dumps(texto)})));""")
    assert js is not None, texto
    for chave, valor in esperado.items():
        if isinstance(valor, float):
            assert abs(js[chave] - valor) < 1e-6, (texto, chave, js[chave], valor)
        else:
            assert js[chave] == valor, (texto, chave, js)
    if esperado.get("formato") == "projetado":
        x = 333000.5 if "," in texto else 333000
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT ST_X(g) AS lon, ST_Y(g) AS lat "
                        "FROM ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 31983), 4326) g", (x, 7394000))
            r = cur.fetchone()
        assert abs(js["lon"] - float(r["lon"])) < 1e-7 and abs(js["lat"] - float(r["lat"])) < 1e-7


@pytest.mark.parametrize("texto", [
    "", "abc", "-95, 100", "23°S", "333.000 7.394.000", "333.000 7.394.000 EPSG:4326", "333.000 7.394.000 EPSG:99999",
    "1e308 1e308 EPSG:31983", "'; DROP TABLE x; --", "𝟚𝟛°𝟛𝟛′S 46°38′W", "x" * 300, "-23.55, -46.63 EPSG:31983",
    "NaN NaN EPSG:31983", "Infinity Infinity EPSG:31983",
])
def test_ir_para_recusa_texto_malformado(texto):
    js = executar_js(CABECALHO + f"""
      const b = await import('./web/js/mapa/busca.js');
      console.log(JSON.stringify(b.interpretarCoordenada({json.dumps(texto)})));""")
    assert js is None, (texto, js)
