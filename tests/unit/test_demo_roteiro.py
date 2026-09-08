"""Unitários do roteiro de demonstração (item L7-29-roteiro-demonstração).

Exercem docs/gerar_demo.py e as cláusulas estruturais do portão que vivem no repositório: 9 passos
com "o que dizer" e "não prometer", tempos somando o roteiro de 30 minutos, versão de 10 minutos
como subconjunto na ordem, a lista "o que a demonstração não faz ainda" GERADA de laco/PAINEL.md
(divergente reprova), a regra de escrita de 03/09 verificável por máquina e o e2e citado existindo
com captura por passo. O tempo total medido (≤ 30 min) é cláusula do e2e, tests/e2e/test_demo.py."""

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
GERADOR = RAIZ / "docs" / "gerar_demo.py"
DEMO = RAIZ / "docs" / "DEMO.md"
E2E = RAIZ / "tests" / "e2e" / "test_demo.py"


def gerador():
    spec = importlib.util.spec_from_file_location("gerar_demo_l729", GERADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_nove_passos_com_dizer_nao_prometer_e_tempo_de_30():
    g = gerador()
    passos = g.parse_passos(DEMO.read_text(encoding="utf-8"))
    assert sorted(passos) == list(range(1, 10)), sorted(passos)
    soma = sum(p["minutos"] for p in passos.values())
    assert soma <= 30, f"o roteiro promete no máximo 30 min e declara {soma}"
    for n, p in sorted(passos.items()):
        assert p["dizer"], f"passo {n} sem 'o que dizer'"
        assert p["nao_prometer"], f"passo {n} sem 'não prometer'"
        assert p["e2e"] == "tests/e2e/test_demo.py", f"passo {n} sem o e2e do roteiro"
    g.validar()


def test_versao_de_10_minutos_e_subconjunto_na_ordem():
    g = gerador()
    demo = DEMO.read_text(encoding="utf-8")
    passos = g.parse_passos(demo)
    versao10 = g.parse_versao10(demo)
    assert versao10, "docs/DEMO.md sem '## Versão de 10 minutos'"
    numeros = [n for n, _ in versao10]
    assert numeros == sorted(numeros), "versão de 10 minutos fora da ordem dos passos"
    assert all(n in passos for n in numeros), "versão de 10 minutos cita passo inexistente"
    assert sum(m for _, m in versao10) <= 10, "versão de 10 minutos passou de 10"


def test_bloco_nao_faz_ainda_gerado_do_painel_esta_atualizado():
    """a lista do fim do documento é GERADA de laco/PAINEL.md; editou o painel e não regenerou, reprova."""
    g = gerador()
    demo = DEMO.read_text(encoding="utf-8")
    commitado = g.bloco_commitado(demo)
    assert commitado is not None, "docs/DEMO.md sem os marcadores do bloco gerado"
    gerado = g.bloco_gerado().strip("\n")
    assert commitado == gerado, (
        "bloco 'não faz ainda' diverge de laco/PAINEL.md; rode venv/bin/python docs/gerar_demo.py --preencher"
    )
    # a lista cobre as linhas de produto do painel com pendência (a fronteira inteira, verbatim)
    linhas_do_painel = g.fronteira_do_painel().count("Não faz ainda")
    assert commitado.count("Não faz ainda") == linhas_do_painel


def test_preencher_e_idempotente():
    g = gerador()
    antes = DEMO.read_text(encoding="utf-8")
    g.preencher()
    depois = DEMO.read_text(encoding="utf-8")
    assert antes == depois, "--preencher numa árvore atualizada não devia mudar nada"


DEMO_MINIMO = """# Roteiro

## Passo 1 — A porta de entrada (1 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: A instalação responde.
- não prometer: {violacao}

## Versão de 10 minutos

- Passo 1 (1 min) — versão.

<!-- gerado de laco/PAINEL.md:inicio -->
{bloco}
<!-- gerado de laco/PAINEL.md:fim -->
"""


@pytest.mark.parametrize("violacao,trecho", [
    ("Você recebe o dossiê.", "você recebe"),
    ("O mapa tem uma maquiagem de dados.", "maquiagem"),
    ("É robusto e impressionante!", "exclamação ou superlativo"),
])
def test_validador_reprova_violacao_da_regra_de_escrita(tmp_path, monkeypatch, violacao, trecho):
    g = gerador()
    fake = tmp_path / "DEMO.md"
    fake.write_text(DEMO_MINIMO.format(violacao=violacao, bloco=g.bloco_gerado()), encoding="utf-8")
    monkeypatch.setattr(g, "DEMO", fake)
    with pytest.raises(SystemExit, match="regra de escrita"):
        g.validar()


def test_validador_reprova_passo_sem_nao_prometer(tmp_path, monkeypatch):
    g = gerador()
    fake = tmp_path / "DEMO.md"
    texto = DEMO_MINIMO.format(violacao="nada", bloco=g.bloco_gerado()).replace(
        "- não prometer: nada\n", "")
    fake.write_text(texto, encoding="utf-8")
    monkeypatch.setattr(g, "DEMO", fake)
    with pytest.raises(SystemExit, match="sem \\['nao_prometer'\\]"):
        g.validar()


def test_validador_reprova_bloco_desatualizado(tmp_path, monkeypatch):
    g = gerador()
    fake = tmp_path / "DEMO.md"
    fake.write_text(DEMO_MINIMO.format(violacao="nada", bloco="lista velha"), encoding="utf-8")
    monkeypatch.setattr(g, "DEMO", fake)
    with pytest.raises(SystemExit, match="diverge"):
        g.validar()


def test_e2e_percorre_todo_passo_com_captura():
    e2e = E2E.read_text(encoding="utf-8")
    for n in range(1, 10):
        assert f"p{n:02d}_" in e2e, f"o e2e não tem o passo {n:02d} do roteiro"
        assert f'capturar("p{n:02d}' in e2e, f"o passo {n:02d} do roteiro não tem captura no e2e"
    assert "TEMPO_LIMITE_S = 30 * 60" in e2e
