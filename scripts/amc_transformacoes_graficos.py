#!/usr/bin/env python3
"""Gera, para cada um dos 16 tipos de transformação (item L3-01-d-transformacoes), um gráfico SVG
valor bruto (x) -> favorabilidade (y) com a fórmula declarada no título, em
`docs/graficos/amc_transformacoes/<tipo>.svg`. Referenciado por `MANUAL.md`. Não abre banco.

Uso: venv/bin/python scripts/amc_transformacoes_graficos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_PARA_IMPORT = Path(__file__).resolve().parents[1]
if str(ROOT_PARA_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_PARA_IMPORT))

import matplotlib  # noqa: E402 — precisa vir depois do sys.path.insert acima

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.amc import transformacoes as tr  # noqa: E402

ROOT = ROOT_PARA_IMPORT
SAIDA = ROOT / "docs" / "graficos" / "amc_transformacoes"

CASOS: dict[str, dict] = {
    "categoria": {
        "transformacao": {"tipo": "categoria", "notas": {"industrial": 100, "misto": 60, "residencial": 10},
                          "outros": 30},
        "formula": "notas[categoria] (ou 'outros' se a categoria não está na lista; NULL se nem isso)",
        "categorica": True,
    },
    "faixas": {
        "transformacao": {"tipo": "faixas", "quebras": [10, 30, 60], "notas": [100, 70, 40, 10]},
        "formula": "notas[i], onde quebras[i-1] < x ≤ quebras[i] (degrau, não linear)",
        "dominio": (-5, 80),
    },
    "linear": {
        "transformacao": {"tipo": "linear", "minimo": 10, "maximo": 90, "direcao": "crescente"},
        "formula": "y = 100 · clip((x − minimo) / (maximo − minimo), 0, 1)",
        "dominio": (-10, 110),
    },
    "linear_simetrica": {
        "transformacao": {"tipo": "linear_simetrica", "minimo": 0, "maximo": 100},
        "formula": "y = 100 · clip(1 − |x − meio| / (meio − minimo), 0, 1), meio = (minimo+maximo)/2",
        "dominio": (-20, 120),
    },
    "degraus": {
        "transformacao": {"tipo": "degraus", "bandas": [{"ate": 15, "nota": 100}, {"ate": 30, "nota": 80},
                                                        {"ate": 45, "nota": 50}, {"ate": 60, "nota": 30}],
                          "acima": 10},
        "formula": "nota da 1ª banda com ate ≥ x; acima da última, o valor de 'acima' (motor logístico de referência)",
        "dominio": (0, 90),
    },
    "potencia": {
        "transformacao": {"tipo": "potencia", "minimo": 0, "maximo": 100, "expoente": 2.5},
        "formula": "y = 100 · clip((x − minimo)/(maximo − minimo), 0, 1) ^ expoente",
        "dominio": (-10, 110),
    },
    "logaritmo": {
        "transformacao": {"tipo": "logaritmo", "minimo": 0, "maximo": 100, "fator": 8},
        "formula": "y = 100 · ln(1 + fator·t) / ln(1 + fator), t = clip((x−minimo)/(maximo−minimo), 0, 1)",
        "dominio": (-10, 110),
    },
    "exponencial": {
        "transformacao": {"tipo": "exponencial", "minimo": 0, "maximo": 100, "base": 4.0},
        "formula": "y = 100 · (base^t − 1)/(base − 1), t = clip((x−minimo)/(maximo−minimo), 0, 1)",
        "dominio": (-10, 110),
    },
    "crescimento_logistico": {
        "transformacao": {"tipo": "crescimento_logistico", "minimo": 0, "maximo": 100,
                          "y_intercepto_percentual": 2.0},
        "formula": "y = 100 / (1 + exp(−k(x−meio))), k resolvido para valer y_intercepto_percentual em x=minimo",
        "dominio": (-10, 110),
    },
    "decaimento_logistico": {
        "transformacao": {"tipo": "decaimento_logistico", "minimo": 0, "maximo": 100,
                          "y_intercepto_percentual": 2.0},
        "formula": "y = 100 − crescimento_logistico(x) (espelho)",
        "dominio": (-10, 110),
    },
    "gaussiana": {
        "transformacao": {"tipo": "gaussiana", "midpoint": 50, "spread": 0.002},
        "formula": "y = 100 · exp(−spread·(x − midpoint)²)",
        "dominio": (-50, 150),
    },
    "proxima": {
        "transformacao": {"tipo": "proxima", "midpoint": 50, "spread": 0.00001},
        "formula": "y = 100 · exp(−spread·(x − midpoint)⁴)  (Near: cai mais rápido que a gaussiana)",
        "dominio": (-50, 150),
    },
    "grande": {
        "transformacao": {"tipo": "grande", "midpoint": 50, "spread": 0.1},
        "formula": "y = 100 / (1 + exp(−spread·(x − midpoint)))",
        "dominio": (-50, 150),
    },
    "pequena": {
        "transformacao": {"tipo": "pequena", "midpoint": 50, "spread": 0.1},
        "formula": "y = 100 / (1 + exp(spread·(x − midpoint)))  (espelho de 'grande')",
        "dominio": (-50, 150),
    },
    "ms_grande": {
        "transformacao": {"tipo": "ms_grande", "media": 50, "desvio": 15, "multiplicador_media": 1.0,
                          "multiplicador_desvio": 1.0},
        "formula": "como 'grande', com midpoint = média×mult_média e spread = mult_desvio/desvio",
        "dominio": (-50, 150),
    },
    "ms_pequena": {
        "transformacao": {"tipo": "ms_pequena", "media": 50, "desvio": 15, "multiplicador_media": 1.0,
                          "multiplicador_desvio": 1.0},
        "formula": "como 'pequena', com midpoint = média×mult_média e spread = mult_desvio/desvio",
        "dominio": (-50, 150),
    },
}


def _grafico_numerico(tipo: str, caso: dict) -> None:
    lo, hi = caso["dominio"]
    x = np.linspace(lo, hi, 2000)
    y = tr.transformar(x.tolist(), caso["transformacao"])
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=110)
    ax.plot(x, y, color="#1f6f4a", linewidth=2)
    ax.set_title(f"{tipo}\n{caso['formula']}", fontsize=9)
    ax.set_xlabel("valor bruto (x)")
    ax.set_ylabel("favorabilidade (y)")
    ax.set_ylim(-5, 105)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / f"{tipo}.svg")
    plt.close(fig)


def _grafico_categorico(tipo: str, caso: dict) -> None:
    t = caso["transformacao"]
    categorias = list(t["notas"]) + ["(outra)"]
    valores = [t["notas"][c] for c in categorias[:-1]] + [t.get("outros", 0)]
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=110)
    ax.bar(categorias, valores, color="#1f6f4a")
    ax.set_title(f"{tipo}\n{caso['formula']}", fontsize=9)
    ax.set_ylabel("favorabilidade (y)")
    ax.set_ylim(0, 105)
    fig.tight_layout()
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / f"{tipo}.svg")
    plt.close(fig)


def gerar_todos() -> list[str]:
    gerados = []
    for tipo, caso in CASOS.items():
        if caso.get("categorica"):
            _grafico_categorico(tipo, caso)
        else:
            _grafico_numerico(tipo, caso)
        gerados.append(tipo)
    return gerados


if __name__ == "__main__":
    tipos = gerar_todos()
    faltando = ({"categoria", "faixas", "linear", "degraus"} | set(tr.FUNCOES_CONTINUAS)) - set(tipos)
    if faltando:
        raise SystemExit(f"tipos do esquema sem gráfico: {sorted(faltando)}")
    print(f"{len(tipos)} gráficos gerados em {SAIDA}")
