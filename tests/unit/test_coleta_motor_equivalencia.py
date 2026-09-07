"""Item L2-07-b: o motor do navegador (`web/js/coleta/motor.js`) e o do servidor (`app/coleta/motor.py`) chegam ao
MESMO resultado — cálculos, relevância (campo não relevante anulado), restrições, obrigatoriedade, cascata e
repetições — sobre os cinco XLSForms de teste e o mesmo conjunto de respostas. Também: o cálculo circular é
detectado dos dois lados com o mesmo código."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
XLSFORMS = ROOT / "tests" / "coleta" / "xlsforms"
RUNNER = ROOT / "tests" / "coleta" / "executar_motor.mjs"
sys.path.insert(0, str(ROOT))
from app.coleta import motor, xlsform  # noqa: E402
from app.coleta.documento import ordem_de_calculo  # noqa: E402
from app.erros import ErroAPI  # noqa: E402

CASOS = [
    ("basico.xlsx", {"nome": "Ana", "idade": 30, "data_visita": "2026-09-07", "aceita": "sim", "fontes": "poco rio"}, {}),
    ("basico.xlsx", {"idade": "x"}, {}),
    ("regras.xlsx", {"idade": 200, "tem_filhos": "sim", "n_filhos": 0}, {}),
    ("regras.xlsx", {"idade": 15, "tem_filhos": "nao", "n_filhos": 5, "email": "sem-arroba", "documento": "1"}, {}),
    ("regras.xlsx", {"idade": 40, "tem_filhos": "sim", "n_filhos": 2, "email": "a@b.c"}, {}),
    ("calculos.xlsx", {"largura": 2.5, "comprimento": 3.3, "preco_m2": 100}, {}),
    ("calculos.xlsx", {"largura": 50, "comprimento": 30}, {}),
    ("cascata.xlsx", {"estado": "ba", "municipio": "ssa", "bairro": "ssa_pit"}, {}),
    ("cascata.xlsx", {"estado": "ba", "municipio": "spo", "bairro": "spo_pin"}, {}),
    ("cascata.xlsx", {"estado": "rs"}, {}),
    ("repeticao.xlsx", {"domicilio": "D-1"},
     {"membros": [{"nome_m": "Ana", "idade_m": 40, "trabalha": "sim"}, {"nome_m": "Bia", "idade_m": 10, "trabalha": "sim"},
                  {"nome_m": "Caio", "idade_m": 3}]}),
    ("repeticao.xlsx", {"domicilio": "D-2"}, {"membros": [{"nome_m": "X", "idade_m": 999}, {"idade_m": 5}]}),
    ("repeticao.xlsx", {}, {}),
]


def _docs() -> dict[str, dict]:
    return {n: xlsform.importar((XLSFORMS / n).read_bytes(), n) for n in {c[0] for c in CASOS}}


def _canon(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    return v


@pytest.fixture(scope="module")
def resultados_js() -> list[dict]:
    docs = _docs()
    entrada = [{"documento": docs[n], "valores": v, "repeticoes": r} for n, v, r in CASOS]
    saida = subprocess.run(["node", str(RUNNER)], input=json.dumps(entrada, ensure_ascii=True), capture_output=True,
                           text=True, timeout=60, cwd=str(ROOT), check=True)
    return json.loads(saida.stdout)


@pytest.mark.parametrize("i", range(len(CASOS)), ids=[f"{c[0]}#{k}" for k, c in enumerate(CASOS)])
def test_motor_js_igual_ao_python(resultados_js, i):
    nome, valores, reps = CASOS[i]
    doc = _docs()[nome]
    py = motor.avaliar_resposta(doc, valores, reps)
    js = resultados_js[i]
    assert "erro" not in js, js
    assert js["ordem"] == doc["ordem_calculo"]
    relevantes_py = {k: v for k, v in py.valores.items() if k in py.relevantes}
    for k, v in relevantes_py.items():
        assert _canon(js["valores"].get(k)) == _canon(v), (k, js["valores"].get(k), v)
    for k in py.valores:
        if k not in py.relevantes:
            assert js["valores"].get(k) in (None, ""), (k, js["valores"].get(k))
    assert _canon(js["repeticoes"]) == _canon(py.repeticoes)
    chave = lambda e: (e.get("repeticao") or "", e.get("indice") or 0, e["campo"], e["erro"])  # noqa: E731
    assert sorted(map(chave, js["erros"])) == sorted(map(chave, py.erros))


def test_ciclo_detectado_nos_dois_lados():
    with pytest.raises(ErroAPI) as e:
        xlsform.importar((XLSFORMS / "circular.xlsx").read_bytes(), "circular.xlsx")
    assert e.value.erro == "dependencia_circular"
    # o mesmo documento com o ciclo montado à mão passa pelo JS e cai no mesmo código
    doc = xlsform.importar((XLSFORMS / "calculos.xlsx").read_bytes(), "calculos.xlsx")
    from app.coleta.documento import regra_de

    for c in doc["campos"]:
        if c["nome"] == "area":
            c["calculo"] = regra_de("$valor + 1")
    with pytest.raises(ErroAPI):
        ordem_de_calculo(doc)
    saida = subprocess.run(["node", str(RUNNER)], input=json.dumps([{"documento": doc, "valores": {}, "repeticoes": {}}]),
                           capture_output=True, text=True, timeout=60, cwd=str(ROOT), check=True)
    js = json.loads(saida.stdout)[0]
    assert js["erro"] == "dependencia_circular" and set(js["campos"]) >= {"area", "valor"}
