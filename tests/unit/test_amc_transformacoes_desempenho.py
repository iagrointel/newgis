"""Cláusula de desempenho do portão de pronto: "pré-visualização com histograma de entrada e
histograma de saída em ≤ 300 ms para 100 mil valores". Mede só a função pura
`app.amc.transformacoes.pre_visualizar` (numpy, sem banco) — é o que o painel de pré-visualização do
navegador de dados chama antes de qualquer coisa entrar no banco.

Regra da casa (brief comum, "Cláusula de DESEMPENHO"): número de tempo sem a carga da máquina ao lado
não vale como prova. Este teste sempre grava `carga_1min`/`ram_livre_gb`/`medido_em` junto com o
tempo, e só reprova se a carga estava calma (≤ 8) — sob carga alta, marca a cláusula NÃO MEDIDA em vez
de reprovar o produto pela casa."""

import datetime
import os
import subprocess

import numpy as np
import pytest

from app.amc import transformacoes as tr

N = 100_000
LIMITE_MS = 300.0
LIMITE_CARGA = 8.0


def _carga_e_ram() -> tuple[float, float]:
    carga_1min = os.getloadavg()[0]
    r = subprocess.run(["free", "-g"], capture_output=True, text=True, timeout=5, check=True)
    linha_mem = [ln for ln in r.stdout.splitlines() if ln.startswith("Mem:")][0]
    ram_livre_gb = float(linha_mem.split()[6])  # coluna "available"
    return carga_1min, ram_livre_gb


CASOS = {
    "linear": {"tipo": "linear", "minimo": 0.0, "maximo": 100.0},
    "gaussiana": {"tipo": "gaussiana", "midpoint": 50.0, "spread": 0.001},
    "faixas": {"tipo": "faixas", "quebras": [10, 30, 60, 90], "notas": [10, 40, 60, 80, 100]},
    "categoria": {"tipo": "categoria", "notas": {str(i): float(i % 100) for i in range(50)}, "outros": 0.0},
}


@pytest.mark.parametrize("tipo", sorted(CASOS))
def test_previsualizacao_100mil_valores(tipo, medida):
    transformacao = CASOS[tipo]
    rng = np.random.default_rng(20260907)
    if tipo == "categoria":
        valores = [str(v) for v in rng.integers(0, 60, size=N)]
    else:
        valores = rng.uniform(-20.0, 120.0, size=N).tolist()
        # 5% de nulo, como uma camada real de baixa cobertura
        idx_nulo = rng.choice(N, size=N // 20, replace=False)
        for i in idx_nulo:
            valores[i] = None

    carga_1min, ram_livre_gb = _carga_e_ram()
    r = tr.pre_visualizar(valores, transformacao)

    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    comando = f"pytest tests/unit/test_amc_transformacoes_desempenho.py::test_previsualizacao_100mil_valores[{tipo}]"
    grava_base = medida("L3-01-d-transformacoes")

    def grava(nome, *a, **kw):
        return grava_base(f"previsualizacao_{tipo}_{nome}", *a, **kw)

    grava("tempo_ms", round(r.tempo_ms, 2), "ms", comando)
    grava("carga_1min", round(carga_1min, 2), "processos", comando)
    grava("ram_livre_gb", round(ram_livre_gb, 1), "GB", comando)
    grava("medido_em", medido_em, "timestamp", comando)
    grava("n", r.n, "valores", comando)

    assert r.n == N
    assert r.entrada_histograma["contagens"] or r.entrada_histograma["tipo"] == "categorico"
    assert r.saida_histograma["contagens"]

    if carga_1min > LIMITE_CARGA:
        pytest.skip(
            f"cláusula de desempenho NÃO MEDIDA: carga_1min={carga_1min:.1f} > {LIMITE_CARGA} "
            f"(máquina em disputa; tempo observado {r.tempo_ms:.1f} ms não é prova sob esta carga)"
        )
    assert r.tempo_ms <= LIMITE_MS, (
        f"pré-visualização de {N} valores ({tipo}) levou {r.tempo_ms:.1f} ms (> {LIMITE_MS} ms), "
        f"carga_1min={carga_1min:.1f} (calma, não é desculpa da casa)"
    )
