"""Testes de `quantizationParameters` modo view (item L2-04-c): quantizar/desquantizar tem de
voltar dentro de tolerance/2, e o parser recusa entrada mal formada."""

import pytest

from app.consulta import quantizacao as quant
from app.erros import ErroAPI

_EXTENT = {"xmin": -50, "ymin": -25, "xmax": -40, "ymax": -20}


def test_parse_view_ok():
    q = quant.parse({"mode": "view", "tolerance": 0.001, "extent": _EXTENT})
    assert q.origin_x == -50
    assert q.origin_y == -20
    assert q.tolerance == 0.001


def test_quantizar_desquantizar_erro_menor_que_meia_tolerancia():
    q = quant.parse({"mode": "view", "tolerance": 0.0001, "extent": _EXTENT})
    x, y = -46.123456, -23.654321
    qx, qy = q.quantizar(x, y)
    assert isinstance(qx, int) and isinstance(qy, int)
    x2, y2 = q.desquantizar(qx, qy)
    assert abs(x2 - x) <= q.tolerance / 2
    assert abs(y2 - y) <= q.tolerance / 2


def test_modo_edit_e_recusado():
    with pytest.raises(ErroAPI) as e:
        quant.parse({"mode": "edit", "tolerance": 0.001, "extent": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}})
    assert e.value.erro == "quantizacao_modo_fora"


def test_sem_tolerance_e_recusado():
    with pytest.raises(ErroAPI):
        quant.parse({"mode": "view", "extent": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}})


def test_sem_extent_e_recusado():
    with pytest.raises(ErroAPI):
        quant.parse({"mode": "view", "tolerance": 0.1})


def test_tolerance_negativa_e_recusada():
    with pytest.raises(ErroAPI):
        quant.parse({"mode": "view", "tolerance": -1, "extent": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}})
