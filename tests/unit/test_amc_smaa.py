"""SMAA-2 simplificado do motor multicritério (item L3-02-c).

O caso central tem RESPOSTA CONHECIDA analiticamente, não conferida contra a própria implementação:
três unidades sintéticas e dois fatores, com peso sorteado uniformemente no simplex (Dirichlet com
alfa 1, que em duas dimensões é w1 ~ U(0, 1)).

    A = (100, 0)   nota 100·w1
    B = (0, 100)   nota 100·(1 − w1)
    C = (49, 49)   nota 49, constante

Daí sai, sem rodar nada:
  - A ganha quando 100·w1 > 100·(1 − w1) e 100·w1 > 49, ou seja w1 > 0,5 → aceitabilidade de 1º = 0,5;
  - B ganha por simetria → 0,5; C nunca ganha (precisaria de w1 < 0,49 e w1 > 0,51 ao mesmo tempo) → 0;
  - C fica em 2º sempre que |w1 − 0,5| > 0,01 → 0,98, e em 3º nos 2 % restantes;
  - o vetor central de A é a média de w em {w1 > 0,5}, que é (0,75; 0,25); o de B é (0,25; 0,75);
  - o fator de confiança de A é 1: com (0,75; 0,25) a nota de A é 75, contra 25 de B e 49 de C.
"""

import numpy as np
import pytest

from app.amc.smaa import LIMITES, REFERENCIA, ErroSmaa, simular_smaa

TRES_UNIDADES = [[100.0, 0.0], [0.0, 100.0], [49.0, 49.0]]
IDS = ["acesso", "declividade"]
NOMES = ["A", "B", "C"]
N = 20_000
TOL = 0.02  # erro de amostragem de 20 mil sorteios é ~0,004; a folga é 5 vezes isso


@pytest.fixture(scope="module")
def resultado():
    return simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=N, ids_fatores=IDS, semente=7, posicoes=3, topo=3)


def test_aceitabilidade_das_tres_unidades_bate_com_a_conta_analitica(resultado):
    b = resultado.aceitabilidade
    assert b[0, 0] == pytest.approx(0.50, abs=TOL)
    assert b[1, 0] == pytest.approx(0.50, abs=TOL)
    assert b[2, 0] == 0.0, "C não pode ganhar em nenhum sorteio"
    assert b[2, 1] == pytest.approx(0.98, abs=TOL), "C é segundo sempre que |w1 − 0,5| > 0,01"
    assert b[2, 2] == pytest.approx(0.02, abs=TOL)
    # cada sorteio distribui exatamente uma vez cada posição entre as unidades
    assert b.sum(axis=0) == pytest.approx(np.ones(3), abs=1e-12)


def test_vetor_central_e_fator_de_confianca_das_tres_unidades(resultado):
    assert resultado.vetor_central[0] == pytest.approx([0.75, 0.25], abs=TOL)
    assert resultado.vetor_central[1] == pytest.approx([0.25, 0.75], abs=TOL)
    assert np.all(np.isnan(resultado.vetor_central[2])), "sem primeiro lugar não há vetor central"
    assert resultado.fator_confianca[0] == 1.0 and resultado.fator_confianca[1] == 1.0
    assert np.isnan(resultado.fator_confianca[2])


def test_soma_da_aceitabilidade_de_primeiro_lugar_e_um(resultado):
    """A conferência que o adversário do item faz: 1 ± 0,01 somando TODAS as unidades."""
    assert resultado.soma_aceitabilidade_primeiro == pytest.approx(1.0, abs=0.01)
    assert resultado.sorteios_sem_vencedor == 0


def test_mesma_semente_reproduz_bit_a_bit():
    a = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=500, ids_fatores=IDS, semente=99, posicoes=3, topo=3)
    b = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=500, ids_fatores=IDS, semente=99, posicoes=3, topo=3)
    assert np.array_equal(a.aceitabilidade, b.aceitabilidade)
    assert np.allclose(a.vetor_central, b.vetor_central, equal_nan=True)
    outra = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=500, ids_fatores=IDS, semente=100, posicoes=3, topo=3)
    assert not np.array_equal(a.aceitabilidade, outra.aceitabilidade)


def test_explicacao_exibe_o_vetor_central_fator_a_fator(resultado):
    e = resultado.explicacao_da_unidade(0, NOMES)
    assert set(e["vetor_central"]) == set(IDS)
    assert e["vetor_central"]["acesso"] == pytest.approx(0.75, abs=TOL)
    for termo in ("A", "vetor central", "acesso", "declividade", "fator de confiança"):
        assert termo in e["texto"], termo
    assert e["referencia"] == REFERENCIA
    sem_central = resultado.explicacao_da_unidade(2, NOMES)
    assert sem_central["vetor_central"] is None
    assert "não ficou em primeiro lugar" in sem_central["texto"]
    with pytest.raises(ErroSmaa):
        resultado.explicacao_da_unidade(99, NOMES)


def test_tabela_do_topo_tem_vinte_linhas_e_vinte_posicoes():
    """Cláusula do portão: tabela de aceitabilidade para o top-20. 30 unidades, tabela de 20 linhas."""
    rng = np.random.default_rng(3)
    m = rng.uniform(0, 100, size=(30, 4))
    r = simular_smaa(m, [1, 1, 1, 1], n=2000, ids_fatores=[f"f{i}" for i in range(4)], semente=11)
    assert r.posicoes == 20 and r.topo == 20
    tabela = r.tabela_do_topo([f"u{i}" for i in range(30)])
    assert len(tabela) == 20
    assert [linha["posicao_na_tabela"] for linha in tabela] == list(range(1, 21))
    assert all(len(linha["aceitabilidade"]) == 20 for linha in tabela)
    # a tabela vem ordenada por aceitabilidade de primeiro lugar, decrescente
    b1 = [linha["aceitabilidade_primeiro"] for linha in tabela]
    assert b1 == sorted(b1, reverse=True)
    # e o vetor central aparece na linha, que é o que a explicação exibe
    assert tabela[0]["vetor_central"] is not None
    assert sum(tabela[0]["vetor_central"].values()) == pytest.approx(1.0, abs=1e-9)
    assert r.soma_aceitabilidade_primeiro == pytest.approx(1.0, abs=0.01)


def test_unidade_vetada_sai_por_construcao_e_nunca_ganha():
    r = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=1000, ids_fatores=IDS, semente=5, posicoes=3, topo=3,
                     fracao_vetada=[1.0, 0.0, 0.0])
    assert r.aceitabilidade[0].sum() == 0.0, "unidade vetada não entra em posição nenhuma"
    # sem A, sobram B (nota 100·(1 − w1)) e C (nota 49): B ganha quando w1 < 0,51 → 0,51 contra 0,49
    assert r.aceitabilidade[1, 0] == pytest.approx(0.51, abs=0.05)
    assert r.aceitabilidade[2, 0] == pytest.approx(0.49, abs=0.05)
    assert bool(r.vetado[0]) and not bool(r.vetado[1])
    assert np.all(np.isnan(r.vetor_central[0]))
    assert r.soma_aceitabilidade_primeiro == pytest.approx(1.0, abs=0.01)


def test_unidade_sem_nota_nao_entra_no_ranking():
    m = [[100.0, 0.0], [0.0, 100.0], [None, None]]
    r = simular_smaa(m, [0.5, 0.5], n=500, ids_fatores=IDS, semente=13, posicoes=3, topo=3,
                     politica_ausente="nulo")
    assert r.aceitabilidade[2].sum() == 0.0
    assert r.soma_aceitabilidade_primeiro == pytest.approx(1.0, abs=0.01)


def test_todas_vetadas_nao_inventa_vencedor():
    r = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=200, ids_fatores=IDS, semente=17, posicoes=3, topo=3,
                     fracao_vetada=[1.0, 1.0, 1.0])
    assert r.soma_aceitabilidade_primeiro == 0.0
    assert r.sorteios_sem_vencedor == 200
    assert any("não tiveram nenhuma unidade classificável" in o for o in r.observacoes)


def test_combinador_sem_peso_avisa_que_o_sorteio_e_inocuo():
    r = simular_smaa(TRES_UNIDADES, [0.5, 0.5], n=200, ids_fatores=IDS, semente=19, posicoes=3, topo=3,
                     combinador="minimo")
    assert set(np.unique(r.aceitabilidade[:, 0])) <= {0.0, 1.0}
    assert any("ignora o peso por definição" in o for o in r.observacoes)


def test_fator_de_confianca_e_medido_e_pode_dar_zero():
    """Com combinador não linear a região de pesos vencedores deixa de ser convexa e o vetor central
    pode cair fora dela — é por isso que o fator de confiança é recalculado, nunca assumido igual a 1."""
    m = [[100.0, 1.0], [1.0, 100.0], [30.0, 30.0]]
    r = simular_smaa(m, [0.5, 0.5], n=4000, ids_fatores=IDS, semente=23, posicoes=3, topo=3,
                     combinador="media_geometrica")
    ganhou = ~np.isnan(r.fator_confianca)
    assert ganhou.any()
    assert set(np.unique(r.fator_confianca[ganhou])) <= {0.0, 1.0}
    assert r.soma_aceitabilidade_primeiro == pytest.approx(1.0, abs=0.01)


def test_invariancia_a_ordem_dos_fatores():
    """Permutar fator e peso junto, com a mesma semente, dá a mesma aceitabilidade por unidade."""
    m = np.array(TRES_UNIDADES)
    a = simular_smaa(m, [0.3, 0.7], n=1000, ids_fatores=IDS, semente=31, posicoes=3, topo=3)
    b = simular_smaa(m[:, ::-1], [0.7, 0.3], n=1000, ids_fatores=IDS[::-1], semente=31, posicoes=3, topo=3)
    assert np.array_equal(a.aceitabilidade, b.aceitabilidade)


def test_contratos_recusados():
    for kwargs, codigo in (
        ({"combinador": "inexistente"}, "combinador_desconhecido"),
        ({"posicoes": 0}, "posicoes_invalidas"),
        ({"topo": 0}, "topo_invalido"),
        ({"metodo": "sorte"}, "metodo_desconhecido"),
        ({"n": 0}, "n_invalido"),
    ):
        with pytest.raises(ErroSmaa) as e:
            simular_smaa(TRES_UNIDADES, [0.5, 0.5], ids_fatores=IDS, semente=1,
                         **{"n": 10, **kwargs})
        assert e.value.codigo == codigo
    with pytest.raises(ErroSmaa) as e:
        simular_smaa([1.0, 2.0], [0.5, 0.5], n=10, ids_fatores=IDS, semente=1)
    assert e.value.codigo == "matriz_invalida"


def test_saida_carrega_referencia_e_limites(resultado):
    d = resultado.como_dicionario(NOMES)
    assert "Lahdelma" in d["referencia"] and "2001" in d["referencia"]
    assert d["limites"] == LIMITES and len(d["limites"]) >= 5
    assert d["soma_aceitabilidade_primeiro"] == pytest.approx(1.0, abs=0.01)
    assert len(d["tabela_topo"]) == 3
    assert d["tabela_topo"][0]["vetor_central"] is not None


# ---------------------------------------------------------------- o SMAA rodando COMO JOB
# Mesma disciplina do item L3-02-a: o tipo de job é exercitado com um ContextoJob de mentira (sem
# banco), e a medida de tempo grava carga, RAM e instante ao lado do número.

import datetime  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

from app.amc import tarefas as amc_tarefas  # noqa: E402
from tests.unit.test_amc_robustez_desempenho import _CtxFalso, _ram_livre_gb  # noqa: E402

UNIDADES_JOB, FATORES_JOB, SORTEIOS_JOB = 2000, 6, 1000
LIMITE_S = 60.0
CARGA_MAXIMA = 8.0


def test_job_amc_smaa_esta_registrado():
    from app.jobs import tipos

    assert "amc.smaa" in tipos.REGISTRO
    t = tipos.REGISTRO["amc.smaa"]
    assert t.funcao is amc_tarefas.amc_smaa
    assert t.pesado is True and t.timeout_s >= 60


def test_job_amc_smaa_entrega_a_tabela_do_topo_e_soma_um(medida):
    grava = medida("L3-02-c-smaa")
    carga_1min = os.getloadavg()[0]
    ram_livre = _ram_livre_gb()
    medido_em = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    contexto = f"carga_1min={carga_1min:.2f}, ram_livre_gb={ram_livre:.2f}, medido_em={medido_em}"

    rng = np.random.default_rng(4242)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES_JOB, FATORES_JOB))
    fatores = [[float(v) for v in linha] for linha in m]
    ctx = _CtxFalso()
    t0 = time.monotonic()
    saida = amc_tarefas.amc_smaa(
        ctx, fatores=fatores, pesos_base=[1.0] * FATORES_JOB,
        ids_fatores=[f"fator_{i}" for i in range(FATORES_JOB)], semente=2026, n_sorteios=SORTEIOS_JOB,
    )
    duracao_s = time.monotonic() - t0

    assert saida["n_unidades"] == UNIDADES_JOB and saida["n_sorteios"] == SORTEIOS_JOB
    assert saida["posicoes"] == 20 and saida["topo"] == 20
    assert len(saida["tabela_topo"]) == 20
    assert all(len(linha["aceitabilidade"]) == 20 for linha in saida["tabela_topo"])
    assert saida["soma_aceitabilidade_primeiro"] == pytest.approx(1.0, abs=0.01)
    assert "Lahdelma" in saida["referencia"] and len(saida["limites"]) >= 5
    assert ctx.progressos and ctx.progressos[-1] == 100

    grava("soma_aceitabilidade_primeiro", round(saida["soma_aceitabilidade_primeiro"], 6), "fração",
          f"soma de b^1 sobre as {UNIDADES_JOB} unidades em {SORTEIOS_JOB} sorteios — a conferência do "
          f"adversário do item é 1 ± 0,01; {contexto}")
    grava("linhas_da_tabela_topo", len(saida["tabela_topo"]), "unidades",
          f"tabela de aceitabilidade do top-20 sobre {UNIDADES_JOB} unidades, 20 posições por linha")
    passou = duracao_s <= LIMITE_S
    if not passou and carga_1min > CARGA_MAXIMA:
        grava("smaa_1000x2000_job_s", round(duracao_s, 3), "s",
              f"NAO MEDIDO (estourou sob disputa): {duracao_s:.3f} s > {LIMITE_S} s com carga de 1 min "
              f"{carga_1min:.2f} > {CARGA_MAXIMA} (12 núcleos); {contexto}")
        pytest.skip(f"cláusula de desempenho NÃO MEDIDA por disputa de máquina ({contexto})")
    grava("smaa_1000x2000_job_s", round(duracao_s, 3), "s",
          f"amc.smaa ({SORTEIOS_JOB} sorteios × {UNIDADES_JOB} unidades × {FATORES_JOB} fatores, "
          f"dirichlet, ContextoJob sem banco) — limite {LIMITE_S} s; {contexto}"
          + (" (passou com folga mesmo sob carga alta)" if carga_1min > CARGA_MAXIMA else ""))
    assert passou, f"{duracao_s:.3f} s > {LIMITE_S} s ({contexto})"
