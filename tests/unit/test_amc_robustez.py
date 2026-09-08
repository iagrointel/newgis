"""Robustez do motor multicritério por sorteio de pesos (item L3-02-a). Sem banco: `simular_robustez`
e `sortear_pesos` são puros (numpy), como o combinador que reusam (`app.amc.combinacao`, item L3-01-e).

Cláusulas do portão de pronto cobertas aqui:
- semente gravada e resultado reproduzível bit a bit com a mesma semente;
- modelo de 2 fatores de resposta analítica conhecida;
- vetos e restrições nunca sorteados (a fração vetada é fixa e a unidade sai da classificação por
  construção, nunca por sorte).
A cláusula de desempenho (1.000 sorteios em 5.000 unidades em ≤ 60 s como job) está em
`test_amc_robustez_desempenho.py`; a refutação do adversário (permutar a ordem dos fatores) está em
`test_amc_robustez_adversario.py`."""

import numpy as np
import pytest

from app.amc import robustez


def test_metodo_desconhecido_e_recusado():
    with pytest.raises(robustez.ErroRobustez, match="método"):
        robustez.sortear_pesos([1.0, 1.0], ["a", "b"], 10, metodo="otimizacao", semente=1)


def test_reproducao_bit_a_bit_com_a_mesma_semente():
    fatores = np.random.default_rng(0).uniform(0, 100, size=(200, 5))
    kwargs = dict(n=300, metodo="dirichlet", semente=42, ids_fatores=[f"f{i}" for i in range(5)])
    r1 = robustez.simular_robustez(fatores, [1, 2, 1, 3, 1], **kwargs)
    r2 = robustez.simular_robustez(fatores, [1, 2, 1, 3, 1], **kwargs)
    assert np.array_equal(r1.media, r2.media, equal_nan=True)
    assert np.array_equal(r1.minimo, r2.minimo, equal_nan=True)
    assert np.array_equal(r1.maximo, r2.maximo, equal_nan=True)
    assert np.array_equal(r1.desvio, r2.desvio, equal_nan=True)
    assert np.array_equal(r1.frequencia_topk, r2.frequencia_topk)
    assert np.array_equal(r1.frequencia_decil_superior, r2.frequencia_decil_superior)
    assert r1.semente == r2.semente == 42


def test_semente_diferente_da_resultado_diferente():
    fatores = np.random.default_rng(0).uniform(0, 100, size=(200, 5))
    kwargs = dict(n=300, metodo="dirichlet", ids_fatores=[f"f{i}" for i in range(5)])
    r1 = robustez.simular_robustez(fatores, [1, 2, 1, 3, 1], semente=1, **kwargs)
    r2 = robustez.simular_robustez(fatores, [1, 2, 1, 3, 1], semente=2, **kwargs)
    assert not np.array_equal(r1.media, r2.media)


def test_faixa_tambem_reproduz_bit_a_bit():
    fatores = np.random.default_rng(0).uniform(0, 100, size=(50, 3))
    kwargs = dict(n=100, metodo="faixa", k_percentual=0.4, semente=7, ids_fatores=["a", "b", "c"])
    r1 = robustez.simular_robustez(fatores, [1, 1, 1], **kwargs)
    r2 = robustez.simular_robustez(fatores, [1, 1, 1], **kwargs)
    assert np.array_equal(r1.media, r2.media, equal_nan=True)


def test_modelo_de_2_fatores_resposta_analitica_conhecida():
    """Duas unidades, dois fatores puros: A só tem fator 1 (100/0), B só tem fator 2 (0/100). Com
    Dirichlet(1,1) (uniforme em [0,1] no peso do fator 1), fav_A = 100·w1 e fav_B = 100·(1−w1) — a
    resposta é linear e conhecida. A média de 1.000 sorteios tem de ficar perto de 50 (esperança
    analítica) e o mínimo/máximo tem de varrer perto dos extremos 0 e 100."""
    fatores = np.array([[100.0, 0.0], [0.0, 100.0]])
    r = robustez.simular_robustez(
        fatores, [1.0, 1.0], n=1000, metodo="dirichlet", semente=123,
        ids_fatores=["f1", "f2"], k_top=1, decil_superior=0.5,
    )
    assert r.media[0] == pytest.approx(50.0, abs=6.0)
    assert r.media[1] == pytest.approx(50.0, abs=6.0)
    # complementares: fav_A + fav_B = 100 sempre (w1 + w2 = 1 no simplex de 2 fatores)
    assert r.media[0] + r.media[1] == pytest.approx(100.0, abs=1e-6)
    assert r.minimo[0] < 5.0 and r.maximo[0] > 95.0
    # nenhuma das duas é "vetada" nem inexistente: cobertura total, sem NaN
    assert not np.isnan(r.media).any()


def test_faixa_em_modelo_analitico_fica_dentro_do_intervalo_declarado():
    """Faixa ± k %: com pesos base iguais e k=0,5, o peso do fator 1 fica em [0,5; 1,5] (antes de
    normalizar pelo combinador) — logo a fração normalizada do fator 1 fica em [0,5/2,5%; 1,5/1,5%]
    aproximadamente [0,25; 0,75], e fav_A = 100 × fração fica dentro de [25, 75] em todo sorteio."""
    fatores = np.array([[100.0, 0.0], [0.0, 100.0]])
    r = robustez.simular_robustez(
        fatores, [1.0, 1.0], n=500, metodo="faixa", k_percentual=0.5, semente=9,
        ids_fatores=["f1", "f2"], k_top=1,
    )
    assert 20.0 <= r.minimo[0] <= 30.0
    assert 70.0 <= r.maximo[0] <= 80.0


def test_veto_e_restricao_nunca_sorteados_unidade_vetada_fora_do_topo():
    """A unidade 0 é 100 % vetada (fração 1,0) e teria a MAIOR nota bruta de todas — mesmo assim nunca
    pode aparecer no top-k em nenhum dos sorteios, porque o veto é fixo e a exclusão é por construção,
    não por a nota cair (a nota bruta dela, sem veto, seria a mais alta do conjunto)."""
    fatores = np.array([[100.0, 100.0], [50.0, 50.0], [10.0, 10.0], [5.0, 5.0], [1.0, 1.0]])
    fracao_vetada = [1.0, 0.0, 0.0, 0.0, 0.0]
    r = robustez.simular_robustez(
        fatores, [1.0, 1.0], n=300, metodo="dirichlet", semente=5,
        ids_fatores=["f1", "f2"], fracao_vetada=fracao_vetada, k_top=1,
    )
    assert r.vetado[0]
    assert r.frequencia_topk[0] == 0.0
    assert not r.estavel[0]


def test_fracao_vetada_fixa_em_todos_os_sorteios_nao_e_parametro_do_sorteio():
    """`fracao_vetada` não faz parte do espaço sorteado: mudar a semente não muda quem está vetado."""
    fatores = np.array([[100.0, 0.0], [0.0, 100.0], [50.0, 50.0]])
    fracao_vetada = [1.0, 0.0, 0.0]
    r1 = robustez.simular_robustez(fatores, [1, 1], n=50, semente=1, ids_fatores=["f1", "f2"],
                                    fracao_vetada=fracao_vetada)
    r2 = robustez.simular_robustez(fatores, [1, 1], n=50, semente=99, ids_fatores=["f1", "f2"],
                                    fracao_vetada=fracao_vetada)
    assert np.array_equal(r1.vetado, r2.vetado)
    assert r1.vetado[0] and r2.vetado[0]


def test_estavel_quando_frequencia_no_topk_e_pelo_menos_95_por_cento():
    fatores = np.array([[100.0, 100.0], [1.0, 1.0], [0.0, 0.0]])
    r = robustez.simular_robustez(fatores, [1, 1], n=400, semente=3, ids_fatores=["f1", "f2"], k_top=1)
    assert r.estavel[0]
    assert r.frequencia_topk[0] == 1.0


def test_pesos_negativos_ou_todos_zero_sao_recusados():
    with pytest.raises(robustez.ErroRobustez, match="peso base"):
        robustez.sortear_pesos([0.0, 0.0], ["a", "b"], 10, semente=1)
    with pytest.raises(robustez.ErroRobustez, match="peso base"):
        robustez.sortear_pesos([-1.0, 2.0], ["a", "b"], 10, semente=1)


def test_ids_incompativeis_com_pesos_e_recusado():
    with pytest.raises(robustez.ErroRobustez, match="ids_incompativeis|identificadores"):
        robustez.sortear_pesos([1.0, 1.0, 1.0], ["a", "b"], 10, semente=1)


def test_como_dicionario_traz_o_aviso_de_sensibilidade_nunca_peso_otimo():
    fatores = np.array([[100.0, 0.0], [0.0, 100.0]])
    r = robustez.simular_robustez(fatores, [1, 1], n=20, semente=1, ids_fatores=["f1", "f2"])
    d = r.como_dicionario()
    assert "sensibilidade" in d["aviso_pesos"]
    # a frase pode CITAR "peso ótimo" só para negar que ele exista aqui, nunca para afirmar um valor:
    assert "peso ótimo aqui" in d["aviso_pesos"] or "não existe peso ótimo" in d["aviso_pesos"]
    assert d["semente"] == 1 and d["n_sorteios"] == 20
