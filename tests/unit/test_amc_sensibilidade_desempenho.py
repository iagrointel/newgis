"""Cláusula de TEMPO MEDIDO do item L3-02-b, rodando COMO JOB (`app.amc.tarefas.amc_sensibilidade`,
registrado em `amc.sensibilidade`) — não só a função pura. O job é chamado com um `ContextoJob` de
mentira (sem banco: `progresso`/`log` só registram chamadas), o mesmo padrão do item L3-02-a.

Mesma disciplina de medição do sorteio: olha carga e RAM antes; carga alta vira NÃO MEDIDA em vez de
reprovação; a medida grava carga, RAM e instante ao lado do número."""

from __future__ import annotations

import datetime
import os
import time

import numpy as np
import pytest

from app.amc import tarefas as amc_tarefas

UNIDADES, FATORES = 2000, 6
N_SOBOL = 512
LIMITE_S = 60.0
CARGA_MAXIMA = 8.0
ITEM = "L3-02-b-sensibilidade-sobol-oat"


def _ram_livre_gb() -> float:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")


class _CtxFalso:
    """ContextoJob de mentira: sem banco, só registra progresso e log."""

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
    rng = np.random.default_rng(50008001)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES, FATORES))
    m[rng.uniform(size=m.shape) < 0.05] = np.nan
    fatores = [[None if not np.isfinite(v) else float(v) for v in linha] for linha in m]
    pesos_base = list(rng.uniform(0.5, 3.0, size=FATORES))
    ids_fatores = [f"fator_{i}" for i in range(FATORES)]
    return fatores, pesos_base, ids_fatores


def test_job_amc_sensibilidade_esta_registrado():
    from app.jobs import tipos

    assert "amc.sensibilidade" in tipos.REGISTRO
    t = tipos.REGISTRO["amc.sensibilidade"]
    assert t.funcao is amc_tarefas.amc_sensibilidade
    assert t.timeout_s >= 60


def test_relatorio_de_sensibilidade_como_job_com_tempo_medido(medida):
    grava = medida(ITEM)
    carga_1min = os.getloadavg()[0]
    ram_livre = _ram_livre_gb()
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre:.2f}, medido_em={medido_em}"

    fatores, pesos_base, ids_fatores = _caso()
    ctx = _CtxFalso()

    t0 = time.monotonic()
    saida = amc_tarefas.amc_sensibilidade(
        ctx, fatores=fatores, pesos_base=pesos_base, ids_fatores=ids_fatores,
        modelo="SIG de teste interno", semente=2026, n=N_SOBOL, n_bootstrap=100,
    )
    duracao_s = time.monotonic() - t0
    passou = duracao_s <= LIMITE_S

    if not passou and carga_1min > CARGA_MAXIMA:
        grava(
            "relatorio_n512_2000x6_job_s", round(duracao_s, 3), "s",
            f"NAO MEDIDO (estourou sob disputa): {duracao_s:.3f} s > {LIMITE_S} s com carga de 1 min "
            f"{carga_1min:.2f} > {CARGA_MAXIMA} (12 núcleos); {contexto}",
        )
        pytest.skip(f"cláusula de tempo NÃO MEDIDA por disputa de máquina ({contexto})")

    grava(
        "relatorio_n512_2000x6_job_s", round(duracao_s, 3), "s",
        f"amc.sensibilidade (N={N_SOBOL} de Saltelli = {N_SOBOL * (FATORES + 2)} recombinações sobre "
        f"{UNIDADES} unidades × {FATORES} fatores, mais tornado de 9 passos por fator e 100 "
        f"reamostragens, ContextoJob sem banco) — limite {LIMITE_S} s; {contexto}"
        + (" (passou com folga mesmo sob carga alta)" if carga_1min > CARGA_MAXIMA else ""),
    )
    grava("tempo_global_s", round(saida["tempo_global_s"], 3), "s",
          f"parte global (índices de Sobol) do mesmo relatório; {contexto}")
    grava("tempo_local_s", round(saida["tempo_local_s"], 3), "s",
          f"parte local (tornado um fator por vez) do mesmo relatório; {contexto}")
    assert passou, f"{duracao_s:.3f} s > {LIMITE_S} s ({contexto})"

    assert saida["global"]["n"] == N_SOBOL
    assert saida["global"]["n_avaliacoes"] == N_SOBOL * (FATORES + 2)
    assert saida["global"]["semente"] == 2026
    assert len(saida["global"]["entradas"]) == FATORES
    assert len(saida["local"]["barras"]) == FATORES
    assert saida["tempo_s"] > 0
    assert ctx.progressos and ctx.progressos[-1] == 100
    assert any("sensibilidade" in msg for _, msg in ctx.logs)


def test_erro_de_ishigami_contra_a_referencia_fica_gravado(medida):
    """A cláusula de referência vira medida gravada, não só assertiva: quanto o estimador errou contra
    o valor em forma fechada, com o N usado."""
    from app.amc import sensibilidade as sens

    grava = medida(ITEM)
    referencia = sens.indices_analiticos_ishigami()
    n = 16384
    t0 = time.monotonic()
    r = sens.sobol(sens.ishigami, sens.LIMITES_ISHIGAMI, n=n, semente=7, n_bootstrap=0)
    duracao_s = time.monotonic() - t0
    erro = max(float(np.abs(r.s1 - np.array(referencia["s1"])).max()),
               float(np.abs(r.st - np.array(referencia["st"])).max()))
    grava("erro_maximo_ishigami", round(erro, 5), "índice",
          f"maior desvio absoluto contra os índices em forma fechada (N={n}, semente 7, "
          f"{r.n_avaliacoes} avaliações em {duracao_s:.3f} s) — tolerância do portão 0,05")
    assert erro <= 0.05


def test_parametros_pydantic_validam_matriz_potencia_de_dois_e_faixa():
    from app.amc.tarefas import SensibilidadeParametros

    with pytest.raises(ValueError, match="mesmo número de colunas"):
        SensibilidadeParametros(fatores=[[1.0, 2.0], [1.0]], pesos_base=[1.0, 1.0],
                                ids_fatores=["a", "b"], modelo="m", semente=1)
    with pytest.raises(ValueError, match="potência de 2"):
        SensibilidadeParametros(fatores=[[1.0, 2.0]], pesos_base=[1.0, 1.0], ids_fatores=["a", "b"],
                                modelo="m", semente=1, n=1000)
    with pytest.raises(ValueError):
        SensibilidadeParametros(fatores=[[1.0, 2.0]], pesos_base=[1.0, 1.0], ids_fatores=["a", "b"],
                                modelo="m", semente=1, faixa_peso_baixo=-1.5)
    p = SensibilidadeParametros(fatores=[[1.0, None], [3.0, 4.0]], pesos_base=[1.0, 2.0],
                                ids_fatores=["a", "b"], modelo="m", semente=1)
    assert p.n == 1024 and p.alvo == "concordancia_topk" and p.n_bootstrap == 100
