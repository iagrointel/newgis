"""Equivalência SQL × numpy da biblioteca declarativa de transformações (item L3-01-d-transformacoes).

Para cada um dos 16 tipos do esquema, aplica a MESMA amostra às duas implementações — `app.amc.
transformacoes.transformar` (numpy, pré-visualização/recomputação) e `plat.amc_transformar_num`/
`plat.amc_transformar_cat` (PL-pgSQL, `db/migracoes/20260907T1602_amc_transformacoes.sql`,
materialização) — e exige |Δ| ≤ 0,01 célula a célula (portão de pronto, cláusula 1). Precisa da base da
trilha (`conexao_plat_app`, ver tests/conftest.py); sem `.env` a suíte pula com aviso, não falha.
"""

import json
import math

import numpy as np
import pytest

from app.amc import transformacoes as tr

TOLERANCIA = 0.01


def _sql_num(cur, valor, transformacao: dict):
    cur.execute("SELECT plat.amc_transformar_num(%s, %s::jsonb) AS r",
                (None if valor is None or (isinstance(valor, float) and math.isnan(valor)) else float(valor),
                 json.dumps(transformacao)))
    r = cur.fetchone()["r"]
    return None if r is None else float(r)


def _sql_cat(cur, valor, transformacao: dict):
    cur.execute("SELECT plat.amc_transformar_cat(%s, %s::jsonb) AS r", (valor, json.dumps(transformacao)))
    r = cur.fetchone()["r"]
    return None if r is None else float(r)


def _comparar(cur, amostra, transformacao: dict, categorica: bool = False) -> float:
    """Compara célula a célula; devolve a maior diferença absoluta observada (para gravar em medidas)."""
    numpy_saida = tr.transformar(amostra, transformacao)
    maior_delta = 0.0
    for i, v in enumerate(amostra):
        esperado = numpy_saida[i]
        esperado = None if (esperado is None or (isinstance(esperado, float) and math.isnan(esperado))) else float(
            esperado)
        sql_val = _sql_cat(cur, v, transformacao) if categorica else _sql_num(cur, v, transformacao)
        if esperado is None or sql_val is None:
            assert esperado is None and sql_val is None, f"valor {v!r}: numpy={esperado!r} sql={sql_val!r}"
        else:
            delta = abs(esperado - sql_val)
            maior_delta = max(maior_delta, delta)
            assert delta <= TOLERANCIA, (
                f"valor {v!r}: numpy={esperado!r} sql={sql_val!r} diferença {delta!r}"
            )
    return maior_delta


CASOS = {
    "categoria": ({"tipo": "categoria", "notas": {"a": 10, "b": 90, "c": 50}, "outros": 5},
                  ["a", "b", "c", "d", None], True),
    "faixas": ({"tipo": "faixas", "quebras": [0, 10, 50], "notas": [100, 80, 40, 10]},
               [-5, 0, 5, 10, 30, 50, 90, None], False),
    "linear": ({"tipo": "linear", "minimo": 0, "maximo": 10, "direcao": "crescente", "abaixo": 0, "acima": 100},
               [-5, 0, 2.5, 5, 7.5, 10, 15, None], False),
    "linear_decrescente_remap": (
        {"tipo": "linear", "minimo": 300, "maximo": 5000, "direcao": "decrescente", "saida_min": 10,
         "saida_max": 100, "abaixo": 100, "acima": 10},
        [100, 300, 1000, 2500, 5000, 6000, None], False),
    "linear_simetrica": ({"tipo": "linear_simetrica", "minimo": 0, "maximo": 10, "abaixo": 0},
                          [-2, 0, 3, 5, 7, 10, 12, None], False),
    "degraus": ({"tipo": "degraus", "bandas": [{"ate": 15, "nota": 100}, {"ate": 30, "nota": 80},
                                               {"ate": 45, "nota": 50}, {"ate": 60, "nota": 30}], "acima": 10},
                [5, 15, 20, 29, 30, 45, 55, 60, 90, None], False),
    "potencia": ({"tipo": "potencia", "minimo": 0, "maximo": 10, "expoente": 2.5, "deslocamento": 0,
                  "abaixo": 0, "acima": 100},
                 [-1, 0, 2, 5, 8, 10, 12, None], False),
    "logaritmo": ({"tipo": "logaritmo", "minimo": 0, "maximo": 100, "fator": 8, "deslocamento": 0},
                  [0, 1, 10, 50, 100, 150, None], False),
    "exponencial": ({"tipo": "exponencial", "minimo": 0, "maximo": 100, "base": 3.0, "deslocamento": 0},
                    [0, 10, 50, 90, 100, None], False),
    "crescimento_logistico": ({"tipo": "crescimento_logistico", "minimo": 0, "maximo": 100,
                               "y_intercepto_percentual": 1.0},
                              [0, 10, 50, 90, 100, None], False),
    "decaimento_logistico": ({"tipo": "decaimento_logistico", "minimo": 0, "maximo": 100,
                              "y_intercepto_percentual": 1.0},
                             [0, 10, 50, 90, 100, None], False),
    "gaussiana": ({"tipo": "gaussiana", "midpoint": 50, "spread": 0.002},
                  [0, 25, 50, 75, 100, None], False),
    "proxima": ({"tipo": "proxima", "midpoint": 50, "spread": 0.00001},
                [0, 25, 50, 75, 100, None], False),
    "grande": ({"tipo": "grande", "midpoint": 50, "spread": 0.1},
               [0, 25, 50, 75, 100, None], False),
    "pequena": ({"tipo": "pequena", "midpoint": 50, "spread": 0.1},
                [0, 25, 50, 75, 100, None], False),
    "ms_grande": ({"tipo": "ms_grande", "media": 50.0, "desvio": 10.0, "multiplicador_media": 1.0,
                  "multiplicador_desvio": 1.0},
                  [0, 30, 50, 70, 100, None], False),
    "ms_pequena": ({"tipo": "ms_pequena", "media": 50.0, "desvio": 10.0, "multiplicador_media": 1.0,
                   "multiplicador_desvio": 1.0},
                   [0, 30, 50, 70, 100, None], False),
}


@pytest.fixture
def cur(conexao_plat_app):
    # SEM cursor_factory aqui: a conexão já nasce com CursorSchemaAmbiente (tests/conftest.py) — passar
    # RealDictCursor por cima troca o cursor por um que NÃO reescreve `plat.` para o schema da trilha,
    # e a consulta bate no `plat` de produção (sem GRANT para o papel da trilha, 403 -> InsufficientPrivilege).
    with conexao_plat_app.cursor() as c:
        yield c


@pytest.mark.parametrize("tipo", sorted(CASOS))
def test_equivalencia_sql_numpy(cur, tipo, medida):
    transformacao, amostra, categorica = CASOS[tipo]
    maior_delta = _comparar(cur, amostra, transformacao, categorica)
    medida("L3-01-d-transformacoes")(
        f"equivalencia_sql_numpy_{tipo}_max_delta", round(maior_delta, 6), "pontos de favorabilidade",
        f"pytest tests/unit/test_amc_transformacoes.py::test_equivalencia_sql_numpy[{tipo}] "
        f"(tolerância {TOLERANCIA})",
    )


def test_todos_os_16_tipos_cobertos():
    """Os 16 tipos do esquema (docs/esquemas/amc_modelo.v1.json) têm caso de teste — se um tipo novo
    entrar no esquema sem entrar aqui, este teste denuncia o buraco."""
    tipos_esquema = {"categoria", "faixas", "linear", "degraus"} | set(tr.FUNCOES_CONTINUAS)
    tipos_com_caso = set(CASOS) - {"linear_decrescente_remap"}  # variante extra do mesmo tipo 'linear'
    assert tipos_esquema == tipos_com_caso, tipos_esquema.symmetric_difference(tipos_com_caso)


# ------------------------------------------------------------------------------- amostra grande aleatória
@pytest.mark.parametrize("tipo,transformacao", [
    ("linear", {"tipo": "linear", "minimo": -100, "maximo": 100}),
    ("gaussiana", {"tipo": "gaussiana", "midpoint": 0, "spread": 0.0005}),
    ("crescimento_logistico", {"tipo": "crescimento_logistico", "minimo": -100, "maximo": 100,
                               "y_intercepto_percentual": 2.0}),
    ("grande", {"tipo": "grande", "midpoint": 0, "spread": 0.05}),
])
def test_equivalencia_amostra_aleatoria(cur, tipo, transformacao):
    rng = np.random.default_rng(20260907)
    amostra = rng.uniform(-300, 300, size=200).tolist()
    amostra[0] = float("nan")
    amostra += [None]
    _comparar(cur, amostra, transformacao)
