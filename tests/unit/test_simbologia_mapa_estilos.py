"""Simbologia proporcional/calor/raster (item L2-01-c-lista-camadas-legenda, extensão de
app/mapa/simbologia.py). Prova a mesma regra do item-pai (L2-01-mapa-web) para os 3 tipos novos:
legenda e estilo saem da MESMA função, nunca cores divergentes."""

import pytest

from app.mapa import simbologia as s


def test_proporcional_exige_campo_minimo_e_maximo():
    with pytest.raises(s.SimbologiaInvalida):
        s.normalizar({"tipo": "proporcional", "campo": "v"}, "Point")
    with pytest.raises(s.SimbologiaInvalida):
        s.normalizar({"tipo": "proporcional", "minimo": 0, "maximo": 10}, "Point")


def test_proporcional_e_calor_recusam_geometria_nao_ponto():
    with pytest.raises(s.SimbologiaInvalida):
        s.normalizar({"tipo": "proporcional", "campo": "v", "minimo": 0, "maximo": 10}, "Polygon")
    with pytest.raises(s.SimbologiaInvalida):
        s.normalizar({"tipo": "calor"}, "LineString")


def test_proporcional_raio_cresce_com_o_valor_e_legenda_bate_com_a_expressao_do_estilo():
    simb = {"tipo": "proporcional", "campo": "populacao", "minimo": 0, "maximo": 1000,
            "raio_min": 2, "raio_max": 24, "cor": "#123456"}
    legenda = s.legenda(simb, "Point")
    estilo = s.camadas_maplibre(simb, "Point", "cam", "fonte", "camfonte")[0]
    raios = [e["raio"] for e in legenda]
    assert raios == sorted(raios)
    assert raios[0] == pytest.approx(2.0)
    assert raios[-1] == pytest.approx(24.0)
    # a mesma cor da legenda é a cor CONSTANTE da expressão do mapa (só o raio varia por valor)
    assert all(e["cor"] == "#123456" for e in legenda)
    assert estilo["paint"]["circle-color"] == "#123456"
    expr = estilo["paint"]["circle-radius"]
    assert expr[0] == "interpolate" and expr[2] == ["to-number", ["get", "populacao"]]
    assert expr[3] == 0 and expr[4] == 2 and expr[-2] == 1000 and expr[-1] == 24


def test_calor_usa_a_mesma_rampa_na_legenda_e_no_heatmap_color():
    rampa = ["#000000", "#888888", "#ffffff"]
    simb = {"tipo": "calor", "rampa": rampa}
    legenda = s.legenda(simb, "Point")
    estilo = s.camadas_maplibre(simb, "Point", "cam", "fonte", "camfonte")[0]
    assert estilo["type"] == "heatmap"
    cores_estilo = [v for v in estilo["paint"]["heatmap-color"] if isinstance(v, str) and v.startswith("#")]
    assert cores_estilo == rampa
    assert legenda[0]["cor"] == rampa[0] and legenda[-1]["cor"] == rampa[-1]
    assert legenda[0]["rampa"] == rampa


def test_calor_com_peso_declarado_usa_o_campo_no_heatmap_weight():
    simb = {"tipo": "calor", "peso": "intensidade"}
    estilo = s.camadas_maplibre(simb, "Point", "cam", "fonte", "camfonte")[0]
    assert estilo["paint"]["heatmap-weight"] == ["to-number", ["get", "intensidade"]]


def test_estilo_raster_gera_rampa_continua_com_minimo_e_maximo():
    rampa = ["#f7fbff", "#08519c"]
    camada = s.estilo_raster("cam-r", "fonte-r", rampa, 10.0, 90.0, opacidade=0.7)
    assert camada["type"] == "raster"
    assert camada["paint"]["raster-color-range"] == [10.0, 90.0]
    expr = camada["paint"]["raster-color"]
    assert expr[0] == "interpolate" and expr[2] == ["raster-value"]
    assert expr[3] == 10.0 and expr[4] == rampa[0]
    assert expr[-2] == 90.0 and expr[-1] == rampa[-1]
    assert camada["paint"]["raster-opacity"] == 0.7


def test_legenda_raster_traz_titulo_unidade_minimo_maximo_e_a_mesma_rampa_do_estilo():
    rampa = ["#f7fbff", "#6baed6", "#08519c"]
    camada = s.estilo_raster("cam-r", "fonte-r", rampa, 0.0, 1.0)
    leg = s.legenda_raster(rampa, 0.0, 1.0, titulo="NDVI médio", unidade="índice (-1 a 1)")
    assert leg["tipo"] == "raster"
    assert leg["titulo"] == "NDVI médio" and leg["unidade"] == "índice (-1 a 1)"
    assert leg["minimo"] == 0.0 and leg["maximo"] == 1.0
    assert leg["rampa"] == rampa == camada["metadata"]["plat:rampa"]


@pytest.mark.parametrize("tipo", ["simples", "valores_unicos", "intervalos", "proporcional", "calor"])
def test_seis_tipos_do_l2_02_c_tem_forma_representavel(tipo):
    """Os "6 tipos de estilo do L2-02-c" do portão do L2-01-c: símbolo único, categorias, classes,
    proporcional, calor e raster com rampa. Os 5 de feição saem daqui; raster é `estilo_raster` acima
    (testado separadamente porque não tem geometria de feição)."""
    if tipo == "simples":
        simb = {"tipo": "simples", "cor": "#4e79a7"}
    elif tipo == "valores_unicos":
        simb = {"tipo": "valores_unicos", "campo": "c", "valores": ["a", "b"]}
    elif tipo == "intervalos":
        simb = {"tipo": "intervalos", "campo": "v", "cortes": [10, 20]}
    elif tipo == "proporcional":
        simb = {"tipo": "proporcional", "campo": "v", "minimo": 0, "maximo": 10}
    else:
        simb = {"tipo": "calor"}
    geometria = "Point" if tipo in ("proporcional", "calor") else "Polygon"
    leg = s.legenda(simb, geometria)
    assert leg and all("cor" in e for e in leg)
