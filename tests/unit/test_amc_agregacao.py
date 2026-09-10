"""Agregação célula → feição (`app.amc.agregacao`), item L3-01-j. Testes puros: sem banco, sem rede.

A regra sob teste tem quatro partes que costumam ser erradas em silêncio: o denominador da média é a área
COM DADO daquele fator (não a área total), célula vetada não entra na média mas entra na fração vetada, o
motivo que a feição carrega é o da MAIOR área vetada, e o arredondamento de empate é meio para longe do
zero (como o banco), não meio para o par (como o numpy)."""

import numpy as np
import pytest

from app.amc.agregacao import ErroAgregacao, agregar_por_feicao, arredondar_meio_para_longe_do_zero


def test_media_ponderada_por_area():
    r = agregar_por_feicao([0, 0], [3.0, 1.0], [[100.0], [0.0]])
    assert r.fatores[0, 0] == pytest.approx(75.0)
    assert r.fracao_vetada[0] == 0.0
    assert r.n_celulas.tolist() == [2]
    assert r.area_total.tolist() == [4.0]


def test_fator_ausente_nao_vira_zero():
    """A célula sem dado sai do denominador daquele fator; a feição não é punida por falta de dado."""
    r = agregar_por_feicao([0, 0], [1.0, 9.0], [[80.0, np.nan], [np.nan, 20.0]])
    assert r.fatores[0, 0] == pytest.approx(80.0)
    assert r.fatores[0, 1] == pytest.approx(20.0)


def test_feicao_sem_dado_nenhum_fica_sem_nota():
    r = agregar_por_feicao([0], [5.0], [[np.nan]])
    assert np.isnan(r.fatores[0, 0])


def test_celula_vetada_sai_da_media_e_entra_na_fracao():
    r = agregar_por_feicao([0, 0], [1.0, 3.0], [[100.0], [0.0]], vetado=[False, True])
    assert r.fatores[0, 0] == pytest.approx(100.0)   # a célula vetada não puxa a média para baixo
    assert r.fracao_vetada[0] == pytest.approx(0.75)
    assert r.n_celulas.tolist() == [1]


def test_feicao_toda_vetada():
    r = agregar_por_feicao([0, 0], [2.0, 2.0], [[10.0], [20.0]], vetado=[True, True],
                           motivo_celula=["a", "b"])
    assert r.fracao_vetada[0] == 1.0
    assert np.isnan(r.fatores[0, 0])  # nenhuma célula não vetada: sem nota, nunca zero por falta de dado
    assert r.motivo_veto[0] in ("a", "b")


def test_motivo_e_o_da_maior_area_vetada():
    r = agregar_por_feicao([0, 0, 0], [1.0, 5.0, 2.0], [[50.0], [50.0], [50.0]],
                           vetado=[True, True, False], motivo_celula=["pequeno", "grande", None])
    assert r.motivo_veto[0] == "grande"


def test_feicao_sem_veto_nao_recebe_motivo():
    r = agregar_por_feicao([0], [1.0], [[50.0]], vetado=[False], motivo_celula=["nao_vale"])
    assert r.motivo_veto == [None]
    assert r.fracao_vetada[0] == 0.0


def test_feicao_sem_par_nenhum_nao_quebra():
    """Feição declarada em `n_feicoes` sem nenhuma célula: sem nota, sem veto, área zero."""
    r = agregar_por_feicao([0], [1.0], [[70.0]], n_feicoes=3)
    assert np.isnan(r.fatores[1, 0]) and np.isnan(r.fatores[2, 0])
    assert r.fracao_vetada.tolist() == [0.0, 0.0, 0.0]
    assert r.area_total.tolist() == [1.0, 0.0, 0.0]


def test_arredondamento_de_empate_e_para_longe_do_zero():
    assert arredondar_meio_para_longe_do_zero(np.array([0.5, 1.5, 2.5, -0.5])).tolist() == [1, 2, 3, -1]
    r = agregar_por_feicao([0, 0], [1.0, 1.0], [[10.0], [11.0]], arredondar=True)
    assert r.fatores[0, 0] == 11.0  # 10,5 vira 11, não 10 (que é o que np.round faria)


def test_nulo_continua_nulo_no_arredondamento():
    r = agregar_por_feicao([0], [1.0], [[np.nan]], arredondar=True)
    assert np.isnan(r.fatores[0, 0])


@pytest.mark.parametrize("chamada, codigo", [
    (dict(indice_feicao=[0], areas=[1.0, 2.0], fatores_celula=[[1.0]]), "tamanhos_incompativeis"),
    (dict(indice_feicao=[0], areas=[-1.0], fatores_celula=[[1.0]]), "area_invalida"),
    (dict(indice_feicao=[-1], areas=[1.0], fatores_celula=[[1.0]]), "indice_negativo"),
    (dict(indice_feicao=[5], areas=[1.0], fatores_celula=[[1.0]], n_feicoes=2), "indice_fora_da_faixa"),
    (dict(indice_feicao=[0], areas=[1.0], fatores_celula=[1.0]), "matriz_invalida"),
])
def test_contrato(chamada, codigo):
    with pytest.raises(ErroAgregacao) as e:
        agregar_por_feicao(**chamada)
    assert e.value.codigo == codigo


def test_motivo_de_tamanho_errado_recusa():
    with pytest.raises(ErroAgregacao) as e:
        agregar_por_feicao([0], [1.0], [[1.0]], vetado=[True], motivo_celula=["a", "b"])
    assert e.value.codigo == "motivo_incompativel"


def test_ordem_dos_pares_nao_muda_o_resultado():
    m = [[10.0, 20.0], [30.0, np.nan], [50.0, 60.0]]
    a = [1.0, 2.0, 3.0]
    idx = [0, 0, 1]
    v = [False, True, False]
    r1 = agregar_por_feicao(idx, a, m, vetado=v)
    ordem = [2, 0, 1]
    r2 = agregar_por_feicao([idx[i] for i in ordem], [a[i] for i in ordem], [m[i] for i in ordem],
                            vetado=[v[i] for i in ordem])
    assert np.allclose(r1.fatores, r2.fatores, equal_nan=True)
    assert np.allclose(r1.fracao_vetada, r2.fracao_vetada)


def test_combina_com_o_combinador_sem_conversao():
    """A saída da agregação entra direto no combinador: matriz de fatores e fração vetada, na ordem."""
    from app.amc.combinacao import combinar

    r = agregar_por_feicao([0, 0, 1], [1.0, 1.0, 2.0], [[100.0, 50.0], [0.0, 50.0], [80.0, np.nan]],
                            vetado=[False, True, False])
    c = combinar(r.fatores, [1.0, 1.0], fracao_vetada=r.fracao_vetada, ids_fatores=["a", "b"])
    assert c.fav[0] == pytest.approx(((100.0 + 50.0) / 2) * (1 - 0.5))
    assert c.fav[1] == pytest.approx(80.0)
