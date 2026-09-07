"""Refutação exigida pelo item L3-02-a: o adversário permuta a ordem dos fatores e reexecuta com a
mesma semente — o resultado por unidade tem de ser IDÊNTICO (o sorteio é ancorado no ID do fator, nunca
na posição de entrada); e confere que a unidade vetada nunca aparece no top-k, mesmo variando semente,
método e concentração."""

import numpy as np
import pytest

from app.amc import robustez


def _permutar(fatores, pesos_base, ids_fatores, ordem):
    f = np.asarray(fatores)[:, ordem]
    p = [pesos_base[i] for i in ordem]
    ids = [ids_fatores[i] for i in ordem]
    return f, p, ids


@pytest.mark.parametrize("metodo,kwargs", [
    ("dirichlet", {}),
    ("dirichlet", {"concentracao": 5.0}),
    ("faixa", {"k_percentual": 0.4}),
])
def test_permutar_fatores_da_o_mesmo_resultado_bit_a_bit(metodo, kwargs):
    rng = np.random.default_rng(11)
    fatores = rng.uniform(0, 100, size=(60, 5))
    pesos_base = [3.0, 1.0, 2.0, 0.5, 4.0]
    ids_fatores = ["custo", "atracao", "risco", "rito", "veto_precaucao"]

    r_original = robustez.simular_robustez(
        fatores, pesos_base, n=200, metodo=metodo, semente=2026, ids_fatores=ids_fatores, **kwargs,
    )

    ordem = [3, 1, 4, 0, 2]  # embaralha as colunas
    f_perm, p_perm, ids_perm = _permutar(fatores, pesos_base, ids_fatores, ordem)
    r_permutado = robustez.simular_robustez(
        f_perm, p_perm, n=200, metodo=metodo, semente=2026, ids_fatores=ids_perm, **kwargs,
    )

    # o sorteio em si (semente -> peso por ID) é idêntico bit a bit; a NOTA final soma os fatores em
    # ordem de coluna diferente (colunas permutadas), e soma de ponto flutuante não é perfeitamente
    # associativa — por isso a comparação da nota usa tolerância apertada (1e-9), não igualdade exata.
    # Contagem/frequência/estabilidade são inteiros derivados de RANKING, não de soma: permanecem exatos.
    assert np.allclose(r_original.media, r_permutado.media, atol=1e-9, equal_nan=True)
    assert np.allclose(r_original.minimo, r_permutado.minimo, atol=1e-9, equal_nan=True)
    assert np.allclose(r_original.maximo, r_permutado.maximo, atol=1e-9, equal_nan=True)
    assert np.allclose(r_original.desvio, r_permutado.desvio, atol=1e-9, equal_nan=True)
    assert np.array_equal(r_original.frequencia_topk, r_permutado.frequencia_topk)
    assert np.array_equal(r_original.frequencia_decil_superior, r_permutado.frequencia_decil_superior)
    assert np.array_equal(r_original.estavel, r_permutado.estavel)
    assert r_original.pesos_base_normalizados == pytest.approx(
        [p_perm[ids_perm.index(fid)] / sum(p_perm) for fid in ids_fatores]
    )


def test_permutar_e_a_ordem_de_ids_fatores_no_resultado_muda_mas_os_valores_por_id_nao():
    rng = np.random.default_rng(3)
    fatores = rng.uniform(0, 100, size=(30, 3))
    pesos_base = [1.0, 5.0, 2.0]
    ids_fatores = ["a", "b", "c"]
    r1 = robustez.simular_robustez(fatores, pesos_base, n=150, semente=7, ids_fatores=ids_fatores)

    ordem = [2, 0, 1]
    f2, p2, ids2 = _permutar(fatores, pesos_base, ids_fatores, ordem)
    r2 = robustez.simular_robustez(f2, p2, n=150, semente=7, ids_fatores=ids2)

    assert r1.ids_fatores == ["a", "b", "c"]
    assert r2.ids_fatores == ["c", "a", "b"]
    # o peso normalizado de cada FATOR (por id) é o mesmo nos dois, só a posição na lista muda
    peso_por_id_1 = dict(zip(r1.ids_fatores, r1.pesos_base_normalizados, strict=True))
    peso_por_id_2 = dict(zip(r2.ids_fatores, r2.pesos_base_normalizados, strict=True))
    for fid in ids_fatores:
        assert peso_por_id_1[fid] == pytest.approx(peso_por_id_2[fid])


def test_unidade_vetada_nunca_no_topk_em_varios_metodos_semente_e_concentracao():
    rng = np.random.default_rng(21)
    n_unidades = 40
    fatores = rng.uniform(0, 100, size=(n_unidades, 4))
    # a unidade 0 recebe a nota máxima em todo fator: sem o veto, ganharia disparado
    fatores[0] = 100.0
    fracao_vetada = [1.0] + [0.0] * (n_unidades - 1)
    ids_fatores = ["f0", "f1", "f2", "f3"]

    casos = [
        dict(metodo="dirichlet", semente=1),
        dict(metodo="dirichlet", semente=999, concentracao=8.0),
        dict(metodo="faixa", semente=42, k_percentual=0.6),
    ]
    for kwargs in casos:
        r = robustez.simular_robustez(
            fatores, [1.0, 1.0, 1.0, 1.0], n=250, ids_fatores=ids_fatores,
            fracao_vetada=fracao_vetada, k_top=3, **kwargs,
        )
        assert r.vetado[0]
        assert r.frequencia_topk[0] == 0.0, f"unidade vetada apareceu no top-k com {kwargs}"
        assert r.frequencia_decil_superior[0] == 0.0, f"unidade vetada apareceu no decil superior com {kwargs}"
