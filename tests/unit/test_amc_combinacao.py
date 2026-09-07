"""Casos de borda e contrato do combinador do motor multicritério (item L3-01-e-combinacao).

Cada combinador é exercido com: todos os fatores nulos, um fator só, e pesos iguais. O modo percentual
recusa soma diferente de 100. A frase "pesos escolhidos pelo usuário, não medidos" aparece em todo
resultado, porque os pesos são escolha de quem usa o produto e nunca uma medida da casa.
"""

import math

import pytest

from app.amc.combinacao import (
    AVISO_PESOS,
    COMBINADORES,
    POLITICAS_AUSENTE,
    SEM_PESO,
    ErroCombinacao,
    combinar,
)

TODOS = sorted(COMBINADORES)


def pesos_de(combinador, n):
    """Pesos válidos para o combinador: percentuais que fecham 100 no modo percentual, 1 nos demais."""
    return [100.0 / n] * n if combinador == "percentual" else [1.0] * n


@pytest.mark.parametrize("combinador", TODOS)
def test_todos_os_fatores_nulos_saem_sem_nota_e_nunca_como_zero(combinador):
    r = combinar([[None, None, None]], pesos_de(combinador, 3), combinador=combinador)
    assert math.isnan(r.fav[0])
    assert r.como_dicionario()["fav"] == [None]
    assert r.cobertura[0] == 0.0
    assert "1 de 1 unidades ficaram sem nota por falta de dado" in r.observacoes


@pytest.mark.parametrize("combinador", TODOS)
def test_um_fator_so_devolve_a_propria_nota_daquele_fator(combinador):
    r = combinar([[40.0]], pesos_de(combinador, 1), combinador=combinador)
    assert r.fav[0] == pytest.approx(40.0, abs=0.5)
    assert r.cobertura[0] == 1.0


@pytest.mark.parametrize("combinador", TODOS)
def test_pesos_iguais_dao_resultado_simetrico_na_ordem_dos_fatores(combinador):
    p = pesos_de(combinador, 3)
    direta = combinar([[80.0, 20.0, 60.0]], p, combinador=combinador).fav[0]
    trocada = combinar([[60.0, 80.0, 20.0]], p, combinador=combinador).fav[0]
    assert direta == pytest.approx(trocada, abs=1e-9)


@pytest.mark.parametrize("combinador", TODOS)
def test_a_frase_dos_pesos_acompanha_todo_resultado(combinador):
    r = combinar([[10.0, 90.0]], pesos_de(combinador, 2), combinador=combinador)
    assert r.aviso_pesos == AVISO_PESOS == "pesos escolhidos pelo usuário, não medidos"
    assert r.como_dicionario()["aviso_pesos"] == AVISO_PESOS


def test_modo_percentual_recusa_soma_diferente_de_100():
    with pytest.raises(ErroCombinacao) as e:
        combinar([[10.0, 20.0]], [50.0, 40.0], combinador="percentual")
    assert e.value.codigo == "percentual_nao_soma_100"
    assert "somaram 90" in e.value.mensagem
    with pytest.raises(ErroCombinacao) as e:
        combinar([[10.0, 20.0]], [50.0, 60.0], combinador="percentual")
    assert e.value.codigo == "percentual_nao_soma_100"
    # a mesma soma fechando 100 passa
    assert combinar([[10.0, 20.0]], [50.0, 50.0], combinador="percentual").fav[0] == pytest.approx(15.0)


def test_modo_percentual_arredonda_ao_inteiro_e_declara_a_perda_de_precisao():
    r = combinar([[10.0, 21.0]], [50.0, 50.0], combinador="percentual")
    assert r.fav[0] == 16.0  # 15,5 arredondado
    assert any("perde precisão" in o for o in r.observacoes)


def test_padrao_e_a_soma_ponderada_normalizada_sobre_os_fatores_com_dado():
    # 100 com peso 1 e 50 com peso 1; o terceiro fator, de peso 2, não tem dado e sai da conta
    r = combinar([[100.0, 50.0, None]], [1.0, 1.0, 2.0])
    assert r.combinador == "soma_ponderada"
    assert r.fav[0] == pytest.approx(75.0)
    assert r.cobertura[0] == pytest.approx(0.5)


@pytest.mark.parametrize("politica", sorted(POLITICAS_AUSENTE))
def test_as_tres_politicas_de_dado_ausente_dao_respostas_diferentes_e_declaradas(politica):
    r = combinar([[100.0, 50.0, None]], [1.0, 1.0, 2.0], politica_ausente=politica)
    esperado = {"excluir": 75.0, "pessimista": 37.5}
    if politica == "nulo":
        assert math.isnan(r.fav[0])
    else:
        assert r.fav[0] == pytest.approx(esperado[politica])
    assert r.politica_ausente == politica


def test_media_geometrica_anula_a_nota_quando_um_fator_e_zero():
    assert combinar([[0.0, 100.0]], [1.0, 1.0], combinador="media_geometrica").fav[0] == 0.0
    assert combinar([[0.0, 100.0]], [1.0, 1.0]).fav[0] == pytest.approx(50.0)


def test_veto_zera_a_nota_e_grava_o_motivo_sem_depender_de_peso():
    r = combinar([[100.0, 100.0]], [1.0, 1.0], fracao_vetada=[1.0])
    assert r.fav[0] == 0.0 and bool(r.vetado[0])
    assert r.motivo[0] == "unidade inteiramente coberta por restrição declarada no modelo"
    assert any("por restrição, não por peso" in o for o in r.observacoes)


def test_veto_parcial_multiplica_a_nota_pela_fracao_livre():
    r = combinar([[80.0, 80.0]], [1.0, 3.0], fracao_vetada=[0.25])
    assert r.fav[0] == pytest.approx(60.0)
    assert not bool(r.vetado[0])


def test_unidade_sem_dado_e_vetada_continua_sem_nota_em_vez_de_virar_zero():
    r = combinar([[None, None]], [1.0, 1.0], fracao_vetada=[1.0])
    assert math.isnan(r.fav[0]) and bool(r.vetado[0])
    assert r.como_dicionario()["fav"] == [None]


@pytest.mark.parametrize("combinador", sorted(SEM_PESO))
def test_combinador_fuzzy_declara_que_nao_usa_peso(combinador):
    r = combinar([[10.0, 90.0]], [1.0, 9.0], combinador=combinador)
    igual = combinar([[10.0, 90.0]], [1.0, 1.0], combinador=combinador)
    assert r.fav[0] == pytest.approx(igual.fav[0])
    assert any("não usa peso por definição matemática" in o for o in r.observacoes)
