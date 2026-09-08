"""Ataque ao combinador do motor multicritério (item L3-01-e-combinacao, cláusula de refutação).

O ataque passa peso negativo, soma de pesos zero, NaN em peso e em fator, fator duplicado e unidade com
todos os fatores ausentes. Nenhuma dessas entradas pode sair com favorabilidade numérica: ou o pedido é
recusado com código de erro, ou a unidade fica sem nota. O mesmo ataque roda contra a implementação
JavaScript, que é a que o navegador executa; os dois lados têm de recusar pelo MESMO código.
"""

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.amc.combinacao import COMBINADORES, ErroCombinacao, combinar

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "amc" / "executar_js.mjs"

ATAQUES = [
    ("peso_negativo", [[10.0, 20.0]], [-1.0, 2.0], {}),
    ("peso_negativo", [[10.0, 20.0]], [1.0, -0.0001], {}),
    ("soma_de_pesos_zero", [[10.0, 20.0]], [0.0, 0.0], {}),
    ("peso_nao_finito", [[10.0, 20.0]], [float("nan"), 1.0], {}),
    ("peso_nao_finito", [[10.0, 20.0]], [float("inf"), 1.0], {}),
    ("pesos_incompativeis", [[10.0, 20.0]], [1.0], {}),
    ("fator_duplicado", [[10.0, 20.0]], [1.0, 1.0], {"ids_fatores": ["declividade", "declividade"]}),
    ("valor_fora_da_escala", [[101.0, 20.0]], [1.0, 1.0], {}),
    ("valor_fora_da_escala", [[-1.0, 20.0]], [1.0, 1.0], {}),
    ("valor_nao_finito", [[float("inf"), 20.0]], [1.0, 1.0], {}),
    ("percentual_nao_soma_100", [[10.0, 20.0]], [60.0, 60.0], {"combinador": "percentual"}),
    ("combinador_desconhecido", [[10.0]], [1.0], {"combinador": "media_harmonica"}),
    ("politica_ausente_desconhecida", [[10.0]], [1.0], {"politica_ausente": "otimista"}),
    ("gama_fora_da_faixa", [[10.0]], [1.0], {"combinador": "gama", "gama": 1.5}),
    ("fracao_vetada_invalida", [[10.0]], [1.0], {"fracao_vetada": [1.5]}),
    ("fracao_vetada_incompativel", [[10.0], [20.0]], [1.0], {"fracao_vetada": [0.5]}),
]


@pytest.mark.parametrize("codigo,fatores,pesos,opcoes", ATAQUES, ids=[f"{i}-{a[0]}" for i, a in enumerate(ATAQUES)])
def test_o_pedido_invalido_e_recusado_com_codigo_e_nao_devolve_numero(codigo, fatores, pesos, opcoes):
    with pytest.raises(ErroCombinacao) as e:
        combinar(fatores, pesos, **opcoes)
    assert e.value.codigo == codigo
    assert e.value.mensagem and e.value.mensagem[0].islower()


@pytest.mark.parametrize("combinador", sorted(COMBINADORES))
def test_nan_no_fator_e_ausencia_de_dado_e_nunca_vira_zero(combinador):
    pesos = [50.0, 50.0] if combinador == "percentual" else [1.0, 1.0]
    r = combinar([[float("nan"), float("nan")], [float("nan"), 80.0]], pesos, combinador=combinador)
    assert math.isnan(r.fav[0]), "unidade sem dado nenhum saiu com número"
    assert r.fav[1] == pytest.approx(80.0, abs=0.5)
    assert r.cobertura[0] == 0.0 and r.cobertura[1] == pytest.approx(0.5)


def test_coluna_inteira_sem_dado_nao_derruba_as_demais_unidades():
    m = np.array([[np.nan, 10.0], [np.nan, 90.0]])
    r = combinar(m, [3.0, 1.0])
    assert list(np.round(r.fav, 6)) == [10.0, 90.0]
    assert list(np.round(r.cobertura, 6)) == [0.25, 0.25]


def test_nenhum_resultado_sai_sem_a_frase_dos_pesos():
    d = combinar([[10.0, 20.0]], [1.0, 1.0]).como_dicionario()
    assert d["aviso_pesos"] == "pesos escolhidos pelo usuário, não medidos"
    assert "medido" not in d["descricao_combinador"] and "otimiz" not in d["descricao_combinador"]


def js_disponivel():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not js_disponivel(), reason="node ausente nesta máquina")
def test_o_javascript_recusa_os_mesmos_ataques_com_os_mesmos_codigos():
    chave = {"ids_fatores": "idsFatores", "politica_ausente": "politicaAusente", "fracao_vetada": "fracaoVetada"}

    def json_seguro(v):
        # JSON não tem Infinity nem NaN; o runner reconverte as cadeias em número (ver executar_js.mjs)
        if isinstance(v, float) and math.isnan(v):
            return "nan"
        if v == float("inf"):
            return "inf"
        if v == float("-inf"):
            return "-inf"
        return v

    casos = [
        {"fatores": [[json_seguro(v) for v in linha] for linha in fatores],
         "pesos": [json_seguro(p) for p in pesos],
         "opcoes": {chave.get(k, k): v for k, v in opcoes.items()}}
        for _, fatores, pesos, opcoes in ATAQUES
    ]
    saida = subprocess.run(["node", str(RUNNER), "--stdin"], input=json.dumps(casos),
                           capture_output=True, text=True, check=True, cwd=ROOT)
    js = json.loads(saida.stdout)
    for (codigo, *_), lado_js in zip(ATAQUES, js, strict=True):
        assert lado_js["erro"] == codigo, f"esperado {codigo}, veio {lado_js['erro']}"
