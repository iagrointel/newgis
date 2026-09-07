"""Cláusula de desempenho e de job do item L3-02-a: 1.000 sorteios em 5.000 unidades em ≤ 60 s, RODANDO
COMO JOB (`app.amc.tarefas.amc_robustez_pesos`, registrado em `amc.robustez_pesos`) — não só a função
pura. O job é chamado com um `ContextoJob` de mentira (sem banco: `progresso`/`log` só registram
chamadas), o mesmo padrão de teste de tipo de job sem banco que `tests/unit/test_jobs_registro.py` usa
para as tarefas de prova.

Mesma disciplina de medição do combinador (item L3-01-e): olha carga e RAM antes de medir; carga alta
vira NÃO MEDIDA, nunca reprovação por causa da máquina; a medida grava carga/RAM/instante ao lado."""

from __future__ import annotations

import datetime
import os
import time

import numpy as np
import pytest

from app.amc import tarefas as amc_tarefas

UNIDADES, FATORES = 5000, 8
N_SORTEIOS = 1000
LIMITE_S = 60.0
CARGA_MAXIMA = 8.0


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")


class _CtxFalso:
    """ContextoJob de mentira: sem banco, só registra progresso/log — mesmo espírito das tarefas de
    prova sem I/O usadas em test_jobs_registro.py (unitário, sem fila real)."""

    def __init__(self):
        self.job_id = "00000000-0000-0000-0000-000000000000"
        self.tenant_id = 0
        self.tentativa = 1
        self.progressos: list[int] = []
        self.logs: list[tuple[str, str]] = []

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.progressos.append(int(pct))

    def log(self, nivel: str, mensagem: str) -> None:
        self.logs.append((nivel, mensagem))


def _caso():
    rng = np.random.default_rng(50008000)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES, FATORES))
    m[rng.uniform(size=m.shape) < 0.05] = np.nan
    fatores = [[None if not np.isfinite(v) else float(v) for v in linha] for linha in m]
    pesos_base = list(rng.uniform(0.5, 3.0, size=FATORES))
    ids_fatores = [f"fator_{i}" for i in range(FATORES)]
    return fatores, pesos_base, ids_fatores


def test_job_amc_robustez_pesos_esta_registrado():
    from app.jobs import tipos

    assert "amc.robustez_pesos" in tipos.REGISTRO
    t = tipos.REGISTRO["amc.robustez_pesos"]
    assert t.funcao is amc_tarefas.amc_robustez_pesos
    assert t.timeout_s >= 60


def test_1000_sorteios_em_5000_unidades_como_job_em_ate_60s(medida):
    grava = medida("L3-02-a-monte-carlo-pesos")
    carga_1min = os.getloadavg()[0]
    ram_livre = _ram_livre_gb()
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre:.2f}, medido_em={medido_em}"

    fatores, pesos_base, ids_fatores = _caso()
    ctx = _CtxFalso()

    # regra de medição sob carga (07/09): mede sempre; carga alta só isenta a REPROVAÇÃO, nunca a
    # aprovação — se passar com folga mesmo disputado, isso conta a favor e entra como medido.
    t0 = time.monotonic()
    saida = amc_tarefas.amc_robustez_pesos(
        ctx, fatores=fatores, pesos_base=pesos_base, ids_fatores=ids_fatores, semente=2026,
        n_sorteios=N_SORTEIOS, metodo="dirichlet",
    )
    duracao_s = time.monotonic() - t0
    passou = duracao_s <= LIMITE_S

    if not passou and carga_1min > CARGA_MAXIMA:
        grava(
            "sorteio_1000x5000_job_s", round(duracao_s, 3), "s",
            f"NAO MEDIDO (estourou sob disputa): {duracao_s:.3f} s > {LIMITE_S} s com carga de 1 min "
            f"{carga_1min:.2f} > {CARGA_MAXIMA} (12 núcleos); {contexto}",
        )
        pytest.skip(f"cláusula de desempenho NÃO MEDIDA por disputa de máquina ({contexto})")

    grava(
        "sorteio_1000x5000_job_s", round(duracao_s, 3), "s",
        f"amc.robustez_pesos ({N_SORTEIOS} sorteios × {UNIDADES} unidades × {FATORES} fatores, "
        f"dirichlet, ContextoJob sem banco) — limite {LIMITE_S} s; {contexto}"
        + (" (passou com folga mesmo sob carga alta)" if carga_1min > CARGA_MAXIMA else ""),
    )
    assert passou, f"{duracao_s:.3f} s > {LIMITE_S} s ({contexto})"

    assert saida["n_sorteios"] == N_SORTEIOS
    assert saida["n_unidades"] == UNIDADES
    assert saida["semente"] == 2026
    assert len(saida["frequencia_topk"]) == UNIDADES  # mapa de frequência: um valor por unidade
    assert ctx.progressos and ctx.progressos[-1] == 100
    assert any("robustez" in msg for _, msg in ctx.logs)


def test_job_reproduz_bit_a_bit_com_a_mesma_semente_via_tarefa():
    fatores, pesos_base, ids_fatores = _caso()
    params = dict(fatores=fatores, pesos_base=pesos_base, ids_fatores=ids_fatores, semente=777,
                  n_sorteios=150, metodo="dirichlet")
    s1 = amc_tarefas.amc_robustez_pesos(_CtxFalso(), **params)
    s2 = amc_tarefas.amc_robustez_pesos(_CtxFalso(), **params)
    assert s1["media"] == s2["media"]
    assert s1["frequencia_topk"] == s2["frequencia_topk"]


def test_parametros_pydantic_validam_matriz_retangular_e_tamanhos():
    from app.amc.tarefas import RobustezParametros

    with pytest.raises(ValueError, match="mesmo número de colunas"):
        RobustezParametros(
            fatores=[[1.0, 2.0], [1.0]], pesos_base=[1.0, 1.0], ids_fatores=["a", "b"], semente=1,
        )
    p = RobustezParametros(
        fatores=[[1.0, None], [3.0, 4.0]], pesos_base=[1.0, 2.0], ids_fatores=["a", "b"], semente=1,
    )
    assert p.n_sorteios == 1000 and p.metodo == "dirichlet"
