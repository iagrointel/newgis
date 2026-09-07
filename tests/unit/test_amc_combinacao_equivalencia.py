"""Verificação independente do combinador (item L3-01-e-combinacao).

Duas provas, ambas sobre as MESMAS 200 unidades × 19 fatores sorteadas com semente fixa:

1. recomputação em numpy escrita aqui do zero, sem importar nenhuma função de
   `app.amc.combinacao` além da porta de entrada `combinar` — se a mesma função fosse reaproveitada,
   o teste não provaria nada. Tolerância: diferença absoluta máxima de 0,5 na escala 0-100;
2. equivalência com a implementação JavaScript (`web/js/amc/combinacao.js`), que é o que roda no
   navegador, pela mesma tolerância.

Os pesos usados aqui são sorteados só para exercitar a conta. Em produção eles são escolhidos pelo
usuário por projeto; nada neste arquivo os mede, calcula ou otimiza.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.amc.combinacao import COMBINADORES, combinar

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "amc" / "executar_js.mjs"
UNIDADES, FATORES = 200, 19
TOLERANCIA = 0.5


def caso_base(semente: int = 20260907):
    """200 unidades × 19 fatores na escala 0-100, com 12 % de célula sem dado e uma unidade toda vazia."""
    rng = np.random.default_rng(semente)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES, FATORES))
    m[rng.uniform(size=m.shape) < 0.12] = np.nan
    m[0, :] = np.nan  # unidade sem nenhum dado
    m[1, :] = 0.0  # unidade toda em zero (a média geométrica tem de anular)
    pesos = rng.uniform(0.1, 5.0, size=FATORES)
    return m, pesos


def referencia(m, pesos, combinador, politica="excluir", gama=0.5):
    """Recomputação independente, escrita a partir da definição de cada combinador — não chama o produto."""
    n, k = m.shape
    total = float(np.sum(pesos))
    saida = []
    for i in range(n):
        linha = list(m[i])
        w = list(pesos)
        if politica == "pessimista":
            linha = [0.0 if math.isnan(v) else v for v in linha]
        elif politica == "nulo" and any(math.isnan(v) for v in linha):
            saida.append(float("nan"))
            continue
        pares = [(wi, v) for wi, v in zip(w, linha, strict=True) if not math.isnan(v)]
        if not pares:
            saida.append(float("nan"))
            continue
        sw = sum(wi for wi, _ in pares)
        if combinador == "soma_ponderada":
            saida.append(sum(wi * v for wi, v in pares) / sw)
        elif combinador == "percentual":
            # os pesos chegam já em porcentagem que fecha 100; a paridade arredonda ao inteiro
            saida.append(round(sum(wi * v for wi, v in pares) / sw))
        elif combinador == "media_geometrica":
            if any(v <= 0 for _, v in pares):
                saida.append(0.0)
            else:
                saida.append(math.exp(sum(wi * math.log(v) for wi, v in pares) / sw))
        elif combinador == "minimo":
            saida.append(min(v for _, v in pares))
        elif combinador == "maximo":
            saida.append(max(v for _, v in pares))
        elif combinador == "produto":
            p = 1.0
            for _, v in pares:
                p *= v / 100.0
            saida.append(p * 100.0)
        elif combinador == "soma_fuzzy":
            p = 1.0
            for _, v in pares:
                p *= 1.0 - v / 100.0
            saida.append((1.0 - p) * 100.0)
        elif combinador == "gama":
            p = 1.0
            c = 1.0
            for _, v in pares:
                p *= v / 100.0
                c *= 1.0 - v / 100.0
            saida.append(((1.0 - c) ** gama) * (p ** (1.0 - gama)) * 100.0)
        else:
            raise AssertionError("combinador fora da lista: " + combinador)
        _ = k, total
    return np.array(saida, dtype=float)


def compara(a, b, rotulo):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    assert a.shape == b.shape
    nulo_a, nulo_b = ~np.isfinite(a), ~np.isfinite(b)
    assert np.array_equal(nulo_a, nulo_b), f"{rotulo}: as unidades sem nota não são as mesmas"
    if (~nulo_a).any():
        d = float(np.max(np.abs(a[~nulo_a] - b[~nulo_a])))
        assert d <= TOLERANCIA, f"{rotulo}: diferença absoluta máxima {d:.6f} passou de {TOLERANCIA}"
        return d
    return 0.0


@pytest.mark.parametrize("combinador", sorted(COMBINADORES))
def test_recomputacao_independente_em_numpy_em_200_unidades(combinador):
    m, pesos = caso_base()
    p = list(100.0 * pesos / pesos.sum()) if combinador == "percentual" else list(pesos)
    obtido = combinar(m, p, combinador=combinador).fav
    compara(obtido, referencia(m, p, combinador), f"numpy × produto ({combinador})")


@pytest.mark.parametrize("politica", ["excluir", "nulo", "pessimista"])
def test_recomputacao_independente_para_cada_politica_de_dado_ausente(politica):
    m, pesos = caso_base()
    obtido = combinar(m, list(pesos), politica_ausente=politica).fav
    compara(obtido, referencia(m, list(pesos), "soma_ponderada", politica), f"numpy × produto ({politica})")


def js_disponivel():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not js_disponivel(), reason="node ausente nesta máquina")
def test_o_javascript_do_navegador_da_o_mesmo_resultado_do_servidor():
    m, pesos = caso_base()
    casos, esperados = [], []
    for combinador in sorted(COMBINADORES):
        p = list(100.0 * pesos / pesos.sum()) if combinador == "percentual" else list(pesos)
        for politica in ["excluir", "nulo", "pessimista"]:
            casos.append({
                "fatores": [[None if math.isnan(v) else float(v) for v in linha] for linha in m],
                "pesos": p,
                "opcoes": {"combinador": combinador, "politicaAusente": politica},
            })
            esperados.append((combinador, politica, combinar(m, p, combinador=combinador, politica_ausente=politica)))
    saida = subprocess.run(
        ["node", str(RUNNER), "--stdin"],
        input=json.dumps(casos), capture_output=True, text=True, check=True, cwd=ROOT,
    )
    js = json.loads(saida.stdout)
    assert len(js) == len(esperados)
    for (combinador, politica, r), lado_js in zip(esperados, js, strict=True):
        assert lado_js["erro"] is None, f"{combinador}/{politica}: {lado_js['erro']}"
        assert lado_js["aviso_pesos"] == r.aviso_pesos
        compara(
            [np.nan if v is None else v for v in lado_js["fav"]],
            r.fav,
            f"javascript × python ({combinador}/{politica})",
        )
        assert lado_js["observacoes"] == r.observacoes
    print(f"equivalência conferida em {len(js)} combinações × {UNIDADES} unidades", file=sys.stderr)
