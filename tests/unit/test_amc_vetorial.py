"""Recomputação independente dos extratores de vetor (item L3-01-c-extracao-fator).

Regra do portão: o teste chama só `vetorial.extrair()` (a função pública) — o valor esperado é recalculado aqui do
zero com shapely/pyproj puros, nunca reaproveitando `_extrair_poligono`, `_mais_proximo` etc. Convergência exigida:
≤ 0,5 % em área e comprimento, sobre 200 unidades; distância comparada com o equivalente a `ST_Distance(geography)`
em 50 unidades (aqui, `pyproj.Geod` — a distância geodésica real, sem projeção).
"""

import random

import pyproj
import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import transform as transformar

from app.amc import vetorial
from app.amc.zonal import ErroExtracao

SRID = 31983  # SIRGAS 2000 / UTM 23S
_ORIGEM = (500_000.0, 7_400_000.0)
_T_PARA_4326 = pyproj.Transformer.from_crs(f"EPSG:{SRID}", "EPSG:4326", always_xy=True)
_T_PARA_UTM = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{SRID}", always_xy=True)


def _p4326(geom_utm):
    return transformar(lambda x, y, z=None: _T_PARA_4326.transform(x, y), geom_utm)


def _poligono_aleatorio(rng, lado=200.0):
    x0 = _ORIGEM[0] + rng.uniform(-500, 500)
    y0 = _ORIGEM[1] + rng.uniform(-500, 500)
    p = box(x0, y0, x0 + rng.uniform(20, lado), y0 + rng.uniform(20, lado))
    if rng.random() < 0.5:
        p = rotate(p, rng.uniform(-60, 60))
    return p


def _camada_poligonos_fixa():
    """Três polígonos com área e atributo conhecidos, cobrindo boa parte da área de teste."""
    base = [
        (box(_ORIGEM[0] - 300, _ORIGEM[1] - 300, _ORIGEM[0] + 100, _ORIGEM[1] + 100), {"nota": 10.0}),
        (box(_ORIGEM[0] + 50, _ORIGEM[1] + 50, _ORIGEM[0] + 400, _ORIGEM[1] + 400), {"nota": 50.0}),
        (box(_ORIGEM[0] - 600, _ORIGEM[1] + 200, _ORIGEM[0] - 100, _ORIGEM[1] + 700), {"nota": 90.0}),
    ]
    return [(f"p{i}", mapping(_p4326(g)), attrs) for i, (g, attrs) in enumerate(base)]


def test_fracao_e_area_contra_shapely_puro_200_unidades():
    rng = random.Random(11)
    camada = _camada_poligonos_fixa()
    # recompõe as geometrias da camada em UTM diretamente (sem passar pelo módulo sob teste)
    camada_geoms_utm = [transformar(lambda x, y, z=None: _T_PARA_UTM.transform(x, y), shape(f[1])) for f in camada]

    unidades_utm = [_poligono_aleatorio(rng) for _ in range(200)]
    unidades = [(f"u{i}", mapping(_p4326(p))) for i, p in enumerate(unidades_utm)]

    r_fracao = vetorial.extrair(unidades, camada, "vetor_fracao_area", SRID)
    r_area = vetorial.extrair(unidades, camada, "vetor_area", SRID)

    divergencias_area = []
    for i, u in enumerate(unidades_utm):
        inter_total = 0.0
        for g in camada_geoms_utm:
            inter = u.intersection(g)
            if not inter.is_empty:
                inter_total += inter.area
        esperado_area = inter_total
        esperado_fracao = inter_total / u.area if u.area > 0 else 0.0
        obtido_area = r_area[f"u{i}"]["valor"]
        obtido_fracao = r_fracao[f"u{i}"]["valor"]
        assert obtido_area == pytest.approx(esperado_area, abs=max(1.0, esperado_area * 0.005))
        assert obtido_fracao == pytest.approx(esperado_fracao, abs=0.005)
        if esperado_area > 0:
            divergencias_area.append(abs(obtido_area - esperado_area) / esperado_area)
    if divergencias_area:
        assert max(divergencias_area) <= 0.005, f"divergência de área acima de 0,5%: {max(divergencias_area)}"


def _T_PARA_UTM_g(geojson):
    return transformar(lambda x, y, z=None: _T_PARA_UTM.transform(x, y), shape(geojson))


def test_atributo_ponderado_por_area_nao_por_centroide():
    """Unidade cruzando dois polígonos com atributos MUITO diferentes e áreas de sobreposição desiguais: o resultado
    ponderado por ÁREA tem de bater com a conta manual; o resultado por CENTRÓIDE (rejeitado) daria outro número."""
    esquerda = box(_ORIGEM[0], _ORIGEM[1], _ORIGEM[0] + 100, _ORIGEM[1] + 100)  # nota 0, área 10.000
    direita = box(_ORIGEM[0] + 100, _ORIGEM[1], _ORIGEM[0] + 110, _ORIGEM[1] + 100)  # nota 100, área 1.000 (fatia fina)
    camada = [("e", mapping(_p4326(esquerda)), {"nota": 0.0}), ("d", mapping(_p4326(direita)), {"nota": 100.0})]
    unidade_geom = box(_ORIGEM[0] + 40, _ORIGEM[1], _ORIGEM[0] + 105, _ORIGEM[1] + 100)  # cruza as duas
    unidade = [("u1", mapping(_p4326(unidade_geom)))]

    r = vetorial.extrair(unidade, camada, "vetor_atributo_ponderado_area", SRID, {"campo": "nota"})

    inter_e = unidade_geom.intersection(esquerda).area  # 60*100 = 6000
    inter_d = unidade_geom.intersection(direita).area  # 5*100 = 500
    esperado_ponderado = (inter_e * 0.0 + inter_d * 100.0) / (inter_e + inter_d)
    # o centróide da unidade (x≈72,5) cai dentro do polígono ESQUERDO (nota 0): se o produto usasse centróide em
    # vez de área, o resultado seria 0,0 — bem diferente do ponderado por área.
    assert r["u1"]["valor"] == pytest.approx(esperado_ponderado, rel=0.01)
    assert r["u1"]["valor"] != pytest.approx(0.0, abs=1.0)


def test_comprimento_dentro_contra_shapely_puro_200_unidades():
    rng = random.Random(23)
    linha_utm = LineString([(_ORIGEM[0] - 800, _ORIGEM[1]), (_ORIGEM[0] + 800, _ORIGEM[1] + 50),
                            (_ORIGEM[0] + 200, _ORIGEM[1] + 600)])
    camada = [("l0", mapping(_p4326(linha_utm)))]
    unidades_utm = [_poligono_aleatorio(rng, lado=150.0) for _ in range(200)]
    unidades = [(f"u{i}", mapping(_p4326(p))) for i, p in enumerate(unidades_utm)]

    r = vetorial.extrair(unidades, camada, "vetor_comprimento_dentro", SRID)

    divergencias = []
    algum_positivo = False
    for i, u in enumerate(unidades_utm):
        inter = u.intersection(linha_utm)
        esperado = inter.length if not inter.is_empty else 0.0
        obtido = r[f"u{i}"]["valor"]
        assert obtido == pytest.approx(esperado, abs=max(0.05, esperado * 0.005))
        if esperado > 1.0:
            algum_positivo = True
            divergencias.append(abs(obtido - esperado) / esperado)
    assert algum_positivo, "o desenho do teste deveria produzir ao menos uma unidade com comprimento > 0"
    if divergencias:
        assert max(divergencias) <= 0.005


def test_distancia_mais_proxima_bate_com_geodesica_pyproj_50_unidades():
    """Equivalente, sem banco, ao que o adversário faz com `ST_Distance(geography)`: compara a distância projetada
    (UTM, o método do produto) com a distância GEODÉSICA verdadeira (`pyproj.Geod`, elipsoide GRS80) em 50 pares."""
    geod = pyproj.Geod(ellps="GRS80")
    rng = random.Random(5)
    pontos_camada_utm = [Point(_ORIGEM[0] + rng.uniform(-2000, 2000), _ORIGEM[1] + rng.uniform(-2000, 2000))
                         for _ in range(15)]
    camada = [(f"p{i}", mapping(_p4326(p))) for i, p in enumerate(pontos_camada_utm)]
    unidades_utm = [translate(box(0, 0, 30, 30), xoff=_ORIGEM[0] + rng.uniform(-3000, 3000),
                              yoff=_ORIGEM[1] + rng.uniform(-3000, 3000))
                    for _ in range(50)]
    unidades = [(f"u{i}", mapping(_p4326(u))) for i, u in enumerate(unidades_utm)]

    r = vetorial.extrair(unidades, camada, "vetor_distancia_mais_proxima", SRID)

    divergencias = []
    for i, u in enumerate(unidades_utm):
        centro_4326 = _p4326(u.centroid)
        melhor = min(
            geod.inv(centro_4326.x, centro_4326.y, _p4326(p).x, _p4326(p).y)[2]
            for p in pontos_camada_utm
        )
        obtido = r[f"u{i}"]["valor"]
        # comparação feita a partir do CENTRÓIDE de ambos os lados (a unidade é pequena, 30 m, então nearest-edge
        # da unidade e centróide da unidade divergem no máximo pela metade da diagonal, ~21 m) — a tolerância cobre
        # essa geometria conhecida, não esconde erro de método.
        divergencias.append(abs(obtido - melhor))
    maximo = max(divergencias)
    assert maximo <= 30.0, f"divergência distância projetada × geodésica: {maximo} m (tolerância 30 m, unidade 30 m)"


def test_camada_vazia_aborta_a_extracao():
    unidade = [("u1", mapping(_p4326(box(_ORIGEM[0], _ORIGEM[1], _ORIGEM[0] + 10, _ORIGEM[1] + 10))))]
    with pytest.raises(ErroExtracao) as exc:
        vetorial.extrair(unidade, [], "vetor_contagem", SRID)
    assert exc.value.codigo == "camada_vazia"


def test_poligono_com_auto_intersecao_e_reparado_sem_derrubar_o_job():
    """Refutação do adversário: entrar com polígono inválido (bowtie) não pode travar nem produzir lixo silencioso —
    é reparado por `shapely.make_valid` e o aviso fica registrado."""
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]],
    }
    from shapely.geometry import shape as _shape
    assert not _shape(bowtie).is_valid  # confirma que o desenho É inválido antes de testar o comportamento
    unidade_utm = box(_ORIGEM[0] - 5, _ORIGEM[1] - 5, _ORIGEM[0] + 15, _ORIGEM[1] + 15)
    unidade = [("u1", mapping(_p4326(unidade_utm)))]
    bowtie_utm = translate(shape(bowtie), xoff=_ORIGEM[0], yoff=_ORIGEM[1])
    camada = [("c1", mapping(_p4326(bowtie_utm)), {"nota": 5.0})]

    r = vetorial.extrair(unidade, camada, "vetor_area", SRID)

    assert r["u1"]["valor"] is not None
    assert r["u1"]["valor"] >= 0.0
    assert any("inválida" in a for a in r["u1"]["avisos"])


def test_contagem_e_densidade_kernel_camada_de_pontos():
    rng = random.Random(3)
    pontos_utm = [Point(_ORIGEM[0] + rng.uniform(-50, 50), _ORIGEM[1] + rng.uniform(-50, 50)) for _ in range(30)]
    camada = [(f"p{i}", mapping(_p4326(p))) for i, p in enumerate(pontos_utm)]
    unidade_utm = box(_ORIGEM[0] - 60, _ORIGEM[1] - 60, _ORIGEM[0] + 60, _ORIGEM[1] + 60)
    unidade = [("u1", mapping(_p4326(unidade_utm)))]

    r = vetorial.extrair(unidade, camada, "vetor_contagem_raio", SRID, {"raio_m": 1000})
    esperado = sum(1 for p in pontos_utm if unidade_utm.centroid.distance(p) <= 1000)
    assert r["u1"]["valor"] == float(esperado)

    r2 = vetorial.extrair(unidade, camada, "vetor_densidade_kernel", SRID, {"largura_m": 40})
    assert r2["u1"]["valor"] > 0.0


def test_cobertura_e_valor_gravados_por_fator():
    unidade = [("u1", mapping(_p4326(box(_ORIGEM[0], _ORIGEM[1], _ORIGEM[0] + 10, _ORIGEM[1] + 10))))]
    camada = _camada_poligonos_fixa()
    r = vetorial.extrair(unidade, camada, "vetor_fracao_area", SRID)
    assert set(r["u1"].keys()) >= {"valor", "cobertura", "avisos"}
