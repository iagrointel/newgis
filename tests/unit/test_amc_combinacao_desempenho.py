"""Cláusula de desempenho do combinador (item L3-01-e-combinacao): recálculo de 4.346 unidades × 19
fatores — o tamanho medido do motor logístico da casa (`cbre.imoveis_fav`/`cbre.hex_fatores`, 19
fatores) — em no máximo 50 ms no servidor (Python/numpy) e 20 ms no navegador (JavaScript via node,
mesmo relógio `performance.now` que o browser usa).

Antes de medir, este teste olha `os.getloadavg()` e a RAM livre. Com carga de 1 minuto acima de 8 (12
núcleos), a máquina está disputada e o número não prova nada: o teste marca a cláusula como NÃO MEDIDA,
grava o motivo em `tests/medidas/L3-01-e-combinacao.json` e não falha por isso — falhar um teste de
desempenho por disputa de CPU seria confundir a máquina com o código. Cada número gravado carrega, ao
lado, a carga de 1 minuto, a RAM livre em GB e o instante da medição: número de desempenho sem isso ao
lado não vale como prova (regra do item).

Grava apenas quando `PLAT_GRAVAR_MEDIDAS=1` (mesma convenção do ADR 0001 seção 10) — a suíte comum
roda a montagem e a checagem do limite, mas não suja a árvore a cada rodada."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from app.amc.combinacao import combinar

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "amc" / "executar_js.mjs"
MEDIDAS = ROOT / "tests" / "medidas"

UNIDADES, FATORES = 4346, 19
LIMITE_SERVIDOR_MS = 50.0
LIMITE_NAVEGADOR_MS = 20.0
CARGA_MAXIMA = 8.0
REPETICOES = 30


def _ram_livre_gb() -> float:
    """MemAvailable de /proc/meminfo (o mesmo número que `free -g` mostra em 'available')."""
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / (1024 * 1024), 2)
    raise RuntimeError("MemAvailable ausente em /proc/meminfo")


def _caso():
    rng = np.random.default_rng(4346190905)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES, FATORES))
    m[rng.uniform(size=m.shape) < 0.1] = np.nan  # mesma ordem de grandeza de ausência do motor logístico
    pesos = list(rng.uniform(0.1, 5.0, size=FATORES))
    return m, pesos


def _js_disponivel() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _medir_servidor_ms(m, pesos) -> float:
    tempos = []
    for _ in range(REPETICOES):
        t0 = time.perf_counter()
        combinar(m, pesos)
        tempos.append((time.perf_counter() - t0) * 1000.0)
    tempos.sort()
    return tempos[len(tempos) // 2]


def _medir_navegador_ms(m, pesos) -> float:
    entrada = {
        "fatores": [[None if not np.isfinite(v) else float(v) for v in linha] for linha in m],
        "pesos": pesos,
        "opcoes": {},
        "repeticoes": REPETICOES,
    }
    r = subprocess.run(
        ["node", str(RUNNER), "--desempenho"],
        input=json.dumps(entrada), capture_output=True, text=True, timeout=60, cwd=ROOT, check=True,
    )
    return json.loads(r.stdout)["ms_mediano"]


def test_recalculo_de_4346_unidades_por_19_fatores_cabe_no_orcamento(medida):
    grava = medida("L3-01-e-combinacao")
    carga_1min = os.getloadavg()[0]
    ram_livre = _ram_livre_gb()
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre:.2f}, medido_em={medido_em}"

    if carga_1min > CARGA_MAXIMA:
        pytest.skip(
            f"cláusula de desempenho NÃO MEDIDA: carga de 1 min {carga_1min:.2f} > {CARGA_MAXIMA} "
            f"(12 núcleos); número sob disputa não prova nada ({contexto})"
        )

    m, pesos = _caso()

    ms_servidor = _medir_servidor_ms(m, pesos)
    grava(
        "recalculo_4346x19_servidor_ms",
        round(ms_servidor, 3),
        "ms",
        f"mediana de {REPETICOES} chamadas a combinar() sobre {UNIDADES}×{FATORES} (numpy, soma_ponderada, "
        f"10% de ausência sorteada) — limite {LIMITE_SERVIDOR_MS} ms; {contexto}",
    )
    assert ms_servidor <= LIMITE_SERVIDOR_MS, (
        f"servidor: {ms_servidor:.3f} ms > {LIMITE_SERVIDOR_MS} ms ({contexto})"
    )

    if not _js_disponivel():
        pytest.skip(f"navegador NÃO MEDIDO: node ausente nesta máquina ({contexto})")

    ms_navegador = _medir_navegador_ms(m, pesos)
    grava(
        "recalculo_4346x19_navegador_ms",
        round(ms_navegador, 3),
        "ms",
        f"mediana de {REPETICOES} chamadas a combinar() em web/js/amc/combinacao.js sobre "
        f"{UNIDADES}×{FATORES}, medida com performance.now() via node (executar_js.mjs --desempenho) — "
        f"o mesmo relógio que o navegador usa; limite {LIMITE_NAVEGADOR_MS} ms; {contexto}",
    )
    assert ms_navegador <= LIMITE_NAVEGADOR_MS, (
        f"navegador: {ms_navegador:.3f} ms > {LIMITE_NAVEGADOR_MS} ms ({contexto})"
    )
