"""Custo da ordenação no TETO declarado de unidades (item L3-08-pareto).

O portão do item não tem cláusula de tempo. O que este teste existe para sustentar é o número que a
rota publica na recusa: `PARETO_UNIDADES_MAX = 50.000`. Declarar um teto sem nunca ter rodado nele
seria um limite de fé; aqui ele é rodado, com 4 objetivos (o máximo) e 3 ordens.

Antes de medir, olha `os.getloadavg()` e a RAM livre: com carga de 1 minuto acima de 8 (12 núcleos) o
número não prova nada sobre o produto e a medida é registrada como NÃO MEDIDA, sem reprovar — falhar
por disputa de CPU seria confundir a máquina com o código. Cada número gravado carrega ao lado a carga,
a RAM livre e o instante. Grava só com `PLAT_GRAVAR_MEDIDAS=1`.
"""

from __future__ import annotations

import datetime
import os
import time

import numpy as np
import pytest

from app.amc import pareto
from app.limites import PARETO_UNIDADES_MAX

CARGA_MAXIMA = 8.0
OBJETIVOS = pareto.MAX_OBJETIVOS
ORDENS = 3
TETO_MS = 30_000.0  # não é alvo de produto: é o sinal de que o teto de unidades virou inviável


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")


def test_ordenacao_no_teto_de_unidades(medida):
    grava = medida("L3-08-pareto")
    carga = os.getloadavg()[0]
    ram = _ram_livre_gb()
    quando = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga:.2f}, ram_livre_gb={ram:.2f}, medido_em={quando}"
    if carga > CARGA_MAXIMA:
        pytest.skip(f"medida NÃO FEITA: carga de 1 min {carga:.2f} > {CARGA_MAXIMA} (12 núcleos); {contexto}")

    rng = np.random.default_rng(20260908)
    m = rng.uniform(0.0, 100.0, size=(PARETO_UNIDADES_MAX, OBJETIVOS))
    t0 = time.perf_counter()
    r = pareto.ordenar(m, ["maximizar"] * OBJETIVOS, ordens=ORDENS)
    ms = (time.perf_counter() - t0) * 1000.0

    assert r.classificadas > 0
    grava(
        "ordenacao_no_teto_ms",
        round(ms, 1),
        "ms",
        f"pareto.ordenar() sobre {PARETO_UNIDADES_MAX} unidades × {OBJETIVOS} objetivos, {ORDENS} ordens "
        f"(uma chamada, sem repetição); {contexto}",
    )
    grava("carga_1min", round(carga, 2), "carga", f"os.getloadavg()[0] no instante da medida; {contexto}")
    grava("ram_livre_gb", ram, "GB", f"MemAvailable de /proc/meminfo no instante da medida; {contexto}")
    assert ms <= TETO_MS, f"{ms:.0f} ms para o teto de {PARETO_UNIDADES_MAX} unidades ({contexto})"
