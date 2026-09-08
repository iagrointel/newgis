"""Refutação exigida pelo item L3-01-g-tela-motor, provada FORA do navegador: o link com pesos adulterados
(peso 999, fator inexistente, soma percentual 130) é RECUSADO com explicação, nunca calculado em silêncio.

O módulo sob teste é `web/js/amc/pesos_url.js` — exatamente o que a tela carrega — corrido por node
(tests/amc/executar_pesos_url.mjs), como já se faz com o combinador em tests/unit/test_amc_combinacao_*.py.
As mesmas três recusas são exercidas na tela inteira em tests/e2e/test_amc_motor.py; aqui a prova é da regra,
lá é da tela. As regras conferidas contra o servidor (`app.amc.esquema.validar_pesos`) estão no último teste:
o que o navegador recusa, o servidor também recusa — nunca o contrário."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.amc.esquema import validar_pesos
from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "amc" / "executar_pesos_url.mjs"
FATORES = [
    {"id": "declividade", "peso_modelo": 3.0},
    {"id": "dist_via", "peso_modelo": 1.5},
]


def js_disponivel() -> bool:
    return shutil.which("node") is not None


def rodar(casos: list[dict]) -> list[dict]:
    p = subprocess.run(["node", str(RUNNER)], input=json.dumps(casos), capture_output=True, text=True,
                       timeout=120, check=False)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


pytestmark = pytest.mark.skipif(not js_disponivel(), reason="node ausente nesta máquina")


def test_link_limpo_e_lido_e_volta_igual():
    (r,) = rodar([{"texto": "declividade:2,dist_via:0.5", "fatores": FATORES}])
    assert r["erros"] == []
    assert r["pesos"] == {"declividade": 2.0, "dist_via": 0.5}
    assert r["texto_de_volta"] == "declividade:2,dist_via:0.5"
    assert "w=declividade%3A2%2Cdist_via%3A0.5" in r["link"]


def test_sem_pesos_no_link_usa_os_do_modelo():
    (r,) = rodar([{"texto": "", "fatores": FATORES}])
    assert r["erros"] == []
    assert r["pesos"] == {"declividade": 3.0, "dist_via": 1.5}


def test_peso_999_e_recusado_com_o_maximo_dito():
    (r,) = rodar([{"texto": "declividade:999", "fatores": FATORES}])
    assert len(r["erros"]) == 1
    assert "999" in r["erros"][0] and str(r["peso_max"]) in r["erros"][0]
    assert r["pesos"]["declividade"] == 3.0  # o peso adulterado NÃO entrou


def test_fator_inexistente_e_recusado_pelo_nome():
    (r,) = rodar([{"texto": "fator_que_nao_existe:1", "fatores": FATORES}])
    assert len(r["erros"]) == 1
    assert "fator_que_nao_existe" in r["erros"][0]
    assert "fator_que_nao_existe" not in r["pesos"]


def test_soma_percentual_130_e_recusada_com_a_soma_dita():
    (r,) = rodar([{"texto": "declividade:100,dist_via:30", "fatores": FATORES, "combinador": "percentual"}])
    assert len(r["erros"]) == 1
    assert "130" in r["erros"][0] and "100" in r["erros"][0]


def test_soma_percentual_100_passa():
    (r,) = rodar([{"texto": "declividade:70,dist_via:30", "fatores": FATORES, "combinador": "percentual"}])
    assert r["erros"] == []


@pytest.mark.parametrize("texto,pedaco", [
    ("declividade:-1", "não é um número não negativo"),
    ("declividade:abc", "não é um número não negativo"),
    ("declividade:1e400", "não é um número não negativo"),
    ("declividade", "mal escrito"),
    ("declividade:1,declividade:2", "mais de uma vez"),
    ("declividade:0,dist_via:0", "soma dos pesos é zero"),
])
def test_cada_adulteracao_tem_recusa_propria(texto, pedaco):
    (r,) = rodar([{"texto": texto, "fatores": FATORES}])
    assert any(pedaco in e for e in r["erros"]), r["erros"]


def test_o_que_o_navegador_recusa_o_servidor_tambem_recusa():
    """Sem isto a tela poderia ser mais frouxa que a API e recolorir um mapa que a API não aceitaria."""
    definicao = {"fatores": [{"id": "declividade", "peso": 3.0}, {"id": "dist_via", "peso": 1.5}]}
    for pesos in ({"fator_que_nao_existe": 1.0}, {"declividade": -1.0},
                  {"declividade": 0.0, "dist_via": 0.0}):
        with pytest.raises(ErroAPI):
            validar_pesos(definicao, pesos)
    definicao_pct = {**definicao, "combinador": {"tipo": "percentual"}}
    with pytest.raises(ErroAPI):
        validar_pesos(definicao_pct, {"declividade": 100.0, "dist_via": 30.0})
