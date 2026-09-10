"""Ligação gráfico -> mapa da tela de Pareto (item L3-08-pareto), executada fora do navegador.

O e2e (tests/e2e/test_amc_pareto.py) prova que o arrasto do ponteiro chega ao mapa; este teste prova a
CONTA que faz a ligação, no mesmo motor que o navegador roda (node sobre web/js/amc/pareto.js), sem
depender de haver nginx na trilha. A referência é recomputada em Python, aqui, a partir da definição
de "ponto dentro do retângulo".
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "amc" / "executar_pareto_js.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node não instalado nesta máquina")


def rodar(entrada: dict) -> dict:
    r = subprocess.run([NODE, str(RUNNER)], input=json.dumps(entrada), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def unidades():
    """9 unidades numa grade 3x3 de valores, mais uma sem dado no segundo objetivo."""
    us = []
    uid = 1
    for x in (0.0, 50.0, 100.0):
        for y in (0.0, 50.0, 100.0):
            us.append({"unidade_id": uid, "ordem": 1 if (x == 100.0 or y == 100.0) else 3, "valores": [x, y]})
            uid += 1
    us.append({"unidade_id": 99, "ordem": 0, "valores": [10.0, None]})
    return us


def dentro(us, x0, x1, y0, y1):
    return [
        u["unidade_id"] for u in us
        if u["valores"][0] is not None and u["valores"][1] is not None
        and x0 <= u["valores"][0] <= x1 and y0 <= u["valores"][1] <= y1
    ]


def test_escova_em_coordenadas_de_dado_bate_com_a_conta_em_python():
    us = unidades()
    caixa = {"x0": 40.0, "x1": 100.0, "y0": 40.0, "y1": 100.0}
    r = rodar({"unidades": us, "ix": 0, "iy": 1, "caixa": caixa})
    assert r["ids"] == dentro(us, 40.0, 100.0, 40.0, 100.0)
    assert r["filtro"] == ["in", ["get", "unidade_id"], ["literal", r["ids"]]]


def test_unidade_sem_dado_nao_e_desenhada_nem_escovavel():
    r = rodar({"unidades": unidades(), "ix": 0, "iy": 1, "caixa": {"x0": -1e9, "x1": 1e9, "y0": -1e9, "y1": 1e9}})
    assert 99 not in [p["unidade_id"] for p in r["desenhados"]]
    assert 99 not in r["ids"]
    assert len(r["desenhados"]) == 9


def test_retangulo_sem_area_nao_seleciona_nada():
    for caixa in ({"x0": 10.0, "x1": 10.0, "y0": 0.0, "y1": 100.0}, {"x0": 0.0, "x1": 100.0, "y0": 5.0, "y1": 5.0}):
        r = rodar({"unidades": unidades(), "ix": 0, "iy": 1, "caixa": caixa})
        assert r["ids"] == [], caixa
        assert r["filtro"] == ["in", ["get", "unidade_id"], ["literal", []]]


def test_caixa_em_pixels_vira_caixa_de_dado_com_o_eixo_vertical_invertido():
    """O SVG cresce para baixo: o canto de cima da escova é o valor MAIOR do objetivo do eixo y."""
    us = unidades()
    largura, altura = 400, 300
    # metade direita e metade de cima do gráfico -> x >= 50, y >= 50 em coordenadas de dado
    r = rodar({
        "unidades": us, "ix": 0, "iy": 1,
        "caixa_px": {"x0": largura / 2, "x1": largura, "y0": 0, "y1": altura / 2},
        "largura": largura, "altura": altura,
    })
    assert r["caixa"]["x0"] == pytest.approx(50.0)
    assert r["caixa"]["x1"] == pytest.approx(100.0)
    assert sorted([r["caixa"]["y0"], r["caixa"]["y1"]]) == pytest.approx([50.0, 100.0])
    assert r["ids"] == dentro(us, 50.0, 100.0, 50.0, 100.0)


def test_projecao_leva_minimo_e_maximo_as_bordas():
    r = rodar({"unidades": unidades(), "ix": 0, "iy": 1, "caixa": None, "largura": 400, "altura": 300})
    xs = [p[0] for p in r["pixels"]]
    ys = [p[1] for p in r["pixels"]]
    assert min(xs) == 0 and max(xs) == 400
    assert min(ys) == 0 and max(ys) == 300  # invertido: o menor valor do dado vai para baixo


def test_cor_por_ordem_e_estavel_e_a_sem_ordem_e_diferente():
    r = rodar({"unidades": unidades(), "ix": 0, "iy": 1, "caixa": None})
    c1, c2, c3, c0 = r["cores"]
    assert len({c1, c2, c3, c0}) == 4
    assert c1 == "#d98a2b"
