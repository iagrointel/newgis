"""Item L2-07-b: a tradução XPath (XLSForm) -> linguagem própria é conferida contra a tabela de equivalência com
vetores compartilhados com o L2-10-c (`tests/expressoes/vetores_xlsform.json`, >= 100). Cada vetor traz o XPath, o
contexto e a saída esperada; o teste traduz, avalia em Python E manda o MESMO texto traduzido ao avaliador
JavaScript (`tests/expressoes/executar_js.mjs --stdin`, o runner do L2-10-c) e exige as três saídas iguais.
Vetores marcados `fora` têm de ficar sem tradução (nunca tradução silenciosa de função sem equivalente)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VETORES = ROOT / "tests" / "expressoes" / "vetores_xlsform.json"
RUNNER_JS = ROOT / "tests" / "expressoes" / "executar_js.mjs"

sys.path.insert(0, str(ROOT))
from app.coleta.xpath import FEITO, FORA, PARCIAL, ErroXPath, tabela_equivalencia, traduzir  # noqa: E402
from app.expressao.avaliador_py import avaliar_texto  # noqa: E402


def _vetores() -> list[dict]:
    return json.loads(VETORES.read_text(encoding="utf-8"))


def _canon(valor):
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, list):
        return [_canon(v) for v in valor]
    return valor


def _traduziveis() -> list[dict]:
    return [v for v in _vetores() if not v.get("fora")]


@pytest.fixture(scope="module")
def resultados_js() -> list[dict]:
    entrada = [{"entrada": traduzir(v["xlsform"]).texto, "contexto": v.get("contexto") or {}} for v in _traduziveis()]
    r = subprocess.run(
        ["node", str(RUNNER_JS), "--stdin"], input=json.dumps(entrada, ensure_ascii=True),
        capture_output=True, text=True, timeout=60, cwd=str(ROOT), check=True,
    )
    return json.loads(r.stdout)


def test_ao_menos_100_vetores():
    assert len(_vetores()) >= 100


@pytest.mark.parametrize("vetor", _vetores(), ids=lambda v: v["descricao"])
def test_traducao_e_avaliacao_em_python(vetor):
    tr = traduzir(vetor["xlsform"])
    if vetor.get("fora"):
        assert tr.texto is None, f"deveria ficar fora: {tr.texto}"
        assert any(a.estado == FORA for a in tr.avisos)
        return
    assert tr.texto == vetor["texto"], "a tradução gravada no vetor mudou"
    assert _canon(avaliar_texto(tr.texto, vetor.get("contexto") or {})) == _canon(vetor["saida"])


def test_javascript_concorda_com_python(resultados_js):
    vetores = _traduziveis()
    assert len(resultados_js) == len(vetores)
    divergencias = []
    for v, js in zip(vetores, resultados_js, strict=True):
        if js.get("erro"):
            divergencias.append((v["descricao"], "erro JS", js["erro"]))
        elif _canon(js.get("resultado")) != _canon(v["saida"]):
            divergencias.append((v["descricao"], js.get("resultado"), v["saida"]))
    assert not divergencias, divergencias


def test_tabela_de_equivalencia_cobre_as_funcoes_mais_usadas():
    tabela = {linha["funcao"]: linha["estado"] for linha in tabela_equivalencia()}
    for f in ("if", "selected", "count", "sum", "today", "now", "string-length", "round", "regex", "pulldata"):
        assert f in tabela
    assert tabela["regex"] == FORA and tabela["pulldata"] == PARCIAL and tabela["if"] == FEITO


def test_erro_de_sintaxe_e_nomeado():
    with pytest.raises(ErroXPath):
        traduzir("${a} +")
    with pytest.raises(ErroXPath):
        traduzir("if(${a}, 1)")
