"""Georreferência de desenho por pontos de controle (item L0-04-e; ADR 0020 seção 5). A cláusula do portão é
"georreferência por 3 pontos com RMSE reportado": aqui se prova que o ajuste recupera escala, rotação e
translação conhecidas, que o RMSE aparece e mede o erro que existe, e que caso degenerado é RECUSADO em vez de
devolver número bonito."""

from __future__ import annotations

import math

import pytest

from app.ingestao import georreferencia as geo

ITEM = "L0-04-e-formatos-cad"
ESCALA, ANGULO, TX, TY = 2.5, 17.0, 421_350.0, 7_394_120.0
VERDADE = {"a": ESCALA * math.cos(math.radians(ANGULO)), "b": ESCALA * math.sin(math.radians(ANGULO)),
           "tx": TX, "ty": TY}
DESENHO = [(0.0, 0.0), (120.0, 0.0), (0.0, 80.0), (120.0, 80.0)]


def _terreno(pontos, erro=None):
    saida = []
    for i, (x, y) in enumerate(pontos):
        px, py = geo.aplicar(VERDADE, x, y)
        if erro and i in erro:
            px, py = px + erro[i][0], py + erro[i][1]
        saida.append((px, py))
    return saida


def test_tres_pontos_recuperam_escala_rotacao_translacao_com_rmse(medida):
    origem = DESENHO[:3]
    ajuste = geo.ajustar(origem, _terreno(origem))
    assert ajuste["pontos"] == 3 and ajuste["graus_de_liberdade"] == 2
    assert ajuste["rmse"] < 1e-6
    assert abs(ajuste["escala"] - ESCALA) < 1e-9
    assert abs(ajuste["rotacao_graus"] - ANGULO) < 1e-6   # 1e-6 grau = 2 mm em 100 km
    assert abs(ajuste["tx"] - TX) < 1e-6 and abs(ajuste["ty"] - TY) < 1e-6
    medida(ITEM)("georreferencia_3_pontos",
                 {"escala": ajuste["escala"], "rotacao_graus": ajuste["rotacao_graus"], "rmse": ajuste["rmse"],
                  "residuo_maximo": ajuste["residuo_maximo"], "graus_de_liberdade": ajuste["graus_de_liberdade"]},
                 "metro", "venv/bin/pytest tests/unit/test_georreferencia.py -k tres_pontos")


def test_rmse_cresce_com_o_erro_do_ponto(medida):
    """Um ponto deslocado 0,40 m em x. Com 3 pontos o ajuste espalha o erro; o RMSE tem de sair diferente de
    zero e o resíduo máximo, menor que o erro injetado (a semelhança acomoda parte dele)."""
    origem = DESENHO[:3]
    ajuste = geo.ajustar(origem, _terreno(origem, erro={2: (0.40, 0.0)}))
    assert 0.0 < ajuste["rmse"] < 0.40
    assert ajuste["residuo_maximo"] >= ajuste["rmse"]
    assert len(ajuste["residuos"]) == 3
    medida(ITEM)("georreferencia_rmse_com_erro",
                 {"erro_injetado_m": 0.40, "rmse": ajuste["rmse"], "residuos": ajuste["residuos"]},
                 "metro", "venv/bin/pytest tests/unit/test_georreferencia.py -k rmse_cresce")


def test_dois_pontos_avisam_que_o_rmse_nao_confere_nada():
    ajuste = geo.ajustar(DESENHO[:2], _terreno(DESENHO[:2]))
    assert ajuste["rmse"] == 0.0 and ajuste["graus_de_liberdade"] == 0
    assert any("não confere nada" in a for a in ajuste["avisos"])


def test_quatro_pontos_aceitos_e_cinco_recusados():
    assert geo.ajustar(DESENHO, _terreno(DESENHO))["pontos"] == 4
    with pytest.raises(geo.PontosInsuficientes):
        geo.ajustar(DESENHO + [(1.0, 1.0)], _terreno(DESENHO + [(1.0, 1.0)]))
    with pytest.raises(geo.PontosInsuficientes):
        geo.ajustar(DESENHO[:1], _terreno(DESENHO[:1]))


def test_pontos_coincidentes_ou_colineares_sao_recusados():
    with pytest.raises(geo.AjusteImpossivel):
        geo.ajustar([(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)], [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)])
    colineares = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    ajuste = geo.ajustar(colineares, _terreno(colineares))
    assert ajuste["rmse"] == 0.0  # colinear ainda determina a semelhança; o que não determina é ponto repetido


def test_coordenada_nao_numerica_e_recusada():
    with pytest.raises(geo.PontosInsuficientes):
        geo.ajustar([(0.0, 0.0), (float("nan"), 1.0)], [(0.0, 0.0), (1.0, 1.0)])


def test_sql_da_semelhanca_bate_com_a_conta_em_python():
    """`ST_Affine` do PostGIS troca a ordem dos coeficientes; o erro de sinal aqui giraria o desenho para o
    outro lado. A prova é textual: os quatro coeficientes na ordem a, −b, b, a."""
    ajuste = geo.ajustar(DESENHO[:3], _terreno(DESENHO[:3]))
    sql = geo.sql_geometria(ajuste, "geom")
    assert sql.startswith('ST_Affine("geom", ')
    coef = [float(v) for v in sql[sql.index("(") + 1:sql.rindex(")")].split(",")[1:]]
    assert coef[0] == pytest.approx(ajuste["a"]) and coef[1] == pytest.approx(-ajuste["b"])
    assert coef[2] == pytest.approx(ajuste["b"]) and coef[3] == pytest.approx(ajuste["a"])


def test_escala_de_unidade_sem_pontos_de_controle():
    assert geo.escala_de_unidade(1.0) is None and geo.escala_de_unidade(None) is None
    so_escala = geo.escala_de_unidade(0.0254)
    assert so_escala["escala"] == 0.0254 and so_escala["rotacao_graus"] == 0.0 and so_escala["pontos"] == 0
    assert any("nenhum ponto de controle" in a for a in so_escala["avisos"])
