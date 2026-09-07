"""Item L3-07-agregacao: agregação de grade para feição. Casos sintéticos (geometria conhecida à mão) para
provar o mecanismo — o cross-check contra o piloto real (`cbre.imoveis_fav`, 4.346 feições) está em
`test_amc_agregacao_cbre.py`. Usa `conexao_plat_app` só porque a interseção/área é feita pelo PostGIS
(ST_Intersection/ST_Area), nunca por reimplementar geometria em Python."""

import pytest

from app.amc import agregacao

SRID = 31983  # SIRGAS 2000 / UTM 23S
_ORIGEM = (500_000.0, 7_400_000.0)  # coordenada UTM plausível, longe de qualquer feição real


def _retangulo(x0, y0, dx, dy):
    x1, y1 = x0 + dx, y0 + dy
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def _celula(i, j, veto=False, motivo=None, fatores=None):
    """Célula de grade 100x100 m na posição (i, j) da grade a partir de `_ORIGEM`."""
    x0, y0 = _ORIGEM[0] + i * 100, _ORIGEM[1] + j * 100
    return (f"c{i}{j}", _retangulo(x0, y0, 100, 100), veto, motivo, fatores or {})


def _agregar(cur, feicao_geom, celulas, **kw):
    fsql, fparams = agregacao.feicoes_de_geojson([("f1", feicao_geom)], SRID, srid_entrada=SRID)
    csql, cparams = agregacao.celulas_de_geojson(celulas, SRID, srid_entrada=SRID)
    return agregacao.agregar(cur, fsql, fparams, csql, cparams, **kw)["resultados"][0]


def test_feicao_cobre_metade_de_duas_celulas_media_ponderada_por_area(conexao_plat_app):
    # feição = retângulo de 200x50 cobrindo a metade de baixo de c00 (fator 10) e a metade de baixo de
    # c10 (fator 90); nenhuma vetada. Média esperada = (5000*10 + 5000*90) / 10000 = 50.
    celulas = [_celula(0, 0, fatores={"f": 10.0}), _celula(1, 0, fatores={"f": 90.0})]
    feicao = _retangulo(*_ORIGEM, 200, 50)
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, feicao, celulas)
    assert r["sem_celula"] is False
    assert r["area_total_m2"] == pytest.approx(10_000.0, rel=1e-6)
    assert r["n_cel"] == 2
    assert r["fracao_vetada"] == pytest.approx(0.0)
    assert r["veto_principal"] is None
    assert r["fatores_media"] == pytest.approx({"f": 50.0})
    assert r["combinacao"] == pytest.approx(50.0)
    assert r["favorabilidade"] == pytest.approx(50.0)
    assert r["fora_do_ranking"] is False


def test_celula_vetada_sai_do_fator_mas_conta_na_fracao_vetada(conexao_plat_app):
    # c00 (fator 80, não vetada) e c10 (vetada, motivo 'restricao_x'); a feição toca as duas por igual.
    celulas = [_celula(0, 0, fatores={"f": 80.0}), _celula(1, 0, veto=True, motivo="restricao_x")]
    feicao = _retangulo(*_ORIGEM, 200, 100)
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, feicao, celulas)
    assert r["fracao_vetada"] == pytest.approx(0.5)
    assert r["veto_principal"] == "restricao_x"
    assert r["n_cel"] == 1  # só a célula não vetada entra em n_cel
    assert r["n_cel_tocadas"] == 2
    assert r["fatores_media"] == pytest.approx({"f": 80.0})
    assert r["combinacao"] == pytest.approx(80.0)  # média do único fator com dado, sobre as não vetadas
    assert r["favorabilidade"] == pytest.approx(40.0)  # 80 * (1 - 0,5)


def test_veto_principal_e_o_de_maior_area_de_intersecao(conexao_plat_app):
    # a feição cobre 75% de c00 (vetada, motivo 'grande') e 25% de c10 (vetada, motivo 'pequena').
    celulas = [_celula(0, 0, veto=True, motivo="grande"), _celula(1, 0, veto=True, motivo="pequena")]
    feicao = _retangulo(_ORIGEM[0], _ORIGEM[1], 125, 100)  # 100 m dentro de c00 + 25 m dentro de c10
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, feicao, celulas)
    assert r["veto_principal"] == "grande"
    assert r["fracao_vetada"] == pytest.approx(1.0)


def test_limiar_de_fracao_vetada_marca_fora_do_ranking(conexao_plat_app):
    celulas = [_celula(0, 0, veto=True, motivo="m1"), _celula(1, 0, fatores={"f": 60.0})]
    feicao = _retangulo(*_ORIGEM, 200, 100)
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, feicao, celulas, limiar_fracao_vetada=0.5)
    assert r["fracao_vetada"] == pytest.approx(0.5)
    assert r["fora_do_ranking"] is True  # 0,5 >= limiar 0,5 (limite é fechado, não estrito)
    with conexao_plat_app.cursor() as cur:
        r2 = _agregar(cur, feicao, celulas, limiar_fracao_vetada=0.51)
    assert r2["fora_do_ranking"] is False


def test_feicao_sem_intersecao_sai_como_sem_celula_nunca_zero(conexao_plat_app):
    celulas = [_celula(0, 0, fatores={"f": 30.0})]
    longe = _retangulo(0.0, 0.0, 0.0001, 0.0001)  # em graus, no meio do Atlântico: não toca a grade UTM
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, longe, celulas)
    assert r["sem_celula"] is True
    assert r["area_total_m2"] is None
    assert r["fracao_vetada"] is None
    assert r["n_cel"] is None
    assert r["n_cel_tocadas"] is None
    assert r["veto_principal"] is None
    assert r["fatores_media"] == {}
    assert r["favorabilidade"] is None
    assert r["combinacao"] is None
    assert r["fora_do_ranking"] is False  # ausência de dado não é restrição: não confundir com veto


def test_caminho_inverso_feicao_para_celulas(conexao_plat_app):
    celulas = [_celula(0, 0, fatores={"f": 10.0}), _celula(1, 0, fatores={"f": 90.0})]
    feicao = _retangulo(*_ORIGEM, 200, 50)
    fsql, fparams = agregacao.feicoes_de_geojson([("f1", feicao)], SRID, srid_entrada=SRID)
    csql, cparams = agregacao.celulas_de_geojson(celulas, SRID, srid_entrada=SRID)
    with conexao_plat_app.cursor() as cur:
        linhas = agregacao.celulas_de_uma_feicao(cur, fsql, fparams, csql, cparams, "f1")
    assert {c["cell_id"] for c in linhas} == {"c00", "c10"}
    for c in linhas:
        assert c["area_intersecao_m2"] == pytest.approx(5_000.0, rel=1e-6)
        assert c["area_celula_m2"] == pytest.approx(10_000.0, rel=1e-6)


def test_pesos_do_modelo_recombinam_varios_fatores(conexao_plat_app):
    # dois fatores por célula, modelo com pesos 3:1 -> combinação = (3*fa + 1*fb) / 4
    celulas = [_celula(0, 0, fatores={"fa": 100.0, "fb": 0.0})]
    feicao = _retangulo(*_ORIGEM, 100, 100)
    modelo = {"fatores": [{"id": "fa", "peso": 3.0}, {"id": "fb", "peso": 1.0}]}
    with conexao_plat_app.cursor() as cur:
        r = _agregar(cur, feicao, celulas, modelo_definicao=modelo)
    assert r["combinacao"] == pytest.approx(75.0)
    assert r["favorabilidade"] == pytest.approx(75.0)


def test_feicao_id_duplicado_recusa():
    with pytest.raises(agregacao.ErroAgregacao):
        agregacao.feicoes_de_geojson([("a", _retangulo(0, 0, 1, 1)), ("a", _retangulo(1, 1, 1, 1))], SRID)


def test_limiar_fora_de_zero_um_recusa(conexao_plat_app):
    celulas = [_celula(0, 0, fatores={"f": 1.0})]
    feicao = _retangulo(*_ORIGEM, 100, 100)
    fsql, fparams = agregacao.feicoes_de_geojson([("f1", feicao)], SRID, srid_entrada=SRID)
    csql, cparams = agregacao.celulas_de_geojson(celulas, SRID, srid_entrada=SRID)
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(agregacao.ErroAgregacao):
            agregacao.agregar(cur, fsql, fparams, csql, cparams, limiar_fracao_vetada=1.5)
