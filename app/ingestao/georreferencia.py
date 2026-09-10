"""Georreferência de desenho por pontos de controle (item L0-04-e).

O DXF quase nunca traz sistema de coordenadas, e muitas plantas estão em coordenada de obra (origem arbitrária,
eixo girado). A conversão para coordenada de terreno é uma **semelhança 2D (transformação de Helmert)**: uma
escala, uma rotação e uma translação, quatro parâmetros, ajustados por mínimos quadrados sobre os pontos que o
usuário dá. É a mesma transformação do `app/georef.py` do SIG de teste interno; o que se acrescenta aqui é o
que o portão de pronto exige e lá não existe: **resíduo por ponto e RMSE reportados**, e o número mínimo de
pontos declarado.

Por que Helmert e não afim: a semelhança preserva ângulo e proporção — um desenho de engenharia não pode ser
esticado em um eixo só para "fechar" nos pontos. Se o RMSE ficar alto, o defeito está nos pontos, e o usuário
tem de vê-lo; esconder o erro dentro de uma transformação com mais parâmetros seria pior.

Contas:

    x' = a·x − b·y + tx        a = s·cos(θ)      s = hypot(a, b)
    y' = b·x + a·y + ty        b = s·sen(θ)      θ = atan2(b, a)

Com 2 pontos o sistema é exatamente determinado (4 equações, 4 incógnitas) e o RMSE é zero por construção — o
que não prova nada. Por isso `AVISO_MINIMO_CONFERENCIA` = 3: só a partir de 3 pontos o resíduo mede alguma
coisa. O portão do item pede exatamente 3.
"""

from __future__ import annotations

import math

import numpy as np

PONTOS_MIN = 2
PONTOS_MAX = 4
AVISO_MINIMO_CONFERENCIA = 3


class PontosInsuficientes(ValueError):
    """Menos de `PONTOS_MIN` pares, ou pares mal formados."""


class AjusteImpossivel(ValueError):
    """Os pontos de origem são colineares/coincidentes: o sistema não tem solução única."""


def ajustar(origem: list[tuple[float, float]], destino: list[tuple[float, float]]) -> dict:
    """Ajusta a semelhança que leva `origem` (coordenada do desenho) em `destino` (coordenada de terreno).
    Devolve os parâmetros, o resíduo de cada ponto (em unidade de destino) e o RMSE."""
    if len(origem) != len(destino):
        raise PontosInsuficientes("cada ponto de controle precisa da coordenada do desenho e da de terreno")
    if len(origem) < PONTOS_MIN:
        raise PontosInsuficientes(f"são necessários ao menos {PONTOS_MIN} pontos de controle; foram enviados "
                                  f"{len(origem)}")
    if len(origem) > PONTOS_MAX:
        raise PontosInsuficientes(f"o máximo é {PONTOS_MAX} pontos de controle; foram enviados {len(origem)}")
    linhas, termos = [], []
    for (x, y), (bx, by) in zip(origem, destino, strict=True):
        for v in (x, y, bx, by):
            if not math.isfinite(float(v)):
                raise PontosInsuficientes("ponto de controle com coordenada não numérica")
        linhas.append([x, -y, 1.0, 0.0])
        termos.append(float(bx))
        linhas.append([y, x, 0.0, 1.0])
        termos.append(float(by))
    matriz = np.array(linhas, dtype=float)
    if np.linalg.matrix_rank(matriz) < 4:
        raise AjusteImpossivel("os pontos de controle do desenho são coincidentes ou colineares demais para "
                               "definir escala e rotação; escolha pontos afastados entre si")
    parametros, *_ = np.linalg.lstsq(matriz, np.array(termos, dtype=float), rcond=None)
    a, b, tx, ty = (float(v) for v in parametros)
    escala = math.hypot(a, b)
    if escala == 0.0:
        raise AjusteImpossivel("o ajuste devolveu escala zero: confira os pontos de controle")
    residuos = []
    for (x, y), (bx, by) in zip(origem, destino, strict=True):
        px, py = aplicar({"a": a, "b": b, "tx": tx, "ty": ty}, x, y)
        residuos.append(math.hypot(px - bx, py - by))
    rmse = math.sqrt(sum(r * r for r in residuos) / len(residuos))
    avisos = []
    if len(origem) < AVISO_MINIMO_CONFERENCIA:
        avisos.append(f"com {len(origem)} pontos o RMSE é zero por construção e não confere nada; use ao menos "
                      f"{AVISO_MINIMO_CONFERENCIA} pontos para que o resíduo signifique alguma coisa")
    return {
        "a": a, "b": b, "tx": tx, "ty": ty,
        "escala": escala,
        "rotacao_graus": math.degrees(math.atan2(b, a)),
        "pontos": len(origem),
        "residuos": [round(r, 6) for r in residuos],
        "residuo_maximo": round(max(residuos), 6),
        "rmse": round(rmse, 6),
        "graus_de_liberdade": 2 * len(origem) - 4,
        "avisos": avisos,
    }


def aplicar(p: dict, x: float, y: float) -> tuple[float, float]:
    return (p["a"] * x - p["b"] * y + p["tx"], p["b"] * x + p["a"] * y + p["ty"])


def sql_geometria(p: dict, coluna: str = "geom") -> str:
    """A mesma semelhança como `ST_Affine` do PostGIS, para aplicar na tabela já carregada em vez de reescrever
    o desenho. `ST_Affine(geom, a, b, d, e, xoff, yoff)` é x' = a·x + b·y + xoff ; y' = d·x + e·y + yoff, logo
    b_postgis = −b e d_postgis = +b."""
    return (f'ST_Affine("{coluna}", {p["a"]!r}, {-p["b"]!r}, {p["b"]!r}, {p["a"]!r}, '
            f'{p["tx"]!r}, {p["ty"]!r})')


def escala_de_unidade(metros_por_unidade: float | None) -> dict | None:
    """Quando não há pontos de controle mas há unidade declarada, a única correção possível é de ESCALA (o
    desenho já está em coordenada de terreno, só que em centímetro, milímetro ou polegada)."""
    if not metros_por_unidade or metros_por_unidade == 1.0:
        return None
    return {"a": metros_por_unidade, "b": 0.0, "tx": 0.0, "ty": 0.0, "escala": metros_por_unidade,
            "rotacao_graus": 0.0, "pontos": 0, "residuos": [], "residuo_maximo": 0.0, "rmse": 0.0,
            "graus_de_liberdade": 0,
            "avisos": ["transformação só de escala, derivada da unidade declarada no desenho; nenhum ponto de "
                       "controle foi usado"]}
