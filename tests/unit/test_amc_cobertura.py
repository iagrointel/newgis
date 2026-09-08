"""Testes do item L3-14-cobertura-dado-ausente: cobertura por fator.

Cláusula do portão coberta aqui: "teste injeta NULL em 30 % de um fator e confere favorabilidade
recalculada só com os presentes e cobertura 70 % exibida".
"""

from __future__ import annotations

import numpy as np
import pytest

from app.amc import cobertura as mod_cobertura
from app.amc import combinacao as mod_combinacao


def _matriz_com_ausencia(n_unidades: int, fracao_ausente: float, semente: int = 7):
    """Uma matriz de 1 fator só, com `fracao_ausente` das unidades em None e o resto em 60.0
    (valor fixo e distinto de 0/100 para nunca se confundir com dado ausente virando extremo)."""
    rng = np.random.default_rng(semente)
    n_ausentes = round(n_unidades * fracao_ausente)
    indices_ausentes = set(rng.choice(n_unidades, size=n_ausentes, replace=False).tolist())
    linhas = [[None] if i in indices_ausentes else [60.0] for i in range(n_unidades)]
    return linhas, indices_ausentes


def test_cobertura_70_por_cento_com_30_por_cento_de_ausencia():
    linhas, ausentes = _matriz_com_ausencia(100, 0.30)
    assert len(ausentes) == 30

    coberturas = mod_cobertura.cobertura_por_fator(linhas, ["f1"])
    assert len(coberturas) == 1
    c = coberturas[0]
    assert c.n_total == 100
    assert c.n_presentes == 70
    assert c.fracao_unidades == pytest.approx(0.70)
    assert c.abaixo_do_limiar is True  # 70 % < limiar padrão 80 %


def test_favorabilidade_recalculada_so_com_os_presentes():
    """Com política 'excluir' (padrão), a unidade com o fator ausente recebe nota a partir dos
    fatores QUE TEM, nunca com o ausente contando como 0."""
    linhas, ausentes = _matriz_com_ausencia(100, 0.30)
    # segundo fator sempre presente, valor fixo 40.0, para toda unidade ter ao menos um fator
    fatores = [[linha[0], 40.0] for linha in linhas]
    pesos = [1.0, 1.0]

    resultado = mod_combinacao.combinar(fatores, pesos, politica_ausente="excluir")

    for i, _linha in enumerate(fatores):
        nota = resultado.fav[i]
        if i in ausentes:
            # só o fator 2 (40.0) entra na conta: soma_ponderada = (1*40)/1 = 40
            assert nota == pytest.approx(40.0), f"unidade {i} com fator ausente não pode herdar 0"
        else:
            # os dois fatores entram: (1*60 + 1*40)/2 = 50
            assert nota == pytest.approx(50.0)


def test_ausencia_nunca_vira_zero_nem_cem_na_cobertura():
    """Regra dura do motor: NULL nunca vira 0 nem 100 em nenhum caminho de código."""
    linhas = [[None], [None], [None]]
    c = mod_cobertura.cobertura_por_fator(linhas, ["f1"])[0]
    assert c.n_presentes == 0
    assert c.fracao_unidades == 0.0  # fração de presença zero é honesta; não é o VALOR do fator
    assert c.area_total is None
    assert c.area_coberta is None
    assert c.fracao_area is None


def test_cobertura_de_area_soma_area_das_unidades_com_dado():
    linhas = [[60.0], [None], [60.0], [None]]
    areas = [10.0, 20.0, 30.0, 5.0]
    c = mod_cobertura.cobertura_por_fator(linhas, ["f1"], areas=areas)[0]
    assert c.area_total == pytest.approx(65.0)
    assert c.area_coberta == pytest.approx(40.0)
    assert c.fracao_area == pytest.approx(40.0 / 65.0)


def test_limiar_customizado_marca_diferente():
    linhas, _ = _matriz_com_ausencia(100, 0.30)
    coberturas_80 = mod_cobertura.cobertura_por_fator(linhas, ["f1"], limiar=0.80)
    coberturas_60 = mod_cobertura.cobertura_por_fator(linhas, ["f1"], limiar=0.60)
    assert coberturas_80[0].abaixo_do_limiar is True
    assert coberturas_60[0].abaixo_do_limiar is False


def test_erro_quando_ids_incompativeis():
    with pytest.raises(mod_cobertura.ErroCobertura) as exc:
        mod_cobertura.cobertura_por_fator([[1.0, 2.0]], ["so_um_id"])
    assert exc.value.codigo == "ids_incompativeis"


def test_erro_quando_sem_fatores():
    with pytest.raises(mod_cobertura.ErroCobertura) as exc:
        mod_cobertura.cobertura_por_fator([[], []], [])
    assert exc.value.codigo == "sem_fatores"


def test_erro_quando_area_nao_finita():
    with pytest.raises(mod_cobertura.ErroCobertura) as exc:
        mod_cobertura.cobertura_por_fator([[1.0], [2.0]], ["f1"], areas=[10.0, float("nan")])
    assert exc.value.codigo == "area_nao_finita"


def test_erro_quando_limiar_fora_da_faixa():
    with pytest.raises(mod_cobertura.ErroCobertura) as exc:
        mod_cobertura.cobertura_por_fator([[1.0]], ["f1"], limiar=1.5)
    assert exc.value.codigo == "limiar_fora_da_faixa"
